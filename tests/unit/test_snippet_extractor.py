"""Tests for twincat_validator.snippet_extractor module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from twincat_validator.snippet_extractor import (
    extract_line_snippet,
    extract_xml_element_snippet,
    extract_guid_snippet,
    extract_first_occurrence_snippet,
    extract_xml_parse_error_context,
    find_literal_location,
    find_regex_location,
    infer_issue_location,
)


class TestExtractLineSnippet:
    """Tests for extract_line_snippet function."""

    def test_extracts_snippet_with_default_context(self):
        """Test extracting snippet with 2 lines of context (default)."""
        content = "\n".join(
            [
                "line 1",
                "line 2",
                "line 3",
                "line 4",  # Target line
                "line 5",
                "line 6",
                "line 7",
            ]
        )

        snippet = extract_line_snippet(content, line_num=4, context_lines=2)

        assert "line 2" in snippet
        assert "line 3" in snippet
        assert "line 4" in snippet
        assert "line 5" in snippet
        assert "line 6" in snippet

        # Should have arrow marker on line 4
        assert "→  4 |" in snippet or "→   4 |" in snippet

    def test_extracts_snippet_with_custom_context(self):
        """Test extracting snippet with custom context lines."""
        content = "\n".join(["line 1", "line 2", "line 3", "line 4", "line 5"])

        snippet = extract_line_snippet(content, line_num=3, context_lines=1)

        assert "line 2" in snippet
        assert "line 3" in snippet
        assert "line 4" in snippet
        assert "line 1" not in snippet
        assert "line 5" not in snippet

    def test_handles_first_line(self):
        """Test extracting snippet for first line."""
        content = "\n".join(["line 1", "line 2", "line 3"])

        snippet = extract_line_snippet(content, line_num=1, context_lines=2)

        assert "line 1" in snippet
        assert "line 2" in snippet
        assert "line 3" in snippet
        assert "→  1 |" in snippet or "→   1 |" in snippet

    def test_handles_last_line(self):
        """Test extracting snippet for last line."""
        content = "\n".join(["line 1", "line 2", "line 3"])

        snippet = extract_line_snippet(content, line_num=3, context_lines=2)

        assert "line 1" in snippet
        assert "line 2" in snippet
        assert "line 3" in snippet
        assert "→  3 |" in snippet or "→   3 |" in snippet

    def test_handles_line_number_beyond_content(self):
        """Test extracting snippet when line number exceeds content length."""
        content = "\n".join(["line 1", "line 2", "line 3"])

        snippet = extract_line_snippet(content, line_num=10, context_lines=2)

        assert snippet == ""

    def test_handles_empty_content(self):
        """Test extracting snippet from empty content."""
        snippet = extract_line_snippet("", line_num=1, context_lines=2)
        assert snippet == ""

    def test_handles_invalid_line_number(self):
        """Test extracting snippet with invalid line number."""
        content = "\n".join(["line 1", "line 2"])

        snippet = extract_line_snippet(content, line_num=0, context_lines=2)
        assert snippet == ""

        snippet = extract_line_snippet(content, line_num=-1, context_lines=2)
        assert snippet == ""

    def test_preserves_tab_characters(self):
        """Test snippet preserves tab characters in content."""
        content = "\n".join(
            [
                "<POU>",
                "\t<Declaration>",  # Tab character
                "\t\t<VAR>",
                "\t</Declaration>",
            ]
        )

        snippet = extract_line_snippet(content, line_num=2, context_lines=1)

        assert "\t<Declaration>" in snippet

    def test_snippet_includes_line_numbers(self):
        """Test snippet includes formatted line numbers."""
        content = "\n".join(["line 1", "line 2", "line 3"])

        snippet = extract_line_snippet(content, line_num=2, context_lines=1)

        # Should have line numbers like "  1 |", "→  2 |", "  3 |"
        assert "1 |" in snippet
        assert "2 |" in snippet
        assert "3 |" in snippet


class TestExtractXmlElementSnippet:
    """Tests for extract_xml_element_snippet function."""

    def test_extracts_xml_element(self):
        """Test extracting complete XML element."""
        content = """
