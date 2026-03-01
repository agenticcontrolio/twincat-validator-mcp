"""Structure validation checks for TwinCAT files.

Extracted from server.py lines 520-857.
"""

import re
from pathlib import Path

from .base import BaseCheck, CheckRegistry
from ..models import ValidationIssue
from ..file_handler import TwinCATFile
from .oop_checks import collect_interface_contract_violations
from ..utils import _extract_pou_declaration_cdata, _extract_declaration_significant_lines
from ..config_loader import get_shared_config
from ..snippet_extractor import extract_xml_element_snippet

# Canonical message constants — keep wording consistent across all call sites.
_VAR_PROTECTED_MSG = (
    "VAR PROTECTED / VAR_PROTECTED block detected in POU declaration. "
    "This is not a valid TwinCAT variable block (server policy). "
    "Use plain VAR...END_VAR and expose members via METHOD/PROPERTY with PROTECTED access specifier."
)
_VAR_PROTECTED_FIX = (
    "Replace VAR PROTECTED...END_VAR (or VAR_PROTECTED...END_VAR) with VAR...END_VAR and "
    "expose members through PROTECTED methods/properties."
)


def _get_config():
    """Get shared config instance."""
    return get_shared_config()


@CheckRegistry.register
class FileEndingCheck(BaseCheck):
    """Validates file ends with "</TcPlcObject>" properly.

    Extracted from server.py lines 520-549 (check_file_ending method).
    """

    check_id = "file_ending"

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        """Check file ending correctness.

        Args:
            file: TwinCATFile to validate

        Returns:
            List of ValidationIssue objects for file ending problems
        """
        issues = []

        # Find last non-empty line
        last_line = ""
        for line in reversed(file.lines):
            if line.strip():
                last_line = line.strip()
                break

        if last_line == "</TcPlcObject>":
            # OK - correct ending
            pass
        elif last_line == "</TcPlcObject>]]>":
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="Format",
                    message="File has ']]>' after </TcPlcObject>",
                    fix_available=True,
                    fix_suggestion="Remove ]]> after </TcPlcObject>",
                )
            )
        elif last_line.endswith("]]>"):
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="Format",
                    message="File ends with ']]>' - should end with '</TcPlcObject>' only",
                    fix_available=True,
                    fix_suggestion="Remove extra ]]> at end of file",
                )
            )
        else:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="Format",
                    message=f"Unexpected ending: '{last_line}'",
                    fix_available=False,
                )
            )

        return issues


@CheckRegistry.register
class PropertyVarBlocksCheck(BaseCheck):
    """Validates property getters have VAR blocks.

    Extracted from server.py lines 551-585 (check_property_var_blocks method).
    """

    check_id = "property_var_blocks"

    def should_skip(self, file: TwinCATFile) -> bool:
        """Skip for non-.TcPOU/.TcIO files and for functions.

        Args:
            file: TwinCATFile to check

        Returns:
            True if check should be skipped
        """
        # Skip for GVLs (no properties) and DUTs
        if file.suffix not in [".TcPOU", ".TcIO"]:
            return True
        # FUNCTIONs cannot have properties
        if file.pou_subtype == "function":
            return True
        return False

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        """Check property getters have VAR blocks.

        Args:
            file: TwinCATFile to validate

        Returns:
            List of ValidationIssue objects for property VAR block problems
        """
        issues = []

        getter_count = file.content.count('<Get Name="Get"')

        if getter_count == 0:
            return issues

        missing_var = 0
        getter_positions = [m.start() for m in re.finditer(r'<Get Name="Get"', file.content)]

        for pos in getter_positions:
            next_content = file.content[pos : pos + 300]
            if (
                "<Declaration><![CDATA[VAR" not in next_content
                and "<Declaration><![CDATA[]]>" not in next_content
            ):
                missing_var += 1

        if missing_var > 0:
            # Get knowledge base entry (Phase 3)
            kb = _get_config().get_check_knowledge("property_var_blocks")

            # Extract correct example (Phase 3)
            correct_example = None
            if kb.get("correct_examples"):
                correct_example = kb["correct_examples"][0].get("code")

            # Extract snippet showing a property element (Phase 3)
            code_snippet = extract_xml_element_snippet(file.content, "Property", max_chars=400)

            issues.append(
                ValidationIssue(
                    severity="error",
                    category="Property",
                    message=f"{missing_var} property getter(s) missing VAR blocks. "
                    + "All getters MUST have 'VAR END_VAR' declaration.",
                    fix_available=True,
                    fix_suggestion="Add VAR END_VAR block to property getters",
                    code_snippet=code_snippet,
                    explanation=kb.get("explanation"),
                    correct_example=correct_example,
                )
            )

        return issues


