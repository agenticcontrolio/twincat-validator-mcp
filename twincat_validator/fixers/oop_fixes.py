"""OOP-specific auto-fix operations for TwinCAT XML files.

Phase 5A fixes:
- OverrideAttributeFix (fix_id="override_attribute"): Replace METHOD OVERRIDE keyword
  with {attribute 'override'} syntax
- DynamicCreationAttributeFix (fix_id="dynamic_creation_attribute"): Add
  {attribute 'enable_dynamic_creation'} to FBs used with __NEW()
"""

import re

from .base import BaseFix, FixRegistry
from ..file_handler import TwinCATFile


@FixRegistry.register
class OverrideAttributeFix(BaseFix):
    """Replace METHOD OVERRIDE keyword with {attribute 'override'} syntax.

    TwinCAT canonical override marker uses attribute syntax, not keyword.
    Converts:
        METHOD OVERRIDE MethodName : ReturnType
    To:
        {attribute 'override'}
        METHOD MethodName : ReturnType
    """

    fix_id = "override_attribute"

    def apply(self, file: TwinCATFile) -> bool:
        """Replace METHOD OVERRIDE with attribute syntax.

        Args:
            file: TwinCATFile to modify

        Returns:
            True if any replacements were made, False otherwise
        """
        # Pattern to match METHOD OVERRIDE declarations in CDATA blocks
        # Must handle CDATA prefix, multiple spaces, case variations, and optional return type
        # Captures: (everything before METHOD)(METHOD OVERRIDE )(method_name)(optional : return_type)
        pattern = r"(?i)(\s*(?:<!\[CDATA\[)?[ \t]*)(METHOD\s+OVERRIDE\s+)([A-Za-z_][A-Za-z0-9_]*)(\s*:\s*\S+)?"

        def replace_override(match):
            prefix = match.group(1)  # Includes CDATA and indentation
            method_name = match.group(3)
            return_type = match.group(4) or ""  # Empty if no return type
            # Extract just the whitespace part for the new METHOD line
            indent_match = re.search(r"([ \t]*)$", prefix)
            indent = indent_match.group(1) if indent_match else ""
            return f"{prefix}{{attribute 'override'}}\n{indent}METHOD {method_name}{return_type}"

        original_content = file.content
        file.content = re.sub(pattern, replace_override, file.content)

        return file.content != original_content


# DynamicCreationAttributeFix removed - cross-file issue cannot be safely fixed
# The check remains (DynamicCreationAttributeCheck) to report the issue, but
# fixing requires manual intervention because:
# - Issue is reported in allocator file A when target FB in file B lacks attribute
# - Fixer would need to modify file B, not A (cross-file refactoring unsafe)
# - No safe way to auto-apply this fix without risking unrelated FB edits
