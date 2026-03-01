"""MCP tool handlers: batch tools.

Tools registered here:
- validate_batch
- autofix_batch

Note: autofix_batch calls autofix_file by importing from mcp_tools_fix at call time
to avoid module-level circular imports.

WS6: Both batch tools are async and accept an optional FastMCP Context for per-file
progress notifications. Clients that do not support progress are unaffected — the
final batch JSON result is identical to the sync version.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from twincat_validator import TwinCATFile
from twincat_validator._server_helpers import (
    _convert_engine_result_to_mcp_format,
    _resolve_execution_context,
    _validate_enforcement_mode,
    _validate_format_profile,
    _validate_profile,
)
from twincat_validator.mcp_app import (
    DEFAULT_ENFORCEMENT_MODE,
    config,
    mcp,
    validation_engine,
)
from twincat_validator.mcp_responses import _tool_error, _with_meta, unresolved_policy_fields
from twincat_validator.result_contract import derive_contract_state
from twincat_validator.utils import _VALID_INTENT_PROFILES, _batch_auto_resolve_intent


def _aggregate_batch_blockers(files: list[dict]) -> list[dict]:
    """Aggregate blocker entries from validate_batch per-file items."""
    blockers: list[dict] = []
    for item in files:
        for blocker in item.get("blockers", []) or []:
            blockers.append(
                {
                    "file_path": item.get("file_path", ""),
                    "check": blocker.get("check", blocker.get("category", "unknown")),
                    "message": blocker.get("message", ""),
                    "line": blocker.get("line_num", blocker.get("line")),
                }
            )
    return blockers


def _assert_validate_batch_contract(result: dict) -> None:
    """Fail-closed contract for validate_batch top-level response shape."""
    required: dict[str, type] = {
        "success": bool,
        "batch_id": str,
        "processed_files": int,
        "total_files": int,
        "batch_summary": dict,
        "files": list,
        "failed_files": list,
        "safe_to_import": bool,
        "safe_to_compile": bool,
        "done": bool,
        "status": str,
        "blocking_count": int,
        "blockers": list,
        "next_action": str,
    }
    for key, expected_type in required.items():
        if key not in result:
            raise ValueError(f"Contract violation: missing required key '{key}'")
        if not isinstance(result[key], expected_type):
            raise ValueError(
                f"Contract violation: key '{key}' expected {expected_type.__name__}, "
                f"got {type(result[key]).__name__}"
            )
    if result["status"] not in {"done", "blocked"}:
        raise ValueError("Contract violation: status must be 'done' or 'blocked'")


def _assert_autofix_batch_contract(result: dict) -> None:
    """Fail-closed contract for autofix_batch top-level response shape."""
    required: dict[str, type] = {
        "success": bool,
        "batch_id": str,
        "processed_files": int,
        "total_files": int,
        "batch_summary": dict,
        "done": bool,
        "status": str,
        "safe_to_import": bool,
        "safe_to_compile": bool,
        "blocking_count": int,
        "blockers": list,
        "files": list,
        "failed_files": list,
        "terminal_mode": bool,
        "next_action": str,
    }
    for key, expected_type in required.items():
        if key not in result:
            raise ValueError(f"Contract violation: missing required key '{key}'")
        if not isinstance(result[key], expected_type):
            raise ValueError(
                f"Contract violation: key '{key}' expected {expected_type.__name__}, "
                f"got {type(result[key]).__name__}"
            )
    if result["status"] not in {"done", "blocked"}:
        raise ValueError("Contract violation: status must be 'done' or 'blocked'")


async def _emit_progress(ctx: Optional[Any], current: int, total: int, message: str) -> None:
    """Best-effort progress notification; silently swallows errors for non-supporting clients."""
    if ctx is None:
        return
    try:
        await ctx.report_progress(progress=float(current), total=float(total), message=message)
    except Exception:
        pass


def register_batch_tools() -> None:
    """Register all batch tool handlers with the mcp instance."""

    @mcp.tool()
    async def validate_batch(
        file_patterns: list[str],
        directory_path: str = ".",
        validation_level: str = "all",
        enforcement_mode: str = DEFAULT_ENFORCEMENT_MODE,
        intent_profile: str = "auto",
        ctx: Optional[Any] = None,
    ) -> str:
        """Validate multiple TwinCAT files matching glob patterns.

        Args:
            file_patterns: Glob patterns (e.g., ["*.TcPOU"])
            directory_path: Base directory
            validation_level: "all", "critical", or "style"
            intent_profile: Programming paradigm intent — "auto" (default), "procedural",
                or "oop".  With "auto", the matched .TcPOU files are scanned for EXTENDS/
                IMPLEMENTS; if any are found the batch resolves to "oop", otherwise "procedural".
            ctx: FastMCP context for per-file progress notifications (injected automatically)
        """
        _t0 = time.monotonic()
        ctx_policy = None
        try:
            mode_error = _validate_enforcement_mode(enforcement_mode, start_time=_t0)
            if mode_error:
                return mode_error
            ctx_policy = _resolve_execution_context(
                directory_path, enforcement_mode=enforcement_mode
            )
            if intent_profile not in _VALID_INTENT_PROFILES:
                return _tool_error(
                    f"Invalid intent_profile: {intent_profile}",
                    start_time=_t0,
                    execution_context=ctx_policy,
                    valid_intent_profiles=list(_VALID_INTENT_PROFILES),
                )
            from glob import glob

            start_time = time.time()
            base_path = Path(directory_path)

            if not base_path.exists():
                return _tool_error(
                    f"Directory not found: {directory_path}",
                    start_time=_t0,
                    execution_context=ctx_policy,
                    error_type="DirectoryNotFoundError",
                )

            all_files: set[Path] = set()
            for pattern in file_patterns:
                pattern_path = base_path / pattern
                matches = glob(str(pattern_path), recursive=True)
                all_files.update(Path(f) for f in matches)

            tc_files = [f for f in all_files if f.suffix in config.supported_extensions]

            # Resolve intent after file discovery so "auto" can scan .TcPOU declarations.
            _intent_resolved = _batch_auto_resolve_intent(tc_files, intent_profile)
            _exclude_cats = frozenset({"oop"}) if _intent_resolved == "procedural" else None

            if not tc_files:
                return _tool_error(
                    "No TwinCAT files found matching patterns",
                    start_time=_t0,
                    execution_context=ctx_policy,
                    patterns=file_patterns,
                    directory=str(base_path),
                )

            total = len(tc_files)
            results = []
            failed_files = []
            passed = 0
            failed = 0
            warnings = 0

            for idx, file_path in enumerate(tc_files):
                await _emit_progress(
                    ctx,
                    current=idx,
                    total=total,
                    message=f"validate {idx + 1}/{total}: {file_path.name}",
                )
                try:
                    file = TwinCATFile.from_path(file_path)
                    validation_time_start = time.time()
                    engine_result = validation_engine.validate(
                        file, validation_level, exclude_categories=_exclude_cats
                    )
                    validation_time = time.time() - validation_time_start

                    file_result = _convert_engine_result_to_mcp_format(
                        engine_result, file, validation_time, validation_level
                    )

                    status = file_result["validation_status"]
                    if status == "passed":
                        passed += 1
                    elif status == "failed":
                        failed += 1
                    elif status == "warnings":
                        warnings += 1

                    # Derive per-file contract state canonically (RC-1).
                    per_file_cs = derive_contract_state(file_result.get("issues", []))
                    results.append(
                        {
                            "file_path": str(file_path),
                            "status": status,
                            # error_count from canonical contract (issues with severity error/critical),
                            # not summary["failed"] which counts failed checks, not error issues.
                            "error_count": per_file_cs.error_count,
                            "warning_count": per_file_cs.warning_count,
                            # Flat per-file safety schema for consistency with process_twincat_batch
                            "safe_to_import": per_file_cs.safe_to_import,
                            "safe_to_compile": per_file_cs.safe_to_compile,
                            "blocking_count": per_file_cs.blocking_count,
                            "blockers": per_file_cs.blockers,
                            "validation_result": file_result,
                        }
                    )

                except Exception as e:
                    failed_files.append(
                        {
                            "file_path": str(file_path),
                            "error": str(e),
                            "error_type": type(e).__name__,
                        }
                    )
                    failed += 1

            await _emit_progress(ctx, current=total, total=total, message="validate complete")

            batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            safe_to_import = (
                all(bool(item.get("safe_to_import", False)) for item in results)
                if results
                else False
            )
            safe_to_compile = (
                all(bool(item.get("safe_to_compile", False)) for item in results)
                if results
                else False
            )
            done = failed == 0 and safe_to_import and safe_to_compile
            blockers = _aggregate_batch_blockers(results)
            result = {
                "success": True,
                "batch_id": batch_id,
                "processed_files": len(results),
                "total_files": total,
                "processing_time": round(time.time() - start_time, 3),
                "batch_summary": {"passed": passed, "failed": failed, "warnings": warnings},
                "files": results,
                "failed_files": failed_files,
                "safe_to_import": safe_to_import,
                "safe_to_compile": safe_to_compile,
                "done": done,
                "status": "done" if done else "blocked",
                "blocking_count": len(blockers),
                "blockers": blockers,
                "next_action": (
                    "done_no_further_validation" if done else "manual_intervention_or_targeted_fix"
                ),
            }
            _assert_validate_batch_contract(result)

            return _with_meta(result, _t0, execution_context=ctx_policy)

        except Exception as e:
            error_kwargs = {"execution_context": ctx_policy}
            if ctx_policy is None:
                error_kwargs.update(unresolved_policy_fields(enforcement_mode))
            return _tool_error(str(e), start_time=_t0, **error_kwargs)

    @mcp.tool()
    async def autofix_batch(
        file_patterns: list[str],
        directory_path: str = ".",
        create_backup: bool = True,
        profile: str = "llm_strict",
        format_profile: str = "twincat_canonical",
        strict_contract: bool = True,
        create_implicit_files: bool = True,
        orchestration_hints: bool = True,
        enforcement_mode: str = DEFAULT_ENFORCEMENT_MODE,
        intent_profile: str = "auto",
        ctx: Optional[Any] = None,
    ) -> str:
        """Automatically fix multiple TwinCAT files matching glob patterns.

        Args:
            file_patterns: Glob patterns (e.g., ["*.TcPOU"])
            directory_path: Base directory
            create_backup: Create backup files before fixing
            profile: Response profile passed to per-file autofix (default: llm_strict)
            format_profile: Formatting profile for per-file autofix
            strict_contract: Enforce generation contract fail-closed in per-file autofix
            create_implicit_files: Auto-create missing interface/DUT dependencies
            orchestration_hints: Include loop-guard hints in per-file responses
            intent_profile: Programming paradigm intent — "auto" (default), "procedural",
                or "oop".  With "auto", each file's content is inspected individually for
                EXTENDS/IMPLEMENTS, so OOP files receive full OOP checks even in mixed batches.
            ctx: FastMCP context for per-file progress notifications (injected automatically)
        """
        _t0 = time.monotonic()
        ctx_policy = None
        try:
            mode_error = _validate_enforcement_mode(enforcement_mode, start_time=_t0)
            if mode_error:
                return mode_error
            ctx_policy = _resolve_execution_context(
                directory_path, enforcement_mode=enforcement_mode
            )
            if intent_profile not in _VALID_INTENT_PROFILES:
                return _tool_error(
                    f"Invalid intent_profile: {intent_profile}",
                    start_time=_t0,
                    execution_context=ctx_policy,
                    valid_intent_profiles=list(_VALID_INTENT_PROFILES),
                )
            from glob import glob

            # Import autofix_file lazily to avoid module-level registration order issues.
            from twincat_validator.server import autofix_file

            profile_error = _validate_profile(profile, start_time=_t0, execution_context=ctx_policy)
            if profile_error:
                return profile_error
            format_profile_error = _validate_format_profile(
                format_profile, start_time=_t0, execution_context=ctx_policy
            )
            if format_profile_error:
                return format_profile_error

            start_time = time.time()
            base_path = Path(directory_path)

            if not base_path.exists():
                return _tool_error(
                    f"Directory not found: {directory_path}",
                    start_time=_t0,
                    execution_context=ctx_policy,
                    error_type="DirectoryNotFoundError",
                )

            all_files: set[Path] = set()
            for pattern in file_patterns:
                pattern_path = base_path / pattern
                matches = glob(str(pattern_path), recursive=True)
                all_files.update(Path(f) for f in matches)

            tc_files = [f for f in all_files if f.suffix in config.supported_extensions]

            if not tc_files:
                return _tool_error(
                    "No TwinCAT files found matching patterns",
                    start_time=_t0,
                    execution_context=ctx_policy,
                    patterns=file_patterns,
                    directory=str(base_path),
                )

            total = len(tc_files)
            results = []
            failed_files = []
            fixed = 0
            no_changes = 0
            safe_to_import_count = 0
            safe_to_compile_count = 0

            for idx, file_path in enumerate(tc_files):
                await _emit_progress(
                    ctx,
                    current=idx,
                    total=total,
                    message=f"autofix {idx + 1}/{total}: {file_path.name}",
                )
                try:
                    fix_result = json.loads(
                        autofix_file(
                            str(file_path),
                            create_backup=create_backup,
                            fixes_to_apply=None,
                            profile=profile,
                            format_profile=format_profile,
                            strict_contract=strict_contract,
                            create_implicit_files=create_implicit_files,
                            orchestration_hints=orchestration_hints,
                            enforcement_mode=enforcement_mode,
                            intent_profile=intent_profile,
                        )
                    )

                    if not fix_result.get("success", False):
                        failed_files.append(
                            {
                                "file_path": str(file_path),
                                "error": fix_result.get("error", "Unknown autofix error"),
                                "error_type": fix_result.get("error_type", "AutofixError"),
                            }
                        )
                        continue

                    content_changed = bool(fix_result.get("content_changed", False))
                    if content_changed:
                        fixed += 1
                    else:
                        no_changes += 1

                    if fix_result.get("safe_to_import") is True:
                        safe_to_import_count += 1
                    if fix_result.get("safe_to_compile") is True:
                        safe_to_compile_count += 1

                    results.append(
                        {
                            "file_path": str(file_path),
                            "fixes_applied_count": len(fix_result.get("fixes_applied", [])),
                            "fix_result": fix_result,
                        }
                    )

                except Exception as e:
                    failed_files.append(
                        {
                            "file_path": str(file_path),
                            "error": str(e),
                            "error_type": type(e).__name__,
                        }
                    )

            await _emit_progress(ctx, current=total, total=total, message="autofix complete")

            batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            done = (
                len(results) > 0
                and len(failed_files) == 0
                and safe_to_import_count == len(results)
                and safe_to_compile_count == len(results)
            )
            blockers: list[dict] = []
            for item in results:
                fix_result = item.get("fix_result", {}) or {}
                for blocker in fix_result.get("blockers", []) or []:
                    blockers.append(
                        {
                            "file_path": item.get("file_path", ""),
                            "check": blocker.get("check", "unknown"),
                            "message": blocker.get("message", ""),
                            "line": blocker.get("line"),
                        }
                    )
            for failed_item in failed_files:
                blockers.append(
                    {
                        "file_path": failed_item.get("file_path", ""),
                        "check": "infrastructure",
                        "message": failed_item.get("error", "Autofix batch infrastructure error"),
                        "line": None,
                    }
                )
            safe_to_import = len(results) > 0 and safe_to_import_count == len(results)
            safe_to_compile = len(results) > 0 and safe_to_compile_count == len(results)

            result = {
                "success": True,
                "batch_id": batch_id,
                "processed_files": len(results),
                "total_files": total,
                "processing_time": round(time.time() - start_time, 3),
                "batch_summary": {
                    "fixed": fixed,
                    "no_changes": no_changes,
                    "failed": len(failed_files),
                    "safe_to_import": safe_to_import_count,
                    "safe_to_compile": safe_to_compile_count,
                },
                "workflow_mode": "strict_pipeline",
                "done": done,
                "status": "done" if done else "blocked",
                "safe_to_import": safe_to_import,
                "safe_to_compile": safe_to_compile,
                "blocking_count": len(blockers),
                "blockers": blockers,
                "files": results,
                "failed_files": failed_files,
            }
            if done:
                result["terminal_mode"] = True
                result["next_action"] = "done_no_further_autofix"
                result["allow_followup_autofix_without_user_request"] = False
            else:
                result["terminal_mode"] = False
                result["next_action"] = "manual_intervention_or_targeted_fix"

            _assert_autofix_batch_contract(result)
            return _with_meta(result, _t0, execution_context=ctx_policy)

        except Exception as e:
            error_kwargs = {"execution_context": ctx_policy}
            if ctx_policy is None:
                error_kwargs.update(unresolved_policy_fields(enforcement_mode))
            return _tool_error(str(e), start_time=_t0, **error_kwargs)
