"""Tests for twincat_validator.fixers.complex_fixes module."""

import sys
from pathlib import Path
import importlib

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from twincat_validator.fixers.base import FixRegistry
from twincat_validator.fixers import complex_fixes
from twincat_validator.file_handler import TwinCATFile


def _ensure_complex_fixes_registered() -> None:
    """Ensure complex_fixes module is registered (clear + reload pattern)."""
    FixRegistry.clear()
    importlib.reload(complex_fixes)


class TestLineIdsFix:
    """Tests for LineIdsFix fixer."""

    @classmethod
    def setup_class(cls):
        """Ensure fixes are registered without mutating global registry state."""
        _ensure_complex_fixes_registered()

    def test_fix_id_matches_config(self):
        """Test that fix_id matches config/fix_capabilities.json."""
        fix_class = FixRegistry.get_fix("lineids")
        assert fix_class.fix_id == "lineids"

    def test_generates_lineids_for_pou_body(self, tmp_path):
        """Test that LineIds are generated for POU main body."""
        test_file = tmp_path / "pou_body.TcPOU"
        test_file.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1">\n'
            '  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789012}">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test]]></Declaration>\n"
            "    <Implementation>\n"
            "      <ST><![CDATA[// Main body code\nx := 1;]]></ST>\n"
            "    </Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("lineids")()

        result = fix.apply(file)

        assert result is True
        assert '<LineIds Name="FB_Test">' in file.content
        assert '<LineId Id="3" Count="1" />' in file.content  # 2 lines: comment + code
        assert '<LineId Id="2" Count="0" />' in file.content

    def test_generates_lineids_for_method(self, tmp_path):
        """Test that LineIds are generated for methods."""
        test_file = tmp_path / "method.TcPOU"
        test_file.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1">\n'
            '  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789012}">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test]]></Declaration>\n"
            "    <Implementation>\n"
            "      <ST><![CDATA[]]></ST>\n"
            "    </Implementation>\n"
            '    <Method Name="M_DoSomething" Id="{87654321-4321-4321-4321-210987654321}">\n'
            "      <Declaration><![CDATA[METHOD M_DoSomething : BOOL]]></Declaration>\n"
            "      <Implementation>\n"
            "        <ST><![CDATA[M_DoSomething := TRUE;]]></ST>\n"
            "      </Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("lineids")()

        result = fix.apply(file)

        assert result is True
        assert '<LineIds Name="FB_Test.M_DoSomething">' in file.content
        assert '<LineId Id="3" Count="0" />' in file.content  # 1 line

    def test_generates_lineids_for_property_get(self, tmp_path):
        """Test that LineIds are generated for property Get accessor."""
        test_file = tmp_path / "property_get.TcPOU"
        test_file.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1">\n'
            '  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789012}">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test]]></Declaration>\n"
            "    <Implementation>\n"
            "      <ST><![CDATA[]]></ST>\n"
            "    </Implementation>\n"
            '    <Property Name="P_Value" Id="{11111111-1111-1111-1111-111111111111}">\n'
            "      <Declaration><![CDATA[PROPERTY P_Value : INT]]></Declaration>\n"
            '      <Get Name="Get" Id="{22222222-2222-2222-2222-222222222222}">\n'
            "        <Declaration><![CDATA[VAR\nEND_VAR]]></Declaration>\n"
            "        <Implementation>\n"
            "          <ST><![CDATA[P_Value := 42;]]></ST>\n"
            "        </Implementation>\n"
            "      </Get>\n"
            "    </Property>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("lineids")()

        result = fix.apply(file)

        assert result is True
        assert '<LineIds Name="FB_Test.P_Value.Get">' in file.content

    def test_generates_lineids_for_property_set(self, tmp_path):
        """Test that LineIds are generated for property Set accessor."""
        test_file = tmp_path / "property_set.TcPOU"
        test_file.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1">\n'
            '  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789012}">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test]]></Declaration>\n"
            "    <Implementation>\n"
            "      <ST><![CDATA[]]></ST>\n"
            "    </Implementation>\n"
            '    <Property Name="P_Value" Id="{11111111-1111-1111-1111-111111111111}">\n'
            "      <Declaration><![CDATA[PROPERTY P_Value : INT]]></Declaration>\n"
            '      <Set Name="Set" Id="{33333333-3333-3333-3333-333333333333}">\n'
            "        <Declaration><![CDATA[VAR\nEND_VAR]]></Declaration>\n"
            "        <Implementation>\n"
            "          <ST><![CDATA[_value := P_Value;]]></ST>\n"
            "        </Implementation>\n"
            "      </Set>\n"
            "    </Property>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("lineids")()

        result = fix.apply(file)

        assert result is True
        assert '<LineIds Name="FB_Test.P_Value.Set">' in file.content

    def test_generates_empty_lineids_for_empty_code(self, tmp_path):
        """Test that empty LineIds are generated for empty code sections."""
        test_file = tmp_path / "empty_code.TcPOU"
        test_file.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1">\n'
            '  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789012}">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test]]></Declaration>\n"
            "    <Implementation>\n"
            "      <ST><![CDATA[]]></ST>\n"
            "    </Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("lineids")()

        result = fix.apply(file)

        assert result is True
        assert '<LineIds Name="FB_Test">' in file.content
        assert '<LineId Id="2" Count="0" />' in file.content
        # Should only have one LineId for empty code
        assert '<LineId Id="3"' not in file.content

    def test_skips_sections_with_existing_lineids(self, tmp_path):
        """Test that sections with existing LineIds are not regenerated."""
        test_file = tmp_path / "existing_lineids.TcPOU"
        test_file.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1">\n'
            '  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789012}">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test]]></Declaration>\n"
            "    <Implementation>\n"
            "      <ST><![CDATA[x := 1;]]></ST>\n"
            "    </Implementation>\n"
            '    <LineIds Name="FB_Test">\n'
            '      <LineId Id="3" Count="0" />\n'
            '      <LineId Id="2" Count="0" />\n'
            "    </LineIds>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        original_content = file.content
        fix = FixRegistry.get_fix("lineids")()

        result = fix.apply(file)

        # Should return False because LineIds already exist
        assert result is False
        assert file.content == original_content

    def test_handles_invalid_xml_gracefully(self, tmp_path):
        """Test that invalid XML is handled gracefully."""
        test_file = tmp_path / "invalid.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "  <POU Name=unclosed\n"  # Invalid XML
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("lineids")()

        result = fix.apply(file)

        # Should return False without crashing
        assert result is False

    def test_handles_missing_pou_name(self, tmp_path):
        """Test that files without POU name are handled gracefully."""
        test_file = tmp_path / "no_name.TcPOU"
        test_file.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1">\n'
            '  <POU Id="{12345678-1234-1234-1234-123456789012}">\n'  # Missing Name
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("lineids")()

        result = fix.apply(file)

        # Should return False because can't determine name
        assert result is False

    def test_validates_generated_xml(self, tmp_path):
        """Test that generated XML is validated before applying."""
        test_file = tmp_path / "pou.TcPOU"
        test_file.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1">\n'
            '  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789012}">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test]]></Declaration>\n"
            "    <Implementation>\n"
            "      <ST><![CDATA[x := 1;]]></ST>\n"
            "    </Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("lineids")()

        result = fix.apply(file)

        assert result is True
        # Verify the result is valid XML by parsing it
        import xml.etree.ElementTree as ET

        root = ET.fromstring(file.content)
        assert root is not None

    def test_multiple_sections_get_lineids(self, tmp_path):
        """Test that multiple code sections all get LineIds."""
        test_file = tmp_path / "multiple.TcPOU"
        test_file.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1">\n'
            '  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789012}">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test]]></Declaration>\n"
            "    <Implementation>\n"
            "      <ST><![CDATA[x := 1;]]></ST>\n"
            "    </Implementation>\n"
            '    <Method Name="M_One" Id="{11111111-1111-1111-1111-111111111111}">\n'
            "      <Declaration><![CDATA[METHOD M_One]]></Declaration>\n"
            "      <Implementation>\n"
            "        <ST><![CDATA[y := 2;]]></ST>\n"
            "      </Implementation>\n"
            "    </Method>\n"
            '    <Method Name="M_Two" Id="{22222222-2222-2222-2222-222222222222}">\n'
            "      <Declaration><![CDATA[METHOD M_Two]]></Declaration>\n"
            "      <Implementation>\n"
            "        <ST><![CDATA[z := 3;]]></ST>\n"
            "      </Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        fix = FixRegistry.get_fix("lineids")()

        result = fix.apply(file)

        assert result is True
        # All three sections should have LineIds
        assert '<LineIds Name="FB_Test">' in file.content
        assert '<LineIds Name="FB_Test.M_One">' in file.content
        assert '<LineIds Name="FB_Test.M_Two">' in file.content
