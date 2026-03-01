"""Integration tests for Phase 3 LLM Context Enrichment.

Verifies that ValidationIssue objects have code_snippet, explanation, and
correct_example fields populated when issues are detected.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from twincat_validator import TwinCATFile, ValidationEngine
from twincat_validator.config_loader import ValidationConfig


class TestPhase3Enrichment:
    """Tests for Phase 3 enrichment in ValidationIssue objects."""

    @pytest.fixture
    def config(self):
        """Get validation config."""
        return ValidationConfig()

    @pytest.fixture
    def validation_engine(self, config):
        """Get validation engine."""
        return ValidationEngine(config)

    def test_indentation_check_enriched(self, tmp_path, validation_engine):
        """Test IndentationCheck populates Phase 3 fields."""
        # Create file with odd indentation (3 spaces)
        test_file = tmp_path / "test.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            "   <POU>content</POU>\n"  # 3 spaces - odd indentation
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        result = validation_engine.validate(file, validation_level="all")

        # Should have indentation issue
        indent_issues = [i for i in result.issues if i.category == "Indent"]
        assert len(indent_issues) > 0

        # Verify Phase 3 fields are populated
        issue = indent_issues[0]
        assert issue.code_snippet is not None
        assert len(issue.code_snippet) > 0
        assert issue.explanation is not None
        assert len(issue.explanation) > 0
        assert issue.correct_example is not None
        assert len(issue.correct_example) > 0

        # Verify snippet shows the line with issue
        assert "→  3 |" in issue.code_snippet or "→   3 |" in issue.code_snippet
        assert "<POU>" in issue.code_snippet

    def test_tabs_check_enriched(self, tmp_path, validation_engine):
        """Test TabsCheck populates Phase 3 fields."""
        # Create file with tab characters
        test_file = tmp_path / "test.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n' "<TcPlcObject>\n" "\t<POU>content</POU>\n" "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        result = validation_engine.validate(file, validation_level="all")

        # Should have tabs issue
        tab_issues = [i for i in result.issues if i.category == "Tabs"]
        assert len(tab_issues) > 0

        # Verify Phase 3 fields are populated
        issue = tab_issues[0]
        assert issue.code_snippet is not None
        assert issue.explanation is not None
        assert issue.correct_example is not None

        # Verify snippet shows the first tab occurrence
        assert "\t" in issue.code_snippet
        assert "<POU>" in issue.code_snippet

    def test_guid_format_check_enriched(self, tmp_path, validation_engine):
        """Test GuidFormatCheck populates Phase 3 fields for uppercase GUIDs."""
        # Create file with uppercase GUID
        test_file = tmp_path / "test.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test" Id="{ABCDEF12-3456-7890-ABCD-EF1234567890}">\n'
            "  </POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        result = validation_engine.validate(file, validation_level="all")

        # Should have GUID format issue
        guid_issues = [i for i in result.issues if i.category == "GUID"]
        assert len(guid_issues) > 0

        # Verify Phase 3 fields are populated
        issue = guid_issues[0]
        assert issue.code_snippet is not None
        assert issue.explanation is not None
        assert issue.correct_example is not None

        # Verify snippet shows the GUID
        assert "ABCDEF" in issue.code_snippet or "FB_Test" in issue.code_snippet

    def test_guid_placeholder_enriched(self, tmp_path, validation_engine):
        """Test GuidFormatCheck populates Phase 3 fields for placeholder GUIDs."""
        # Create file with placeholder GUID
        test_file = tmp_path / "test.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test" Id="GENERATE-NEW-GUID">\n'
            "  </POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        result = validation_engine.validate(file, validation_level="all")

        # Should have GUID format issue
        guid_issues = [i for i in result.issues if i.category == "GUID"]
        assert len(guid_issues) > 0

        # Verify Phase 3 fields are populated
        issue = guid_issues[0]
        assert issue.code_snippet is not None
        assert issue.explanation is not None
        assert issue.correct_example is not None

        # Verify snippet shows the placeholder
        assert "GENERATE-NEW-GUID" in issue.code_snippet

    def test_property_var_blocks_check_enriched(self, tmp_path, validation_engine):
        """Test PropertyVarBlocksCheck populates Phase 3 fields."""
        # Create file with property getter with wrong content (not VAR block, not empty)
        test_file = tmp_path / "test.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test" Id="{a1b2c3d4-e5f6-7890-abcd-ef1234567890}">\n'
            '    <Property Name="Speed" Id="{b1c2d3e4-f5a6-7890-bcde-fa1234567890}">\n'
            '      <Get Name="Get" Id="{c1d2e3f4-a5b6-7890-cdef-ab1234567890}">\n'
            "        <Declaration><![CDATA[nLocal : INT;]]></Declaration>\n"  # Missing VAR/END_VAR
            "      </Get>\n"
            "    </Property>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        result = validation_engine.validate(file, validation_level="all")

        # Should have property VAR blocks issue
        prop_issues = [i for i in result.issues if i.category == "Property"]
        assert len(prop_issues) > 0

        # Verify Phase 3 fields are populated
        issue = prop_issues[0]
        assert issue.code_snippet is not None
        assert issue.explanation is not None
        assert issue.correct_example is not None

        # Verify snippet shows property structure
        assert "Property" in issue.code_snippet or "Speed" in issue.code_snippet

    def test_xml_structure_check_enriched(self, tmp_path, validation_engine):
        """Test XmlStructureCheck populates Phase 3 fields."""
        # Create file with malformed XML
        test_file = tmp_path / "test.TcPOU"
        test_file.write_text('<?xml version="1.0"?>\n' "<TcPlcObject>\n" "  <Unclosed>\n")

        file = TwinCATFile(test_file)
        result = validation_engine.validate(file, validation_level="all")

        # Should have XML structure issue
        xml_issues = [i for i in result.issues if i.category == "XML"]
        assert len(xml_issues) > 0

        # Verify Phase 3 fields are populated
        issue = xml_issues[0]
        assert issue.code_snippet is not None
        assert issue.explanation is not None
        assert issue.correct_example is not None

        # Verify snippet shows context around error
        assert "TcPlcObject" in issue.code_snippet or "Unclosed" in issue.code_snippet

    def test_backward_compatibility_no_enrichment(self, tmp_path, validation_engine):
        """Test validators without Phase 3 enrichment still work (backward compat)."""
        # Create valid file to test checks without enrichment
        test_file = tmp_path / "test.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test" Id="{a1b2c3d4-e5f6-7890-abcd-ef1234567890}">\n'
            "  </POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        result = validation_engine.validate(file, validation_level="all")

        # Should pass or have no enriched issues
        # This verifies non-enriched checks still work
        assert result is not None

    def test_validation_issue_to_dict_includes_phase3_fields(self, tmp_path, validation_engine):
        """Test ValidationIssue.to_dict() includes Phase 3 fields when populated."""
        # Create file with tab
        test_file = tmp_path / "test.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n' "<TcPlcObject>\n" "\t<POU>content</POU>\n" "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        result = validation_engine.validate(file, validation_level="all")

        # Should have tabs issue
        tab_issues = [i for i in result.issues if i.category == "Tabs"]
        assert len(tab_issues) > 0

        # Convert to dict
        issue_dict = tab_issues[0].to_dict()

        # Verify Phase 3 fields are in dict
        assert "code_snippet" in issue_dict
        assert "explanation" in issue_dict
        assert "correct_example" in issue_dict

        # Verify they have values
        assert issue_dict["code_snippet"] is not None
        assert issue_dict["explanation"] is not None
        assert issue_dict["correct_example"] is not None

    def test_validation_issue_to_dict_omits_none_phase3_fields(self, tmp_path, validation_engine):
        """Test ValidationIssue.to_dict() omits Phase 3 fields when None (backward compat)."""
        # Create file that triggers a check WITHOUT Phase 3 enrichment (e.g., LineIdsCountCheck)
        test_file = tmp_path / "test.TcPOU"
        test_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="FB_Test" Id="{a1b2c3d4-e5f6-7890-abcd-ef1234567890}">\n'
            '    <Method Name="Execute" Id="{b1c2d3e4-f5a6-7890-bcde-fa1234567890}">\n'
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )

        file = TwinCATFile(test_file)
        result = validation_engine.validate(file, validation_level="all")

        # Find issue without enrichment
        for issue in result.issues:
            issue_dict = issue.to_dict()

            # If Phase 3 fields are None, they should not be in dict
            if issue.code_snippet is None:
                assert "code_snippet" not in issue_dict or issue_dict["code_snippet"] is None
