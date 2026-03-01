"""Private helper functions shared by all MCP tool modules.

This module contains all non-decorated helper functions extracted from the
original monolithic server.py. It imports shared state from mcp_app and
response helpers from mcp_responses.

Import order: mcp_app → mcp_responses → _server_helpers → mcp_tools_*
"""

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Literal, Optional, cast

from twincat_validator import TwinCATFile
from twincat_validator.policy_context import (
    ExecutionContext,
    compute_policy_fingerprint,
    resolve_execution_context,
)
from twincat_validator.mcp_app import (
    POLICY_RESPONSE_VERSION,
    SUPPORTED_POU_SUBTYPES,
    VALID_FORMAT_PROFILES,
    VALID_PROFILES,
    _LOOP_GUARD_STATE,
    config,
)
from twincat_validator.mcp_responses import _build_meta, _tool_error  # noqa: F401
from twincat_validator.result_contract import derive_contract_state
from twincat_validator.snippet_extractor import infer_issue_location


# ============================================================================
# INPUT VALIDATION HELPERS
# ============================================================================


def _validate_file_path(
    file_path: str,
    start_time: Optional[float] = None,
    execution_context: Optional[ExecutionContext] = None,
) -> tuple:
    """Validate file path exists and has a supported extension.

    Returns:
        (Path, None) on success, or (None, error_json_string) on failure.
    """
    path = Path(file_path)
    if not path.exists():
        return None, _tool_error(
            f"File not found: {file_path}",
            file_path=file_path,
            start_time=start_time,
            execution_context=execution_context,
            error_type="FileNotFoundError",
        )
    if path.suffix not in config.supported_extensions:
        return None, _tool_error(
            f"Unsupported file type: {path.suffix}",
            file_path=file_path,
            start_time=start_time,
            execution_context=execution_context,
            supported_types=config.supported_extensions,
        )
    return path, None


def _validate_profile(
    profile: str,
    start_time: Optional[float] = None,
    execution_context: Optional[ExecutionContext] = None,
) -> Optional[str]:
    """Validate response profile value.

    Returns:
        None on success, or error_json_string on failure.
    """
    if profile not in VALID_PROFILES:
        return _tool_error(
            f"Invalid profile: {profile}",
            start_time=start_time,
            execution_context=execution_context,
            valid_profiles=list(VALID_PROFILES),
        )
    return None


def _validate_format_profile(
    format_profile: str,
    start_time: Optional[float] = None,
    execution_context: Optional[ExecutionContext] = None,
) -> Optional[str]:
    """Validate formatting profile value."""
    if format_profile not in VALID_FORMAT_PROFILES:
        return _tool_error(
            f"Invalid format_profile: {format_profile}",
            start_time=start_time,
            execution_context=execution_context,
            valid_format_profiles=list(VALID_FORMAT_PROFILES),
        )
    return None


def _validate_enforcement_mode(
    enforcement_mode: str,
    start_time: Optional[float] = None,
    execution_context: Optional[ExecutionContext] = None,
) -> Optional[str]:
    """Validate policy enforcement mode."""
    if enforcement_mode not in ("strict", "compat"):
        return _tool_error(
            f"Invalid enforcement_mode: {enforcement_mode}",
            start_time=start_time,
            execution_context=execution_context,
            policy_checked=False,
            enforcement_mode=enforcement_mode,
            response_version=POLICY_RESPONSE_VERSION,
            valid_enforcement_modes=["strict", "compat"],
        )
    return None


def _normalize_file_type(file_type: str) -> str:
    """Normalize file type string to leading-dot format."""
    normalized = file_type.strip()
    if not normalized:
        return normalized
    if not normalized.startswith("."):
        normalized = f".{normalized}"
    return normalized


def _resolve_policy_target_path(target_path: str) -> Path:
    """Resolve policy lookup target path (file or directory) into a pseudo file path."""
    raw = (target_path or "").strip()
    if not raw:
        return Path.cwd() / "__policy_target__.TcPOU"

    candidate = Path(raw)
    if candidate.exists() and candidate.is_dir():
        return candidate / "__policy_target__.TcPOU"
    if candidate.suffix:
        return candidate
    return candidate / "__policy_target__.TcPOU"


def _compute_policy_fingerprint(policy: dict) -> str:
    """Compatibility wrapper for deterministic policy hashing."""
    return compute_policy_fingerprint(policy)


def _resolve_execution_context(
    target_path: str,
    enforcement_mode: str = "strict",
    response_version: str = "2",
) -> ExecutionContext:
    """Resolve policy execution context for OOP-sensitive tool calls."""
    mode = cast(Literal["strict", "compat"], enforcement_mode)
    return resolve_execution_context(
        target_path=target_path,
        enforcement_mode=mode,
        resolve_target_path=_resolve_policy_target_path,
        resolve_policy=config.resolve_oop_policy,
        response_version=response_version,
    )


# ============================================================================
# GENERATION CONTRACT HELPERS
# ============================================================================


def _contract_element_has_attributes(
    root: ET.Element, element_name: str, required_attributes: list[str]
) -> Optional[str]:
    """Validate that at least one element has all required attributes."""
    matching = [el for el in root.iter() if el.tag == element_name]
    if not matching:
        return f"Missing required element: <{element_name}>"
    for element in matching:
        missing = [attr for attr in required_attributes if attr not in element.attrib]
        if not missing:
            return None
    missing_list = ", ".join(required_attributes)
    return f"Element <{element_name}> must include attributes: {missing_list}"


def _check_generation_contract(file: TwinCATFile) -> list[str]:
    """Run deterministic generation-contract checks for a file."""
    contract = config.get_file_type_contract(file.suffix)
    if not contract:
        return [f"No generation contract found for file type {file.suffix}"]

    errors: list[str] = []

    try:
        root = file.xml_tree
    except ET.ParseError as exc:
        return [f"XML parse error: {exc}"]

    element_tags = {element.tag for element in root.iter()}
    for required_element in contract.get("required_elements", []):
        if required_element not in element_tags:
            errors.append(f"Missing required element: <{required_element}>")

    required_attributes = contract.get("required_attributes", {})
    for element_name, attrs in required_attributes.items():
        attr_error = _contract_element_has_attributes(root, element_name, attrs)
        if attr_error:
            errors.append(attr_error)

    content = file.content
    if "<Declaration><![CDATA[" not in content:
        errors.append(
            "Declaration must use CDATA format: <Declaration><![CDATA[...]]></Declaration>"
        )

    if file.suffix == ".TcPOU":
        if "<Implementation>" not in content or "<ST><![CDATA[" not in content:
            errors.append(
                "POU files must include <Implementation><ST><![CDATA[...]]></ST></Implementation>"
            )
        if "<LineIds" not in content:
            errors.append('POU files must include <LineIds Name="..."> section')

    return errors