@CheckRegistry.register
class LineIdsCountCheck(BaseCheck):
    """Validates LineIds count matches methods+properties+1.

    Extracted from server.py lines 587-608 (check_lineids_count method).
    """

    check_id = "lineids_count"

    @staticmethod
    def _extract_pou_name(content: str) -> str | None:
        """Extract POU Name attribute."""
        match = re.search(r'<POU\b[^>]*\bName="([^"]+)"', content)
        return match.group(1) if match else None

    @staticmethod
    def _find_lineids_inside_methods(content: str) -> list[str]:
        """Detect <LineIds> nested inside <Method> blocks."""
        offenders: list[str] = []
        method_pattern = re.compile(r'(?is)<Method\s+Name="([^"]+)"[^>]*>(.*?)</Method>')
        for match in method_pattern.finditer(content):
            method_name = match.group(1)
            method_body = match.group(2)
            if "<LineIds " in method_body:
                offenders.append(method_name)
        return offenders

    @staticmethod
    def _find_mismatched_lineids_names(content: str) -> list[str]:
        """Detect invalid LineIds Name values for POU and its methods."""
        pou_name = LineIdsCountCheck._extract_pou_name(content)
        if not pou_name:
            return []

        lineid_names = re.findall(r'<LineIds\s+Name="([^"]+)"', content)
        method_names = set(re.findall(r'<Method\s+Name="([^"]+)"', content))

        expected_names = {pou_name}
        expected_names.update({f"{pou_name}.{method_name}" for method_name in method_names})

        invalid: list[str] = []
        for name in lineid_names:
            if name in expected_names:
                continue
            # Keep compatibility with property accessor naming like FB_Test.Value.Get/.Set
            if name.startswith(f"{pou_name}.") and (name.endswith(".Get") or name.endswith(".Set")):
                continue
            invalid.append(name)
        return invalid

    @staticmethod
    def _count_st_lines(st_code: str) -> int:
        """Count semantic ST lines for LineIds Count attribute."""
        lines = st_code.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        non_empty = [ln for ln in lines if ln.strip()]
        return 0 if not non_empty else max(len(non_empty) - 1, 0)

    @staticmethod
    def _expected_lineids_counts(content: str) -> dict[str, int]:
        """Compute expected LineIds section->Count values using canonical rules."""
        expected: dict[str, int] = {}
        pou_name = LineIdsCountCheck._extract_pou_name(content)
        if not pou_name:
            return expected

        main_st_match = re.search(
            r"(?is)<Implementation>\s*<ST><!\[CDATA\[(.*?)\]\]></ST>\s*</Implementation>",
            content,
        )
        expected[pou_name] = LineIdsCountCheck._count_st_lines(
            main_st_match.group(1) if main_st_match else ""
        )

        for method_match in re.finditer(
            r'(?is)<Method\s+Name="([^"]+)"[^>]*>(.*?)</Method>',
            content,
        ):
            method_name = method_match.group(1)
            method_body = method_match.group(2)
            method_st_match = re.search(
                r"(?is)<Implementation>\s*<ST><!\[CDATA\[(.*?)\]\]></ST>\s*</Implementation>",
                method_body,
            )
            method_st = method_st_match.group(1) if method_st_match else ""
            expected[f"{pou_name}.{method_name}"] = LineIdsCountCheck._count_st_lines(method_st)

        for prop_match in re.finditer(
            r'(?is)<Property\s+Name="([^"]+)"[^>]*>(.*?)</Property>',
            content,
        ):
            prop_name = prop_match.group(1)
            prop_body = prop_match.group(2)
            get_match = re.search(
                r"(?is)<Get\b[^>]*>.*?<Implementation>\s*<ST><!\[CDATA\[(.*?)\]\]></ST>\s*</Implementation>.*?</Get>",
                prop_body,
            )
            if get_match:
                expected[f"{pou_name}.{prop_name}.Get"] = LineIdsCountCheck._count_st_lines(
                    get_match.group(1)
                )
                continue
            set_match = re.search(
                r"(?is)<Set\b[^>]*>.*?<Implementation>\s*<ST><!\[CDATA\[(.*?)\]\]></ST>\s*</Implementation>.*?</Set>",
                prop_body,
            )
            if set_match:
                expected[f"{pou_name}.{prop_name}.Set"] = LineIdsCountCheck._count_st_lines(
                    set_match.group(1)
                )

        return expected

    @staticmethod
    def _lineids_quality_issues(content: str) -> list[str]:
        """Validate deterministic LineIds quality (Id sequence + Count sanity)."""
        issues: list[str] = []
        expected_counts = LineIdsCountCheck._expected_lineids_counts(content)

        blocks: list[tuple[str, list[tuple[int, int]]]] = []
        for block in re.finditer(r'(?is)<LineIds\s+Name="([^"]+)"\s*>(.*?)</LineIds>', content):
            name = block.group(1)
            entries: list[tuple[int, int]] = []
            for item in re.finditer(
                r'<LineId\b[^>]*\bId="(\d+)"[^>]*\bCount="(\d+)"[^>]*/>',
                block.group(2),
            ):
                entries.append((int(item.group(1)), int(item.group(2))))
            blocks.append((name, entries))

        # Keep backward compatibility for legacy files where blocks exist but entries were omitted.
        if not any(entries for _, entries in blocks):
            return issues

        for name, entries in blocks:
            if len(entries) != 1:
                issues.append(
                    f"LineIds block '{name}' must contain exactly one LineId entry, found {len(entries)}"
                )

        canonical = [(name, entries[0]) for name, entries in blocks if len(entries) == 1]
        for idx, (name, (line_id, count)) in enumerate(canonical, start=1):
            if line_id != idx:
                issues.append(
                    f"LineIds block '{name}' has non-canonical Id={line_id}; expected {idx}"
                )
            expected = expected_counts.get(name)
            if expected is not None and count != expected:
                issues.append(f"LineIds block '{name}' has Count={count}; expected {expected}")
        return issues

    def should_skip(self, file: TwinCATFile) -> bool:
        """Skip for non-.TcPOU files.

        Args:
            file: TwinCATFile to check

        Returns:
            True if check should be skipped
        """
        # Skip for non-POU files (no executable code)
        return file.suffix != ".TcPOU"

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        """Check LineIds count matches methods/properties.

        Args:
            file: TwinCATFile to validate

        Returns:
            List of ValidationIssue objects for LineIds count problems
        """
        issues = []

        method_count = len(re.findall(r"<(?:Method|Property) Name=", file.content))
        lineids_count = len(re.findall(r"<LineIds Name=", file.content))
        expected_lineids = method_count + 1  # +1 for POU body (FB, FUNCTION, or PROGRAM)

        if lineids_count != expected_lineids:
            delta = expected_lineids - lineids_count
            if delta > 0:
                fix_suggestion = f"Add {delta} missing LineIds entries"
            else:
                fix_suggestion = f"Remove {abs(delta)} extra LineIds entries"
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="LineIds",
                    message=(
                        "LineIds count mismatch. "
                        f"Expected {expected_lineids}, found {lineids_count}"
                    ),
                    fix_available=True,
                    fix_suggestion=fix_suggestion,
                )
            )

        nested_lineids = self._find_lineids_inside_methods(file.content)
        if nested_lineids:
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="LineIds",
                    message=(
                        "LineIds elements found inside Method blocks: " + ", ".join(nested_lineids)
                    ),
                    fix_available=False,
                    fix_suggestion=(
                        'Move method LineIds to POU level using Name="' 'POUName.MethodName".'
                    ),
                )
            )

        invalid_names = self._find_mismatched_lineids_names(file.content)
        if invalid_names:
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="LineIds",
                    message=(
                        "Invalid LineIds Name entries: " + ", ".join(sorted(set(invalid_names)))
                    ),
                    fix_available=False,
                    fix_suggestion=(
                        'Use Name="POUName" for body and ' 'Name="POUName.MethodName" for methods.'
                    ),
                )
            )

        quality_issues = self._lineids_quality_issues(file.content)
        if quality_issues:
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="LineIds",
                    message="LineIds quality mismatch: " + "; ".join(quality_issues[:4]),
                    fix_available=True,
                    fix_suggestion=(
                        "Run autofix_file(format_profile='twincat_canonical') to rebuild "
                        "canonical sequential LineIds Id/Count metadata."
                    ),
                )
            )

        return issues


@CheckRegistry.register
class ElementOrderingCheck(BaseCheck):
    """Validates Declaration before Implementation.

    Extracted from server.py lines 610-647 (check_element_ordering method).
    """

    check_id = "element_ordering"

    def should_skip(self, file: TwinCATFile) -> bool:
        """Skip for non-.TcPOU files and for functions.

        Args:
            file: TwinCATFile to check

        Returns:
            True if check should be skipped
        """
        # Skip for non-POU files (different structure)
        if file.suffix != ".TcPOU":
            return True
        # FUNCTIONs cannot have Methods or Properties, skip ordering check
        if file.pou_subtype == "function":
            return True
        return False

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        """Check elements are in correct order.

        Args:
            file: TwinCATFile to validate

        Returns:
            List of ValidationIssue objects for element ordering problems
        """
        issues = []

        declaration_pos = file.content.find("<Declaration>")
        implementation_pos = file.content.find("<Implementation>")
        first_method_pos = file.content.find("<Method ")
        first_property_pos = file.content.find("<Property ")

        if declaration_pos > 0 and implementation_pos > 0:
            if declaration_pos > implementation_pos:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        category="Order",
                        message="Declaration should come before Implementation",
                        fix_available=False,
                    )
                )

        if implementation_pos > 0:
            if first_method_pos > 0 and first_method_pos < implementation_pos:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        category="Order",
                        message="Methods should come after Implementation",
                        fix_available=False,
                    )
                )
            if first_property_pos > 0 and first_property_pos < implementation_pos:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        category="Order",
                        message="Properties should come after Implementation",
                        fix_available=False,
                    )
                )

        return issues


# ============================================================================
# WS4: PouStructureCheck decomposition — focused sub-checks
# ============================================================================


@CheckRegistry.register
class PouStructureHeaderCheck(BaseCheck):
    """Check POU header-level structural integrity.

    Catches:
    - INTERFACE declarations stored in .TcPOU files
    - Inline STRUCT declarations in POU variable sections
    - EXTENDS clause on non-FUNCTION_BLOCK POUs
    - Missing base FUNCTION_BLOCK when EXTENDS is present
    """

    check_id = "pou_structure_header"

    def should_skip(self, file: TwinCATFile) -> bool:
        # Must run even when pou_subtype is None — misfiled INTERFACE files have no recognized subtype
        return file.suffix != ".TcPOU"

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        # Misfiled interface
        if _PouStructureHelpers._is_misfiled_interface_in_tcpou(file):
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="Structure",
                    message="INTERFACE declaration found in .TcPOU file. Interfaces must be stored "
                    "as .TcIO with a top-level <Itf> element.",
                    fix_available=False,
                    fix_suggestion=(
                        'Move this interface to an .TcIO file and use <Itf Name="...">.'
                    ),
                )
            )

        # Inline STRUCT
        if _PouStructureHelpers._find_inline_struct_in_pou_declaration(file):
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="Structure",
                    message=(
                        "Inline STRUCT declaration detected in POU variable section. "
                        "Use a separate .TcDUT type (e.g., ST_*), then reference it."
                    ),
                    fix_available=False,
                    fix_suggestion=(
                        "Create a .TcDUT file with TYPE ST_* : STRUCT ... END_STRUCT END_TYPE, "
                        "and replace inline STRUCT with ST_*."
                    ),
                )
            )

        # Inline TYPE declaration in POU declaration
        if _PouStructureHelpers._find_inline_type_in_pou_declaration(file):
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="Structure",
                    message=(
                        "Inline TYPE declaration detected in POU declaration. "
                        "Declare user types in dedicated .TcDUT files instead of inside .TcPOU."
                    ),
                    fix_available=False,
                    fix_suggestion=(
                        "Move TYPE...END_TYPE to a .TcDUT file and reference that type from the POU."
                    ),
                )
            )

        # CONST...END_CONST is not a valid TwinCAT POU declaration block
        if _PouStructureHelpers._find_const_block_in_pou_declaration(file):
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="Structure",
                    message=(
                        "CONST...END_CONST block detected in POU declaration. "
                        "TwinCAT POU declarations should use VAR CONSTANT...END_VAR."
                    ),
                    fix_available=False,
                    fix_suggestion="Replace CONST...END_CONST with VAR CONSTANT...END_VAR.",
                )
            )

        # VAR_TEMP block disallowed by project convention
        if _PouStructureHelpers._find_var_temp_in_pou_declaration(file):
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="Structure",
                    message=(
                        "VAR_TEMP block detected in POU declaration. "
                        "Use regular VAR for local mutable variables."
                    ),
                    fix_available=False,
                    fix_suggestion="Replace VAR_TEMP...END_VAR with VAR...END_VAR.",
                )
            )

        # VAR PROTECTED / VAR_PROTECTED are not valid TwinCAT variable blocks (server policy).
        if _PouStructureHelpers._find_var_protected_in_pou_declaration(file):
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="Structure",
                    message=_VAR_PROTECTED_MSG,
                    fix_available=False,
                    fix_suggestion=_VAR_PROTECTED_FIX,
                )
            )

        # EXTENDS constraints
        base_name = _PouStructureHelpers._extract_extended_base(file)
        if base_name:
            if file.pou_subtype != "function_block":
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="Structure",
                        message="EXTENDS clause found on non-FUNCTION_BLOCK POU. "
                        "Only FUNCTION_BLOCK can inherit via EXTENDS in TwinCAT.",
                        fix_available=False,
                        fix_suggestion="Use FUNCTION_BLOCK for inheritance or remove EXTENDS.",
                    )
                )
            elif not _PouStructureHelpers._base_definition_exists(file, base_name):
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="Structure",
                        message=f"POU extends base '{base_name}' but no matching base "
                        "FUNCTION_BLOCK (.TcPOU) was found nearby.",
                        fix_available=False,
                        fix_suggestion=f"Create base file '{base_name}.TcPOU' or adjust "
                        "the EXTENDS clause to an existing base FUNCTION_BLOCK.",
                    )
                )

        return issues


