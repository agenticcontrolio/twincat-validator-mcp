"""Phase 8B: Tests for enhanced should_skip() on OOP checks.

Verifies that:
- Checks requiring EXTENDS/IMPLEMENTS skip files without those keywords
- FUNCTION_BLOCK-only checks skip FUNCTION and PROGRAM subtypes
- General OOP checks skip plain FUNCTION POUs
- All checks still run correctly on valid OOP files (no false negatives)
- PolicyInterfaceContractIntegrityCheck still runs on abstract BASE classes
  (which have no EXTENDS/IMPLEMENTS but are detected via their descendants)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from twincat_validator.file_handler import TwinCATFile
from twincat_validator.validators.oop_checks import (
    AbstractContractCheck,
    AbstractInstantiationCheck,
    CompositionDepthCheck,
    DiamondInheritanceWarningCheck,
    DynamicCreationAttributeCheck,
    ExtendsCycleCheck,
    ExtendsVisibilityCheck,
    FbExitContractCheck,
    FbInitSignatureCheck,
    FbInitSuperCallCheck,
    ForbiddenAbstractAttributeCheck,
    HardcodedDispatchCheck,
    InheritancePropertyContractCheck,
    InterfaceContractCheck,
    MethodCountCheck,
    MethodVisibilityConsistencyCheck,
    OverrideMarkerCheck,
    OverrideSignatureCheck,
    OverrideSuperCallCheck,
    PolicyInterfaceContractIntegrityCheck,
    PointerDeletePairingCheck,
    PropertyAccessorPairingCheck,
    ThisPointerConsistencyCheck,
)


# ---------------------------------------------------------------------------
# Minimal file factories
# ---------------------------------------------------------------------------


def _make_function_block(
    tmp_path: Path, name: str = "FB_Test", extra_decl: str = ""
) -> TwinCATFile:
    """Plain FUNCTION_BLOCK with no EXTENDS / IMPLEMENTS."""
    path = tmp_path / f"{name}.TcPOU"
    path.write_text(
        f'<?xml version="1.0" encoding="utf-8"?>\n'
        f'<TcPlcObject Version="1.1.0.1">\n'
        f'  <POU Name="{name}" Id="{{11111111-1111-1111-1111-111111111111}}" SpecialFunc="None">\n'
        f"    <Declaration><![CDATA[FUNCTION_BLOCK {name}\n{extra_decl}VAR END_VAR\n]]></Declaration>\n"
        f"    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
        f"  </POU>\n"
        f"</TcPlcObject>\n",
        encoding="utf-8",
    )
    return TwinCATFile(path)


def _make_function(tmp_path: Path, name: str = "F_Test") -> TwinCATFile:
    """Plain FUNCTION — can never use OOP constructs."""
    path = tmp_path / f"{name}.TcPOU"
    path.write_text(
        f'<?xml version="1.0" encoding="utf-8"?>\n'
        f'<TcPlcObject Version="1.1.0.1">\n'
        f'  <POU Name="{name}" Id="{{22222222-2222-2222-2222-222222222222}}" SpecialFunc="None">\n'
        f"    <Declaration><![CDATA[FUNCTION {name} : BOOL\nVAR_INPUT\n  x : BOOL;\nEND_VAR\n]]></Declaration>\n"
        f"    <Implementation><ST><![CDATA[{name} := x;]]></ST></Implementation>\n"
        f"  </POU>\n"
        f"</TcPlcObject>\n",
        encoding="utf-8",
    )
    return TwinCATFile(path)


def _make_program(tmp_path: Path, name: str = "PRG_Test") -> TwinCATFile:
    """Plain PROGRAM — cannot extend/implement."""
    path = tmp_path / f"{name}.TcPOU"
    path.write_text(
        f'<?xml version="1.0" encoding="utf-8"?>\n'
        f'<TcPlcObject Version="1.1.0.1">\n'
        f'  <POU Name="{name}" Id="{{33333333-3333-3333-3333-333333333333}}" SpecialFunc="None">\n'
        f"    <Declaration><![CDATA[PROGRAM {name}\nVAR END_VAR\n]]></Declaration>\n"
        f"    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
        f"  </POU>\n"
        f"</TcPlcObject>\n",
        encoding="utf-8",
    )
    return TwinCATFile(path)


def _make_derived_fb(
    tmp_path: Path, name: str = "FB_Derived", base: str = "FB_Base"
) -> TwinCATFile:
    """FUNCTION_BLOCK with EXTENDS — OOP file."""
    path = tmp_path / f"{name}.TcPOU"
    path.write_text(
        f'<?xml version="1.0" encoding="utf-8"?>\n'
        f'<TcPlcObject Version="1.1.0.1">\n'
        f'  <POU Name="{name}" Id="{{44444444-4444-4444-4444-444444444444}}" SpecialFunc="None">\n'
        f"    <Declaration><![CDATA[FUNCTION_BLOCK {name} EXTENDS {base}\nVAR END_VAR\n]]></Declaration>\n"
        f"    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
        f"  </POU>\n"
        f"</TcPlcObject>\n",
        encoding="utf-8",
    )
    return TwinCATFile(path)


def _make_implements_fb(
    tmp_path: Path, name: str = "FB_Impl", interface: str = "I_Test"
) -> TwinCATFile:
    """FUNCTION_BLOCK with IMPLEMENTS — OOP file."""
    path = tmp_path / f"{name}.TcPOU"
    path.write_text(
        f'<?xml version="1.0" encoding="utf-8"?>\n'
        f'<TcPlcObject Version="1.1.0.1">\n'
        f'  <POU Name="{name}" Id="{{55555555-5555-5555-5555-555555555555}}" SpecialFunc="None">\n'
        f"    <Declaration><![CDATA[FUNCTION_BLOCK {name} IMPLEMENTS {interface}\nVAR END_VAR\n]]></Declaration>\n"
        f"    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
        f"  </POU>\n"
        f"</TcPlcObject>\n",
        encoding="utf-8",
    )
    return TwinCATFile(path)


# ---------------------------------------------------------------------------
# Tests: EXTENDS-requiring checks skip plain FBs and FUNCTIONs
# ---------------------------------------------------------------------------

_EXTENDS_REQUIRING_CHECKS = [
    ExtendsVisibilityCheck,
    OverrideMarkerCheck,
    OverrideSignatureCheck,
    ExtendsCycleCheck,
    OverrideSuperCallCheck,
    InheritancePropertyContractCheck,
    FbInitSuperCallCheck,
    MethodVisibilityConsistencyCheck,
    CompositionDepthCheck,
    InterfaceContractCheck,
    DiamondInheritanceWarningCheck,
]


@pytest.mark.parametrize("check_class", _EXTENDS_REQUIRING_CHECKS)
def test_extends_checks_skip_plain_function_block(check_class, tmp_path):
    """Checks requiring EXTENDS/IMPLEMENTS must skip a plain FB with no OOP keywords."""
    fb = _make_function_block(tmp_path)
    check = check_class()
    assert (
        check.should_skip(fb) is True
    ), f"{check_class.__name__}.should_skip() should return True for plain FUNCTION_BLOCK"


@pytest.mark.parametrize("check_class", _EXTENDS_REQUIRING_CHECKS)
def test_extends_checks_skip_function(check_class, tmp_path):
    """Checks requiring EXTENDS/IMPLEMENTS must skip FUNCTION subtypes."""
    fn = _make_function(tmp_path)
    check = check_class()
    assert check.should_skip(fn) is True


@pytest.mark.parametrize("check_class", _EXTENDS_REQUIRING_CHECKS)
def test_extends_checks_do_not_skip_derived_fb(check_class, tmp_path):
    """Checks requiring EXTENDS/IMPLEMENTS must NOT skip FBs that have EXTENDS."""
    fb = _make_derived_fb(tmp_path)
    check = check_class()
    assert (
        check.should_skip(fb) is False
    ), f"{check_class.__name__}.should_skip() should return False for FB with EXTENDS"


@pytest.mark.parametrize("check_class", [InterfaceContractCheck, DiamondInheritanceWarningCheck])
def test_extends_checks_do_not_skip_implements_fb(check_class, tmp_path):
    """Interface-related checks must NOT skip FBs that have IMPLEMENTS."""
    fb = _make_implements_fb(tmp_path)
    check = check_class()
    assert check.should_skip(fb) is False


# ---------------------------------------------------------------------------
# Tests: FUNCTION_BLOCK-only checks skip FUNCTION and PROGRAM
# ---------------------------------------------------------------------------

_FB_ONLY_CHECKS = [
    FbInitSignatureCheck,
    AbstractContractCheck,
    FbExitContractCheck,
]


@pytest.mark.parametrize("check_class", _FB_ONLY_CHECKS)
def test_fb_only_checks_skip_function(check_class, tmp_path):
    """FUNCTION_BLOCK-only checks must skip FUNCTION subtypes."""
    fn = _make_function(tmp_path)
    check = check_class()
    assert check.should_skip(fn) is True


@pytest.mark.parametrize("check_class", _FB_ONLY_CHECKS)
def test_fb_only_checks_skip_program(check_class, tmp_path):
    """FUNCTION_BLOCK-only checks must skip PROGRAM subtypes."""
    prg = _make_program(tmp_path)
    check = check_class()
    assert check.should_skip(prg) is True


@pytest.mark.parametrize("check_class", _FB_ONLY_CHECKS)
def test_fb_only_checks_do_not_skip_function_block(check_class, tmp_path):
    """FUNCTION_BLOCK-only checks must NOT skip FUNCTION_BLOCK (even plain ones)."""
    fb = _make_function_block(tmp_path)
    check = check_class()
    assert check.should_skip(fb) is False


# ---------------------------------------------------------------------------
# Tests: General OOP checks skip plain FUNCTION but run on FB/PROGRAM
# ---------------------------------------------------------------------------

_FUNCTION_SKIP_CHECKS = [
    ThisPointerConsistencyCheck,
    DynamicCreationAttributeCheck,
    PointerDeletePairingCheck,
    AbstractInstantiationCheck,
    MethodCountCheck,
    ForbiddenAbstractAttributeCheck,
    HardcodedDispatchCheck,
]


@pytest.mark.parametrize("check_class", _FUNCTION_SKIP_CHECKS)
def test_general_oop_checks_skip_function(check_class, tmp_path):
    """General OOP checks must skip plain FUNCTION subtypes."""
    fn = _make_function(tmp_path)
    check = check_class()
    assert check.should_skip(fn) is True


@pytest.mark.parametrize("check_class", _FUNCTION_SKIP_CHECKS)
def test_general_oop_checks_do_not_skip_function_block(check_class, tmp_path):
    """General OOP checks must NOT skip FUNCTION_BLOCK subtypes."""
    fb = _make_function_block(tmp_path)
    check = check_class()
    assert check.should_skip(fb) is False


# ---------------------------------------------------------------------------
# Tests: PolicyInterfaceContractIntegrityCheck — special base-class check
# ---------------------------------------------------------------------------


def test_policy_integrity_check_does_not_skip_abstract_base_without_implements(tmp_path):
    """PolicyInterfaceContractIntegrityCheck must NOT skip abstract FBs with no IMPLEMENTS.

    This check targets BASE classes that have no OOP keywords themselves but have
    descendants. Skipping based on _file_has_oop_keywords would cause false negatives.
    """
    path = tmp_path / "FB_AbstractBase.TcPOU"
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1">\n'
        '  <POU Name="FB_AbstractBase" Id="{66666666-6666-6666-6666-666666666666}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK ABSTRACT FB_AbstractBase\nVAR END_VAR\n]]></Declaration>\n"
        "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
        "  </POU>\n"
        "</TcPlcObject>\n",
        encoding="utf-8",
    )
    fb = TwinCATFile(path)
    check = PolicyInterfaceContractIntegrityCheck()
    assert (
        check.should_skip(fb) is False
    ), "PolicyInterfaceContractIntegrityCheck must run on abstract FBs with no IMPLEMENTS keyword"


def test_policy_integrity_check_skips_function(tmp_path):
    """PolicyInterfaceContractIntegrityCheck must skip FUNCTION subtypes."""
    fn = _make_function(tmp_path)
    check = PolicyInterfaceContractIntegrityCheck()
    assert check.should_skip(fn) is True


# ---------------------------------------------------------------------------
# Tests: PropertyAccessorPairingCheck — runs on .TcPOU and .TcIO
# ---------------------------------------------------------------------------


def test_property_accessor_pairing_skips_function(tmp_path):
    """PropertyAccessorPairingCheck must skip FUNCTION subtypes."""
    fn = _make_function(tmp_path)
    check = PropertyAccessorPairingCheck()
    assert check.should_skip(fn) is True


def test_property_accessor_pairing_does_not_skip_function_block(tmp_path):
    """PropertyAccessorPairingCheck must NOT skip FUNCTION_BLOCK."""
    fb = _make_function_block(tmp_path)
    check = PropertyAccessorPairingCheck()
    assert check.should_skip(fb) is False


# ---------------------------------------------------------------------------
# Tests: _file_has_oop_keywords robustness (via check behaviour)
# ---------------------------------------------------------------------------


def test_extends_check_does_not_skip_fb_with_extra_whitespace_around_declaration(tmp_path):
    """_file_has_oop_keywords must not false-skip OOP FBs when <Declaration> has
    irregular surrounding whitespace or newlines (regression guard for the original
    bare-regex implementation that lacked the <POU ...> anchor).
    """
    path = tmp_path / "FB_Derived.TcPOU"
    # Deliberately add extra whitespace/newlines around Declaration and CDATA markers
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1">\n'
        '  <POU Name="FB_Derived" Id="{77777777-7777-7777-7777-777777777777}" SpecialFunc="None">\n'
        "    <Declaration>\n"
        "      <![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\n"
        "VAR END_VAR\n"
        "]]>\n"
        "    </Declaration>\n"
        "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
        "  </POU>\n"
        "</TcPlcObject>\n",
        encoding="utf-8",
    )
    fb = TwinCATFile(path)
    # ExtendsVisibilityCheck uses _file_has_oop_keywords — must NOT skip this file
    check = ExtendsVisibilityCheck()
    assert (
        check.should_skip(fb) is False
    ), "_file_has_oop_keywords should handle whitespace/newlines around <Declaration> CDATA"


def test_extends_check_does_not_false_positive_on_method_declaration_with_oop_word(tmp_path):
    """A method whose body text contains 'EXTENDS' must not make a plain FB appear OOP.

    _file_has_oop_keywords must scan only the POU-level declaration, not method
    Declaration blocks, to avoid false positives.
    """
    path = tmp_path / "FB_Plain.TcPOU"
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1">\n'
        '  <POU Name="FB_Plain" Id="{88888888-8888-8888-8888-888888888888}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Plain\nVAR END_VAR\n]]></Declaration>\n"
        "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
        '    <Method Name="M_Check" Id="{88888888-8888-8888-8888-888888888889}">\n'
        # Method declaration CDATA contains the word EXTENDS — must not trip up the check
        "      <Declaration><![CDATA[METHOD M_Check : BOOL\n"
        "(* This method EXTENDS the base behaviour *)\n"
        "END_VAR\n]]></Declaration>\n"
        "      <Implementation><ST><![CDATA[M_Check := TRUE;]]></ST></Implementation>\n"
        "    </Method>\n"
        "  </POU>\n"
        "</TcPlcObject>\n",
        encoding="utf-8",
    )
    fb = TwinCATFile(path)
    check = ExtendsVisibilityCheck()
    # Plain FB: POU declaration has no EXTENDS/IMPLEMENTS, should be skipped
    assert (
        check.should_skip(fb) is True
    ), "_file_has_oop_keywords must not match EXTENDS inside a method Declaration block"


# ---------------------------------------------------------------------------
# Sanity: all checks still reject non-TcPOU files
# ---------------------------------------------------------------------------

_ALL_TCPOU_CHECKS = (
    _EXTENDS_REQUIRING_CHECKS
    + _FB_ONLY_CHECKS
    + _FUNCTION_SKIP_CHECKS
    + [PolicyInterfaceContractIntegrityCheck, PropertyAccessorPairingCheck]
)


@pytest.mark.parametrize("check_class", _ALL_TCPOU_CHECKS)
def test_all_checks_skip_tcgvl_file(check_class, tmp_path):
    """All TcPOU-targeting OOP checks must still skip non-TcPOU extensions."""
    path = tmp_path / "GVL_Test.TcGVL"
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject><GVL Name="GVL_Test"><Declaration><![CDATA[VAR_GLOBAL END_VAR]]>'
        "</Declaration></GVL></TcPlcObject>\n",
        encoding="utf-8",
    )
    gvl = TwinCATFile(path)
    check = check_class()
    assert check.should_skip(gvl) is True
