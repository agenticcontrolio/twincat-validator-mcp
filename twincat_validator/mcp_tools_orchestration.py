"""MCP tool handlers: orchestration tools.

Tools registered here:
- process_twincat_single
- process_twincat_batch
- verify_determinism_batch
- get_effective_oop_policy
- lint_oop_policy
- get_context_pack
"""

import json
import time
from pathlib import Path

from twincat_validator._server_helpers import (
    _derive_next_action,
    _resolve_execution_context,
    _resolve_policy_target_path,
    _validate_enforcement_mode,
)
from twincat_validator.mcp_app import (
    DEFAULT_ENFORCEMENT_MODE,
    config,
    mcp,
)
from twincat_validator.mcp_responses import _tool_error, _with_meta, unresolved_policy_fields
from twincat_validator.utils import (
    _VALID_INTENT_PROFILES,
    _resolve_intent_profile,
    _batch_auto_resolve_intent,
)


def _aggregate_blockers_from_files(files: list[dict]) -> list[dict]:
    """Collect normalized blocker entries from per-file summaries."""
    blockers: list[dict] = []
    for item in files:
        for blocker in item.get("blockers", []) or []:
            entry: dict = {
                "file_path": item.get("file_path", ""),
                "check": blocker.get("check", blocker.get("category", "unknown")),
                "message": blocker.get("message", ""),
                "line": blocker.get("line"),
            }
            # Preserve check_id when present — used by include_knowledge_hints
            check_id = blocker.get("check_id")
            if check_id:
                entry["check_id"] = check_id
            blockers.append(entry)
    return blockers


def _assert_orchestration_contract(result: dict, *, is_batch: bool) -> None:
    """Fail-closed guard for required structured orchestration keys."""
    required_base = {
        "success": bool,
        "workflow": str,
        "safe_to_import": bool,
        "safe_to_compile": bool,
        "done": bool,
        "status": str,
        "blocking_count": int,
        "blockers": list,
        "next_action": str,
        "terminal_mode": bool,
    }
    if is_batch:
        required_base["files"] = list
    else:
        required_base["file_path"] = str

    for key, expected_type in required_base.items():
        if key not in result:
            raise ValueError(f"Contract violation: missing required key '{key}'")
        if not isinstance(result[key], expected_type):
            raise ValueError(
                f"Contract violation: key '{key}' expected {expected_type.__name__}, "
                f"got {type(result[key]).__name__}"
            )
    if result["status"] not in {"done", "blocked"}:
        raise ValueError("Contract violation: status must be 'done' or 'blocked'")


def _collect_intent_mismatch_warnings(
    expected_resolved: str,
    *,
    steps: list[tuple[str, dict]],
) -> list[str]:
    """Collect non-fatal workflow warnings for intent propagation mismatches."""
    warnings: list[str] = []
    for step_name, payload in steps:
        if not isinstance(payload, dict):
            continue
        step_req = payload.get("intent_profile_requested")
        step_res = payload.get("intent_profile_resolved")
        if isinstance(step_req, str) and step_req != expected_resolved:
            warnings.append(
                f"{step_name}: intent_profile_requested='{step_req}' "
                f"does not match expected '{expected_resolved}'"
            )
        if isinstance(step_res, str) and step_res != expected_resolved:
            warnings.append(
                f"{step_name}: intent_profile_resolved='{step_res}' "
                f"does not match expected '{expected_resolved}'"
            )
    return warnings


def _failed_check_ids(file_result: dict) -> list[str]:
    """Extract failed check IDs from validate_batch per-file validation_result."""
    validation_result = file_result.get("validation_result", {})
    checks = validation_result.get("checks", [])
    failed_ids: list[str] = []
    for check in checks:
        if check.get("status") == "failed":
            check_id = str(check.get("id", "")).strip()
            if check_id:
                failed_ids.append(check_id)
    return failed_ids


def _safe_flags_from_validate_file_entry(file_result: dict) -> tuple[bool, bool]:
    """Resolve per-file safety flags from validate_batch entry, with conservative fallback."""
    safe_to_import = file_result.get("safe_to_import")
    safe_to_compile = file_result.get("safe_to_compile")
    if isinstance(safe_to_import, bool) and isinstance(safe_to_compile, bool):
        return safe_to_import, safe_to_compile

    validation_result = file_result.get("validation_result", {})
    safe_to_import = validation_result.get("safe_to_import")
    safe_to_compile = validation_result.get("safe_to_compile")
    if isinstance(safe_to_import, bool) and isinstance(safe_to_compile, bool):
        return safe_to_import, safe_to_compile

    # Fallback: failed status or any errors means unsafe.
    status = str(file_result.get("status", "")).lower()
    errors = int(file_result.get("error_count", 0) or 0)
    inferred_safe = status != "failed" and errors == 0
    return inferred_safe, inferred_safe