# ============================================================================
# SKELETON BUILDER HELPERS
# ============================================================================


def _build_pou_skeleton(pou_subtype: str) -> str:
    """Build canonical .TcPOU skeleton for a specific subtype."""
    subtype = pou_subtype.lower()
    if subtype == "function":
        name = "FUNC_Example"
        declaration = [
            f"FUNCTION {name} : BOOL",
            "VAR_INPUT",
            "  bEnable : BOOL;",
            "END_VAR",
        ]
    elif subtype == "program":
        name = "PRG_Example"
        declaration = [
            f"PROGRAM {name}",
            "VAR",
            "  bEnable : BOOL;",
            "END_VAR",
        ]
    else:
        name = "FB_Example"
        declaration = [
            f"FUNCTION_BLOCK {name}",
            "VAR_INPUT",
            "  bEnable : BOOL;",
            "END_VAR",
        ]

    declaration_block = "\n".join(declaration)
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">',
        f'  <POU Name="{name}" Id="{{12345678-1234-1234-1234-123456789abc}}" SpecialFunc="None">',
        f"    <Declaration><![CDATA[{declaration_block}]]></Declaration>",
        "    <Implementation>",
        "      <ST><![CDATA[]]></ST>",
        "    </Implementation>",
        f'    <LineIds Name="{name}">',
        '      <LineId Id="1" Count="0" />',
        "    </LineIds>",
        "  </POU>",
        "</TcPlcObject>",
    ]
    return "\n".join(lines) + "\n"


def _build_contract_skeleton(
    file_type: str, subtype: Optional[str] = None
) -> tuple[Optional[str], Optional[str]]:
    """Return canonical skeleton text from contract with optional subtype specialization."""
    normalized_type = _normalize_file_type(file_type)
    if normalized_type not in config.supported_extensions:
        return None, f"Unsupported file type: {file_type}"

    if normalized_type == ".TcPOU":
        selected_subtype = (subtype or "function_block").lower()
        if selected_subtype not in SUPPORTED_POU_SUBTYPES:
            valid = ", ".join(SUPPORTED_POU_SUBTYPES)
            return None, f"Invalid POU subtype: {selected_subtype}. Valid values: {valid}"
        return _build_pou_skeleton(selected_subtype), None

    contract = config.get_file_type_contract(normalized_type)
    skeleton_lines = contract.get("minimal_skeleton", [])
    if not skeleton_lines:
        return None, f"No minimal skeleton defined for {normalized_type}"
    return "\n".join(skeleton_lines) + "\n", None


# ============================================================================
# INTERFACE / DUT EXTRACTION HELPERS
# ============================================================================


def _extract_implemented_interfaces(file: TwinCATFile) -> list[str]:
    """Extract interface names from a POU declaration with IMPLEMENTS clause."""
    if file.suffix != ".TcPOU":
        return []

    match = re.search(
        r"<POU\b[^>]*>.*?<Declaration><!\[CDATA\[(.*?)\]\]></Declaration>",
        file.content,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return []

    declaration = match.group(1)
    lines = []
    for raw in declaration.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("{") or line.startswith("//") or line.startswith("(*"):
            continue
        lines.append(line)
    if not lines:
        return []

    header = lines[0]
    impl_match = re.search(r"(?i)\bIMPLEMENTS\b\s+(.+?)(?=\bEXTENDS\b|$)", header)
    if not impl_match:
        return []

    names = [part.strip() for part in impl_match.group(1).split(",")]
    return [name for name in names if name]


def _extract_extended_base(file: TwinCATFile) -> Optional[str]:
    """Extract base FUNCTION_BLOCK name from EXTENDS clause in POU header."""
    if file.suffix != ".TcPOU":
        return None

    match = re.search(
        r"<POU\b[^>]*>.*?<Declaration><!\[CDATA\[(.*?)\]\]></Declaration>",
        file.content,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return None

    declaration = match.group(1)
    lines = []
    for raw in declaration.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("{") or line.startswith("//") or line.startswith("(*"):
            continue
        lines.append(line)
    if not lines:
        return None

    header = lines[0]
    extends_match = re.search(r"(?i)\bEXTENDS\b\s+([A-Za-z_][A-Za-z0-9_]*)", header)
    if not extends_match:
        return None
    return extends_match.group(1)


# ============================================================================
# DETERMINISTIC GUID / XML TAG REWRITE HELPERS
# ============================================================================


def _deterministic_guid(seed: str) -> str:
    """Generate deterministic lowercase GUID from seed text."""
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return f"{{{digest[0:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}}}"


def _rewrite_id_attr_in_tag(tag_text: str, guid_value: str) -> str:
    """Replace or inject Id attribute in an opening XML tag string."""
    if re.search(r'\bId="\{[^"]+\}"', tag_text):
        return re.sub(r'\bId="\{[^"]+\}"', f'Id="{guid_value}"', tag_text, count=1)
    return tag_text[:-1] + f' Id="{guid_value}">'


def _ensure_tcplcobject_attrs(file: TwinCATFile) -> bool:
    """Ensure root TcPlcObject carries canonical Version/ProductVersion attributes."""
    content = file.content
    match = re.search(r"<TcPlcObject\b[^>]*>", content)
    if not match:
        return False

    tag = match.group(0)
    updated_tag = tag
    changed = False
    if 'Version="' not in updated_tag:
        updated_tag = updated_tag[:-1] + ' Version="1.1.0.1">'
        changed = True
    if 'ProductVersion="' not in updated_tag:
        updated_tag = updated_tag[:-1] + ' ProductVersion="3.1.4024.12">'
        changed = True

    if changed:
        file.content = content[: match.start()] + updated_tag + content[match.end() :]
        return True
    return False


def _canonicalize_ids(file: TwinCATFile) -> bool:
    """Rewrite XML Id attributes to deterministic non-placeholder GUIDs.

    This addresses weak-model outputs that use repeated placeholder GUIDs.
    """
    content = file.content
    updated = content
    changed = False

    scope = f"{file.filepath.stem}:{file.suffix}"

    # Root object tags
    tag_patterns = [
        ("POU", "Name", lambda name, _idx: f"{scope}:pou:{name}"),
        ("DUT", "Name", lambda name, _idx: f"{scope}:dut:{name}"),
        ("GVL", "Name", lambda name, _idx: f"{scope}:gvl:{name}"),
        ("Itf", "Name", lambda name, _idx: f"{scope}:itf:{name}"),
        ("Method", "Name", lambda name, idx: f"{scope}:method:{name}:{idx}"),
        ("Property", "Name", lambda name, idx: f"{scope}:property:{name}:{idx}"),
        ("Get", "Name", lambda name, idx: f"{scope}:get:{name}:{idx}"),
        ("Set", "Name", lambda name, idx: f"{scope}:set:{name}:{idx}"),
        ("Action", "Name", lambda name, idx: f"{scope}:action:{name}:{idx}"),
    ]

    for tag_name, key_attr, seed_fn in tag_patterns:
        pattern = re.compile(rf"<{tag_name}\b[^>]*>")
        occurrence = 0

        def _replace(match: re.Match) -> str:
            nonlocal occurrence, changed
            occurrence += 1
            tag_text = match.group(0)
            name_match = re.search(rf'\b{key_attr}="([^"]+)"', tag_text)
            if not name_match:
                return tag_text
            seed = seed_fn(name_match.group(1), occurrence)
            new_tag = _rewrite_id_attr_in_tag(tag_text, _deterministic_guid(seed))
            if new_tag != tag_text:
                changed = True
            return new_tag

        updated = pattern.sub(_replace, updated)

    if changed:
        file.content = updated
    return changed


# ============================================================================
# INTERFACE SKELETON BUILDERS
# ============================================================================


def _build_interface_skeleton(interface_name: str) -> str:
    """Build canonical .TcIO interface skeleton for a specific interface name."""
    interface_id = _deterministic_guid(f"itf:{interface_name}")
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">',
        f'  <Itf Name="{interface_name}" Id="{interface_id}">',
        f"    <Declaration><![CDATA[INTERFACE {interface_name}",
        "]]></Declaration>",
        "  </Itf>",
        "</TcPlcObject>",
        "",
    ]
    return "\n".join(lines)


def _build_named_fb_skeleton(function_block_name: str) -> str:
    """Build canonical minimal FUNCTION_BLOCK .TcPOU skeleton for a specific name."""
    fb_id = _deterministic_guid(f"pou:{function_block_name}")
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">',
        f'  <POU Name="{function_block_name}" Id="{fb_id}" SpecialFunc="None">',
        f"    <Declaration><![CDATA[FUNCTION_BLOCK {function_block_name}",
        "END_FUNCTION_BLOCK]]></Declaration>",
        "    <Implementation>",
        "      <ST><![CDATA[]]></ST>",
        "    </Implementation>",
        f'    <LineIds Name="{function_block_name}">',
        '      <LineId Id="1" Count="0" />',
        "    </LineIds>",
        "  </POU>",
        "</TcPlcObject>",
        "",
    ]
    return "\n".join(lines)


