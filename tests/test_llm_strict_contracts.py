"""Phase 5A.1: Contract tests for llm_strict response schemas.

These tests enforce the exact API contract for deterministic LLM workflows.
If these tests fail, it means a BREAKING CHANGE to the llm_strict API.

Contract guarantees:
1. Exact required keys (no more, no less)
2. Correct types for all fields
3. Semantic correctness (safe flags, blockers)
4. Backward compatibility (full profile unchanged)
"""

import json
import pytest

from server import autofix_file, validate_file, validate_for_import


class TestAutofixFileLLMStrictContract:
    """Contract tests for autofix_file(profile="llm_strict")."""

    @pytest.fixture
    def test_file_with_errors(self, tmp_path):
        """Create a test file with fixable and unfixable errors."""
        content = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1">\n'
            '\t<POU Name="FB_Test" Id="{ABCD1234-5678-90AB-CDEF-ABCD1234ABCD}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_Test\n"
            "VAR\n"
            "END_VAR\n"
            "]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )
        file_path = tmp_path / "test.TcPOU"
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def test_response_has_exact_required_keys(self, test_file_with_errors):
        """Test that llm_strict response has exactly the required keys."""
        result_json = autofix_file(str(test_file_with_errors), profile="llm_strict")
        result = json.loads(result_json)

        # REQUIRED keys - must be present
        required_keys = {
            "success",
            "file_path",
            "safe_to_import",
            "safe_to_compile",
            "content_changed",
            "fixes_applied",
            "blocking_count",
            "blockers",
            "invalid_guid_count",
            "contract_violations",
            "policy_checked",
            "policy_source",
            "policy_fingerprint",
            "enforcement_mode",
            "response_version",
            "meta",
        }

        actual_keys = set(result.keys())

        # Assert exact match
        assert actual_keys == required_keys, (
            f"Contract violation: llm_strict response keys changed. "
            f"Expected: {sorted(required_keys)}, "
            f"Got: {sorted(actual_keys)}, "
            f"Missing: {sorted(required_keys - actual_keys)}, "
            f"Extra: {sorted(actual_keys - required_keys)}"
        )

    def test_response_field_types(self, test_file_with_errors):
        """Test that all fields have correct types."""
        result_json = autofix_file(str(test_file_with_errors), profile="llm_strict")
        result = json.loads(result_json)

        # Type contracts
        assert isinstance(result["success"], bool), "success must be bool"
        assert isinstance(result["file_path"], str), "file_path must be str"
        assert isinstance(result["safe_to_import"], bool), "safe_to_import must be bool"
        assert isinstance(result["safe_to_compile"], bool), "safe_to_compile must be bool"
        assert isinstance(result["content_changed"], bool), "content_changed must be bool"
        assert isinstance(result["fixes_applied"], list), "fixes_applied must be list"
        assert isinstance(result["blocking_count"], int), "blocking_count must be int"
        assert isinstance(result["blockers"], list), "blockers must be list"
        assert isinstance(result["invalid_guid_count"], int), "invalid_guid_count must be int"
        assert isinstance(result["contract_violations"], list), "contract_violations must be list"

        # List element types
        for fix_id in result["fixes_applied"]:
            assert isinstance(fix_id, str), f"fixes_applied element must be str, got {type(fix_id)}"

        for blocker in result["blockers"]:
            assert isinstance(blocker, dict), f"blocker must be dict, got {type(blocker)}"

    def test_safe_to_import_semantic(self, tmp_path):
        """Test safe_to_import is False when critical errors exist."""
        # Malformed XML - critical error
        malformed = '<?xml version="1.0"?>\n' "<TcPlcObject>\n" "  <POU>\n"  # Missing closing tags
        malformed_file = tmp_path / "malformed.TcPOU"
        malformed_file.write_text(malformed, encoding="utf-8")

        result = json.loads(autofix_file(str(malformed_file), profile="llm_strict"))

        assert result["safe_to_import"] is False, "safe_to_import must be False for malformed XML"
        assert (
            result["blocking_count"] >= 1
        ), "blocking_count must be >= 1 when safe_to_import is False"

    def test_safe_to_compile_semantic(self, tmp_path):
        """Test safe_to_compile reflects error-free state (warnings OK)."""
        # Valid file (no errors, possibly warnings)
        valid_content = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.0">\n'
            '  <POU Name="FB_Test" Id="{abcd1234-5678-90ab-cdef-1234567890ab}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_Test\n"
            "VAR\n"
            "END_VAR\n"
            "]]></Declaration>\n"
            "    <Implementation>\n"
            "      <ST><![CDATA[]]></ST>\n"
            "    </Implementation>\n"
            '    <LineIds Name="FB_Test">\n'
            '      <LineId Id="1" Count="0" />\n'
            "    </LineIds>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )
        valid_file = tmp_path / "valid.TcPOU"
        valid_file.write_text(valid_content, encoding="utf-8")

        result = json.loads(autofix_file(str(valid_file), profile="llm_strict"))

        # After autofix, should be safe to compile
        assert (
            result["safe_to_compile"] is True
        ), "safe_to_compile must be True for valid files after autofix"

    def test_blocking_count_matches_blockers_length(self, test_file_with_errors):
        """Test that blocking_count equals len(blockers)."""
        result = json.loads(autofix_file(str(test_file_with_errors), profile="llm_strict"))

        assert result["blocking_count"] == len(result["blockers"]), (
            f"blocking_count ({result['blocking_count']}) must equal len(blockers) "
            f"({len(result['blockers'])})"
        )

    def test_blocker_schema(self, tmp_path):
        """Test that each blocker has the minimal llm_strict schema."""
        # Create file with unfixable error
        malformed = '<?xml version="1.0"?>\n<TcPlcObject>\n<POU>\n'
        malformed_file = tmp_path / "malformed.TcPOU"
        malformed_file.write_text(malformed, encoding="utf-8")

        result = json.loads(autofix_file(str(malformed_file), profile="llm_strict"))

        if result["blockers"]:
            blocker = result["blockers"][0]

            # Minimal blocker schema (llm_strict profile)
            required_blocker_keys = {"check", "line", "message", "fixable"}

            actual_keys = set(blocker.keys())

            # May have fix_suggestion for unfixable issues; may have canonical aliases
            # added alongside legacy keys (check_id, severity, category, line_num, auto_fixable)
            allowed_keys = required_blocker_keys | {
                "fix_suggestion",
                "check_id",
                "severity",
                "category",
                "line_num",
                "auto_fixable",
            }

            assert required_blocker_keys.issubset(actual_keys), (
                f"Blocker missing required keys. Expected: {required_blocker_keys}, "
                f"Got: {actual_keys}"
            )

            assert actual_keys.issubset(allowed_keys), (
                f"Blocker has unexpected keys. Allowed: {allowed_keys}, " f"Got: {actual_keys}"
            )

            # Type checks
            assert isinstance(blocker["check"], str)
            assert isinstance(blocker["message"], str)
            assert isinstance(blocker["fixable"], bool)
            assert blocker["fixable"] is False, "Blockers must have fixable=False"

    def test_success_is_always_true_on_no_exception(self, test_file_with_errors):
        """Test that success=True even when file has errors (no exception thrown)."""
        result = json.loads(autofix_file(str(test_file_with_errors), profile="llm_strict"))

        # success should be True (operation completed without exception)
        assert (
            result["success"] is True
        ), "success should be True when tool completes without exception"