<?xml version="1.0"?>
<TcPlcObject>
  <POU Name="FB_Test" Id="{guid}">
    <Declaration>VAR END_VAR</Declaration>
  </POU>
</TcPlcObject>
        """

        snippet = extract_xml_element_snippet(content, "POU", max_chars=300)

        assert "<POU" in snippet
        assert "</POU>" in snippet
        assert "FB_Test" in snippet

    def test_truncates_long_elements(self):
        """Test truncation of long XML elements."""
        # Create a very long element
        long_content = "<POU>" + "x" * 500 + "</POU>"

        snippet = extract_xml_element_snippet(long_content, "POU", max_chars=100)

        assert len(snippet) <= 103  # 100 + "..."
        assert snippet.endswith("...")

    def test_handles_element_with_attributes(self):
        """Test extracting element with attributes."""
        content = '<Method Name="Execute" Id="{guid}">body</Method>'

        snippet = extract_xml_element_snippet(content, "Method", max_chars=300)

        assert "<Method" in snippet
        assert "Execute" in snippet
        assert "</Method>" in snippet

    def test_handles_missing_element(self):
        """Test extracting non-existent element."""
        content = "<POU>content</POU>"

        snippet = extract_xml_element_snippet(content, "Method", max_chars=300)

        assert snippet == ""

    def test_handles_empty_content(self):
        """Test extracting from empty content."""
        snippet = extract_xml_element_snippet("", "POU", max_chars=300)
        assert snippet == ""

    def test_handles_empty_element_tag(self):
        """Test with empty element tag."""
        content = "<POU>content</POU>"
        snippet = extract_xml_element_snippet(content, "", max_chars=300)
        assert snippet == ""

    def test_extracts_first_occurrence_of_multiple_elements(self):
        """Test extracts first occurrence when multiple elements exist."""
        content = """
<Method Name="First">body1</Method>
<Method Name="Second">body2</Method>
        """

        snippet = extract_xml_element_snippet(content, "Method", max_chars=300)

        assert "First" in snippet
        # Should only extract first occurrence
        assert "Second" not in snippet


class TestExtractGuidSnippet:
    """Tests for extract_guid_snippet function."""

    def test_extracts_line_containing_guid(self):
        """Test extracting line with GUID."""
        content = """
line 1
<POU Name="FB_Test" Id="{a1b2c3d4-e5f6-7890-abcd-ef1234567890}">
line 3
        """

        guid = "{a1b2c3d4-e5f6-7890-abcd-ef1234567890}"
        snippet = extract_guid_snippet(content, guid)

        assert guid in snippet
        assert "FB_Test" in snippet

    def test_strips_whitespace(self):
        """Test snippet has leading/trailing whitespace stripped."""
        content = '   <POU Id="{guid}">   \n'

        snippet = extract_guid_snippet(content, "{guid}")

        assert snippet == '<POU Id="{guid}">'

    def test_handles_missing_guid(self):
        """Test extracting non-existent GUID."""
        content = '<POU Id="{other-guid}"></POU>'

        snippet = extract_guid_snippet(content, "{target-guid}")

        assert snippet == ""

    def test_handles_empty_content(self):
        """Test extracting from empty content."""
        snippet = extract_guid_snippet("", "{guid}")
        assert snippet == ""

    def test_handles_empty_guid(self):
        """Test with empty GUID."""
        content = '<POU Id="{guid}"></POU>'
        snippet = extract_guid_snippet(content, "")
        assert snippet == ""

    def test_returns_first_occurrence(self):
        """Test returns first line when GUID appears multiple times."""
        content = """
