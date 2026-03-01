"""Naming convention validation checks for TwinCAT files.

Extracted from server.py lines 649-729.
"""

import re

from .base import BaseCheck, CheckRegistry
from ..models import ValidationIssue
from ..file_handler import TwinCATFile


def _extract_top_level_name(content: str, suffix: str) -> str | None:
    """Extract the primary top-level object name for the given TwinCAT file type."""
    patterns = {
        ".TcPOU": r'<POU\b[^>]*\bName="([^"]+)"',
        ".TcIO": r'<Itf\b[^>]*\b(?:Name|Itf)="([^"]+)"',
        ".TcDUT": r'<DUT\b[^>]*\bName="([^"]+)"',
        ".TcGVL": r'<GVL\b[^>]*\bName="([^"]+)"',
    }
    pattern = patterns.get(suffix)
    if not pattern:
        return None
    match = re.search(pattern, content)
    return match.group(1) if match else None


@CheckRegistry.register
class NamingConventionsCheck(BaseCheck):
    """Validates naming conventions for TwinCAT files.

    Extracted from server.py lines 649-729 (check_naming_conventions method).

    Naming conventions:
    - .TcPOU: FB_ (function_block), PRG_ (program), FUNC_ (function)
    - .TcIO: I_ (interface)
    - .TcDUT: ST_ (struct), E_ (enum), T_ (type alias)
    - .TcGVL: GVL_ (global variable list)
    """

    check_id = "naming_conventions"

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        """Check naming conventions.

        Args:
            file: TwinCATFile to validate

        Returns:
            List of ValidationIssue objects for naming convention violations
        """
        issues = []

        name = _extract_top_level_name(file.content, file.suffix)
        if not name:
            return issues

        suffix = file.suffix

        if suffix == ".TcPOU":
            if file.pou_subtype == "function_block":
                if not name.startswith("FB_"):
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            category="Naming",
                            message=f"Function block '{name}' should start with 'FB_'",
                            fix_available=False,
                            fix_suggestion="Rename to follow FB_ naming convention",
                        )
                    )
            elif file.pou_subtype == "program":
                if not name.startswith("PRG_"):
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            category="Naming",
                            message=f"Program '{name}' should start with 'PRG_'",
                            fix_available=False,
                            fix_suggestion="Rename to follow PRG_ naming convention",
                        )
                    )
            elif file.pou_subtype == "function":
                if not name.startswith("FUNC_"):
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            category="Naming",
                            message=f"Function '{name}' should start with 'FUNC_'",
                            fix_available=False,
                            fix_suggestion="Rename to follow FUNC_ naming convention",
                        )
                    )
            else:
                # Fallback: subtype detection failed, use loose check
                if (
                    not name.startswith("FB_")
                    and not name.startswith("PRG_")
                    and not name.startswith("FUNC_")
                ):
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            category="Naming",
                            message=f"POU '{name}' should start with 'FB_', 'PRG_', or 'FUNC_'",
                            fix_available=False,
                            fix_suggestion="Rename to follow TwinCAT naming conventions",
                        )
                    )

        elif suffix == ".TcIO":
            if not name.startswith("I_"):
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        category="Naming",
                        message=f"Interface '{name}' should start with 'I_'",
                        fix_available=False,
                        fix_suggestion="Rename interface to start with 'I_'",
                    )
                )

        elif suffix == ".TcDUT":
            if not (name.startswith("ST_") or name.startswith("E_") or name.startswith("T_")):
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        category="Naming",
                        message=f"Data type '{name}' should start with 'ST_', 'E_', or 'T_'",
                        fix_available=False,
                        fix_suggestion="Rename data type to follow conventions",
                    )
                )

        elif suffix == ".TcGVL":
            if not name.startswith("GVL_"):
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        category="Naming",
                        message=f"Global variable list '{name}' should start with 'GVL_'",
                        fix_available=False,
                        fix_suggestion="Rename global variable list to start with 'GVL_'",
                    )
                )

        return issues