def _build_batch_file_summaries(post_validation: dict, autofix_result: dict) -> list[dict]:
    """Create stable per-file summary records for orchestration responses."""
    post_files = post_validation.get("files", []) or []
    autofix_files = autofix_result.get("files", []) or []

    fix_by_path: dict[str, dict] = {}
    for fix_item in autofix_files:
        path = str(fix_item.get("file_path", ""))
        if path:
            fix_by_path[path] = fix_item

    summaries: list[dict] = []
    for post_item in post_files:
        file_path = str(post_item.get("file_path", ""))
        file_name = Path(file_path).name if file_path else ""
        safe_to_import, safe_to_compile = _safe_flags_from_validate_file_entry(post_item)
        failed_checks = _failed_check_ids(post_item)

        fix_item = fix_by_path.get(file_path, {})
        fix_result = fix_item.get("fix_result", {}) if isinstance(fix_item, dict) else {}
        summaries.append(
            {
                "file_path": file_path,
                "file_name": file_name,
                "status": post_item.get("status", "unknown"),
                "error_count": int(post_item.get("error_count", 0) or 0),
                "warning_count": int(post_item.get("warning_count", 0) or 0),
                "safe_to_import": safe_to_import,
                "safe_to_compile": safe_to_compile,
                "failed_checks": failed_checks,
                "blocking_count": int(fix_result.get("blocking_count", 0) or 0),
                "blockers": fix_result.get("blockers", []) or [],
                "content_changed": bool(fix_result.get("content_changed", False)),
                "fixes_applied_count": int(fix_item.get("fixes_applied_count", 0) or 0),
            }
        )
    return summaries


# ---------------------------------------------------------------------------
# Batch response shaping
# ---------------------------------------------------------------------------

#: Heavy sections excluded by default in summary mode; opt-in via include_sections
_BATCH_HEAVY_SECTIONS = frozenset(
    {
        "blockers",
        "issues",
        "pre_validation",
        "autofix",
        "post_validation",
        "effective_oop_policy",
        "meta_detailed",
    }
)

#: Per-file keys kept in summary mode (strips deep diagnostic fields)
_BATCH_SUMMARY_FILE_KEYS = frozenset(
    {
        "file_name",
        "safe_to_import",
        "safe_to_compile",
        "blocking_count",
        "warning_count",
    }
)

#: Additional per-file keys kept in summary mode for verify_determinism_batch
_DETERMINISM_SUMMARY_FILE_KEYS = frozenset(
    {
        "file_name",
        "safe_to_import",
        "safe_to_compile",
        "blocking_count",
        "content_changed_first_pass",
        "content_changed_second_pass",
        "stable",
    }
)


def _shape_batch_response(
    result: dict,
    response_mode: str,
    include_sections: list[str] | None,
    *,
    summary_file_keys: frozenset[str] = _BATCH_SUMMARY_FILE_KEYS,
) -> tuple[dict, list[str]]:
    """Project a full batch result dict to the requested response_mode.

    In summary mode:
    - Top-level heavy sections (pre_validation, autofix, post_validation, etc.) are dropped
      unless explicitly requested via include_sections.
    - Per-file entries are slimmed to summary_file_keys only.
    - All other scalar/light keys are kept as-is.

    Args:
        result: Full internal result dict.
        response_mode: "summary", "compact", or "full".
        include_sections: In summary mode only — heavy section names to opt-in. No-op otherwise.
        summary_file_keys: Which per-file keys to keep in summary mode.

    Returns:
        (shaped_result, unknown_sections) where unknown_sections lists any include_sections
        names not in _BATCH_HEAVY_SECTIONS. Always empty in compact/full mode.
    """
    if response_mode != "summary":
        # "compact" and "full" pass through unchanged; include_sections is a no-op.
        return result, []

    # --- summary mode ---
    unknown: list[str] = []
    requested_heavy: set[str] = set()
    for s in include_sections or []:
        if s in _BATCH_HEAVY_SECTIONS:
            requested_heavy.add(s)
        else:
            unknown.append(s)

    # Slim per-file entries
    slim_files = []
    for item in result.get("files", []):
        entry = {k: item[k] for k in summary_file_keys if k in item}
        slim_files.append(entry)

    # Build shaped result: keep all keys except heavy sections (unless opted-in),
    # replacing "files" with the slimmed version.
    shaped: dict = {}
    for k, v in result.items():
        if k == "files":
            shaped["files"] = slim_files
        elif k in _BATCH_HEAVY_SECTIONS:
            if k in requested_heavy:
                shaped[k] = v
            # else: drop
        else:
            shaped[k] = v

    return shaped, unknown


CONTEXT_PACK_VERSION = "1"
_DEFAULT_MAX_ENTRIES = 10
_VALID_STAGES = ("pre_generation", "troubleshooting")
# _VALID_INTENT_PROFILES imported from twincat_validator.utils

# Core pre-generation checks: always included regardless of intent profile.
_CORE_PRE_GENERATION_CHECK_IDS: list[str] = [
    "xml_structure",
    "pou_structure",
    "pou_structure_header",
    "pou_structure_var_protected",  # explicit VAR_PROTECTED / VAR PROTECTED prohibition
    "pou_structure_subtype",
    "guid_uniqueness",
    "naming_conventions",
]

# OOP pre-generation checks: only included when intent_profile resolves to "oop".
_OOP_PRE_GENERATION_CHECK_IDS: list[str] = [
    "extends_visibility",
    "override_marker",
    "override_signature",
    "interface_contract",
    "fb_init_signature",
    "abstract_contract",
    "forbidden_abstract_attribute",
    "hardcoded_dispatch",
]

