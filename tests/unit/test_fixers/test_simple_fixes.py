"""Tests for twincat_validator.fixers.simple_fixes module."""

import sys
from pathlib import Path
import importlib

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from twincat_validator.fixers.base import FixRegistry
from twincat_validator.fixers import simple_fixes
from twincat_validator.file_handler import TwinCATFile


def _ensure_simple_fixes_registered() -> None:
    """Ensure simple_fixes module is registered (clear + reload pattern)."""
    FixRegistry.clear()
    importlib.reload(simple_fixes)


class TestTabsFix:
    """Tests for TabsFix fixer."""

    @classmethod
    def setup_class(cls):
        """Ensure fixes are registered without mutating global registry state."""
        _ensure_simple_fixes_registered()

    def test_fix_id_matches_config(self):
        """Test that fix_id matches config/fix_capabilities.json."""
        fix_class = FixRegistry.get_fix("tabs")
        assert fix_class.fix_id == "tabs"

    def test_replaces_tabs_with_spaces(self, tmp_path):
        """Test that tabs are replaced with 2 spaces."""
        test_file = tmp_path / "tabs.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "\t<POU>\n"
            "\t\t<Declaration>Test</Declaration>\n"
            "\t</POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("tabs")()

        result = fix.apply(file)

        assert result is True
        assert "\t" not in file.content
        assert "  <POU>" in file.content
        assert "    <Declaration>Test</Declaration>" in file.content

    def test_no_tabs_returns_false(self, tmp_path):
        """Test that file without tabs returns False and content unchanged."""
        test_file = tmp_path / "no_tabs.TcPOU"
        original_content = (
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "  <POU>\n"
            "    <Declaration>Test</Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )
        test_file.write_text(original_content)

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("tabs")()

        result = fix.apply(file)

        assert result is False
        assert file.content == original_content


class TestGuidCaseFix:
    """Tests for GuidCaseFix fixer."""

    @classmethod
    def setup_class(cls):
        """Ensure fixes are registered without mutating global registry state."""
        _ensure_simple_fixes_registered()

    def test_fix_id_matches_config(self):
        """Test that fix_id matches config/fix_capabilities.json."""
        fix_class = FixRegistry.get_fix("guid_case")
        assert fix_class.fix_id == "guid_case"

    def test_converts_uppercase_guids_to_lowercase(self, tmp_path):
        """Test that uppercase GUIDs are converted to lowercase."""
        test_file = tmp_path / "uppercase_guid.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Id="{AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE}">\n'
            "  </POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("guid_case")()

        result = fix.apply(file)

        assert result is True
        assert "{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}" in file.content
        assert "{AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE}" not in file.content

    def test_mixed_case_guids_converted(self, tmp_path):
        """Test that mixed case GUIDs are converted."""
        test_file = tmp_path / "mixed_guid.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Id="{AaBbCcDd-EeFf-1122-3344-556677889900}">\n'
            "  </POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("guid_case")()

        result = fix.apply(file)

        assert result is True
        assert "{aabbccdd-eeff-1122-3344-556677889900}" in file.content

    def test_already_lowercase_returns_false(self, tmp_path):
        """Test that already lowercase GUIDs return False."""
        test_file = tmp_path / "lowercase_guid.TcPOU"
        original_content = (
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Id="{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}">\n'
            "  </POU>\n"
            "</TcPlcObject>\n"
        )
        test_file.write_text(original_content)

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("guid_case")()

        result = fix.apply(file)

        assert result is False
        assert file.content == original_content


class TestFileEndingFix:
    """Tests for FileEndingFix fixer."""

    @classmethod
    def setup_class(cls):
        """Ensure fixes are registered without mutating global registry state."""
        _ensure_simple_fixes_registered()

    def test_fix_id_matches_config(self):
        """Test that fix_id matches config/fix_capabilities.json."""
        fix_class = FixRegistry.get_fix("file_ending")
        assert fix_class.fix_id == "file_ending"

    def test_removes_extra_cdata_marker(self, tmp_path):
        """Test that extra ]]> after </TcPlcObject> is removed."""
        test_file = tmp_path / "extra_marker.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n' "<TcPlcObject>\n" "  <POU></POU>\n" "</TcPlcObject>\n]]>\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("file_ending")()

        result = fix.apply(file)

        assert result is True
        assert file.content.rstrip().endswith("</TcPlcObject>")
        assert "]]>" not in file.content

    def test_removes_cdata_marker_without_newline(self, tmp_path):
        """Test that ]]> directly after </TcPlcObject> is removed."""
        test_file = tmp_path / "marker_no_newline.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n' "<TcPlcObject>\n" "  <POU></POU>\n" "</TcPlcObject>]]>"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("file_ending")()

        result = fix.apply(file)

        assert result is True
        assert file.content.rstrip().endswith("</TcPlcObject>")
        assert "]]>" not in file.content

    def test_fixes_missing_final_tag(self, tmp_path):
        """Test that content after </TcPlcObject> is removed."""
        test_file = tmp_path / "extra_content.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "  <POU></POU>\n"
            "</TcPlcObject>\nextra content here\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("file_ending")()

        result = fix.apply(file)

        assert result is True
        assert file.content.rstrip() == (
            '<?xml version="1.0"?>\n<TcPlcObject>\n  <POU></POU>\n</TcPlcObject>'
        )

    def test_proper_ending_returns_false(self, tmp_path):
        """Test that proper file ending returns False."""
        test_file = tmp_path / "proper_ending.TcPOU"
        original_content = (
            '<?xml version="1.0"?>\n' "<TcPlcObject>\n" "  <POU></POU>\n" "</TcPlcObject>\n"
        )
        test_file.write_text(original_content)

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("file_ending")()

        result = fix.apply(file)

        assert result is False
        assert file.content == original_content


