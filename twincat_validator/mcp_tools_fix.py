"""MCP tool handlers: fix tools.

Tools registered here:
- autofix_file
- generate_skeleton
- extract_methods_to_xml
"""

import time
import re
from typing import Optional

from twincat_validator import TwinCATFile
from twincat_validator._server_helpers import (
    _artifact_sanity_violations,
    _canonicalize_getter_declarations,
    _canonicalize_ids,
    _canonicalize_tcdut_layout,
    _canonicalize_tcio_layout,
    _canonicalize_tcpou_method_layout,
    _check_generation_contract,
    _compute_issue_fingerprint,
    _count_invalid_guid_tokens,
    _create_missing_implicit_files,
    _derive_next_action,
    _engine_issues_to_records,
    _ensure_tcplcobject_attrs,
    _normalize_interface_inline_methods,
    _normalize_line_endings_and_trailing_ws,
    _build_contract_skeleton,
    _normalize_file_type,
    _promote_inline_methods_to_xml,
    _rebuild_pou_lineids,
    _resolve_execution_context,
    _sha256_text,
    _update_no_progress_count,
    _validate_enforcement_mode,
    _validate_file_path,
    _validate_format_profile,
    _validate_profile,
)
from twincat_validator.mcp_app import (
    DEFAULT_ENFORCEMENT_MODE,
    ERROR_SEVERITIES,
    SUPPORTED_POU_SUBTYPES,
    config,
    fix_engine,
    mcp,
    validation_engine,
)
from twincat_validator.mcp_responses import _tool_error, _with_meta, unresolved_policy_fields
from twincat_validator.result_contract import derive_contract_state
from twincat_validator.utils import _VALID_INTENT_PROFILES, _resolve_intent_profile