def _extract_inline_methods_from_st(st_body: str) -> tuple[str, list[dict[str, str]]]:
    """Extract METHOD...END_METHOD blocks from ST body."""
    block_pattern = re.compile(
        r"(?ims)^\s*METHOD\s+([A-Za-z_][A-Za-z0-9_]*)\s*:[^\n]*\n.*?^\s*END_METHOD\s*$"
    )
    methods: list[dict[str, str]] = []

    def _parse_method_block(block: str) -> dict[str, str]:
        lines = block.splitlines()
        header = lines[0].strip() if lines else "METHOD Method : BOOL"
        name_match = re.match(r"(?i)METHOD\s+([A-Za-z_][A-Za-z0-9_]*)", header)
        method_name = name_match.group(1) if name_match else "Method"

        declaration_lines = [header]
        idx = 1
        while idx < len(lines) - 1:
            current = lines[idx]
            stripped = current.strip()
            if stripped == "":
                declaration_lines.append(current)
                idx += 1
                continue
            if re.match(r"(?i)^VAR(?:_INPUT|_OUTPUT|_IN_OUT|_TEMP)?\b", stripped):
                declaration_lines.append(current)
                idx += 1
                while idx < len(lines) - 1:
                    declaration_lines.append(lines[idx])
                    if lines[idx].strip().upper() == "END_VAR":
                        idx += 1
                        break
                    idx += 1
                continue
            break

        impl_lines = lines[idx:-1] if len(lines) > 1 else []
        return {
            "name": method_name,
            "declaration": "\n".join(declaration_lines).strip("\n"),
            "implementation": "\n".join(impl_lines).strip("\n"),
        }

    for match in block_pattern.finditer(st_body):
        methods.append(_parse_method_block(match.group(0)))

    cleaned = block_pattern.sub("", st_body)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip("\n")
    if cleaned:
        cleaned += "\n"
    return cleaned, methods


def _extract_method_declarations_for_interface(
    file: TwinCATFile,
) -> list[dict[str, str]]:
    """Extract method declarations from POU XML/inline-method forms for interface synthesis."""
    methods: list[dict[str, str]] = []

    xml_method_pattern = re.compile(
        r'<Method\s+Name="([^"]+)"[^>]*>\s*<Declaration><!\[CDATA\[(.*?)\]\]></Declaration>',
        re.DOTALL | re.IGNORECASE,
    )
    for match in xml_method_pattern.finditer(file.content):
        name = match.group(1).strip()
        declaration = match.group(2).strip("\n")
        if not declaration:
            declaration = f"METHOD {name} : BOOL"
        methods.append({"name": name, "declaration": declaration})

    impl_match = re.search(
        r"(?is)<Implementation>\s*<ST><!\[CDATA\[(.*?)\]\]></ST>\s*</Implementation>",
        file.content,
    )
    if impl_match:
        _, inline_methods = _extract_inline_methods_from_st(impl_match.group(1))
        for method in inline_methods:
            methods.append({"name": method["name"], "declaration": method["declaration"]})

    deduped: dict[str, str] = {}
    for method in methods:
        name = method["name"]
        declaration = method["declaration"].strip()
        declaration = re.sub(r"(?im)^\s*END_METHOD\s*$", "", declaration).strip()
        deduped[name] = declaration

    return [{"name": name, "declaration": declaration} for name, declaration in deduped.items()]


