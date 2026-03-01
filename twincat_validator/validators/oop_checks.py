"""OOP-focused TwinCAT validation checks."""

from __future__ import annotations

from pathlib import Path
import re

from .base import BaseCheck, CheckRegistry
from ..config_loader import get_shared_config
from ..models import ValidationIssue
from ..file_handler import TwinCATFile
from ..oop_index import (
    MethodSymbol,
    PropertySymbol,
    parse_interface_symbol,
    parse_pou_symbol,
    resolve_nearby_symbol_file,
    _strip_st_comments_and_strings,
)


def _pou_subtype(file: TwinCATFile) -> str | None:
    """Return the POU subtype string or None for non-TcPOU files.

    Delegates to the shared utility so detection logic stays in one place.
    """
    from ..utils import detect_pou_subtype  # local import to avoid circular dep

    return detect_pou_subtype(file)


def _file_has_oop_keywords(file: TwinCATFile) -> bool:
    """Return True if the POU declaration block contains EXTENDS or IMPLEMENTS.

    Uses the shared ``_extract_pou_declaration_cdata`` extractor which anchors
    on ``<POU ...>`` before matching the ``<Declaration>`` block.  This is more
    robust than a bare ``<Declaration>`` regex, which could match method-level
    declaration blocks and is sensitive to surrounding whitespace variations.

    Only the top-level POU declaration is scanned — not method bodies — to
    avoid false positives from comments or string literals.

    Used by should_skip() to avoid running inheritance/interface checks on
    plain FUNCTION_BLOCK / PROGRAM / FUNCTION files that never use OOP.
    """
    from ..utils import _extract_pou_declaration_cdata  # local import, same module

    decl = _extract_pou_declaration_cdata(file.content)
    if not decl:
        return False
    return bool(re.search(r"\b(?:EXTENDS|IMPLEMENTS)\b", decl, re.IGNORECASE))


def _summarize(items: list[str], limit: int = 4) -> str:
    unique = sorted(set(items))
    if len(unique) <= limit:
        return ", ".join(unique)
    return ", ".join(unique[:limit]) + f" (+{len(unique) - limit} more)"


def _get_oop_policy(file_path: Path) -> dict:
    """Resolve merged OOP policy from global defaults + project override."""
    return get_shared_config().get_oop_policy(file_path)


def _collect_direct_descendants(file: TwinCATFile, base_name: str) -> list[str]:
    """Collect direct sibling FUNCTION_BLOCK descendants for a base class name."""
    descendants: list[str] = []
    for candidate in sorted(file.filepath.parent.glob("*.TcPOU")):
        try:
            symbol = parse_pou_symbol(TwinCATFile(candidate))
        except Exception:
            symbol = None
        if symbol is None:
            continue
        if symbol.extends == base_name:
            descendants.append(symbol.name)
    return descendants


def _find_matching_interfaces_for_abstract_methods(file: TwinCATFile, pou) -> list[str]:
    """Find nearby interfaces whose method contracts fully match local abstract methods."""
    abstract_methods = {name: method for name, method in pou.methods.items() if method.is_abstract}
    if not abstract_methods:
        return []

    matches: list[str] = []
    for candidate in sorted(file.filepath.parent.glob("*.TcIO")):
        itf = parse_interface_symbol(candidate)
        if itf is None or not itf.methods:
            continue

        all_methods_match = True
        for method_name, itf_method in itf.methods.items():
            local_method = abstract_methods.get(method_name)
            if local_method is None or local_method.signature_key() != itf_method.signature_key():
                all_methods_match = False
                break

        if all_methods_match:
            matches.append(itf.name)
    return matches


def _collect_base_chain(file: TwinCATFile, start_base: str) -> tuple[list, str | None]:
    """Collect base symbol chain and detect cycles.

    Returns:
        (base_symbols, cycle_repr_or_none)
    """
    chain = []
    seen: list[str] = []
    current = start_base
    while current:
        if current in seen:
            idx = seen.index(current)
            cycle = seen[idx:] + [current]
            return chain, " -> ".join(cycle)
        seen.append(current)
        base_path = resolve_nearby_symbol_file(file.filepath, current, ".TcPOU")
        if not base_path:
            return chain, None
        base_symbol = parse_pou_symbol(TwinCATFile(base_path))
        if base_symbol is None:
            return chain, None
        chain.append(base_symbol)
        current = base_symbol.extends or ""
    return chain, None


def _collect_effective_interface_context(
    file: TwinCATFile,
) -> tuple[object | None, dict[str, MethodSymbol], dict[str, PropertySymbol], set[str]]:
    """Collect effective methods/properties and inherited interfaces for a POU."""
    pou = parse_pou_symbol(file)
    if pou is None:
        return None, {}, {}, set()

    chain, _ = _collect_base_chain(file, pou.extends or "")
    effective_methods: dict[str, MethodSymbol] = {}
    effective_properties: dict[str, PropertySymbol] = {}
    inherited_interfaces: set[str] = set()

    # Root-first merge so nearest/derived declarations override older base declarations.
    for symbol in reversed(chain):
        effective_methods.update(symbol.methods)
        effective_properties.update(symbol.properties)
        inherited_interfaces.update(symbol.implements)

    effective_methods.update(pou.methods)
    effective_properties.update(pou.properties)
    return pou, effective_methods, effective_properties, inherited_interfaces


def _check_interface_contract_violations(
    interface_path: Path,
    effective_methods: dict[str, MethodSymbol],
    effective_properties: dict[str, PropertySymbol],
) -> list[str]:
    """Return normalized interface contract violation fragments for one .TcIO file."""
    issues: list[str] = []
    itf = parse_interface_symbol(interface_path)
    if itf is None:
        return issues

    for method_name, itf_method in itf.methods.items():
        if method_name not in effective_methods:
            issues.append(f"{itf.name}: missing method {method_name}")
            continue
        if effective_methods[method_name].signature_key() != itf_method.signature_key():
            issues.append(f"{itf.name}: signature mismatch {method_name}")

    for prop_name, itf_prop in itf.properties.items():
        effective_prop = effective_properties.get(prop_name)
        if effective_prop is None:
            issues.append(f"{itf.name}: missing property {prop_name}")
            continue
        if itf_prop.prop_type and effective_prop.prop_type != itf_prop.prop_type:
            issues.append(f"{itf.name}: property type mismatch {prop_name}")
        if itf_prop.accessor_key() != effective_prop.accessor_key():
            issues.append(f"{itf.name}: accessor mismatch {prop_name}")

    return issues


def collect_interface_contract_violations(
    file: TwinCATFile,
    *,
    interface_names: set[str] | None = None,
    include_inherited_interfaces: bool = True,
) -> tuple[list[str], list[str]]:
    """Collect interface resolution misses and effective contract violations.

    Returns:
        (missing_interface_names, violation_fragments)
    """
    pou, effective_methods, effective_properties, inherited_interfaces = (
        _collect_effective_interface_context(file)
    )
    if pou is None:
        return [], []

    if interface_names is None:
        names = set(pou.implements)
        if include_inherited_interfaces:
            names.update(inherited_interfaces)
    else:
        names = set(interface_names)

    if not names:
        return [], []

    missing_interfaces: list[str] = []
    violations: list[str] = []
    for interface_name in sorted(names):
        path = resolve_nearby_symbol_file(file.filepath, interface_name, ".TcIO")
        if path is None:
            missing_interfaces.append(interface_name)
            continue
        violations.extend(
            _check_interface_contract_violations(path, effective_methods, effective_properties)
        )
    return missing_interfaces, violations


