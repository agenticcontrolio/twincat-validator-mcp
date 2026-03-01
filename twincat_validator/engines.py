"""Orchestration engines for validation and auto-fix operations."""

from typing import Optional

from .file_handler import TwinCATFile
from .config_loader import ValidationConfig
from .models import EngineValidationResult, EngineCheckResult, EngineFixResult, ValidationIssue
from .validators import CheckRegistry
from .fixers import FixRegistry
from .exceptions import CheckNotFoundError, FixNotFoundError


class ValidationEngine:
    """Orchestrates execution of validation checks on TwinCAT files.

    The engine:
    - Retrieves checks from CheckRegistry based on validation level
    - Runs checks against the file
    - Aggregates results into ValidationResult
    - Respects check severity overrides and disabled checks
    """

    def __init__(self, config: ValidationConfig):
        """Initialize the validation engine.

        Args:
            config: ValidationConfig instance with check definitions and overrides
        """
        self.config = config

    def validate(
        self,
        file: TwinCATFile,
        validation_level: str = "all",
        exclude_categories: Optional[frozenset[str]] = None,
    ) -> EngineValidationResult:
        """Run validation checks on the file.

        Args:
            file: TwinCATFile to validate
            validation_level: "all", "critical", or "style" to filter checks
            exclude_categories: Optional set of category names whose checks are
                skipped entirely (e.g. ``frozenset({"oop"})`` for procedural mode).
                Uses the ``category`` field from ``validation_rules.json``.

        Returns:
            EngineValidationResult with all issues found
        """
        # Get checks to run based on validation level
        checks_to_run = self._get_checks_for_level(
            validation_level, exclude_categories=exclude_categories
        )

        # Run all checks
        all_issues = []
        check_results = []

        for check_id in checks_to_run:
            # Skip disabled checks
            if check_id in self.config.disabled_checks:
                continue

            # Get check class and instantiate
            try:
                check_class = CheckRegistry.get_check(check_id)
            except CheckNotFoundError:
                # Check not found in registry (might not be implemented yet)
                continue

            check = check_class()

            # Skip if should_skip returns True
            try:
                if check.should_skip(file):
                    continue
            except Exception as exc:
                skip_issue = ValidationIssue(
                    severity="error",
                    category=check_id,
                    message=f"Check should_skip() crashed: {type(exc).__name__}: {exc}",
                    check_id=check_id,
                )
                all_issues.append(skip_issue)
                check_results.append(
                    EngineCheckResult(check_id=check_id, issues=[skip_issue], passed=False)
                )
                continue

            # Run check — isolated so one broken check never aborts the pipeline
            try:
                issues = check.run(file)
            except Exception as exc:
                crash_issue = ValidationIssue(
                    severity="error",
                    category=check_id,
                    message=f"Check crashed: {type(exc).__name__}: {exc}",
                    check_id=check_id,
                )
                all_issues.append(crash_issue)
                check_results.append(
                    EngineCheckResult(check_id=check_id, issues=[crash_issue], passed=False)
                )
                continue

            # Stamp origin and apply severity overrides
            for issue in issues:
                issue.check_id = check_id
                if check_id in self.config.severity_overrides:
                    issue.severity = self.config.severity_overrides[check_id]

            all_issues.extend(issues)
            check_results.append(
                EngineCheckResult(
                    check_id=check_id,
                    issues=issues,
                    passed=len(issues) == 0,
                )
            )

        # Count issues by severity
        # Treat "critical" as an error-class severity for engine pass/fail semantics.
        errors = sum(1 for issue in all_issues if issue.severity in ("error", "critical"))
        warnings = sum(1 for issue in all_issues if issue.severity == "warning")
        infos = sum(1 for issue in all_issues if issue.severity == "info")

        return EngineValidationResult(
            filepath=str(file.filepath),
            passed=errors == 0,
            issues=all_issues,
            check_results=check_results,
            errors=errors,
            warnings=warnings,
            infos=infos,
        )

    def _get_checks_for_level(
        self,
        validation_level: str,
        exclude_categories: Optional[frozenset[str]] = None,
    ) -> list[str]:
        """Get list of check IDs to run for the given validation level.

        Args:
            validation_level: "all", "critical", or "style"
            exclude_categories: Optional set of category names to exclude.
                Any check whose ``category`` field matches an entry in this set
                is excluded from the returned list.  Example:
                ``frozenset({"oop"})`` removes all OOP-family checks.

        Returns:
            List of check IDs to run

        Note: checks marked ``umbrella_alias=true`` in validation_rules.json are
        excluded from all automatic run paths (RC-3: structural de-duplication).
        They remain available via check_specific() for explicit invocation.
        """
        _exclude = exclude_categories or frozenset()

        def _is_runnable(check_def: dict) -> bool:
            """True when a check should be included in automatic run paths."""
            # umbrella_alias=true: legacy umbrella delegating to sub-checks (RC-3)
            # guidance_only=true:  config-only entry with no registered check class
            if check_def.get("umbrella_alias", False):
                return False
            if check_def.get("guidance_only", False):
                return False
            # Category exclusion: skip if the check's category is in the exclude set
            if check_def.get("category") in _exclude:
                return False
            return True

        if validation_level == "all":
            return [
                check_id
                for check_id, check_def in self.config.validation_checks.items()
                if _is_runnable(check_def)
            ]
        elif validation_level == "critical":
            return [
                check_id
                for check_id, check_def in self.config.validation_checks.items()
                if _is_runnable(check_def)
                and (
                    check_def.get("severity") in ("critical", "error")
                    or check_def.get("category") == "critical"
                )
            ]
        elif validation_level == "style":
            return [
                check_id
                for check_id, check_def in self.config.validation_checks.items()
                if _is_runnable(check_def)
                and (
                    check_def.get("severity") in ["warning", "info"]
                    or check_def.get("category") == "style"
                )
            ]
        else:
            return [
                check_id
                for check_id, check_def in self.config.validation_checks.items()
                if _is_runnable(check_def)
            ]


