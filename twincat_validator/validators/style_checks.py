"""Style and formatting validation checks."""

import re

from .base import BaseCheck, CheckRegistry
from ..models import ValidationIssue
from ..file_handler import TwinCATFile
from ..config_loader import get_shared_config
from ..snippet_extractor import extract_line_snippet, extract_first_occurrence_snippet


def _get_config():
    """Get shared config instance."""
    return get_shared_config()


@CheckRegistry.register
class IndentationCheck(BaseCheck):
    """Validates consistent 2-space indentation.

    Extracted from server.py lines 489-504 (check_indentation method).
    """

    check_id = "indentation"

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        """Check for consistent 2-space indentation.

        Args:
            file: TwinCATFile to validate

        Returns:
            List of ValidationIssue objects for indentation problems
        """
        issues = []

        # Get knowledge base entry (Phase 3)
        kb = _get_config().get_check_knowledge("indentation")

        for i, line in enumerate(file.lines, 1):
            if not line or not line[0].isspace():
                continue

            spaces = len(line) - len(line.lstrip(" "))
            if spaces % 2 != 0:
                # Extract correct example (Phase 3)
                correct_example = None
                if kb.get("correct_examples"):
                    correct_example = kb["correct_examples"][0].get("code")

                issues.append(
                    ValidationIssue(
                        severity="warning",
                        category="Indent",
                        message=f"Line {i}: Indentation not multiple of 2 ({spaces} spaces)",
                        line_num=i,
                        fix_available=True,
                        fix_suggestion="Adjust indentation to nearest multiple of 2 spaces",
                        code_snippet=extract_line_snippet(file.content, i, context_lines=2),
                        explanation=kb.get("explanation"),
                        correct_example=correct_example,
                    )
                )

        return issues


@CheckRegistry.register
class TabsCheck(BaseCheck):
    """Validates that spaces are used instead of tabs.

    Extracted from server.py lines 506-518 (check_tabs method).
    """

    check_id = "tabs"

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        """Check for tabs (should use spaces).

        Args:
            file: TwinCATFile to validate

        Returns:
            List with single ValidationIssue if tabs found, empty list otherwise
        """
        issues = []

        tab_lines = [(i + 1, line) for i, line in enumerate(file.lines) if "\t" in line]

        if tab_lines:
            # Get knowledge base entry (Phase 3)
            kb = _get_config().get_check_knowledge("tabs")

            # Extract correct example (Phase 3)
            correct_example = None
            if kb.get("correct_examples"):
                correct_example = kb["correct_examples"][0].get("code")

            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="Tabs",
                    message=f"Found {len(tab_lines)} line(s) with tabs. Should use 2 spaces.",
                    fix_available=True,
                    fix_suggestion="Replace all tabs with 2 spaces",
                    code_snippet=extract_first_occurrence_snippet(
                        file.content, "\t", context_lines=2
                    ),
                    explanation=kb.get("explanation"),
                    correct_example=correct_example,
                )
            )

        return issues


@CheckRegistry.register
class CdataFormattingCheck(BaseCheck):
    """Validates CDATA section formatting.

    Extracted from server.py lines 731-742 (check_cdata_formatting method).
    """

    check_id = "cdata_formatting"

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        """Check CDATA section formatting.

        Args:
            file: TwinCATFile to validate

        Returns:
            List with single ValidationIssue if bad CDATA formatting found
        """
        issues = []

        bad_pattern = r"<Declaration><!\[CDATA\[PROPERTY [^\]]+\n\]\]></Declaration>"
        if re.search(bad_pattern, file.content):
            issues.append(
                ValidationIssue(
                    severity="info",
                    category="Format",
                    message="Property declarations should not have trailing newline in CDATA",
                    fix_available=True,
                    fix_suggestion="Remove trailing newline before ]]>",
                )
            )

        return issues


@CheckRegistry.register
class ExcessiveBlankLinesCheck(BaseCheck):
    """Validates that there are not excessive consecutive blank lines.

    Extracted from server.py lines 744-786 (check_excessive_blank_lines method).
    """

    check_id = "excessive_blank_lines"

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        """Check for excessive consecutive blank lines.

        Args:
            file: TwinCATFile to validate

        Returns:
            List with single ValidationIssue if excessive blank lines found
        """
        issues = []
        lines = file.lines
        consecutive_blanks = 0
        blank_sequences = []
        current_start = 0

        for i, line in enumerate(lines, 1):
            if line.strip() == "":
                if consecutive_blanks == 0:
                    current_start = i
                consecutive_blanks += 1
            else:
                if consecutive_blanks > 3:  # Threshold: >3 blank lines
                    blank_sequences.append((current_start, i - 1, consecutive_blanks))
                consecutive_blanks = 0

        # Check if last sequence extends to end of file
        if consecutive_blanks > 3:
            blank_sequences.append((current_start, len(lines), consecutive_blanks))

        if blank_sequences:
            total_excessive = sum(
                count - 2 for _, _, count in blank_sequences
            )  # Keep max 2 blank lines

            # Build detailed message
            if len(blank_sequences) == 1:
                start, end, count = blank_sequences[0]
                message = f"Found {count} consecutive blank lines (lines {start}-{end}). {total_excessive} lines could be removed."
            else:
                message = f"Found {len(blank_sequences)} sequence(s) with excessive blank lines. {total_excessive} lines could be removed."

            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="Format",
                    message=message,
                    fix_available=True,
                    fix_suggestion="Reduce to maximum 2 consecutive blank lines",
                )
            )

        return issues
