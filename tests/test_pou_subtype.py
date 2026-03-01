"""Tests for POU subtype detection and subtype-aware validation."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---- Subtype Detection ----


class TestPouSubtypeDetection:
    """Tests for the _detect_pou_subtype_from_content function."""

    def test_detect_function_block(self, valid_tcpou):
        from twincat_validator import TwinCATFile

        file = TwinCATFile.from_path(valid_tcpou)
        assert file.pou_subtype == "function_block"

    def test_detect_function(self, valid_function):
        from twincat_validator import TwinCATFile

        file = TwinCATFile.from_path(valid_function)
        assert file.pou_subtype == "function"

    def test_detect_program(self, valid_program):
        from twincat_validator import TwinCATFile

        file = TwinCATFile.from_path(valid_program)
        assert file.pou_subtype == "program"

    def test_non_pou_returns_none(self, valid_tcio):
        from twincat_validator import TwinCATFile

        file = TwinCATFile.from_path(valid_tcio)
        assert file.pou_subtype is None

    def test_dut_returns_none(self, valid_tcdut):
        from twincat_validator import TwinCATFile

        file = TwinCATFile.from_path(valid_tcdut)
        assert file.pou_subtype is None

    def test_gvl_returns_none(self, valid_tcgvl):
        from twincat_validator import TwinCATFile

        file = TwinCATFile.from_path(valid_tcgvl)
        assert file.pou_subtype is None

    def test_subtype_in_validation_output(self, valid_function):
        from server import validate_file

        result = json.loads(validate_file(str(valid_function)))
        assert result["success"] is True
        assert result["pou_subtype"] == "function"

    def test_subtype_in_fb_validation_output(self, valid_tcpou):
        from server import validate_file

        result = json.loads(validate_file(str(valid_tcpou)))
        assert result["success"] is True
        assert result["pou_subtype"] == "function_block"

    def test_detect_function_with_pragma_line(self, tmp_tcpou):
        from twincat_validator import TwinCATFile

        content = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FUNC_Pragma" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">
    <Declaration><![CDATA[{attribute 'qualified_only'}
FUNCTION FUNC_Pragma : INT
VAR_INPUT
  n : INT;
END_VAR]]></Declaration>
    <Implementation>
      <ST><![CDATA[FUNC_Pragma := n;]]></ST>
    </Implementation>
    <LineIds Name="FUNC_Pragma">
      <LineId Id="3" Count="0" />
      <LineId Id="2" Count="0" />
    </LineIds>
  </POU>
</TcPlcObject>"""

        path = tmp_tcpou(content, name="FUNC_Pragma.TcPOU")
        file = TwinCATFile.from_path(path)
        assert file.pou_subtype == "function"

    def test_detect_lowercase_program_keyword(self, tmp_tcpou):
        from twincat_validator import TwinCATFile

        content = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="PRG_Lower" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">
    <Declaration><![CDATA[program PRG_Lower
VAR
  bRunning : BOOL;
END_VAR]]></Declaration>
    <Implementation>
      <ST><![CDATA[bRunning := TRUE;]]></ST>
    </Implementation>
    <LineIds Name="PRG_Lower">
      <LineId Id="3" Count="0" />
      <LineId Id="2" Count="0" />
    </LineIds>
  </POU>
