"""Unit tests for Phase 5B OOP design quality checks."""

from pathlib import Path

from twincat_validator.file_handler import TwinCATFile
from twincat_validator.validators.oop_checks import (
    CompositionDepthCheck,
    InterfaceSegregationCheck,
    MethodVisibilityConsistencyCheck,
    DiamondInheritanceWarningCheck,
)


def _write_file(path: Path, content: str) -> None:
    """Helper to write test files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestCompositionDepthCheck:
    """Tests for CompositionDepthCheck (max inheritance depth)."""

    def test_pass_when_no_inheritance(self, tmp_path):
        """Test that standalone FB passes (depth = 0)."""
        _write_file(
            tmp_path / "FB_Standalone.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Standalone" Id="{a1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Standalone\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        check = CompositionDepthCheck()
        issues = check.run(TwinCATFile(tmp_path / "FB_Standalone.TcPOU"))
        assert len(issues) == 0

    def test_pass_when_depth_equals_max(self, tmp_path):
        """Test that depth exactly at threshold passes (default max = 4)."""
        # Create chain: FB_Level0 -> FB_Level1 -> FB_Level2 -> FB_Level3 -> FB_Level4
        # Depth of FB_Level4 = 4 (should pass)

        for i in range(5):
            if i == 0:
                extends = ""
            else:
                extends = f" EXTENDS FB_Level{i-1}"

            _write_file(
                tmp_path / f"FB_Level{i}.TcPOU",
                (
                    '<?xml version="1.0" encoding="utf-8"?>\n'
                    '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                    f'  <POU Name="FB_Level{i}" Id="{{a111111{i}-1111-1111-1111-111111111111}}" SpecialFunc="None">\n'
                    f"    <Declaration><![CDATA[FUNCTION_BLOCK FB_Level{i}{extends}\n"
                    "END_VAR\n"
                    "]]></Declaration>\n"
                    "  </POU>\n"
                    "</TcPlcObject>\n"
                ),
            )

        check = CompositionDepthCheck()
        issues = check.run(TwinCATFile(tmp_path / "FB_Level4.TcPOU"))
        assert len(issues) == 0  # Depth 4 = max, should pass

    def test_warn_when_depth_exceeds_max(self, tmp_path):
        """Test that depth > 4 triggers warning."""
        # Create chain: FB_Level0 -> ... -> FB_Level5 (depth = 5 > 4)

        for i in range(6):
            if i == 0:
                extends = ""
            else:
                extends = f" EXTENDS FB_Level{i-1}"

            _write_file(
                tmp_path / f"FB_Level{i}.TcPOU",
                (
                    '<?xml version="1.0" encoding="utf-8"?>\n'
                    '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                    f'  <POU Name="FB_Level{i}" Id="{{a111111{i}-1111-1111-1111-111111111111}}" SpecialFunc="None">\n'
                    f"    <Declaration><![CDATA[FUNCTION_BLOCK FB_Level{i}{extends}\n"
                    "END_VAR\n"
                    "]]></Declaration>\n"
                    "  </POU>\n"
                    "</TcPlcObject>\n"
                ),
            )

        check = CompositionDepthCheck()
        issues = check.run(TwinCATFile(tmp_path / "FB_Level5.TcPOU"))
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert "depth 5 exceeds recommended maximum 4" in issues[0].message
        assert "composition" in issues[0].message.lower()

    def test_respects_policy_override(self, tmp_path):
        """Test that custom max_inheritance_depth policy is respected."""
        # Create chain with depth 2
        _write_file(
            tmp_path / "FB_Base.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Base" Id="{a1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Base\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_Middle.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Middle" Id="{a2222222-2222-2222-2222-222222222222}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Middle EXTENDS FB_Base\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_Derived.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Derived" Id="{a3333333-3333-3333-3333-333333333333}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Middle\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        # Create policy file with max_inheritance_depth = 1
        _write_file(
            tmp_path / ".twincat-validator.json",
            '{"oop_policy": {"max_inheritance_depth": 1}}',
        )

        check = CompositionDepthCheck()
        issues = check.run(TwinCATFile(tmp_path / "FB_Derived.TcPOU"))
        assert len(issues) == 1
        assert "depth 2 exceeds recommended maximum 1" in issues[0].message


class TestInterfaceSegregationCheck:
    """Tests for InterfaceSegregationCheck (max interface size)."""

    def test_pass_when_interface_below_threshold(self, tmp_path):
        """Test that interface with 5 members passes (default max = 7)."""
        _write_file(
            tmp_path / "I_Small.TcIO",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <Itf Name="I_Small" Id="{a1111111-1111-1111-1111-111111111111}">\n'
                "    <Declaration><![CDATA[INTERFACE I_Small\n"
                "]]></Declaration>\n"
                '    <Method Name="M_Read" Id="{a2222222-2222-2222-2222-222222222222}">\n'
                "      <Declaration><![CDATA[METHOD M_Read : BOOL\n]]></Declaration>\n"
                "    </Method>\n"
                '    <Method Name="M_Write" Id="{a3333333-3333-3333-3333-333333333333}">\n'
                "      <Declaration><![CDATA[METHOD M_Write : BOOL\n]]></Declaration>\n"
                "    </Method>\n"
                '    <Property Name="Status" Id="{a4444444-4444-4444-4444-444444444444}">\n'
                "      <Declaration><![CDATA[PROPERTY Status : INT\n]]></Declaration>\n"
                '      <Get Name="Get" Id="{a5555555-5555-5555-5555-555555555555}">\n'
                "        <Declaration><![CDATA[]]></Declaration>\n"
                "      </Get>\n"
                "    </Property>\n"
                "  </Itf>\n"
                "</TcPlcObject>\n"
            ),
        )

        check = InterfaceSegregationCheck()
        issues = check.run(TwinCATFile(tmp_path / "I_Small.TcIO"))
        assert len(issues) == 0

    def test_warn_when_interface_exceeds_threshold(self, tmp_path):
        """Test that interface with 8 members triggers warning (> 7)."""
        # Build interface with 5 methods + 3 properties = 8 total
        methods = ""
        for i in range(5):
            methods += (
                f'    <Method Name="M_Method{i}" Id="{{a{i}{i}{i}{i}{i}{i}{i}{i}-1111-1111-1111-111111111111}}">\n'
                f"      <Declaration><![CDATA[METHOD M_Method{i} : BOOL\n]]></Declaration>\n"
                "    </Method>\n"
            )

        properties = ""
        for i in range(3):
            j = i + 5
            properties += (
                f'    <Property Name="Prop{i}" Id="{{a{j}{j}{j}{j}{j}{j}{j}{j}-2222-2222-2222-222222222222}}">\n'
                f"      <Declaration><![CDATA[PROPERTY Prop{i} : INT\n]]></Declaration>\n"
                f'      <Get Name="Get" Id="{{a{j}{j}{j}{j}{j}{j}{j}{j}-3333-3333-3333-333333333333}}">\n'
                "        <Declaration><![CDATA[]]></Declaration>\n"
                "      </Get>\n"
                "    </Property>\n"
            )

        _write_file(
            tmp_path / "I_Large.TcIO",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <Itf Name="I_Large" Id="{a1111111-1111-1111-1111-111111111111}">\n'
                "    <Declaration><![CDATA[INTERFACE I_Large\n"
                "]]></Declaration>\n"
                f"{methods}"
                f"{properties}"
                "  </Itf>\n"
                "</TcPlcObject>\n"
            ),
        )

        check = InterfaceSegregationCheck()
        issues = check.run(TwinCATFile(tmp_path / "I_Large.TcIO"))
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert "has 8 members" in issues[0].message
        assert "5 methods + 3 properties" in issues[0].message
        assert "Interface Segregation" in issues[0].message

    def test_respects_policy_override(self, tmp_path):
        """Test that custom max_interface_methods policy is respected."""
        _write_file(
            tmp_path / "I_Medium.TcIO",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <Itf Name="I_Medium" Id="{a1111111-1111-1111-1111-111111111111}">\n'
                "    <Declaration><![CDATA[INTERFACE I_Medium\n"
                "]]></Declaration>\n"
                '    <Method Name="M1" Id="{a2222222-2222-2222-2222-222222222222}">\n'
                "      <Declaration><![CDATA[METHOD M1 : BOOL\n]]></Declaration>\n"
                "    </Method>\n"
                '    <Method Name="M2" Id="{a3333333-3333-3333-3333-333333333333}">\n'
                "      <Declaration><![CDATA[METHOD M2 : BOOL\n]]></Declaration>\n"
                "    </Method>\n"
                '    <Method Name="M3" Id="{a4444444-4444-4444-4444-444444444444}">\n'
                "      <Declaration><![CDATA[METHOD M3 : BOOL\n]]></Declaration>\n"
                "    </Method>\n"
                "  </Itf>\n"
                "</TcPlcObject>\n"
            ),
        )

        # Create policy file with max_interface_methods = 2
        _write_file(
            tmp_path / ".twincat-validator.json",
            '{"oop_policy": {"max_interface_methods": 2}}',
        )

        check = InterfaceSegregationCheck()
        issues = check.run(TwinCATFile(tmp_path / "I_Medium.TcIO"))
        assert len(issues) == 1
        assert "exceeding recommended maximum 2" in issues[0].message


class TestMethodVisibilityConsistencyCheck:
    """Tests for MethodVisibilityConsistencyCheck (Liskov Substitution)."""

    def test_pass_when_visibility_maintained(self, tmp_path):
        """Test that PUBLIC -> PUBLIC passes."""
        _write_file(
            tmp_path / "FB_Base.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Base" Id="{a1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Base\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                '    <Method Name="M_Execute" Id="{a2222222-2222-2222-2222-222222222222}">\n'
                "      <Declaration><![CDATA[METHOD PUBLIC M_Execute : BOOL\n"
                "VAR_INPUT\nEND_VAR\n"
                "]]></Declaration>\n"
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
                '  <POU Name="FB_Derived" Id="{a3333333-3333-3333-3333-333333333333}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                '    <Method Name="M_Execute" Id="{a4444444-4444-4444-4444-444444444444}">\n'
                "      <Declaration><![CDATA[METHOD PUBLIC M_Execute : BOOL\n"
                "VAR_INPUT\nEND_VAR\n"
                "]]></Declaration>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        check = MethodVisibilityConsistencyCheck()
        issues = check.run(TwinCATFile(tmp_path / "FB_Derived.TcPOU"))
        assert len(issues) == 0

    def test_pass_when_visibility_increased(self, tmp_path):
        """Test that PRIVATE -> PUBLIC passes (increasing visibility is OK)."""
        _write_file(
            tmp_path / "FB_Base.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Base" Id="{a1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Base\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                '    <Method Name="M_Helper" Id="{a2222222-2222-2222-2222-222222222222}">\n'
                "      <Declaration><![CDATA[METHOD PRIVATE M_Helper : BOOL\n"
                "VAR_INPUT\nEND_VAR\n"
                "]]></Declaration>\n"
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
                '  <POU Name="FB_Derived" Id="{a3333333-3333-3333-3333-333333333333}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                '    <Method Name="M_Helper" Id="{a4444444-4444-4444-4444-444444444444}">\n'
                "      <Declaration><![CDATA[METHOD PUBLIC M_Helper : BOOL\n"
                "VAR_INPUT\nEND_VAR\n"
                "]]></Declaration>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        check = MethodVisibilityConsistencyCheck()
        issues = check.run(TwinCATFile(tmp_path / "FB_Derived.TcPOU"))
        assert len(issues) == 0  # Increasing visibility is allowed

    def test_warn_when_visibility_reduced_public_to_private(self, tmp_path):
        """Test that PUBLIC -> PRIVATE triggers warning (Liskov violation)."""
        _write_file(
            tmp_path / "FB_Base.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Base" Id="{a1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Base\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                '    <Method Name="M_Execute" Id="{a2222222-2222-2222-2222-222222222222}">\n'
                "      <Declaration><![CDATA[METHOD PUBLIC M_Execute : BOOL\n"
                "VAR_INPUT\nEND_VAR\n"
                "]]></Declaration>\n"
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
                '  <POU Name="FB_Derived" Id="{a3333333-3333-3333-3333-333333333333}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                '    <Method Name="M_Execute" Id="{a4444444-4444-4444-4444-444444444444}">\n'
                "      <Declaration><![CDATA[METHOD PRIVATE M_Execute : BOOL\n"
                "VAR_INPUT\nEND_VAR\n"
                "]]></Declaration>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        check = MethodVisibilityConsistencyCheck()
        issues = check.run(TwinCATFile(tmp_path / "FB_Derived.TcPOU"))
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert "visibility reduced" in issues[0].message.lower()
        assert "Liskov" in issues[0].message
        assert "PUBLIC → PRIVATE" in issues[0].message or "PUBLIC -> PRIVATE" in issues[0].message

    def test_default_visibility_is_public(self, tmp_path):
        """Test that methods without specifier are treated as PUBLIC (TwinCAT default)."""
        _write_file(
            tmp_path / "FB_Base.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Base" Id="{a1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Base\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                '    <Method Name="M_Execute" Id="{a2222222-2222-2222-2222-222222222222}">\n'
                "      <Declaration><![CDATA[METHOD M_Execute : BOOL\n"  # No specifier = PUBLIC
                "VAR_INPUT\nEND_VAR\n"
                "]]></Declaration>\n"
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
                '  <POU Name="FB_Derived" Id="{a3333333-3333-3333-3333-333333333333}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                '    <Method Name="M_Execute" Id="{a4444444-4444-4444-4444-444444444444}">\n'
                "      <Declaration><![CDATA[METHOD PRIVATE M_Execute : BOOL\n"  # Reducing from PUBLIC
                "VAR_INPUT\nEND_VAR\n"
                "]]></Declaration>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        check = MethodVisibilityConsistencyCheck()
        issues = check.run(TwinCATFile(tmp_path / "FB_Derived.TcPOU"))
        assert len(issues) == 1
        # Should flag: default PUBLIC → explicit PRIVATE
        assert "PUBLIC → PRIVATE" in issues[0].message or "PUBLIC -> PRIVATE" in issues[0].message


class TestDiamondInheritanceWarningCheck:
    """Tests for DiamondInheritanceWarningCheck (redundant interface implementation)."""

    def test_pass_when_no_duplicate_interfaces(self, tmp_path):
        """Test that unique interfaces pass."""
        _write_file(
            tmp_path / "I_Logger.TcIO",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <Itf Name="I_Logger" Id="{a1111111-1111-1111-1111-111111111111}">\n'
                "    <Declaration><![CDATA[INTERFACE I_Logger\n"
                "]]></Declaration>\n"
                "  </Itf>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_Base.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Base" Id="{a2222222-2222-2222-2222-222222222222}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Base IMPLEMENTS I_Logger\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_Derived.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Derived" Id="{a3333333-3333-3333-3333-333333333333}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\n"  # Inherits I_Logger from base
                "END_VAR\n"
                "]]></Declaration>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        check = DiamondInheritanceWarningCheck()
        issues = check.run(TwinCATFile(tmp_path / "FB_Derived.TcPOU"))
        assert len(issues) == 0

    def test_warn_when_interface_reimplemented(self, tmp_path):
        """Test that redundant interface implementation triggers warning."""
        _write_file(
            tmp_path / "I_Logger.TcIO",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <Itf Name="I_Logger" Id="{a1111111-1111-1111-1111-111111111111}">\n'
                "    <Declaration><![CDATA[INTERFACE I_Logger\n"
                "]]></Declaration>\n"
                "  </Itf>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_Base.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Base" Id="{a2222222-2222-2222-2222-222222222222}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Base IMPLEMENTS I_Logger\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_Derived.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Derived" Id="{a3333333-3333-3333-3333-333333333333}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base IMPLEMENTS I_Logger\n"  # Redundant!
                "END_VAR\n"
                "]]></Declaration>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        check = DiamondInheritanceWarningCheck()
        issues = check.run(TwinCATFile(tmp_path / "FB_Derived.TcPOU"))
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert "redundant interface implementation" in issues[0].message.lower()
        assert "I_Logger" in issues[0].message
        assert "FB_Base" in issues[0].message
        assert "FB_Derived" in issues[0].message

    def test_respects_policy_disable(self, tmp_path):
        """Test that warn_diamond_inheritance=false disables the check."""
        _write_file(
            tmp_path / "I_Logger.TcIO",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <Itf Name="I_Logger" Id="{a1111111-1111-1111-1111-111111111111}">\n'
                "    <Declaration><![CDATA[INTERFACE I_Logger\n"
                "]]></Declaration>\n"
                "  </Itf>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_Base.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Base" Id="{a2222222-2222-2222-2222-222222222222}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Base IMPLEMENTS I_Logger\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        _write_file(
            tmp_path / "FB_Derived.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Derived" Id="{a3333333-3333-3333-3333-333333333333}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base IMPLEMENTS I_Logger\n"
                "END_VAR\n"
                "]]></Declaration>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        # Create policy file with warn_diamond_inheritance = false
        _write_file(
            tmp_path / ".twincat-validator.json",
            '{"oop_policy": {"warn_diamond_inheritance": false}}',
        )

        check = DiamondInheritanceWarningCheck()
        issues = check.run(TwinCATFile(tmp_path / "FB_Derived.TcPOU"))
        assert len(issues) == 0  # Check disabled by policy