def _st_has_executable_content(st_body: str) -> bool:
    """Return True when ST block contains executable (non-comment) content."""
    text = re.sub(r"(?is)\(\*.*?\*\)", "", st_body)
    text = re.sub(r"(?m)//.*$", "", text)
    text = text.strip()
    return bool(text)


def _is_trivial_false_stub(method_name: str, st_body: str) -> bool:
    """Detect trivial stub implementations like `M_Foo := FALSE;`."""
    text = _strip_st_comments_and_strings(st_body).strip()
    if not text:
        return False
    # Accept optional RETURN; after assignment.
    pattern = rf"(?is)^\s*{re.escape(method_name)}\s*:=\s*FALSE\s*;\s*(?:RETURN\s*;\s*)?$"
    return bool(re.match(pattern, text))


def _has_fb_init_signature(method) -> bool:
    """Validate canonical FB_init signature prefix."""
    if method.return_type.upper() != "BOOL":
        return False
    if len(method.signature_params) < 2:
        return False
    p0 = method.signature_params[0]
    p1 = method.signature_params[1]
    return (
        p0[0].upper() == "VAR_INPUT"
        and p0[1].lower() == "binitretains"
        and p0[2].upper() == "BOOL"
        and p1[0].upper() == "VAR_INPUT"
        and p1[1].lower() == "bincopycode"
        and p1[2].upper() == "BOOL"
    )


@CheckRegistry.register
class ExtendsVisibilityCheck(BaseCheck):
    """Ensure derived FUNCTION_BLOCKs do not access base private members."""

    check_id = "extends_visibility"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return not _file_has_oop_keywords(file)

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        derived = parse_pou_symbol(file)
        if derived is None or not derived.extends or derived.pou_type != "FUNCTION_BLOCK":
            return []

        base_path = resolve_nearby_symbol_file(file.filepath, derived.extends, ".TcPOU")
        if not base_path:
            return []
        base_file = TwinCATFile(base_path)
        base = parse_pou_symbol(base_file)
        if base is None:
            return []

        private_only = base.private_members - base.protected_members - base.public_members
        if not private_only:
            return []

        illegal = sorted(
            symbol
            for symbol in derived.used_symbols
            if symbol in private_only and symbol not in derived.local_symbols
        )
        if not illegal:
            return []

        return [
            ValidationIssue(
                severity="error",
                category="OOP",
                message=(
                    f"Derived FUNCTION_BLOCK '{derived.name}' accesses private member(s) "
                    f"of base '{base.name}': {_summarize(illegal)}"
                ),
                fix_available=False,
                fix_suggestion=(
                    "Expose shared base state through METHOD PROTECTED and/or "
                    "PROPERTY members on the base FUNCTION_BLOCK instead of "
                    "accessing private VAR members directly from derived code."
                ),
            )
        ]


@CheckRegistry.register
class OverrideMarkerCheck(BaseCheck):
    """Ensure overriding methods use explicit canonical override marker."""

    check_id = "override_marker"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return not _file_has_oop_keywords(file)

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        derived = parse_pou_symbol(file)
        if derived is None or not derived.extends:
            return []
        base_path = resolve_nearby_symbol_file(file.filepath, derived.extends, ".TcPOU")
        if not base_path:
            return []
        base = parse_pou_symbol(TwinCATFile(base_path))
        if base is None:
            return []

        invalid_keyword = []
        missing_marker = []
        for method_name, derived_method in derived.methods.items():
            if method_name not in base.methods:
                continue
            if derived_method.has_override_keyword and not derived_method.has_override_attribute:
                invalid_keyword.append(method_name)
                continue
            if not derived_method.has_override_attribute:
                missing_marker.append(method_name)

        issues: list[ValidationIssue] = []
        if invalid_keyword:
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="OOP",
                    message=(
                        "Override marker must use TwinCAT attribute syntax "
                        f"{{attribute 'override'}}. Invalid METHOD OVERRIDE usage in: "
                        f"{_summarize(invalid_keyword)}"
                    ),
                    fix_available=True,  # override_attribute fixer can auto-fix this
                    fix_suggestion=(
                        "Run autofix with override_attribute fixer, or manually replace:\n"
                        "METHOD OVERRIDE MethodName : ReturnType\n"
                        "with:\n"
                        "{attribute 'override'}\nMETHOD MethodName : ReturnType"
                    ),
                )
            )
        if missing_marker:
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="OOP",
                    message=(
                        "Derived methods shadow base methods without explicit override marker: "
                        f"{_summarize(missing_marker)}"
                    ),
                    fix_available=False,
                    fix_suggestion=(
                        "Add {attribute 'override'} before each overriding " "METHOD declaration."
                    ),
                )
            )
        return issues


@CheckRegistry.register
class OverrideSignatureCheck(BaseCheck):
    """Ensure overriding method signatures match base signatures exactly."""

    check_id = "override_signature"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return not _file_has_oop_keywords(file)

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        derived = parse_pou_symbol(file)
        if derived is None or not derived.extends:
            return []
        base_path = resolve_nearby_symbol_file(file.filepath, derived.extends, ".TcPOU")
        if not base_path:
            return []
        base = parse_pou_symbol(TwinCATFile(base_path))
        if base is None:
            return []

        mismatches = []
        for method_name, derived_method in derived.methods.items():
            base_method = base.methods.get(method_name)
            if not base_method:
                continue
            if derived_method.signature_key() != base_method.signature_key():
                mismatches.append(method_name)

        if not mismatches:
            return []

        return [
            ValidationIssue(
                severity="error",
                category="OOP",
                message=(
                    f"Override signature mismatch against base '{base.name}' for method(s): "
                    f"{_summarize(mismatches)}"
                ),
                fix_available=False,
                fix_suggestion=(
                    "Match return type and ordered VAR_INPUT/VAR_IN_OUT/VAR_OUTPUT parameter "
                    "signature exactly to base method declaration."
                ),
            )
        ]


@CheckRegistry.register
class InterfaceContractCheck(BaseCheck):
    """Ensure IMPLEMENTS contracts are complete and signature-compatible."""

    check_id = "interface_contract"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return not _file_has_oop_keywords(file)

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        pou = parse_pou_symbol(file)
        if pou is None:
            return []
        _missing, violations = collect_interface_contract_violations(
            file,
            include_inherited_interfaces=True,
        )

        if not violations:
            return []
        return [
            ValidationIssue(
                severity="error",
                category="OOP",
                message=(
                    f"INTERFACE contract violation(s) for '{pou.name}': "
                    f"{_summarize(violations)}"
                ),
                fix_available=False,
                fix_suggestion=(
                    "Implement all interface methods/properties and keep signatures/accessors "
                    "exactly aligned with .TcIO contract."
                ),
            )
        ]


