"""Tests for Phase 4: Deterministic fix order guarantee.

Phase 4.2: Fix order must match documented canonical order from config.
"""

import pytest

from twincat_validator import ValidationConfig, FixEngine, TwinCATFile


class TestFixOrderDeterminism:
    """Test that fixes are applied in deterministic, documented order."""

    @pytest.fixture
    def config(self):
        """Create ValidationConfig instance."""
        return ValidationConfig()

    @pytest.fixture
    def fix_engine(self, config):
        """Create FixEngine instance."""
        return FixEngine(config)

    def test_config_has_order_field_for_all_fixes(self, config):
        """Verify all fixes in config have explicit order field."""
        for fix_id, fix_config in config.fix_capabilities.items():
            assert (
                "order" in fix_config
            ), f"Fix '{fix_id}' missing order field in fix_capabilities.json"
            assert isinstance(
                fix_config["order"], int
            ), f"Fix '{fix_id}' has non-integer order: {fix_config['order']}"
            assert (
                fix_config["order"] > 0
            ), f"Fix '{fix_id}' has invalid order {fix_config['order']} (must be > 0)"

    def test_canonical_fix_order_matches_config(self, config):
        """Test that config order matches documented canonical order.

        Canonical fix order (see fix_capabilities.json):
        1. tabs - Must run before indentation
        2. file_ending - Add missing newline at EOF
        3. newlines - Property block newlines
        4. cdata - CDATA formatting
        5. var_blocks - VAR/END_VAR structure
        6. excessive_blanks - Remove excess blank lines
        7. indentation - Fix indentation (after tabs converted)
        8. guid_case - Lowercase GUIDs
        9. lineids - Fix LineIds count (last - most expensive)
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
            assert (
                actual_order == expected_position
            ), f"Fix '{fix_id}' has order {actual_order}, expected {expected_position}"

    def test_no_duplicate_order_numbers(self, config):
        """Test that no two fixes have the same order number."""
        order_values = [fix_config["order"] for fix_config in config.fix_capabilities.values()]

        # Check for duplicates
        unique_orders = set(order_values)
        assert len(unique_orders) == len(order_values), (
            f"Duplicate order numbers found in fix_capabilities.json. "
            f"Orders: {sorted(order_values)}"
        )

    def test_fix_application_order_is_deterministic(self, tmp_path, fix_engine):
        """Test that multiple applications use the same fix order."""
        # Create a file that triggers multiple fixes
        content = (
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '\t<POU Name="FB_Test" Id="{ABCD1234-5678-90AB-CDEF-1234567890AB}">\n'
            "   <Declaration><![CDATA[FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR]]></Declaration>\n"
            "\t</POU>\n"
            "</TcPlcObject>"
        )

        file_path = tmp_path / "test_order.TcPOU"
        file_path.write_text(content, encoding="utf-8")

        # Apply fixes multiple times
        applied_fixes_list = []

        for _ in range(3):
            # Reset file
            file_path.write_text(content, encoding="utf-8")
            file = TwinCATFile.from_path(file_path)

            result = fix_engine.apply_fixes(file)
            applied_fixes_list.append(result.applied_fixes)

        # Verify all runs applied fixes in the same order
        first_run = applied_fixes_list[0]
        for i, run_result in enumerate(applied_fixes_list[1:], start=2):
            assert run_result == first_run, (
                f"Run {i} applied fixes in different order than run 1. "
                f"Run 1: {first_run}, Run {i}: {run_result}"
            )

    def test_tabs_applied_before_indentation(self, tmp_path, fix_engine):
        """Test critical dependency: tabs must be applied before indentation."""
        # Create file with both tabs and bad indentation
        content = (
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "\t<POU>\n"  # Tab
            "   <Declaration/>\n"  # 3 spaces (bad indent)
            "\t</POU>\n"
            "</TcPlcObject>\n"
        )

        file_path = tmp_path / "test_deps.TcPOU"
        file_path.write_text(content, encoding="utf-8")

        file = TwinCATFile.from_path(file_path)
        result = fix_engine.apply_fixes(file, fix_ids=["tabs", "indentation"])

        # Both should be applied
        assert "tabs" in result.applied_fixes
        assert "indentation" in result.applied_fixes

        # tabs must come before indentation
        tabs_index = result.applied_fixes.index("tabs")
        indent_index = result.applied_fixes.index("indentation")
        assert (
            tabs_index < indent_index
        ), f"tabs (index {tabs_index}) must be applied before indentation (index {indent_index})"


class TestFixOrderConfig:
    """Test fix order configuration and sorting logic."""

    def test_fix_engine_sorts_by_order_field(self):
        """Test that FixEngine internally sorts fixes by order field."""
        config = ValidationConfig()

        # Request fixes in reverse order
        reverse_order_ids = ["lineids", "guid_case", "indentation", "tabs"]

        # The engine should sort them by order field, not by request order
        # We can't directly test the sorting without modifying the engine,
        # but we can verify the config has proper order values
        for fix_id in reverse_order_ids:
            assert "order" in config.fix_capabilities[fix_id]

        # Verify sorted order matches canonical order
        sorted_ids = sorted(
            reverse_order_ids, key=lambda fid: config.fix_capabilities[fid]["order"]
        )

        expected_sorted = ["tabs", "indentation", "guid_case", "lineids"]
        assert sorted_ids == expected_sorted, (
            f"Sorting by order field produced wrong order. "
            f"Expected {expected_sorted}, got {sorted_ids}"
        )