def register_fix_tools() -> None:
    """Register all fix tool handlers with the mcp instance."""

    @mcp.tool()
    def autofix_file(
        file_path: str,
        create_backup: bool = True,
        fixes_to_apply: Optional[list[str]] = None,
        profile: str = "full",
        format_profile: str = "default",
        strict_contract: bool = False,
        create_implicit_files: bool = False,
        orchestration_hints: bool = False,
        enforcement_mode: str = DEFAULT_ENFORCEMENT_MODE,
        intent_profile: str = "auto",
    ) -> str:
        """Automatically fix common TwinCAT XML issues.

        Args:
            file_path: Path to TwinCAT file
            create_backup: Create backup before fixing
            fixes_to_apply: List of fix IDs, or None for all
            profile: "full" (default) verbose response, "llm_strict" minimal response
            format_profile: "default" or "twincat_canonical" formatting pass
            strict_contract: If True, fail closed on generation-contract violations
            create_implicit_files: If True, auto-create missing implicit dependency files
                (currently interface .TcIO files for IMPLEMENTS I_* clauses)
            orchestration_hints: If True, include next_action/terminal/no_change hints
                and content fingerprints for loop prevention in weak agents.
            intent_profile: Programming paradigm intent — "auto" (default), "procedural",
                or "oop".  Controls which check families are used in post-fix validation.
        """
        _t0 = time.monotonic()
        ctx = None
        try:
            mode_error = _validate_enforcement_mode(enforcement_mode, start_time=_t0)
            if mode_error:
                return mode_error
            ctx = _resolve_execution_context(file_path, enforcement_mode=enforcement_mode)
            if intent_profile not in _VALID_INTENT_PROFILES:
                return _tool_error(
                    f"Invalid intent_profile: {intent_profile}",
                    file_path=file_path,
                    start_time=_t0,
                    execution_context=ctx,
                    valid_intent_profiles=list(_VALID_INTENT_PROFILES),
                )
            profile_error = _validate_profile(profile, start_time=_t0, execution_context=ctx)
            if profile_error:
                return profile_error
            format_profile_error = _validate_format_profile(
                format_profile, start_time=_t0, execution_context=ctx
            )
            if format_profile_error:
                return format_profile_error

            path, error = _validate_file_path(file_path, start_time=_t0, execution_context=ctx)
            if error:
                return error

            file = TwinCATFile.from_path(path)
            _intent_resolved = _resolve_intent_profile(file.content, intent_profile)
            _exclude_cats = frozenset({"oop"}) if _intent_resolved == "procedural" else None
            implicit_files_created: list[str] = []
            original_content = file.content
            content_fingerprint_before = _sha256_text(original_content)

            pre_canon_invalid_guids = _count_invalid_guid_tokens(original_content)

            implicit_creation_enabled = create_implicit_files or profile == "llm_strict"
            if implicit_creation_enabled:
                implicit_files_created = _create_missing_implicit_files(file)

            if file.suffix == ".TcPOU":
                _canonicalize_tcpou_method_layout(file)
            elif file.suffix == ".TcIO":
                _normalize_interface_inline_methods(file)
                _canonicalize_tcio_layout(file)
            elif file.suffix == ".TcDUT":
                _canonicalize_tcdut_layout(file)

            if format_profile == "twincat_canonical":
                _ensure_tcplcobject_attrs(file)
                _canonicalize_getter_declarations(file)
                _canonicalize_ids(file)
                if file.suffix == ".TcPOU":
                    _rebuild_pou_lineids(file)
                _normalize_line_endings_and_trailing_ws(file)

            if strict_contract:
                contract_errors = _check_generation_contract(file)
                if contract_errors:
                    blockers = [
                        {
                            "check": "generation_contract",
                            "line": None,
                            "message": msg,
                            "fixable": False,
                        }
                        for msg in contract_errors
                    ]
                    if profile == "llm_strict":
                        content_changed = file.content != original_content
                        if content_changed:
                            file.save(create_backup=create_backup)
                        post_canon_invalid_guids, contract_violations = _artifact_sanity_violations(
                            file, strict_contract=True
                        )
                        invalid_guid_count = max(pre_canon_invalid_guids, post_canon_invalid_guids)
                        result = {
                            "success": True,
                            "file_path": str(file.filepath),
                            "safe_to_import": False,
                            "safe_to_compile": False,
                            "content_changed": content_changed,
                            "fixes_applied": [],
                            "blocking_count": len(blockers),
                            "blockers": blockers,
                            "contract_passed": False,
                            "contract_errors": contract_errors,
                            "requires_regeneration": True,
                            "implicit_files_created": implicit_files_created,
                            "invalid_guid_count": invalid_guid_count,
                            "contract_violations": contract_violations,
                        }
                        if orchestration_hints:
                            issue_fingerprint = _compute_issue_fingerprint(blockers)
                            no_progress_count = _update_no_progress_count(
                                str(file.filepath),
                                issue_fingerprint,
                                content_changed,
                            )
                            next_action, terminal = _derive_next_action(
                                safe_to_import=False,
                                safe_to_compile=False,
                                blockers=blockers,
                                no_change_detected=not content_changed,
                                no_progress_count=no_progress_count,
                                contract_failed=True,
                            )
                            result.update(
                                {
                                    "no_change_detected": not content_changed,
                                    "content_fingerprint_before": content_fingerprint_before,
                                    "content_fingerprint_after": _sha256_text(file.content),
                                    "issue_fingerprint": issue_fingerprint,
                                    "no_progress_count": no_progress_count,
                                    "next_action": next_action,
                                    "terminal": terminal,
                                }
                            )
                        return _with_meta(result, _t0, execution_context=ctx)

                    return _with_meta(
                        {
                            "success": True,
                            "file_path": str(file.filepath),
                            "content_changed": file.content != original_content,
                            "fixes_applied": [],
                            "validation_after_fix": None,
                            "contract_passed": False,
                            "contract_errors": contract_errors,
                            "requires_regeneration": True,
                            "implicit_files_created": implicit_files_created,
                            "invalid_guid_count": max(
                                pre_canon_invalid_guids,
                                _count_invalid_guid_tokens(file.content),
                            ),
                            "contract_violations": contract_errors,
                        },
                        _t0,
                        execution_context=ctx,
                    )

            resolved_fix_ids = fixes_to_apply
            # In canonical profile, LineIds are rebuilt deterministically after fixes.
            # Skipping the experimental lineids fixer avoids duplicate/unstable edits.
            if format_profile == "twincat_canonical":
                if resolved_fix_ids is None:
                    resolved_fix_ids = [
                        fix_id for fix_id in config.fix_capabilities.keys() if fix_id != "lineids"
                    ]
                else:
                    resolved_fix_ids = [
                        fix_id for fix_id in resolved_fix_ids if fix_id != "lineids"
                    ]

            fix_result = fix_engine.apply_fixes(file, fix_ids=resolved_fix_ids)

            if format_profile == "twincat_canonical":
                _ensure_tcplcobject_attrs(file)
                if file.suffix == ".TcPOU":
                    _canonicalize_tcpou_method_layout(file)
                elif file.suffix == ".TcIO":
                    _normalize_interface_inline_methods(file)
                    _canonicalize_tcio_layout(file)
                elif file.suffix == ".TcDUT":
                    _canonicalize_tcdut_layout(file)
                _canonicalize_getter_declarations(file)
                _canonicalize_ids(file)
                if file.suffix == ".TcPOU":
                    _rebuild_pou_lineids(file)
                _normalize_line_endings_and_trailing_ws(file)

            content_changed = file.content != original_content
            content_fingerprint_after = _sha256_text(file.content)

            backup_path = None
            if content_changed:
                backup_path = file.save(create_backup=create_backup)

            validation_result_all = validation_engine.validate(
                file, "all", exclude_categories=_exclude_cats
            )

            if profile == "llm_strict":
                validation_result_blockers = validation_engine.validate(
                    file, "critical", exclude_categories=_exclude_cats
                )
            else:
                validation_result_blockers = validation_result_all

            # Build policy-enforcement blockers from issues (special-cased serialisation).
            policy_blockers: list[dict] = []
            for issue in validation_result_blockers.issues:
                if issue.severity not in ERROR_SEVERITIES or issue.fix_available:
                    continue
                if str(issue.category).lower() == "policy_enforcement":
                    rule_match = re.search(r"\[rule_id:([a-z0-9_]+)\]", issue.message)
                    rule_id = (
                        rule_match.group(1)
                        if rule_match
                        else "enforce_interface_contract_integrity"
                    )
                    clean_message = re.sub(r"^\[rule_id:[a-z0-9_]+\]\s*", "", issue.message)
                    policy_blockers.append(
                        {
                            "check": "policy_enforcement",
                            "rule_id": rule_id,
                            "line": issue.line_num,
                            "message": clean_message,
                            "severity": "error",
                            "fixable": False,
                        }
                    )

            post_canon_invalid_guids, contract_violations = _artifact_sanity_violations(
                file, strict_contract=strict_contract
            )
            invalid_guid_count = max(pre_canon_invalid_guids, post_canon_invalid_guids)
            issue_records = _engine_issues_to_records(validation_result_all)
            sanity_blockers: list[dict] = []
            if invalid_guid_count > 0:
                sanity_blockers.append(
                    {
                        "check": "artifact_sanity",
                        "line": None,
                        "message": (
                            f"Found {invalid_guid_count} malformed GUID token(s) in Id attributes."
                        ),
                        "fixable": False,
                    }
                )
            if contract_violations:
                for violation in contract_violations:
                    sanity_blockers.append(
                        {
                            "check": "generation_contract",
                            "line": None,
                            "message": violation,
                            "fixable": False,
                        }
                    )

            # Derive canonical contract state (RC-1: single source of truth).
            # Pass policy_blockers + sanity_blockers as extra_blockers so that
            # the canonical derivation accounts for them without duplicating issues.
            all_extra_blockers = policy_blockers + sanity_blockers
            cs = derive_contract_state(
                validation_result_blockers.issues,
                extra_blockers=all_extra_blockers if all_extra_blockers else None,
                profile=profile,
            )
            # Override blockers list: use cs.blockers which has the canonical merged set,
            # but replace any policy-enforcement issues with the specially-formatted dicts.
            # Strategy: build blockers as cs.blockers but substitute policy_blockers.
            non_policy_issue_blockers = [
                b
                for b in cs.blockers
                if isinstance(b, dict)
                and b.get("check") != "policy_enforcement"
                and b not in sanity_blockers
            ]
            blockers = non_policy_issue_blockers + policy_blockers + sanity_blockers
            safe_to_import = cs.safe_to_import
            safe_to_compile = cs.safe_to_compile
            if sanity_blockers:
                issue_records.extend(sanity_blockers)

            if profile == "llm_strict":
                result = {
                    "success": True,
                    "file_path": str(file.filepath),
                    "safe_to_import": safe_to_import,
                    "safe_to_compile": safe_to_compile,
                    "content_changed": content_changed,
                    "fixes_applied": fix_result.applied_fixes,
                    "blocking_count": len(blockers),
                    "blockers": blockers,
                    "invalid_guid_count": invalid_guid_count,
                    "contract_violations": contract_violations,
                }
                if create_implicit_files:
                    result["implicit_files_created"] = implicit_files_created
                if orchestration_hints:
                    no_change_detected = not content_changed
                    issue_fingerprint = _compute_issue_fingerprint(issue_records)
                    no_progress_count = _update_no_progress_count(
                        str(file.filepath),
                        issue_fingerprint,
                        content_changed,
                    )
                    next_action, terminal = _derive_next_action(
                        safe_to_import=safe_to_import,
                        safe_to_compile=safe_to_compile,
                        blockers=blockers,
                        no_change_detected=no_change_detected,
                        no_progress_count=no_progress_count,
                        contract_failed=False,
                    )
                    result.update(
                        {
                            "no_change_detected": no_change_detected,
                            "content_fingerprint_before": content_fingerprint_before,
                            "content_fingerprint_after": content_fingerprint_after,
                            "issue_fingerprint": issue_fingerprint,
                            "no_progress_count": no_progress_count,
                            "next_action": next_action,
                            "terminal": terminal,
                        }
                    )
            else:
                validation_after_fix = {
                    "status": "passed" if validation_result_all.passed else "failed",
                    "remaining_issues": len(validation_result_all.issues),
                    "error_count": validation_result_all.errors,
                    "warning_count": validation_result_all.warnings,
                }

                result = {
                    "success": True,
                    "file_path": str(file.filepath),
                    "backup_created": create_backup and content_changed,
                    "backup_path": str(backup_path) if backup_path else None,
                    "content_changed": content_changed,
                    "fixes_applied": [
                        {"type": fix_id, "description": f"Applied {fix_id} fix", "count": 1}
                        for fix_id in fix_result.applied_fixes
                    ],
                    "validation_after_fix": validation_after_fix,
                    "invalid_guid_count": invalid_guid_count,
                    "contract_violations": contract_violations,
                }
                if create_implicit_files:
                    result["implicit_files_created"] = implicit_files_created

            return _with_meta(result, _t0, execution_context=ctx)

        except Exception as e:
            error_kwargs = {"execution_context": ctx}
            if ctx is None:
                error_kwargs.update(unresolved_policy_fields(enforcement_mode))
            return _tool_error(str(e), file_path=file_path, start_time=_t0, **error_kwargs)

    @mcp.tool()
    def generate_skeleton(
        file_type: str,
        subtype: Optional[str] = None,
        enforcement_mode: str = DEFAULT_ENFORCEMENT_MODE,
    ) -> str:
        """Generate canonical deterministic TwinCAT XML skeleton for a file type.

        Args:
            file_type: .TcPOU, .TcDUT, .TcGVL, or .TcIO (with or without leading dot)
            subtype: For .TcPOU only: function_block, function, or program
        """
        _t0 = time.monotonic()
        ctx = None
        try:
            mode_error = _validate_enforcement_mode(enforcement_mode, start_time=_t0)
            if mode_error:
                return mode_error
            ctx = _resolve_execution_context("", enforcement_mode=enforcement_mode)
        except Exception as exc:
            return _tool_error(
                str(exc),
                start_time=_t0,
                **unresolved_policy_fields(enforcement_mode),
            )
        skeleton, error = _build_contract_skeleton(file_type, subtype)
        if error:
            return _tool_error(
                error,
                start_time=_t0,
                execution_context=ctx,
                supported_file_types=config.supported_extensions,
                supported_pou_subtypes=list(SUPPORTED_POU_SUBTYPES),
            )

        normalized = _normalize_file_type(file_type)
        result = {
            "success": True,
            "file_type": normalized,
            "subtype": subtype.lower() if subtype and normalized == ".TcPOU" else None,
            "contract_version": config.get_generation_contract().get("version", "unknown"),
            "skeleton": skeleton,
            "note": (
                "Fill placeholders (name/GUID/declaration/ST body), "
                "then run autofix_file with strict_contract=true."
            ),
        }
        return _with_meta(result, _t0, execution_context=ctx)

    @mcp.tool()
    def extract_methods_to_xml(file_path: str, create_backup: bool = True) -> str:
        """Promote inline METHOD blocks from main ST to <Method> XML elements.

        Args:
            file_path: Path to .TcPOU file
            create_backup: Create .bak backup when content changes
        """
        _t0 = time.monotonic()
        try:
            path, error = _validate_file_path(file_path, start_time=_t0)
            if error:
                return error

            file = TwinCATFile.from_path(path)
            if file.suffix != ".TcPOU":
                return _tool_error(
                    "extract_methods_to_xml only supports .TcPOU files",
                    file_path=file_path,
                    start_time=_t0,
                )

            before_hash = _sha256_text(file.content)
            changed, methods_extracted = _promote_inline_methods_to_xml(file)
            backup_path = None
            if changed:
                backup_path = file.save(create_backup=create_backup)

            after_hash = _sha256_text(file.content)
            return _with_meta(
                {
                    "success": True,
                    "file_path": str(file.filepath),
                    "content_changed": changed,
                    "methods_extracted": methods_extracted,
                    "backup_created": create_backup and changed,
                    "backup_path": str(backup_path) if backup_path else None,
                    "content_fingerprint_before": before_hash,
                    "content_fingerprint_after": after_hash,
                },
                _t0,
            )
        except Exception as exc:
            return _tool_error(str(exc), file_path=file_path, start_time=_t0)