def _build_interface_with_methods(
    interface_name: str, method_declarations: list[dict[str, str]]
) -> str:
    """Build TcIO interface XML using explicit <Method> elements."""
    interface_id = _deterministic_guid(f"itf:{interface_name}")
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">',
        f'  <Itf Name="{interface_name}" Id="{interface_id}">',
        f"    <Declaration><![CDATA[INTERFACE {interface_name}",
        "]]></Declaration>",
    ]

    for method in method_declarations:
        method_id = _deterministic_guid(f"itf:{interface_name}:method:{method['name']}")
        lines.extend(
            [
                f'    <Method Name="{method["name"]}" Id="{method_id}">',
                f'      <Declaration><![CDATA[{method["declaration"]}',
                "]]></Declaration>",
                "    </Method>",
            ]
        )

    lines.extend(["  </Itf>", "</TcPlcObject>", ""])
    return "\n".join(lines)


def _to_pascal_case(name: str) -> str:
    """Convert a variable-like name into PascalCase (best effort)."""
    parts = re.split(r"[^A-Za-z0-9]+", name)
    joined = "".join(part[:1].upper() + part[1:] for part in parts if part)
    if not joined:
        return "Type"
    return joined


def _extract_structs_to_dut_files(file: TwinCATFile) -> list[str]:
    """Extract inline STRUCT declarations into generated .TcDUT files.

    Rewrites declaration references from inline STRUCT to ST_* DUT types.
    """
    if file.suffix != ".TcPOU":
        return []

    declaration_match = re.search(
        r"(?is)(<Declaration><!\[CDATA\[)(.*?)(\]\]></Declaration>)",
        file.content,
    )
    if not declaration_match:
        return []

    declaration = declaration_match.group(2)
    created: list[str] = []

    struct_pattern = re.compile(
        r"(?ims)^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(ARRAY\s*\[[^\]]+\]\s+OF\s+)?STRUCT\s*\n(.*?)^\s*END_STRUCT\s*;",
    )

    def _replace(match: re.Match) -> str:
        indent = match.group(1)
        var_name = match.group(2)
        array_prefix = match.group(3) or ""
        struct_body = match.group(4).rstrip("\n")

        base_name = _to_pascal_case(var_name)
        if len(base_name) > 1 and base_name[0] in {"A", "N", "S", "B", "R", "I", "U"}:
            base_name = base_name[1:]
        dut_name = f"ST_{base_name}Entry"
        dut_path = file.filepath.parent / f"{dut_name}.TcDUT"

        if not dut_path.exists():
            dut_id = _deterministic_guid(f"dut:{dut_name}")
            dut_lines = [
                '<?xml version="1.0" encoding="utf-8"?>',
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">',
                f'  <DUT Name="{dut_name}" Id="{dut_id}">',
                f"    <Declaration><![CDATA[TYPE {dut_name} : STRUCT",
                struct_body,
                "END_STRUCT",
                "END_TYPE]]></Declaration>",
                "  </DUT>",
                "</TcPlcObject>",
                "",
            ]
            dut_path.write_text("\n".join(dut_lines), encoding="utf-8", newline="\n")
            created.append(str(dut_path))

        return f"{indent}{var_name} : {array_prefix}{dut_name};"

    updated_declaration = struct_pattern.sub(_replace, declaration)
    if updated_declaration != declaration:
        file.content = (
            file.content[: declaration_match.start(2)]
            + updated_declaration
            + file.content[declaration_match.end(2) :]
        )

    return created


def _create_missing_implicit_files(file: TwinCATFile) -> list[str]:
    """Create deterministic implicit dependency files.

    Currently:
    - Interface .TcIO files for IMPLEMENTS I_* clauses
    - DUT .TcDUT files for inline STRUCT declarations in POU declaration blocks
    """
    created: list[str] = []
    for interface_name in _extract_implemented_interfaces(file):
        if not interface_name.startswith("I_"):
            continue
        interface_path = file.filepath.parent / f"{interface_name}.TcIO"
        if interface_path.exists():
            continue
        method_declarations = _extract_method_declarations_for_interface(file)
        if method_declarations:
            interface_content = _build_interface_with_methods(interface_name, method_declarations)
        else:
            interface_content = _build_interface_skeleton(interface_name)
        interface_path.write_text(interface_content, encoding="utf-8", newline="\n")
        created.append(str(interface_path))

    base_name = _extract_extended_base(file)
    if base_name and base_name.startswith("FB_"):
        base_path = file.filepath.parent / f"{base_name}.TcPOU"
        if not base_path.exists():
            base_content = _build_named_fb_skeleton(base_name)
            base_path.write_text(base_content, encoding="utf-8", newline="\n")
            created.append(str(base_path))

    created.extend(_extract_structs_to_dut_files(file))
    return created


# ============================================================================
# CANONICALIZATION HELPERS
# ============================================================================


def _normalize_interface_inline_methods(file: TwinCATFile) -> tuple[bool, int]:
    """Normalize TcIO interfaces from inline METHOD text to <Method> XML nodes.

    Returns:
        (changed, method_count)
    """
    if file.suffix != ".TcIO":
        return False, 0
    if "<Method " in file.content:
        return False, 0

    declaration_match = re.search(
        r"(?is)(<Declaration><!\[CDATA\[)(.*?)(\]\]></Declaration>)",
        file.content,
    )
    if not declaration_match:
        return False, 0

    declaration_body = declaration_match.group(2)
    if "METHOD " not in declaration_body.upper():
        return False, 0

    lines = declaration_body.splitlines()
    if not lines:
        return False, 0

    header_line = lines[0].strip()
    if not header_line.upper().startswith("INTERFACE "):
        return False, 0

    method_pattern = re.compile(
        r"(?ims)^\s*METHOD\s+([A-Za-z_][A-Za-z0-9_]*)\s*:[^\n]*\n.*?(?=^\s*METHOD\s+|^\s*END_INTERFACE\b|\Z)"
    )
    method_blocks = [m.group(0).strip("\n") for m in method_pattern.finditer(declaration_body)]
    if not method_blocks:
        return False, 0

    method_xml_blocks: list[str] = []
    for block in method_blocks:
        first_line = block.splitlines()[0].strip()
        name_match = re.match(r"(?i)METHOD\s+([A-Za-z_][A-Za-z0-9_]*)", first_line)
        method_name = name_match.group(1) if name_match else "Method"
        method_id = _deterministic_guid(f"itf:{file.filepath.stem}:method:{method_name}")
        method_xml_blocks.append(
            "\n".join(
                [
                    f'    <Method Name="{method_name}" Id="{method_id}">',
                    f"      <Declaration><![CDATA[{block}",
                    "]]></Declaration>",
                    "    </Method>",
                ]
            )
        )

    # Keep declaration as interface header only (canonical style)
    replacement_declaration = (
        f"{declaration_match.group(1)}{header_line}\n{declaration_match.group(3)}"
    )
    updated = (
        file.content[: declaration_match.start()]
        + replacement_declaration
        + file.content[declaration_match.end() :]
    )

    itf_close = re.search(r"(?is)</Itf>", updated)
    if not itf_close:
        return False, 0
    updated = (
        updated[: itf_close.start()]
        + "\n"
        + "\n".join(method_xml_blocks)
        + "\n"
        + updated[itf_close.start() :]
    )

    file.content = updated
    return True, len(method_blocks)


