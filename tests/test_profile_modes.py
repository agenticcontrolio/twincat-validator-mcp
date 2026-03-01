"""Tests for Phase 4: Profile modes (llm_strict vs full).

Phase 4.4: Test minimal response mode reduces output size significantly.
"""

import json
import pytest

from server import autofix_file, validate_file


class TestProfileModes:
    """Test llm_strict vs full profile mode differences."""

    @pytest.fixture
    def tabs_file(self, tmp_path):
        """Create a test file with tabs."""
        content = (
            '<?xml version="1.0"?>\n'
            '<TcPlcObject Version="1.1.0.1">\n'
            '\t<POU Name="FB_Test" Id="{abcd1234-5678-90ab-cdef-1234567890ab}">\n'
            "\t\t<Declaration><![CDATA[FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR]]></Declaration>\n"
            "\t</POU>\n"
            "</TcPlcObject>\n"
        )
        file_path = tmp_path / "tabs.TcPOU"
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def test_validation_issue_to_dict_full_profile(self):
        """Test ValidationIssue.to_dict() with full profile includes all fields."""
        from twincat_validator.models import ValidationIssue

        issue = ValidationIssue(
            severity="error",
            category="Tabs",
            message="File contains tab characters",
            line_num=3,
            fix_available=True,
            fix_suggestion="Replace tabs with 2 spaces",
            code_snippet="  3 | \t<POU>",
            explanation="TwinCAT requires 2-space indentation",
            correct_example="  <POU>",
        )

        result = issue.to_dict(profile="full")

        # Full profile includes all fields
        assert "type" in result  # severity is called "type" in full profile
        assert "category" in result
        assert "message" in result
        assert "line_num" in result
        assert "auto_fixable" in result  # fix_available is called "auto_fixable"
        assert "fix_suggestion" in result
        assert "code_snippet" in result
        assert "explanation" in result
        assert "correct_example" in result

    def test_validation_issue_to_dict_llm_strict_profile(self):
        """Test ValidationIssue.to_dict() with llm_strict profile is minimal."""
        from twincat_validator.models import ValidationIssue

        issue = ValidationIssue(
            severity="error",
            category="Tabs",
            message="File contains tab characters",
            line_num=3,
            fix_available=True,
            fix_suggestion="Replace tabs with 2 spaces",
            code_snippet="  3 | \t<POU>",
            explanation="TwinCAT requires 2-space indentation",
            correct_example="  <POU>",
        )

        result = issue.to_dict(profile="llm_strict")

        # LLM strict includes only minimal fields
        assert "check" in result
        assert "line" in result
        assert "message" in result
        assert "fixable" in result

        # Should NOT include verbose fields
        assert "code_snippet" not in result
        assert "explanation" not in result
        assert "correct_example" not in result
        assert "fix_suggestion" not in result  # Omitted for fixable issues

    def test_validation_issue_llm_strict_includes_fix_suggestion_for_unfixable(self):
        """Test that llm_strict includes fix_suggestion for unfixable errors."""
        from twincat_validator.models import ValidationIssue

        issue = ValidationIssue(
            severity="error",
            category="Structure",
            message="Invalid structure",
            line_num=5,
            fix_available=False,
            fix_suggestion="Manually restructure the code",
        )

        result = issue.to_dict(profile="llm_strict")

        # For unfixable issues, include fix_suggestion
        assert "fix_suggestion" in result
        assert result["fix_suggestion"] == "Manually restructure the code"

    def test_autofix_file_full_profile_verbose_response(self, tabs_file):
        """Test autofix_file with full profile returns verbose response."""
        result_json = autofix_file(str(tabs_file), profile="full")
        result = json.loads(result_json)

        # Full profile includes verbose fields
        assert "success" in result
        assert "file_path" in result
        assert "content_changed" in result
        assert "fixes_applied" in result
        assert "validation_after_fix" in result  # Validation summary
        assert "backup_created" in result
        assert "backup_path" in result

        # validation_after_fix has summary fields
        assert "status" in result["validation_after_fix"]
        assert "remaining_issues" in result["validation_after_fix"]
        assert "error_count" in result["validation_after_fix"]
        assert "warning_count" in result["validation_after_fix"]

        # safe_to_import/safe_to_compile are only in llm_strict mode
        assert "safe_to_import" not in result
        assert "safe_to_compile" not in result

    def test_autofix_file_llm_strict_profile_minimal_response(self, tabs_file):
        """Test autofix_file with llm_strict profile returns minimal response."""
        result_json = autofix_file(str(tabs_file), profile="llm_strict")
        result = json.loads(result_json)

        # LLM strict includes only essential fields
        assert "success" in result
        assert "file_path" in result
        assert "safe_to_import" in result
        assert "safe_to_compile" in result
        assert "content_changed" in result
        assert "fixes_applied" in result
        assert "blocking_count" in result
        assert "blockers" in result

        # Should NOT include verbose validation results
        assert "validation_after_fix" not in result
        assert "backup_path" not in result

    def test_validate_file_full_profile_verbose_response(self, tabs_file):
        """Test validate_file with full profile returns verbose response."""
        result_json = validate_file(str(tabs_file), profile="full")
        result = json.loads(result_json)

        # Full profile includes verbose fields
        assert "success" in result
        assert "file_path" in result
        assert "file_type" in result
        assert "pou_subtype" in result
        assert "validation_status" in result
        assert "validation_time" in result
        assert "summary" in result
        assert "checks" in result
        assert "issues" in result
        assert "metrics" in result

    def test_validate_file_llm_strict_profile_minimal_response(self, tabs_file):
        """Test validate_file with llm_strict profile returns minimal response."""
        result_json = validate_file(str(tabs_file), profile="llm_strict")
        result = json.loads(result_json)

        # LLM strict includes only essential fields
        assert "file_path" in result
        assert "safe_to_import" in result
        assert "safe_to_compile" in result
        assert "blocking_count" in result
        assert "blockers" in result

        # Should NOT include verbose fields
        assert "file_type" not in result
        assert "pou_subtype" not in result
        assert "validation_time" not in result
        assert "summary" not in result
        assert "checks" not in result
        assert "metrics" not in result

    def test_llm_strict_response_size_significantly_smaller(self, tabs_file):
        """Test that validate_file llm_strict reduces response size by at least 90%.

        Uses validate_file (read-only) so both profiles see the same file state.
        The tabs fixture has actual issues, producing rich output in full mode
        (checks, issues, summary, metrics) that gets stripped in llm_strict.
        Use intent_profile="oop" to ensure the full OOP check set runs for both
        profiles (measuring the full payload vs strict, not the profile filter).
        Actual reduction is ~98%, so 90% threshold catches meaningful regressions
        without being fragile.
        """
        from server import validate_file

        full_json = validate_file(str(tabs_file), profile="full", intent_profile="oop")
        strict_json = validate_file(str(tabs_file), profile="llm_strict", intent_profile="oop")

        full_size = len(full_json)
        strict_size = len(strict_json)

        reduction_ratio = (full_size - strict_size) / full_size
        assert reduction_ratio >= 0.90, (
            f"LLM strict mode only reduced response size by {reduction_ratio*100:.1f}%. "
            f"Expected at least 90% reduction. Full: {full_size} bytes, Strict: {strict_size} bytes"
        )

    def test_autofix_llm_strict_is_more_compact_than_full(self, tmp_path):
        """Test that autofix_file llm_strict is more compact than full mode.

        Uses separate file copies so mutation doesn't contaminate the comparison.
        autofix_file's full response is already compact, so we assert a modest
        but meaningful reduction (at least 20%).
        """
        import shutil
        from server import autofix_file

        source = tmp_path / "original.TcPOU"
        source.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
            '  <POU Name="FB_Test" Id="{AABB1234-5678-9abc-def0-123456789abc}"'
            ' SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR"
            "]]></Declaration>\n"
            "\t\t<Implementation>\n"
            "      <ST><![CDATA[]]></ST>\n"
            "    </Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>\n",
            encoding="utf-8",
        )

        full_copy = tmp_path / "full_copy.TcPOU"
        strict_copy = tmp_path / "strict_copy.TcPOU"
        shutil.copy2(source, full_copy)
        shutil.copy2(source, strict_copy)

        full_json = autofix_file(str(full_copy), profile="full")
        strict_json = autofix_file(str(strict_copy), profile="llm_strict")

        full_size = len(full_json)
        strict_size = len(strict_json)

        reduction_ratio = (full_size - strict_size) / full_size
        assert reduction_ratio >= 0.20, (
            f"autofix_file llm_strict only reduced by {reduction_ratio*100:.1f}%. "
            f"Expected at least 20%. Full: {full_size} bytes, Strict: {strict_size} bytes"
        )

    def test_safe_to_import_flag_derivation(self, tmp_path):
        """Test safe_to_import flag is correctly derived from critical errors."""
        malformed_content = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.0">\n'
            '  <POU Name="FB_Test" Id="{abcd1234-5678-90ab-cdef-1234567890ab}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_Test\n"
            "VAR\n"
            "END_VAR\n"
            "]]></Declaration>\n"
            "  </POU>\n"
        )  # Missing closing </TcPlcObject>
        malformed_file = tmp_path / "malformed.TcPOU"
        malformed_file.write_text(malformed_content, encoding="utf-8")

        result = autofix_file(str(malformed_file), profile="llm_strict")
        result_dict = json.loads(result)

        assert result_dict["safe_to_import"] is False
        assert result_dict["blocking_count"] >= 1

    def test_safe_to_compile_flag_derivation(self, tmp_path):
        """Test safe_to_compile is True with warnings, False with errors."""
        # Warnings should NOT prevent compilation
        # File has proper structure (no errors) but naming convention warning
        warning_only_content = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.0">\n'
            '  <POU Name="MyBlock" Id="{abcd1234-5678-90ab-cdef-1234567890ab}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_Test\n"
            "VAR\n"
            "END_VAR\n"
            "]]></Declaration>\n"
            "    <Implementation>\n"
            "      <ST><![CDATA[]]></ST>\n"
            "    </Implementation>\n"
            '    <LineIds Name="MyBlock">\n'
            '      <LineId Id="1" Count="0" />\n'
            "    </LineIds>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )
        warning_file = tmp_path / "warning_only.TcPOU"
        warning_file.write_text(warning_only_content, encoding="utf-8")

        result = autofix_file(str(warning_file), profile="llm_strict")
        result_dict = json.loads(result)

        # Warnings should not block import or compilation
        assert result_dict["safe_to_import"] is True
        assert result_dict["safe_to_compile"] is True  # Warnings are OK

    def test_validate_file_invalid_profile_returns_error(self, tabs_file):
        """Invalid profile should return clear error."""
        result_json = validate_file(str(tabs_file), profile="compact")
        result = json.loads(result_json)
        assert result["success"] is False
        assert "Invalid profile" in result["error"]
        assert result["valid_profiles"] == ["full", "llm_strict"]

    def test_autofix_file_invalid_profile_returns_error(self, tabs_file):
        """Invalid profile should return clear error."""
        result_json = autofix_file(str(tabs_file), profile="compact")
        result = json.loads(result_json)
        assert result["success"] is False
        assert "Invalid profile" in result["error"]
        assert result["valid_profiles"] == ["full", "llm_strict"]
