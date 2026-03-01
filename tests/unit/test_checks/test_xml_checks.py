"""Tests for twincat_validator.validators.xml_checks module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from twincat_validator.validators.base import CheckRegistry
from twincat_validator.validators.xml_checks import XmlStructureCheck
from twincat_validator.file_handler import TwinCATFile


class TestXmlStructureCheck:
    """Tests for XmlStructureCheck validator."""

    @classmethod
    def setup_class(cls):
        """Ensure XmlStructureCheck is registered before tests run.

        This is needed because test_base.py clears the registry for isolation,
        so we need to ensure our check is registered for tests that use the registry.
        """
        if "xml_structure" not in CheckRegistry.get_all_checks():
            CheckRegistry.register(XmlStructureCheck)

    def test_valid_xml_produces_no_issues(self, valid_tcpou):
        """Test well-formed XML file produces no issues."""
        file = TwinCATFile(valid_tcpou)
        check = XmlStructureCheck()

        issues = check.run(file)

        assert isinstance(issues, list)
        assert len(issues) == 0

    def test_malformed_xml_detected(self, tmp_path):
        """Test malformed XML is detected with error issue."""
        malformed_file = tmp_path / "malformed.TcPOU"
        malformed_file.write_text('<?xml version="1.0"?>\n<TcPlcObject><Unclosed>')

        file = TwinCATFile(malformed_file)
        check = XmlStructureCheck()

        issues = check.run(file)

        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "error"
        assert issue.category == "XML"
        assert "parse error" in issue.message.lower()
        assert issue.fix_available is False

    def test_missing_closing_tag_detected(self, tmp_path):
        """Test missing closing tag is detected."""
        bad_xml = tmp_path / "missing_close.TcPOU"
        bad_xml.write_text(
            '<?xml version="1.0"?>\n<TcPlcObject>\n  <POU Name="Test">\n</TcPlcObject>'
        )

        file = TwinCATFile(bad_xml)
        check = XmlStructureCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].category == "XML"

    def test_invalid_xml_characters_detected(self, tmp_path):
        """Test invalid XML characters are detected."""
        bad_xml = tmp_path / "invalid_chars.TcPOU"
        # & without proper escaping
        bad_xml.write_text(
            '<?xml version="1.0"?>\n<TcPlcObject attr="value & other"></TcPlcObject>'
        )

        file = TwinCATFile(bad_xml)
        check = XmlStructureCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "error"

    def test_check_registered_in_registry(self):
        """Test XmlStructureCheck is auto-registered via decorator."""
        check_class = CheckRegistry.get_check("xml_structure")
        assert check_class == XmlStructureCheck
        assert check_class.check_id == "xml_structure"

    def test_check_can_be_instantiated_via_registry(self, valid_tcpou):
        """Test check can be retrieved and used via registry (integration test)."""
        # Get check class from registry
        check_class = CheckRegistry.get_check("xml_structure")

        # Instantiate and run
        check = check_class()
        file = TwinCATFile(valid_tcpou)
        issues = check.run(file)

        assert isinstance(issues, list)
        assert len(issues) == 0

    def test_check_id_matches_config(self):
        """Test check_id matches expected config ID."""
        check = XmlStructureCheck()
        assert check.check_id == "xml_structure"

    def test_should_skip_defaults_to_false(self, valid_tcpou):
        """Test should_skip() returns False (check applies to all files)."""
        file = TwinCATFile(valid_tcpou)
        check = XmlStructureCheck()

        assert check.should_skip(file) is False

    def test_empty_xml_detected(self, tmp_path):
        """Test completely empty XML is detected."""
        empty_file = tmp_path / "empty.TcPOU"
        empty_file.write_text("")

        file = TwinCATFile(empty_file)
        check = XmlStructureCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].category == "XML"

    def test_non_xml_content_detected(self, tmp_path):
        """Test non-XML content is detected."""
        non_xml = tmp_path / "not_xml.TcPOU"
        non_xml.write_text("This is just plain text, not XML")

        file = TwinCATFile(non_xml)
        check = XmlStructureCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "parse error" in issues[0].message.lower()

    def test_tcio_with_pou_top_level_detected(self, tmp_path):
        """Test .TcIO files must use <Itf> as top-level TwinCAT object."""
        bad_itf = tmp_path / "I_Record.TcIO"
        bad_itf.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Name="I_Record">\n'
            "    <Declaration><![CDATA[INTERFACE I_Record]]></Declaration>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(bad_itf)
        check = XmlStructureCheck()
        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "expects <Itf>" in issues[0].message

    def test_tcpou_with_itf_top_level_detected(self, tmp_path):
        """Test .TcPOU files must use <POU> as top-level TwinCAT object."""
        bad_pou = tmp_path / "FB_Test.TcPOU"
        bad_pou.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <Itf Name="FB_Test">\n'
            "    <Declaration><![CDATA[INTERFACE FB_Test]]></Declaration>\n"
            "  </Itf>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(bad_pou)
        check = XmlStructureCheck()
        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "expects <POU>" in issues[0].message

    def test_tcio_mixed_method_declaration_styles_detected(self, tmp_path):
        """Test .TcIO rejects inline METHOD text plus <Method> nodes together."""
        mixed_itf = tmp_path / "I_Record.TcIO"
        mixed_itf.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <Itf Name="I_Record" Id="{12345678-1234-1234-1234-123456789abc}">\n'
            "    <Declaration><![CDATA[INTERFACE I_Record\n"
            "METHOD M_AddAlarm : BOOL\n"
            "END_INTERFACE]]></Declaration>\n"
            '    <Method Name="M_AddAlarm">\n'
            "      <Declaration><![CDATA[METHOD M_AddAlarm : BOOL]]></Declaration>\n"
            "    </Method>\n"
            "  </Itf>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(mixed_itf)
        check = XmlStructureCheck()
        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "mixed method declaration styles" in issues[0].message
