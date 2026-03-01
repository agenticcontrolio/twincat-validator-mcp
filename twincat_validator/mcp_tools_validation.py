"""MCP tool handlers: validation tools.

Tools registered here:
- validate_file
- validate_for_import
- check_specific
- get_validation_summary
- suggest_fixes
"""

import json
import time

from twincat_validator import CheckRegistry, TwinCATFile
from twincat_validator._server_helpers import (
    _apply_known_limitation_tags,
    _convert_engine_result_to_mcp_format,
    _dedupe_validation_issues,
    _resolve_execution_context,
    _validate_enforcement_mode,
    _validate_file_path,
    _validate_profile,
)
from twincat_validator.mcp_app import (
    DEFAULT_ENFORCEMENT_MODE,
    config,
    mcp,
    validation_engine,
)
from twincat_validator.mcp_responses import _tool_error, _with_meta, unresolved_policy_fields
from twincat_validator.snippet_extractor import infer_issue_location
from twincat_validator.utils import _VALID_INTENT_PROFILES, _resolve_intent_profile


def register_validation_tools() -> None:
    """Register all validation tool handlers with the mcp instance."""

    @mcp.tool()
    def validate_file(
        file_path: str,
        validation_level: str = "all",
        profile: str = "full",
        enforcement_mode: str = DEFAULT_ENFORCEMENT_MODE,
        intent_profile: str = "auto",
    ) -> str:
        """Validate a single TwinCAT file.

        Args:
            file_path: Path to TwinCAT file
            validation_level: "all", "critical", or "style"
            profile: Output profile - "full" (verbose, default) or "llm_strict" (minimal)
            intent_profile: Programming paradigm intent — "auto" (default), "procedural",
                or "oop".  Controls which check families run:
                - "procedural": OOP checks are skipped.
                - "oop": Full OOP check family is enforced.
                - "auto": Resolved from file content (EXTENDS/IMPLEMENTS → oop, else procedural).

        Returns:
            JSON string with validation results.

            Full profile includes: validation_status, checks array, issues with Phase 3
            enrichment, metrics, timing.

            LLM strict profile includes only: file_path, safe_to_import, safe_to_compile,
            blocking_count, blockers (unfixable errors).
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
            if validation_level not in ["all", "critical", "style"]:
                return _tool_error(
                    f"Invalid validation_level: {validation_level}",
                    file_path=file_path,
                    start_time=_t0,
                    execution_context=ctx,
                    valid_levels=["all", "critical", "style"],
                )
            profile_error = _validate_profile(profile, start_time=_t0, execution_context=ctx)
            if profile_error:
                return profile_error

            path, error = _validate_file_path(file_path, start_time=_t0, execution_context=ctx)
            if error:
                return error

            file = TwinCATFile.from_path(path)

            _intent_resolved = _resolve_intent_profile(file.content, intent_profile)
            _exclude_cats = frozenset({"oop"}) if _intent_resolved == "procedural" else None

            engine_start = time.time()
            engine_result = validation_engine.validate(
                file, validation_level, exclude_categories=_exclude_cats
            )
            validation_time = time.time() - engine_start

            result = _convert_engine_result_to_mcp_format(
                engine_result, file, validation_time, validation_level, profile
            )
            result["success"] = True

            return _with_meta(result, _t0, execution_context=ctx)

        except Exception as e:
            error_kwargs = {"execution_context": ctx}
            if ctx is None:
                error_kwargs.update(unresolved_policy_fields(enforcement_mode))
            return _tool_error(
                str(e),
                file_path=file_path,
                start_time=_t0,
                **error_kwargs,
            )

    @mcp.tool()
    def validate_for_import(
        file_path: str, enforcement_mode: str = DEFAULT_ENFORCEMENT_MODE
    ) -> str:
        """Quick validation check for TwinCAT import readiness.

        Args:
            file_path: Path to TwinCAT file
        """
        _t0 = time.monotonic()
        ctx = None
        try:
            mode_error = _validate_enforcement_mode(enforcement_mode, start_time=_t0)
            if mode_error:
                return mode_error
            ctx = _resolve_execution_context(file_path, enforcement_mode=enforcement_mode)
            path, error = _validate_file_path(file_path, start_time=_t0, execution_context=ctx)
            if error:
                return error

            engine_start = time.time()

            file = TwinCATFile.from_path(path)
            engine_result = validation_engine.validate(file, "critical")

            safe_to_import = engine_result.errors == 0

            deduped_issues = _dedupe_validation_issues(engine_result.issues)
            critical_issues = [
                {"category": issue.category, "message": issue.message, "severity": "critical"}
                for issue in deduped_issues
                if issue.severity in ("error", "critical")
            ]

            result = {
                "success": True,
                "file_path": str(path),
                "safe_to_import": safe_to_import,
                "critical_issues": critical_issues,
                "error_count": engine_result.errors,
                "validation_time": round(time.time() - engine_start, 3),
            }

            return _with_meta(result, _t0, execution_context=ctx)

        except Exception as e:
            error_kwargs = {"execution_context": ctx}
            if ctx is None:
                error_kwargs.update(unresolved_policy_fields(enforcement_mode))
            return _tool_error(
                str(e),
                file_path=file_path,
                start_time=_t0,
                **error_kwargs,
            )

    @mcp.tool()
    def check_specific(
        file_path: str,
        check_names: list[str],
        enforcement_mode: str = DEFAULT_ENFORCEMENT_MODE,
    ) -> str:
        """Run specific validation checks on a TwinCAT file.

        Args:
            file_path: Path to TwinCAT file
            check_names: List of check IDs to run
        """
        _t0 = time.monotonic()
        ctx = None
        try:
            mode_error = _validate_enforcement_mode(enforcement_mode, start_time=_t0)
            if mode_error:
                return mode_error
            ctx = _resolve_execution_context(file_path, enforcement_mode=enforcement_mode)
            check_id_map = config.check_id_map

            check_ids = []
            for name in check_names:
                check_id = check_id_map.get(name, name)
                check_ids.append(check_id)

            valid_checks = set(config.validation_checks.keys())
            invalid = set(check_ids) - valid_checks
            if invalid:
                return _tool_error(
                    f"Invalid check names: {', '.join(invalid)}",
                    file_path=file_path,
                    start_time=_t0,
                    execution_context=ctx,
                    valid_checks=sorted(list(valid_checks)),
                )

            path, error = _validate_file_path(file_path, start_time=_t0, execution_context=ctx)
            if error:
                return error

            file = TwinCATFile.from_path(path)

            all_issues = []
            check_results = []
            for check_id in check_ids:
                if check_id in config.disabled_checks:
                    continue

                try:
                    from twincat_validator.exceptions import CheckNotFoundError

                    check_class = CheckRegistry.get_check(check_id)
                except CheckNotFoundError:
                    continue

                check = check_class()
                if check.should_skip(file):
                    continue

                issues = check.run(file)
                if check_id in config.severity_overrides:
                    for issue in issues:
                        issue.severity = config.severity_overrides[check_id]
                for issue in issues:
                    issue.check_id = (
                        check_id  # stamp for dedupe/tracing parity with ValidationEngine
                    )
                    if issue.line_num is not None:
                        _apply_known_limitation_tags(check_id, issue, file)
                        continue
                    line_num, column = infer_issue_location(file.content, check_id, issue.message)
                    issue.line_num = line_num
                    issue.column = column
                    _apply_known_limitation_tags(check_id, issue, file)

                all_issues.extend(issues)
                check_config = config.validation_checks.get(check_id, {})

                if any(i.severity in ("error", "critical") for i in issues):
                    status = "failed"
                elif any(i.severity == "warning" for i in issues):
                    status = "warning"
                else:
                    status = "passed"

                check_results.append(
                    {
                        "id": check_id,
                        "name": check_config.get("name", "Unknown Check"),
                        "status": status,
                        "message": check_config.get("description", ""),
                        "auto_fixable": check_config.get("auto_fixable", False),
                        "severity": check_config.get("severity", "info"),
                    }
                )

            passed = sum(1 for c in check_results if c["status"] == "passed")
            failed = sum(1 for c in check_results if c["status"] == "failed")
            warnings = sum(1 for c in check_results if c["status"] == "warning")

            validation_status = "passed"
            if failed > 0:
                validation_status = "failed"
            elif warnings > 0:
                validation_status = "warnings"

            all_issues = _dedupe_validation_issues(all_issues)
            result = {
                "success": True,
                "file_path": str(path),
                "validation_status": validation_status,
                "checks_requested": len(check_names),
                "summary": {"passed": passed, "failed": failed, "warnings": warnings},
                "checks": check_results,
                "issues": [issue.to_dict() for issue in all_issues],
            }

            return _with_meta(result, _t0, execution_context=ctx)

        except Exception as e:
            error_kwargs = {"execution_context": ctx}
            if ctx is None:
                error_kwargs.update(unresolved_policy_fields(enforcement_mode))
            return _tool_error(
                str(e),
                file_path=file_path,
                start_time=_t0,
                **error_kwargs,
            )

    @mcp.tool()
    def get_validation_summary(file_path: str) -> str:
        """Get high-level file quality summary with health score.

        Args:
            file_path: Path to TwinCAT file
        """
        _t0 = time.monotonic()
        try:
            path, error = _validate_file_path(file_path, start_time=_t0)
            if error:
                return error

            file = TwinCATFile.from_path(path)
            engine_result = validation_engine.validate(file, "all")

            health_score = 100
            health_score -= engine_result.errors * 25
            health_score -= engine_result.warnings * 5
            health_score -= engine_result.infos * 1
            health_score = max(0, min(100, health_score))

            if health_score >= 90:
                status = "excellent"
            elif health_score >= 70:
                status = "good"
            elif health_score >= 50:
                status = "needs_work"
            else:
                status = "critical_issues"

            quick_fixes = sum(1 for issue in engine_result.issues if issue.fix_available)

            if quick_fixes == 0:
                fix_time = "No fixes needed"
            elif quick_fixes <= 3:
                fix_time = "< 1 minute"
            elif quick_fixes <= 10:
                fix_time = "1-2 minutes"
            else:
                fix_time = "2-5 minutes"

            result = {
                "success": True,
                "file_path": str(path),
                "health_score": health_score,
                "status": status,
                "issue_breakdown": {
                    "critical": engine_result.errors,
                    "warnings": engine_result.warnings,
                    "info": engine_result.infos,
                },
                "quick_fixes_available": quick_fixes,
                "estimated_fix_time": fix_time,
            }

            return _with_meta(result, _t0)

        except Exception as e:
            return _tool_error(str(e), file_path=file_path, start_time=_t0)

    @mcp.tool()
    def suggest_fixes(validation_result: str) -> str:
        """Generate prioritized fix recommendations from validation results.

        Args:
            validation_result: JSON string from validate_file()
        """
        _t0 = time.monotonic()
        try:
            result = json.loads(validation_result)

            if not result.get("success"):
                return _tool_error("Invalid validation result provided", start_time=_t0)

            issues = result.get("issues", [])

            fixes = []
            auto_fixable = 0
            manual_required = 0

            for issue in issues:
                priority = (
                    "high"
                    if issue["type"] == "error"
                    else "medium" if issue["type"] == "warning" else "low"
                )
                fix_type = "auto" if issue["auto_fixable"] else "manual"

                if fix_type == "auto":
                    auto_fixable += 1
                else:
                    manual_required += 1

                if fix_type == "auto":
                    effort = "< 1 second (automatic)"
                elif issue["category"] in ["GUID", "XML"]:
                    effort = "5-10 minutes (requires regeneration)"
                elif issue["category"] in ["Naming", "Order"]:
                    effort = "2-5 minutes (refactoring)"
                else:
                    effort = "1-2 minutes (simple edit)"

                fix_suggestion = {
                    "priority": priority,
                    "type": fix_type,
                    "category": issue["category"],
                    "issue": issue["message"],
                    "solution": issue.get("fix_suggestion", "Manual correction required"),
                    "code_example": None,
                    "estimated_effort": effort,
                }

                fixes.append(fix_suggestion)

            priority_order = {"high": 0, "medium": 1, "low": 2}
            fixes.sort(key=lambda x: priority_order[x["priority"]])

            result = {
                "success": True,
                "fixes": fixes,
                "auto_fixable_count": auto_fixable,
                "manual_fixes_required": manual_required,
            }

            return _with_meta(result, _t0)

        except json.JSONDecodeError:
            return _tool_error("Invalid JSON in validation_result", start_time=_t0)
        except Exception as e:
            return _tool_error(str(e), start_time=_t0)
