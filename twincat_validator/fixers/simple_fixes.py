"""Simple auto-fix operations for TwinCAT XML files.

Contains 5 simple fixes extracted from server.py:
- TabsFix (fix_id="tabs", lines 987-998)
- GuidCaseFix (fix_id="guid_case", lines 1000-1023)
- FileEndingFix (fix_id="file_ending", lines 1025-1052)
- PropertyNewlinesFix (fix_id="property_newlines", lines 1080-1099)
- CdataFormattingFix (fix_id="cdata_formatting", lines 1101-1105)
"""

import re

from .base import BaseFix, FixRegistry
from ..file_handler import TwinCATFile


@FixRegistry.register
class TabsFix(BaseFix):
    """Replace tabs with 2 spaces.

    Extracted from server.py lines 987-998.
    """

    fix_id = "tabs"

    def apply(self, file: TwinCATFile) -> bool:
        """Replace all tab characters with 2 spaces.

        Args:
            file: TwinCATFile to modify

        Returns:
            True if tabs were replaced, False otherwise
        """
        if "\t" not in file.content:
            return False

        file.content = file.content.replace("\t", "  ")
        return True


@FixRegistry.register
class GuidCaseFix(BaseFix):
    """Convert all GUIDs to lowercase hex.

    Extracted from server.py lines 1000-1023.
    """

    fix_id = "guid_case"

    def apply(self, file: TwinCATFile) -> bool:
        """Convert all GUIDs to lowercase hex format.

        Args:
            file: TwinCATFile to modify

        Returns:
            True if any GUIDs were converted, False otherwise
        """
        # Pattern to match GUIDs (any case)
        guid_pattern = r'Id="(\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\})"'

        def lowercase_guid(match):
            return f'Id="{match.group(1).lower()}"'

        # Count GUIDs that will be changed
        uppercase_count = 0
        for match in re.finditer(guid_pattern, file.content):
            guid_value = match.group(1)
            if guid_value != guid_value.lower():
                uppercase_count += 1

        if uppercase_count == 0:
            return False

        file.content = re.sub(guid_pattern, lowercase_guid, file.content)
        return True


@FixRegistry.register
class FileEndingFix(BaseFix):
    """Fix file ending issues.

    Extracted from server.py lines 1025-1052.
    """

    fix_id = "file_ending"

    def apply(self, file: TwinCATFile) -> bool:
        """Fix file ending to ensure proper </TcPlcObject> termination.

        Removes extra ]]> after </TcPlcObject> and ensures single newline.

        Args:
            file: TwinCATFile to modify

        Returns:
            True if file ending was fixed, False otherwise
        """
        # Remove ]]> after </TcPlcObject>
        if file.content.rstrip().endswith("</TcPlcObject>\n]]>") or file.content.rstrip().endswith(
            "</TcPlcObject>]]>"
        ):
            file.content = re.sub(r"</TcPlcObject>\s*\]\]>\s*$", "</TcPlcObject>\n", file.content)
            return True

        # Ensure file ends with exactly </TcPlcObject> and single newline
        if not file.content.rstrip().endswith("</TcPlcObject>"):
            # Find last </TcPlcObject>
            last_close = file.content.rfind("</TcPlcObject>")
            if last_close > 0:
                file.content = file.content[: last_close + len("</TcPlcObject>")] + "\n"
                return True

        return False


@FixRegistry.register
class PropertyNewlinesFix(BaseFix):
    """Fix property declaration newlines.

    Extracted from server.py lines 1080-1099.
    """

    fix_id = "newlines"

    def apply(self, file: TwinCATFile) -> bool:
        """Remove trailing newlines in property declarations.

        Args:
            file: TwinCATFile to modify

        Returns:
            True if property newlines were fixed, False otherwise
        """
        pattern = r"<Declaration><!\[CDATA\[PROPERTY ([^\]]+)\n\]\]></Declaration>"

        def fix_newline(match):
            prop_decl = match.group(1)
            return f"<Declaration><![CDATA[PROPERTY {prop_decl}]]></Declaration>"

        new_content = re.sub(pattern, fix_newline, file.content)

        if new_content == file.content:
            return False

        file.content = new_content
        return True


@FixRegistry.register
class CdataFormattingFix(BaseFix):
    """Fix CDATA section formatting.

    Delegates to PropertyNewlinesFix (extracted from server.py lines 1101-1105).
    This fix exists to keep the "cdata" fix ID valid.
    """

    fix_id = "cdata"

    def apply(self, file: TwinCATFile) -> bool:
        """Fix CDATA formatting by delegating to property newlines fix.

        Args:
            file: TwinCATFile to modify

        Returns:
            True if CDATA formatting was fixed, False otherwise
        """
        # Delegate to property_newlines fix
        property_newlines_fix = PropertyNewlinesFix()
        return property_newlines_fix.apply(file)
