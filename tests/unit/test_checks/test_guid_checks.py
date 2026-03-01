"""Tests for twincat_validator.validators.guid_checks module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from twincat_validator.validators.base import CheckRegistry
from twincat_validator.validators.guid_checks import GuidFormatCheck, GuidUniquenessCheck
from twincat_validator.file_handler import TwinCATFile


def _ensure_guid_checks_registered() -> None:
    for check_class in (GuidFormatCheck, GuidUniquenessCheck):
        if check_class.check_id not in CheckRegistry.get_all_checks():
            CheckRegistry.register(check_class)


class TestGuidFormatCheck:
    """Tests for GuidFormatCheck validator."""

    @classmethod
    def setup_class(cls):
        """Ensure checks are registered without mutating global registry state."""
        _ensure_guid_checks_registered()

    def test_valid_guids_produce_no_issues(self, valid_tcpou):
        """Test file with all lowercase GUIDs produces no issues."""
        file = TwinCATFile(valid_tcpou)
        check = GuidFormatCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_placeholder_guid_detected(self, tmp_path):
        """Test placeholder GUID is detected."""
        placeholder_file = tmp_path / "placeholder.TcPOU"
        placeholder_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Id="GENERATE-NEW-GUID">\n'
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(placeholder_file)
        check = GuidFormatCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].category == "GUID"
        assert "placeholder" in issues[0].message.lower()
        assert "1" in issues[0].message  # Count should be 1
        assert issues[0].fix_available is False

    def test_multiple_placeholder_guids(self, tmp_path):
        """Test multiple placeholder GUIDs are counted correctly."""
        placeholder_file = tmp_path / "multi_placeholder.TcPOU"
        placeholder_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Id="GENERATE-NEW-GUID">\n'
            '    <Property Id="GENERATE-NEW-GUID">\n'
            "    </Property>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(placeholder_file)
        check = GuidFormatCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert "2" in issues[0].message  # Count should be 2

    def test_repeated_char_guid_placeholder_detected(self, tmp_path):
        """Test repeated-char GUID placeholders like aaaa... are detected."""
        repeated_file = tmp_path / "repeated_guid.TcPOU"
        repeated_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Id="{aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa}">\n'
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(repeated_file)
        check = GuidFormatCheck()
        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "placeholder GUID" in issues[0].message

    def test_uppercase_guid_detected(self, tmp_path):
        """Test GUID with uppercase letters is detected."""
        uppercase_file = tmp_path / "uppercase.TcPOU"
        uppercase_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Id="{12345678-ABCD-1234-5678-123456789ABC}">\n'
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(uppercase_file)
        check = GuidFormatCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].category == "GUID"
        assert "uppercase" in issues[0].message.lower()
        assert issues[0].fix_available is True

    def test_malformed_guid_token_detected(self, tmp_path):
        """Test malformed GUID token in Id attribute is detected."""
        malformed_file = tmp_path / "malformed_guid.TcDUT"
        malformed_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <DUT Name="ST_X" Id="{e6f7a8b9-ca db-4cee-e05b-6c7d8e9fa6b7}">\n'
            "  </DUT>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(malformed_file)
        check = GuidFormatCheck()
        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "malformed GUID token" in issues[0].message
        assert issues[0].fix_available is False

    def test_mixed_case_guids(self, tmp_path):
        """Test file with mixed lowercase and uppercase GUIDs."""
        mixed_file = tmp_path / "mixed.TcPOU"
        mixed_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Id="{12345678-abcd-1234-5678-123456789abc}">\n'
            '    <Property Id="{ABCDEF12-3456-7890-ABCD-EF1234567890}">\n'
            "    </Property>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(mixed_file)
        check = GuidFormatCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert "1" in issues[0].message  # 1 uppercase GUID

    def test_check_id_matches_config(self):
        """Test check_id matches expected config ID."""
        check = GuidFormatCheck()
        assert check.check_id == "guid_format"


class TestGuidUniquenessCheck:
    """Tests for GuidUniquenessCheck validator."""

    @classmethod
    def setup_class(cls):
        """Ensure checks are registered without mutating global registry state."""
        _ensure_guid_checks_registered()

    def test_unique_guids_produce_no_issues(self, valid_tcpou):
        """Test file with all unique GUIDs produces no issues."""
        file = TwinCATFile(valid_tcpou)
        check = GuidUniquenessCheck()

        issues = check.run(file)

        assert len(issues) == 0

    def test_duplicate_guid_detected(self, tmp_path):
        """Test duplicate GUID is detected."""
        duplicate_file = tmp_path / "duplicate.TcPOU"
        duplicate_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Id="{12345678-abcd-1234-5678-123456789abc}">\n'
            '    <Property Id="{12345678-abcd-1234-5678-123456789abc}">\n'
            "    </Property>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(duplicate_file)
        check = GuidUniquenessCheck()

        issues = check.run(file)

        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].category == "GUID"
        assert "duplicate" in issues[0].message.lower()
        assert "12345678-abcd-1234-5678-123456789abc" in issues[0].message
        assert issues[0].fix_available is False

    def test_multiple_duplicates(self, tmp_path):
        """Test multiple different duplicate GUIDs are all reported."""
        multi_dup_file = tmp_path / "multi_dup.TcPOU"
        multi_dup_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Id="{11111111-1111-1111-1111-111111111111}">\n'
            '    <Property Id="{11111111-1111-1111-1111-111111111111}">\n'
            "    </Property>\n"
            '    <Property Id="{22222222-2222-2222-2222-222222222222}">\n'
            "    </Property>\n"
            '    <Property Id="{22222222-2222-2222-2222-222222222222}">\n'
            "    </Property>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(multi_dup_file)
        check = GuidUniquenessCheck()

        issues = check.run(file)

        assert len(issues) == 2  # Two different duplicate GUIDs
        assert any("11111111-1111-1111-1111-111111111111" in issue.message for issue in issues)
        assert any("22222222-2222-2222-2222-222222222222" in issue.message for issue in issues)

    def test_uppercase_guids_not_checked(self, tmp_path):
        """Test uppercase GUIDs are not checked for uniqueness (format check handles them)."""
        uppercase_dup = tmp_path / "uppercase_dup.TcPOU"
        uppercase_dup.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <POU Id="{AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA}">\n'
            '    <Property Id="{AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA}">\n'
            "    </Property>\n"
            "  </POU>\n"
            "</TcPlcObject>"
        )

        file = TwinCATFile(uppercase_dup)
        check = GuidUniquenessCheck()

        issues = check.run(file)

        # Uppercase GUIDs are not matched by the lowercase-only pattern
        assert len(issues) == 0

    def test_check_id_matches_config(self):
        """Test check_id matches expected config ID."""
        check = GuidUniquenessCheck()
        assert check.check_id == "guid_uniqueness"
