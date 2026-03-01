"""Tests for twincat_validator.fixers.structural_fixes module."""

import sys
from pathlib import Path
import importlib

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from twincat_validator.fixers.base import FixRegistry
from twincat_validator.fixers import structural_fixes
from twincat_validator.file_handler import TwinCATFile


def _ensure_structural_fixes_registered() -> None:
    """Ensure structural_fixes module is registered (clear + reload pattern)."""
    FixRegistry.clear()
    importlib.reload(structural_fixes)


class TestPropertyVarBlocksFix:
    """Tests for PropertyVarBlocksFix fixer."""

    @classmethod
    def setup_class(cls):
        """Ensure fixes are registered without mutating global registry state."""
        _ensure_structural_fixes_registered()

    def test_fix_id_matches_config(self):
        """Test that fix_id matches config/fix_capabilities.json."""
        fix_class = FixRegistry.get_fix("var_blocks")
        assert fix_class.fix_id == "var_blocks"

    def test_adds_var_blocks_to_empty_property_getter(self, tmp_path):
        """Test that VAR/END_VAR blocks are added to empty property getters."""
        test_file = tmp_path / "empty_getter.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "  <POU>\n"
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test]]></Declaration>\n"
            "    <Property>\n"
            '      <Get Name="Get" Id="{12345678-1234-1234-1234-123456789012}">\n'
            "        <Declaration><![CDATA[]]></Declaration>\n"
            "      </Get>\n"
            "    </Property>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("var_blocks")()

        result = fix.apply(file)

        assert result is True
        assert "<Declaration><![CDATA[VAR\nEND_VAR\n]]></Declaration>" in file.content

    def test_skips_non_tcpou_files(self, tmp_path):
        """Test that fix is skipped for non-.TcPOU/.TcIO files."""
        test_file = tmp_path / "data_type.TcDUT"
        test_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "  <DUT>\n"
            "    <Declaration><![CDATA[TYPE MyType : STRUCT]]></Declaration>\n"
            "  </DUT>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("var_blocks")()

        # should_skip should return True
        assert fix.should_skip(file) is True

    def test_skips_function_pou(self, tmp_path):
        """Test that fix is skipped for FUNCTION POUs (cannot have properties)."""
        test_file = tmp_path / "function.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "  <POU>\n"
            "    <Declaration><![CDATA[FUNCTION F_Test : INT]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("var_blocks")()

        # should_skip should return True for functions
        assert fix.should_skip(file) is True

    def test_no_empty_getters_returns_false(self, tmp_path):
        """Test that file without empty getters returns False."""
        test_file = tmp_path / "no_empty_getters.TcPOU"
        original_content = (
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "  <POU>\n"
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test]]></Declaration>\n"
            "    <Property>\n"
            '      <Get Name="Get" Id="{12345678-1234-1234-1234-123456789012}">\n'
            "        <Declaration><![CDATA[VAR\nEND_VAR\n]]></Declaration>\n"
            "      </Get>\n"
            "    </Property>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )
        test_file.write_text(original_content)

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("var_blocks")()

        result = fix.apply(file)

        assert result is False
        assert file.content == original_content


