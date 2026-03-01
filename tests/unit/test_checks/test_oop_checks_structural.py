"""Tests for Phase 5C OOP checks: abstract_instantiation, property_accessor_pairing, method_count."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from twincat_validator.file_handler import TwinCATFile
from twincat_validator.validators.oop_checks import (
    AbstractInstantiationCheck,
    MethodCountCheck,
    PropertyAccessorPairingCheck,
)


def _write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


class TestAbstractInstantiationCheck:
    """Tests for abstract_instantiation check (critical - prevents runtime crashes)."""

    def test_pass_when_no_new_calls(self, tmp_path):
        """Test that FBs without __NEW() calls pass."""
        _write_file(
            tmp_path / "FB_Normal.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Normal" Id="{a1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Normal\n"
                "VAR\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation>\n"
                "      <ST><![CDATA[// No __NEW() calls here]]></ST>\n"
                "    </Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        check = AbstractInstantiationCheck()
        issues = check.run(TwinCATFile(tmp_path / "FB_Normal.TcPOU"))
        assert len(issues) == 0

    def test_pass_when_instantiating_concrete_fb(self, tmp_path):
        """Test that instantiating concrete FBs is allowed."""
        # Create concrete FB
        _write_file(
            tmp_path / "FB_Concrete.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Concrete" Id="{a1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[{attribute 'enable_dynamic_creation'}\n"
                "FUNCTION_BLOCK FB_Concrete\n"
                "VAR\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation>\n"
                "      <ST><![CDATA[]]></ST>\n"
                "    </Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        # Create FB that instantiates the concrete FB
        _write_file(
            tmp_path / "FB_User.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_User" Id="{a2222222-2222-2222-2222-222222222222}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_User\n"
                "VAR\n"
                "  pInstance : POINTER TO FB_Concrete;\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation>\n"
                "      <ST><![CDATA[pInstance := __NEW(FB_Concrete);]]></ST>\n"
                "    </Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        check = AbstractInstantiationCheck()
        issues = check.run(TwinCATFile(tmp_path / "FB_User.TcPOU"))
        assert len(issues) == 0

    def test_critical_when_instantiating_abstract_fb(self, tmp_path):
        """Test that instantiating abstract FBs triggers critical error."""
        # Create abstract FB
        _write_file(
            tmp_path / "FB_AbstractBase.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_AbstractBase" Id="{a1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK ABSTRACT FB_AbstractBase\n"
                "VAR\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation>\n"
                "      <ST><![CDATA[]]></ST>\n"
                "    </Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        # Create FB that tries to instantiate abstract FB
        _write_file(
            tmp_path / "FB_Buggy.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Buggy" Id="{a2222222-2222-2222-2222-222222222222}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Buggy\n"
                "VAR\n"
                "  pBase : POINTER TO FB_AbstractBase;\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation>\n"
                "      <ST><![CDATA[pBase := __NEW(FB_AbstractBase); // This will crash!]]></ST>\n"
                "    </Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        check = AbstractInstantiationCheck()
        issues = check.run(TwinCATFile(tmp_path / "FB_Buggy.TcPOU"))

        assert len(issues) == 1
        assert issues[0].severity == "critical"
        assert "Abstract instantiation" in issues[0].message
        assert "FB_AbstractBase" in issues[0].message
        assert issues[0].fix_available is False

    def test_detects_abstract_instantiation_in_method(self, tmp_path):
        """Test that abstract instantiation in methods is also detected."""
        _write_file(
            tmp_path / "FB_AbstractEngine.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_AbstractEngine" Id="{a1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK ABSTRACT FB_AbstractEngine\n"
                "VAR\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation>\n"
                "      <ST><![CDATA[]]></ST>\n"
                "    </Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        _write_file(
            tmp_path / "FB_Factory.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Factory" Id="{a2222222-2222-2222-2222-222222222222}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Factory\n"
                "VAR\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation>\n"
                "      <ST><![CDATA[]]></ST>\n"
                "    </Implementation>\n"
                '    <Method Name="CreateEngine" Id="{a3333333-3333-3333-3333-333333333333}">\n'
                "      <Declaration><![CDATA[METHOD CreateEngine : POINTER TO FB_AbstractEngine\n"
                "VAR\nEND_VAR\n"
                "]]></Declaration>\n"
                "      <Implementation>\n"
                "        <ST><![CDATA[CreateEngine := __NEW(FB_AbstractEngine);]]></ST>\n"
                "      </Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        check = AbstractInstantiationCheck()
        issues = check.run(TwinCATFile(tmp_path / "FB_Factory.TcPOU"))

        assert len(issues) == 1
        assert issues[0].severity == "critical"
        assert "FB_Factory.CreateEngine" in issues[0].message

    def test_ignores_new_in_comments(self, tmp_path):
        """Test that __NEW() in comments is ignored."""
        _write_file(
            tmp_path / "FB_AbstractBase.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_AbstractBase" Id="{a1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK ABSTRACT FB_AbstractBase\n"
                "VAR\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation>\n"
                "      <ST><![CDATA[]]></ST>\n"
                "    </Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        _write_file(
            tmp_path / "FB_Safe.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Safe" Id="{a2222222-2222-2222-2222-222222222222}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Safe\n"
                "VAR\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation>\n"
                "      <ST><![CDATA[\n"
                "// Don't do this: pBase := __NEW(FB_AbstractBase);\n"
                "(* Also bad: pBase := __NEW(FB_AbstractBase); *)\n"
                "]]></ST>\n"
                "    </Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        check = AbstractInstantiationCheck()
        issues = check.run(TwinCATFile(tmp_path / "FB_Safe.TcPOU"))
        assert len(issues) == 0


class TestPropertyAccessorPairingCheck:
    """Tests for property_accessor_pairing check (warning - completeness)."""

    def test_pass_when_properties_fully_paired(self, tmp_path):
        """Test that properties with both getter and setter pass."""
        _write_file(
            tmp_path / "FB_Complete.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Complete" Id="{a1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Complete\n"
                "VAR\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation>\n"
                "      <ST><![CDATA[]]></ST>\n"
                "    </Implementation>\n"
                '    <Property Name="P_Value" Id="{a2222222-2222-2222-2222-222222222222}">\n'
                "      <Declaration><![CDATA[PROPERTY P_Value : INT]]></Declaration>\n"
                '      <Get Name="Get" Id="{a3333333-3333-3333-3333-333333333333}">\n'
                "        <Declaration><![CDATA[]]></Declaration>\n"
                "      </Get>\n"
                '      <Set Name="Set" Id="{a4444444-4444-4444-4444-444444444444}">\n'
                "        <Declaration><![CDATA[]]></Declaration>\n"
                "      </Set>\n"
                "    </Property>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        check = PropertyAccessorPairingCheck()
        issues = check.run(TwinCATFile(tmp_path / "FB_Complete.TcPOU"))
        assert len(issues) == 0

    def test_pass_when_readonly_allowed(self, tmp_path):
        """Test that read-only properties pass when allowed by policy (default)."""
        _write_file(
            tmp_path / "FB_ReadOnly.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_ReadOnly" Id="{a1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_ReadOnly\n"
                "VAR\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation>\n"
                "      <ST><![CDATA[]]></ST>\n"
                "    </Implementation>\n"
                '    <Property Name="P_Status" Id="{a2222222-2222-2222-2222-222222222222}">\n'
                "      <Declaration><![CDATA[PROPERTY P_Status : STRING]]></Declaration>\n"
                '      <Get Name="Get" Id="{a3333333-3333-3333-3333-333333333333}">\n'
                "        <Declaration><![CDATA[]]></Declaration>\n"
                "      </Get>\n"
                "    </Property>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        check = PropertyAccessorPairingCheck()
        issues = check.run(TwinCATFile(tmp_path / "FB_ReadOnly.TcPOU"))
        # Default policy allows read-only
        assert len(issues) == 0

    def test_warn_when_writeonly_by_default(self, tmp_path):
        """Test that write-only properties warn (writeonly not allowed by default)."""
        _write_file(
            tmp_path / "FB_WriteOnly.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_WriteOnly" Id="{a1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_WriteOnly\n"
                "VAR\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation>\n"
                "      <ST><![CDATA[]]></ST>\n"
                "    </Implementation>\n"
                '    <Property Name="P_Command" Id="{a2222222-2222-2222-2222-222222222222}">\n'
                "      <Declaration><![CDATA[PROPERTY P_Command : INT]]></Declaration>\n"
                '      <Set Name="Set" Id="{a3333333-3333-3333-3333-333333333333}">\n'
                "        <Declaration><![CDATA[]]></Declaration>\n"
                "      </Set>\n"
                "    </Property>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        check = PropertyAccessorPairingCheck()
        issues = check.run(TwinCATFile(tmp_path / "FB_WriteOnly.TcPOU"))

        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert "Unpaired property accessor" in issues[0].message
        assert "P_Command" in issues[0].message
        assert "write-only" in issues[0].message

    def test_works_with_interfaces(self, tmp_path):
        """Test that check works with interface properties too."""
        _write_file(
            tmp_path / "I_Motor.TcIO",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <Itf Name="I_Motor" Id="{a1111111-1111-1111-1111-111111111111}">\n'
                "    <Declaration><![CDATA[INTERFACE I_Motor\n]]></Declaration>\n"
                '    <Property Name="P_Speed" Id="{a2222222-2222-2222-2222-222222222222}">\n'
                "      <Declaration><![CDATA[PROPERTY P_Speed : REAL]]></Declaration>\n"
                '      <Get Name="Get" Id="{a3333333-3333-3333-3333-333333333333}">\n'
                "        <Declaration><![CDATA[]]></Declaration>\n"
                "      </Get>\n"
                "    </Property>\n"
                "  </Itf>\n"
                "</TcPlcObject>\n"
            ),
        )

        check = PropertyAccessorPairingCheck()
        issues = check.run(TwinCATFile(tmp_path / "I_Motor.TcIO"))
        # Read-only is allowed by default
        assert len(issues) == 0

    def test_detects_multiple_unpaired_properties(self, tmp_path):
        """Test that multiple unpaired properties are all reported."""
        _write_file(
            tmp_path / "FB_Incomplete.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Incomplete" Id="{a1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Incomplete\n"
                "VAR\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation>\n"
                "      <ST><![CDATA[]]></ST>\n"
                "    </Implementation>\n"
                '    <Property Name="P_SetOnly1" Id="{a2222222-2222-2222-2222-222222222222}">\n'
                "      <Declaration><![CDATA[PROPERTY P_SetOnly1 : INT]]></Declaration>\n"
                '      <Set Name="Set" Id="{a3333333-3333-3333-3333-333333333333}">\n'
                "        <Declaration><![CDATA[]]></Declaration>\n"
                "      </Set>\n"
                "    </Property>\n"
                '    <Property Name="P_SetOnly2" Id="{a4444444-4444-4444-4444-444444444444}">\n'
                "      <Declaration><![CDATA[PROPERTY P_SetOnly2 : BOOL]]></Declaration>\n"
                '      <Set Name="Set" Id="{a5555555-5555-5555-5555-555555555555}">\n'
                "        <Declaration><![CDATA[]]></Declaration>\n"
                "      </Set>\n"
                "    </Property>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        check = PropertyAccessorPairingCheck()
        issues = check.run(TwinCATFile(tmp_path / "FB_Incomplete.TcPOU"))

        assert len(issues) == 1
        assert "P_SetOnly1" in issues[0].message
        assert "P_SetOnly2" in issues[0].message


class TestMethodCountCheck:
    """Tests for method_count check (warning - SRP guidance)."""

    def test_pass_when_member_count_at_default_limit(self, tmp_path):
        """Default max_methods_per_pou is 15 and should pass at the boundary."""
        methods = ""
        for i in range(10):
            methods += (
                f'    <Method Name="M_Task{i}" Id="{{b{i}{i}{i}{i}{i}{i}{i}{i}-1111-1111-1111-111111111111}}">\n'
                f"      <Declaration><![CDATA[METHOD M_Task{i} : BOOL\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[M_Task0 := TRUE;]]></ST></Implementation>\n"
                "    </Method>\n"
            )

        properties = ""
        for i in range(5):
            properties += (
                f'    <Property Name="P_Value{i}" Id="{{c{i}{i}{i}{i}{i}{i}{i}{i}-2222-2222-2222-222222222222}}">\n'
                f"      <Declaration><![CDATA[PROPERTY P_Value{i} : INT]]></Declaration>\n"
                f'      <Get Name="Get" Id="{{d{i}{i}{i}{i}{i}{i}{i}{i}-3333-3333-3333-333333333333}}">\n'
                "        <Declaration><![CDATA[]]></Declaration>\n"
                "      </Get>\n"
                "    </Property>\n"
            )

        _write_file(
            tmp_path / "FB_AtLimit.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_AtLimit" Id="{a1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_AtLimit\nEND_VAR\n]]></Declaration>\n"
                f"{methods}"
                f"{properties}"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        issues = MethodCountCheck().run(TwinCATFile(tmp_path / "FB_AtLimit.TcPOU"))
        assert len(issues) == 0

    def test_warn_when_member_count_exceeds_default_limit(self, tmp_path):
        """Warn when methods + properties > 15 by default."""
        methods = ""
        for i in range(12):
            methods += (
                f'    <Method Name="M_Work{i}" Id="{{e{i}{i}{i}{i}{i}{i}{i}{i}-1111-1111-1111-111111111111}}">\n'
                f"      <Declaration><![CDATA[METHOD M_Work{i} : BOOL\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[M_Work0 := TRUE;]]></ST></Implementation>\n"
                "    </Method>\n"
            )

        properties = ""
        for i in range(4):
            properties += (
                f'    <Property Name="P_Stat{i}" Id="{{f{i}{i}{i}{i}{i}{i}{i}{i}-2222-2222-2222-222222222222}}">\n'
                f"      <Declaration><![CDATA[PROPERTY P_Stat{i} : INT]]></Declaration>\n"
                f'      <Get Name="Get" Id="{{a{i}{i}{i}{i}{i}{i}{i}{i}-3333-3333-3333-333333333333}}">\n'
                "        <Declaration><![CDATA[]]></Declaration>\n"
                "      </Get>\n"
                "    </Property>\n"
            )

        _write_file(
            tmp_path / "FB_TooLarge.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_TooLarge" Id="{a2222222-2222-2222-2222-222222222222}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_TooLarge\nEND_VAR\n]]></Declaration>\n"
                f"{methods}"
                f"{properties}"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        issues = MethodCountCheck().run(TwinCATFile(tmp_path / "FB_TooLarge.TcPOU"))
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert "has 16 members (12 methods + 4 properties)" in issues[0].message
        assert "maximum 15" in issues[0].message

    def test_respects_policy_override(self, tmp_path):
        """Custom max_methods_per_pou from policy should be honored."""
        _write_file(
            tmp_path / ".twincat-validator.json",
            '{"oop_policy": {"max_methods_per_pou": 3}}',
        )

        methods = ""
        for i in range(4):
            methods += (
                f'    <Method Name="M_Op{i}" Id="{{b{i}{i}{i}{i}{i}{i}{i}{i}-4444-4444-4444-444444444444}}">\n'
                f"      <Declaration><![CDATA[METHOD M_Op{i} : BOOL\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[M_Op0 := TRUE;]]></ST></Implementation>\n"
                "    </Method>\n"
            )

        _write_file(
            tmp_path / "FB_CustomLimit.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_CustomLimit" Id="{a3333333-3333-3333-3333-333333333333}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_CustomLimit\nEND_VAR\n]]></Declaration>\n"
                f"{methods}"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        issues = MethodCountCheck().run(TwinCATFile(tmp_path / "FB_CustomLimit.TcPOU"))
        assert len(issues) == 1
        assert "maximum 3" in issues[0].message

    def test_skip_for_non_pou_files(self, tmp_path):
        """Check only applies to .TcPOU files."""
        _write_file(
            tmp_path / "I_Big.TcIO",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <Itf Name="I_Big" Id="{a4444444-4444-4444-4444-444444444444}">\n'
                "    <Declaration><![CDATA[INTERFACE I_Big\n]]></Declaration>\n"
                '    <Method Name="M_Do" Id="{a5555555-5555-5555-5555-555555555555}">\n'
                "      <Declaration><![CDATA[METHOD M_Do : BOOL\n]]></Declaration>\n"
                "    </Method>\n"
                "  </Itf>\n"
                "</TcPlcObject>\n"
            ),
        )

        issues = MethodCountCheck().run(TwinCATFile(tmp_path / "I_Big.TcIO"))
        assert len(issues) == 0
