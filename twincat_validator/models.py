"""Data models for validation and fix results."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


class ValidationIssue:
    """Represents a validation issue.

    Extracted from server.py (lines 202-232).
    Enhanced with Phase 3 fields (set to None in Phase 2 for backward compatibility).
    """

    def __init__(
        self,
        severity: str,
        category: str,
        message: str,
        line_num: Optional[int] = None,
        column: Optional[int] = None,
        fix_available: bool = False,
        fix_suggestion: Optional[str] = None,
        known_limitation: Optional[bool] = None,
        limitation_code: Optional[str] = None,
        code_snippet: Optional[str] = None,  # Phase 3 field
        explanation: Optional[str] = None,  # Phase 3 field
        correct_example: Optional[str] = None,  # Phase 3 field
        check_id: Optional[str] = None,  # stamped by ValidationEngine
    ):
        self.severity = severity  # 'error', 'warning', 'info'
        self.category = category
        self.message = message
        self.line_num = line_num
        self.column = column
        self.fix_available = fix_available
        self.fix_suggestion = fix_suggestion
        self.known_limitation = known_limitation
        self.limitation_code = limitation_code

        # Phase 3 fields (populated as None in Phase 2)
        self.code_snippet = code_snippet
        self.explanation = explanation
        self.correct_example = correct_example

        # Stamped by ValidationEngine after check.run(); used for tracing and dedup
        self.check_id = check_id

    def to_dict(self, profile: str = "full") -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Maintains exact output format from Phase 1 for backward compatibility.
        Phase 3 fields omitted if None.

        Args:
            profile: "full" (default) includes all fields, "llm_strict" minimal fields only

        Returns:
            Dictionary representation for JSON serialization
        """
        if profile == "llm_strict":
            # Minimal response for LLM workflows (Phase 4)
            # Omit Phase 3 fields and fix_suggestion for auto-fixable issues.
            # Canonical keys (severity, category, line_num, auto_fixable) are emitted
            # alongside the legacy short keys (check, line, fixable) for backward
            # compatibility. Legacy keys will be removed in a future phase.
            result = {
                "check": self.category,  # legacy — use "category" instead
                "category": self.category,  # canonical
                "line": self.line_num,  # legacy — use "line_num" instead
                "line_num": self.line_num,  # canonical
                "message": self.message,
                "fixable": self.fix_available,  # legacy — use "auto_fixable" instead
                "auto_fixable": self.fix_available,  # canonical
                "severity": self.severity,  # canonical (was absent in llm_strict)
            }
            # Only include fix_suggestion for non-fixable issues
            if not self.fix_available and self.fix_suggestion:
                result["fix_suggestion"] = self.fix_suggestion
            if self.known_limitation is not None:
                result["known_limitation"] = self.known_limitation
            if self.limitation_code:
                result["limitation_code"] = self.limitation_code
            if self.check_id:
                result["check_id"] = self.check_id
            return result

        # Full profile (backward compatible, default)
        # "type" is the legacy key for severity; "severity" is the canonical key.
        # Both are emitted so callers can migrate at their own pace.
        result = {
            "type": self.severity,  # legacy — use "severity" instead
            "severity": self.severity,  # canonical
            "category": self.category,
            "message": self.message,
            "location": f"Line {self.line_num}" if self.line_num else None,
            "line_num": self.line_num,
            "column": self.column,
            "auto_fixable": self.fix_available,
            "fix_suggestion": self.fix_suggestion,
        }
        if self.known_limitation is not None:
            result["known_limitation"] = self.known_limitation
        if self.limitation_code:
            result["limitation_code"] = self.limitation_code

        # Add Phase 3 fields only if populated (not in Phase 2)
        if self.code_snippet:
            result["code_snippet"] = self.code_snippet
        if self.explanation:
            result["explanation"] = self.explanation
        if self.correct_example:
            result["correct_example"] = self.correct_example

        if self.check_id:
            result["check_id"] = self.check_id

        return result


@dataclass
class CheckResult:
    """Result of running a single validation check."""

    check_id: str
    check_name: str
    status: str  # 'passed', 'failed', 'warning', 'skipped'
    message: str
    auto_fixable: bool
    severity: str
    issues: list[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON format matching current server.py output."""
        return {
            "id": self.check_id,
            "name": self.check_name,
            "status": self.status,
            "message": self.message,
            "auto_fixable": self.auto_fixable,
            "severity": self.severity,
        }


@dataclass
class ValidationResult:
    """Complete validation result for a file."""

    file_path: Path
    file_type: str
    pou_subtype: Optional[str]
    file_size: int
    validation_status: str  # 'passed', 'failed', 'warnings'
    validation_time: float
    checks: list[CheckResult]
    issues: list[ValidationIssue]
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON format matching current server.py output exactly."""
        return {
            "file_path": str(self.file_path),
            "file_type": self.file_type,
            "pou_subtype": self.pou_subtype,
            "file_size": self.file_size,
            "validation_status": self.validation_status,
            "validation_time": round(self.validation_time, 3),
            "summary": {
                "total_checks": len(self.checks),
                "passed": sum(1 for c in self.checks if c.status == "passed"),
                "failed": sum(1 for c in self.checks if c.status == "failed"),
                "warnings": sum(1 for c in self.checks if c.status == "warning"),
            },
            "checks": [c.to_dict() for c in self.checks],
            "issues": [i.to_dict() for i in self.issues],
            "metrics": self.metrics,
        }


@dataclass
class FixApplication:
    """Single fix that was applied."""

    fix_type: str
    description: str
    count: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON format."""
        return {
            "type": self.fix_type,
            "description": self.description,
            "count": self.count,
        }


# Engine-specific result models (simpler than the above MCP-output models)


@dataclass
class EngineCheckResult:
    """Simplified result of running a single check (used internally by ValidationEngine)."""

    check_id: str
    passed: bool
    issues: list[ValidationIssue] = field(default_factory=list)


@dataclass
class EngineValidationResult:
    """Simplified validation result (used internally by ValidationEngine)."""

    filepath: str
    passed: bool  # True if no errors
    issues: list[ValidationIssue] = field(default_factory=list)
    check_results: list[EngineCheckResult] = field(default_factory=list)
    errors: int = 0
    warnings: int = 0
    infos: int = 0


@dataclass
class EngineFixResult:
    """Simplified fix result (used internally by FixEngine)."""

    filepath: str
    applied_fixes: list[str] = field(default_factory=list)
    failed_fixes: list[str] = field(default_factory=list)
    success: bool = True  # True if no fixes failed
