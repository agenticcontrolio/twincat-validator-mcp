"""OOP symbol extraction utilities for TwinCAT POU/interface contract checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

from .file_handler import TwinCATFile
from .utils import _extract_declaration_significant_lines, _extract_pou_declaration_cdata


_ST_RESERVED_WORDS = {
    "ABS",
    "AND",
    "ARRAY",
    "BOOL",
    "BY",
    "CASE",
    "DINT",
    "DO",
    "ELSE",
    "ELSIF",
    "END_CASE",
    "END_FOR",
    "END_FUNCTION",
    "END_FUNCTION_BLOCK",
    "END_IF",
    "END_PROGRAM",
    "END_REPEAT",
    "END_STRUCT",
    "END_TYPE",
    "END_VAR",
    "END_WHILE",
    "EXIT",
    "FALSE",
    "FOR",
    "FUNCTION",
    "FUNCTION_BLOCK",
    "IF",
    "IMPLEMENTS",
    "INT",
    "INTERFACE",
    "MOD",
    "NOT",
    "OF",
    "OR",
    "PROGRAM",
    "PROPERTY",
    "REAL",
    "REPEAT",
    "RETURN",
    "STRUCT",
    "SUPER",
    "THEN",
    "THIS",
    "TIME",
    "TO_INT",
    "TRUE",
    "UDINT",
    "UNTIL",
    "VAR",
    "VAR_CONSTANT",
    "VAR_IN_OUT",
    "VAR_INPUT",
    "VAR_OUTPUT",
    "VAR_TEMP",
    "WHILE",
    "XOR",
}


@dataclass
class MethodSymbol:
    name: str
    return_type: str
    signature_params: list[tuple[str, str, str]] = field(default_factory=list)
    declaration: str = ""
    implementation: str = ""
    local_symbols: set[str] = field(default_factory=set)
    has_override_attribute: bool = False
    has_override_keyword: bool = False
    is_abstract: bool = False
    has_abstract_keyword: bool = False

    def signature_key(self) -> tuple[str, tuple[tuple[str, str, str], ...]]:
        return self.return_type, tuple(self.signature_params)

    def has_super_call(self) -> bool:
        pattern = rf"(?i)\bSUPER\^\s*\.\s*{re.escape(self.name)}\s*\("
        return bool(re.search(pattern, self.implementation))


@dataclass
class PropertySymbol:
    name: str
    prop_type: str
    has_get: bool
    has_set: bool

    def accessor_key(self) -> tuple[bool, bool]:
        return self.has_get, self.has_set


@dataclass
class PouSymbol:
    name: str
    pou_type: str
    extends: str | None
    implements: list[str]
    member_by_block: dict[str, set[str]]
    methods: dict[str, MethodSymbol]
    properties: dict[str, PropertySymbol]
    used_symbols: set[str]
    is_abstract: bool = False
    has_abstract_keyword: bool = False

    @property
    def private_members(self) -> set[str]:
        private = set()
        private.update(self.member_by_block.get("VAR", set()))
        private.update(self.member_by_block.get("VAR_TEMP", set()))
        private.update(self.member_by_block.get("VAR_CONSTANT", set()))
        return private

    @property
    def protected_members(self) -> set[str]:
        return set()

    @property
    def public_members(self) -> set[str]:
        return set()

    @property
    def local_symbols(self) -> set[str]:
        symbols = set()
        for names in self.member_by_block.values():
            symbols.update(names)
        symbols.update(self.methods.keys())
        symbols.update(self.properties.keys())
        for method in self.methods.values():
            symbols.update(method.local_symbols)
        return symbols


@dataclass
class InterfaceSymbol:
    name: str
    methods: dict[str, MethodSymbol]
    properties: dict[str, PropertySymbol]


def _normalize_type(type_text: str) -> str:
    if not type_text:
        return ""
    normalized = re.sub(r"\s+", " ", type_text.strip().rstrip(";"))
    return normalized.upper()


def _strip_st_comments_and_strings(st_text: str) -> str:
    text = st_text
    text = re.sub(r"(?is)\(\*.*?\*\)", "", text)
    text = re.sub(r"'(?:''|[^'])*'", "''", text)
    text = re.sub(r"(?m)//.*$", "", text)
    return text


def _extract_main_declaration(content: str, suffix: str) -> str:
    if suffix == ".TcPOU":
        declaration = _extract_pou_declaration_cdata(content)
        return declaration or ""
    if suffix == ".TcIO":
        match = re.search(
            r"(?is)<Itf\b[^>]*>\s*<Declaration><!\[CDATA\[(.*?)\]\]></Declaration>",
            content,
        )
        return match.group(1) if match else ""
    return ""


def _extract_header_info(declaration: str) -> tuple[str, str, str | None, list[str]]:
    lines = _extract_declaration_significant_lines(declaration)
    if not lines:
        return "", "", None, []
    header = lines[0].strip()
    upper = header.upper()
    if upper.startswith("FUNCTION_BLOCK "):
        pou_type = "FUNCTION_BLOCK"
    elif upper.startswith("FUNCTION "):
        pou_type = "FUNCTION"
    elif upper.startswith("PROGRAM "):
        pou_type = "PROGRAM"
    elif upper.startswith("INTERFACE "):
        pou_type = "INTERFACE"
    else:
        pou_type = ""

    fb_match = re.match(
        r"(?i)^FUNCTION_BLOCK\s+(?:ABSTRACT\s+)?([A-Za-z_][A-Za-z0-9_]*)",
        header,
    )
    if fb_match:
        name = fb_match.group(1)
    else:
        name_match = re.match(
            r"(?i)^(FUNCTION|PROGRAM|INTERFACE)\s+([A-Za-z_][A-Za-z0-9_]*)",
            header,
        )
        name = name_match.group(2) if name_match else ""

    extends_match = re.search(r"(?i)\bEXTENDS\b\s+([A-Za-z_][A-Za-z0-9_]*)", header)
    extends = extends_match.group(1) if extends_match else None

    implements_match = re.search(r"(?i)\bIMPLEMENTS\b\s+(.+?)(?=\bEXTENDS\b|$)", header)
    if not implements_match:
        return pou_type, name, extends, []
    interfaces = [item.strip() for item in implements_match.group(1).split(",") if item.strip()]
    return pou_type, name, extends, interfaces


def _parse_var_blocks(
    declaration: str,
) -> tuple[dict[str, set[str]], dict[str, list[tuple[str, str, str]]]]:
    by_block: dict[str, set[str]] = {}
    signature_blocks: dict[str, list[tuple[str, str, str]]] = {}
    current_block = ""
    for raw in declaration.splitlines():
        line = raw.strip()
        if not line:
            continue
        block_match = re.match(
            r"(?i)^(VAR|VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT|VAR_TEMP|VAR_CONSTANT)\b",
            line,
        )
        if block_match:
            current_block = block_match.group(1).upper()
            by_block.setdefault(current_block, set())
            signature_blocks.setdefault(current_block, [])
            continue
        if line.upper() == "END_VAR":
            current_block = ""
            continue
        if not current_block:
            continue

        var_match = re.match(r"^([A-Za-z_][A-Za-z0-9_,\s]*)\s*:\s*([^;]+);?", line)
        if not var_match:
            continue
        raw_names = [name.strip() for name in var_match.group(1).split(",") if name.strip()]
        var_type = _normalize_type(var_match.group(2))
        for name in raw_names:
            by_block[current_block].add(name)
            signature_blocks[current_block].append((current_block, name, var_type))
    return by_block, signature_blocks


def _parse_method_declaration(declaration: str, implementation: str = "") -> MethodSymbol | None:
    lines = declaration.replace("\r\n", "\n").split("\n")
    header = ""
    for line in lines:
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith("{")
            or stripped.startswith("//")
            or stripped.startswith("(*")
        ):
            continue
        if re.match(r"(?i)^METHOD\b", stripped):
            header = stripped
            break
    if not header:
        return None

    method_match = re.match(
        r"(?i)^METHOD(?:\s+(?:PUBLIC|PROTECTED|PRIVATE|ABSTRACT|OVERRIDE))*\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s*:\s*(.+))?$",
        header,
    )
    if not method_match:
        return None
    name = method_match.group(1)
    return_type = _normalize_type(method_match.group(2)) if method_match.group(2) else ""
    _, signature_blocks = _parse_var_blocks(declaration)

    params: list[tuple[str, str, str]] = []
    for block_name in ("VAR_INPUT", "VAR_IN_OUT", "VAR_OUTPUT"):
        params.extend(signature_blocks.get(block_name, []))

    local_symbols = set()
    local_blocks, _ = _parse_var_blocks(declaration)
    for names in local_blocks.values():
        local_symbols.update(names)
    local_symbols.add(name)

    has_override_attr = bool(re.search(r"(?im)^\s*\{attribute\s+['\"]override['\"]\}", declaration))
    has_override_keyword = bool(re.search(r"(?i)\bOVERRIDE\b", header))
    has_abstract_keyword = bool(re.search(r"(?i)\bABSTRACT\b", header))

    return MethodSymbol(
        name=name,
        return_type=return_type,
        signature_params=params,
        declaration=declaration,
        implementation=implementation,
        local_symbols=local_symbols,
        has_override_attribute=has_override_attr,
        has_override_keyword=has_override_keyword,
        is_abstract=has_abstract_keyword,
        has_abstract_keyword=has_abstract_keyword,
    )


def _parse_property_declaration(declaration: str) -> tuple[str, str] | None:
    lines = _extract_declaration_significant_lines(declaration)
    if not lines:
        return None
    prop_line = lines[0]
    match = re.match(r"(?i)^PROPERTY\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+)$", prop_line)
    if not match:
        return None
    return match.group(1), _normalize_type(match.group(2))


def parse_pou_symbol(file: TwinCATFile) -> PouSymbol | None:
    if file.suffix != ".TcPOU":
        return None

    declaration = _extract_main_declaration(file.content, file.suffix)
    pou_type, name, extends, interfaces = _extract_header_info(declaration)
    first_sig_lines = _extract_declaration_significant_lines(declaration)
    first_sig = first_sig_lines[0] if first_sig_lines else ""
    abstract_keyword = bool(re.search(r"(?i)\bABSTRACT\b", first_sig))
    member_by_block, _ = _parse_var_blocks(declaration)

    methods: dict[str, MethodSymbol] = {}
    method_pattern = re.compile(
        r'(?is)<Method\s+[^>]*Name="([^"]+)"[^>]*>\s*'
        r"<Declaration><!\[CDATA\[(.*?)\]\]></Declaration>(.*?)</Method>"
    )
    for match in method_pattern.finditer(file.content):
        method_body = match.group(3)
        implementation_match = re.search(
            r"(?is)<Implementation>\s*<ST><!\[CDATA\[(.*?)\]\]></ST>\s*</Implementation>",
            method_body,
        )
        implementation = implementation_match.group(1).strip("\n") if implementation_match else ""
        parsed = _parse_method_declaration(match.group(2).strip("\n"), implementation)
        if parsed is None:
            continue
        # Prefer parsed declaration name for consistency.
        methods[parsed.name] = parsed

    properties: dict[str, PropertySymbol] = {}
    for match in re.finditer(
        r'(?is)<Property\s+[^>]*Name="([^"]+)"[^>]*>(.*?)</Property>',
        file.content,
    ):
        prop_name_xml = match.group(1)
        body = match.group(2)
        decl_match = re.search(r"(?is)<Declaration><!\[CDATA\[(.*?)\]\]></Declaration>", body)
        if not decl_match:
            continue
        parsed_prop = _parse_property_declaration(decl_match.group(1).strip("\n"))
        if parsed_prop:
            prop_name, prop_type = parsed_prop
        else:
            prop_name = prop_name_xml
            prop_type = ""
        properties[prop_name] = PropertySymbol(
            name=prop_name,
            prop_type=prop_type,
            has_get=bool(re.search(r"(?is)<Get\b", body)),
            has_set=bool(re.search(r"(?is)<Set\b", body)),
        )

    st_blocks = re.findall(r"(?is)<ST><!\[CDATA\[(.*?)\]\]></ST>", file.content)
    used_symbols: set[str] = set()
    for st in st_blocks:
        cleaned = _strip_st_comments_and_strings(st)
        for token in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", cleaned):
            if token.upper() in _ST_RESERVED_WORDS:
                continue
            used_symbols.add(token)

    return PouSymbol(
        name=name,
        pou_type=pou_type,
        extends=extends,
        implements=interfaces,
        member_by_block=member_by_block,
        methods=methods,
        properties=properties,
        used_symbols=used_symbols,
        is_abstract=abstract_keyword,
        has_abstract_keyword=abstract_keyword,
    )


def parse_interface_symbol(path: Path) -> InterfaceSymbol | None:
    if not path.exists() or path.suffix != ".TcIO":
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None

    declaration = _extract_main_declaration(content, ".TcIO")
    _, name, _, _ = _extract_header_info(declaration)
    if not name:
        itf_match = re.search(r'(?is)<Itf\b[^>]*\bName="([^"]+)"', content)
        name = itf_match.group(1) if itf_match else ""

    methods: dict[str, MethodSymbol] = {}
    for match in re.finditer(
        r'(?is)<Method\s+[^>]*Name="([^"]+)"[^>]*>\s*<Declaration><!\[CDATA\[(.*?)\]\]></Declaration>',
        content,
    ):
        parsed = _parse_method_declaration(match.group(2).strip("\n"))
        if parsed is not None:
            methods[parsed.name] = parsed

    properties: dict[str, PropertySymbol] = {}
    for match in re.finditer(
        r'(?is)<Property\s+[^>]*Name="([^"]+)"[^>]*>(.*?)</Property>', content
    ):
        body = match.group(2)
        decl_match = re.search(r"(?is)<Declaration><!\[CDATA\[(.*?)\]\]></Declaration>", body)
        if not decl_match:
            continue
        parsed_prop = _parse_property_declaration(decl_match.group(1).strip("\n"))
        if parsed_prop:
            prop_name, prop_type = parsed_prop
        else:
            prop_name = match.group(1)
            prop_type = ""
        properties[prop_name] = PropertySymbol(
            name=prop_name,
            prop_type=prop_type,
            has_get=bool(re.search(r"(?is)<Get\b", body)),
            has_set=bool(re.search(r"(?is)<Set\b", body)),
        )

    return InterfaceSymbol(name=name, methods=methods, properties=properties)


def resolve_nearby_symbol_file(origin: Path, symbol_name: str, suffix: str) -> Path | None:
    """Resolve nearby TwinCAT symbol file from same/parent folders."""
    same_dir = origin.parent / f"{symbol_name}{suffix}"
    if same_dir.exists():
        return same_dir

    roots = [origin.parent]
    parent = origin.parent.parent
    if parent != origin.parent:
        roots.append(parent)

    attr_name = "POU" if suffix == ".TcPOU" else "Itf" if suffix == ".TcIO" else ""
    name_fragment = f'Name="{symbol_name}"'
    for root in roots:
        for candidate in root.rglob(f"*{suffix}"):
            try:
                text = candidate.read_text(encoding="utf-8")
            except OSError:
                continue
            if attr_name and f"<{attr_name} " not in text:
                continue
            if name_fragment in text:
                return candidate
    return None
