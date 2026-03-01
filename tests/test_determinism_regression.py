"""Phase 5A.2: Determinism regression gate tests.

These tests enforce deterministic behavior contracts and will FAIL if:
- Fix order changes unexpectedly
- Blocker logic changes (severity filtering, auto_fixable logic)
- Safe flag derivation changes (safe_to_import, safe_to_compile)

IMPORTANT: If these tests fail, it indicates a BREAKING CHANGE to deterministic behavior.
"""

import json

import pytest

from server import autofix_file, validate_file
from twincat_validator import ValidationConfig, FixEngine, TwinCATFile


class TestFixOrderDeterminism:
    """Regression tests for fix order stability."""

    @pytest.fixture
    def config(self):
        """Get validation config."""
        return ValidationConfig()

    def test_canonical_fix_order_unchanged(self, config):
        """Test that canonical fix order matches documented contract.

        CANONICAL ORDER (see fix_capabilities.json):
        1. tabs - Must run before indentation
        2. file_ending - Add missing newline at EOF
        3. newlines - Property block newlines
        4. cdata - CDATA formatting
        5. var_blocks - VAR/END_VAR structure
        6. excessive_blanks - Remove excess blank lines
        7. indentation - Fix indentation (after tabs converted)
        8. guid_case - Lowercase GUIDs
        9. lineids - Fix LineIds count (last - most expensive)

        This order is a CONTRACT and must not change without explicit approval.
        """
        expected_order = [
            ("tabs", 1),
            ("file_ending", 2),
            ("newlines", 3),
            ("cdata", 4),
            ("var_blocks", 5),
            ("excessive_blanks", 6),
            ("indentation", 7),
            ("guid_case", 8),
            ("lineids", 9),
        ]

        for fix_id, expected_position in expected_order:
            actual_order = config.fix_capabilities[fix_id]["order"]
            assert actual_order == expected_position, (
                f"REGRESSION: Fix order changed for '{fix_id}'! "
                f"Expected position {expected_position}, got {actual_order}. "
                f"Fix order is a contract and must not change without approval."
            )

    def test_fix_order_no_duplicates(self, config):
        """Test that no two fixes have the same order number."""
        order_values = [fix_config["order"] for fix_config in config.fix_capabilities.values()]

        unique_orders = set(order_values)
        assert len(unique_orders) == len(order_values), (
            f"REGRESSION: Duplicate order numbers found! "
            f"Orders: {sorted(order_values)}. "
            f"Each fix must have a unique order number."
        )

    def test_fix_order_covers_all_fixes(self, config):
        """Test that all 10 fixes have order numbers."""
        expected_fixes = {
            "tabs",
            "file_ending",
            "newlines",
            "cdata",
            "var_blocks",
            "excessive_blanks",
            "indentation",
            "guid_case",
            "lineids",
            "override_attribute",  # Phase 5A OOP fix
        }

        actual_fixes = set(config.fix_capabilities.keys())

        assert actual_fixes == expected_fixes, (
            f"REGRESSION: Fix set changed! "
            f"Expected: {sorted(expected_fixes)}, "
            f"Got: {sorted(actual_fixes)}. "
            f"Missing: {sorted(expected_fixes - actual_fixes)}, "
            f"Extra: {sorted(actual_fixes - expected_fixes)}"
        )

    def test_fix_order_is_applied(self, tmp_path):
        """Test that FixEngine actually applies fixes in order."""
        config = ValidationConfig()
        engine = FixEngine(config)

        # Create file that triggers multiple fixes
        content = (
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '\t<POU Name="FB_Test" Id="{ABCD1234-5678-90AB-CDEF-1234567890AB}">\n'
            "   <Declaration/>\n"  # Bad indentation
            "\t</POU>\n"
            "</TcPlcObject>"  # Missing final newline
        )

        file_path = tmp_path / "test.TcPOU"
        file_path.write_text(content, encoding="utf-8")

        file = TwinCATFile.from_path(file_path)
        result = engine.apply_fixes(file)

        # Verify fixes were applied in order
        applied = result.applied_fixes

        if len(applied) >= 2:
            # Get order numbers for applied fixes
            orders = [config.fix_capabilities[fix_id]["order"] for fix_id in applied]

            # Verify they're in ascending order
            assert orders == sorted(orders), (
                f"REGRESSION: Fixes not applied in order! " f"Applied: {applied}, Orders: {orders}"
            )


class TestBlockerLogicStability:
    """Regression tests for blocker identification logic."""

    def test_blocker_severity_contract(self, tmp_path):
        """Test that blockers include error and critical severities only.

        CONTRACT: Blockers are issues where:
        - severity in ("error", "critical") AND
        - auto_fixable = False

        This contract must not change.
        """
        # Create file with unfixable error
        malformed = '<?xml version="1.0"?>\n<TcPlcObject>\n<POU>\n'  # Missing closing tags
        malformed_file = tmp_path / "malformed.TcPOU"
        malformed_file.write_text(malformed, encoding="utf-8")

        result = json.loads(autofix_file(str(malformed_file), profile="llm_strict"))

        # Verify blockers exist
        assert result["blocking_count"] >= 1, "REGRESSION: Malformed XML should produce blockers"

        # Verify each blocker is unfixable
        for blocker in result["blockers"]:
            assert (
                blocker["fixable"] is False
            ), f"REGRESSION: Blocker must have fixable=False, got {blocker}"

    def test_blocker_count_matches_length(self, tmp_path):
        """Test that blocking_count always equals len(blockers)."""
        # Test with various files
        test_cases = [
            ('<?xml version="1.0"?>\n<TcPlcObject>\n<POU>\n', "malformed.TcPOU"),
            (
                '<?xml version="1.0"?>\n<TcPlcObject>\n  <POU Name="FB_Test" Id="{abcd1234-5678-90ab-cdef-1234567890ab}">\n    <Declaration/>\n  </POU>\n</TcPlcObject>\n',
                "valid.TcPOU",
            ),
        ]

        for content, filename in test_cases:
            file_path = tmp_path / filename
            file_path.write_text(content, encoding="utf-8")

            result = json.loads(autofix_file(str(file_path), profile="llm_strict"))

            assert result["blocking_count"] == len(result["blockers"]), (
                f"REGRESSION: blocking_count mismatch for {filename}. "
                f"Count: {result['blocking_count']}, Blockers: {len(result['blockers'])}"
            )