@CheckRegistry.register
class PouStructureMethodsCheck(BaseCheck):
    """Check POU method-level structural integrity.

    Catches:
    - METHOD declarations inside main <Implementation><ST> block
    - VAR declaration blocks inside method implementation ST
    - Invalid RETURN value syntax in methods
    - Assignments to VAR_INPUT parameters
    - Assignments to undeclared method-local symbols
    """

    check_id = "pou_structure_methods"

    def should_skip(self, file: TwinCATFile) -> bool:
        return file.pou_subtype is None

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        # Illegal METHOD in main ST
        if _PouStructureHelpers._find_illegal_method_in_main_implementation(file):
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="Structure",
                    message="METHOD declaration found inside main <Implementation><ST> block. "
                    'TwinCAT methods must be separate <Method Name="..."> XML elements.',
                    fix_available=False,
                    fix_suggestion="Move each METHOD body into its own <Method> element and keep "
                    "main Implementation for POU body logic only.",
                )
            )

        # Illegal VAR blocks in main ST implementation
        if _PouStructureHelpers._find_main_impl_var_block(file):
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="Structure",
                    message=(
                        "VAR declaration block found inside main <Implementation><ST> block. "
                        "Declare POU-local symbols in the <Declaration> section."
                    ),
                    fix_available=False,
                    fix_suggestion=(
                        "Move VAR...END_VAR blocks from main ST implementation to "
                        "POU Declaration CDATA."
                    ),
                )
            )

        # VAR blocks inside method impl
        methods_with_var_block = _PouStructureHelpers._find_method_impl_var_block_issues(file)
        if methods_with_var_block:
            method_list = ", ".join(methods_with_var_block)
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="Structure",
                    message=(
                        "Method implementation contains VAR declaration block(s): "
                        f"{method_list}. "
                        "Method-local declarations must be in "
                        "<Method><Declaration>, not <Method><Implementation><ST>."
                    ),
                    fix_available=False,
                    fix_suggestion=(
                        "Move VAR...END_VAR blocks from method ST implementation "
                        "into the method Declaration CDATA block."
                    ),
                )
            )

        # VAR_TEMP blocks in method declarations are disallowed by project convention
        methods_with_var_temp_decl = _PouStructureHelpers._find_method_declaration_var_temp_issues(
            file
        )
        if methods_with_var_temp_decl:
            method_list = ", ".join(methods_with_var_temp_decl)
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="Structure",
                    message=(
                        "Method declaration contains VAR_TEMP block(s): "
                        f"{method_list}. Use VAR...END_VAR for local mutable variables."
                    ),
                    fix_available=False,
                    fix_suggestion="Replace VAR_TEMP...END_VAR with VAR...END_VAR in method declarations.",
                )
            )

        # Invalid RETURN syntax
        methods_with_invalid_return = _PouStructureHelpers._find_invalid_return_value_statements(
            file
        )
        if methods_with_invalid_return:
            method_list = ", ".join(methods_with_invalid_return)
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="Structure",
                    message=f"Invalid ST return syntax in method(s): {method_list}. "
                    "Use 'MethodName := value; RETURN;' instead of 'RETURN value;'.",
                    fix_available=False,
                    fix_suggestion=(
                        "Assign method result via method name, then use RETURN; with no value."
                    ),
                )
            )

        # VAR_INPUT mutations
        input_mutations = _PouStructureHelpers._find_var_input_mutations(file)
        if input_mutations:
            mutation_list = ", ".join(f"{method}.{name}" for method, name in input_mutations)
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="Structure",
                    message=f"Assignments to VAR_INPUT parameter(s) detected: {mutation_list}.",
                    fix_available=False,
                    fix_suggestion=(
                        "Copy VAR_INPUT values to local variables before normalization/mutation."
                    ),
                )
            )

        # Undeclared assignments
        undeclared_assignments = _PouStructureHelpers._find_undeclared_method_assignments(file)
        if undeclared_assignments:
            missing = ", ".join(f"{method}.{symbol}" for method, symbol in undeclared_assignments)
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="Structure",
                    message=f"Undeclared assignment target(s) in method implementation: {missing}.",
                    fix_available=False,
                    fix_suggestion=(
                        "Declare method-local variables in <Method><Declaration> VAR...END_VAR."
                    ),
                )
            )

        # Interface arrays used polymorphically without explicit binding
        unbound_interface_arrays = _PouStructureHelpers._find_unbound_interface_array_usage(file)
        if unbound_interface_arrays:
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="Structure",
                    message=(
                        "Potential unbound interface array reference(s): "
                        + ", ".join(unbound_interface_arrays)
                        + ". Interface array elements are used but no concrete assignment "
                        "(:= or REF=) was detected."
                    ),
                    fix_available=False,
                    fix_suggestion=(
                        "Bind interface array entries before first use, e.g. "
                        "aIfaces[0] := fbConcrete; or aIfaces[0] REF= fbConcrete."
                    ),
                )
            )

        # Logic-safety warning: hard-fault classes should not clear via unauthenticated reset.
        reset_without_auth = _PouStructureHelpers._find_reset_clears_fault_without_auth(file)
        if reset_without_auth:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="Logic",
                    message=(
                        "Reset method(s) clear fault state without authorization input while "
                        "hard-fault paths are present: " + ", ".join(reset_without_auth) + "."
                    ),
                    fix_available=False,
                    fix_suggestion=(
                        "Require explicit authorization input for hard-fault reset or add a "
                        "dedicated authorized reset method."
                    ),
                )
            )

        # Logic-safety warning: orchestration should consume M_Reset result.
        unchecked_resets = _PouStructureHelpers._find_unchecked_reset_calls(file)
        if unchecked_resets:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="Logic",
                    message=(
                        "M_Reset call(s) ignored without checking return value: "
                        + ", ".join(unchecked_resets[:5])
                        + "."
                    ),
                    fix_available=False,
                    fix_suggestion=(
                        "Use IF ... M_Reset(...) THEN / ELSE or assign the result to drive "
                        "recovery transitions."
                    ),
                )
            )

        # Logic-safety warning: repeated reset loops can hide real runtime behavior.
        reset_spam_loops = _PouStructureHelpers._find_unconditional_reset_loops(file)
        if reset_spam_loops:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="Logic",
                    message=(
                        "Potential reset-spam loop detected: "
                        + ", ".join(reset_spam_loops[:5])
                        + "."
                    ),
                    fix_available=False,
                    fix_suggestion=(
                        "Gate M_Reset calls with explicit conditions/backoff/edges instead "
                        "of calling every scan in looped orchestration states."
                    ),
                )
            )

        # Logic-safety warning: hard-fault types should expose an explicit hard-reset path.
        if _PouStructureHelpers._has_hard_fault_pattern(
            file
        ) and _PouStructureHelpers._missing_hard_reset_api(file):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="Logic",
                    message=(
                        "Hard-fault pattern detected but no explicit hard-reset API was found "
                        "(e.g., auth-gated M_Reset input or dedicated M_ResetHard/M_AuthorizedReset)."
                    ),
                    fix_available=False,
                    fix_suggestion=(
                        "Add an explicit hard-reset contract path and gate invocation from PRG "
                        "with operator authorization."
                    ),
                )
            )

        return issues