@CheckRegistry.register
class PolicyInterfaceContractIntegrityCheck(BaseCheck):
    """Block contract-weakening patterns on abstract base classes."""

    check_id = "policy_interface_contract_integrity"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        # Cannot skip based on OOP keywords: this check targets abstract BASE classes
        # which themselves have no EXTENDS/IMPLEMENTS but are validated by looking at descendants.
        return _pou_subtype(file) == "function"

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        policy = _get_oop_policy(file.filepath)
        if not policy.get("enforce_interface_contract_integrity", True):
            return []

        pou = parse_pou_symbol(file)
        if pou is None or pou.pou_type != "FUNCTION_BLOCK" or not pou.is_abstract:
            return []
        if pou.implements:
            return []

        descendants = _collect_direct_descendants(file, pou.name)
        if not descendants:
            return []

        candidate_interfaces = _find_matching_interfaces_for_abstract_methods(file, pou)
        if not candidate_interfaces:
            return []

        return [
            ValidationIssue(
                severity="error",
                category="policy_enforcement",
                message=(
                    "[rule_id:enforce_interface_contract_integrity] "
                    f"Abstract base '{pou.name}' has active descendants "
                    f"({_summarize(descendants)}) and matches interface contract(s) "
                    f"({_summarize(candidate_interfaces)}) but does not declare IMPLEMENTS."
                ),
                fix_available=False,
                fix_suggestion=(
                    "Declare IMPLEMENTS on the abstract base and keep abstract methods explicit "
                    "until concrete descendants implement them. Avoid removing base contracts or "
                    "adding redundant derived IMPLEMENTS declarations as a workaround."
                ),
            )
        ]


@CheckRegistry.register
class ExtendsCycleCheck(BaseCheck):
    """Detect cyclic EXTENDS relationships in nearby FUNCTION_BLOCK hierarchy."""

    check_id = "extends_cycle"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return not _file_has_oop_keywords(file)

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        pou = parse_pou_symbol(file)
        if pou is None or not pou.extends:
            return []
        _, cycle_repr = _collect_base_chain(file, pou.extends)
        if not cycle_repr:
            return []
        return [
            ValidationIssue(
                severity="error",
                category="OOP",
                message=(
                    f"Cyclic EXTENDS hierarchy detected starting from '{pou.name}': "
                    f"{cycle_repr}"
                ),
                fix_available=False,
                fix_suggestion=(
                    "Break inheritance cycle so each FUNCTION_BLOCK has an acyclic " "base chain."
                ),
            )
        ]


@CheckRegistry.register
class OverrideSuperCallCheck(BaseCheck):
    """Enforce SUPER^ call in selected overriding lifecycle methods."""

    check_id = "override_super_call"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return not _file_has_oop_keywords(file)

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        policy = _get_oop_policy(file.filepath)
        if not policy["enforce_override_super_call"]:
            return []

        derived = parse_pou_symbol(file)
        if derived is None or not derived.extends:
            return []
        base_path = resolve_nearby_symbol_file(file.filepath, derived.extends, ".TcPOU")
        if not base_path:
            return []
        base = parse_pou_symbol(TwinCATFile(base_path))
        if base is None:
            return []

        missing = []
        required_super_methods = set(policy["required_super_methods"])
        for method_name, derived_method in derived.methods.items():
            if method_name not in required_super_methods:
                continue
            if method_name not in base.methods:
                continue
            if not derived_method.has_super_call():
                missing.append(method_name)

        if not missing:
            return []
        return [
            ValidationIssue(
                severity="error",
                category="OOP",
                message=(
                    "Overriding lifecycle method(s) missing required base call "
                    f"SUPER^.<method>(...): {_summarize(missing)}"
                ),
                fix_available=False,
                fix_suggestion=(
                    "Call SUPER^.MethodName(...) inside overriding lifecycle methods "
                    "unless your project explicitly documents skip semantics."
                ),
            )
        ]


@CheckRegistry.register
class InheritancePropertyContractCheck(BaseCheck):
    """Ensure derived/base property mutability and type contracts match."""

    check_id = "inheritance_property_contract"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return not _file_has_oop_keywords(file)

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        derived = parse_pou_symbol(file)
        if derived is None or not derived.extends:
            return []

        chain, _ = _collect_base_chain(file, derived.extends)
        if not chain:
            return []

        mismatches: list[str] = []
        # Walk derived properties and compare to nearest base declaration in chain.
        for prop_name, derived_prop in derived.properties.items():
            base_prop = None
            owner = ""
            for base_symbol in chain:
                if prop_name in base_symbol.properties:
                    base_prop = base_symbol.properties[prop_name]
                    owner = base_symbol.name
                    break
            if base_prop is None:
                continue

            if base_prop.prop_type and derived_prop.prop_type != base_prop.prop_type:
                mismatches.append(f"{prop_name} (type vs {owner})")
            if derived_prop.accessor_key() != base_prop.accessor_key():
                mismatches.append(f"{prop_name} (accessor mutability vs {owner})")

        if not mismatches:
            return []

        return [
            ValidationIssue(
                severity="error",
                category="OOP",
                message=(
                    "Derived property contract mismatch in inheritance chain: "
                    f"{_summarize(mismatches)}"
                ),
                fix_available=False,
                fix_suggestion=(
                    "Keep overridden property type and Get/Set mutability identical "
                    "to the nearest base declaration."
                ),
            )
        ]


@CheckRegistry.register
class FbInitSignatureCheck(BaseCheck):
    """Ensure FB_init uses TwinCAT canonical signature/return contract."""

    check_id = "fb_init_signature"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return _pou_subtype(file) in ("function", "program")

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        pou = parse_pou_symbol(file)
        if pou is None or pou.pou_type != "FUNCTION_BLOCK":
            return []
        fb_init = pou.methods.get("FB_init")
        if fb_init is None:
            return []
        if _has_fb_init_signature(fb_init):
            return []
        return [
            ValidationIssue(
                severity="error",
                category="OOP",
                message=(
                    "FB_init signature/return type mismatch. "
                    "Expected: METHOD FB_init : BOOL with leading VAR_INPUT "
                    "(bInitRetains : BOOL, bInCopyCode : BOOL)."
                ),
                fix_available=False,
                fix_suggestion=(
                    "Use canonical FB_init declaration and keep any extra VAR_INPUT "
                    "parameters after the two required TwinCAT parameters."
                ),
            )
        ]


@CheckRegistry.register
class FbInitSuperCallCheck(BaseCheck):
    """Ensure overriding FB_init in derived blocks calls SUPER^.FB_init(...)."""

    check_id = "fb_init_super_call"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return not _file_has_oop_keywords(file)

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        policy = _get_oop_policy(file.filepath)
        if not policy["enforce_fb_init_super_call"]:
            return []

        derived = parse_pou_symbol(file)
        if derived is None or not derived.extends:
            return []
        derived_fb_init = derived.methods.get("FB_init")
        if derived_fb_init is None:
            return []

        base_path = resolve_nearby_symbol_file(file.filepath, derived.extends, ".TcPOU")
        if not base_path:
            return []
        base = parse_pou_symbol(TwinCATFile(base_path))
        if base is None:
            return []
        if "FB_init" not in base.methods:
            return []

        if derived_fb_init.has_super_call():
            return []
        return [
            ValidationIssue(
                severity="error",
                category="OOP",
                message=(
                    "Derived FB_init overrides base FB_init but does not call "
                    "SUPER^.FB_init(...)."
                ),
                fix_available=False,
                fix_suggestion=(
                    "Call SUPER^.FB_init(...) in derived FB_init to preserve base "
                    "initialization contract."
                ),
            )
        ]


