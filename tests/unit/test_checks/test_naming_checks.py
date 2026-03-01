"""Tests for twincat_validator.validators.naming_checks module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from twincat_validator.validators.base import CheckRegistry
from twincat_validator.validators.naming_checks import NamingConventionsCheck
from twincat_validator.file_handler import TwinCATFile


def _ensure_naming_checks_registered() -> None:
    if NamingConventionsCheck.check_id not in CheckRegistry.get_all_checks():
        CheckRegistry.register(NamingConventionsCheck)


class TestNamingConventionsCheck:
    """Tests for NamingConventionsCheck validator."""

    @classmethod
    def setup_class(cls):
        """Ensure checks are registered without mutating global registry state."""
        _ensure_naming_checks_registered()

    def test_valid_function_block_name(self, tmp_path):
        """Test valid FUNCTION_BLOCK name produces no issues."""
        fb_file = tmp_path / "FB_Test.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_Test\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = NamingConventionsCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_invalid_function_block_name(self, tmp_path):
        """Test invalid FUNCTION_BLOCK name is detected."""
        fb_file = tmp_path / "MyBlock.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="MyBlock">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK MyBlock\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = NamingConventionsCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].category == "Naming"
        assert "Function block 'MyBlock' should start with 'FB_'" in issues[0].message
        assert issues[0].fix_available is False

    def test_uses_top_level_pou_name_not_first_name_attribute(self, tmp_path):
        """Top-level POU Name should be used even if earlier Name attributes exist."""
        fb_file = tmp_path / "FB_RealName.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <Meta Name="Wrong_Inner_Name" />\n'
            '  <POU Name="FB_RealName">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_RealName\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = NamingConventionsCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_valid_program_name(self, tmp_path):
        """Test valid PROGRAM name produces no issues."""
        prg_file = tmp_path / "PRG_Main.TcPOU"
        prg_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="PRG_Main">\n'
            "    <Declaration><![CDATA[\n"
            "PROGRAM PRG_Main\n"
            "END_PROGRAM\n"
            "]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(prg_file)
        check = NamingConventionsCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_invalid_program_name(self, tmp_path):
        """Test invalid PROGRAM name is detected."""
        prg_file = tmp_path / "MAIN.TcPOU"
        prg_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="MAIN">\n'
            "    <Declaration><![CDATA[\n"
            "PROGRAM MAIN\n"
            "END_PROGRAM\n"
            "]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(prg_file)
        check = NamingConventionsCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].category == "Naming"
        assert "Program 'MAIN' should start with 'PRG_'" in issues[0].message

    def test_valid_function_name(self, tmp_path):
        """Test valid FUNCTION name produces no issues."""
        func_file = tmp_path / "FUNC_Calculate.TcPOU"
        func_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FUNC_Calculate">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION FUNC_Calculate : INT\n"
            "END_FUNCTION\n"
            "]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(func_file)
        check = NamingConventionsCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_invalid_function_name(self, tmp_path):
        """Test invalid FUNCTION name is detected."""
        func_file = tmp_path / "Calculate.TcPOU"
        func_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="Calculate">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION Calculate : INT\n"
            "END_FUNCTION\n"
            "]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(func_file)
        check = NamingConventionsCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].category == "Naming"
        assert "Function 'Calculate' should start with 'FUNC_'" in issues[0].message

    def test_pou_unknown_subtype_fallback(self, tmp_path):
        """Test POU with unknown subtype uses fallback check."""
        pou_file = tmp_path / "Unknown.TcPOU"
        pou_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="Unknown">\n'
            "    <Declaration><![CDATA[\n"
            "// Malformed declaration\n"
            "]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(pou_file)
        check = NamingConventionsCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].category == "Naming"
        assert "POU 'Unknown' should start with 'FB_', 'PRG_', or 'FUNC_'" in issues[0].message

    def test_valid_interface_name(self, tmp_path):
        """Test valid interface name produces no issues."""
        io_file = tmp_path / "I_Motor.TcIO"
        io_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <Itf Name="I_Motor">\n'
            "  </Itf>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(io_file)
        check = NamingConventionsCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_invalid_interface_name(self, tmp_path):
        """Test invalid interface name is detected."""
        io_file = tmp_path / "Motor.TcIO"
        io_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <Itf Name="Motor">\n'
            "  </Itf>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(io_file)
        check = NamingConventionsCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].category == "Naming"
        assert "Interface 'Motor' should start with 'I_'" in issues[0].message

    def test_valid_struct_name(self, tmp_path):
        """Test valid struct name produces no issues."""
        dut_file = tmp_path / "ST_Data.TcDUT"
        dut_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <DUT Name="ST_Data">\n'
            "  </DUT>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(dut_file)
        check = NamingConventionsCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_valid_enum_name(self, tmp_path):
        """Test valid enum name produces no issues."""
        dut_file = tmp_path / "E_State.TcDUT"
        dut_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <DUT Name="E_State">\n'
            "  </DUT>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(dut_file)
        check = NamingConventionsCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_valid_type_alias_name(self, tmp_path):
        """Test valid type alias name produces no issues."""
        dut_file = tmp_path / "T_Pointer.TcDUT"
        dut_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <DUT Name="T_Pointer">\n'
            "  </DUT>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(dut_file)
        check = NamingConventionsCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_invalid_dut_name(self, tmp_path):
        """Test invalid DUT name is detected."""
        dut_file = tmp_path / "MyData.TcDUT"
        dut_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <DUT Name="MyData">\n'
            "  </DUT>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(dut_file)
        check = NamingConventionsCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].category == "Naming"
        assert "Data type 'MyData' should start with 'ST_', 'E_', or 'T_'" in issues[0].message

    def test_valid_gvl_name(self, tmp_path):
        """Test valid GVL name produces no issues."""
        gvl_file = tmp_path / "GVL_Config.TcGVL"
        gvl_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <GVL Name="GVL_Config">\n'
            "  </GVL>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(gvl_file)
        check = NamingConventionsCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_invalid_gvl_name(self, tmp_path):
        """Test invalid GVL name is detected."""
        gvl_file = tmp_path / "Constants.TcGVL"
        gvl_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <GVL Name="Constants">\n'
            "  </GVL>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(gvl_file)
        check = NamingConventionsCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].category == "Naming"
        assert "Global variable list 'Constants' should start with 'GVL_'" in issues[0].message

    def test_file_without_name_attribute(self, tmp_path):
        """Test file without Name attribute produces no issues."""
        file_no_name = tmp_path / "NoName.TcPOU"
        file_no_name.write_text(
            '<?xml version="1.0"?>\n' "<TcPlcObject>\n" "  <POU>\n" "  </POU>\n" "</TcPlcObject>"
        )

        file = TwinCATFile(file_no_name)
        check = NamingConventionsCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_check_id_matches_config(self):
        """Test check_id matches expected config ID."""
        check = NamingConventionsCheck()
        assert check.check_id == "naming_conventions"