def _canonicalize_getter_declarations(file: TwinCATFile) -> bool:
    """Normalize empty getter/setter <Declaration> CDATA to canonical 'VAR\\nEND_VAR\\n' form.

    Applied only under format_profile='twincat_canonical'.  Ensures that every
    <Get> and <Set> declaration block uses the explicit VAR/END_VAR scaffold
    rather than a bare empty CDATA (which can confuse some TwinCAT versions).

    Symmetry guarantee: running this function twice on the same content yields
    identical output (idempotent).

    Supports both .TcPOU and .TcIO files.

    Returns:
        True if content was changed, False otherwise.
    """
    if file.suffix not in (".TcPOU", ".TcIO"):
        return False

    content = file.content
    accessor_decl_pattern = re.compile(
        r"(?is)(<(?:Get|Set)\b[^>]*>\s*<Declaration><!\[CDATA\[)(.*?)(\]\]></Declaration>)"
    )

    CANONICAL_EMPTY = "VAR\nEND_VAR\n"

    def _normalize_body(match: re.Match) -> str:
        body = match.group(2).replace("\r\n", "\n").strip()
        if body and body not in ("VAR\nEND_VAR", "VAR\nEND_VAR\n"):
            return match.group(0)
        return f"{match.group(1)}{CANONICAL_EMPTY}{match.group(3)}"

    updated = accessor_decl_pattern.sub(_normalize_body, content)
    if updated != content:
        file.content = updated
        return True
    return False


def _canonicalize_tcio_layout(file: TwinCATFile) -> tuple[bool, int]:
    """Normalize .TcIO declaration/method CDATA blocks to stable multiline layout.

    Returns:
        (changed, declaration_blocks_rewritten)
    """
    if file.suffix != ".TcIO":
        return False, 0

    content = file.content
    rewritten = 0

    itf_decl_pattern = re.compile(
        r'(?is)(<Itf\b[^>]*\bName="([^"]+)"[^>]*>.*?<Declaration><!\[CDATA\[)(.*?)(\]\]></Declaration>)'
    )
    itf_match = itf_decl_pattern.search(content)
    if itf_match:
        interface_name = itf_match.group(2)
        canonical_decl = f"{itf_match.group(1)}INTERFACE {interface_name}\n{itf_match.group(4)}"
        content = content[: itf_match.start()] + canonical_decl + content[itf_match.end() :]
        rewritten += 1

    method_decl_pattern = re.compile(
        r'(?is)(<Method\s+Name="[^"]+"[^>]*>\s*<Declaration><!\[CDATA\[)(.*?)(\]\]></Declaration>)'
    )

    def _rewrite_method_decl(match: re.Match) -> str:
        nonlocal rewritten
        body = match.group(2).replace("\r\n", "\n").strip("\n")
        body = re.sub(r"(?ims)^\s*VAR_INPUT\s*\n\s*END_VAR\s*$", "", body).strip("\n")
        if body:
            body = body + "\n"
        rewritten += 1
        return f"{match.group(1)}{body}{match.group(3)}"

    content = method_decl_pattern.sub(_rewrite_method_decl, content)

    if content != file.content:
        file.content = content
        return True, rewritten
    return False, 0


def _canonicalize_tcpou_method_layout(file: TwinCATFile) -> tuple[bool, int]:
    """Normalize .TcPOU layout for deterministic, compiler-friendly output.

    Currently:
    - Remove empty local VAR...END_VAR blocks from <Method><Declaration> CDATA.
    - Ensure method declaration CDATA ends with a trailing newline.
    - Collapse duplicate <LineId .../> entries inside each <LineIds ...> block.

    Returns:
        (changed, declaration_blocks_rewritten)
    """
    if file.suffix != ".TcPOU":
        return False, 0

    content = file.content
    rewritten = 0

    method_decl_pattern = re.compile(
        r'(?is)(<Method\s+Name="[^"]+"[^>]*>\s*<Declaration><!\[CDATA\[)(.*?)(\]\]></Declaration>)'
    )

    def _rewrite_method_decl(match: re.Match) -> str:
        nonlocal rewritten
        body = match.group(2).replace("\r\n", "\n").strip("\n")

        body = re.sub(r"(?ims)\n\s*VAR\s*\n\s*END_VAR\s*$", "", body)
        body = re.sub(
            r"(?ims)\n\s*VAR(?:_INPUT|_OUTPUT|_IN_OUT|_TEMP)\s*\n\s*END_VAR\s*$",
            "",
            body,
        )

        if body:
            body = body + "\n"
        rewritten += 1
        return f"{match.group(1)}{body}{match.group(3)}"

    content = method_decl_pattern.sub(_rewrite_method_decl, content)

    accessor_decl_pattern = re.compile(
        r"(?is)(<(?:Get|Set)\b[^>]*>\s*<Declaration><!\[CDATA\[)(.*?)(\]\]></Declaration>)"
    )

    def _rewrite_accessor_decl(match: re.Match) -> str:
        nonlocal rewritten
        body = match.group(2).replace("\r\n", "\n").strip("\n")
        body = re.sub(r"(?ims)^\s*VAR\s*\n\s*END_VAR\s*$", "", body).strip("\n")
        if body:
            body = body + "\n"
        rewritten += 1
        return f"{match.group(1)}{body}{match.group(3)}"

    content = accessor_decl_pattern.sub(_rewrite_accessor_decl, content)

    st_block_pattern = re.compile(r"(?is)(<ST><!\[CDATA\[)(.*?)(\]\]></ST>)")

    def _rewrite_st_block(match: re.Match) -> str:
        nonlocal rewritten
        body = match.group(2).replace("\r\n", "\n")
        lines = body.split("\n")
        updated_lines: list[str] = []
        changed_local = False

        for line in lines:
            # Canonical style: no semicolon on block terminators.
            # Example: END_IF; -> END_IF
            terminator_match = re.match(
                r"^(\s*)(END_(?:IF|FOR|WHILE|REPEAT|CASE))\s*;\s*(//.*)?$",
                line,
            )
            if terminator_match:
                indent = terminator_match.group(1) or ""
                keyword = terminator_match.group(2)
                comment = terminator_match.group(3) or ""
                line = f"{indent}{keyword}"
                if comment:
                    line = f"{line} {comment}"
                changed_local = True
            updated_lines.append(line)

        if changed_local:
            rewritten += 1
        joined_lines = "\n".join(updated_lines)
        return f"{match.group(1)}{joined_lines}{match.group(3)}"

    content = st_block_pattern.sub(_rewrite_st_block, content)

    lineids_block_pattern = re.compile(r'(?is)(<LineIds\s+Name="[^"]+"\s*>)(.*?)(</LineIds>)')

    def _rewrite_lineids_block(match: re.Match) -> str:
        nonlocal rewritten
        inner = match.group(2)
        lineid_entries = re.findall(r"<LineId\b[^>]*/>", inner, flags=re.IGNORECASE)
        if len(lineid_entries) <= 1:
            return match.group(0)
        rewritten += 1
        return f"{match.group(1)}\n      {lineid_entries[0]}\n    {match.group(3)}"

    content = lineids_block_pattern.sub(_rewrite_lineids_block, content)

    if content != file.content:
        file.content = content
        return True, rewritten
    return False, 0


