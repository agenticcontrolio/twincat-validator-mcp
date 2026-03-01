"""Tests for twincat_validator.models module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from twincat_validator.models import (
    ValidationIssue,
    CheckResult,
    ValidationResult,
    FixApplication,
)


class TestValidationIssue:
    """Tests for ValidationIssue model."""

    def test_to_dict_basic(self):
        """Test to_dict() produces correct output format."""
        issue = ValidationIssue(
            severity="error",
            category="GUID",
            message="Invalid GUID format",
            line_num=42,
            fix_available=True,
            fix_suggestion="Use lowercase hex only",
        )

        result = issue.to_dict()

        assert result["type"] == "error"
        assert result["category"] == "GUID"
        assert result["message"] == "Invalid GUID format"
        assert result["location"] == "Line 42"
        assert result["line_num"] == 42
        assert "column" in result
        assert result["column"] is None
        assert result["auto_fixable"] is True
        assert result["fix_suggestion"] == "Use lowercase hex only"

    def test_to_dict_backward_compatibility(self):
        """Test to_dict() maintains Phase 1 output format."""
        issue = ValidationIssue(
            severity="warning",
            category="Style",
            message="Tab characters detected",
        )

        result = issue.to_dict()

        # Required keys from Phase 1
        assert "type" in result
        assert "category" in result
        assert "message" in result
        assert "location" in result
        assert "line_num" in result
        assert "column" in result
        assert "auto_fixable" in result
        assert "fix_suggestion" in result

        # Phase 3 fields should not appear when None
        assert "code_snippet" not in result
        assert "explanation" not in result
        assert "correct_example" not in result

    def test_phase3_fields_in_dict_when_provided(self):
        """Test Phase 3 fields appear in dict when provided."""
        issue = ValidationIssue(
            severity="error",
            category="Test",
            message="Test message",
            code_snippet="  <Bad>",
            explanation="Why this is bad",
            correct_example="<Good>",
        )

        result = issue.to_dict()

        assert result["code_snippet"] == "  <Bad>"
        assert result["explanation"] == "Why this is bad"
        assert result["correct_example"] == "<Good>"

    def test_known_limitation_fields_in_dict_when_provided(self):
        """Test known limitation metadata appears when populated."""
        issue = ValidationIssue(
            severity="error",
            category="Structure",
            message="signature mismatch",
            known_limitation=True,
            limitation_code="interface_signature_text_normalization",
        )
        result = issue.to_dict()
        assert result["known_limitation"] is True
        assert result["limitation_code"] == "interface_signature_text_normalization"


class TestCheckResult:
    """Tests for CheckResult model."""

    def test_to_dict_format(self):
        """Test to_dict() produces correct output format."""
        check = CheckResult(
            check_id="guid_format",
            check_name="GUID Format Validation",
            status="failed",
            message="Validates GUID format",
            auto_fixable=True,
            severity="critical",
            issues=[],
        )

        result = check.to_dict()

        assert result["id"] == "guid_format"
        assert result["name"] == "GUID Format Validation"
        assert result["status"] == "failed"
        assert result["message"] == "Validates GUID format"
        assert result["auto_fixable"] is True
        assert result["severity"] == "critical"


class TestValidationResult:
    """Tests for ValidationResult model."""

    def test_to_dict_structure(self):
        """Test to_dict() produces complete validation result structure."""
        result_obj = ValidationResult(
            file_path=Path("/test/file.TcPOU"),
            file_type=".TcPOU",
            pou_subtype="function_block",
            file_size=1024,
            validation_status="passed",
            validation_time=0.123456,
            checks=[],
            issues=[],
            metrics={},
        )

        result = result_obj.to_dict()

        # Required top-level keys
        assert "file_path" in result
        assert "file_type" in result
        assert "pou_subtype" in result
        assert "file_size" in result
        assert "validation_status" in result
        assert "validation_time" in result
        assert "summary" in result
        assert "checks" in result
        assert "issues" in result
        assert "metrics" in result

        # Summary structure
        assert result["summary"]["total_checks"] == 0
        assert result["summary"]["passed"] == 0
        assert result["summary"]["failed"] == 0
        assert result["summary"]["warnings"] == 0

        # Validation time should be rounded
        assert result["validation_time"] == 0.123


class TestFixApplication:
    """Tests for FixApplication model."""

    def test_to_dict_format(self):
        """Test to_dict() produces correct output format."""
        fix = FixApplication(
            fix_type="tabs",
            description="Replaced 5 tabs with spaces",
            count=5,
        )

        result = fix.to_dict()

        assert result["type"] == "tabs"
        assert result["description"] == "Replaced 5 tabs with spaces"
        assert result["count"] == 5