@CheckRegistry.register
class MainVarInputMutationCheck(BaseCheck):
    """Detect assignments to POU-level VAR_INPUT symbols in main implementation ST."""

    check_id = "main_var_input_mutation"

    def should_skip(self, file: TwinCATFile) -> bool:
        return file.pou_subtype is None

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        mutations = _PouStructureHelpers._find_main_var_input_mutations(file)
        if not mutations:
            return []
        return [
            ValidationIssue(
                severity="error",
                category="Structure",
                message=(
                    "Assignments to POU VAR_INPUT symbol(s) in main implementation "
                    f"detected: {', '.join(mutations)}."
                ),
                fix_available=False,
                fix_suggestion=(
                    "Treat VAR_INPUT as read-only. Move one-shot/latched behavior "
                    "to internal VAR state."
                ),
            )
        ]


@CheckRegistry.register
class PouStructureInterfaceCheck(BaseCheck):
    """Check POU IMPLEMENTS interface contract compliance.

    Catches:
    - Missing interface definition (.TcIO) for IMPLEMENTS clause
    - Method signature mismatches against declared interface
    """

    check_id = "pou_structure_interface"

    def should_skip(self, file: TwinCATFile) -> bool:
        return file.pou_subtype is None

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        local_interfaces = set(_PouStructureHelpers._extract_implemented_interfaces(file))
        if not local_interfaces:
            return issues

        missing_interfaces, violations = collect_interface_contract_violations(
            file,
            interface_names=local_interfaces,
            include_inherited_interfaces=False,
        )

        for interface_name in missing_interfaces:
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="Structure",
                    message=f"POU implements interface '{interface_name}' but no matching "
                    "interface definition (.TcIO) was found nearby.",
                    fix_available=False,
                    fix_suggestion=f"Create interface file '{interface_name}.TcIO' or adjust "
                    "the IMPLEMENTS clause to an existing interface.",
                )
            )

        if violations:
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="Structure",
                    message=(
                        "POU method signature mismatch for interface contract(s): "
                        + ", ".join(violations)
                    ),
                    fix_available=False,
                    fix_suggestion=(
                        "Match METHOD signatures and property accessors/types to the "
                        ".TcIO interface definition (including inherited members)."
                    ),
                )
            )

        return issues


@CheckRegistry.register
class PouStructureSyntaxCheck(BaseCheck):
    """Conservative ST syntax guard for common compile-breakers.

    Catches:
    - Unmatched IF/END_IF, FOR/END_FOR, WHILE/END_WHILE, CASE/END_CASE, REPEAT/UNTIL
    - Missing semicolons on assignments and control statements
    """

    check_id = "pou_structure_syntax"

    def should_skip(self, file: TwinCATFile) -> bool:
        return file.pou_subtype is None

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        syntax_issues = _PouStructureHelpers._find_st_syntax_guard_issues(file)
        if syntax_issues:
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="Structure",
                    message="ST syntax guard detected potential compile-breakers: "
                    + "; ".join(sorted(set(syntax_issues))[:5]),
                    fix_available=False,
                    fix_suggestion=(
                        "Use autofix_file(format_profile='twincat_canonical') and "
                        "ensure ST statements/terminators end with ';'."
                    ),
                )
            )

        return issues


@CheckRegistry.register
class UnsignedLoopUnderflowCheck(BaseCheck):
    """Detect FOR-loop upper bounds like 'UINT_symbol - 1' that can underflow at 0."""

    check_id = "unsigned_loop_underflow"

    def should_skip(self, file: TwinCATFile) -> bool:
        return file.pou_subtype is None

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        loops = _PouStructureHelpers._find_unsigned_for_loop_underflow(file)
        if not loops:
            return []
        summarized = ", ".join(loops[:5])
        return [
            ValidationIssue(
                severity="error",
                category="Structure",
                message=(
                    "Potential unsigned FOR-loop underflow in upper bound "
                    f"(... TO unsigned_symbol - 1 ...): {summarized}."
                ),
                fix_available=False,
                fix_suggestion=(
                    "Guard zero case before loop or rewrite bounds to avoid "
                    "unsigned subtraction."
                ),
            )
        ]


@CheckRegistry.register
class PouStructureSubtypeCheck(BaseCheck):
    """Check POU subtype-specific constraints.

    Catches:
    - FUNCTION with Method/Property/Action elements
    - FUNCTION missing return type declaration
    - PROGRAM with Property elements (advisory warning)
    """

    check_id = "pou_structure_subtype"

    def should_skip(self, file: TwinCATFile) -> bool:
        return file.pou_subtype not in ("function", "program")

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        if file.pou_subtype == "function":
            method_count = len(re.findall(r"<Method\s+Name=", file.content))
            property_count = len(re.findall(r"<Property\s+Name=", file.content))
            action_count = len(re.findall(r"<Action\s+Name=", file.content))

            if method_count > 0:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="Structure",
                        message=f"FUNCTION contains {method_count} Method(s). "
                        "FUNCTIONs cannot have Methods in TwinCAT.",
                        fix_available=False,
                        fix_suggestion="Move methods to a FUNCTION_BLOCK or remove them",
                    )
                )
            if property_count > 0:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="Structure",
                        message=f"FUNCTION contains {property_count} Property/Properties. "
                        "FUNCTIONs cannot have Properties in TwinCAT.",
                        fix_available=False,
                        fix_suggestion="Move properties to a FUNCTION_BLOCK or remove them",
                    )
                )
            if action_count > 0:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="Structure",
                        message=f"FUNCTION contains {action_count} Action(s). "
                        "FUNCTIONs cannot have Actions in TwinCAT.",
                        fix_available=False,
                        fix_suggestion="Move actions to a FUNCTION_BLOCK or PROGRAM",
                    )
                )

            # Check for return type: FUNCTION Name : ReturnType
            declaration = _extract_pou_declaration_cdata(file.content)
            return_match = None
            if declaration is not None:
                significant_lines = _extract_declaration_significant_lines(declaration)
                normalized_declaration = "\n".join(significant_lines)
                return_match = re.search(
                    r"(?im)^\s*FUNCTION\s+\S+\s*:\s*\S+",
                    normalized_declaration,
                )
            if not return_match:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="Structure",
                        message="FUNCTION is missing a return type declaration "
                        "(expected 'FUNCTION Name : ReturnType')",
                        fix_available=False,
                        fix_suggestion="Add return type: FUNCTION FUNC_Name : INT",
                    )
                )

        elif file.pou_subtype == "program":
            property_count = len(re.findall(r"<Property\s+Name=", file.content))
            if property_count > 0:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        category="Structure",
                        message=f"PROGRAM contains {property_count} Property/Properties. "
                        "PROGRAMs typically should not have Properties.",
                        fix_available=False,
                        fix_suggestion="Consider using a FUNCTION_BLOCK instead",
                    )
                )

        return issues