class TestValidateFileLLMStrictContract:
    """Contract tests for validate_file(profile="llm_strict")."""

    @pytest.fixture
    def test_file(self, tmp_path):
        """Create a test file."""
        content = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1">\n'
            '  <POU Name="FB_Test" Id="{abcd1234-5678-90ab-cdef-1234567890ab}">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )
        file_path = tmp_path / "test.TcPOU"
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def test_response_has_exact_required_keys(self, test_file):
        """Test that llm_strict response has exactly the required keys."""
        result_json = validate_file(str(test_file), profile="llm_strict")
        result = json.loads(result_json)

        # REQUIRED keys for llm_strict mode
        required_keys = {
            "success",
            "file_path",
            "safe_to_import",
            "safe_to_compile",
            "done",
            "status",
            "blocking_count",
            "blockers",
            "next_action",
            "policy_checked",
            "policy_source",
            "policy_fingerprint",
            "enforcement_mode",
            "response_version",
            "meta",
        }

        actual_keys = set(result.keys())

        assert actual_keys == required_keys, (
            f"Contract violation: validate_file llm_strict response keys changed. "
            f"Expected: {sorted(required_keys)}, "
            f"Got: {sorted(actual_keys)}, "
            f"Missing: {sorted(required_keys - actual_keys)}, "
            f"Extra: {sorted(actual_keys - required_keys)}"
        )

    def test_response_field_types(self, test_file):
        """Test that all fields have correct types."""
        result_json = validate_file(str(test_file), profile="llm_strict")
        result = json.loads(result_json)

        assert isinstance(result["success"], bool), "success must be bool"
        assert isinstance(result["file_path"], str), "file_path must be str"
        assert isinstance(result["safe_to_import"], bool), "safe_to_import must be bool"
        assert isinstance(result["safe_to_compile"], bool), "safe_to_compile must be bool"
        assert isinstance(result["done"], bool), "done must be bool"
        assert result["status"] in {"done", "blocked"}, "status must be done|blocked"
        assert isinstance(result["blocking_count"], int), "blocking_count must be int"
        assert isinstance(result["blockers"], list), "blockers must be list"
        assert isinstance(result["next_action"], str), "next_action must be str"