class TestSafeFlagDeterminism:
    """Regression tests for safe_to_import and safe_to_compile flag logic."""

    def test_safe_to_import_contract(self, tmp_path):
        """Test safe_to_import derivation contract.

        CONTRACT: safe_to_import = (critical_error_count == 0)

        Where critical_error_count = count of issues with severity in ("error", "critical").
        """
        # Test case 1: Malformed XML (critical error) -> safe_to_import = False
        malformed = '<?xml version="1.0"?>\n<TcPlcObject>\n<POU>\n'
        malformed_file = tmp_path / "malformed.TcPOU"
        malformed_file.write_text(malformed, encoding="utf-8")

        result = json.loads(autofix_file(str(malformed_file), profile="llm_strict"))

        assert (
            result["safe_to_import"] is False
        ), "REGRESSION: Malformed XML must have safe_to_import=False"

        # Test case 2: Valid file (no errors) -> safe_to_import = True
        valid = (
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
        valid_file.write_text(valid, encoding="utf-8")

        result = json.loads(autofix_file(str(valid_file), profile="llm_strict"))

        assert (
            result["safe_to_import"] is True
        ), "REGRESSION: Valid file after autofix must have safe_to_import=True"

    def test_safe_to_compile_contract(self, tmp_path):
        """Test safe_to_compile derivation contract.

        CONTRACT: safe_to_compile = (error_count == 0)

        Where error_count = count of issues with severity in ("error", "critical").
        Warnings do NOT prevent compilation.
        """
        # Test case 1: File with only warnings -> safe_to_compile = True
        warning_only = (
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
        warning_file = tmp_path / "warning.TcPOU"
        warning_file.write_text(warning_only, encoding="utf-8")

        result = json.loads(autofix_file(str(warning_file), profile="llm_strict"))

        assert (
            result["safe_to_compile"] is True
        ), "REGRESSION: File with only warnings must have safe_to_compile=True"

        # Test case 2: Malformed XML (error) -> safe_to_compile = False
        malformed = '<?xml version="1.0"?>\n<TcPlcObject>\n<POU>\n'
        malformed_file = tmp_path / "malformed.TcPOU"
        malformed_file.write_text(malformed, encoding="utf-8")

        result = json.loads(autofix_file(str(malformed_file), profile="llm_strict"))

        assert (
            result["safe_to_compile"] is False
        ), "REGRESSION: Malformed XML must have safe_to_compile=False"

    def test_safe_flags_consistency(self, tmp_path):
        """Test that safe flags are consistent across validate_file and autofix_file."""
        valid = (
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
        valid_file.write_text(valid, encoding="utf-8")

        # Autofix first
        autofix_result = json.loads(autofix_file(str(valid_file), profile="llm_strict"))

        # Then validate
        validate_result = json.loads(validate_file(str(valid_file), profile="llm_strict"))

        # Flags should match
        assert (
            autofix_result["safe_to_import"] == validate_result["safe_to_import"]
        ), "REGRESSION: safe_to_import differs between autofix_file and validate_file"

        assert (
            autofix_result["safe_to_compile"] == validate_result["safe_to_compile"]
        ), "REGRESSION: safe_to_compile differs between autofix_file and validate_file"


class TestIdempotencyRegression:
    """Regression tests for idempotency guarantee."""

    @pytest.fixture
    def fix_engine(self):
        """Create FixEngine instance."""
        config = ValidationConfig()
        return FixEngine(config)

    def test_double_autofix_produces_no_changes(self, tmp_path, fix_engine):
        """Test that running autofix twice produces no changes on second pass.

        CONTRACT: Idempotency guarantee - running autofix twice on the same input
        produces identical output.
        """
        # Create file with fixable issues
        content = (
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '\t<POU Name="FB_Test" Id="{ABCD1234-5678-90AB-CDEF-1234567890AB}">\n'
            "   <Declaration/>\n"
            "\t</POU>\n"
            "</TcPlcObject>"
        )

        file_path = tmp_path / "test.TcPOU"
        file_path.write_text(content, encoding="utf-8")

        # First pass
        file1 = TwinCATFile.from_path(file_path)
        fix_engine.apply_fixes(file1)
        file1.save()
        content_after_first = file1.content

        # Second pass
        file2 = TwinCATFile.from_path(file_path)
        result2 = fix_engine.apply_fixes(file2)
        content_after_second = file2.content

        # REGRESSION CHECK: Second pass must produce no changes
        assert content_after_first == content_after_second, (
            f"REGRESSION: Idempotency violated! Second pass changed content. "
            f"Applied fixes in second pass: {result2.applied_fixes}"
        )

        assert len(result2.applied_fixes) == 0, (
            f"REGRESSION: Second pass applied fixes: {result2.applied_fixes}. "
            f"This violates idempotency guarantee."
        )