def _normalize_line_endings_and_trailing_ws(file: TwinCATFile) -> bool:
    """Normalize line endings/newline and trim trailing whitespace."""
    original = file.content
    content = original.replace("\r\n", "\n").replace("\r", "\n")
    content = "\n".join(line.rstrip() for line in content.split("\n"))
    if not content.endswith("\n"):
        content += "\n"
    if content != original:
        file.content = content
        return True
    return False


def _rebuild_pou_lineids(file: TwinCATFile) -> bool:
    """Rebuild POU-level LineIds blocks with deterministic IDs and realistic counts.

    Generates entries for:
    - main POU body
    - each <Method Name="..."> in file order
    - each <Property Name="..."> accessor (Get preferred, Set fallback)
    """
    if file.suffix != ".TcPOU":
        return False

    content = file.content
    pou_match = re.search(r'(?is)<POU\b[^>]*\bName="([^"]+)"[^>]*>(.*)</POU>', content)
    if not pou_match:
        return False

    pou_name = pou_match.group(1)
    pou_body = pou_match.group(2)

    pou_body_wo_lineids = re.sub(r'(?is)\s*<LineIds\s+Name="[^"]+"\s*>.*?</LineIds>', "", pou_body)

    main_st_match = re.search(
        r"(?is)<Implementation>\s*<ST><!\[CDATA\[(.*?)\]\]></ST>\s*</Implementation>",
        pou_body_wo_lineids,
    )
    main_st = main_st_match.group(1) if main_st_match else ""

    def _count_lines(st_code: str) -> int:
        lines = st_code.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        non_empty = [ln for ln in lines if ln.strip()]
        return 0 if not non_empty else max(len(non_empty) - 1, 0)

    sections: list[tuple[str, int]] = [(pou_name, _count_lines(main_st))]

    for method_match in re.finditer(
        r'(?is)<Method\s+Name="([^"]+)"[^>]*>(.*?)</Method>',
        pou_body_wo_lineids,
    ):
        method_name = method_match.group(1)
        method_body = method_match.group(2)
        method_st_match = re.search(
            r"(?is)<Implementation>\s*<ST><!\[CDATA\[(.*?)\]\]></ST>\s*</Implementation>",
            method_body,
        )
        method_st = method_st_match.group(1) if method_st_match else ""
        sections.append((f"{pou_name}.{method_name}", _count_lines(method_st)))

    for prop_match in re.finditer(
        r'(?is)<Property\s+Name="([^"]+)"[^>]*>(.*?)</Property>',
        pou_body_wo_lineids,
    ):
        prop_name = prop_match.group(1)
        prop_body = prop_match.group(2)
        get_match = re.search(
            r"(?is)<Get\b[^>]*>.*?<Implementation>\s*<ST><!\[CDATA\[(.*?)\]\]></ST>\s*</Implementation>.*?</Get>",
            prop_body,
        )
        if get_match:
            sections.append((f"{pou_name}.{prop_name}.Get", _count_lines(get_match.group(1))))
            continue
        set_match = re.search(
            r"(?is)<Set\b[^>]*>.*?<Implementation>\s*<ST><!\[CDATA\[(.*?)\]\]></ST>\s*</Implementation>.*?</Set>",
            prop_body,
        )
        if set_match:
            sections.append((f"{pou_name}.{prop_name}.Set", _count_lines(set_match.group(1))))

    lineids_parts = []
    next_id = 1
    for section_name, count in sections:
        lineids_parts.append(
            "\n".join(
                [
                    f'    <LineIds Name="{section_name}">',
                    f'      <LineId Id="{next_id}" Count="{count}" />',
                    "    </LineIds>",
                ]
            )
        )
        next_id += 1

    rebuilt = (
        content[: pou_match.start(2)]
        + pou_body_wo_lineids.rstrip()
        + "\n"
        + "\n".join(lineids_parts)
        + "\n"
        + content[pou_match.end(2) :]
    )

    if rebuilt != content:
        file.content = rebuilt
        return True
    return False