class TestValidateForImportContract:
    """Contract tests for validate_for_import() response schema."""

    @pytest.fixture
    def test_file(self, tmp_path):
        """Create a test file."""
        content = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1">\n'
            '  <POU Name="FB_Test" Id="{abcd1234-5678-90ab-cdef-1234567890ab}">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )
        file_path = tmp_path / "test.TcPOU"
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def test_response_has_exact_required_keys(self, test_file):
        """Test that validate_for_import has exactly the required keys."""
        result_json = validate_for_import(str(test_file))
        result = json.loads(result_json)

        # REQUIRED keys (this tool already has a minimal response)
        required_keys = {
            "success",
            "file_path",
            "safe_to_import",
            "critical_issues",
            "error_count",
            "validation_time",
            "policy_checked",
            "policy_source",
            "policy_fingerprint",
            "enforcement_mode",
            "response_version",
            "meta",
        }

        actual_keys = set(result.keys())

        assert actual_keys == required_keys, (
            f"Contract violation: validate_for_import response keys changed. "
            f"Expected: {sorted(required_keys)}, "
            f"Got: {sorted(actual_keys)}, "
            f"Missing: {sorted(required_keys - actual_keys)}, "
            f"Extra: {sorted(actual_keys - required_keys)}"
        )

    def test_response_field_types(self, test_file):
        """Test that all fields have correct types."""
        result_json = validate_for_import(str(test_file))
        result = json.loads(result_json)

        assert isinstance(result["success"], bool), "success must be bool"
        assert isinstance(result["file_path"], str), "file_path must be str"
        assert isinstance(result["safe_to_import"], bool), "safe_to_import must be bool"
        assert isinstance(result["critical_issues"], list), "critical_issues must be list"
        assert isinstance(result["error_count"], int), "error_count must be int"
        assert isinstance(result["validation_time"], (int, float)), "validation_time must be number"


class TestFullProfileBackwardCompatibility:
    """Contract tests ensuring full profile remains unchanged."""

    @pytest.fixture
    def test_file(self, tmp_path):
        """Create a test file."""
        content = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1">\n'
            '\t<POU Name="FB_Test" Id="{abcd1234-5678-90ab-cdef-1234567890ab}">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )
        file_path = tmp_path / "test.TcPOU"
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def test_autofix_file_full_profile_has_required_keys(self, test_file):
        """Test that full profile includes all expected verbose keys."""
        result_json = autofix_file(str(test_file), profile="full")
        result = json.loads(result_json)

        # Required keys for full profile (backward compatible)
        required_keys = {
            "success",
            "file_path",
            "backup_created",
            "backup_path",
            "content_changed",
            "fixes_applied",
            "validation_after_fix",
        }

        actual_keys = set(result.keys())

        assert required_keys.issubset(actual_keys), (
            f"Full profile missing required keys. Expected at least: {required_keys}, "
            f"Got: {actual_keys}"
        )

        # Ensure safe flags are NOT in full mode
        assert (
            "safe_to_import" not in actual_keys
        ), "safe_to_import should only be in llm_strict mode"
        assert (
            "safe_to_compile" not in actual_keys
        ), "safe_to_compile should only be in llm_strict mode"

    def test_validate_file_full_profile_has_required_keys(self, test_file):
        """Test that full profile includes all expected verbose keys."""
        result_json = validate_file(str(test_file), profile="full")
        result = json.loads(result_json)

        # Required keys for full profile
        required_keys = {
            "success",
            "file_path",
            "file_type",
            "pou_subtype",
            "validation_status",
            "validation_time",
            "summary",
            "checks",
            "issues",
            "metrics",
        }

        actual_keys = set(result.keys())

        assert required_keys.issubset(actual_keys), (
            f"Full profile missing required keys. Expected at least: {required_keys}, "
            f"Got: {actual_keys}"
        )
