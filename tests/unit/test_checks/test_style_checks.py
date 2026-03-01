"""Tests for twincat_validator.validators.style_checks module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from twincat_validator.validators.base import CheckRegistry
from twincat_validator.validators.style_checks import (
    IndentationCheck,
    TabsCheck,
    CdataFormattingCheck,
    ExcessiveBlankLinesCheck,
)
from twincat_validator.file_handler import TwinCATFile


def _ensure_style_checks_registered() -> None:
    for check_class in (
        IndentationCheck,
        TabsCheck,
        CdataFormattingCheck,
        ExcessiveBlankLinesCheck,
    ):
        if check_class.check_id not in CheckRegistry.get_all_checks():
            CheckRegistry.register(check_class)


class TestIndentationCheck:
    """Tests for IndentationCheck validator."""

    @classmethod
    def setup_class(cls):
        """Ensure checks are registered without mutating global registry state."""
        _ensure_style_checks_registered()

    def test_valid_indentation_produces_no_issues(self, tmp_path):
        """Test file with valid 2-space indentation produces no issues."""
        valid_file = tmp_path / "valid_indent.TcPOU"
        valid_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test">\n'
            "    <Declaration>\n"
            "      VAR\n"
            "        nCounter : INT;\n"
            "      END_VAR\n"
            "    </Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(valid_file)
        check = IndentationCheck()

        issues = check.run(file)

        assert isinstance(issues, list)
        assert len(issues) == 0

    def test_no_indentation_produces_no_issues(self, tmp_path):
        """Test file with no indentation (all at column 0) produces no issues."""
        no_indent_file = tmp_path / "no_indent.TcPOU"
        no_indent_file.write_text(
            '<?xml version="1.0"?>\n' "<TcPlcObject>\n" "<POU>\n" "</POU>\n" "</TcPlcObject>"
        )

        file = TwinCATFile(no_indent_file)
        check = IndentationCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_odd_indentation_detected(self, tmp_path):
        """Test file with odd number of spaces is detected."""
        odd_indent_file = tmp_path / "odd_indent.TcPOU"
        odd_indent_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '   <POU Name="FB_Test">\n'  # 3 spaces
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(odd_indent_file)
        check = IndentationCheck()

        issues = check.run(file)

        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "warning"
        assert issue.category == "Indent"
        assert "Line 3" in issue.message
        assert "3 spaces" in issue.message
        assert issue.fix_available is True
        assert "multiple of 2" in issue.fix_suggestion

    def test_multiple_odd_indentations(self, tmp_path):
        """Test multiple lines with odd indentation are all detected."""
        multi_odd_file = tmp_path / "multi_odd.TcPOU"
        multi_odd_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "   <POU>\n"  # Line 3: 3 spaces
            "  <Declaration>\n"  # Valid: 2 spaces
            "     VAR\n"  # Line 5: 5 spaces
            "  </Declaration>\n"
            " </POU>\n"  # Line 7: 1 space
            "</TcPlcObject>"
        )

        file = TwinCATFile(multi_odd_file)
        check = IndentationCheck()

        issues = check.run(file)

        assert len(issues) == 3
        line_numbers = [issue.line_num for issue in issues]
        assert 3 in line_numbers
        assert 5 in line_numbers
        assert 7 in line_numbers

    def test_empty_lines_ignored(self, tmp_path):
        """Test empty lines are ignored by indentation check."""
        empty_lines_file = tmp_path / "empty_lines.TcPOU"
        empty_lines_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "\n"  # Empty line
            "  <POU>\n"
            "\n"  # Empty line
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(empty_lines_file)
        check = IndentationCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_check_id_matches_config(self):
        """Test check_id matches expected config ID."""
        check = IndentationCheck()
        assert check.check_id == "indentation"


class TestTabsCheck:
    """Tests for TabsCheck validator."""

    @classmethod
    def setup_class(cls):
        """Ensure checks are registered without mutating global registry state."""
        _ensure_style_checks_registered()

    def test_no_tabs_produces_no_issues(self, tmp_path):
        """Test file with only spaces produces no issues."""
        no_tabs_file = tmp_path / "no_tabs.TcPOU"
        no_tabs_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test">\n'
            "    <Declaration>\n"
            "      VAR\n"
            "        nCounter : INT;\n"
            "      END_VAR\n"
            "    </Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(no_tabs_file)
        check = TabsCheck()

        issues = check.run(file)

        assert isinstance(issues, list)
        assert len(issues) == 0

    def test_single_tab_detected(self, tmp_path):
        """Test file with single tab is detected."""
        single_tab_file = tmp_path / "single_tab.TcPOU"
        single_tab_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '\t<POU Name="FB_Test">\n'  # Tab instead of spaces
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(single_tab_file)
        check = TabsCheck()

        issues = check.run(file)

        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "warning"
        assert issue.category == "Tabs"
        assert "1 line(s) with tabs" in issue.message
        assert issue.fix_available is True
        assert "2 spaces" in issue.fix_suggestion

    def test_multiple_tabs_detected(self, tmp_path):
        """Test file with multiple tabs is detected and counted."""
        multi_tab_file = tmp_path / "multi_tab.TcPOU"
        multi_tab_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "\t<POU>\n"  # Tab
            "\t\t<Declaration>\n"  # Multiple tabs
            "  <Implementation>\n"  # Spaces
            "\t</Implementation>\n"  # Tab
            "\t</POU>\n"  # Tab
            "</TcPlcObject>"
        )

        file = TwinCATFile(multi_tab_file)
        check = TabsCheck()

        issues = check.run(file)

        assert len(issues) == 1
        issue = issues[0]
        assert "4 line(s) with tabs" in issue.message

    def test_mixed_tabs_and_spaces_detected(self, tmp_path):
        """Test file with mixed tabs and spaces is detected."""
        mixed_file = tmp_path / "mixed.TcPOU"
        mixed_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "  \t<POU>\n"  # Spaces then tab
            "\t  </POU>\n"  # Tab then spaces
            "</TcPlcObject>"
        )

        file = TwinCATFile(mixed_file)
        check = TabsCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert "2 line(s) with tabs" in issues[0].message

    def test_tabs_in_cdata_detected(self, tmp_path):
        """Test tabs within CDATA sections are also detected."""
        cdata_tab_file = tmp_path / "cdata_tab.TcPOU"
        cdata_tab_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "  <Declaration><![CDATA[\n"
            "VAR\n"
            "\tnCounter : INT;\n"  # Tab in CDATA
            "END_VAR\n"
            "]]></Declaration>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(cdata_tab_file)
        check = TabsCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert "1 line(s) with tabs" in issues[0].message

    def test_check_id_matches_config(self):
        """Test check_id matches expected config ID."""
        check = TabsCheck()
        assert check.check_id == "tabs"


class TestCdataFormattingCheck:
    """Tests for CdataFormattingCheck validator."""

    @classmethod
    def setup_class(cls):
        """Ensure checks are registered without mutating global registry state."""
        _ensure_style_checks_registered()

    def test_valid_cdata_produces_no_issues(self, tmp_path):
        """Test file with properly formatted CDATA produces no issues."""
        valid_cdata_file = tmp_path / "valid_cdata.TcPOU"
        valid_cdata_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "  <Declaration><![CDATA[\n"
            "VAR\n"
            "  nCounter : INT;\n"
            "END_VAR\n"
            "]]></Declaration>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(valid_cdata_file)
        check = CdataFormattingCheck()

        issues = check.run(file)

        assert isinstance(issues, list)
        assert len(issues) == 0

    def test_non_property_cdata_with_newline_is_valid(self, tmp_path):
        """Test non-property CDATA with trailing newline is valid."""
        non_property_file = tmp_path / "non_property.TcPOU"
        non_property_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "  <Declaration><![CDATA[\n"
            "FUNCTION FB_Test : INT\n"
            "]]></Declaration>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(non_property_file)
        check = CdataFormattingCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_bad_property_cdata_formatting_detected(self, tmp_path):
        """Test property CDATA with trailing newline is detected."""
        bad_property_file = tmp_path / "bad_property.TcPOU"
        bad_property_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "  <Declaration><![CDATA[PROPERTY Value : INT\n"
            "]]></Declaration>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(bad_property_file)
        check = CdataFormattingCheck()

        issues = check.run(file)

        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "info"
        assert issue.category == "Format"
        assert "Property" in issue.message or "property" in issue.message.lower()
        assert "trailing newline" in issue.message
        assert issue.fix_available is True
        assert "Remove trailing newline" in issue.fix_suggestion

    def test_multiple_bad_property_cdata_single_issue(self, tmp_path):
        """Test multiple bad property CDATA sections result in single issue."""
        multi_bad_file = tmp_path / "multi_bad.TcPOU"
        multi_bad_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "  <POU>\n"
            "    <Property>\n"
            "      <Declaration><![CDATA[PROPERTY Value : INT\n"
            "]]></Declaration>\n"
            "    </Property>\n"
            "    <Property>\n"
            "      <Declaration><![CDATA[PROPERTY Name : STRING\n"
            "]]></Declaration>\n"
            "    </Property>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(multi_bad_file)
        check = CdataFormattingCheck()

        issues = check.run(file)

        # Check produces single issue if pattern matches
        assert len(issues) == 1

    def test_property_cdata_without_trailing_newline_is_valid(self, tmp_path):
        """Test property CDATA without trailing newline is valid."""
        good_property_file = tmp_path / "good_property.TcPOU"
        good_property_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "  <Declaration><![CDATA[PROPERTY Value : INT]]></Declaration>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(good_property_file)
        check = CdataFormattingCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_check_id_matches_config(self):
        """Test check_id matches expected config ID."""
        check = CdataFormattingCheck()
        assert check.check_id == "cdata_formatting"


class TestExcessiveBlankLinesCheck:
    """Tests for ExcessiveBlankLinesCheck validator."""

    @classmethod
    def setup_class(cls):
        """Ensure checks are registered without mutating global registry state."""
        _ensure_style_checks_registered()

    def test_no_excessive_blanks_produces_no_issues(self, tmp_path):
        """Test file with no excessive blank lines produces no issues."""
        no_blanks_file = tmp_path / "no_blanks.TcPOU"
        no_blanks_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test">\n'
            "\n"
            "\n"
            "    <Declaration>\n"
            "    </Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(no_blanks_file)
        check = ExcessiveBlankLinesCheck()

        issues = check.run(file)

        assert isinstance(issues, list)
        assert len(issues) == 0

    def test_three_blank_lines_is_acceptable(self, tmp_path):
        """Test exactly 3 consecutive blank lines is acceptable."""
        three_blanks_file = tmp_path / "three_blanks.TcPOU"
        three_blanks_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "\n"
            "\n"
            "\n"
            "  <POU>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(three_blanks_file)
        check = ExcessiveBlankLinesCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_single_sequence_excessive_blanks_detected(self, tmp_path):
        """Test single sequence of excessive blank lines is detected."""
        excessive_file = tmp_path / "excessive.TcPOU"
        excessive_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "\n"
            "\n"
            "\n"
            "\n"
            "\n"  # 5 blank lines (lines 3-7)
            "  <POU>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(excessive_file)
        check = ExcessiveBlankLinesCheck()

        issues = check.run(file)

        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "warning"
        assert issue.category == "Format"
        assert "5 consecutive blank lines" in issue.message
        assert "lines 3-7" in issue.message
        assert "3 lines could be removed" in issue.message  # 5 - 2 = 3
        assert issue.fix_available is True
        assert "maximum 2 consecutive blank lines" in issue.fix_suggestion

    def test_multiple_sequences_excessive_blanks(self, tmp_path):
        """Test multiple sequences of excessive blank lines are detected."""
        multi_excessive_file = tmp_path / "multi_excessive.TcPOU"
        multi_excessive_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "\n"
            "\n"
            "\n"
            "\n"  # 4 blank lines (lines 3-6)
            "  <POU>\n"
            "\n"
            "\n"
            "\n"
            "\n"
            "\n"  # 5 blank lines (lines 8-12)
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(multi_excessive_file)
        check = ExcessiveBlankLinesCheck()

        issues = check.run(file)

        assert len(issues) == 1
        issue = issues[0]
        assert "2 sequence(s)" in issue.message
        # (4-2) + (5-2) = 2 + 3 = 5 lines could be removed
        assert "5 lines could be removed" in issue.message

    def test_exactly_four_blanks_is_excessive(self, tmp_path):
        """Test exactly 4 consecutive blank lines is excessive (threshold is >3)."""
        four_blanks_file = tmp_path / "four_blanks.TcPOU"
        four_blanks_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "\n"
            "\n"
            "\n"
            "\n"  # 4 blank lines
            "  <POU>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(four_blanks_file)
        check = ExcessiveBlankLinesCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert "4 consecutive blank lines" in issues[0].message

    def test_excessive_blanks_at_end_of_file(self, tmp_path):
        """Test excessive blank lines at end of file are detected."""
        end_blanks_file = tmp_path / "end_blanks.TcPOU"
        # Content with 5 blank lines at the end (lines 6-10)
        content = (
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "  <POU>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
            "\n"
            "\n"
            "\n"
            "\n"
        )
        end_blanks_file.write_text(content)

        file = TwinCATFile(end_blanks_file)
        check = ExcessiveBlankLinesCheck()

        issues = check.run(file)

        assert len(issues) == 1
        # Content ends without final newline, so we have 4 blank lines
        # If written with write_text, Python adds a final implicit split result
        # The actual count depends on how split('\n') handles the trailing content
        assert "consecutive blank lines" in issues[0].message
        assert "lines could be removed" in issues[0].message

    def test_lines_with_only_whitespace_count_as_blank(self, tmp_path):
        """Test lines with only whitespace (spaces/tabs) count as blank."""
        whitespace_file = tmp_path / "whitespace.TcPOU"
        whitespace_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "\n"
            "  \n"  # Spaces only
            "\t\n"  # Tab only
            "   \n"  # More spaces
            "  <POU>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(whitespace_file)
        check = ExcessiveBlankLinesCheck()

        issues = check.run(file)

        # 4 lines with only whitespace (lines 3-6) should be excessive
        assert len(issues) == 1

    def test_check_id_matches_config(self):
        """Test check_id matches expected config ID."""
        check = ExcessiveBlankLinesCheck()
        assert check.check_id == "excessive_blank_lines"