</TcPlcObject>"""

        path = tmp_tcpou(content, name="PRG_Lower.TcPOU")
        file = TwinCATFile.from_path(path)
        assert file.pou_subtype == "program"


# ---- Function-Specific Validation ----


class TestFunctionValidation:
    """Tests for FUNCTION-specific rules."""

    def test_valid_function_passes(self, valid_function):
        from server import validate_file

        result = json.loads(validate_file(str(valid_function)))
        assert result["success"] is True
        assert result["validation_status"] == "passed"

    def test_function_with_methods_fails(self, function_with_methods):
        from server import validate_file

        result = json.loads(validate_file(str(function_with_methods)))
        issues = [i for i in result["issues"] if i["category"] == "Structure"]
        method_issues = [i for i in issues if "Method" in i["message"]]
        assert len(method_issues) > 0

    def test_function_no_return_type_is_error(self, function_no_return_type):
        from server import validate_file

        result = json.loads(validate_file(str(function_no_return_type)))
        issues = [i for i in result["issues"] if "return type" in i["message"].lower()]
        assert len(issues) > 0
        assert any(i["type"] == "error" for i in issues)

    def test_function_no_return_type_blocks_import(self, function_no_return_type):
        from server import validate_for_import

        result = json.loads(validate_for_import(str(function_no_return_type)))
        assert result["success"] is True
        assert result["safe_to_import"] is False
        assert result["error_count"] > 0

    def test_function_properties_skipped(self, valid_function):
        """Property VAR block check should be skipped for FUNCTIONs."""
        from server import check_specific

        result = json.loads(check_specific(str(valid_function), ["var_blocks"]))
        assert result["success"] is True
        assert result["validation_status"] == "passed"

    def test_function_element_ordering_skipped(self, valid_function):
        """Element ordering check should be skipped for FUNCTIONs."""
        from server import check_specific

        result = json.loads(check_specific(str(valid_function), ["element_order"]))
        assert result["success"] is True
        assert result["validation_status"] == "passed"


# ---- Program Validation ----


class TestProgramValidation:
    """Tests for PROGRAM-specific rules."""

    def test_valid_program_passes(self, valid_program):
        from server import validate_file

        result = json.loads(validate_file(str(valid_program)))
        assert result["success"] is True
        assert result["validation_status"] == "passed"

    def test_program_subtype_detected(self, valid_program):
        from twincat_validator import TwinCATFile

        file = TwinCATFile.from_path(valid_program)
        assert file.pou_subtype == "program"


# ---- Naming Convention Precision ----


class TestSubtypeNaming:
    """Tests for subtype-precise naming convention enforcement."""

    def test_fb_named_prg_gets_warning(self, tmp_tcpou):
        """A FUNCTION_BLOCK named PRG_Something should get a naming warning."""
        from server import validate_file

        content = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="PRG_Wrong" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK PRG_Wrong
VAR
END_VAR]]></Declaration>
    <Implementation>
      <ST><![CDATA[]]></ST>
    </Implementation>
    <LineIds Name="PRG_Wrong">
      <LineId Id="2" Count="0" />
    </LineIds>
  </POU>
</TcPlcObject>"""

        path = tmp_tcpou(content)
        result = json.loads(validate_file(str(path)))
        naming_issues = [i for i in result["issues"] if i["category"] == "Naming"]
        assert len(naming_issues) > 0
        assert "FB_" in naming_issues[0]["message"]

    def test_function_named_fb_gets_warning(self, tmp_tcpou):
        """A FUNCTION named FB_Something should get a naming warning."""
        from server import validate_file

        content = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_Wrong" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION FB_Wrong : INT
VAR_INPUT
  n : INT;
END_VAR]]></Declaration>
    <Implementation>
      <ST><![CDATA[FB_Wrong := n;]]></ST>
    </Implementation>
    <LineIds Name="FB_Wrong">
      <LineId Id="3" Count="0" />
      <LineId Id="2" Count="0" />
    </LineIds>
  </POU>
</TcPlcObject>"""

        path = tmp_tcpou(content, name="FB_Wrong.TcPOU")
        result = json.loads(validate_file(str(path)))
        naming_issues = [i for i in result["issues"] if i["category"] == "Naming"]
        assert len(naming_issues) > 0
        assert "FUNC_" in naming_issues[0]["message"]

    def test_correctly_named_fb_passes(self, valid_tcpou):
        """An FB_ named FUNCTION_BLOCK should not get a naming warning."""
        from server import check_specific

        result = json.loads(check_specific(str(valid_tcpou), ["naming"]))
        naming_issues = [i for i in result["issues"] if i["category"] == "Naming"]
        assert len(naming_issues) == 0


# ---- Backward Compatibility ----


class TestBackwardCompatibility:
    """Ensure existing behavior is not broken."""

    def test_existing_fb_fixture_still_passes(self, valid_tcpou):
        from server import validate_file

        result = json.loads(validate_file(str(valid_tcpou)))
        assert result["success"] is True
        assert result["validation_status"] == "passed"

    def test_existing_interface_still_passes(self, valid_tcio):
        from server import validate_file

        result = json.loads(validate_file(str(valid_tcio)))
        assert result["success"] is True

    def test_existing_dut_still_passes(self, valid_tcdut):
        from server import validate_file

        result = json.loads(validate_file(str(valid_tcdut)))
        assert result["success"] is True

    def test_existing_gvl_still_passes(self, valid_tcgvl):
        from server import validate_file

        result = json.loads(validate_file(str(valid_tcgvl)))
        assert result["success"] is True

    def test_pou_structure_check_in_check_specific(self, valid_tcpou):
        """The new pou_structure check should be available via check_specific."""
        from server import check_specific

        result = json.loads(check_specific(str(valid_tcpou), ["pou_structure"]))
        assert result["success"] is True