@CheckRegistry.register
class ThisPointerConsistencyCheck(BaseCheck):
    """Detect ambiguous member shadowing where THIS^ should be explicit."""

    check_id = "this_pointer_consistency"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return _pou_subtype(file) == "function"

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        policy = _get_oop_policy(file.filepath)
        if not policy["enforce_this_pointer_consistency"]:
            return []

        pou = parse_pou_symbol(file)
        if pou is None:
            return []

        member_symbols = set()
        for names in pou.member_by_block.values():
            member_symbols.update(names)
        if not member_symbols:
            return []

        ambiguous: list[str] = []
        for method_name, method in pou.methods.items():
            shadowed = sorted(method.local_symbols.intersection(member_symbols))
            if not shadowed:
                continue
            for name in shadowed:
                # If local and member share name and unqualified assignment exists,
                # require explicit THIS^.name for member access clarity.
                unqualified_assign = re.search(
                    rf"(?im)^\s*{re.escape(name)}\s*:=",
                    method.implementation,
                )
                qualified_assign = re.search(
                    rf"(?im)^\s*THIS\^\.\s*{re.escape(name)}\s*:=",
                    method.implementation,
                )
                if unqualified_assign and not qualified_assign:
                    ambiguous.append(f"{method_name}.{name}")

        if not ambiguous:
            return []
        return [
            ValidationIssue(
                severity="error",
                category="OOP",
                message=(
                    "Ambiguous local/member shadowing detected; use THIS^ for member "
                    f"writes: {_summarize(ambiguous)}"
                ),
                fix_available=False,
                fix_suggestion=(
                    "Rename local variable or use explicit THIS^.MemberName := ... "
                    "when writing to class members."
                ),
            )
        ]


@CheckRegistry.register
class AbstractContractCheck(BaseCheck):
    """Validate ABSTRACT class/method contracts for TwinCAT FB inheritance."""

    check_id = "abstract_contract"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return _pou_subtype(file) in ("function", "program")

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        policy = _get_oop_policy(file.filepath)
        pou = parse_pou_symbol(file)
        if pou is None or pou.pou_type != "FUNCTION_BLOCK":
            return []

        issues: list[ValidationIssue] = []
        abstract_methods_local = [m for m in pou.methods.values() if m.is_abstract]

        if not policy["allow_abstract_keyword"]:
            keyword_usage = []
            if pou.has_abstract_keyword:
                keyword_usage.append(f"class {pou.name}")
            keyword_usage.extend(m.name for m in abstract_methods_local if m.has_abstract_keyword)
            if keyword_usage:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="OOP",
                        message=(
                            "Abstract keyword syntax is disabled by project policy. "
                            f"Found: {_summarize(keyword_usage)}"
                        ),
                        fix_available=False,
                        fix_suggestion=("Switch to allowed ABSTRACT style per project policy."),
                    )
                )

        # Abstract methods should not contain executable implementation.
        bad_abstract_impl = [
            m.name for m in abstract_methods_local if _st_has_executable_content(m.implementation)
        ]
        if bad_abstract_impl:
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="OOP",
                    message=(
                        "Abstract method(s) must not include executable implementation: "
                        f"{_summarize(bad_abstract_impl)}"
                    ),
                    fix_available=False,
                    fix_suggestion=(
                        "Remove method implementation body for abstract methods or "
                        "mark method/class concrete and provide full implementation."
                    ),
                )
            )

        # Guardrail: prevent abstract base classes from silently downgrading contract
        # methods into trivial FALSE stubs.
        if pou.is_abstract:
            bad_stub_methods = [
                method.name
                for method in pou.methods.values()
                if (not method.is_abstract)
                and _is_trivial_false_stub(method.name, method.implementation)
            ]
            if bad_stub_methods:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="OOP",
                        message=(
                            "ABSTRACT FUNCTION_BLOCK contains trivial FALSE stub method(s): "
                            f"{_summarize(bad_stub_methods)}"
                        ),
                        fix_available=False,
                        fix_suggestion=(
                            "Declare these methods as METHOD ABSTRACT or provide real "
                            "non-stub behavior in a concrete class."
                        ),
                    )
                )

        # If class defines abstract methods, class itself must be abstract.
        if abstract_methods_local and not pou.is_abstract:
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="OOP",
                    message=(
                        "Concrete FUNCTION_BLOCK declares abstract method(s): "
                        f"{_summarize([m.name for m in abstract_methods_local])}"
                    ),
                    fix_available=False,
                    fix_suggestion=(
                        "Mark FUNCTION_BLOCK as ABSTRACT or implement all methods "
                        "as concrete methods."
                    ),
                )
            )

        if not pou.extends:
            return issues

        chain, _ = _collect_base_chain(file, pou.extends)
        if not chain:
            return issues

        # Track unresolved abstract methods through inheritance (root -> nearest base -> derived).
        unresolved: dict[str, str] = {}
        for base_symbol in reversed(chain):
            for method_name, method in base_symbol.methods.items():
                if method.is_abstract:
                    unresolved[method_name] = base_symbol.name
                elif method_name in unresolved:
                    unresolved.pop(method_name, None)

        for method_name, method in pou.methods.items():
            if method_name not in unresolved:
                continue
            if not method.is_abstract:
                unresolved.pop(method_name, None)

        if unresolved and not pou.is_abstract:
            missing = [f"{name} (from {owner})" for name, owner in sorted(unresolved.items())]
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="OOP",
                    message=(
                        "Concrete FUNCTION_BLOCK does not implement inherited abstract "
                        f"method(s): {_summarize(missing)}"
                    ),
                    fix_available=False,
                    fix_suggestion=(
                        "Implement all inherited abstract methods or mark this "
                        "FUNCTION_BLOCK as ABSTRACT."
                    ),
                )
            )

        return issues


