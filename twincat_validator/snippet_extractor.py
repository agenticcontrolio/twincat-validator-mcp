"""Code snippet extraction utilities for ValidationIssue enrichment (Phase 3).

Provides functions to extract code snippets from TwinCAT XML files to populate
the code_snippet field in ValidationIssue objects.
"""

import re


def _line_col_from_offset(content: str, offset: int) -> tuple[int, int]:
    """Convert 0-based string offset to 1-based (line, column)."""
    if offset < 0:
        return (1, 1)
    prefix = content[:offset]
    line_num = prefix.count("\n") + 1
    last_newline = prefix.rfind("\n")
    if last_newline == -1:
        column = offset + 1
    else:
        column = offset - last_newline
    return (line_num, column)


def find_literal_location(
    content: str,
    literal: str,
    *,
    case_sensitive: bool = True,
) -> tuple[int | None, int | None]:
    """Find first location of a literal in content as (line, column)."""
    if not content or not literal:
        return (None, None)
    if case_sensitive:
        idx = content.find(literal)
        if idx == -1:
            return (None, None)
        return _line_col_from_offset(content, idx)

    lower_content = content.lower()
    lower_lit = literal.lower()
    idx = lower_content.find(lower_lit)
    if idx == -1:
        return (None, None)
    return _line_col_from_offset(content, idx)


def find_regex_location(
    content: str,
    pattern: str,
    *,
    flags: int = 0,
) -> tuple[int | None, int | None]:
    """Find first regex match location in content as (line, column)."""
    if not content or not pattern:
        return (None, None)
    match = re.search(pattern, content, flags)
    if not match:
        return (None, None)
    return _line_col_from_offset(content, match.start())


def infer_issue_location(
    content: str,
    check_id: str,
    message: str,
) -> tuple[int | None, int | None]:
    """Best-effort deterministic location inference for issues without line info."""
    # Parse explicit line/column from parser-style messages first.
    line_col = re.search(r"line[:\s=]+(\d+)(?:[,:\s]+column[:\s=]+(\d+))?", message, re.I)
    if line_col:
        line_num = int(line_col.group(1))
        column = int(line_col.group(2)) if line_col.group(2) else None
        return (line_num, column)

    if check_id == "tabs":
        line, col = find_literal_location(content, "\t")
        if line is not None:
            return (line, col)
    if check_id == "file_ending":
        # Prefer trailing garbage marker if present.
        line, col = find_literal_location(content, "]]>")
        if line is not None:
            return (line, col)
        non_empty = [i for i, ln in enumerate(content.split("\n"), start=1) if ln.strip()]
        return (non_empty[-1], 1) if non_empty else (1, 1)
    if check_id == "lineids_count":
        line, col = find_literal_location(content, "<LineIds")
        if line is not None:
            return (line, col)
    if check_id == "property_var_blocks":
        line, col = find_literal_location(content, '<Get Name="Get"')
        if line is not None:
            return (line, col)
    if check_id == "excessive_blank_lines":
        line, col = find_regex_location(content, r"\n[ \t]*\n[ \t]*\n[ \t]*\n", flags=re.M)
        if line is not None:
            return (line, col)

    # Method-focused OOP and structure checks: anchor to first mentioned method when possible.
    method_name_match = re.search(r"\b(FB_init|FB_exit|M_[A-Za-z0-9_]+)\b", message)
    if method_name_match:
        method_name = method_name_match.group(1)
        line, col = find_regex_location(
            content,
            rf'<Method\s+[^>]*Name="{re.escape(method_name)}"',
            flags=re.I,
        )
        if line is not None:
            return (line, col)

    # Try to locate quoted snippets/tokens from message.
    quoted = re.findall(r"'([^']+)'", message)
    for token in quoted:
        if not token.strip():
            continue
        line, col = find_literal_location(content, token, case_sensitive=False)
        if line is not None:
            return (line, col)

    # Fallback by check family.
    if check_id.startswith("pou_structure") or check_id in {
        "extends_visibility",
        "override_marker",
        "override_signature",
        "interface_contract",
        "policy_interface_contract_integrity",
        "extends_cycle",
        "override_super_call",
        "inheritance_property_contract",
        "fb_init_signature",
        "fb_init_super_call",
        "this_pointer_consistency",
        "abstract_contract",
        "fb_exit_contract",
        "dynamic_creation_attribute",
        "pointer_delete_pairing",
        "composition_depth",
        "interface_segregation",
        "method_visibility_consistency",
        "diamond_inheritance_warning",
        "abstract_instantiation",
        "property_accessor_pairing",
        "method_count",
        "main_var_input_mutation",
        "unsigned_loop_underflow",
    }:
        line, col = find_literal_location(content, "<POU ")
        if line is not None:
            return (line, col)

    if check_id.startswith("guid_"):
        line, col = find_regex_location(content, r'Id="\{[^"]+\}"')
        if line is not None:
            return (line, col)

    if check_id == "naming_conventions":
        for tag in ("<POU ", "<Itf ", "<DUT ", "<GVL "):
            line, col = find_literal_location(content, tag)
            if line is not None:
                return (line, col)

    # Final deterministic fallback.
    non_empty = [i for i, ln in enumerate(content.split("\n"), start=1) if ln.strip()]
    return (non_empty[0], 1) if non_empty else (1, 1)