<POU Id="{guid}">
  <Method Id="{guid}">
        """

        snippet = extract_guid_snippet(content, "{guid}")

        # Should return first line
        assert "POU" in snippet
        assert "Method" not in snippet


class TestExtractFirstOccurrenceSnippet:
    """Tests for extract_first_occurrence_snippet function."""

    def test_extracts_first_occurrence_with_context(self):
        """Test extracting first occurrence of text with context."""
        content = "\n".join(
            [
                "line 1",
                "line 2",
                "line with \ttab",  # First occurrence
                "line 4",
                "line with \ttab again",  # Second occurrence
            ]
        )

        snippet = extract_first_occurrence_snippet(content, "\t", context_lines=1)

        assert "line 2" in snippet
        assert "line with \ttab" in snippet
        assert "line 4" in snippet
        # Should NOT include second occurrence
        assert "again" not in snippet

    def test_handles_missing_text(self):
        """Test when search text not found."""
        content = "\n".join(["line 1", "line 2", "line 3"])

        snippet = extract_first_occurrence_snippet(content, "\t", context_lines=2)

        assert snippet == ""

    def test_handles_empty_content(self):
        """Test with empty content."""
        snippet = extract_first_occurrence_snippet("", "text", context_lines=2)
        assert snippet == ""

    def test_handles_empty_search_text(self):
        """Test with empty search text."""
        content = "\n".join(["line 1", "line 2"])
        snippet = extract_first_occurrence_snippet(content, "", context_lines=2)
        assert snippet == ""


class TestExtractXmlParseErrorContext:
    """Tests for extract_xml_parse_error_context function."""

    def test_extracts_context_from_error_with_line_number(self):
        """Test extracting context when error message includes line number."""
        content = "\n".join(
            [
                "line 1",
                "line 2",
                "line 3 with error",
                "line 4",
                "line 5",
            ]
        )

        error_msg = "syntax error: line 3, column 5"
        snippet = extract_xml_parse_error_context(content, error_msg)

        assert "line 1" in snippet
        assert "line 2" in snippet
        assert "line 3 with error" in snippet
        assert "line 4" in snippet
        assert "line 5" in snippet

    def test_handles_different_error_message_formats(self):
        """Test parsing different error message formats."""
        content = "\n".join(["line 1", "line 2", "line 3"])

        # Format: "line: 2"
        snippet = extract_xml_parse_error_context(content, "error at line: 2")
        assert "line 2" in snippet

        # Format: "line=2"
        snippet = extract_xml_parse_error_context(content, "error at line=2")
        assert "line 2" in snippet

        # Format: "row 2"
        snippet = extract_xml_parse_error_context(content, "error at row 2")
        assert "line 2" in snippet

    def test_fallback_when_no_line_number_in_error(self):
        """Test fallback to first 5 lines when no line number found."""
        content = "\n".join([f"line {i}" for i in range(1, 11)])

        error_msg = "generic XML parse error"
        snippet = extract_xml_parse_error_context(content, error_msg)

        # Should show first 5 lines
        assert "line 1" in snippet
        assert "line 2" in snippet
        assert "line 3" in snippet
        assert "line 4" in snippet
        assert "line 5" in snippet
        assert "line 6" not in snippet

    def test_handles_empty_content(self):
        """Test with empty content."""
        snippet = extract_xml_parse_error_context("", "line 1 error")
        assert snippet == ""

    def test_handles_short_content(self):
        """Test with content shorter than 5 lines."""
        content = "\n".join(["line 1", "line 2"])

        error_msg = "generic error"
        snippet = extract_xml_parse_error_context(content, error_msg)

        assert "line 1" in snippet
        assert "line 2" in snippet


class TestIssueLocationInference:
    """Tests for generic issue location inference helpers."""

    def test_find_literal_location(self):
        content = "a\nbbb\ncccc"
        line, col = find_literal_location(content, "bbb")
        assert line == 2
        assert col == 1

    def test_find_regex_location(self):
        content = "x\n  FOR i := 0 TO nCount - 1 DO\nz"
        line, col = find_regex_location(content, r"FOR\s+i\s*:=", flags=0)
        assert line == 2
        assert col == 3

    def test_infer_issue_location_from_line_in_message(self):
        content = "line1\nline2\nline3"
        line, col = infer_issue_location(content, "xml_structure", "syntax error: line 2, column 5")
        assert line == 2
        assert col == 5

    def test_infer_issue_location_for_tabs(self):
        content = "a\n\tb"
        line, col = infer_issue_location(content, "tabs", "tab found")
        assert line == 2
        assert col == 1