def _canonicalize_tcdut_layout(file: TwinCATFile) -> tuple[bool, int]:
    """Normalize .TcDUT layout and remove non-canonical elements.

    Returns:
        (changed, rewrite_count)
    """
    if file.suffix != ".TcDUT":
        return False, 0

    content = file.content
    rewrites = 0

    lineids_pattern = re.compile(r"(?is)\s*<LineIds\b[^>]*>.*?</LineIds>")
    content_no_lineids, removed = lineids_pattern.subn("", content)
    if removed > 0:
        content = content_no_lineids
        rewrites += removed

    dut_match = re.search(r'(?is)<DUT\b[^>]*\bName="([^"]+)"', content)
    declaration_match = re.search(
        r"(?is)(<Declaration><!\[CDATA\[)(.*?)(\]\]></Declaration>)",
        content,
    )
    if dut_match and declaration_match:
        dut_name = dut_match.group(1)
        body = declaration_match.group(2).replace("\r\n", "\n").strip("\n")
        body = re.sub(
            r"(?ims)^TYPE\s+[A-Za-z_][A-Za-z0-9_]*\s*:\s*\n\s*STRUCT\b",
            f"TYPE {dut_name} : STRUCT",
            body,
        )
        body = re.sub(
            r"(?ims)^TYPE\s+[A-Za-z_][A-Za-z0-9_]*\s*:\s*STRUCT\b",
            f"TYPE {dut_name} : STRUCT",
            body,
        )
        body = re.sub(r"(?ims)^\s*END_TYPE\s*$", "END_TYPE", body)
        body = re.sub(r"(?m)^([ \t]{1,})([A-Za-z_][A-Za-z0-9_]*\s*:)", r"  \2", body)
        canonical_decl = f"{declaration_match.group(1)}{body}\n{declaration_match.group(3)}"
        if canonical_decl != declaration_match.group(0):
            content = (
                content[: declaration_match.start()]
                + canonical_decl
                + content[declaration_match.end() :]
            )
            rewrites += 1

    if content != file.content:
        file.content = content
        return True, rewrites
    return False, 0


# ============================================================================
# FINGERPRINT / LOOP-GUARD HELPERS
# ============================================================================