def extract_line_snippet(content: str, line_num: int, context_lines: int = 2) -> str:
    """Extract code snippet around a specific line.

    Args:
        content: Full file content
        line_num: 1-indexed line number (matches ValidationIssue.line_num)
        context_lines: Number of context lines before/after (default 2)

    Returns:
        Snippet with line markers. Issue line marked with →

    Example:
        >>> extract_line_snippet(content, line_num=42, context_lines=2)
        "  40 |   <POU Name='FB_Test'>\\n"
        "  41 |     <Declaration>\\n"
        "→ 42 | \\t<VAR>\\n"        # ← Issue line marked
        "  43 |     END_VAR\\n"
        "  44 |   </Declaration>\\n"
    """
    if not content or line_num < 1:
        return ""

    lines = content.split("\n")

    # Handle invalid line numbers
    if line_num > len(lines):
        return ""

    # Calculate snippet range (0-indexed)
    start = max(0, line_num - context_lines - 1)  # -1 for 0-indexing
    end = min(len(lines), line_num + context_lines)

    snippet_lines = []
    for i in range(start, end):
        line_marker = "→" if (i + 1) == line_num else " "
        # Format: "→ 42 | <content>"
        snippet_lines.append(f"{line_marker} {i+1:3} | {lines[i]}")

    return "\n".join(snippet_lines)


def extract_xml_element_snippet(content: str, element_tag: str, max_chars: int = 300) -> str:
    """Extract snippet of specific XML element.

    Args:
        content: Full file content
        element_tag: Tag name (e.g., "POU", "Method", "Property")
        max_chars: Maximum snippet length (default 300)

    Returns:
        XML element snippet (truncated with ... if needed)

    Example:
        >>> extract_xml_element_snippet(content, "POU", max_chars=100)
        "<POU Name=\"FB_Example\" Id=\"{guid}\">\\n  <Declaration>...</Declaration>\\n</POU>"
    """
    if not content or not element_tag:
        return ""

    # Pattern to match opening and closing tags (non-greedy)
    pattern = rf"<{element_tag}[^>]*>.*?</{element_tag}>"

    match = re.search(pattern, content, re.DOTALL)
    if match:
        snippet = match.group(0)

        # Truncate if too long
        if len(snippet) > max_chars:
            return snippet[:max_chars] + "..."

        return snippet

    return ""


def extract_guid_snippet(content: str, guid: str) -> str:
    """Extract snippet showing a GUID in context.

    Args:
        content: Full file content
        guid: GUID to find (e.g., "{abcd-1234-5678-...}")

    Returns:
        Line containing the GUID (stripped of leading/trailing whitespace)

    Example:
        >>> extract_guid_snippet(content, "{a1b2c3d4-e5f6-7890-abcd-ef1234567890}")
        '<POU Name="FB_Motor" Id="{a1b2c3d4-e5f6-7890-abcd-ef1234567890}">'
    """
    if not content or not guid:
        return ""

    for line in content.split("\n"):
        if guid in line:
            return line.strip()

    return ""


def extract_first_occurrence_snippet(content: str, search_text: str, context_lines: int = 2) -> str:
    """Extract snippet around first occurrence of search text.

    Useful for file-level issues (e.g., tabs, trailing content) where you want
    to show the first problematic location.

    Args:
        content: Full file content
        search_text: Text to search for (e.g., "\\t" for tabs, "]]>" for trailing content)
        context_lines: Number of context lines before/after (default 2)

    Returns:
        Snippet with line markers around first occurrence

    Example:
        >>> extract_first_occurrence_snippet(content, "\\t", context_lines=1)
        " 41 |   <Declaration>\\n"
        "→ 42 | \\t<VAR>\\n"
        " 43 |   END_VAR\\n"
    """
    if not content or not search_text:
        return ""

    lines = content.split("\n")

    # Find first line containing search text
    for i, line in enumerate(lines):
        if search_text in line:
            # Use extract_line_snippet to show context
            return extract_line_snippet(content, i + 1, context_lines)

    return ""


def extract_xml_parse_error_context(content: str, error_message: str) -> str:
    """Extract context around XML parse error location.

    Attempts to extract line number from error message and show context.

    Args:
        content: Full file content (that failed to parse)
        error_message: XML parse error message (e.g., "syntax error: line 42, column 15")

    Returns:
        Snippet around error location, or first 5 lines if line number not found

    Example:
        >>> extract_xml_parse_error_context(content, "syntax error: line 42, column 15")
        " 40 |   <POU Name='FB_Test'>\\n"
        " 41 |     <Declaration>\\n"
        "→ 42 | <Unclosed\\n"
        " 43 |   </POU>\\n"
        " 44 | </TcPlcObject>\\n"
    """
    if not content:
        return ""

    # Try to extract line number from error message
    # Common patterns: "line 42", "line=42", "row 42"
    line_match = re.search(r"line[:\s=]+(\d+)", error_message, re.IGNORECASE)
    if not line_match:
        line_match = re.search(r"row[:\s=]+(\d+)", error_message, re.IGNORECASE)

    if line_match:
        line_num = int(line_match.group(1))
        return extract_line_snippet(content, line_num, context_lines=2)

    # Fallback: show first 5 lines (where errors often occur)
    lines = content.split("\n")
    snippet_lines = []
    for i in range(min(5, len(lines))):
        snippet_lines.append(f"  {i+1:3} | {lines[i]}")

    return "\n".join(snippet_lines)