@CheckRegistry.register
class FbExitContractCheck(BaseCheck):
    """Validate FB_exit canonical signature and warn if missing when __NEW() is used."""

    check_id = "fb_exit_contract"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return _pou_subtype(file) in ("function", "program")

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        policy = _get_oop_policy(file.filepath)
        if not policy["enforce_fb_exit_contract"]:
            return []

        pou = parse_pou_symbol(file)
        if pou is None or pou.pou_type != "FUNCTION_BLOCK":
            return []

        fb_exit = pou.methods.get("FB_exit")

        # Check for __NEW() usage with comment stripping to avoid false positives
        uses_new = False
        for st_block in re.findall(r"(?is)<ST><!\[CDATA\[(.*?)\]\]></ST>", file.content):
            # Strip comments before checking
            st_no_comments = re.sub(r"(?is)\(\*.*?\*\)", "", st_block)
            st_no_comments = re.sub(r"(?m)//.*$", "", st_no_comments)
            if re.search(r"(?i)\b__NEW\s*\(", st_no_comments):
                uses_new = True
                break

        issues: list[ValidationIssue] = []

        # Check if FB_exit exists at all (even if unparseable)
        # Handle any attribute order: Name first OR Id first
        fb_exit_exists = bool(re.search(r'(?is)<Method\s+[^>]*Name="FB_exit"', file.content))

        # If FB uses __NEW() but has no FB_exit at all, warn
        if uses_new and not fb_exit_exists:
            issues.append(
                ValidationIssue(
                    severity="critical",
                    category="OOP",
                    message=(
                        f"FUNCTION_BLOCK '{pou.name}' uses __NEW() for dynamic allocation "
                        "but has no FB_exit method for cleanup."
                    ),
                    fix_available=False,
                    fix_suggestion=(
                        "Add canonical FB_exit method: "
                        "METHOD FB_exit : BOOL\\nVAR_INPUT\\n  bInCopyCode : BOOL;\\nEND_VAR"
                    ),
                )
            )
            return issues

        # If FB_exit exists but wasn't parsed, it has malformed signature
        if fb_exit_exists and fb_exit is None:
            issues.append(
                ValidationIssue(
                    severity="critical",
                    category="OOP",
                    message=(
                        f"FB_exit in '{pou.name}' has malformed signature. "
                        "Expected: METHOD FB_exit : BOOL\\nVAR_INPUT\\n  bInCopyCode : BOOL;\\nEND_VAR"
                    ),
                    fix_available=False,
                    fix_suggestion=(
                        "Ensure FB_exit has canonical signature with return type BOOL and "
                        "single VAR_INPUT parameter (bInCopyCode : BOOL)."
                    ),
                )
            )
            return issues

        # If FB_exit exists and was parsed, validate canonical signature
        if fb_exit is not None:
            # Expected: METHOD FB_exit : BOOL with VAR_INPUT (bInCopyCode : BOOL)
            # Normalize case for comparison
            if fb_exit.return_type.upper() != "BOOL":
                issues.append(
                    ValidationIssue(
                        severity="critical",
                        category="OOP",
                        message=(
                            f"FB_exit in '{pou.name}' has incorrect return type "
                            f"'{fb_exit.return_type}'. Expected: BOOL"
                        ),
                        fix_available=False,
                        fix_suggestion="Change FB_exit return type to BOOL.",
                    )
                )

            # Check signature with case-insensitive comparison
            sig_valid = (
                len(fb_exit.signature_params) >= 1
                and fb_exit.signature_params[0][0].upper() == "VAR_INPUT"
                and fb_exit.signature_params[0][1].lower() == "bincopycode"
                and fb_exit.signature_params[0][2].upper() == "BOOL"
            )
            if not sig_valid:
                issues.append(
                    ValidationIssue(
                        severity="critical",
                        category="OOP",
                        message=(
                            f"FB_exit in '{pou.name}' has incorrect signature. "
                            "Expected: METHOD FB_exit : BOOL\\nVAR_INPUT\\n  bInCopyCode : BOOL;\\nEND_VAR"
                        ),
                        fix_available=False,
                        fix_suggestion=(
                            "Use canonical FB_exit signature with single VAR_INPUT parameter "
                            "(bInCopyCode : BOOL)."
                        ),
                    )
                )

        return issues


@CheckRegistry.register
class DynamicCreationAttributeCheck(BaseCheck):
    """Ensure target FBs used with __NEW() have {attribute 'enable_dynamic_creation'}."""

    check_id = "dynamic_creation_attribute"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return _pou_subtype(file) == "function"

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        policy = _get_oop_policy(file.filepath)
        if not policy["enforce_dynamic_creation_attribute"]:
            return []

        pou = parse_pou_symbol(file)
        if pou is None:
            return []

        # Find all __NEW(TypeName) patterns in ST blocks (strip comments first)
        new_types: set[str] = set()
        for st_block in re.findall(r"(?is)<ST><!\[CDATA\[(.*?)\]\]></ST>", file.content):
            # Strip comments to avoid false positives from commented-out __NEW() calls
            st_no_comments = re.sub(r"(?is)\(\*.*?\*\)", "", st_block)
            st_no_comments = re.sub(r"(?m)//.*$", "", st_no_comments)
            for match in re.finditer(
                r"(?i)\b__NEW\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)", st_no_comments
            ):
                new_types.add(match.group(1))

        if not new_types:
            return []

        issues: list[ValidationIssue] = []
        for type_name in sorted(new_types):
            target_path = resolve_nearby_symbol_file(file.filepath, type_name, ".TcPOU")
            if target_path is None:
                # Can't resolve, skip (could be standard library type or external)
                continue

            target_file = TwinCATFile(target_path)
            target_pou = parse_pou_symbol(target_file)
            if target_pou is None:
                continue

            # Check if target has {attribute 'enable_dynamic_creation'}
            has_attribute = bool(
                re.search(
                    r"(?im)^\s*\{attribute\s+['\"]enable_dynamic_creation['\"]\}",
                    target_file.content,
                )
            )

            if not has_attribute:
                issues.append(
                    ValidationIssue(
                        severity="critical",
                        category="OOP",
                        message=(
                            f"__NEW({type_name}) is used in '{pou.name}', but target FB "
                            f"'{type_name}' lacks {{attribute 'enable_dynamic_creation'}}. "
                            "Dynamic instantiation will silently fail at runtime."
                        ),
                        fix_available=False,  # Cross-file issue - can't safely auto-fix
                        fix_suggestion=(
                            f"Add {{attribute 'enable_dynamic_creation'}} to the declaration "
                            f"of FUNCTION_BLOCK {type_name}."
                        ),
                    )
                )

        return issues