class TestPropertyNewlinesFix:
    """Tests for PropertyNewlinesFix fixer."""

    @classmethod
    def setup_class(cls):
        """Ensure fixes are registered without mutating global registry state."""
        _ensure_simple_fixes_registered()

    def test_fix_id_matches_config(self):
        """Test that fix_id matches config/fix_capabilities.json."""
        fix_class = FixRegistry.get_fix("newlines")
        assert fix_class.fix_id == "newlines"

    def test_removes_trailing_newline_in_property_declaration(self, tmp_path):
        """Test that trailing newlines in property declarations are removed."""
        test_file = tmp_path / "property_newline.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "  <Property>\n"
            "    <Declaration><![CDATA[PROPERTY MyProp : INT\n]]></Declaration>\n"
            "  </Property>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("newlines")()

        result = fix.apply(file)

        assert result is True
        assert "<Declaration><![CDATA[PROPERTY MyProp : INT]]></Declaration>" in file.content

    def test_no_trailing_newline_returns_false(self, tmp_path):
        """Test that property without trailing newline returns False."""
        test_file = tmp_path / "no_newline.TcPOU"
        original_content = (
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "  <Property>\n"
            "    <Declaration><![CDATA[PROPERTY MyProp : INT]]></Declaration>\n"
            "  </Property>\n"
            "</TcPlcObject>\n"
        )
        test_file.write_text(original_content)

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("newlines")()

        result = fix.apply(file)

        assert result is False
        assert file.content == original_content


class TestCdataFormattingFix:
    """Tests for CdataFormattingFix fixer."""

    @classmethod
    def setup_class(cls):
        """Ensure fixes are registered without mutating global registry state."""
        _ensure_simple_fixes_registered()

    def test_fix_id_matches_config(self):
        """Test that fix_id matches config/fix_capabilities.json."""
        fix_class = FixRegistry.get_fix("cdata")
        assert fix_class.fix_id == "cdata"

    def test_delegates_to_property_newlines_fix(self, tmp_path):
        """Test that CDATA fix delegates to property newlines fix."""
        test_file = tmp_path / "cdata_issue.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "  <Property>\n"
            "    <Declaration><![CDATA[PROPERTY MyProp : INT\n]]></Declaration>\n"
            "  </Property>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("cdata")()

        result = fix.apply(file)

        assert result is True
        assert "<Declaration><![CDATA[PROPERTY MyProp : INT]]></Declaration>" in file.content

    def test_no_cdata_issues_returns_false(self, tmp_path):
        """Test that file without CDATA issues returns False."""
        test_file = tmp_path / "no_issues.TcPOU"
        original_content = (
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "  <Property>\n"
            "    <Declaration><![CDATA[PROPERTY MyProp : INT]]></Declaration>\n"
            "  </Property>\n"
            "</TcPlcObject>\n"
        )
        test_file.write_text(original_content)

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("cdata")()

        result = fix.apply(file)

        assert result is False
        assert file.content == original_content
