"""Tests for twincat_validator.validators.oop_checks module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from twincat_validator.file_handler import TwinCATFile
from twincat_validator.validators.base import CheckRegistry
from twincat_validator.validators.oop_checks import (
    AbstractContractCheck,
    ExtendsVisibilityCheck,
    ExtendsCycleCheck,
    FbInitSignatureCheck,
    FbInitSuperCallCheck,
    InheritancePropertyContractCheck,
    InterfaceContractCheck,
    PolicyInterfaceContractIntegrityCheck,
    ThisPointerConsistencyCheck,
    OverrideMarkerCheck,
    OverrideSignatureCheck,
    OverrideSuperCallCheck,
)
from twincat_validator.validators.structure_checks import PouStructureInterfaceCheck


def _ensure_oop_checks_registered() -> None:
    for check_class in (
        AbstractContractCheck,
        ExtendsVisibilityCheck,
        ExtendsCycleCheck,
        FbInitSignatureCheck,
        FbInitSuperCallCheck,
        OverrideMarkerCheck,
        OverrideSignatureCheck,
        OverrideSuperCallCheck,
        InheritancePropertyContractCheck,
        InterfaceContractCheck,
        PolicyInterfaceContractIntegrityCheck,
        ThisPointerConsistencyCheck,
    ):
        if check_class.check_id not in CheckRegistry.get_all_checks():
            CheckRegistry.register(check_class)


def _write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _base_fb() -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <POU Name="FB_Base" Id="{11111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Base\n"
        "VAR\n"
        "  nPrivate : INT;\n"
        "  nShared : INT;\n"
        "END_VAR\n"
        "]]></Declaration>\n"
        "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
        '    <Method Name="M_Do" Id="{11111111-1111-1111-1111-111111111112}">\n'
        "      <Declaration><![CDATA[METHOD M_Do : BOOL\n"
        "VAR_INPUT\n"
        "  nTarget : INT;\n"
        "END_VAR\n"
        "]]></Declaration>\n"
        "      <Implementation><ST><![CDATA[M_Do := TRUE;]]></ST></Implementation>\n"
        "    </Method>\n"
        "  </POU>\n"
        "</TcPlcObject>\n"
    )


def _derived_fb(
    declaration_extra: str, method_decl: str, method_impl: str = "M_Do := TRUE;"
) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <POU Name="FB_Derived" Id="{22222222-2222-2222-2222-222222222222}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\n"
        f"{declaration_extra}"
        "]]></Declaration>\n"
        "    <Implementation><ST><![CDATA[nPrivate := 1;\n"
        "nShared := 2;]]></ST></Implementation>\n"
        '    <Method Name="M_Do" Id="{22222222-2222-2222-2222-222222222223}">\n'
        f"      <Declaration><![CDATA[{method_decl}\n]]></Declaration>\n"
        f"      <Implementation><ST><![CDATA[{method_impl}]]></ST></Implementation>\n"
        "    </Method>\n"
        "  </POU>\n"
        "</TcPlcObject>\n"
    )


class TestExtendsVisibilityCheck:
    @classmethod
    def setup_class(cls):
        _ensure_oop_checks_registered()

    def test_detects_private_member_access_from_derived(self, tmp_path):
        _write_file(tmp_path / "FB_Base.TcPOU", _base_fb())
        _write_file(
            tmp_path / "FB_Derived.TcPOU",
            _derived_fb("", "{attribute 'override'}\nMETHOD M_Do : BOOL"),
        )
        file = TwinCATFile(tmp_path / "FB_Derived.TcPOU")
        issues = ExtendsVisibilityCheck().run(file)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "nPrivate" in issues[0].message
        assert "nShared" in issues[0].message
        assert "VAR_PROTECTED" not in (issues[0].fix_suggestion or "")
        assert "METHOD PROTECTED" in (issues[0].fix_suggestion or "")


class TestOverrideMarkerCheck:
    @classmethod
    def setup_class(cls):
        _ensure_oop_checks_registered()

    def test_reports_missing_override_marker(self, tmp_path):
        _write_file(tmp_path / "FB_Base.TcPOU", _base_fb())
        _write_file(tmp_path / "FB_Derived.TcPOU", _derived_fb("", "METHOD M_Do : BOOL"))
        file = TwinCATFile(tmp_path / "FB_Derived.TcPOU")
        issues = OverrideMarkerCheck().run(file)

        assert len(issues) == 1
        assert "without explicit override marker" in issues[0].message

    def test_reports_noncanonical_method_override_keyword(self, tmp_path):
        _write_file(tmp_path / "FB_Base.TcPOU", _base_fb())
        _write_file(tmp_path / "FB_Derived.TcPOU", _derived_fb("", "METHOD OVERRIDE M_Do : BOOL"))
        file = TwinCATFile(tmp_path / "FB_Derived.TcPOU")
        issues = OverrideMarkerCheck().run(file)

        assert len(issues) == 1
        assert "Invalid METHOD OVERRIDE usage" in issues[0].message

    def test_detects_override_with_visibility_modifier(self, tmp_path):
        """Test that OVERRIDE keyword is detected even with visibility modifiers."""
        _write_file(tmp_path / "FB_Base.TcPOU", _base_fb())
        _write_file(
            tmp_path / "FB_Derived.TcPOU", _derived_fb("", "METHOD PUBLIC OVERRIDE M_Do : BOOL")
        )
        file = TwinCATFile(tmp_path / "FB_Derived.TcPOU")
        issues = OverrideMarkerCheck().run(file)

        assert len(issues) == 1
        assert "Invalid METHOD OVERRIDE usage" in issues[0].message

    def test_detects_override_with_multiple_modifiers(self, tmp_path):
        """Test that OVERRIDE keyword is detected with multiple modifiers."""
        _write_file(tmp_path / "FB_Base.TcPOU", _base_fb())
        _write_file(
            tmp_path / "FB_Derived.TcPOU", _derived_fb("", "METHOD PROTECTED OVERRIDE M_Do : BOOL")
        )
        file = TwinCATFile(tmp_path / "FB_Derived.TcPOU")
        issues = OverrideMarkerCheck().run(file)

        assert len(issues) == 1
        assert "Invalid METHOD OVERRIDE usage" in issues[0].message


class TestOverrideSignatureCheck:
    @classmethod
    def setup_class(cls):
        _ensure_oop_checks_registered()

    def test_detects_signature_mismatch(self, tmp_path):
        _write_file(tmp_path / "FB_Base.TcPOU", _base_fb())
        _write_file(
            tmp_path / "FB_Derived.TcPOU",
            _derived_fb(
                "",
                "{attribute 'override'}\nMETHOD M_Do : BOOL\nVAR_INPUT\n  nTarget : DINT;\nEND_VAR",
            ),
        )
        file = TwinCATFile(tmp_path / "FB_Derived.TcPOU")
        issues = OverrideSignatureCheck().run(file)

        assert len(issues) == 1
        assert "Override signature mismatch" in issues[0].message


class TestInterfaceContractCheck:
    @classmethod
    def setup_class(cls):
        _ensure_oop_checks_registered()

    def test_detects_missing_interface_members(self, tmp_path):
        _write_file(
            tmp_path / "I_Motor.TcIO",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <Itf Name="I_Motor" Id="{33333333-3333-3333-3333-333333333333}">\n'
                "    <Declaration><![CDATA[INTERFACE I_Motor\n]]></Declaration>\n"
                '    <Method Name="M_Reset" Id="{33333333-3333-3333-3333-333333333334}">\n'
                "      <Declaration><![CDATA[METHOD M_Reset : BOOL\n]]></Declaration>\n"
                "    </Method>\n"
                '    <Property Name="P_Healthy" Id="{33333333-3333-3333-3333-333333333335}">\n'
                "      <Declaration><![CDATA[PROPERTY P_Healthy : BOOL]]></Declaration>\n"
                '      <Get Name="Get" Id="{33333333-3333-3333-3333-333333333336}">\n'
                "        <Declaration><![CDATA[]]></Declaration>\n"
                "      </Get>\n"
                "    </Property>\n"
                "  </Itf>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_Impl.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Impl" Id="{44444444-4444-4444-4444-444444444444}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Impl IMPLEMENTS I_Motor\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        file = TwinCATFile(tmp_path / "FB_Impl.TcPOU")
        issues = InterfaceContractCheck().run(file)

        assert len(issues) == 1
        assert "missing method M_Reset" in issues[0].message
        assert "missing property P_Healthy" in issues[0].message

    def test_detects_interface_signature_and_accessor_mismatch(self, tmp_path):
        _write_file(
            tmp_path / "I_State.TcIO",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <Itf Name="I_State" Id="{55555555-5555-5555-5555-555555555555}">\n'
                "    <Declaration><![CDATA[INTERFACE I_State\n]]></Declaration>\n"
                '    <Method Name="M_Set" Id="{55555555-5555-5555-5555-555555555556}">\n'
                "      <Declaration><![CDATA[METHOD M_Set : BOOL\nVAR_INPUT\n"
                "  nMode : INT;\nEND_VAR\n]]></Declaration>\n"
                "    </Method>\n"
                '    <Property Name="P_Mode" Id="{55555555-5555-5555-5555-555555555557}">\n'
                "      <Declaration><![CDATA[PROPERTY P_Mode : INT]]></Declaration>\n"
                '      <Get Name="Get" Id="{55555555-5555-5555-5555-555555555558}">'
                "<Declaration><![CDATA[]]></Declaration></Get>\n"
                '      <Set Name="Set" Id="{55555555-5555-5555-5555-555555555559}">'
                "<Declaration><![CDATA[]]></Declaration></Set>\n"
                "    </Property>\n"
                "  </Itf>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_State.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_State" Id="{66666666-6666-6666-6666-666666666666}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_State IMPLEMENTS I_State\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_Set" Id="{66666666-6666-6666-6666-666666666667}">\n'
                "      <Declaration><![CDATA[METHOD M_Set : BOOL\nVAR_INPUT\n"
                "  nMode : DINT;\nEND_VAR\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[M_Set := TRUE;]]></ST></Implementation>\n"
                "    </Method>\n"
                '    <Property Name="P_Mode" Id="{66666666-6666-6666-6666-666666666668}">\n'
                "      <Declaration><![CDATA[PROPERTY P_Mode : DINT]]></Declaration>\n"
                '      <Get Name="Get" Id="{66666666-6666-6666-6666-666666666669}">\n'
                "        <Declaration><![CDATA[]]></Declaration>\n"
                "        <Implementation><ST><![CDATA[P_Mode := 0;]]></ST></Implementation>\n"
                "      </Get>\n"
                "    </Property>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        file = TwinCATFile(tmp_path / "FB_State.TcPOU")
        issues = InterfaceContractCheck().run(file)

        assert len(issues) == 1
        assert "signature mismatch M_Set" in issues[0].message
        assert "property type mismatch P_Mode" in issues[0].message
        assert "accessor mismatch P_Mode" in issues[0].message

    def test_checks_inherited_interface_contract_from_base(self, tmp_path):
        _write_file(
            tmp_path / "I_Diag.TcIO",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <Itf Name="I_Diag" Id="{55666666-6666-6666-6666-666666666666}">\n'
                "    <Declaration><![CDATA[INTERFACE I_Diag\n]]></Declaration>\n"
                '    <Method Name="M_GetFaultCode" Id="{55666666-6666-6666-6666-666666666667}">\n'
                "      <Declaration><![CDATA[METHOD M_GetFaultCode : INT\n]]></Declaration>\n"
                "    </Method>\n"
                "  </Itf>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_Base.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Base" Id="{55777777-7777-7777-7777-777777777777}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Base IMPLEMENTS I_Diag\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_GetFaultCode" Id="{55777777-7777-7777-7777-777777777778}">\n'
                "      <Declaration><![CDATA[METHOD M_GetFaultCode : INT\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[M_GetFaultCode := 0;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_Derived.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Derived" Id="{55888888-8888-8888-8888-888888888888}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_GetFaultCode" Id="{55888888-8888-8888-8888-888888888889}">\n'
                "      <Declaration><![CDATA[{attribute 'override'}\n"
                "METHOD M_GetFaultCode : DINT\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[M_GetFaultCode := 1;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = InterfaceContractCheck().run(TwinCATFile(tmp_path / "FB_Derived.TcPOU"))
        assert len(issues) == 1
        assert "signature mismatch M_GetFaultCode" in issues[0].message

    def test_structure_and_oop_interface_checks_agree_on_inherited_ok(self, tmp_path):
        _write_file(
            tmp_path / "I_Common.TcIO",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <Itf Name="I_Common" Id="{55999999-9999-9999-9999-999999999991}">\n'
                "    <Declaration><![CDATA[INTERFACE I_Common\n]]></Declaration>\n"
                '    <Method Name="M_Read" Id="{55999999-9999-9999-9999-999999999992}">\n'
                "      <Declaration><![CDATA[METHOD M_Read : INT\n]]></Declaration>\n"
                "    </Method>\n"
                "  </Itf>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_BaseCommon.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_BaseCommon" Id="{55999999-9999-9999-9999-999999999993}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_BaseCommon IMPLEMENTS I_Common\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_Read" Id="{55999999-9999-9999-9999-999999999994}">\n'
                "      <Declaration><![CDATA[METHOD M_Read : INT\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[M_Read := 1;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_DerivedCommon.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_DerivedCommon" Id="{55999999-9999-9999-9999-999999999995}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_DerivedCommon EXTENDS FB_BaseCommon IMPLEMENTS I_Common\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        file = TwinCATFile(tmp_path / "FB_DerivedCommon.TcPOU")
        issues_oop = InterfaceContractCheck().run(file)
        issues_structure = PouStructureInterfaceCheck().run(file)
        assert issues_oop == []
        assert issues_structure == []


class TestExtendsCycleCheck:
    @classmethod
    def setup_class(cls):
        _ensure_oop_checks_registered()

    def test_detects_extends_cycle(self, tmp_path):
        _write_file(
            tmp_path / "FB_A.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_A" Id="{77777777-7777-7777-7777-777777777777}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_A EXTENDS FB_B\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_B.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_B" Id="{88888888-8888-8888-8888-888888888888}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_B EXTENDS FB_A\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        issues = ExtendsCycleCheck().run(TwinCATFile(tmp_path / "FB_A.TcPOU"))
        assert len(issues) == 1
        assert "Cyclic EXTENDS hierarchy detected" in issues[0].message


class TestOverrideSuperCallCheck:
    @classmethod
    def setup_class(cls):
        _ensure_oop_checks_registered()

    def test_detects_missing_super_call_for_lifecycle_override(self, tmp_path):
        (tmp_path / ".twincat-validator.json").write_text(
            (
                "{\n"
                '  "oop_policy": {\n'
                '    "enforce_override_super_call": true,\n'
                '    "required_super_methods": ["M_Start"]\n'
                "  }\n"
                "}\n"
            ),
            encoding="utf-8",
        )
        _write_file(
            tmp_path / "FB_Base.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Base" Id="{99999999-9999-9999-9999-999999999999}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Base\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_Start" Id="{99999999-9999-9999-9999-999999999998}">\n'
                "      <Declaration><![CDATA[METHOD M_Start : BOOL\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[M_Start := TRUE;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_Derived.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Derived" Id="{aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_Start" Id="{aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab}">\n'
                "      <Declaration><![CDATA[{attribute 'override'}\n"
                "METHOD M_Start : BOOL\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[M_Start := TRUE;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = OverrideSuperCallCheck().run(TwinCATFile(tmp_path / "FB_Derived.TcPOU"))
        assert len(issues) == 1
        assert "missing required base call" in issues[0].message

    def test_allows_super_call_for_lifecycle_override(self, tmp_path):
        (tmp_path / ".twincat-validator.json").write_text(
            (
                "{\n"
                '  "oop_policy": {\n'
                '    "enforce_override_super_call": true,\n'
                '    "required_super_methods": ["M_Start"]\n'
                "  }\n"
                "}\n"
            ),
            encoding="utf-8",
        )
        _write_file(
            tmp_path / "FB_Base.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Base" Id="{dddddddd-dddd-dddd-dddd-dddddddddddd}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Base\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_Start" Id="{dddddddd-dddd-dddd-dddd-ddddddddddde}">\n'
                "      <Declaration><![CDATA[METHOD M_Start : BOOL\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[M_Start := TRUE;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_Derived.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Derived" Id="{eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_Start" Id="{eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeef}">\n'
                "      <Declaration><![CDATA[{attribute 'override'}\n"
                "METHOD M_Start : BOOL\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[M_Start := SUPER^.M_Start();]]></ST>"
                "</Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = OverrideSuperCallCheck().run(TwinCATFile(tmp_path / "FB_Derived.TcPOU"))
        assert len(issues) == 0

    def test_respects_project_policy_when_super_call_enforcement_disabled(self, tmp_path):
        (tmp_path / ".twincat-validator.json").write_text(
            (
                "{\n"
                '  "oop_policy": {\n'
                '    "enforce_override_super_call": false\n'
                "  }\n"
                "}\n"
            ),
            encoding="utf-8",
        )
        _write_file(
            tmp_path / "FB_Base.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Base" Id="{deadbeef-dead-beef-dead-beef00000001}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Base\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_Start" Id="{deadbeef-dead-beef-dead-beef00000002}">\n'
                "      <Declaration><![CDATA[METHOD M_Start : BOOL\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[M_Start := TRUE;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_Derived.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Derived" Id="{deadbeef-dead-beef-dead-beef00000003}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_Start" Id="{deadbeef-dead-beef-dead-beef00000004}">\n'
                "      <Declaration><![CDATA[{attribute 'override'}\n"
                "METHOD M_Start : BOOL\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[M_Start := TRUE;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = OverrideSuperCallCheck().run(TwinCATFile(tmp_path / "FB_Derived.TcPOU"))
        assert issues == []


class TestInheritancePropertyContractCheck:
    @classmethod
    def setup_class(cls):
        _ensure_oop_checks_registered()

    def test_detects_property_mutability_mismatch_vs_base(self, tmp_path):
        _write_file(
            tmp_path / "FB_Base.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Base" Id="{bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Base\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Property Name="P_Mode" Id="{bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbc}">\n'
                "      <Declaration><![CDATA[PROPERTY P_Mode : INT]]></Declaration>\n"
                '      <Get Name="Get" Id="{bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbd}">'
                "<Declaration><![CDATA[]]></Declaration></Get>\n"
                '      <Set Name="Set" Id="{bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbe}">'
                "<Declaration><![CDATA[]]></Declaration></Set>\n"
                "    </Property>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_Derived.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Derived" Id="{cccccccc-cccc-cccc-cccc-cccccccccccc}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Property Name="P_Mode" Id="{cccccccc-cccc-cccc-cccc-cccccccccccd}">\n'
                "      <Declaration><![CDATA[PROPERTY P_Mode : DINT]]></Declaration>\n"
                '      <Get Name="Get" Id="{cccccccc-cccc-cccc-cccc-ccccccccccce}">'
                "<Declaration><![CDATA[]]></Declaration></Get>\n"
                "    </Property>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = InheritancePropertyContractCheck().run(TwinCATFile(tmp_path / "FB_Derived.TcPOU"))
        assert len(issues) == 1
        assert "property contract mismatch" in issues[0].message.lower()


class TestFbInitChecks:
    @classmethod
    def setup_class(cls):
        _ensure_oop_checks_registered()

    def test_fb_init_signature_detects_invalid_prefix(self, tmp_path):
        _write_file(
            tmp_path / "FB_InitBad.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_InitBad" Id="{f1111111-1111-1111-1111-111111111111}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_InitBad\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="FB_init" Id="{f1111111-1111-1111-1111-111111111112}">\n'
                "      <Declaration><![CDATA[METHOD FB_init : BOOL\nVAR_INPUT\n"
                "  nMode : INT;\nEND_VAR\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[FB_init := TRUE;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = FbInitSignatureCheck().run(TwinCATFile(tmp_path / "FB_InitBad.TcPOU"))
        assert len(issues) == 1
        assert "FB_init signature/return type mismatch" in issues[0].message

    def test_fb_init_super_call_required_when_base_has_fb_init(self, tmp_path):
        _write_file(
            tmp_path / "FB_Base.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Base" Id="{f2222222-2222-2222-2222-222222222221}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Base\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="FB_init" Id="{f2222222-2222-2222-2222-222222222222}">\n'
                "      <Declaration><![CDATA[METHOD FB_init : BOOL\nVAR_INPUT\n"
                "  bInitRetains : BOOL;\n  bInCopyCode : BOOL;\nEND_VAR\n"
                "]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[FB_init := TRUE;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_Derived.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Derived" Id="{f2222222-2222-2222-2222-222222222223}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="FB_init" Id="{f2222222-2222-2222-2222-222222222224}">\n'
                "      <Declaration><![CDATA[{attribute 'override'}\nMETHOD FB_init : BOOL\n"
                "VAR_INPUT\n"
                "  bInitRetains : BOOL;\n"
                "  bInCopyCode : BOOL;\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[FB_init := TRUE;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = FbInitSuperCallCheck().run(TwinCATFile(tmp_path / "FB_Derived.TcPOU"))
        assert len(issues) == 1
        assert "does not call SUPER^.FB_init" in issues[0].message

    def test_fb_init_super_call_ok_when_present(self, tmp_path):
        _write_file(
            tmp_path / "FB_Base.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Base" Id="{f3333333-3333-3333-3333-333333333331}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Base\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="FB_init" Id="{f3333333-3333-3333-3333-333333333332}">\n'
                "      <Declaration><![CDATA[METHOD FB_init : BOOL\nVAR_INPUT\n"
                "  bInitRetains : BOOL;\n  bInCopyCode : BOOL;\nEND_VAR\n"
                "]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[FB_init := TRUE;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_Derived.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Derived" Id="{f3333333-3333-3333-3333-333333333333}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="FB_init" Id="{f3333333-3333-3333-3333-333333333334}">\n'
                "      <Declaration><![CDATA[{attribute 'override'}\nMETHOD FB_init : BOOL\n"
                "VAR_INPUT\n"
                "  bInitRetains : BOOL;\n"
                "  bInCopyCode : BOOL;\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[FB_init := SUPER^.FB_init(\n"
                "  bInitRetains := bInitRetains,\n"
                "  bInCopyCode := bInCopyCode\n"
                ");]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = FbInitSuperCallCheck().run(TwinCATFile(tmp_path / "FB_Derived.TcPOU"))
        assert len(issues) == 0


class TestThisPointerConsistencyCheck:
    @classmethod
    def setup_class(cls):
        _ensure_oop_checks_registered()

    def test_detects_shadowed_member_write_without_this(self, tmp_path):
        _write_file(
            tmp_path / "FB_Shadow.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Shadow" Id="{f4444444-4444-4444-4444-444444444444}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Shadow\n"
                "VAR\n"
                "  nCount : INT;\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_Inc" Id="{f4444444-4444-4444-4444-444444444445}">\n'
                "      <Declaration><![CDATA[METHOD M_Inc : BOOL\nVAR\n"
                "  nCount : INT;\nEND_VAR\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[nCount := nCount + 1;\n"
                "M_Inc := TRUE;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = ThisPointerConsistencyCheck().run(TwinCATFile(tmp_path / "FB_Shadow.TcPOU"))
        assert len(issues) == 1
        assert "Ambiguous local/member shadowing" in issues[0].message


class TestAbstractContractCheck:
    @classmethod
    def setup_class(cls):
        _ensure_oop_checks_registered()

    def test_abstract_method_with_implementation_is_rejected(self, tmp_path):
        _write_file(
            tmp_path / "FB_AbstractBad.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_AbstractBad" Id="{f5555555-5555-5555-5555-555555555555}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK ABSTRACT FB_AbstractBad\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_Run" Id="{f5555555-5555-5555-5555-555555555556}">\n'
                "      <Declaration><![CDATA[METHOD ABSTRACT M_Run : BOOL\n"
                "]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[M_Run := TRUE;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = AbstractContractCheck().run(TwinCATFile(tmp_path / "FB_AbstractBad.TcPOU"))
        assert len(issues) == 1
        assert "must not include executable implementation" in issues[0].message

    def test_concrete_class_missing_inherited_abstract_method(self, tmp_path):
        _write_file(
            tmp_path / "FB_Base.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Base" Id="{f6666666-6666-6666-6666-666666666661}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK ABSTRACT FB_Base\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_Run" Id="{f6666666-6666-6666-6666-666666666662}">\n'
                "      <Declaration><![CDATA[METHOD ABSTRACT M_Run : BOOL\n"
                "]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_Derived.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Derived" Id="{f6666666-6666-6666-6666-666666666663}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = AbstractContractCheck().run(TwinCATFile(tmp_path / "FB_Derived.TcPOU"))
        assert len(issues) == 1
        assert "does not implement inherited abstract method(s)" in issues[0].message

    def test_concrete_class_with_abstract_method_is_rejected(self, tmp_path):
        _write_file(
            tmp_path / "FB_ConcreteBad.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_ConcreteBad" Id="{f7777777-7777-7777-7777-777777777771}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_ConcreteBad\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_Run" Id="{f7777777-7777-7777-7777-777777777772}">\n'
                "      <Declaration><![CDATA[METHOD ABSTRACT M_Run : BOOL\n"
                "]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = AbstractContractCheck().run(TwinCATFile(tmp_path / "FB_ConcreteBad.TcPOU"))
        assert len(issues) == 1
        assert "Concrete FUNCTION_BLOCK declares abstract method(s)" in issues[0].message

    def test_keyword_only_abstract_style_is_accepted(self, tmp_path):
        _write_file(
            tmp_path / "FB_AbstractKeyword.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_AbstractKeyword" Id="{f8888888-8888-8888-8888-888888888884}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK ABSTRACT FB_AbstractKeyword\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_Run" Id="{f8888888-8888-8888-8888-888888888885}">\n'
                "      <Declaration><![CDATA[METHOD ABSTRACT M_Run : BOOL\n"
                "]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = AbstractContractCheck().run(TwinCATFile(tmp_path / "FB_AbstractKeyword.TcPOU"))
        assert not issues

    def test_abstract_base_false_stub_methods_are_rejected(self, tmp_path):
        _write_file(
            tmp_path / "FB_AbstractStub.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_AbstractStub" Id="{f8888888-8888-8888-8888-888888888886}" '
                'SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK ABSTRACT FB_AbstractStub\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_Execute" Id="{f8888888-8888-8888-8888-888888888887}">\n'
                "      <Declaration><![CDATA[METHOD M_Execute : BOOL\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[M_Execute := FALSE;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = AbstractContractCheck().run(TwinCATFile(tmp_path / "FB_AbstractStub.TcPOU"))
        assert any("trivial FALSE stub method(s)" in i.message for i in issues)


class TestPolicyInterfaceContractIntegrityCheck:
    @classmethod
    def setup_class(cls):
        _ensure_oop_checks_registered()

    def test_flags_contract_weakening_for_abstract_base(self, tmp_path):
        _write_file(
            tmp_path / "I_MotorControl.TcIO",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <Itf Name="I_MotorControl" Id="{91111111-1111-1111-1111-111111111111}">\n'
                "    <Declaration><![CDATA[INTERFACE I_MotorControl\n]]></Declaration>\n"
                '    <Method Name="M_SetSpeed" Id="{91111111-1111-1111-1111-111111111112}">\n'
                "      <Declaration><![CDATA[METHOD M_SetSpeed : BOOL\nVAR_INPUT\n"
                "  rSpeedRpm : LREAL;\nEND_VAR\n]]></Declaration>\n"
                "    </Method>\n"
                '    <Method Name="M_GetTelemetry" Id="{91111111-1111-1111-1111-111111111113}">\n'
                "      <Declaration><![CDATA[METHOD M_GetTelemetry : BOOL\n]]></Declaration>\n"
                "    </Method>\n"
                "  </Itf>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_MotorBase.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_MotorBase" Id="{92222222-2222-2222-2222-222222222222}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK ABSTRACT FB_MotorBase\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_SetSpeed" Id="{92222222-2222-2222-2222-222222222223}">\n'
                "      <Declaration><![CDATA[METHOD ABSTRACT M_SetSpeed : BOOL\nVAR_INPUT\n"
                "  rSpeedRpm : LREAL;\nEND_VAR\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                "    </Method>\n"
                '    <Method Name="M_GetTelemetry" Id="{92222222-2222-2222-2222-222222222224}">\n'
                "      <Declaration><![CDATA[METHOD ABSTRACT M_GetTelemetry : BOOL\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_ServoMotor.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_ServoMotor" Id="{93333333-3333-3333-3333-333333333333}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_ServoMotor EXTENDS FB_MotorBase\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        issues = PolicyInterfaceContractIntegrityCheck().run(
            TwinCATFile(tmp_path / "FB_MotorBase.TcPOU")
        )
        assert len(issues) == 1
        assert issues[0].category == "policy_enforcement"
        assert "enforce_interface_contract_integrity" in issues[0].message

    def test_policy_override_disables_integrity_guard(self, tmp_path):
        (tmp_path / ".twincat-validator.json").write_text(
            '{\n  "oop_policy": {"enforce_interface_contract_integrity": false}\n}\n',
            encoding="utf-8",
        )
        _write_file(
            tmp_path / "I_MotorControl.TcIO",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <Itf Name="I_MotorControl" Id="{94111111-1111-1111-1111-111111111111}">\n'
                "    <Declaration><![CDATA[INTERFACE I_MotorControl\n]]></Declaration>\n"
                '    <Method Name="M_SetSpeed" Id="{94111111-1111-1111-1111-111111111112}">\n'
                "      <Declaration><![CDATA[METHOD M_SetSpeed : BOOL\n]]></Declaration>\n"
                "    </Method>\n"
                "  </Itf>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_MotorBase.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_MotorBase" Id="{94222222-2222-2222-2222-222222222222}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK ABSTRACT FB_MotorBase\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_SetSpeed" Id="{94222222-2222-2222-2222-222222222223}">\n'
                "      <Declaration><![CDATA[METHOD ABSTRACT M_SetSpeed : BOOL\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_ServoMotor.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_ServoMotor" Id="{94333333-3333-3333-3333-333333333333}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_ServoMotor EXTENDS FB_MotorBase\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        issues = PolicyInterfaceContractIntegrityCheck().run(
            TwinCATFile(tmp_path / "FB_MotorBase.TcPOU")
        )
        assert issues == []
