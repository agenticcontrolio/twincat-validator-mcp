"""Utility functions for TwinCAT Validator.

Extracted from server.py (lines 142-195).
"""

import re
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .file_handler import TwinCATFile

_VALID_INTENT_PROFILES: tuple[str, ...] = ("auto", "procedural", "oop")


def detect_pou_subtype(file: "TwinCATFile") -> Optional[str]:
    """Detect POU subtype from the main Declaration CDATA block.

    Args:
        file: TwinCATFile to analyze

    Returns:
        'function_block', 'function', 'program', or None if not a POU
        or detection fails.
    """
    if file.suffix != ".TcPOU":
        return None

    declaration = _extract_pou_declaration_cdata(file.content)
    if declaration is None:
        return None

    significant_lines = _extract_declaration_significant_lines(declaration)
    if not significant_lines:
        return None
    first_line = significant_lines[0].upper()

    # Check FUNCTION_BLOCK before FUNCTION to avoid false match
    if first_line.startswith("FUNCTION_BLOCK"):
        return "function_block"
    elif first_line.startswith("PROGRAM"):
        return "program"
    elif first_line.startswith("FUNCTION"):
        return "function"
    return None


def _extract_pou_declaration_cdata(content: str) -> Optional[str]:
    """Extract the main POU Declaration CDATA contents, if present.

    Args:
        content: XML file content

    Returns:
        Declaration CDATA content or None
    """
    match = re.search(
        r"<POU\b[^>]*>.*?<Declaration>\s*<!\[CDATA\[(.*?)\]\]>\s*</Declaration>",
        content,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1)


def _extract_declaration_significant_lines(declaration: str) -> list[str]:
    """Return declaration lines excluding blank lines and common TwinCAT pragmas/comments.

    Args:
        declaration: Declaration CDATA content

    Returns:
        List of significant (non-comment, non-pragma) lines
    """
    significant_lines = []
    for raw_line in declaration.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Skip TwinCAT pragmas/attributes and common comment line starts.
        if line.startswith("{") or line.startswith("//") or line.startswith("(*"):
            continue
        significant_lines.append(line)
    return significant_lines


def _resolve_intent_profile(file_content: Optional[str], intent_profile: str) -> str:
    """Resolve the effective intent profile from the declared profile and optional file content.

    Args:
        file_content: Raw XML content of the TwinCAT file being processed.  May be
            ``None`` when no file content is available (e.g. batch context or pre-generation).
            Only consulted when ``intent_profile="auto"``.
        intent_profile: Caller-supplied profile: ``"auto"``, ``"procedural"``, or ``"oop"``.

    Returns:
        ``"oop"`` or ``"procedural"``.  ``"auto"`` is never returned; it always resolves
        to one of the two concrete profiles.

    Resolution rules for ``"auto"``:
    - If the POU-level Declaration CDATA contains ``EXTENDS`` or ``IMPLEMENTS``  → ``"oop"``
    - Otherwise → ``"procedural"`` (conservative default)
    - If ``file_content`` is ``None`` → ``"procedural"`` (no evidence, safe default)
    """
    if intent_profile == "oop":
        return "oop"
    if intent_profile == "procedural":
        return "procedural"

    # "auto": inspect file content for OOP keywords in the POU-level declaration.
    if file_content is None:
        return "procedural"

    decl = _extract_pou_declaration_cdata(file_content)
    if decl and re.search(r"\b(?:EXTENDS|IMPLEMENTS)\b", decl, re.IGNORECASE):
        return "oop"
    return "procedural"


def _batch_auto_resolve_intent(tc_files: list[Path], intent_profile: str) -> str:
    """Resolve intent profile for a batch of files.

    When ``intent_profile`` is ``"auto"``, scans the POU-level declarations of all
    ``.TcPOU`` files in ``tc_files``.  If **any** file declares ``EXTENDS`` or
    ``IMPLEMENTS``, resolves to ``"oop"``; otherwise resolves to ``"procedural"``.

    For explicit ``"oop"`` or ``"procedural"`` values the scan is skipped entirely.

    Args:
        tc_files: List of TwinCAT file paths already matched by the batch tool.
        intent_profile: Caller-supplied profile: ``"auto"``, ``"procedural"``, or ``"oop"``.

    Returns:
        ``"oop"`` or ``"procedural"`` — never ``"auto"``.
    """
    if intent_profile == "oop":
        return "oop"
    if intent_profile == "procedural":
        return "procedural"

    # "auto": scan .TcPOU files for OOP keyword evidence.
    for path in tc_files:
        if path.suffix != ".TcPOU":
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _resolve_intent_profile(content, "auto") == "oop":
            return "oop"
    return "procedural"