@CheckRegistry.register
class PointerDeletePairingCheck(BaseCheck):
    """Ensure __NEW() allocations have matching __DELETE() in cleanup methods."""

    check_id = "pointer_delete_pairing"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return _pou_subtype(file) == "function"

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        policy = _get_oop_policy(file.filepath)
        if not policy["enforce_pointer_delete_pairing"]:
            return []

        pou = parse_pou_symbol(file)
        if pou is None:
            return []

        # Track allocations: pVar := __NEW(Type) (strip comments first)
        allocations: dict[str, str] = {}  # {pointer_name: type_name}
        for st_block in re.findall(r"(?is)<ST><!\[CDATA\[(.*?)\]\]></ST>", file.content):
            # Strip comments to avoid false positives
            st_no_comments = re.sub(r"(?is)\(\*.*?\*\)", "", st_block)
            st_no_comments = re.sub(r"(?m)//.*$", "", st_no_comments)
            for match in re.finditer(
                r"(?i)([A-Za-z_][A-Za-z0-9_]*)\s*:=\s*__NEW\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",
                st_no_comments,
            ):
                allocations[match.group(1)] = match.group(2)

        if not allocations:
            return []

        # Check for matching __DELETE(pVar) in cleanup methods
        # Use XML-based search to find cleanup methods (don't rely on parsing)
        cleanup_method_names = {"FB_exit"} | set(policy["cleanup_method_names"])
        cleanup_implementations: list[str] = []

        # Search for cleanup methods in XML directly
        # Handle any attribute order: Name first OR Id first
        for method_name in cleanup_method_names:
            method_pattern = re.compile(
                rf'(?is)<Method\s+[^>]*Name="{re.escape(method_name)}"[^>]*>.*?'
                r"<Implementation>\s*<ST><!\[CDATA\[(.*?)\]\]></ST>\s*</Implementation>.*?</Method>"
            )
            for match in method_pattern.finditer(file.content):
                cleanup_implementations.append(match.group(1))

        if not cleanup_implementations:
            # No cleanup methods found at all
            return [
                ValidationIssue(
                    severity="critical",
                    category="OOP",
                    message=(
                        f"FUNCTION_BLOCK '{pou.name}' allocates pointers with __NEW() "
                        f"({_summarize(list(allocations.keys()))}) but has no cleanup method. "
                        f"Expected one of: {_summarize(sorted(cleanup_method_names))}"
                    ),
                    fix_available=False,
                    fix_suggestion=(
                        "Add FB_exit method with __DELETE() calls for all allocated pointers."
                    ),
                )
            ]

        # Check which allocations are deleted
        missing_deletes: list[str] = []
        for ptr_name in allocations:
            deleted = any(
                re.search(rf"(?i)\b__DELETE\s*\(\s*{re.escape(ptr_name)}\s*\)", impl)
                for impl in cleanup_implementations
            )
            if not deleted:
                missing_deletes.append(ptr_name)

        if not missing_deletes:
            return []

        return [
            ValidationIssue(
                severity="critical",
                category="OOP",
                message=(
                    f"Pointer(s) allocated with __NEW() in '{pou.name}' lack matching "
                    f"__DELETE() in cleanup methods: {_summarize(missing_deletes)}"
                ),
                fix_available=False,
                fix_suggestion=(
                    f"Add __DELETE() calls in {_summarize(sorted(cleanup_method_names))} "
                    "for all allocated pointers to prevent memory leaks."
                ),
            )
        ]


# =============================================================================
# Phase 5B: OOP Design Quality Checks
# =============================================================================


@CheckRegistry.register
class CompositionDepthCheck(BaseCheck):
    """Warn if inheritance depth exceeds configurable maximum (SOLID: favor composition)."""

    check_id = "composition_depth"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return not _file_has_oop_keywords(file)

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        policy = _get_oop_policy(file.filepath)
        max_depth = policy.get("max_inheritance_depth", 4)

        pou = parse_pou_symbol(file)
        if pou is None or not pou.extends:
            return []

        # Count inheritance depth
        chain, _ = _collect_base_chain(file, pou.extends)
        depth = len(chain)  # Does not include self

        if depth <= max_depth:
            return []

        return [
            ValidationIssue(
                severity="warning",
                category="OOP",
                message=(
                    f"Inheritance depth {depth} exceeds recommended maximum {max_depth} "
                    f"for '{pou.name}'. Consider composition over deep inheritance."
                ),
                fix_available=False,
                fix_suggestion=(
                    "Refactor to use composition (HAS-A) instead of deep inheritance (IS-A). "
                    "Extract shared behavior into separate components."
                ),
            )
        ]


@CheckRegistry.register
class InterfaceSegregationCheck(BaseCheck):
    """Warn if interface has too many methods (Interface Segregation Principle)."""

    check_id = "interface_segregation"

    def should_skip(self, file: TwinCATFile) -> bool:
        return file.suffix != ".TcIO"

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        policy = _get_oop_policy(file.filepath)
        max_methods = policy.get("max_interface_methods", 7)

        itf = parse_interface_symbol(file.filepath)
        if itf is None:
            return []

        method_count = len(itf.methods)
        property_count = len(itf.properties)
        total_surface = method_count + property_count

        if total_surface <= max_methods:
            return []

        return [
            ValidationIssue(
                severity="warning",
                category="OOP",
                message=(
                    f"Interface '{itf.name}' has {total_surface} members "
                    f"({method_count} methods + {property_count} properties), "
                    f"exceeding recommended maximum {max_methods}. "
                    "This violates Interface Segregation Principle."
                ),
                fix_available=False,
                fix_suggestion=(
                    f"Split '{itf.name}' into smaller, focused interfaces. "
                    "Clients should not depend on methods they don't use."
                ),
            )
        ]


@CheckRegistry.register
class MethodVisibilityConsistencyCheck(BaseCheck):
    """Ensure derived methods don't reduce visibility (Liskov Substitution Principle)."""

    check_id = "method_visibility_consistency"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return not _file_has_oop_keywords(file)

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        pou = parse_pou_symbol(file)
        if pou is None or not pou.extends:
            return []

        base_path = resolve_nearby_symbol_file(file.filepath, pou.extends, ".TcPOU")
        if not base_path:
            return []

        base = parse_pou_symbol(TwinCATFile(base_path))
        if base is None:
            return []

        # Visibility ranking: PUBLIC > PROTECTED > PRIVATE
        # TwinCAT default is PUBLIC when no specifier is present (per IEC 61131-3 course docs)
        visibility_rank = {"PUBLIC": 3, "PROTECTED": 2, "PRIVATE": 1, "": 3}  # Default is PUBLIC

        violations: list[str] = []
        for method_name, derived_method in pou.methods.items():
            if method_name not in base.methods:
                continue

            base_method = base.methods[method_name]

            # Infer visibility from method declaration or VAR block
            # TwinCAT doesn't store visibility in MethodSymbol, so we parse from declaration
            base_visibility = self._infer_visibility(base_method.declaration)
            derived_visibility = self._infer_visibility(derived_method.declaration)

            base_rank = visibility_rank.get(base_visibility, 3)  # Default PUBLIC = 3
            derived_rank = visibility_rank.get(derived_visibility, 3)  # Default PUBLIC = 3

            if derived_rank < base_rank:
                violations.append(
                    f"{method_name}: {base_visibility or 'PUBLIC'} → {derived_visibility or 'PUBLIC'}"
                )

        if not violations:
            return []

        return [
            ValidationIssue(
                severity="warning",
                category="OOP",
                message=(
                    f"Method visibility reduced in '{pou.name}' (violates Liskov Substitution): "
                    f"{_summarize(violations)}"
                ),
                fix_available=False,
                fix_suggestion=(
                    "Derived methods must have equal or greater visibility than base methods. "
                    "Reductions are invalid: PUBLIC → PROTECTED/PRIVATE, PROTECTED → PRIVATE."
                ),
            )
        ]

    def _infer_visibility(self, declaration: str) -> str:
        """Infer visibility from method declaration text."""
        # TwinCAT syntax: METHOD PUBLIC M_Start
        if re.search(r"\bPUBLIC\b", declaration, re.IGNORECASE):
            return "PUBLIC"
        if re.search(r"\bPROTECTED\b", declaration, re.IGNORECASE):
            return "PROTECTED"
        if re.search(r"\bPRIVATE\b", declaration, re.IGNORECASE):
            return "PRIVATE"
        return ""  # Default is PUBLIC in TwinCAT (per IEC 61131-3 spec)