# Legacy alias: full list used when no intent filtering is active (backward compat).
_PRE_GENERATION_CHECK_IDS: list[str] = (
    _CORE_PRE_GENERATION_CHECK_IDS + _OOP_PRE_GENERATION_CHECK_IDS
)


def register_orchestration_tools() -> None:
    """Register all orchestration tool handlers with the mcp instance."""

    @mcp.tool()
    def process_twincat_single(
        file_path: str,
        create_backup: bool = False,
        validation_level: str = "all",
        enforcement_mode: str = DEFAULT_ENFORCEMENT_MODE,
        include_knowledge_hints: bool = False,
        intent_profile: str = "auto",
    ) -> str:
        """Run enforced deterministic single-file TwinCAT workflow.

        Steps:
        1. validate_file (pre-check)
        2. autofix_file (strict pipeline)
        3. validate_file (post-check)
        4. suggest_fixes (only if still unsafe)

        Args:
            file_path: Path to the TwinCAT file to process.
            create_backup: Create a backup before applying fixes.
            validation_level: "all", "critical", or "style".
            enforcement_mode: Policy enforcement mode ("strict" or "compat").
            include_knowledge_hints: Include recommended_check_ids from blockers.
            intent_profile: Programming paradigm intent — "auto" (default), "procedural",
                or "oop".  Controls which check families run:
                - "procedural": OOP checks are skipped (safe for plain FUNCTION_BLOCK/PROGRAM).
                - "oop": Full OOP check family is enforced.
                - "auto": Resolved from file content (EXTENDS/IMPLEMENTS → oop, else procedural).
        """
        _t0 = time.monotonic()
        ctx = None
        try:
            mode_error = _validate_enforcement_mode(enforcement_mode, start_time=_t0)
            if mode_error:
                return mode_error
            ctx = _resolve_execution_context(file_path, enforcement_mode=enforcement_mode)
            # Lazy imports to avoid registration-order problems.
            from twincat_validator.server import autofix_file, suggest_fixes, validate_file

            if intent_profile not in _VALID_INTENT_PROFILES:
                return _tool_error(
                    f"Invalid intent_profile: {intent_profile}",
                    file_path=file_path,
                    start_time=_t0,
                    execution_context=ctx,
                    valid_intent_profiles=list(_VALID_INTENT_PROFILES),
                )

            if validation_level not in ["all", "critical", "style"]:
                return _tool_error(
                    f"Invalid validation_level: {validation_level}",
                    file_path=file_path,
                    start_time=_t0,
                    execution_context=ctx,
                    valid_levels=["all", "critical", "style"],
                )

            # Resolve intent profile from file content for engine-level category filtering.
            try:
                _file_content_for_intent = Path(file_path).read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError:
                _file_content_for_intent = None
            intent_profile_resolved = _resolve_intent_profile(
                _file_content_for_intent, intent_profile
            )

            pre_validation = json.loads(
                validate_file(
                    file_path,
                    validation_level=validation_level,
                    profile="llm_strict",
                    enforcement_mode=enforcement_mode,
                    intent_profile=intent_profile_resolved,
                )
            )
            if not pre_validation.get("success", False):
                return _with_meta(
                    {
                        "success": False,
                        "file_path": file_path,
                        "workflow": "single_strict_pipeline",
                        "failed_step": "validate_file_pre",
                        "step_error": pre_validation,
                        "done": False,
                        "terminal_mode": False,
                        "next_action": "inspect_error",
                    },
                    _t0,
                    execution_context=ctx,
                )

            autofix_result = json.loads(
                autofix_file(
                    file_path=file_path,
                    create_backup=create_backup,
                    profile="llm_strict",
                    format_profile="twincat_canonical",
                    strict_contract=True,
                    create_implicit_files=True,
                    orchestration_hints=True,
                    enforcement_mode=enforcement_mode,
                    intent_profile=intent_profile_resolved,
                )
            )
            if not autofix_result.get("success", False):
                return _with_meta(
                    {
                        "success": False,
                        "file_path": file_path,
                        "workflow": "single_strict_pipeline",
                        "failed_step": "autofix_file",
                        "step_error": autofix_result,
                        "done": False,
                        "terminal_mode": False,
                        "next_action": "inspect_error",
                    },
                    _t0,
                    execution_context=ctx,
                )

            post_validation = json.loads(
                validate_file(
                    file_path,
                    validation_level=validation_level,
                    profile="llm_strict",
                    enforcement_mode=enforcement_mode,
                    intent_profile=intent_profile_resolved,
                )
            )
            if not post_validation.get("success", False):
                return _with_meta(
                    {
                        "success": False,
                        "file_path": file_path,
                        "workflow": "single_strict_pipeline",
                        "failed_step": "validate_file_post",
                        "step_error": post_validation,
                        "done": False,
                        "terminal_mode": False,
                        "next_action": "inspect_error",
                    },
                    _t0,
                    execution_context=ctx,
                )

            safe_to_import = bool(autofix_result.get("safe_to_import")) and bool(
                post_validation.get("safe_to_import")
            )
            safe_to_compile = bool(autofix_result.get("safe_to_compile")) and bool(
                post_validation.get("safe_to_compile")
            )
            done = safe_to_import and safe_to_compile
            blockers = autofix_result.get("blockers", []) or []
            check_categories_executed = (
                ["core", "oop"] if intent_profile_resolved == "oop" else ["core"]
            )
            workflow_compliance_warnings = _collect_intent_mismatch_warnings(
                intent_profile_resolved,
                steps=[
                    ("validate_file_pre", pre_validation),
                    ("autofix_file", autofix_result),
                    ("validate_file_post", post_validation),
                ],
            )
            result = {
                "success": True,
                "file_path": file_path,
                "workflow": "single_strict_pipeline",
                "tools_used": [
                    "validate_file",
                    "autofix_file",
                    "validate_file",
                ],
                "intent_profile_requested": intent_profile,
                "intent_profile_resolved": intent_profile_resolved,
                "check_categories_executed": check_categories_executed,
                "workflow_compliance_warnings": workflow_compliance_warnings,
                "safe_to_import": safe_to_import,
                "safe_to_compile": safe_to_compile,
                "pre_validation": pre_validation,
                "autofix": autofix_result,
                "post_validation": post_validation,
                "done": done,
                "status": "done" if done else "blocked",
                "blocking_count": int(autofix_result.get("blocking_count", 0) or 0),
                "blockers": blockers,
                "effective_oop_policy": {
                    "policy_source": ctx.policy_source,
                    "policy": ctx.effective_oop_policy,
                },
            }
            no_change = bool(autofix_result.get("no_change_detected", False))
            no_progress = int(autofix_result.get("no_progress_count", 0) or 0)
            contract_failed = bool(autofix_result.get("contract_passed") is False)
            derived_action, terminal = _derive_next_action(
                safe_to_import=safe_to_import,
                safe_to_compile=safe_to_compile,
                blockers=blockers,
                no_change_detected=no_change,
                no_progress_count=no_progress,
                contract_failed=contract_failed,
            )
            # When the file is fully clean, the workflow is always terminal.
            # _derive_next_action returns terminal=False for "done" (meaning "not stuck"),
            # but the single-file contract means terminal=True when done=True.
            result["terminal_mode"] = True if done else terminal
            result["next_action"] = derived_action
            result["allow_followup_autofix_without_user_request"] = False

            if not result["done"]:
                full_validation = validate_file(
                    file_path,
                    validation_level=validation_level,
                    profile="full",
                    enforcement_mode=enforcement_mode,
                    intent_profile=intent_profile_resolved,
                )
                suggestions = json.loads(suggest_fixes(full_validation))
                result["tools_used"].append("suggest_fixes")
                result["suggested_fixes"] = suggestions

                if include_knowledge_hints:
                    result["recommended_check_ids"] = sorted(
                        set(b["check_id"] for b in blockers if b.get("check_id"))
                    )

            _assert_orchestration_contract(result, is_batch=False)
            return _with_meta(result, _t0, execution_context=ctx)
        except Exception as e:
            error_kwargs = {"execution_context": ctx}
            if ctx is None:
                error_kwargs.update(unresolved_policy_fields(enforcement_mode))
            return _tool_error(str(e), file_path=file_path, start_time=_t0, **error_kwargs)

    @mcp.tool()
    async def process_twincat_batch(
        file_patterns: list[str],
        directory_path: str = ".",
        create_backup: bool = False,
        validation_level: str = "all",
        enforcement_mode: str = DEFAULT_ENFORCEMENT_MODE,
        response_mode: str = "summary",
        include_sections: list[str] | None = None,
        include_knowledge_hints: bool = False,
        intent_profile: str = "auto",
    ) -> str:
        """Run enforced deterministic batch TwinCAT workflow.

        Steps:
        1. validate_batch (pre-check)
        2. autofix_batch (strict pipeline)
        3. validate_batch (post-check)

        Args:
            file_patterns: Glob patterns (e.g., ["*.TcPOU"])
            directory_path: Base directory
            create_backup: Create backup files before fixing
            validation_level: "all", "critical", or "style"
            enforcement_mode: Policy enforcement mode ("strict" or "compat")
            response_mode: "summary" (minimal, default), "compact" (no pre/post blobs),
                or "full" (all detail sections included).
            include_sections: In summary mode only — optional list of heavy sections to add.
                Supported: "blockers", "issues", "pre_validation", "autofix", "post_validation",
                "effective_oop_policy", "meta_detailed". Unknown names are ignored with a warning
                in the response. Has no effect in compact or full mode.
            include_knowledge_hints: Include recommended_check_ids from blockers (when not done).
            intent_profile: Programming paradigm intent — "auto" (default), "procedural",
                or "oop".  Controls which check families run:
                - "procedural": OOP checks are skipped.
                - "oop": Full OOP check family is enforced.
                - "auto": Scans matched .TcPOU declarations for EXTENDS/IMPLEMENTS; resolves
                  to "oop" if any are found, otherwise "procedural".
        """
        _t0 = time.monotonic()
        ctx = None
        try:
            mode_error = _validate_enforcement_mode(enforcement_mode, start_time=_t0)
            if mode_error:
                return mode_error
            ctx = _resolve_execution_context(directory_path, enforcement_mode=enforcement_mode)
            from glob import glob as _glob

            from twincat_validator.server import autofix_batch, validate_batch

            if validation_level not in ["all", "critical", "style"]:
                return _tool_error(
                    f"Invalid validation_level: {validation_level}",
                    start_time=_t0,
                    execution_context=ctx,
                    valid_levels=["all", "critical", "style"],
                )
            if response_mode not in ["full", "compact", "summary"]:
                return _tool_error(
                    f"Invalid response_mode: {response_mode}",
                    start_time=_t0,
                    execution_context=ctx,
                    valid_response_modes=["full", "compact", "summary"],
                )
            if intent_profile not in _VALID_INTENT_PROFILES:
                return _tool_error(
                    f"Invalid intent_profile: {intent_profile}",
                    start_time=_t0,
                    execution_context=ctx,
                    valid_intent_profiles=list(_VALID_INTENT_PROFILES),
                )

            # Resolve intent by scanning matched files so "auto" detects OOP content.
            _base_path = Path(directory_path)
            _all_files: set[Path] = set()
            for _pattern in file_patterns:
                _matches = _glob(str(_base_path / _pattern), recursive=True)
                _all_files.update(Path(f) for f in _matches)
            _tc_files = [f for f in _all_files if f.suffix in config.supported_extensions]
            intent_profile_resolved = _batch_auto_resolve_intent(_tc_files, intent_profile)
            check_categories_executed = (
                ["core", "oop"] if intent_profile_resolved == "oop" else ["core"]
            )
            pre_validation = json.loads(
                await validate_batch(
                    file_patterns=file_patterns,
                    directory_path=directory_path,
                    validation_level=validation_level,
                    enforcement_mode=enforcement_mode,
                    intent_profile=intent_profile_resolved,
                )
            )
            if not pre_validation.get("success", False):
                return _with_meta(
                    {
                        "success": False,
                        "workflow": "batch_strict_pipeline",
                        "failed_step": "validate_batch_pre",
                        "step_error": pre_validation,
                        "done": False,
                        "terminal_mode": False,
                        "next_action": "inspect_error",
                    },
                    _t0,
                    execution_context=ctx,
                )

            autofix_result = json.loads(
                await autofix_batch(
                    file_patterns=file_patterns,
                    directory_path=directory_path,
                    create_backup=create_backup,
                    profile="llm_strict",
                    format_profile="twincat_canonical",
                    strict_contract=True,
                    create_implicit_files=True,
                    orchestration_hints=True,
                    enforcement_mode=enforcement_mode,
                    intent_profile=intent_profile_resolved,
                )
            )
            if not autofix_result.get("success", False):
                return _with_meta(
                    {
                        "success": False,
                        "workflow": "batch_strict_pipeline",
                        "failed_step": "autofix_batch",
                        "step_error": autofix_result,
                        "done": False,
                        "terminal_mode": False,
                        "next_action": "inspect_error",
                    },
                    _t0,
                    execution_context=ctx,
                )

            post_validation = json.loads(
                await validate_batch(
                    file_patterns=file_patterns,
                    directory_path=directory_path,
                    validation_level=validation_level,
                    enforcement_mode=enforcement_mode,
                    intent_profile=intent_profile_resolved,
                )
            )
            if not post_validation.get("success", False):
                return _with_meta(
                    {
                        "success": False,
                        "workflow": "batch_strict_pipeline",
                        "failed_step": "validate_batch_post",
                        "step_error": post_validation,
                        "done": False,
                        "terminal_mode": False,
                        "next_action": "inspect_error",
                    },
                    _t0,
                    execution_context=ctx,
                )

            workflow_compliance_warnings = _collect_intent_mismatch_warnings(
                intent_profile_resolved,
                steps=[
                    ("validate_batch_pre", pre_validation),
                    ("autofix_batch", autofix_result),
                    ("validate_batch_post", post_validation),
                ],
            )

            batch_summary = post_validation.get("batch_summary", {})
            file_summaries = _build_batch_file_summaries(post_validation, autofix_result)
            safe_to_import = (
                all(item["safe_to_import"] for item in file_summaries) if file_summaries else False
            )
            safe_to_compile = (
                all(item["safe_to_compile"] for item in file_summaries) if file_summaries else False
            )
            done = batch_summary.get("failed", 0) == 0 and safe_to_import and safe_to_compile
            blockers = _aggregate_blockers_from_files(file_summaries)
            result = {
                "success": True,
                "workflow": "batch_strict_pipeline",
                "tools_used": ["validate_batch", "autofix_batch", "validate_batch"],
                "file_patterns": file_patterns,
                "directory_path": directory_path,
                "response_mode": response_mode,
                "intent_profile_requested": intent_profile,
                "intent_profile_resolved": intent_profile_resolved,
                "check_categories_executed": check_categories_executed,
                "workflow_compliance_warnings": workflow_compliance_warnings,
                "batch_summary": batch_summary,
                "safe_to_import": safe_to_import,
                "safe_to_compile": safe_to_compile,
                "files": file_summaries,
                "done": done,
                "status": "done" if done else "blocked",
                "blocking_count": len(blockers),
                "blockers": blockers,
                "effective_oop_policy": {
                    "policy_source": ctx.policy_source,
                    "policy": ctx.effective_oop_policy,
                },
            }
            if response_mode == "full":
                result["pre_validation"] = pre_validation
                result["autofix"] = autofix_result
                result["post_validation"] = post_validation
            if done:
                result["terminal_mode"] = True
                result["next_action"] = "done_no_further_autofix"
                result["allow_followup_autofix_without_user_request"] = False
            else:
                result["terminal_mode"] = False
                result["next_action"] = "manual_intervention_or_targeted_fix"

                if include_knowledge_hints:
                    result["recommended_check_ids"] = sorted(
                        set(b["check_id"] for b in blockers if b.get("check_id"))
                    )

            _assert_orchestration_contract(result, is_batch=True)

            # Apply response shaping (summary mode projects to minimal payload).
            shaped, unknown_sections = _shape_batch_response(
                result, response_mode, include_sections
            )
            if unknown_sections:
                shaped["unknown_include_sections"] = unknown_sections
            return _with_meta(shaped, _t0, execution_context=ctx)
        except Exception as e:
            error_kwargs = {"execution_context": ctx}
            if ctx is None:
                error_kwargs.update(unresolved_policy_fields(enforcement_mode))
            return _tool_error(str(e), start_time=_t0, **error_kwargs)

    @mcp.tool()
    async def verify_determinism_batch(
        file_patterns: list[str],
        directory_path: str = ".",
        create_backup: bool = False,
        validation_level: str = "all",
        enforcement_mode: str = DEFAULT_ENFORCEMENT_MODE,
        response_mode: str = "summary",
        include_sections: list[str] | None = None,
    ) -> str:
        """Run strict batch orchestration twice and report per-file idempotence stability.

        Args:
            file_patterns: Glob patterns (e.g., ["*.TcPOU"])
            directory_path: Base directory
            create_backup: Create backup files before fixing
            validation_level: "all", "critical", or "style"
            enforcement_mode: Policy enforcement mode ("strict" or "compat")
            response_mode: "summary" (minimal, default), "compact", or "full".
            include_sections: In summary mode only — optional heavy sections to include.
                Supported: "blockers", "pre_validation", "autofix", "post_validation",
                "effective_oop_policy", "meta_detailed". Unknown names ignored with a warning
                in the response. Has no effect in compact or full mode.
        """
        _t0 = time.monotonic()
        ctx = None
        try:
            mode_error = _validate_enforcement_mode(enforcement_mode, start_time=_t0)
            if mode_error:
                return mode_error
            ctx = _resolve_execution_context(directory_path, enforcement_mode=enforcement_mode)
            if response_mode not in ["full", "compact", "summary"]:
                return _tool_error(
                    f"Invalid response_mode: {response_mode}",
                    start_time=_t0,
                    execution_context=ctx,
                    valid_response_modes=["full", "compact", "summary"],
                )

            # Always use "compact" internally so per-file data is available for aggregation;
            # the caller's preferred response_mode is applied to the final result only.
            first = json.loads(
                await process_twincat_batch(
                    file_patterns=file_patterns,
                    directory_path=directory_path,
                    create_backup=create_backup,
                    validation_level=validation_level,
                    enforcement_mode=enforcement_mode,
                    response_mode="compact",
                )
            )
            if not first.get("success", False):
                return json.dumps(first, indent=2)

            second = json.loads(
                await process_twincat_batch(
                    file_patterns=file_patterns,
                    directory_path=directory_path,
                    create_backup=create_backup,
                    validation_level=validation_level,
                    enforcement_mode=enforcement_mode,
                    response_mode="compact",
                )
            )
            if not second.get("success", False):
                return json.dumps(second, indent=2)

            first_by_path = {
                str(item.get("file_path", "")): item for item in first.get("files", [])
            }
            second_by_path = {
                str(item.get("file_path", "")): item for item in second.get("files", [])
            }
            all_paths = sorted(set(first_by_path) | set(second_by_path))

            files = []
            stable_all = True
            for path in all_paths:
                first_item = first_by_path.get(path, {})
                second_item = second_by_path.get(path, {})
                changed_first = bool(first_item.get("content_changed", False))
                changed_second = bool(second_item.get("content_changed", False))
                stable = not changed_second
                if not stable:
                    stable_all = False
                files.append(
                    {
                        "file_path": path,
                        "file_name": Path(path).name if path else "",
                        "safe_to_import": bool(second_item.get("safe_to_import", False)),
                        "safe_to_compile": bool(second_item.get("safe_to_compile", False)),
                        "content_changed_first_pass": changed_first,
                        "content_changed_second_pass": changed_second,
                        "stable": stable,
                    }
                )

            # RC-2 fix: done requires stability AND safety, not just stability.
            # Aggregate safety flags directly from per-file entries (already canonical —
            # set by process_twincat_batch which uses derive_contract_state internally).
            # Do NOT derive solely from per-file blockers: fixable errors make a file
            # unsafe without contributing blockers, so blockers-only aggregation can
            # produce safe_to_compile=True for genuinely unsafe files.
            all_safe_to_import = all(f["safe_to_import"] for f in files) if files else False
            all_safe_to_compile = all(f["safe_to_compile"] for f in files) if files else False

            # Collect actual per-file blockers from the second-pass results.
            second_pass_blockers: list[dict] = []
            for item in second.get("files", []):
                second_pass_blockers.extend(item.get("blockers", []) or [])

            # Add a determinism-specific blocker when content still changed on pass 2.
            determinism_extra_blockers: list[dict] = []
            if not stable_all:
                determinism_extra_blockers.append(
                    {"check": "determinism", "message": "Second pass changed content", "line": None}
                )

            all_blockers = second_pass_blockers + determinism_extra_blockers
            blocking_count = len(all_blockers)

            # Compute done: requires stability, both safe flags, and zero blockers.
            safe_to_import = all_safe_to_import
            safe_to_compile = all_safe_to_compile
            done = stable_all and safe_to_import and safe_to_compile and blocking_count == 0
            det_status = "done" if done else "blocked"

            result = {
                "success": True,
                "workflow": "determinism_batch",
                "tools_used": ["process_twincat_batch", "process_twincat_batch"],
                "file_patterns": file_patterns,
                "directory_path": directory_path,
                "response_mode": response_mode,
                "stable": stable_all,
                "files": files,
                "first_pass_summary": first.get("batch_summary", {}),
                "second_pass_summary": second.get("batch_summary", {}),
                "batch_summary": second.get("batch_summary", {}),
                "safe_to_import": safe_to_import,
                "safe_to_compile": safe_to_compile,
                "done": done,
                "status": det_status,
                "blocking_count": blocking_count,
                "blockers": all_blockers,
                "terminal_mode": done,
                "next_action": (
                    "done_no_further_autofix" if done else "manual_intervention_or_targeted_fix"
                ),
                "effective_oop_policy": {
                    "policy_source": ctx.policy_source,
                    "policy": ctx.effective_oop_policy,
                },
            }
            _assert_orchestration_contract(result, is_batch=True)

            # Apply response shaping (determinism-specific file keys preserve stability fields).
            shaped, unknown_sections = _shape_batch_response(
                result,
                response_mode,
                include_sections,
                summary_file_keys=_DETERMINISM_SUMMARY_FILE_KEYS,
            )
            if unknown_sections:
                shaped["unknown_include_sections"] = unknown_sections
            return _with_meta(shaped, _t0, execution_context=ctx)
        except Exception as e:
            error_kwargs = {"execution_context": ctx}
            if ctx is None:
                error_kwargs.update(unresolved_policy_fields(enforcement_mode))
            return _tool_error(str(e), start_time=_t0, **error_kwargs)

    @mcp.tool()
    def get_effective_oop_policy(target_path: str = "") -> str:
        """Get effective OOP validation policy for a file or directory target.

        Args:
            target_path: Optional path to a file or directory. If omitted, uses current working
                directory defaults.
        """
        _t0 = time.monotonic()
        try:
            policy_target = _resolve_policy_target_path(target_path)
            resolved = config.resolve_oop_policy(policy_target)
            result = {
                "success": True,
                "target_path": str(policy_target),
                "policy_source": resolved["source"],
                "policy": resolved["policy"],
            }
            return _with_meta(result, _t0)
        except Exception as e:
            return _tool_error(str(e), file_path=target_path or None, start_time=_t0)

    @mcp.tool()
    def lint_oop_policy(target_path: str = "", strict: bool = True) -> str:
        """Lint nearest .twincat-validator.json policy keys/types and return normalized policy."""
        _t0 = time.monotonic()
        try:
            policy_target = _resolve_policy_target_path(target_path)
            lint = config.lint_oop_policy(policy_target, strict=bool(strict))
            result = {
                "success": True,
                "target_path": str(policy_target),
                "valid": bool(lint.get("valid", False)),
                "strict": bool(lint.get("strict", strict)),
                "source": lint.get("source", "defaults"),
                "policy_file": lint.get("policy_file"),
                "recognized_keys": lint.get("recognized_keys", []),
                "unknown_keys": lint.get("unknown_keys", []),
                "type_errors": lint.get("type_errors", []),
                "constraint_errors": lint.get("constraint_errors", []),
                "parse_error": lint.get("parse_error"),
                "normalized_policy": lint.get("normalized_policy", {}),
            }
            return _with_meta(result, _t0)
        except Exception as e:
            return _tool_error(str(e), file_path=target_path or None, start_time=_t0)

    @mcp.tool()
    def get_context_pack(
        stage: str = "pre_generation",
        check_ids: list[str] | None = None,
        target_path: str = "",
        max_entries: int = _DEFAULT_MAX_ENTRIES,
        include_examples: bool = True,
        enforcement_mode: str = DEFAULT_ENFORCEMENT_MODE,
        intent_profile: str | None = None,
    ) -> str:
        """Get curated knowledge base entries and OOP policy scoped by workflow stage.

        Stages:
        - pre_generation: Returns high-priority non-fixable checks the LLM must
          get right when generating TwinCAT XML from scratch.
        - troubleshooting: Returns KB entries for specific check_ids (typically
          extracted from blocker lists after orchestration).

        Args:
            stage: Workflow stage ("pre_generation" or "troubleshooting").
            check_ids: Explicit check IDs (required for troubleshooting, ignored
                for pre_generation).
            target_path: Optional file/dir path for OOP policy resolution.
            max_entries: Maximum KB entries to return (default 10).
            include_examples: Include correct_examples and common_mistakes arrays
                (default True). Set False to save tokens.
            enforcement_mode: Policy enforcement mode ("strict" or "compat").
            intent_profile: Programming paradigm intent — "oop", "procedural",
                or "auto". In pre_generation stage:
                - omitted: defaults to "oop" (backward compatible behavior).
                - "oop": Core + OOP check guidance is returned.
                - "procedural": Only core (non-OOP) check guidance is returned.
                - "auto": No file content is available at pre-generation time, so resolves
                  to "procedural". Use "oop" or "procedural" explicitly for predictability.
                In troubleshooting stage:
                - explicit value is required (workflow guardrail).
                - value has no routing effect (check_ids drive selection).

        Returns:
            JSON with effective_oop_policy, curated entries[], missing_check_ids[],
            intent metadata, truncation info, and meta envelope.
        """
        _t0 = time.monotonic()
        ctx = None
        try:
            if stage not in _VALID_STAGES:
                return _tool_error(
                    f"Invalid stage: {stage}",
                    start_time=_t0,
                    valid_stages=list(_VALID_STAGES),
                )

            if not isinstance(max_entries, int) or max_entries < 1:
                max_entries = _DEFAULT_MAX_ENTRIES

            mode_error = _validate_enforcement_mode(enforcement_mode, start_time=_t0)
            if mode_error:
                return mode_error

            if stage == "troubleshooting" and intent_profile is None:
                return _tool_error(
                    "intent_profile is required for troubleshooting stage",
                    start_time=_t0,
                    execution_context=ctx,
                    valid_intent_profiles=list(_VALID_INTENT_PROFILES),
                )

            if intent_profile is None:
                intent_profile_effective = "oop"
            else:
                intent_profile_effective = intent_profile

            if intent_profile_effective not in _VALID_INTENT_PROFILES:
                return _tool_error(
                    f"Invalid intent_profile: {intent_profile_effective}",
                    start_time=_t0,
                    valid_intent_profiles=list(_VALID_INTENT_PROFILES),
                )

            # Resolve policy context
            if target_path:
                ctx = _resolve_execution_context(target_path, enforcement_mode=enforcement_mode)
                oop_policy_block = {
                    "policy_source": ctx.policy_source,
                    "policy": ctx.effective_oop_policy,
                }
            else:
                resolved = config.resolve_oop_policy(None)
                oop_policy_block = {
                    "policy_source": resolved["source"],
                    "policy": resolved["policy"],
                }

            # Resolve intent profile (no file content at pre_generation; defaults to procedural).
            intent_profile_resolved = _resolve_intent_profile(None, intent_profile_effective)

            # Determine which check_ids to look up
            if stage == "pre_generation":
                # In procedural mode: core checks only.  In OOP mode: core + OOP checks.
                if intent_profile_resolved == "oop":
                    requested_ids = list(_PRE_GENERATION_CHECK_IDS)
                else:
                    requested_ids = list(_CORE_PRE_GENERATION_CHECK_IDS)
            else:
                if not check_ids:
                    return _tool_error(
                        "check_ids is required for troubleshooting stage",
                        start_time=_t0,
                        execution_context=ctx,
                    )
                requested_ids = list(dict.fromkeys(check_ids))  # dedupe, preserve order

            # Build entries
            entries: list[dict] = []
            missing_check_ids: list[str] = []

            for cid in requested_ids:
                check_config = config.validation_checks.get(cid)
                if check_config is None:
                    missing_check_ids.append(cid)
                    continue

                entry: dict = {
                    "check_id": cid,
                    "name": check_config.get("name", ""),
                    "severity": check_config.get("severity", ""),
                    "category": check_config.get("category", ""),
                    "auto_fixable": bool(check_config.get("auto_fixable", False)),
                }

                kb = config.get_check_knowledge(cid)
                if kb:
                    entry["explanation"] = kb.get("explanation", "")
                    entry["why_it_matters"] = kb.get("why_it_matters", "")
                    if include_examples:
                        entry["correct_examples"] = kb.get("correct_examples", [])
                        entry["common_mistakes"] = kb.get("common_mistakes", [])
                else:
                    missing_check_ids.append(cid)

                entries.append(entry)

            # Apply max_entries truncation
            entries_requested = len(entries)
            truncated = len(entries) > max_entries
            entries = entries[:max_entries]

            result = {
                "success": True,
                "context_pack_version": CONTEXT_PACK_VERSION,
                "stage": stage,
                "intent_profile_requested": intent_profile_effective,
                "intent_profile_resolved": intent_profile_resolved,
                "entries_requested": entries_requested,
                "entries_returned": len(entries),
                "max_entries": max_entries,
                "truncated": truncated,
                "effective_oop_policy": oop_policy_block,
                "entries": entries,
                "missing_check_ids": sorted(set(missing_check_ids)),
            }

            return _with_meta(result, _t0, execution_context=ctx)

        except Exception as e:
            error_kwargs: dict = {"execution_context": ctx}
            if ctx is None:
                error_kwargs.update(unresolved_policy_fields(enforcement_mode))
            return _tool_error(str(e), start_time=_t0, **error_kwargs)