def _sha256_text(content: str) -> str:
    """Compute stable content fingerprint."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _compute_issue_fingerprint(issue_records: list[dict]) -> str:
    """Build stable fingerprint for remaining issues/blockers."""
    normalized = []
    for issue in issue_records:
        normalized.append(
            {
                "check": str(issue.get("check", "")),
                "line": issue.get("line"),
                "message": str(issue.get("message", "")),
                "severity": str(issue.get("severity", "")),
                "fixable": bool(issue.get("fixable", False)),
            }
        )
    payload = json.dumps(
        sorted(normalized, key=lambda x: (x["check"], str(x["line"]), x["message"]))
    )
    return _sha256_text(payload)


def _engine_issues_to_records(validation_result) -> list[dict]:
    """Map engine issues into deterministic dict records for loop-guard tracking."""
    records: list[dict] = []
    for issue in validation_result.issues:
        records.append(
            {
                "check": getattr(issue, "check_id", "") or "",
                "line": getattr(issue, "line_num", None),  # corrected: attr is line_num, not line
                "message": getattr(issue, "message", "") or "",
                "severity": getattr(issue, "severity", "") or "",
                "fixable": bool(getattr(issue, "fix_available", False)),
            }
        )
    return records


def _update_no_progress_count(file_path: str, issue_fingerprint: str, content_changed: bool) -> int:
    """Update no-progress counter for a file.

    Increments only when issue fingerprint repeats and content did not change.
    """
    key = str(Path(file_path).resolve())
    previous = _LOOP_GUARD_STATE.get(key, {})
    previous_fp = str(previous.get("issue_fingerprint", ""))
    previous_count = int(previous.get("no_progress_count", 0))

    if not issue_fingerprint:
        count = 0
    elif issue_fingerprint == previous_fp and not content_changed:
        count = previous_count + 1
    else:
        count = 0

    _LOOP_GUARD_STATE[key] = {
        "issue_fingerprint": issue_fingerprint,
        "no_progress_count": count,
    }
    return count


# ============================================================================
# GUID / ARTIFACT SANITY HELPERS
# ============================================================================


def _count_invalid_guid_tokens(content: str) -> int:
    """Count truly malformed GUID tokens in Id="{...}" attributes.

    Uppercase-but-well-formed GUIDs are NOT counted because they are
    auto-fixable by canonicalization.  Only tokens that fail the any-case
    GUID pattern (wrong length, non-hex chars, spaces, etc.) are counted.
    This aligns with GuidFormatCheck's three-tier logic.
    """
    guid_token_pattern = re.compile(r'Id="\{([^"]+)\}"')
    any_case_guid_pattern = re.compile(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    )
    invalid = 0
    for token in guid_token_pattern.findall(content):
        if not any_case_guid_pattern.match(token):
            invalid += 1
    return invalid


def _artifact_sanity_violations(file: TwinCATFile, strict_contract: bool) -> tuple[int, list[str]]:
    """Run final fail-closed artifact sanity checks."""
    invalid_guid_count = _count_invalid_guid_tokens(file.content)
    contract_violations = _check_generation_contract(file) if strict_contract else []
    return invalid_guid_count, contract_violations


# ============================================================================
# ORCHESTRATION HINT HELPERS
# ============================================================================


def _derive_next_action(
    safe_to_import: bool,
    safe_to_compile: bool,
    blockers: list[dict],
    no_change_detected: bool,
    no_progress_count: int = 0,
    contract_failed: bool = False,
) -> tuple[str, bool]:
    """Derive deterministic next step guidance for weak-model orchestration."""
    if safe_to_import and safe_to_compile:
        return "done_no_further_autofix", False
    if contract_failed:
        return "regenerate_from_skeleton", True

    if (
        no_change_detected
        and no_progress_count >= 2
        and (not safe_to_import or not safe_to_compile)
    ):
        return "stop_and_report", True

    if any(
        "METHOD declaration found inside main <Implementation><ST> block"
        in blocker.get("message", "")
        for blocker in blockers
    ):
        return "extract_methods_to_xml", False

    if blockers:
        return "manual_intervention", True
    return "rerun_autofix", False


# ============================================================================
# METHOD PROMOTION HELPER
# ============================================================================


def _promote_inline_methods_to_xml(file: TwinCATFile) -> tuple[bool, int]:
    """Promote inline main-ST METHOD blocks to proper <Method> XML nodes."""
    if file.suffix != ".TcPOU":
        return False, 0

    impl_match = re.search(
        r"(?is)(<Implementation>\s*<ST><!\[CDATA\[)(.*?)(\]\]></ST>\s*</Implementation>)",
        file.content,
    )
    if not impl_match:
        return False, 0

    cleaned_st, methods = _extract_inline_methods_from_st(impl_match.group(2))
    if not methods:
        return False, 0

    method_xml_blocks: list[str] = []
    for method in methods:
        method_xml_blocks.append(
            "\n".join(
                [
                    f'    <Method Name="{method["name"]}">',
                    f'      <Declaration><![CDATA[{method["declaration"]}]]></Declaration>',
                    "      <Implementation>",
                    f'        <ST><![CDATA[{method["implementation"]}]]></ST>',
                    "      </Implementation>",
                    "    </Method>",
                ]
            )
        )

    new_impl = f"{impl_match.group(1)}{cleaned_st}{impl_match.group(3)}"
    updated = file.content[: impl_match.start()] + new_impl + file.content[impl_match.end() :]

    lineids_match = re.search(r"(?is)\s*<LineIds\b", updated)
    if lineids_match:
        updated = (
            updated[: lineids_match.start()]
            + "\n"
            + "\n".join(method_xml_blocks)
            + "\n"
            + updated[lineids_match.start() :]
        )
    else:
        pou_close = re.search(r"(?is)</POU>", updated)
        if not pou_close:
            return False, 0
        updated = (
            updated[: pou_close.start()]
            + "\n"
            + "\n".join(method_xml_blocks)
            + "\n"
            + updated[pou_close.start() :]
        )

    file.content = updated
    return True, len(methods)


# ============================================================================
# ENGINE RESULT CONVERSION
# ============================================================================


def _dedupe_validation_issues(issues: list) -> list:
    """Deduplicate ValidationIssue objects by check_id/severity/category/message/location."""
    seen: set[tuple[str, str, str, str, int | None, int | None]] = set()
    deduped = []
    for issue in issues:
        key = (
            str(getattr(issue, "check_id", "") or ""),  # different checks → different issues
            str(getattr(issue, "severity", "")),
            str(getattr(issue, "category", "")),
            str(getattr(issue, "message", "")),
            getattr(issue, "line_num", None),
            getattr(issue, "column", None),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return deduped


def _apply_known_limitation_tags(check_id: str, issue, file: TwinCATFile) -> None:
    """Annotate known validator/parser limitation metadata on issue objects."""
    message = str(getattr(issue, "message", "") or "")

    # Legacy subtype parser can misclassify FUNCTION_BLOCK declarations in edge cases.
    if (
        check_id == "pou_structure"
        and file.pou_subtype == "function_block"
        and "FUNCTION cannot have Methods" in message
    ):
        issue.known_limitation = True
        issue.limitation_code = "pou_subtype_parser_misclassification"
        return

    # Interface signature mismatch false-positive when declaration text differs semantically
    # only by formatting/comment artifacts after normalization.
    if check_id == "pou_structure_interface" and "signature mismatch" in message:
        issue.known_limitation = True
        issue.limitation_code = "interface_signature_text_normalization"
        return

    if getattr(issue, "known_limitation", None) is None:
        issue.known_limitation = False


def _convert_engine_result_to_mcp_format(
    engine_result,
    file: TwinCATFile,
    validation_time: float,
    validation_level: str,
    profile: str = "full",
) -> dict:
    """Convert EngineValidationResult to MCP output format.

    Args:
        engine_result: Validation result from ValidationEngine
        file: TwinCATFile that was validated
        validation_time: Time taken for validation
        validation_level: Validation level used ("all", "critical", "style")
        profile: Output profile ("full" or "llm_strict")

    Returns:
        Dict in MCP format (minimal if llm_strict, verbose if full)
    """
    validation_status = "passed"
    if engine_result.errors > 0:
        validation_status = "failed"
    elif engine_result.warnings > 0:
        validation_status = "warnings"

    # Fill deterministic issue locations for checks that don't set line_num/column.
    for check_result in engine_result.check_results:
        for issue in check_result.issues:
            if issue.line_num is not None:
                _apply_known_limitation_tags(check_result.check_id, issue, file)
                continue
            line_num, column = infer_issue_location(
                file.content, check_result.check_id, issue.message
            )
            issue.line_num = line_num
            issue.column = column
            _apply_known_limitation_tags(check_result.check_id, issue, file)

    check_results = []
    for check_result in engine_result.check_results:
        check_config = config.validation_checks.get(check_result.check_id, {})

        issues = check_result.issues
        if any(i.severity in ("error", "critical") for i in issues):
            status = "failed"
        elif any(i.severity == "warning" for i in issues):
            status = "warning"
        else:
            status = "passed"

        check_results.append(
            {
                "id": check_result.check_id,
                "name": check_config.get("name", "Unknown Check"),
                "status": status,
                "message": check_config.get("description", ""),
                "auto_fixable": check_config.get("auto_fixable", False),
                "severity": check_config.get("severity", "info"),
            }
        )

    metrics = {
        "guid_count": 0,
        "method_count": 0,
        "property_count": 0,
        "lineids_expected": 0,
        "lineids_found": 0,
        "tab_lines": 0,
        "cdata_issues": 0,
        "excessive_blank_lines": 0,
    }

    for issue in engine_result.issues:
        if issue.category == "Tabs":
            metrics["tab_lines"] += 1
        elif issue.category == "Format" and "CDATA" in issue.message:
            metrics["cdata_issues"] += 1
        elif issue.category == "Format" and "blank lines" in issue.message:
            metrics["excessive_blank_lines"] += 1

    if profile == "llm_strict":
        deduped_issues = _dedupe_validation_issues(engine_result.issues)
        cs = derive_contract_state(deduped_issues, profile=profile)

        return {
            "file_path": str(file.filepath),
            "safe_to_import": cs.safe_to_import,
            "safe_to_compile": cs.safe_to_compile,
            "done": cs.done,
            "status": cs.status,
            "blocking_count": cs.blocking_count,
            "blockers": cs.blockers,
            "next_action": (
                "done_no_further_validation" if cs.done else "manual_intervention_or_targeted_fix"
            ),
        }

    deduped_issues = _dedupe_validation_issues(engine_result.issues)
    return {
        "file_path": str(file.filepath),
        "file_type": file.suffix,
        "pou_subtype": file.pou_subtype,
        "file_size": len(file.content),
        "validation_status": validation_status,
        "validation_time": round(validation_time, 3),
        "summary": {
            "total_checks": len(check_results),
            "passed": sum(1 for c in check_results if c["status"] == "passed"),
            "failed": sum(1 for c in check_results if c["status"] == "failed"),
            "warnings": sum(1 for c in check_results if c["status"] == "warning"),
        },
        "checks": check_results,
        "issues": [issue.to_dict() for issue in deduped_issues],
        "metrics": metrics,
    }