@CheckRegistry.register
class DiamondInheritanceWarningCheck(BaseCheck):
    """Warn about duplicate interface implementation in inheritance chain."""

    check_id = "diamond_inheritance_warning"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return not _file_has_oop_keywords(file)

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        policy = _get_oop_policy(file.filepath)
        if not policy.get("warn_diamond_inheritance", True):
            return []

        pou = parse_pou_symbol(file)
        if pou is None:
            return []

        # Collect interfaces from inheritance chain and check for duplicates
        # Note: This detects redundant re-implementation of same interface,
        # not true "diamond" (which requires graph analysis of multiple branches)
        interface_sources: dict[str, list[str]] = {}  # interface_name -> [source_class, ...]

        # Direct interfaces from this class
        for itf_name in pou.implements:
            interface_sources.setdefault(itf_name, []).append(pou.name)

        # Interfaces from base chain (linear, single inheritance)
        if pou.extends:
            chain, _ = _collect_base_chain(file, pou.extends)
            for symbol in chain:
                for itf_name in symbol.implements:
                    interface_sources.setdefault(itf_name, []).append(symbol.name)

        # Find interfaces implemented more than once
        duplicates = {
            itf: sources for itf, sources in interface_sources.items() if len(sources) > 1
        }

        if not duplicates:
            return []

        # Report the first duplicate found
        itf_name, sources = next(iter(duplicates.items()))
        return [
            ValidationIssue(
                severity="warning",
                category="OOP",
                message=(
                    f"Redundant interface implementation in '{pou.name}': "
                    f"interface '{itf_name}' is implemented in multiple classes in the "
                    f"inheritance chain: {_summarize(sources)}. This may indicate "
                    "unnecessary re-implementation or potential diamond pattern."
                ),
                fix_available=False,
                fix_suggestion=(
                    f"Remove redundant IMPLEMENTS {itf_name} declaration. "
                    "An interface only needs to be implemented once in the hierarchy."
                ),
            )
        ]


@CheckRegistry.register
class AbstractInstantiationCheck(BaseCheck):
    """Prevent instantiation of abstract function blocks (runtime crash)."""

    check_id = "abstract_instantiation"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return _pou_subtype(file) == "function"

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        pou = parse_pou_symbol(file)
        if pou is None:
            return []

        # Find all __NEW(...) calls in implementation and method bodies
        new_calls: list[tuple[str, str]] = []  # [(target_type, context)]

        # Check main implementation
        main_impl = file.content
        impl_match = re.search(
            r"<Implementation>\s*<ST><!\[CDATA\[(.*?)\]\]></ST>",
            main_impl,
            re.DOTALL | re.IGNORECASE,
        )
        if impl_match:
            st_code = impl_match.group(1)
            new_calls.extend(self._find_new_calls(st_code, pou.name))

        # Check all methods
        for method_name, method_symbol in pou.methods.items():
            new_calls.extend(
                self._find_new_calls(method_symbol.implementation, f"{pou.name}.{method_name}")
            )

        if not new_calls:
            return []

        # Resolve each target type to check if it's abstract
        violations: list[str] = []
        for target_type, context in new_calls:
            target_path = resolve_nearby_symbol_file(file.filepath, target_type, ".TcPOU")
            if not target_path:
                continue  # Can't resolve - might be external, skip

            target_pou = parse_pou_symbol(TwinCATFile(target_path))
            if target_pou and target_pou.is_abstract:
                violations.append(f"{context}: __NEW({target_type})")

        if not violations:
            return []

        return [
            ValidationIssue(
                severity="critical",
                category="OOP",
                message=(
                    f"Abstract instantiation detected in '{pou.name}': "
                    f"{_summarize(violations)}. "
                    "Cannot instantiate abstract function blocks at runtime."
                ),
                fix_available=False,
                fix_suggestion=(
                    "Replace abstract type with concrete implementation. "
                    "Abstract function blocks can only be used as base classes, not instantiated."
                ),
            )
        ]

    def _find_new_calls(self, st_code: str, context: str) -> list[tuple[str, str]]:
        """Find all __NEW(Type) calls in ST code, return [(type, context)]."""
        if not st_code:
            return []

        # Strip comments to avoid false positives
        cleaned = _strip_st_comments_and_strings(st_code)

        # Match __NEW(TypeName)
        new_pattern = re.compile(r"__NEW\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)", re.IGNORECASE)
        matches = new_pattern.findall(cleaned)

        return [(type_name, context) for type_name in matches]


@CheckRegistry.register
class PropertyAccessorPairingCheck(BaseCheck):
    """Warn about properties with only getter or only setter (suspicious asymmetry)."""

    check_id = "property_accessor_pairing"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix not in (".TcPOU", ".TcIO"):
            return True
        if file.suffix == ".TcPOU":
            return _pou_subtype(file) == "function"
        return False

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        if file.suffix == ".TcPOU":
            pou = parse_pou_symbol(file)
            if pou is None:
                return []
            properties = pou.properties
            owner_name = pou.name
        else:  # .TcIO
            itf = parse_interface_symbol(file.filepath)
            if itf is None:
                return []
            properties = itf.properties
            owner_name = itf.name

        if not properties:
            return []

        # Check OOP policy for exceptions
        policy = _get_oop_policy(file.filepath)
        allow_readonly = policy.get("allow_readonly_properties", True)
        allow_writeonly = policy.get("allow_writeonly_properties", False)

        unpaired: list[str] = []
        for prop_name, prop_symbol in properties.items():
            has_get = prop_symbol.has_get
            has_set = prop_symbol.has_set

            if has_get and not has_set:
                if not allow_readonly:
                    unpaired.append(f"{prop_name} (read-only)")
            elif has_set and not has_get:
                if not allow_writeonly:
                    unpaired.append(f"{prop_name} (write-only)")

        if not unpaired:
            return []

        return [
            ValidationIssue(
                severity="warning",
                category="OOP",
                message=(
                    f"Unpaired property accessor(s) in '{owner_name}': "
                    f"{_summarize(unpaired)}. "
                    "Asymmetric properties may indicate incomplete implementation."
                ),
                fix_available=False,
                fix_suggestion=(
                    "Add missing getter/setter or mark property as intentionally read-only/write-only "
                    "via project policy (allow_readonly_properties, allow_writeonly_properties)."
                ),
            )
        ]


