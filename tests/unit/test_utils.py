"""Tests for twincat_validator.utils module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from twincat_validator.file_handler import TwinCATFile


class TestPouSubtypeDetection:
    """Tests for POU subtype detection."""

    def test_detect_function_block(self, valid_tcpou):
        """Test detection of FUNCTION_BLOCK subtype."""
        file = TwinCATFile(valid_tcpou)
        assert file.pou_subtype == "function_block"

    def test_detect_function(self, valid_function):
        """Test detection of FUNCTION subtype."""
        file = TwinCATFile(valid_function)
        assert file.pou_subtype == "function"

    def test_detect_program(self, valid_program):
        """Test detection of PROGRAM subtype."""
        file = TwinCATFile(valid_program)
        assert file.pou_subtype == "program"

    def test_non_pou_returns_none(self, valid_tcio):
        """Test non-POU files return None."""
        file = TwinCATFile(valid_tcio)
        assert file.pou_subtype is None

    def test_dut_returns_none(self, valid_tcdut):
        """Test DUT files return None."""
        file = TwinCATFile(valid_tcdut)
        assert file.pou_subtype is None

    def test_gvl_returns_none(self, valid_tcgvl):
        """Test GVL files return None."""
        file = TwinCATFile(valid_tcgvl)
        assert file.pou_subtype is None

    def test_detect_with_pragma_line(self, tmp_tcpou):
        """Test detection works with pragma lines before keyword."""
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
  </POU>
</TcPlcObject>"""

        path = tmp_tcpou(content, name="FUNC_Pragma.TcPOU")
        file = TwinCATFile(path)
        assert file.pou_subtype == "function"

    def test_detect_lowercase_keyword(self, tmp_tcpou):
        """Test detection works with lowercase keywords."""
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
  </POU>
</TcPlcObject>"""

        path = tmp_tcpou(content, name="PRG_Lower.TcPOU")
        file = TwinCATFile(path)
        assert file.pou_subtype == "program"