class _PouStructureHelpers:
    """Internal helper methods used by focused POU structure sub-checks."""

    @staticmethod
    def _extract_implemented_interfaces(file: TwinCATFile) -> list[str]:
        """Extract interface names from POU declaration line with IMPLEMENTS."""
        declaration = _extract_pou_declaration_cdata(file.content)
        if declaration is None:
            return []

        significant_lines = _extract_declaration_significant_lines(declaration)
        if not significant_lines:
            return []

        header_line = significant_lines[0]
        implements_match = re.search(r"(?i)\bIMPLEMENTS\b\s+(.+?)(?=\bEXTENDS\b|$)", header_line)
        if not implements_match:
            return []

        raw_names = implements_match.group(1)
        interfaces = [name.strip() for name in raw_names.split(",") if name.strip()]
        return interfaces

    @staticmethod
    def _extract_extended_base(file: TwinCATFile) -> str | None:
        """Extract base FUNCTION_BLOCK name from EXTENDS clause."""
        declaration = _extract_pou_declaration_cdata(file.content)
        if declaration is None:
            return None

        significant_lines = _extract_declaration_significant_lines(declaration)
        if not significant_lines:
            return None

        header_line = significant_lines[0]
        extends_match = re.search(r"(?i)\bEXTENDS\b\s+([A-Za-z_][A-Za-z0-9_]*)", header_line)
        if not extends_match:
            return None
        return extends_match.group(1)

    @staticmethod
    def _interface_definition_exists(file: TwinCATFile, interface_name: str) -> bool:
        """Check whether interface definition exists in current or parent directories."""
        # Fast path: same folder conventional file name.
        same_dir = file.filepath.parent / f"{interface_name}.TcIO"
        if same_dir.exists():
            return True

        # Best-effort workspace scan: look for .TcIO declaring this interface name.
        search_roots = [file.filepath.parent]
        parent = file.filepath.parent.parent
        if parent != file.filepath.parent:
            search_roots.append(parent)

        name_fragment = f'Name="{interface_name}"'
        for root in search_roots:
            for path in root.rglob("*.TcIO"):
                try:
                    content = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                if "<Itf " in content and name_fragment in content:
                    return True
        return False

    @staticmethod
    def _resolve_interface_definition_path(file: TwinCATFile, interface_name: str) -> Path | None:
        """Resolve nearby interface definition path for IMPLEMENTS checks."""
        same_dir = file.filepath.parent / f"{interface_name}.TcIO"
        if same_dir.exists():
            return same_dir

        search_roots = [file.filepath.parent]
        parent = file.filepath.parent.parent
        if parent != file.filepath.parent:
            search_roots.append(parent)

        name_fragment = f'Name="{interface_name}"'
        for root in search_roots:
            for path in root.rglob("*.TcIO"):
                try:
                    content = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                if "<Itf " in content and name_fragment in content:
                    return path
        return None

    @staticmethod
    def _base_definition_exists(file: TwinCATFile, base_name: str) -> bool:
        """Check whether base FUNCTION_BLOCK definition exists nearby."""
        same_dir = file.filepath.parent / f"{base_name}.TcPOU"
        if same_dir.exists():
            return True

        search_roots = [file.filepath.parent]
        parent = file.filepath.parent.parent
        if parent != file.filepath.parent:
            search_roots.append(parent)

        name_fragment = f'Name="{base_name}"'
        for root in search_roots:
            for path in root.rglob("*.TcPOU"):
                try:
                    content = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                if "<POU " in content and name_fragment in content:
                    if re.search(r"(?im)\bFUNCTION_BLOCK\b", content):
                        return True
        return False

    @staticmethod
    def _find_illegal_method_in_main_implementation(file: TwinCATFile) -> bool:
        """Detect METHOD declarations written inside main POU implementation ST CDATA."""
        implementation_match = re.search(
            r"<POU\b[^>]*>.*?<Implementation>\s*<ST><!\[CDATA\[(.*?)\]\]></ST>\s*</Implementation>",
            file.content,
            re.DOTALL | re.IGNORECASE,
        )
        if not implementation_match:
            return False

        st_body = implementation_match.group(1)
        return bool(re.search(r"(?im)^\s*METHOD\s+[A-Za-z_][A-Za-z0-9_]*", st_body))

    @staticmethod
    def _find_main_impl_var_block(file: TwinCATFile) -> bool:
        """Detect illegal VAR...END_VAR declarations in main implementation ST body."""
        st_body = _PouStructureHelpers._extract_main_implementation_st(file)
        if not st_body:
            return False
        return bool(re.search(r"(?im)^\s*VAR(?:_INPUT|_OUTPUT|_IN_OUT|_TEMP)?\b", st_body))

    @staticmethod
    def _find_method_impl_var_block_issues(file: TwinCATFile) -> list[str]:
        """Detect illegal VAR...END_VAR declaration blocks inside method implementation ST."""
        issues: list[str] = []
        for (
            method_name,
            _decl,
            st_body,
            has_implementation,
        ) in _PouStructureHelpers._iter_method_blocks(file):
            if not has_implementation:
                continue
            if re.search(r"(?im)^\s*VAR(?:_INPUT|_OUTPUT|_IN_OUT|_TEMP)?\b", st_body):
                issues.append(method_name)
        return issues

    @staticmethod
    def _find_inline_struct_in_pou_declaration(file: TwinCATFile) -> bool:
        """Detect inline STRUCT declarations inside POU VAR declarations."""
        declaration = _extract_pou_declaration_cdata(file.content)
        if declaration is None:
            return False
        return bool(re.search(r"(?im)\bOF\s+STRUCT\b|\:\s*STRUCT\b", declaration))

    @staticmethod
    def _find_inline_type_in_pou_declaration(file: TwinCATFile) -> bool:
        """Detect inline TYPE blocks in POU declarations."""
        declaration = _extract_pou_declaration_cdata(file.content)
        if declaration is None:
            return False
        return bool(re.search(r"(?is)\bTYPE\b.*?\bEND_TYPE\b", declaration))

    @staticmethod
    def _find_const_block_in_pou_declaration(file: TwinCATFile) -> bool:
        """Detect CONST...END_CONST blocks in POU declarations."""
        declaration = _extract_pou_declaration_cdata(file.content)
        if declaration is None:
            return False
        return bool(
            re.search(r"(?im)^\s*CONST\s*$", declaration)
            and re.search(r"(?im)^\s*END_CONST\s*$", declaration)
        )

    @staticmethod
    def _find_var_temp_in_pou_declaration(file: TwinCATFile) -> bool:
        """Detect VAR_TEMP blocks in top-level POU declarations."""
        declaration = _extract_pou_declaration_cdata(file.content)
        if declaration is None:
            return False
        return bool(re.search(r"(?im)^\s*VAR_TEMP\b", declaration))

    @staticmethod
    def _find_var_protected_in_pou_declaration(file: TwinCATFile) -> bool:
        """Detect invalid VAR PROTECTED / VAR_PROTECTED block in POU declarations.

        Matches both the space form (VAR PROTECTED) and the underscore form (VAR_PROTECTED).
        """
        declaration = _extract_pou_declaration_cdata(file.content)
        if declaration is None:
            return False
        # Space form: "VAR PROTECTED" (most common hallucination)
        if re.search(r"(?im)^\s*VAR\s+PROTECTED\b", declaration):
            return True
        # Underscore form: "VAR_PROTECTED" (alternate hallucination spelling)
        if re.search(r"(?im)^\s*VAR_PROTECTED\b", declaration):
            return True
        return False

    @staticmethod
    def _is_misfiled_interface_in_tcpou(file: TwinCATFile) -> bool:
        """Detect INTERFACE declarations incorrectly stored in .TcPOU files."""
        if file.suffix != ".TcPOU":
            return False
        declaration = _extract_pou_declaration_cdata(file.content)
        if declaration is None:
            return False
        significant_lines = _extract_declaration_significant_lines(declaration)
        if not significant_lines:
            return False
        return significant_lines[0].strip().upper().startswith("INTERFACE ")

    @staticmethod
    def _extract_declared_symbols_from_declaration(declaration: str) -> set[str]:
        """Extract symbol names declared in METHOD/VAR blocks."""
        symbols: set[str] = set()
        lines = declaration.splitlines()
        if lines:
            first = lines[0].strip()
            method_match = re.match(
                r"(?i)^METHOD(?:\s+(?:PUBLIC|PROTECTED|PRIVATE|ABSTRACT|OVERRIDE))*\s+([A-Za-z_][A-Za-z0-9_]*)",
                first,
            )
            if method_match:
                symbols.add(method_match.group(1))

        in_var_block = False
        for raw in lines:
            line = raw.strip()
            if re.match(r"(?i)^VAR(?:_INPUT|_OUTPUT|_IN_OUT|_TEMP)?\b", line):
                in_var_block = True
                continue
            if line.upper() == "END_VAR":
                in_var_block = False
                continue
            if not in_var_block:
                continue
            var_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:", line)
            if var_match:
                symbols.add(var_match.group(1))
        return symbols

    @staticmethod
    def _collect_pou_symbols(file: TwinCATFile) -> set[str]:
        """Collect symbols declared in the main POU declaration VAR blocks."""
        declaration = _extract_pou_declaration_cdata(file.content)
        if declaration is None:
            return set()
        return _PouStructureHelpers._extract_declared_symbols_from_declaration(declaration)

    @staticmethod
    def _extract_pou_var_input_symbols(file: TwinCATFile) -> set[str]:
        """Extract POU-level VAR_INPUT symbols from the POU declaration block."""
        declaration = _extract_pou_declaration_cdata(file.content)
        if declaration is None:
            return set()

        symbols: set[str] = set()
        in_var_input = False
        for raw in declaration.splitlines():
            line = raw.strip()
            if re.match(r"(?i)^VAR_INPUT\b", line):
                in_var_input = True
                continue
            if line.upper() == "END_VAR":
                in_var_input = False
                continue
            if not in_var_input:
                continue
            vm = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:", line)
            if vm:
                symbols.add(vm.group(1))
        return symbols

    @staticmethod
    def _extract_main_implementation_st(file: TwinCATFile) -> str:
        """Extract POU main implementation ST body (excluding method implementations)."""
        implementation_match = re.search(
            r"<POU\b[^>]*>.*?<Implementation>\s*<ST><!\[CDATA\[(.*?)\]\]></ST>\s*</Implementation>",
            file.content,
            re.DOTALL | re.IGNORECASE,
        )
        if not implementation_match:
            return ""
        return implementation_match.group(1)

    @staticmethod
    def _find_main_var_input_mutations(file: TwinCATFile) -> list[str]:
        """Detect assignments to POU VAR_INPUT symbols in main implementation."""
        var_inputs = _PouStructureHelpers._extract_pou_var_input_symbols(file)
        if not var_inputs:
            return []

        st_body = _PouStructureHelpers._extract_main_implementation_st(file)
        if not st_body:
            return []

        mutated: list[str] = []
        for symbol in sorted(var_inputs):
            if re.search(rf"(?im)^\s*{re.escape(symbol)}\s*:=", st_body):
                mutated.append(symbol)
        return mutated

    @staticmethod
    def _extract_interface_array_symbols(file: TwinCATFile) -> list[str]:
        """Collect POU symbols declared as ARRAY[...] OF I_* interface references."""
        declaration = _extract_pou_declaration_cdata(file.content)
        if declaration is None:
            return []
        names: list[str] = []
        for match in re.finditer(
            r"(?im)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*ARRAY\s*\[[^\]]+\]\s+OF\s+(?:REFERENCE\s+TO\s+)?(I_[A-Za-z_][A-Za-z0-9_]*)\b",
            declaration,
        ):
            _ = match.group(2)
            names.append(match.group(1))
        return names

    @staticmethod
    def _find_unbound_interface_array_usage(file: TwinCATFile) -> list[str]:
        """Find interface arrays used via index/member access without any detected binding."""
        arrays = _PouStructureHelpers._extract_interface_array_symbols(file)
        if not arrays:
            return []

        st_body = _PouStructureHelpers._extract_main_implementation_st(file)
        if not st_body:
            return []

        offenders: list[str] = []
        for name in arrays:
            used = bool(re.search(rf"(?is)\b{re.escape(name)}\s*\[[^\]]+\]\s*\.", st_body))
            if not used:
                continue
            bound_anywhere = bool(
                re.search(rf"(?is)\b{re.escape(name)}\s*\[[^\]]+\]\s*(?::=|REF=)", file.content)
            )
            if not bound_anywhere:
                offenders.append(name)
        return offenders

    @staticmethod
    def _extract_var_input_symbols_from_declaration(declaration: str) -> set[str]:
        """Extract method VAR_INPUT symbol names from a method declaration block."""
        symbols: set[str] = set()
        in_var_input = False
        for raw in declaration.splitlines():
            line = raw.strip()
            if re.match(r"(?i)^VAR_INPUT\b", line):
                in_var_input = True
                continue
            if line.upper() == "END_VAR":
                in_var_input = False
                continue
            if not in_var_input:
                continue
            vm = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:", line)
            if vm:
                symbols.add(vm.group(1))
        return symbols

    @staticmethod
    def _has_hard_fault_pattern(file: TwinCATFile) -> bool:
        """Best-effort detector for hard-fault semantics in ST code."""
        hard_setfault = re.search(
            r"(?is)\bM_SetFault\s*\(\s*[^)]*\bbHard\s*:=\s*TRUE\b",
            file.content,
        )
        hard_latch_name = re.search(
            r"(?im)\bHardFault|OverTempLatch|ThermalLatch|Latch\b", file.content
        )
        return bool(hard_setfault or hard_latch_name)

    @staticmethod
    def _find_reset_clears_fault_without_auth(file: TwinCATFile) -> list[str]:
        """Find reset methods that clear faults without any auth-gating input."""
        if not _PouStructureHelpers._has_hard_fault_pattern(file):
            return []

        offenders: list[str] = []
        for (
            method_name,
            declaration,
            st_body,
            has_implementation,
        ) in _PouStructureHelpers._iter_method_blocks(file):
            if not has_implementation:
                continue
            if method_name.upper() != "M_RESET":
                continue

            inputs = _PouStructureHelpers._extract_var_input_symbols_from_declaration(declaration)
            has_auth_input = any(
                token in name.upper()
                for name in inputs
                for token in ("AUTH", "AUTHOR", "PERMIT", "ALLOW", "CONFIRM")
            )
            clears_fault = bool(
                re.search(r"(?is)\b(?:THIS\^\.)?M_ClearFault\s*\(", st_body)
                or re.search(r"(?im)\b(?:THIS\^\.)?bFault\s*:=\s*FALSE\s*;", st_body)
            )
            if clears_fault and not has_auth_input:
                offenders.append(method_name)
        return offenders

    @staticmethod
    def _find_unchecked_reset_calls(file: TwinCATFile) -> list[str]:
        """Find M_Reset invocations where result is ignored."""
        offenders: list[str] = []
        for context, st_body in _PouStructureHelpers._iter_st_blocks_with_context(file):
            for raw in st_body.splitlines():
                line = re.sub(r"//.*$", "", raw).strip()
                if not line:
                    continue
                if not re.search(r"\bM_Reset\s*\(", line):
                    continue
                if ":=" in line:
                    continue
                if re.match(r"(?i)^(IF|ELSIF|WHILE)\b", line):
                    continue
                if not line.endswith(";"):
                    continue
                offenders.append(f"{context}: {line}")
        return offenders

    @staticmethod
    def _find_unconditional_reset_loops(file: TwinCATFile) -> list[str]:
        """Find FOR loops that invoke M_Reset in loop body without effective guard."""
        offenders: list[str] = []
        for context, st_body in _PouStructureHelpers._iter_st_blocks_with_context(file):
            for loop in re.finditer(r"(?is)\bFOR\b.*?\bDO\b(.*?)\bEND_FOR\s*;", st_body):
                body = loop.group(1)
                if not re.search(r"(?is)\bM_Reset\s*\(", body):
                    continue
                # Local guard inside loop body.
                if re.search(r"(?is)\bIF\b", body):
                    continue
                # Parent guard around the loop (edge/backoff/auth/allow style gate).
                if _PouStructureHelpers._loop_has_parent_reset_guard(
                    st_body, loop.start(), loop.end()
                ):
                    continue
                offenders.append(f"{context}: FOR..END_FOR with M_Reset()")
        return offenders

    @staticmethod
    def _loop_has_parent_reset_guard(st_body: str, loop_start: int, loop_end: int) -> bool:
        """Return True when loop is enclosed by an explicit parent reset-gating IF block."""
        if_pattern = re.compile(r"(?is)\bIF\b(.*?)\bTHEN\b(.*?)\bEND_IF\s*;")
        for if_match in if_pattern.finditer(st_body):
            if if_match.start() > loop_start or if_match.end() < loop_end:
                continue
            cond = (if_match.group(1) or "").strip()
            if _PouStructureHelpers._is_reset_guard_condition(cond):
                return True
        return False

    @staticmethod
    def _is_reset_guard_condition(cond: str) -> bool:
        """Heuristic for explicit reset gating conditions (edge/backoff/auth/allow/retry)."""
        if not cond:
            return False
        upper = cond.upper()
        if " AND NOT " in upper:
            return True
        tokens = (
            "EDGE",
            "BACKOFF",
            "AUTH",
            "AUTHOR",
            "ALLOW",
            "PERMIT",
            "RETRY",
            "GATE",
            "LATCH",
            "TRIGGER",
            "ONESHOT",
            "ONE_SHOT",
            "R_TRIG",
            "F_TRIG",
        )
        return any(token in upper for token in tokens)

    @staticmethod
    def _missing_hard_reset_api(file: TwinCATFile) -> bool:
        """Detect absence of explicit hard-reset contract when hard-fault logic exists."""
        method_names = re.findall(r'(?is)<Method\s+Name="([^"]+)"', file.content)
        if not method_names:
            return False

        reset_like = [name for name in method_names if "RESET" in name.upper()]
        if not reset_like:
            return True

        if any(("HARD" in name.upper() or "AUTH" in name.upper()) for name in reset_like):
            return False

        # If only M_Reset exists, allow it only when auth input is explicit.
        m = re.search(
            r'(?is)<Method\s+Name="M_Reset"[^>]*>\s*<Declaration><!\[CDATA\[(.*?)\]\]></Declaration>',
            file.content,
        )
        if not m:
            return True
        inputs = _PouStructureHelpers._extract_var_input_symbols_from_declaration(m.group(1))
        return not any("AUTH" in name.upper() for name in inputs)

    @staticmethod
    def _extract_unsigned_declared_symbols(file: TwinCATFile) -> set[str]:
        """Extract declared symbols with unsigned integer scalar type from POU declaration."""
        declaration = _extract_pou_declaration_cdata(file.content)
        if declaration is None:
            return set()

        unsigned = {"USINT", "UINT", "UDINT", "ULINT"}
        symbols: set[str] = set()
        for raw in declaration.splitlines():
            line = raw.strip()
            if not line or line.startswith("//") or line.startswith("{"):
                continue
            vm = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^;]+);?$", line)
            if not vm:
                continue
            symbol = vm.group(1)
            type_expr = vm.group(2).split(":=", 1)[0].strip()
            array_match = re.match(r"(?i)^ARRAY\s*\[[^\]]+\]\s+OF\s+(.+)$", type_expr)
            if array_match:
                type_expr = array_match.group(1).strip()
            type_token = re.split(r"\s+", type_expr, maxsplit=1)[0].upper()
            if type_token in unsigned:
                symbols.add(symbol)
        return symbols

    @staticmethod
    def _iter_st_blocks_with_context(file: TwinCATFile) -> list[tuple[str, str]]:
        """Iterate ST code blocks with context labels."""
        blocks: list[tuple[str, str]] = []

        main_st = _PouStructureHelpers._extract_main_implementation_st(file)
        if main_st:
            blocks.append(("POU", main_st))

        for (
            method_name,
            _decl,
            st_body,
            has_implementation,
        ) in _PouStructureHelpers._iter_method_blocks(file):
            if has_implementation:
                blocks.append((f"METHOD {method_name}", st_body))

        return blocks

    @staticmethod
    def _find_unsigned_for_loop_underflow(file: TwinCATFile) -> list[str]:
        """Find loops with upper bound 'unsigned_symbol - 1' in ST blocks."""
        unsigned_symbols = _PouStructureHelpers._extract_unsigned_declared_symbols(file)
        if not unsigned_symbols:
            return []

        issues: list[str] = []
        guarded_if_pattern = re.compile(
            r"(?is)\bIF\s+\(?\s*(?:THIS\^\.)?([A-Za-z_][A-Za-z0-9_]*)\s*"
            r"(?:>|<>|>=)\s*0\s*\)?\s+THEN\b(.*?)\bEND_IF\s*;",
        )
        pattern = re.compile(
            r"(?im)^\s*FOR\s+([A-Za-z_][A-Za-z0-9_]*)\s*:=\s*0\s+TO\s+\(?\s*"
            r"(?:THIS\^\.)?([A-Za-z_][A-Za-z0-9_]*)\s*-\s*1\s*\)?\s+DO\b"
        )
        for context, st_body in _PouStructureHelpers._iter_st_blocks_with_context(file):
            guarded_ranges: list[tuple[int, int, str]] = []
            for guarded in guarded_if_pattern.finditer(st_body):
                guard_symbol = guarded.group(1)
                if guard_symbol not in unsigned_symbols:
                    continue
                body_start = guarded.start(2)
                body_end = guarded.end(2)
                guarded_ranges.append((body_start, body_end, guard_symbol))

            for match in pattern.finditer(st_body):
                loop_var = match.group(1)
                bound_symbol = match.group(2)
                if bound_symbol in unsigned_symbols:
                    loop_pos = match.start()
                    if any(
                        start <= loop_pos <= end and symbol == bound_symbol
                        for start, end, symbol in guarded_ranges
                    ):
                        continue
                    issues.append(f"{context}: FOR {loop_var} TO {bound_symbol} - 1")
        return issues

    @staticmethod
    def _find_invalid_return_value_statements(file: TwinCATFile) -> list[str]:
        """Detect invalid ST usage like `RETURN FALSE;` in method implementations."""
        invalid_methods: list[str] = []
        for (
            method_name,
            _decl,
            st_body,
            has_implementation,
        ) in _PouStructureHelpers._iter_method_blocks(file):
            if not has_implementation:
                continue
            if re.search(r"(?im)^\s*RETURN\s+[^;\s][^;]*;", st_body):
                invalid_methods.append(method_name)
        return invalid_methods

    @staticmethod
    def _find_var_input_mutations(file: TwinCATFile) -> list[tuple[str, str]]:
        """Detect assignments to METHOD VAR_INPUT parameters."""
        mutations: list[tuple[str, str]] = []
        for (
            method_name,
            declaration,
            st_body,
            has_implementation,
        ) in _PouStructureHelpers._iter_method_blocks(file):
            if not has_implementation:
                continue

            var_inputs: set[str] = set()
            in_var_input = False
            for raw in declaration.splitlines():
                line = raw.strip()
                if re.match(r"(?i)^VAR_INPUT\b", line):
                    in_var_input = True
                    continue
                if line.upper() == "END_VAR":
                    in_var_input = False
                    continue
                if not in_var_input:
                    continue
                var_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:", line)
                if var_match:
                    var_inputs.add(var_match.group(1))

            if not var_inputs:
                continue
            for input_name in var_inputs:
                assign_pattern = rf"(?im)^\s*{re.escape(input_name)}\s*:="
                if re.search(assign_pattern, st_body):
                    mutations.append((method_name, input_name))
        return mutations

    @staticmethod
    def _find_undeclared_method_assignments(file: TwinCATFile) -> list[tuple[str, str]]:
        """Detect assignments to undeclared method-local symbols."""
        issues: list[tuple[str, str]] = []
        pou_symbols = _PouStructureHelpers._collect_pou_symbols(file)
        for (
            method_name,
            declaration,
            st_body,
            has_implementation,
        ) in _PouStructureHelpers._iter_method_blocks(file):
            if not has_implementation:
                continue

            method_symbols = _PouStructureHelpers._extract_declared_symbols_from_declaration(
                declaration
            )
            declared_symbols = pou_symbols.union(method_symbols)
            declared_symbols.add(method_name)

            assigned_symbols: set[str] = set()
            for assign in re.finditer(r"(?im)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:=", st_body):
                assigned_symbols.add(assign.group(1))
            for for_loop in re.finditer(r"(?im)^\s*FOR\s+([A-Za-z_][A-Za-z0-9_]*)\s*:=", st_body):
                assigned_symbols.add(for_loop.group(1))

            for symbol in sorted(assigned_symbols):
                if symbol not in declared_symbols:
                    issues.append((method_name, symbol))
        return issues

    @staticmethod
    def _find_method_declaration_var_temp_issues(file: TwinCATFile) -> list[str]:
        """Detect VAR_TEMP blocks in method declarations."""
        issues: list[str] = []
        for (
            method_name,
            declaration,
            _st_body,
            _has_implementation,
        ) in _PouStructureHelpers._iter_method_blocks(file):
            if re.search(r"(?im)^\s*VAR_TEMP\b", declaration):
                issues.append(method_name)
        return issues

    @staticmethod
    def _iter_method_blocks(file: TwinCATFile) -> list[tuple[str, str, str, bool]]:
        """Iterate method blocks as isolated units to avoid cross-method regex leakage.

        Returns:
            List of tuples:
            (method_name, declaration_cdata, implementation_st_cdata, has_implementation)
        """
        methods: list[tuple[str, str, str, bool]] = []
        method_block_pattern = re.compile(r"(?is)<Method\b([^>]*)>(.*?)</Method>")
        for m in method_block_pattern.finditer(file.content):
            attrs = m.group(1) or ""
            body = m.group(2) or ""
            name_match = re.search(r'(?i)\bName="([^"]+)"', attrs)
            if not name_match:
                continue
            method_name = name_match.group(1)
            decl_match = re.search(
                r"(?is)<Declaration><!\[CDATA\[(.*?)\]\]></Declaration>",
                body,
            )
            declaration = (decl_match.group(1) if decl_match else "").strip("\n")
            impl_match = re.search(
                r"(?is)<Implementation>\s*<ST><!\[CDATA\[(.*?)\]\]></ST>\s*</Implementation>",
                body,
            )
            if impl_match:
                methods.append((method_name, declaration, impl_match.group(1), True))
            else:
                methods.append((method_name, declaration, "", False))
        return methods

    @staticmethod
    def _parse_method_signature_from_declaration(
        declaration: str,
    ) -> tuple[str, list[tuple[str, str]]]:
        """Parse return type and ordered VAR_INPUT entries from METHOD declaration text."""
        text = declaration.replace("\r\n", "\n")
        text = _PouStructureHelpers._strip_declaration_comments(text)
        lines = [ln.rstrip() for ln in text.split("\n")]
        header = ""
        header_index = -1
        for idx, raw in enumerate(lines):
            stripped = raw.strip()
            if (
                not stripped
                or stripped.startswith("{")
                or stripped.startswith("//")
                or stripped.startswith("(*")
            ):
                continue
            if re.match(r"(?i)^METHOD\b", stripped):
                header = stripped
                header_index = idx
                break
        if not header:
            return "", []
        return_type = ""
        m = re.match(
            r"(?i)^METHOD(?:\s+(?:PUBLIC|PROTECTED|PRIVATE|ABSTRACT|OVERRIDE))*\s+[A-Za-z_][A-Za-z0-9_]*\s*:\s*(.+)$",
            header,
        )
        if m:
            return_type = _PouStructureHelpers._normalize_signature_type(m.group(1))

        var_inputs: list[tuple[str, str]] = []
        in_var_input = False
        for raw in lines[header_index + 1 :]:
            line = raw.strip()
            if re.match(r"(?i)^VAR_INPUT\b", line):
                in_var_input = True
                continue
            if line.upper() == "END_VAR":
                in_var_input = False
                continue
            if not in_var_input:
                continue
            vm = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^;]+);?$", line)
            if vm:
                var_inputs.append(
                    (
                        vm.group(1).strip(),
                        _PouStructureHelpers._normalize_signature_type(vm.group(2)),
                    )
                )
        return return_type, var_inputs

    @staticmethod
    def _strip_declaration_comments(text: str) -> str:
        """Remove line and block comments from declaration text."""
        # Remove block comments first because they can span lines.
        out = re.sub(r"(?is)\(\*.*?\*\)", "", text)
        # Remove line comments.
        out = re.sub(r"(?m)//.*$", "", out)
        return out

    @staticmethod
    def _normalize_signature_type(type_expr: str) -> str:
        """Canonicalize type expressions for signature comparison."""
        normalized = type_expr.strip().rstrip(";")
        normalized = re.sub(r"\s+", " ", normalized)
        # Normalize spacing around punctuation.
        normalized = re.sub(r"\s*:\s*", ":", normalized)
        normalized = re.sub(r"\s*,\s*", ",", normalized)
        normalized = re.sub(r"\s*\[\s*", "[", normalized)
        normalized = re.sub(r"\s*\]\s*", "]", normalized)
        normalized = re.sub(r"\s*\(\s*", "(", normalized)
        normalized = re.sub(r"\s*\)\s*", ")", normalized)
        return normalized.upper()

    @staticmethod
    def _collect_tcio_method_signatures(path: Path) -> dict[str, tuple[str, list[tuple[str, str]]]]:
        """Collect interface method signatures from a .TcIO file."""
        signatures: dict[str, tuple[str, list[tuple[str, str]]]] = {}
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return signatures

        for match in re.finditer(
            r'(?is)<Method\s+Name="([^"]+)"[^>]*>\s*<Declaration><!\[CDATA\[(.*?)\]\]></Declaration>',
            content,
        ):
            method_name = match.group(1)
            declaration = match.group(2).strip("\n")
            signatures[method_name] = _PouStructureHelpers._parse_method_signature_from_declaration(
                declaration
            )
        return signatures

    @staticmethod
    def _collect_tcpou_method_signatures(
        file: TwinCATFile,
    ) -> dict[str, tuple[str, list[tuple[str, str]]]]:
        """Collect method signatures from a .TcPOU file."""
        signatures: dict[str, tuple[str, list[tuple[str, str]]]] = {}
        for (
            method_name,
            declaration,
            _st_body,
            _has_implementation,
        ) in _PouStructureHelpers._iter_method_blocks(file):
            signatures[method_name] = _PouStructureHelpers._parse_method_signature_from_declaration(
                declaration
            )
        return signatures

    @staticmethod
    def _find_st_syntax_guard_issues(file: TwinCATFile) -> list[str]:
        """Conservative ST syntax guard checks for common compile-breakers."""
        issues: list[str] = []
        st_blocks = re.findall(r"(?is)<ST><!\[CDATA\[(.*?)\]\]></ST>", file.content)

        def _strip_comments_and_strings(st_text: str) -> str:
            """Remove comments and string literals to reduce token false positives."""
            text = st_text
            # Remove block comments first (can span lines).
            text = re.sub(r"(?is)\(\*.*?\*\)", "", text)
            # Remove single-quoted string literals (TwinCAT ST).
            text = re.sub(r"'(?:''|[^'])*'", "''", text)
            # Remove line comments.
            text = re.sub(r"(?m)//.*$", "", text)
            return text

        token_pattern = re.compile(
            r"(?i)\b(END_IF|END_FOR|END_WHILE|END_CASE|UNTIL|IF|FOR|WHILE|CASE|REPEAT)\b"
        )
        opener_for_closer = {
            "END_IF": "IF",
            "END_FOR": "FOR",
            "END_WHILE": "WHILE",
            "END_CASE": "CASE",
            "UNTIL": "REPEAT",
        }

        for st in st_blocks:
            normalized = st.replace("\r\n", "\n")
            semantic = _strip_comments_and_strings(normalized)
            stack: list[str] = []
            for token_match in token_pattern.finditer(semantic):
                token = token_match.group(1).upper()
                if token in ("IF", "FOR", "WHILE", "CASE", "REPEAT"):
                    stack.append(token)
                    continue
                expected_opener = opener_for_closer[token]
                if not stack or stack[-1] != expected_opener:
                    issues.append(f"Unmatched {expected_opener}/{token}")
                    continue
                stack.pop()

            while stack:
                opener = stack.pop()
                closer = {
                    "IF": "END_IF",
                    "FOR": "END_FOR",
                    "WHILE": "END_WHILE",
                    "CASE": "END_CASE",
                    "REPEAT": "UNTIL",
                }[opener]
                issues.append(f"Unmatched {opener}/{closer}")

            for raw in normalized.split("\n"):
                # Ignore trailing comments for semicolon checks.
                candidate = re.sub(r"//.*$", "", raw)
                candidate = re.sub(r"\(\*.*?\*\)\s*$", "", candidate).strip()
                line = candidate
                if not line or line.startswith("//") or line.startswith("(*"):
                    continue
                if line.endswith(";"):
                    continue
                if re.search(r"(?i)(\(|,|\+|-|\*|/|\bAND\b|\bOR\b|\bXOR\b)\s*$", line):
                    continue
                if re.search(r"(?i)\b(THEN|DO|ELSE|CASE|OF|REPEAT)\s*$", line):
                    continue
                if line.upper().startswith(("VAR", "END_VAR")):
                    continue
                if ":=" in line:
                    issues.append(f"Missing semicolon after assignment: '{line}'")
                    continue
                if re.match(r"(?i)^(RETURN|EXIT|CONTINUE)\b", line):
                    issues.append(f"Missing semicolon on control statement: '{line}'")
                    continue
                # Do not enforce semicolons on block terminators (END_IF/END_FOR/...).
                # TwinCAT accepts terminators with or without ';', and enforcing this
                # creates noisy false positives for otherwise valid ST.
                if re.match(r"(?i)^END_(IF|FOR|WHILE|REPEAT|CASE)\b", line):
                    continue
        return issues

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        """Aggregate results from all focused POU structure sub-checks.

        Delegates to the five focused sub-checks (WS4 decomposition) and
        returns a combined issue list. Callers using the legacy 'pou_structure'
        check ID continue to receive the same full result set.

        Args:
            file: TwinCATFile to validate

        Returns:
            Combined list of ValidationIssue objects from all sub-checks.
        """
        sub_checks = [
            PouStructureHeaderCheck(),
            PouStructureMethodsCheck(),
            PouStructureInterfaceCheck(),
            PouStructureSyntaxCheck(),
            PouStructureSubtypeCheck(),
        ]
        issues: list[ValidationIssue] = []
        for sub_check in sub_checks:
            if not sub_check.should_skip(file):
                issues.extend(sub_check.run(file))
        return issues


@CheckRegistry.register
class PouStructureCheck(BaseCheck):
    """Backward-compatible umbrella check for legacy check_id='pou_structure'."""

    check_id = "pou_structure"

    def should_skip(self, file: TwinCATFile) -> bool:
        return file.pou_subtype is None

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        sub_checks = [
            PouStructureHeaderCheck(),
            PouStructureMethodsCheck(),
            PouStructureInterfaceCheck(),
            PouStructureSyntaxCheck(),
            PouStructureSubtypeCheck(),
        ]
        issues: list[ValidationIssue] = []
        for sub_check in sub_checks:
            if not sub_check.should_skip(file):
                issues.extend(sub_check.run(file))
        return issues