@CheckRegistry.register
class MethodCountCheck(BaseCheck):
    """Warn if a POU has too many methods (Single Responsibility Principle).

    Configurable via ``max_methods_per_pou`` in OOP policy (default: 15).
    Counts Method and Property children as members.
    """

    check_id = "method_count"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return _pou_subtype(file) == "function"

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        policy = _get_oop_policy(file.filepath)
        max_methods = policy.get("max_methods_per_pou", 15)

        pou = parse_pou_symbol(file)
        if pou is None:
            return []

        method_count = len(pou.methods)
        property_count = len(pou.properties)
        total_members = method_count + property_count

        if total_members <= max_methods:
            return []

        return [
            ValidationIssue(
                severity="warning",
                category="OOP",
                message=(
                    f"POU '{pou.name}' has {total_members} members "
                    f"({method_count} methods + {property_count} properties), "
                    f"exceeding recommended maximum {max_methods}. "
                    "This may indicate a Single Responsibility Principle violation."
                ),
                fix_available=False,
                fix_suggestion=(
                    f"Consider splitting '{pou.name}' into smaller, focused function blocks. "
                    "Extract cohesive groups of methods into separate FBs with clear responsibilities."
                ),
            )
        ]


@CheckRegistry.register
class ForbiddenAbstractAttributeCheck(BaseCheck):
    """Detect {attribute 'abstract'} which is not valid TwinCAT 3 syntax."""

    check_id = "forbidden_abstract_attribute"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return _pou_subtype(file) == "function"

    # Compiled at class body level to avoid repeated compilation on each run() call
    _ABSTRACT_ATTR_RE = re.compile(r"\{attribute\s+['\"]abstract['\"]\}", re.IGNORECASE)
    _DECL_CDATA_RE = re.compile(
        r"<Declaration>\s*<!\[CDATA\[(.*?)\]\]>\s*</Declaration>",
        re.DOTALL | re.IGNORECASE,
    )
    _ST_CDATA_RE = re.compile(r"<ST><!\[CDATA\[(.*?)\]\]></ST>", re.DOTALL | re.IGNORECASE)
    _BLOCK_COMMENT_RE = re.compile(r"\(\*.*?\*\)", re.DOTALL | re.IGNORECASE)
    _LINE_COMMENT_RE = re.compile(r"//.*$", re.MULTILINE)

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        # Declaration CDATA blocks are scanned with only comment stripping (not string stripping)
        # because the pragma itself uses single quotes: {attribute 'abstract'}.
        # ST implementation blocks are scanned with full comment+string stripping via the shared
        # helper, which avoids false-positives on (* {attribute 'abstract'} *) in code comments.
        pattern = self._ABSTRACT_ATTR_RE

        def _strip_decl_comments(text: str) -> str:
            text = self._BLOCK_COMMENT_RE.sub("", text)
            text = self._LINE_COMMENT_RE.sub("", text)
            return text

        found = False
        for m in self._DECL_CDATA_RE.finditer(file.content):
            cleaned = _strip_decl_comments(m.group(1))
            if pattern.search(cleaned):
                found = True
                break

        if not found:
            for m in self._ST_CDATA_RE.finditer(file.content):
                cleaned = _strip_st_comments_and_strings(m.group(1))
                if pattern.search(cleaned):
                    found = True
                    break

        if not found:
            return []

        return [
            ValidationIssue(
                severity="error",
                category="OOP",
                message=(
                    "{attribute 'abstract'} is not valid TwinCAT 3 syntax and will be "
                    "rejected by the compiler. Use METHOD ABSTRACT MethodName or "
                    "FUNCTION_BLOCK ABSTRACT ClassName instead."
                ),
                fix_available=False,
                fix_suggestion=(
                    "Replace {attribute 'abstract'} + METHOD Name with "
                    "METHOD ABSTRACT Name (ABSTRACT keyword on the same header line, "
                    "no attribute pragma needed)."
                ),
            )
        ]


@CheckRegistry.register
class HardcodedDispatchCheck(BaseCheck):
    """Warn when the same method is called on an array with multiple hardcoded integer literals."""

    check_id = "hardcoded_dispatch"

    def should_skip(self, file: TwinCATFile) -> bool:
        if file.suffix != ".TcPOU":
            return True
        return _pou_subtype(file) == "function"

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        # Collect all ST implementation blocks from the file
        all_st: list[str] = []
        for m in re.finditer(
            r"<ST><!\[CDATA\[(.*?)\]\]></ST>", file.content, re.DOTALL | re.IGNORECASE
        ):
            cleaned = _strip_st_comments_and_strings(m.group(1))
            all_st.append(cleaned)

        if not all_st:
            return []

        # Match: identifier[integer_literal].method_name(
        dispatch_pattern = re.compile(
            r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*(\d+)\s*\]\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            re.IGNORECASE,
        )

        # Map (array_base_lower, method_name_lower) -> set of integer literals seen
        counts: dict[tuple[str, str], set[str]] = {}
        match_spans: dict[tuple[str, str], list[tuple[str, int, int, str]]] = {}
        # Keep original casing of first seen names for the message
        display: dict[tuple[str, str], tuple[str, str]] = {}
        for st in all_st:
            for m in dispatch_pattern.finditer(st):
                arr, idx, method = m.group(1), m.group(2), m.group(3)
                key = (arr.lower(), method.lower())
                if key not in counts:
                    counts[key] = set()
                    match_spans[key] = []
                    display[key] = (arr, method)
                counts[key].add(idx)
                match_spans[key].append((idx, m.start(), m.end(), st))

        violations = [
            f"{display[key][0]}[...].{display[key][1]} ({len(idxs)} literals)"
            for key, idxs in counts.items()
            if len(idxs) >= 2
            and not self._is_guarded_unrolled_dispatch(key, match_spans.get(key, []))
        ]
        if not violations:
            return []

        return [
            ValidationIssue(
                severity="warning",
                category="OOP",
                message=(
                    f"Hardcoded array-index dispatch detected: {_summarize(violations)}. "
                    "Use a FOR loop over an interface array instead of per-index method calls."
                ),
                fix_available=False,
                fix_suggestion=(
                    "Replace hardcoded arr[1].Method() / arr[2].Method() calls with: "
                    "FOR i := 1 TO nCount DO arr[i].Method(); END_FOR"
                ),
            )
        ]

    @staticmethod
    def _is_guarded_unrolled_dispatch(
        key: tuple[str, str], spans: list[tuple[str, int, int, str]]
    ) -> bool:
        """Suppress warning for explicit guarded unrolled dispatch (compatibility path).

        This avoids contradictory guidance with reset-spam heuristics when users intentionally
        unroll reset calls inside a strong edge/backoff/auth gate.
        """
        if not spans:
            return False
        _arr_name, method_name = key
        if method_name != "m_reset":
            return False
        st = spans[0][3]
        if not st:
            return False
        if_pattern = re.compile(r"(?is)\bIF\b(.*?)\bTHEN\b(.*?)\bEND_IF\s*;")
        guard_tokens = (
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
        for if_match in if_pattern.finditer(st):
            cond = (if_match.group(1) or "").upper()
            body = if_match.group(2) or ""
            if " AND NOT " not in cond and not any(tok in cond for tok in guard_tokens):
                continue
            hits = 0
            for _idx, start, end, _ in spans:
                if if_match.start(2) <= start and end <= if_match.end(2):
                    hits += 1
            if hits >= 2:
                return True
            if (
                hits == 1
                and re.search(r"\[\s*\d+\s*\]\s*\.\s*M_Reset\s*\(", body, re.IGNORECASE)
                and len({idx for idx, *_rest in spans}) >= 2
            ):
                return True
        return False