class TestExcessiveBlankLinesFix:
    """Tests for ExcessiveBlankLinesFix fixer."""

    @classmethod
    def setup_class(cls):
        """Ensure fixes are registered without mutating global registry state."""
        _ensure_structural_fixes_registered()

    def test_fix_id_matches_config(self):
        """Test that fix_id matches config/fix_capabilities.json."""
        fix_class = FixRegistry.get_fix("excessive_blanks")
        assert fix_class.fix_id == "excessive_blanks"

    def test_reduces_excessive_blank_lines(self, tmp_path):
        """Test that excessive blank lines are reduced to max 2."""
        test_file = tmp_path / "excessive_blanks.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "\n\n\n\n\n"  # 5 blank lines
            "  <POU></POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("excessive_blanks")()

        result = fix.apply(file)

        assert result is True
        # Should have at most 2 consecutive blank lines
        assert "\n\n\n\n" not in file.content  # No 4 consecutive newlines
        assert "\n\n\n" in file.content  # Max 2 blank lines = 3 newlines

    def test_preserves_max_two_blank_lines(self, tmp_path):
        """Test that 2 blank lines are preserved."""
        test_file = tmp_path / "two_blanks.TcPOU"
        original_content = (
            '<?xml version="1.0"?>\n<TcPlcObject>\n\n\n  <POU></POU>\n</TcPlcObject>\n'
        )
        test_file.write_text(original_content)

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("excessive_blanks")()

        result = fix.apply(file)

        # 2 blank lines should be preserved
        assert result is False
        assert file.content == original_content

    def test_no_excessive_blanks_returns_false(self, tmp_path):
        """Test that file without excessive blanks returns False."""
        test_file = tmp_path / "no_excessive_blanks.TcPOU"
        original_content = (
            '<?xml version="1.0"?>\n' "<TcPlcObject>\n" "  <POU></POU>\n" "</TcPlcObject>\n"
        )
        test_file.write_text(original_content)

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("excessive_blanks")()

        result = fix.apply(file)

        assert result is False
        assert file.content == original_content


class TestIndentationFix:
    """Tests for IndentationFix fixer."""

    @classmethod
    def setup_class(cls):
        """Ensure fixes are registered without mutating global registry state."""
        _ensure_structural_fixes_registered()

    def test_fix_id_matches_config(self):
        """Test that fix_id matches config/fix_capabilities.json."""
        fix_class = FixRegistry.get_fix("indentation")
        assert fix_class.fix_id == "indentation"

    def test_fixes_odd_indentation(self, tmp_path):
        """Test that odd indentation is fixed to multiples of 2."""
        test_file = tmp_path / "odd_indent.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            " <POU>\n"  # 1 space
            "   <Declaration>Test</Declaration>\n"  # 3 spaces
            "     <Implementation>Code</Implementation>\n"  # 5 spaces
            " </POU>\n"  # 1 space
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("indentation")()

        result = fix.apply(file)

        assert result is True
        lines = file.content.split("\n")
        # Check that odd indents are fixed
        assert lines[2] == "  <POU>"  # 1 -> 2 spaces
        assert lines[3] == "    <Declaration>Test</Declaration>"  # 3 -> 4 spaces
        assert lines[4] == "      <Implementation>Code</Implementation>"  # 5 -> 6 spaces
        assert lines[5] == "  </POU>"  # 1 -> 2 spaces

    def test_preserves_even_indentation(self, tmp_path):
        """Test that even indentation is preserved."""
        test_file = tmp_path / "even_indent.TcPOU"
        original_content = (
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "  <POU>\n"  # 2 spaces
            "    <Declaration>Test</Declaration>\n"  # 4 spaces
            "  </POU>\n"  # 2 spaces
            "</TcPlcObject>\n"
        )
        test_file.write_text(original_content)

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("indentation")()

        result = fix.apply(file)

        assert result is False
        assert file.content == original_content

    def test_preserves_empty_lines(self, tmp_path):
        """Test that empty lines are preserved as-is."""
        test_file = tmp_path / "with_empty_lines.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "\n"  # Empty line
            "  <POU>\n"
            "\n"  # Empty line
            "  </POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("indentation")()

        result = fix.apply(file)

        # Empty lines should be preserved
        assert result is False
        lines = file.content.split("\n")
        assert lines[2] == ""  # Empty line preserved
        assert lines[4] == ""  # Empty line preserved

    def test_no_indentation_issues_returns_false(self, tmp_path):
        """Test that file without indentation issues returns False."""
        test_file = tmp_path / "no_indent_issues.TcPOU"
        original_content = (
            '<?xml version="1.0"?>\n' "<TcPlcObject>\n" "  <POU></POU>\n" "</TcPlcObject>\n"
        )
        test_file.write_text(original_content)

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("indentation")()

        result = fix.apply(file)

        assert result is False
        assert file.content == original_content
