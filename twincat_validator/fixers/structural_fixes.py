"""Structural auto-fix operations for TwinCAT XML files.

Contains 3 structural fixes extracted from server.py:
- PropertyVarBlocksFix (fix_id="var_blocks", lines 1054-1078)
- ExcessiveBlankLinesFix (fix_id="excessive_blanks", lines 1107-1134)
- IndentationFix (fix_id="indentation", lines 1136-1169)
"""

import re

from .base import BaseFix, FixRegistry
from ..file_handler import TwinCATFile


@FixRegistry.register
class PropertyVarBlocksFix(BaseFix):
    """Add missing VAR blocks to property getters.

    Extracted from server.py lines 1054-1078.
    """

    fix_id = "var_blocks"

    def should_skip(self, file: TwinCATFile) -> bool:
        """Skip for non-.TcPOU/.TcIO files AND function POUs.

        Args:
            file: TwinCATFile to check

        Returns:
            True if fix should be skipped, False otherwise
        """
        # Only apply to .TcPOU and .TcIO files
        if file.suffix not in [".TcPOU", ".TcIO"]:
            return True

        # FUNCTIONs cannot have properties
        if file.pou_subtype == "function":
            return True

        return False

    def apply(self, file: TwinCATFile) -> bool:
        """Add VAR/END_VAR blocks to empty property getters.

        Args:
            file: TwinCATFile to modify

        Returns:
            True if VAR blocks were added, False otherwise
        """
        pattern = (
            r'(<Get Name="Get" Id="\{[^}]+\}">)\s*(<Declaration><!\[CDATA\[\]\]></Declaration>)'
        )

        def add_var_block(match):
            get_tag = match.group(1)
            return f"{get_tag}\n      <Declaration><![CDATA[VAR\nEND_VAR\n]]></Declaration>"

        new_content = re.sub(pattern, add_var_block, file.content)

        if new_content == file.content:
            return False

        file.content = new_content
        return True


@FixRegistry.register
class ExcessiveBlankLinesFix(BaseFix):
    """Reduce excessive consecutive blank lines to maximum of 2.

    Extracted from server.py lines 1107-1134.
    """

    fix_id = "excessive_blanks"

    def apply(self, file: TwinCATFile) -> bool:
        """Reduce consecutive blank lines to max 2.

        Args:
            file: TwinCATFile to modify

        Returns:
            True if excessive blank lines were removed, False otherwise
        """
        lines = file.content.split("\n")
        fixed_lines = []
        consecutive_blanks = 0
        max_allowed_blanks = 2

        for line in lines:
            if line.strip() == "":
                consecutive_blanks += 1
                if consecutive_blanks <= max_allowed_blanks:
                    fixed_lines.append(line)
            else:
                consecutive_blanks = 0
                fixed_lines.append(line)

        new_content = "\n".join(fixed_lines)

        if new_content == file.content:
            return False

        file.content = new_content
        return True


@FixRegistry.register
class IndentationFix(BaseFix):
    """Fix indentation to multiples of 2 spaces.

    Extracted from server.py lines 1136-1169.
    """

    fix_id = "indentation"

    def apply(self, file: TwinCATFile) -> bool:
        """Fix indentation to ensure all lines use multiples of 2 spaces.

        Args:
            file: TwinCATFile to modify

        Returns:
            True if indentation was fixed, False otherwise
        """
        lines = file.content.split("\n")
        fixed_lines = []
        fixes_count = 0

        for line in lines:
            if not line or line.strip() == "":
                # Keep empty lines as-is
                fixed_lines.append(line)
                continue

            # Count leading spaces
            leading_spaces = len(line) - len(line.lstrip(" "))

            # Check if it's not a multiple of 2
            if leading_spaces > 0 and leading_spaces % 2 != 0:
                # Round to nearest multiple of 2
                corrected_spaces = (leading_spaces + 1) // 2 * 2
                fixed_line = " " * corrected_spaces + line.lstrip(" ")
                fixed_lines.append(fixed_line)
                fixes_count += 1
            else:
                fixed_lines.append(line)

        if fixes_count == 0:
            return False

        file.content = "\n".join(fixed_lines)
        return True