class FixEngine:
    """Orchestrates execution of auto-fix operations on TwinCAT files.

    The engine:
    - Retrieves fixes from FixRegistry
    - Applies fixes in order
    - Tracks which fixes were applied successfully
    - Returns FixApplication results
    """

    def __init__(self, config: ValidationConfig):
        """Initialize the fix engine.

        Args:
            config: ValidationConfig instance with fix definitions
        """
        self.config = config

    def apply_fixes(
        self, file: TwinCATFile, fix_ids: Optional[list[str]] = None
    ) -> EngineFixResult:
        """Apply fixes to the file.

        Args:
            file: TwinCATFile to fix (modified in-place)
            fix_ids: List of fix IDs to apply, or None to apply all available fixes

        Returns:
            EngineFixResult with results of fix operations
        """
        # If no fix_ids specified, get all auto-fixable issues
        if fix_ids is None:
            fix_ids = list(self.config.fix_capabilities.keys())

        # Sort fixes by order field for deterministic execution
        # Fixes are sorted by the "order" field in fix_capabilities.json
        def get_fix_order(fix_id: str) -> int:
            fix_config = self.config.fix_capabilities.get(fix_id, {})
            return fix_config.get("order", 999)  # Default to high number if no order

        fix_ids = sorted(fix_ids, key=get_fix_order)

        applied_fixes = []
        failed_fixes = []

        for fix_id in fix_ids:
            # Get fix class and instantiate
            try:
                fix_class = FixRegistry.get_fix(fix_id)
            except FixNotFoundError:
                # Fix not found in registry
                failed_fixes.append(fix_id)
                continue

            fix = fix_class()

            # Skip if should_skip returns True
            if fix.should_skip(file):
                continue

            # Apply fix
            try:
                success = fix.apply(file)
                if success:
                    applied_fixes.append(fix_id)
                # If success=False, fix was not needed (no changes made)
            except Exception:
                failed_fixes.append(fix_id)
                # Could log exception here if needed

        return EngineFixResult(
            filepath=str(file.filepath),
            applied_fixes=applied_fixes,
            failed_fixes=failed_fixes,
            success=len(failed_fixes) == 0,
        )
