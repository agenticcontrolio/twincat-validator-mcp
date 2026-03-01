"""Tests for twincat_validator.validators.structure_checks module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from twincat_validator.validators.base import CheckRegistry
from twincat_validator.validators.structure_checks import (
    FileEndingCheck,
    PropertyVarBlocksCheck,
    LineIdsCountCheck,
    ElementOrderingCheck,
    PouStructureCheck,
    PouStructureHeaderCheck,
    PouStructureMethodsCheck,
    MainVarInputMutationCheck,
    PouStructureInterfaceCheck,
    PouStructureSyntaxCheck,
    UnsignedLoopUnderflowCheck,
    PouStructureSubtypeCheck,
)
from twincat_validator.file_handler import TwinCATFile


def _ensure_structure_checks_registered() -> None:
    for check_class in (
        FileEndingCheck,
        PropertyVarBlocksCheck,
        LineIdsCountCheck,
        ElementOrderingCheck,
        PouStructureCheck,
        MainVarInputMutationCheck,
        UnsignedLoopUnderflowCheck,
    ):
        if check_class.check_id not in CheckRegistry.get_all_checks():
            CheckRegistry.register(check_class)


class TestFileEndingCheck:
    """Tests for FileEndingCheck validator."""

    @classmethod
    def setup_class(cls):
        """Ensure checks are registered without mutating global registry state."""
        _ensure_structure_checks_registered()

    def test_valid_file_ending(self, tmp_path):
        """Test file with correct ending produces no issues."""
        valid_file = tmp_path / "valid.TcPOU"
        valid_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test">\n'
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(valid_file)
        check = FileEndingCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_file_ending_with_extra_closing_brackets(self, tmp_path):
        """Test file ending with ']]>' is detected."""
        bad_ending_file = tmp_path / "bad_ending.TcPOU"
        bad_ending_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test">\n'
            "  </POU>\n"
            "]]>"
        )

        file = TwinCATFile(bad_ending_file)
        check = FileEndingCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].category == "Format"
        assert "]]>" in issues[0].message
        assert "should end with '</TcPlcObject>'" in issues[0].message
        assert issues[0].fix_available is True

    def test_file_ending_with_closing_tag_and_brackets(self, tmp_path):
        """Test file ending with '</TcPlcObject>]]>' is detected."""
        bad_ending_file = tmp_path / "bad_ending2.TcPOU"
        bad_ending_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test">\n'
            "  </POU>\n"
            "</TcPlcObject>]]>"
        )

        file = TwinCATFile(bad_ending_file)
        check = FileEndingCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].category == "Format"
        assert "]]>" in issues[0].message
        assert "after </TcPlcObject>" in issues[0].message
        assert issues[0].fix_available is True

    def test_unexpected_file_ending(self, tmp_path):
        """Test file with completely unexpected ending."""
        unexpected_file = tmp_path / "unexpected.TcPOU"
        unexpected_file.write_text(
            '<?xml version="1.0"?>\n' "<TcPlcObject>\n" '  <POU Name="FB_Test">\n' "  </POU>"
        )

        file = TwinCATFile(unexpected_file)
        check = FileEndingCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].category == "Format"
        assert "Unexpected ending" in issues[0].message
        assert issues[0].fix_available is False

    def test_check_id_matches_config(self):
        """Test check_id matches expected config ID."""
        check = FileEndingCheck()
        assert check.check_id == "file_ending"


class TestPropertyVarBlocksCheck:
    """Tests for PropertyVarBlocksCheck validator."""

    @classmethod
    def setup_class(cls):
        """Ensure checks are registered without mutating global registry state."""
        _ensure_structure_checks_registered()

    def test_should_skip_for_gvl(self, tmp_path):
        """Test check is skipped for .TcGVL files."""
        gvl_file = tmp_path / "GVL_Test.TcGVL"
        gvl_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <GVL Name="GVL_Test">\n'
            "  </GVL>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(gvl_file)
        check = PropertyVarBlocksCheck()

        assert check.should_skip(file) is True

    def test_should_skip_for_dut(self, tmp_path):
        """Test check is skipped for .TcDUT files."""
        dut_file = tmp_path / "ST_Test.TcDUT"
        dut_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <DUT Name="ST_Test">\n'
            "  </DUT>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(dut_file)
        check = PropertyVarBlocksCheck()

        assert check.should_skip(file) is True

    def test_should_skip_for_function(self, tmp_path):
        """Test check is skipped for FUNCTION .TcPOU files."""
        function_file = tmp_path / "FUNC_Test.TcPOU"
        function_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FUNC_Test">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION FUNC_Test : INT\n"
            "END_FUNCTION\n"
            "]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(function_file)
        check = PropertyVarBlocksCheck()

        assert check.should_skip(file) is True

    def test_no_properties_no_issues(self, tmp_path):
        """Test file with no properties produces no issues."""
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
        check = PropertyVarBlocksCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_property_with_var_block_no_issues(self, tmp_path):
        """Test property with VAR block produces no issues."""
        fb_file = tmp_path / "FB_Test.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test">\n'
            '    <Property Name="Value">\n'
            '      <Get Name="Get">\n'
            "        <Declaration><![CDATA[VAR\nEND_VAR\n]]></Declaration>\n"
            "      </Get>\n"
            "    </Property>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = PropertyVarBlocksCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_property_with_empty_var_block_no_issues(self, tmp_path):
        """Test property with empty VAR block produces no issues."""
        fb_file = tmp_path / "FB_Test.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test">\n'
            '    <Property Name="Value">\n'
            '      <Get Name="Get">\n'
            "        <Declaration><![CDATA[]]></Declaration>\n"
            "      </Get>\n"
            "    </Property>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = PropertyVarBlocksCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_property_missing_var_block_detected(self, tmp_path):
        """Test property missing VAR block is detected."""
        fb_file = tmp_path / "FB_Test.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test">\n'
            '    <Property Name="Value">\n'
            '      <Get Name="Get">\n'
            "        <Declaration><![CDATA[\n"
            "// No VAR block here\n"
            "]]></Declaration>\n"
            "      </Get>\n"
            "    </Property>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = PropertyVarBlocksCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].category == "Property"
        assert "1 property getter(s) missing VAR blocks" in issues[0].message
        assert issues[0].fix_available is True

    def test_multiple_properties_missing_var_blocks(self, tmp_path):
        """Test multiple properties missing VAR blocks."""
        fb_file = tmp_path / "FB_Test.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test">\n'
            '    <Property Name="Value1">\n'
            '      <Get Name="Get">\n'
            "        <Declaration><![CDATA[]]></Declaration>\n"
            "      </Get>\n"
            "    </Property>\n"
            '    <Property Name="Value2">\n'
            '      <Get Name="Get">\n'
            "        <Declaration><![CDATA[// comment]]></Declaration>\n"
            "      </Get>\n"
            "    </Property>\n"
            '    <Property Name="Value3">\n'
            '      <Get Name="Get">\n'
            "        <Declaration><![CDATA[// comment]]></Declaration>\n"
            "      </Get>\n"
            "    </Property>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = PropertyVarBlocksCheck()

        issues = check.run(file)

        # Empty CDATA is valid, so only 2 should be flagged
        assert len(issues) == 1
        assert "2 property getter(s) missing VAR blocks" in issues[0].message

    def test_check_id_matches_config(self):
        """Test check_id matches expected config ID."""
        check = PropertyVarBlocksCheck()
        assert check.check_id == "property_var_blocks"


class TestLineIdsCountCheck:
    """Tests for LineIdsCountCheck validator."""

    @classmethod
    def setup_class(cls):
        """Ensure checks are registered without mutating global registry state."""
        _ensure_structure_checks_registered()

    def test_should_skip_for_non_tcpou(self, tmp_path):
        """Test check is skipped for non-.TcPOU files."""
        gvl_file = tmp_path / "GVL_Test.TcGVL"
        gvl_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <GVL Name="GVL_Test">\n'
            "  </GVL>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(gvl_file)
        check = LineIdsCountCheck()

        assert check.should_skip(file) is True

    def test_correct_lineids_count_no_issues(self, tmp_path):
        """Test file with correct LineIds count produces no issues."""
        fb_file = tmp_path / "FB_Test.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test">\n'
            '    <Method Name="Execute">\n'
            "    </Method>\n"
            '    <LineIds Name="FB_Test">\n'
            "    </LineIds>\n"
            '    <LineIds Name="FB_Test.Execute">\n'
            "    </LineIds>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = LineIdsCountCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_missing_lineids_detected(self, tmp_path):
        """Test missing LineIds is detected."""
        fb_file = tmp_path / "FB_Test.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test">\n'
            '    <Method Name="Execute">\n'
            "    </Method>\n"
            '    <LineIds Name="FB_Test">\n'
            "    </LineIds>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = LineIdsCountCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].category == "LineIds"
        assert "Expected 2, found 1" in issues[0].message
        assert issues[0].fix_available is True

    def test_extra_lineids_detected(self, tmp_path):
        """Test extra LineIds is detected."""
        fb_file = tmp_path / "FB_Test.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test">\n'
            '    <Method Name="Execute">\n'
            "    </Method>\n"
            '    <LineIds Name="FB_Test">\n'
            "    </LineIds>\n"
            '    <LineIds Name="FB_Test.Execute">\n'
            "    </LineIds>\n"
            '    <LineIds Name="FB_Test.Extra">\n'
            "    </LineIds>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = LineIdsCountCheck()

        issues = check.run(file)

        assert len(issues) == 2  # Count mismatch + invalid entries
        assert all(i.severity == "error" for i in issues)
        assert all(i.category == "LineIds" for i in issues)
        # First issue: count mismatch
        assert "Expected 2, found 3" in issues[0].message
        # Second issue: invalid entry
        assert "Invalid LineIds Name entries" in issues[1].message
        assert "FB_Test.Extra" in issues[1].message
        assert issues[0].fix_suggestion == "Remove 1 extra LineIds entries"

    def test_lineids_with_properties(self, tmp_path):
        """Test LineIds count includes properties."""
        fb_file = tmp_path / "FB_Test.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test">\n'
            '    <Property Name="Value">\n'
            "    </Property>\n"
            '    <Method Name="Execute">\n'
            "    </Method>\n"
            '    <LineIds Name="FB_Test">\n'
            "    </LineIds>\n"
            '    <LineIds Name="FB_Test.Value.Get">\n'
            "    </LineIds>\n"
            '    <LineIds Name="FB_Test.Execute">\n'
            "    </LineIds>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = LineIdsCountCheck()

        issues = check.run(file)

        # Property + Method + 1 (POU body) = 3 expected
        assert len(issues) == 0

    def test_lineids_nested_inside_method_detected(self, tmp_path):
        """Test LineIds tags inside Method blocks are rejected."""
        fb_file = tmp_path / "FB_NestedLineIds.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_NestedLineIds">\n'
            '    <Method Name="M_Add">\n'
            '      <LineIds Name="M_Add">\n'
            "      </LineIds>\n"
            "    </Method>\n"
            '    <LineIds Name="FB_NestedLineIds"></LineIds>\n'
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = LineIdsCountCheck()
        issues = check.run(file)

        assert any("inside Method blocks" in issue.message for issue in issues)

    def test_lineids_invalid_name_detected(self, tmp_path):
        """Test non-qualified method LineIds names are rejected."""
        fb_file = tmp_path / "FB_BadLineIdsName.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_BadLineIdsName">\n'
            '    <Method Name="M_Add"></Method>\n'
            '    <LineIds Name="FB_BadLineIdsName"></LineIds>\n'
            '    <LineIds Name="M_Add"></LineIds>\n'
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = LineIdsCountCheck()
        issues = check.run(file)

        assert any("Invalid LineIds Name entries" in issue.message for issue in issues)

    def test_lineids_quality_detects_duplicate_entries(self, tmp_path):
        """Duplicate LineId entries in one block should be rejected."""
        fb_file = tmp_path / "FB_LineIdsQuality.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_LineIdsQuality">\n'
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <LineIds Name="FB_LineIdsQuality">\n'
            '      <LineId Id="1" Count="0" />\n'
            '      <LineId Id="2" Count="0" />\n'
            "    </LineIds>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        issues = LineIdsCountCheck().run(TwinCATFile(fb_file))
        assert any("LineIds quality mismatch" in issue.message for issue in issues)
        assert any("must contain exactly one LineId entry" in issue.message for issue in issues)

    def test_lineids_quality_detects_noncanonical_id_and_count(self, tmp_path):
        """Id sequence and Count should match canonical deterministic expectations."""
        fb_file = tmp_path / "FB_LineIdsCanon.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_LineIdsCanon">\n'
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Run">\n'
            "      <Declaration><![CDATA[METHOD M_Run : BOOL\n]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[M_Run := TRUE;]]></ST></Implementation>\n"
            "    </Method>\n"
            '    <LineIds Name="FB_LineIdsCanon">\n'
            '      <LineId Id="2" Count="7" />\n'
            "    </LineIds>\n"
            '    <LineIds Name="FB_LineIdsCanon.M_Run">\n'
            '      <LineId Id="9" Count="3" />\n'
            "    </LineIds>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        issues = LineIdsCountCheck().run(TwinCATFile(fb_file))
        assert any("LineIds quality mismatch" in issue.message for issue in issues)
        assert any(
            "non-canonical Id" in issue.message or "Count=" in issue.message for issue in issues
        )

    def test_check_id_matches_config(self):
        """Test check_id matches expected config ID."""
        check = LineIdsCountCheck()
        assert check.check_id == "lineids_count"


class TestElementOrderingCheck:
    """Tests for ElementOrderingCheck validator."""

    @classmethod
    def setup_class(cls):
        """Ensure checks are registered without mutating global registry state."""
        _ensure_structure_checks_registered()

    def test_should_skip_for_non_tcpou(self, tmp_path):
        """Test check is skipped for non-.TcPOU files."""
        gvl_file = tmp_path / "GVL_Test.TcGVL"
        gvl_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <GVL Name="GVL_Test">\n'
            "  </GVL>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(gvl_file)
        check = ElementOrderingCheck()

        assert check.should_skip(file) is True

    def test_should_skip_for_function(self, tmp_path):
        """Test check is skipped for FUNCTION .TcPOU files."""
        function_file = tmp_path / "FUNC_Test.TcPOU"
        function_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FUNC_Test">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION FUNC_Test : INT\n"
            "END_FUNCTION\n"
            "]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(function_file)
        check = ElementOrderingCheck()

        assert check.should_skip(file) is True

    def test_correct_order_no_issues(self, tmp_path):
        """Test file with correct element order produces no issues."""
        fb_file = tmp_path / "FB_Test.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_Test\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation>\n"
            "    </Implementation>\n"
            '    <Method Name="Execute">\n'
            "    </Method>\n"
            '    <Property Name="Value">\n'
            "    </Property>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = ElementOrderingCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_declaration_after_implementation_detected(self, tmp_path):
        """Test Declaration after Implementation is detected."""
        fb_file = tmp_path / "FB_Test.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test">\n'
            "    <Implementation>\n"
            "    </Implementation>\n"
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_Test\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = ElementOrderingCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].category == "Order"
        assert "Declaration should come before Implementation" in issues[0].message

    def test_method_before_implementation_detected(self, tmp_path):
        """Test Method before Implementation is detected."""
        fb_file = tmp_path / "FB_Test.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_Test\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            '    <Method Name="Execute">\n'
            "    </Method>\n"
            "    <Implementation>\n"
            "    </Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = ElementOrderingCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].category == "Order"
        assert "Methods should come after Implementation" in issues[0].message

    def test_property_before_implementation_detected(self, tmp_path):
        """Test Property before Implementation is detected."""
        fb_file = tmp_path / "FB_Test.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_Test\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            '    <Property Name="Value">\n'
            "    </Property>\n"
            "    <Implementation>\n"
            "    </Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = ElementOrderingCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].category == "Order"
        assert "Properties should come after Implementation" in issues[0].message

    def test_check_id_matches_config(self):
        """Test check_id matches expected config ID."""
        check = ElementOrderingCheck()
        assert check.check_id == "element_ordering"


class TestPouStructureCheck:
    """Tests for PouStructureCheck validator."""

    @classmethod
    def setup_class(cls):
        """Ensure checks are registered without mutating global registry state."""
        _ensure_structure_checks_registered()

    def test_should_skip_for_non_pou(self, tmp_path):
        """Test check is skipped for files without POU subtype."""
        gvl_file = tmp_path / "GVL_Test.TcGVL"
        gvl_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <GVL Name="GVL_Test">\n'
            "  </GVL>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(gvl_file)
        check = PouStructureCheck()

        assert check.should_skip(file) is True

    def test_valid_function_no_issues(self, tmp_path):
        """Test valid FUNCTION with return type produces no issues."""
        function_file = tmp_path / "FUNC_Test.TcPOU"
        function_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FUNC_Test">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION FUNC_Test : INT\n"
            "VAR_INPUT\n"
            "  nValue : INT;\n"
            "END_VAR\n"
            "END_FUNCTION\n"
            "]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(function_file)
        check = PouStructureCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_function_with_method_detected(self, tmp_path):
        """Test FUNCTION with Method is detected."""
        function_file = tmp_path / "FUNC_Test.TcPOU"
        function_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FUNC_Test">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION FUNC_Test : INT\n"
            "END_FUNCTION\n"
            "]]></Declaration>\n"
            '    <Method Name="Helper">\n'
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(function_file)
        check = PouStructureCheck()

        issues = check.run(file)

        assert len(issues) >= 1
        method_issues = [i for i in issues if "Method" in i.message]
        assert len(method_issues) == 1
        assert method_issues[0].severity == "error"
        assert method_issues[0].category == "Structure"
        assert "1 Method(s)" in method_issues[0].message
        assert "FUNCTIONs cannot have Methods" in method_issues[0].message

    def test_function_with_property_detected(self, tmp_path):
        """Test FUNCTION with Property is detected."""
        function_file = tmp_path / "FUNC_Test.TcPOU"
        function_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FUNC_Test">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION FUNC_Test : INT\n"
            "END_FUNCTION\n"
            "]]></Declaration>\n"
            '    <Property Name="Value">\n'
            "    </Property>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(function_file)
        check = PouStructureCheck()

        issues = check.run(file)

        assert len(issues) >= 1
        property_issues = [i for i in issues if "Property" in i.message]
        assert len(property_issues) == 1
        assert property_issues[0].severity == "error"
        assert property_issues[0].category == "Structure"
        assert "1 Property" in property_issues[0].message
        assert "FUNCTIONs cannot have Properties" in property_issues[0].message

    def test_function_with_action_detected(self, tmp_path):
        """Test FUNCTION with Action is detected."""
        function_file = tmp_path / "FUNC_Test.TcPOU"
        function_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FUNC_Test">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION FUNC_Test : INT\n"
            "END_FUNCTION\n"
            "]]></Declaration>\n"
            '    <Action Name="Initialize">\n'
            "    </Action>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(function_file)
        check = PouStructureCheck()

        issues = check.run(file)

        assert len(issues) >= 1
        action_issues = [i for i in issues if "Action" in i.message]
        assert len(action_issues) == 1
        assert action_issues[0].severity == "error"
        assert action_issues[0].category == "Structure"
        assert "1 Action(s)" in action_issues[0].message
        assert "FUNCTIONs cannot have Actions" in action_issues[0].message

    def test_function_missing_return_type_detected(self, tmp_path):
        """Test FUNCTION missing return type is detected."""
        function_file = tmp_path / "FUNC_Test.TcPOU"
        function_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FUNC_Test">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION FUNC_Test\n"
            "VAR_INPUT\n"
            "  nValue : INT;\n"
            "END_VAR\n"
            "END_FUNCTION\n"
            "]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(function_file)
        check = PouStructureCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].category == "Structure"
        assert "missing a return type" in issues[0].message
        assert "FUNCTION Name : ReturnType" in issues[0].message

    def test_program_with_property_warning(self, tmp_path):
        """Test PROGRAM with Property generates warning."""
        program_file = tmp_path / "PRG_Test.TcPOU"
        program_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="PRG_Test">\n'
            "    <Declaration><![CDATA[\n"
            "PROGRAM PRG_Test\n"
            "END_PROGRAM\n"
            "]]></Declaration>\n"
            '    <Property Name="Status">\n'
            "    </Property>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(program_file)
        check = PouStructureCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].category == "Structure"
        assert "PROGRAM contains 1 Property" in issues[0].message
        assert "should not have Properties" in issues[0].message

    def test_function_block_no_issues(self, tmp_path):
        """Test valid FUNCTION_BLOCK produces no issues."""
        fb_file = tmp_path / "FB_Test.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_Test\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            '    <Method Name="Execute">\n'
            "    </Method>\n"
            '    <Property Name="Value">\n'
            "    </Property>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = PouStructureCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_method_declaration_inside_main_implementation_detected(self, tmp_path):
        """Test METHOD declared in main ST implementation is detected."""
        fb_file = tmp_path / "FB_BadImpl.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_BadImpl" '
            'Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_BadImpl\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation>\n"
            "      <ST><![CDATA[\n"
            "METHOD LogError : BOOL\n"
            "LogError := TRUE;\n"
            "END_METHOD\n"
            "]]></ST>\n"
            "    </Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = PouStructureCheck()
        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].category == "Structure"
        assert (
            "METHOD declaration found inside main <Implementation><ST> block" in issues[0].message
        )
        assert issues[0].fix_available is False

    def test_var_temp_inside_main_implementation_detected(self, tmp_path):
        """Test VAR_TEMP declaration in main implementation ST is flagged."""
        fb_file = tmp_path / "FB_MainVarTemp.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_MainVarTemp" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_MainVarTemp\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation>\n"
            "      <ST><![CDATA[\n"
            "VAR_TEMP\n"
            "  nX : INT;\n"
            "END_VAR\n"
            "nX := 1;\n"
            "]]></ST>\n"
            "    </Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        issues = PouStructureCheck().run(TwinCATFile(fb_file))
        assert any(
            "VAR declaration block found inside main <Implementation><ST> block" in i.message
            for i in issues
        )

    def test_inline_type_in_pou_declaration_detected(self, tmp_path):
        """Inline TYPE blocks should be rejected in POU declarations."""
        prg_file = tmp_path / "PRG_InlineType.TcPOU"
        prg_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="PRG_InlineType" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "PROGRAM PRG_InlineType\n"
            "VAR\n"
            "  nValue : INT;\n"
            "END_VAR\n"
            "TYPE E_Local : (A := 0, B := 1) DINT;\n"
            "END_TYPE\n"
            "END_PROGRAM\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        issues = PouStructureCheck().run(TwinCATFile(prg_file))
        assert any(
            "Inline TYPE declaration detected in POU declaration" in i.message for i in issues
        )

    def test_const_end_const_in_pou_declaration_detected(self, tmp_path):
        """CONST...END_CONST should be rejected in POU declaration blocks."""
        fb_file = tmp_path / "FB_BadConstBlock.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_BadConstBlock" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_BadConstBlock\n"
            "CONST\n"
            "  N_MAX : UINT := 4;\n"
            "END_CONST\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        issues = PouStructureCheck().run(TwinCATFile(fb_file))
        assert any(
            "CONST...END_CONST block detected in POU declaration" in i.message for i in issues
        )

    def test_var_temp_in_pou_declaration_detected(self, tmp_path):
        """VAR_TEMP in top-level POU declaration should be rejected by project convention."""
        fb_file = tmp_path / "FB_BadVarTempDecl.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_BadVarTempDecl" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_BadVarTempDecl\n"
            "VAR_TEMP\n"
            "  nScratch : INT;\n"
            "END_VAR\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        issues = PouStructureCheck().run(TwinCATFile(fb_file))
        assert any("VAR_TEMP block detected in POU declaration" in i.message for i in issues)

    def test_var_temp_in_method_declaration_detected(self, tmp_path):
        """VAR_TEMP in method declaration should be rejected by project convention."""
        fb_file = tmp_path / "FB_BadVarTempMethod.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_BadVarTempMethod" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_BadVarTempMethod\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Test">\n'
            "      <Declaration><![CDATA[METHOD M_Test : BOOL\n"
            "VAR_TEMP\n"
            "  nScratch : INT;\n"
            "END_VAR\n"
            "]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[\n"
            "M_Test := TRUE;\n"
            "RETURN;\n"
            "]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        issues = PouStructureCheck().run(TwinCATFile(fb_file))
        assert any(
            "Method declaration contains VAR_TEMP block(s): M_Test" in i.message for i in issues
        )

    def test_var_protected_in_pou_declaration_detected(self, tmp_path):
        """VAR PROTECTED should be rejected in POU declarations."""
        fb_file = tmp_path / "FB_BadVarProtected.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_BadVarProtected" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_BadVarProtected\n"
            "VAR PROTECTED\n"
            "  nValue : INT;\n"
            "END_VAR\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        issues = PouStructureCheck().run(TwinCATFile(fb_file))
        assert any("VAR PROTECTED / VAR_PROTECTED block detected" in i.message for i in issues)
        # Canonical fix suggestion may mention VAR_PROTECTED only as the thing to *replace*, not as a solution.
        # Guard: the suggestion must contain "replace" or "with VAR" to confirm it points away from VAR_PROTECTED.
        for issue in issues:
            if issue.fix_suggestion and (
                "VAR_PROTECTED" in issue.fix_suggestion or "VAR PROTECTED" in issue.fix_suggestion
            ):
                suggestion_lower = issue.fix_suggestion.lower()
                assert (
                    "replace" in suggestion_lower or "with var" in suggestion_lower
                ), f"fix_suggestion mentions VAR_PROTECTED without directing away from it: {issue.fix_suggestion!r}"

    def test_var_protected_underscore_spelling_detected(self, tmp_path):
        """VAR_PROTECTED (underscore form) should also be rejected in POU declarations."""
        fb_file = tmp_path / "FB_BadVarProtectedUnderscore.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_BadVarProtectedUnderscore" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_BadVarProtectedUnderscore\n"
            "VAR_PROTECTED\n"
            "  nValue : INT;\n"
            "END_VAR\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        issues = PouStructureCheck().run(TwinCATFile(fb_file))
        assert any("VAR PROTECTED / VAR_PROTECTED block detected" in i.message for i in issues)
        # Must be an error, never fixable by auto-fix
        var_protected_issues = [i for i in issues if "VAR PROTECTED / VAR_PROTECTED" in i.message]
        assert var_protected_issues
        assert all(i.severity == "error" for i in var_protected_issues)
        assert all(not i.fix_available for i in var_protected_issues)

    def test_interface_array_used_without_binding_detected(self, tmp_path):
        """Interface array member calls without assignment should be flagged."""
        prg_file = tmp_path / "PRG_UnboundIfaces.TcPOU"
        prg_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="PRG_UnboundIfaces" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "PROGRAM PRG_UnboundIfaces\n"
            "VAR\n"
            "  aDrives : ARRAY[0..1] OF I_Drive;\n"
            "  nIdx    : UINT;\n"
            "END_VAR\n"
            "END_PROGRAM\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[\n"
            "FOR nIdx := 0 TO 1 DO\n"
            "  aDrives[nIdx].M_Reset();\n"
            "END_FOR\n"
            "]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        issues = PouStructureCheck().run(TwinCATFile(prg_file))
        assert any(
            "Potential unbound interface array reference(s): aDrives" in i.message for i in issues
        )

    def test_interface_array_with_binding_not_flagged(self, tmp_path):
        """Interface array should not be flagged when explicit bindings exist."""
        prg_file = tmp_path / "PRG_BoundIfaces.TcPOU"
        prg_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="PRG_BoundIfaces" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "PROGRAM PRG_BoundIfaces\n"
            "VAR\n"
            "  fbDriveA : FB_DriveA;\n"
            "  aDrives  : ARRAY[0..1] OF I_Drive;\n"
            "  nIdx     : UINT;\n"
            "END_VAR\n"
            "END_PROGRAM\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[\n"
            "aDrives[0] := fbDriveA;\n"
            "FOR nIdx := 0 TO 1 DO\n"
            "  aDrives[nIdx].M_Reset();\n"
            "END_FOR\n"
            "]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        issues = PouStructureCheck().run(TwinCATFile(prg_file))
        assert not any("Potential unbound interface array reference" in i.message for i in issues)

    def test_implements_interface_without_tc_io_detected(self, tmp_path):
        """Test missing interface definition for IMPLEMENTS clause is detected."""
        # Use a unique interface name to avoid cross-test pollution from rglob
        fb_file = tmp_path / "FB_WithInterface.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_WithInterface" '
            'Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_WithInterface IMPLEMENTS I_UniqueTestItf\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = PouStructureCheck()
        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].category == "Structure"
        assert "implements interface 'I_UniqueTestItf'" in issues[0].message
        assert issues[0].fix_available is False

    def test_implements_interface_with_matching_tc_io_no_issue(self, tmp_path):
        """Test no issue when IMPLEMENTS interface has matching TcIO definition."""
        itf_file = tmp_path / "I_Log.TcIO"
        itf_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <Itf Name="I_Log" Id="{12345678-1234-1234-1234-123456789abc}">\n'
            "    <Declaration><![CDATA[\n"
            "INTERFACE I_Log\n"
            "END_INTERFACE\n"
            "]]></Declaration>\n"
            "  </Itf>\n"
            "</TcPlcObject>"
        )

        fb_file = tmp_path / "FB_WithInterface.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_WithInterface" '
            'Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_WithInterface IMPLEMENTS I_Log\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = PouStructureCheck()
        issues = check.run(file)

        assert len(issues) == 0

    def test_method_implementation_var_block_detected(self, tmp_path):
        """Test VAR declarations inside method implementation ST are detected."""
        fb_file = tmp_path / "FB_MethodVar.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_MethodVar" '
            'Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_MethodVar\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation>\n"
            "      <ST><![CDATA[]]></ST>\n"
            "    </Implementation>\n"
            '    <Method Name="GetLastError">\n'
            "      <Declaration><![CDATA[METHOD GetLastError : STRING(255)]]></Declaration>\n"
            "      <Implementation>\n"
            "        <ST><![CDATA[\n"
            "VAR nLastIndex : UDINT;\n"
            "nLastIndex := 0;\n"
            "RETURN '';\n"
            "        ]]></ST>\n"
            "      </Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = PouStructureCheck()
        issues = check.run(file)

        assert len(issues) == 3  # VAR block + invalid RETURN + undeclared assignment
        assert all(i.severity == "error" for i in issues)
        assert all(i.category == "Structure" for i in issues)
        # Check reports all 3 structure violations
        assert "Method implementation contains VAR declaration block(s)" in issues[0].message
        assert "Invalid ST return syntax" in issues[1].message
        assert "Undeclared assignment target" in issues[2].message

    def test_inline_struct_in_pou_var_detected(self, tmp_path):
        """Test inline STRUCT declarations in POU declarations are rejected."""
        fb_file = tmp_path / "FB_InlineStruct.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_InlineStruct" Id="{12345678-1234-1234-1234-123456789abc}">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_InlineStruct\n"
            "VAR\n"
            "  aHistory : ARRAY[0..99] OF STRUCT\n"
            "    nAlarmId : DINT;\n"
            "  END_STRUCT;\n"
            "END_VAR\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = PouStructureCheck()
        issues = check.run(file)

        assert any("Inline STRUCT declaration detected" in issue.message for issue in issues)

    def test_interface_misfiled_as_tcpou_detected(self, tmp_path):
        """Test INTERFACE declarations in .TcPOU files are flagged."""
        interface_pou = tmp_path / "I_Record.TcPOU"
        interface_pou.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="I_Record" Id="{12345678-1234-1234-1234-123456789abc}">\n'
            "    <Declaration><![CDATA[\n"
            "INTERFACE I_Record\n"
            "END_INTERFACE\n"
            "]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(interface_pou)
        check = PouStructureCheck()
        issues = check.run(file)

        assert len(issues) >= 1
        assert any(
            "INTERFACE declaration found in .TcPOU file" in issue.message for issue in issues
        )

    def test_invalid_return_value_statement_detected(self, tmp_path):
        """Test `RETURN value;` in methods is flagged."""
        fb_file = tmp_path / "FB_ReturnBad.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_ReturnBad" '
            'Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_ReturnBad\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Add">\n'
            "      <Declaration><![CDATA[METHOD M_Add : BOOL]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[\n"
            "RETURN FALSE;\n"
            "]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = PouStructureCheck()
        issues = check.run(file)

        assert len(issues) >= 1
        assert any("Invalid ST return syntax" in issue.message for issue in issues)

    def test_var_input_mutation_detected(self, tmp_path):
        """Test assignments to VAR_INPUT symbols are flagged."""
        fb_file = tmp_path / "FB_InputMutate.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_InputMutate" '
            'Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_InputMutate\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Add">\n'
            "      <Declaration><![CDATA[METHOD M_Add : BOOL\n"
            "VAR_INPUT\n"
            "  nSeverity : INT;\n"
            "END_VAR]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[\n"
            "nSeverity := 0;\n"
            "M_Add := TRUE;\n"
            "RETURN;\n"
            "]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = PouStructureCheck()
        issues = check.run(file)

        assert len(issues) >= 1
        assert any(
            "Assignments to VAR_INPUT parameter(s) detected" in issue.message for issue in issues
        )

    def test_undeclared_method_assignment_detected(self, tmp_path):
        """Test assignment to undeclared local variables is flagged."""
        fb_file = tmp_path / "FB_Undeclared.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Undeclared" '
            'Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_Undeclared\n"
            "VAR\n"
            "  nCount : UINT;\n"
            "END_VAR\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Add">\n'
            "      <Declaration><![CDATA[METHOD M_Add : BOOL]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[\n"
            "nIndex := nCount;\n"
            "M_Add := TRUE;\n"
            "RETURN;\n"
            "]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = PouStructureCheck()
        issues = check.run(file)

        assert len(issues) >= 1
        assert any("Undeclared assignment target(s)" in issue.message for issue in issues)

    def test_extends_base_without_tcpou_detected(self, tmp_path):
        """Test missing base FUNCTION_BLOCK for EXTENDS is detected."""
        # Use a unique base name to avoid cross-test pollution from rglob
        derived_file = tmp_path / "FB_Derived.TcPOU"
        derived_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Derived" '
            'Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_Derived EXTENDS FB_UniqueTestBase\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(derived_file)
        check = PouStructureCheck()
        issues = check.run(file)

        assert any("extends base 'FB_UniqueTestBase'" in issue.message for issue in issues)

    def test_extends_base_with_matching_tcpou_no_issue(self, tmp_path):
        """Test no issue when EXTENDS base FUNCTION_BLOCK exists."""
        base_file = tmp_path / "FB_Base.TcPOU"
        base_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Base" '
            'Id="{22345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_Base\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        derived_file = tmp_path / "FB_Derived.TcPOU"
        derived_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Derived" '
            'Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(derived_file)
        check = PouStructureCheck()
        issues = check.run(file)

        assert not any("extends base 'FB_Base'" in issue.message for issue in issues)

    def test_extends_on_non_function_block_detected(self, tmp_path):
        """Test EXTENDS on FUNCTION is flagged as invalid."""
        function_file = tmp_path / "FUNC_BadExtends.TcPOU"
        function_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FUNC_BadExtends" '
            'Id="{32345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[\n"
            "FUNCTION FUNC_BadExtends : BOOL EXTENDS FB_Base\n"
            "END_FUNCTION\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(function_file)
        check = PouStructureCheck()
        issues = check.run(file)

        assert any(
            "Only FUNCTION_BLOCK can inherit via EXTENDS" in issue.message for issue in issues
        )

    def test_implements_interface_signature_mismatch_detected(self, tmp_path):
        """Test method signature mismatch vs .TcIO interface is detected."""
        itf_file = tmp_path / "I_Record.TcIO"
        itf_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <Itf Name="I_Record" Id="{12345678-1234-1234-1234-123456789abc}">\n'
            "    <Declaration><![CDATA[INTERFACE I_Record\n]]></Declaration>\n"
            '    <Method Name="M_Add">\n'
            "      <Declaration><![CDATA[METHOD M_Add : BOOL\n"
            "VAR_INPUT\n"
            "  nSeverity : INT;\n"
            "END_VAR\n"
            "]]></Declaration>\n"
            "    </Method>\n"
            "  </Itf>\n"
            "</TcPlcObject>"
        )
        fb_file = tmp_path / "FB_Record.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Record" Id="{22345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Record IMPLEMENTS I_Record\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Add">\n'
            "      <Declaration><![CDATA[METHOD M_Add : BOOL\n"
            "VAR_INPUT\n"
            "  nSeverity : DINT;\n"
            "END_VAR\n"
            "]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[M_Add := TRUE;]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = PouStructureCheck()
        issues = check.run(file)
        assert any("signature mismatch" in issue.message for issue in issues)

    def test_implements_interface_signature_ignores_inline_comments(self, tmp_path):
        """Equivalent signatures should match even when interface includes inline comments."""
        itf_file = tmp_path / "I_Record.TcIO"
        itf_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <Itf Name="I_Record" Id="{12345678-1234-1234-1234-123456789abc}">\n'
            "    <Declaration><![CDATA[INTERFACE I_Record\n]]></Declaration>\n"
            '    <Method Name="M_Stop">\n'
            "      <Declaration><![CDATA[METHOD M_Stop : BOOL\n"
            "VAR_INPUT\n"
            "  bImmediate : BOOL;   (* operator requested immediate stop *)\n"
            "END_VAR\n"
            "]]></Declaration>\n"
            "    </Method>\n"
            "  </Itf>\n"
            "</TcPlcObject>"
        )
        fb_file = tmp_path / "FB_Record.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Record" Id="{22345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Record IMPLEMENTS I_Record\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Stop">\n'
            "      <Declaration><![CDATA[METHOD M_Stop : BOOL\n"
            "VAR_INPUT\n"
            "  bImmediate : BOOL;\n"
            "END_VAR\n"
            "]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[M_Stop := TRUE;]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = PouStructureCheck()
        issues = check.run(file)
        assert not any("signature mismatch" in issue.message for issue in issues)

    def test_st_syntax_guard_detects_missing_semicolon(self, tmp_path):
        """Test ST syntax guard catches assignment without semicolon."""
        fb_file = tmp_path / "FB_Syntax.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Syntax" Id="{32345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Syntax\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Run">\n'
            "      <Declaration><![CDATA[METHOD M_Run : BOOL\n]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[\n"
            "M_Run := TRUE\n"
            "END_IF\n"
            "]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = PouStructureCheck()
        issues = check.run(file)
        assert any("ST syntax guard detected" in issue.message for issue in issues)

    def test_st_syntax_guard_ignores_if_tokens_in_comments_and_strings(self, tmp_path):
        """IF/END_IF inside comments/strings should not create false unmatched errors."""
        fb_file = tmp_path / "FB_SyntaxComments.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_SyntaxComments" Id="{42345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_SyntaxComments\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Run">\n'
            "      <Declaration><![CDATA[METHOD M_Run : BOOL\n]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[\n"
            "// IF this were code, it would be unmatched\n"
            "M_Run := TRUE;\n"
            "IF TRUE THEN\n"
            "  M_Run := 'END_IF';\n"
            "END_IF;\n"
            "]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(fb_file)
        check = PouStructureCheck()
        issues = check.run(file)
        assert not any("Unmatched IF/END_IF" in issue.message for issue in issues)

    def test_st_syntax_guard_allows_missing_terminator_semicolon(self, tmp_path):
        """END_IF without ';' should not be flagged as a syntax error."""
        fb_file = tmp_path / "FB_SyntaxNoTermSemi.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_SyntaxNoTermSemi" Id="{52345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_SyntaxNoTermSemi\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Run">\n'
            "      <Declaration><![CDATA[METHOD M_Run : BOOL\n]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[\n"
            "IF TRUE THEN\n"
            "  M_Run := TRUE;\n"
            "END_IF\n"
            "]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        issues = PouStructureCheck().run(TwinCATFile(fb_file))
        assert not any("Missing semicolon on terminator" in issue.message for issue in issues)

    def test_st_syntax_guard_ignores_trailing_block_comment_after_assignment(self, tmp_path):
        """Assignment with trailing (* ... *) comment should not trigger semicolon false positives."""
        fb_file = tmp_path / "FB_SyntaxInlineComment.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_SyntaxInlineComment" Id="{62345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_SyntaxInlineComment\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Run">\n'
            "      <Declaration><![CDATA[METHOD M_Run : BOOL\n]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[\n"
            "M_Run := TRUE; (* trailing inline comment *)\n"
            "]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        issues = PouStructureCheck().run(TwinCATFile(fb_file))
        assert not any("Missing semicolon after assignment" in issue.message for issue in issues)

    def test_check_id_matches_config(self):
        """Test check_id matches expected config ID."""
        check = PouStructureCheck()
        assert check.check_id == "pou_structure"


class TestPouStructureSubChecks:
    """Tests for the focused PouStructure sub-checks (WS4 decomposition)."""

    # ------------------------------------------------------------------ #
    # PouStructureHeaderCheck
    # ------------------------------------------------------------------ #

    def test_header_check_id(self):
        assert PouStructureHeaderCheck().check_id == "pou_structure_header"

    def test_header_skips_non_tcpou(self, tmp_path):
        """Header check must not run on .TcIO or .TcDUT files."""
        f = tmp_path / "I_Foo.TcIO"
        f.write_text(
            '<TcPlcObject><Itf Name="I_Foo" Id="{11111111-0000-0000-0000-000000000001}"/></TcPlcObject>'
        )
        check = PouStructureHeaderCheck()
        assert check.should_skip(TwinCATFile(f))

    def test_header_runs_for_tcpou_with_none_subtype(self, tmp_path):
        """Header check must NOT skip .TcPOU even when pou_subtype is None (misfiled interface)."""
        iface_file = tmp_path / "I_Record.TcPOU"
        iface_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="I_Record" Id="{12345678-0000-0000-0000-000000000001}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[INTERFACE I_Record\n"
            "END_INTERFACE\n]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        file = TwinCATFile(iface_file)
        check = PouStructureHeaderCheck()
        assert not check.should_skip(file)
        issues = check.run(file)
        assert any("INTERFACE" in issue.message for issue in issues)

    def test_header_inline_struct_detected(self, tmp_path):
        fb_file = tmp_path / "FB_Test.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test" Id="{12345678-0000-0000-0000-000000000002}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test\n"
            "VAR\n"
            "  myStruct : STRUCT\n"
            "    x : INT;\n"
            "  END_STRUCT;\n"
            "END_VAR\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        file = TwinCATFile(fb_file)
        issues = PouStructureHeaderCheck().run(file)
        assert any("Inline STRUCT" in issue.message for issue in issues)

    # ------------------------------------------------------------------ #
    # PouStructureMethodsCheck
    # ------------------------------------------------------------------ #

    def test_methods_check_id(self):
        assert PouStructureMethodsCheck().check_id == "pou_structure_methods"

    def test_methods_skips_when_subtype_none(self, tmp_path):
        iface_file = tmp_path / "I_Foo.TcPOU"
        iface_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="I_Foo" Id="{12345678-0000-0000-0000-000000000003}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[INTERFACE I_Foo\nEND_INTERFACE\n]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        assert PouStructureMethodsCheck().should_skip(TwinCATFile(iface_file))

    def test_methods_detects_method_in_main_implementation(self, tmp_path):
        fb_file = tmp_path / "FB_M.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_M" Id="{12345678-0000-0000-0000-000000000004}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_M\nVAR\nEND_VAR\n]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[\n"
            "METHOD M_Run : BOOL\n"
            "M_Run := TRUE;\n"
            "END_METHOD\n"
            "]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        issues = PouStructureMethodsCheck().run(TwinCATFile(fb_file))
        assert any("METHOD declaration found inside main" in issue.message for issue in issues)

    def test_methods_warns_when_reset_clears_hard_fault_without_auth(self, tmp_path):
        fb_file = tmp_path / "FB_ResetUnsafe.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_ResetUnsafe" Id="{12345678-0000-0000-0000-000000000046}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_ResetUnsafe\nEND_FUNCTION_BLOCK\n]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Execute">\n'
            "      <Declaration><![CDATA[METHOD M_Execute : BOOL\n]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[\n"
            "THIS^.M_SetFault(nCode := 99, bHard := TRUE);\n"
            "M_Execute := FALSE;\n"
            "]]></ST></Implementation>\n"
            "    </Method>\n"
            '    <Method Name="M_Reset">\n'
            "      <Declaration><![CDATA[METHOD M_Reset : BOOL\nVAR_INPUT\nEND_VAR\n]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[\n"
            "THIS^.M_ClearFault();\n"
            "M_Reset := TRUE;\n"
            "]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        issues = PouStructureMethodsCheck().run(TwinCATFile(fb_file))
        assert any(
            issue.severity == "warning"
            and "clear fault state without authorization input" in issue.message
            for issue in issues
        )
        assert any(
            issue.severity == "warning" and "no explicit hard-reset API" in issue.message
            for issue in issues
        )

    def test_methods_warns_when_reset_result_is_ignored(self, tmp_path):
        prg_file = tmp_path / "PRG_ResetIgnored.TcPOU"
        prg_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="PRG_ResetIgnored" Id="{12345678-0000-0000-0000-000000000047}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[PROGRAM PRG_ResetIgnored\n"
            "VAR\n"
            "  aUnits : ARRAY[0..1] OF I_ProcessUnit;\n"
            "  i : INT;\n"
            "END_VAR\n"
            "END_PROGRAM\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[\n"
            "FOR i := 0 TO 1 DO\n"
            "  aUnits[i].M_Reset();\n"
            "END_FOR;\n"
            "]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        issues = PouStructureMethodsCheck().run(TwinCATFile(prg_file))
        assert any(
            issue.severity == "warning" and "M_Reset call(s) ignored" in issue.message
            for issue in issues
        )

    def test_methods_no_warning_when_reset_result_checked(self, tmp_path):
        prg_file = tmp_path / "PRG_ResetChecked.TcPOU"
        prg_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="PRG_ResetChecked" Id="{12345678-0000-0000-0000-000000000048}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[PROGRAM PRG_ResetChecked\n"
            "VAR\n"
            "  aUnits : ARRAY[0..1] OF I_ProcessUnit;\n"
            "  i : INT;\n"
            "END_VAR\n"
            "END_PROGRAM\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[\n"
            "FOR i := 0 TO 1 DO\n"
            "  IF NOT aUnits[i].M_Reset() THEN\n"
            "    RETURN;\n"
            "  END_IF;\n"
            "END_FOR;\n"
            "]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        issues = PouStructureMethodsCheck().run(TwinCATFile(prg_file))
        assert not any("M_Reset call(s) ignored" in issue.message for issue in issues)

    def test_methods_warns_on_unconditional_reset_loop(self, tmp_path):
        prg_file = tmp_path / "PRG_ResetLoop.TcPOU"
        prg_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="PRG_ResetLoop" Id="{12345678-0000-0000-0000-000000000049}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[PROGRAM PRG_ResetLoop\n"
            "VAR\n"
            "  aUnits : ARRAY[0..1] OF I_ProcessUnit;\n"
            "  i : INT;\n"
            "END_VAR\n"
            "END_PROGRAM\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[\n"
            "FOR i := 0 TO 1 DO\n"
            "  aUnits[i].M_Reset(bAuthorizeHardRecovery := FALSE);\n"
            "END_FOR;\n"
            "]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        issues = PouStructureMethodsCheck().run(TwinCATFile(prg_file))
        assert any("reset-spam loop" in issue.message for issue in issues)

    def test_methods_no_reset_spam_warning_when_loop_has_guard(self, tmp_path):
        prg_file = tmp_path / "PRG_ResetLoopGuarded.TcPOU"
        prg_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="PRG_ResetLoopGuarded" Id="{12345678-0000-0000-0000-000000000050}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[PROGRAM PRG_ResetLoopGuarded\n"
            "VAR\n"
            "  aUnits : ARRAY[0..1] OF I_ProcessUnit;\n"
            "  i : INT;\n"
            "  bAllow : BOOL;\n"
            "END_VAR\n"
            "END_PROGRAM\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[\n"
            "FOR i := 0 TO 1 DO\n"
            "  IF bAllow THEN\n"
            "    aUnits[i].M_Reset(bAuthorizeHardRecovery := FALSE);\n"
            "  END_IF;\n"
            "END_FOR;\n"
            "]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        issues = PouStructureMethodsCheck().run(TwinCATFile(prg_file))
        assert not any("reset-spam loop" in issue.message for issue in issues)

    def test_methods_no_reset_spam_warning_when_parent_edge_guard_wraps_loop(self, tmp_path):
        prg_file = tmp_path / "PRG_ResetLoopParentGuarded.TcPOU"
        prg_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="PRG_ResetLoopParentGuarded" Id="{12345678-0000-0000-0000-000000000051}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[PROGRAM PRG_ResetLoopParentGuarded\n"
            "VAR\n"
            "  aUnits : ARRAY[0..1] OF I_ProcessUnit;\n"
            "  i : INT;\n"
            "  bRetryEdge : BOOL;\n"
            "  bRetryEdgePrev : BOOL;\n"
            "END_VAR\n"
            "END_PROGRAM\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[\n"
            "IF bRetryEdge AND NOT bRetryEdgePrev THEN\n"
            "  FOR i := 0 TO 1 DO\n"
            "    aUnits[i].M_Reset(bAuthorizeHardRecovery := TRUE);\n"
            "  END_FOR;\n"
            "END_IF;\n"
            "]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        issues = PouStructureMethodsCheck().run(TwinCATFile(prg_file))
        assert not any("reset-spam loop" in issue.message for issue in issues)

    def test_main_var_input_mutation_check_id(self):
        assert MainVarInputMutationCheck().check_id == "main_var_input_mutation"

    def test_main_var_input_mutation_detects_main_st_assignment(self, tmp_path):
        fb_file = tmp_path / "FB_InputMutMain.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_InputMutMain" Id="{12345678-0000-0000-0000-000000000041}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_InputMutMain\n"
            "VAR_INPUT\n"
            "  bResetAll : BOOL;\n"
            "END_VAR\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[\n"
            "IF bResetAll THEN\n"
            "  bResetAll := FALSE;\n"
            "END_IF;\n"
            "]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        issues = MainVarInputMutationCheck().run(TwinCATFile(fb_file))
        assert any(
            "VAR_INPUT symbol(s) in main implementation" in issue.message for issue in issues
        )
        assert any("bResetAll" in issue.message for issue in issues)

    def test_main_var_input_mutation_ignores_method_var_input_assignment(self, tmp_path):
        fb_file = tmp_path / "FB_InputMutMethodOnly.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_InputMutMethodOnly" Id="{12345678-0000-0000-0000-000000000042}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_InputMutMethodOnly\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Run">\n'
            "      <Declaration><![CDATA[METHOD M_Run : BOOL\n"
            "VAR_INPUT\n"
            "  bResetAll : BOOL;\n"
            "END_VAR\n"
            "]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[\n"
            "bResetAll := FALSE;\n"
            "M_Run := TRUE;\n"
            "]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        issues = MainVarInputMutationCheck().run(TwinCATFile(fb_file))
        assert issues == []

    def test_unsigned_loop_underflow_check_id(self):
        assert UnsignedLoopUnderflowCheck().check_id == "unsigned_loop_underflow"

    def test_unsigned_loop_underflow_detects_uint_upper_bound_minus_one(self, tmp_path):
        fb_file = tmp_path / "FB_Underflow.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Underflow" Id="{12345678-0000-0000-0000-000000000043}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Underflow\n"
            "VAR\n"
            "  nCount : UINT;\n"
            "  i      : UINT;\n"
            "END_VAR\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[\n"
            "FOR i := 0 TO nCount - 1 DO\n"
            "END_FOR;\n"
            "]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        issues = UnsignedLoopUnderflowCheck().run(TwinCATFile(fb_file))
        assert any("unsigned FOR-loop underflow" in issue.message for issue in issues)
        assert any("nCount - 1" in issue.message for issue in issues)

    def test_unsigned_loop_underflow_does_not_flag_signed_counter(self, tmp_path):
        fb_file = tmp_path / "FB_NoUnderflow.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_NoUnderflow" Id="{12345678-0000-0000-0000-000000000044}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_NoUnderflow\n"
            "VAR\n"
            "  nCount : INT;\n"
            "  i      : INT;\n"
            "END_VAR\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[\n"
            "FOR i := 0 TO nCount - 1 DO\n"
            "END_FOR;\n"
            "]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        issues = UnsignedLoopUnderflowCheck().run(TwinCATFile(fb_file))
        assert issues == []

    def test_unsigned_loop_underflow_does_not_flag_guarded_unsigned_counter(self, tmp_path):
        fb_file = tmp_path / "FB_GuardedUnderflow.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_GuardedUnderflow" Id="{12345678-0000-0000-0000-000000000045}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_GuardedUnderflow\n"
            "VAR\n"
            "  nCount : UINT;\n"
            "  i      : UINT;\n"
            "END_VAR\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[\n"
            "IF nCount > 0 THEN\n"
            "  FOR i := 0 TO nCount - 1 DO\n"
            "  END_FOR;\n"
            "END_IF;\n"
            "]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        issues = UnsignedLoopUnderflowCheck().run(TwinCATFile(fb_file))
        assert issues == []

    # ------------------------------------------------------------------ #
    # PouStructureInterfaceCheck
    # ------------------------------------------------------------------ #

    def test_interface_check_id(self):
        assert PouStructureInterfaceCheck().check_id == "pou_structure_interface"

    def test_interface_skips_when_subtype_none(self, tmp_path):
        iface_file = tmp_path / "I_Foo2.TcPOU"
        iface_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="I_Foo2" Id="{12345678-0000-0000-0000-000000000005}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[INTERFACE I_Foo2\nEND_INTERFACE\n]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        assert PouStructureInterfaceCheck().should_skip(TwinCATFile(iface_file))

    def test_interface_detects_missing_tcio(self, tmp_path):
        fb_file = tmp_path / "FB_Impl.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Impl" Id="{12345678-0000-0000-0000-000000000006}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Impl IMPLEMENTS I_Missing\n"
            "VAR\nEND_VAR\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        issues = PouStructureInterfaceCheck().run(TwinCATFile(fb_file))
        assert any("I_Missing" in issue.message for issue in issues)

    def test_interface_allows_inherited_implementation_via_base(self, tmp_path):
        (tmp_path / "I_Diag.TcIO").write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <Itf Name="I_Diag" Id="{12345678-0000-0000-0000-000000000101}">\n'
            "    <Declaration><![CDATA[INTERFACE I_Diag\n]]></Declaration>\n"
            '    <Method Name="M_Read" Id="{12345678-0000-0000-0000-000000000102}">\n'
            "      <Declaration><![CDATA[METHOD M_Read : INT\n]]></Declaration>\n"
            "    </Method>\n"
            "  </Itf>\n"
            "</TcPlcObject>",
            encoding="utf-8",
        )
        (tmp_path / "FB_Base.TcPOU").write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Base" Id="{12345678-0000-0000-0000-000000000103}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Base IMPLEMENTS I_Diag\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Read" Id="{12345678-0000-0000-0000-000000000104}">\n'
            "      <Declaration><![CDATA[METHOD M_Read : INT\n]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[M_Read := 1;]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>",
            encoding="utf-8",
        )
        (tmp_path / "FB_Derived.TcPOU").write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Derived" Id="{12345678-0000-0000-0000-000000000105}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base IMPLEMENTS I_Diag\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>",
            encoding="utf-8",
        )
        issues = PouStructureInterfaceCheck().run(TwinCATFile(tmp_path / "FB_Derived.TcPOU"))
        assert issues == []

    def test_interface_detects_inherited_signature_mismatch(self, tmp_path):
        (tmp_path / "I_Diag2.TcIO").write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <Itf Name="I_Diag2" Id="{12345678-0000-0000-0000-000000000111}">\n'
            "    <Declaration><![CDATA[INTERFACE I_Diag2\n]]></Declaration>\n"
            '    <Method Name="M_Read" Id="{12345678-0000-0000-0000-000000000112}">\n'
            "      <Declaration><![CDATA[METHOD M_Read : INT\n]]></Declaration>\n"
            "    </Method>\n"
            "  </Itf>\n"
            "</TcPlcObject>",
            encoding="utf-8",
        )
        (tmp_path / "FB_Base2.TcPOU").write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Base2" Id="{12345678-0000-0000-0000-000000000113}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Base2 IMPLEMENTS I_Diag2\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Read" Id="{12345678-0000-0000-0000-000000000114}">\n'
            "      <Declaration><![CDATA[METHOD M_Read : INT\n]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[M_Read := 1;]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>",
            encoding="utf-8",
        )
        (tmp_path / "FB_Derived2.TcPOU").write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Derived2" Id="{12345678-0000-0000-0000-000000000115}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived2 EXTENDS FB_Base2 IMPLEMENTS I_Diag2\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Read" Id="{12345678-0000-0000-0000-000000000116}">\n'
            "      <Declaration><![CDATA[{attribute 'override'}\nMETHOD M_Read : DINT\n]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[M_Read := 2;]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>",
            encoding="utf-8",
        )
        issues = PouStructureInterfaceCheck().run(TwinCATFile(tmp_path / "FB_Derived2.TcPOU"))
        assert len(issues) == 1
        assert "signature mismatch M_Read" in issues[0].message

    # ------------------------------------------------------------------ #
    # Phase 5 parser robustness (RC-5 + RC-6)
    # ------------------------------------------------------------------ #

    def test_interface_signature_accepts_abstract_modifier(self, tmp_path):
        (tmp_path / "I_Mod.TcIO").write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <Itf Name="I_Mod" Id="{12345678-0000-0000-0000-000000000201}">\n'
            "    <Declaration><![CDATA[INTERFACE I_Mod\n]]></Declaration>\n"
            '    <Method Name="M_Run" Id="{12345678-0000-0000-0000-000000000202}">\n'
            "      <Declaration><![CDATA[METHOD M_Run : BOOL\n]]></Declaration>\n"
            "    </Method>\n"
            "  </Itf>\n"
            "</TcPlcObject>",
            encoding="utf-8",
        )
        (tmp_path / "FB_ModA.TcPOU").write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_ModA" Id="{12345678-0000-0000-0000-000000000203}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_ModA IMPLEMENTS I_Mod\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Run" Id="{12345678-0000-0000-0000-000000000204}">\n'
            "      <Declaration><![CDATA[METHOD ABSTRACT M_Run : BOOL\n]]></Declaration>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>",
            encoding="utf-8",
        )
        issues = PouStructureInterfaceCheck().run(TwinCATFile(tmp_path / "FB_ModA.TcPOU"))
        assert not any("signature mismatch" in issue.message for issue in issues)

    def test_interface_signature_accepts_visibility_override_modifiers(self, tmp_path):
        (tmp_path / "I_Mod2.TcIO").write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <Itf Name="I_Mod2" Id="{12345678-0000-0000-0000-000000000211}">\n'
            "    <Declaration><![CDATA[INTERFACE I_Mod2\n]]></Declaration>\n"
            '    <Method Name="M_Write" Id="{12345678-0000-0000-0000-000000000212}">\n'
            "      <Declaration><![CDATA[METHOD M_Write : BOOL\n"
            "VAR_INPUT\n"
            "  nValue : INT;\n"
            "END_VAR\n"
            "]]></Declaration>\n"
            "    </Method>\n"
            "  </Itf>\n"
            "</TcPlcObject>",
            encoding="utf-8",
        )
        (tmp_path / "FB_ModB.TcPOU").write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_ModB" Id="{12345678-0000-0000-0000-000000000213}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_ModB IMPLEMENTS I_Mod2\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Write" Id="{12345678-0000-0000-0000-000000000214}">\n'
            "      <Declaration><![CDATA[METHOD PROTECTED OVERRIDE M_Write : BOOL\n"
            "VAR_INPUT\n"
            "  nValue : INT;\n"
            "END_VAR\n"
            "]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[M_Write := TRUE;]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>",
            encoding="utf-8",
        )
        issues = PouStructureInterfaceCheck().run(TwinCATFile(tmp_path / "FB_ModB.TcPOU"))
        assert not any("signature mismatch" in issue.message for issue in issues)

    def test_interface_signature_accepts_pragma_and_modifier(self, tmp_path):
        (tmp_path / "I_Mod3.TcIO").write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <Itf Name="I_Mod3" Id="{12345678-0000-0000-0000-000000000221}">\n'
            "    <Declaration><![CDATA[INTERFACE I_Mod3\n]]></Declaration>\n"
            '    <Method Name="M_Reset" Id="{12345678-0000-0000-0000-000000000222}">\n'
            "      <Declaration><![CDATA[METHOD M_Reset : BOOL\n"
            "VAR_INPUT\n"
            "  bOperatorAuth : BOOL;\n"
            "END_VAR\n"
            "]]></Declaration>\n"
            "    </Method>\n"
            "  </Itf>\n"
            "</TcPlcObject>",
            encoding="utf-8",
        )
        (tmp_path / "FB_ModC.TcPOU").write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_ModC" Id="{12345678-0000-0000-0000-000000000223}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_ModC IMPLEMENTS I_Mod3\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Reset" Id="{12345678-0000-0000-0000-000000000224}">\n'
            "      <Declaration><![CDATA[{attribute 'override'}\n"
            "METHOD OVERRIDE M_Reset : BOOL\n"
            "VAR_INPUT\n"
            "  bOperatorAuth : BOOL;\n"
            "END_VAR\n"
            "]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[M_Reset := bOperatorAuth;]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>",
            encoding="utf-8",
        )
        issues = PouStructureInterfaceCheck().run(TwinCATFile(tmp_path / "FB_ModC.TcPOU"))
        assert not any("signature mismatch" in issue.message for issue in issues)

    def test_method_assignment_detection_does_not_leak_across_no_impl_method(self, tmp_path):
        fb_file = tmp_path / "FB_NoLeakAssign.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_NoLeakAssign" Id="{12345678-0000-0000-0000-000000000231}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_NoLeakAssign\nEND_FUNCTION_BLOCK\n]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Execute" Id="{12345678-0000-0000-0000-000000000232}">\n'
            "      <Declaration><![CDATA[METHOD ABSTRACT M_Execute : BOOL\n]]></Declaration>\n"
            "    </Method>\n"
            '    <Method Name="M_Run" Id="{12345678-0000-0000-0000-000000000233}">\n'
            "      <Declaration><![CDATA[METHOD M_Run : BOOL\n]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[\n"
            "xMissing := 1;\n"
            "M_Run := TRUE;\n"
            "]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>",
            encoding="utf-8",
        )
        issues = PouStructureMethodsCheck().run(TwinCATFile(fb_file))
        messages = [issue.message for issue in issues]
        assert any(
            "Undeclared assignment target(s)" in msg and "M_Run.xMissing" in msg for msg in messages
        )
        assert not any("M_Execute." in msg for msg in messages)

    def test_var_input_mutation_detection_does_not_leak_across_no_impl_method(self, tmp_path):
        fb_file = tmp_path / "FB_NoLeakVarInput.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_NoLeakVarInput" Id="{12345678-0000-0000-0000-000000000241}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_NoLeakVarInput\nEND_FUNCTION_BLOCK\n]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Execute" Id="{12345678-0000-0000-0000-000000000242}">\n'
            "      <Declaration><![CDATA[METHOD ABSTRACT M_Execute : BOOL\n"
            "VAR_INPUT\n"
            "  bFlag : BOOL;\n"
            "END_VAR\n"
            "]]></Declaration>\n"
            "    </Method>\n"
            '    <Method Name="M_Run" Id="{12345678-0000-0000-0000-000000000243}">\n'
            "      <Declaration><![CDATA[METHOD M_Run : BOOL\n"
            "VAR_INPUT\n"
            "  bFlag : BOOL;\n"
            "END_VAR\n"
            "]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[\n"
            "bFlag := FALSE;\n"
            "M_Run := TRUE;\n"
            "]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>",
            encoding="utf-8",
        )
        issues = PouStructureMethodsCheck().run(TwinCATFile(fb_file))
        messages = [issue.message for issue in issues]
        assert any(
            "Assignments to VAR_INPUT parameter(s) detected" in msg and "M_Run.bFlag" in msg
            for msg in messages
        )
        assert not any("M_Execute.bFlag" in msg for msg in messages)

    def test_legacy_m_execute_m_getstatus_false_positive_is_not_emitted(self, tmp_path):
        fb_file = tmp_path / "FB_NoLeakLegacy.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_NoLeakLegacy" Id="{12345678-0000-0000-0000-000000000251}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_NoLeakLegacy\nEND_FUNCTION_BLOCK\n]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_Execute" Id="{12345678-0000-0000-0000-000000000252}">\n'
            "      <Declaration><![CDATA[METHOD ABSTRACT M_Execute : BOOL\n]]></Declaration>\n"
            "    </Method>\n"
            '    <Method Name="M_GetStatus" Id="{12345678-0000-0000-0000-000000000253}">\n'
            "      <Declaration><![CDATA[METHOD M_GetStatus : BOOL\n]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[\n"
            "M_GetStatus := TRUE;\n"
            "]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>",
            encoding="utf-8",
        )
        issues = PouStructureMethodsCheck().run(TwinCATFile(fb_file))
        assert not any("M_Execute.M_GetStatus" in issue.message for issue in issues)

    # ------------------------------------------------------------------ #
    # PouStructureSyntaxCheck
    # ------------------------------------------------------------------ #

    def test_syntax_check_id(self):
        assert PouStructureSyntaxCheck().check_id == "pou_structure_syntax"

    def test_syntax_skips_when_subtype_none(self, tmp_path):
        iface_file = tmp_path / "I_Foo3.TcPOU"
        iface_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="I_Foo3" Id="{12345678-0000-0000-0000-000000000007}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[INTERFACE I_Foo3\nEND_INTERFACE\n]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        assert PouStructureSyntaxCheck().should_skip(TwinCATFile(iface_file))

    def test_syntax_detects_missing_semicolon(self, tmp_path):
        fb_file = tmp_path / "FB_Syntax.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Syntax" Id="{12345678-0000-0000-0000-000000000008}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Syntax\nVAR\nEND_VAR\n]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[\n"
            "IF xFlag THEN\n"
            "  nValue := 1\n"
            "END_IF;\n"
            "]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        issues = PouStructureSyntaxCheck().run(TwinCATFile(fb_file))
        assert any("ST syntax guard" in issue.message for issue in issues)

    # ------------------------------------------------------------------ #
    # PouStructureSubtypeCheck
    # ------------------------------------------------------------------ #

    def test_subtype_check_id(self):
        assert PouStructureSubtypeCheck().check_id == "pou_structure_subtype"

    def test_subtype_skips_for_function_block(self, tmp_path):
        fb_file = tmp_path / "FB_Skip.TcPOU"
        fb_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Skip" Id="{12345678-0000-0000-0000-000000000009}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Skip\nVAR\nEND_VAR\n]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        assert PouStructureSubtypeCheck().should_skip(TwinCATFile(fb_file))

    def test_subtype_detects_function_missing_return(self, tmp_path):
        fn_file = tmp_path / "FUNC_NoReturn.TcPOU"
        fn_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FUNC_NoReturn" Id="{12345678-0000-0000-0000-00000000000a}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION FUNC_NoReturn\nVAR_INPUT\n  x : INT;\nEND_VAR\n]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        issues = PouStructureSubtypeCheck().run(TwinCATFile(fn_file))
        assert any("return type" in issue.message.lower() for issue in issues)

    def test_subtype_detects_function_with_method(self, tmp_path):
        fn_file = tmp_path / "FUNC_WithMethod.TcPOU"
        fn_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FUNC_WithMethod" Id="{12345678-0000-0000-0000-00000000000b}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION FUNC_WithMethod : BOOL\nVAR_INPUT\n  x : INT;\nEND_VAR\n]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[FUNC_WithMethod := TRUE;\n]]></ST></Implementation>\n"
            '    <Method Name="M_Bad">\n'
            "      <Declaration><![CDATA[METHOD M_Bad : BOOL\n]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[M_Bad := FALSE;\n]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )
        issues = PouStructureSubtypeCheck().run(TwinCATFile(fn_file))
        assert any("FUNCTIONs cannot have Methods" in issue.message for issue in issues)
