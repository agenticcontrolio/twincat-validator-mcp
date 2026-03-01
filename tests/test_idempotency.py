"""Tests for Phase 4: Idempotency guarantee.

Phase 4.3: Running autofix twice on same input produces identical output.
"""

import pytest
from pathlib import Path

from twincat_validator import TwinCATFile, FixEngine, ValidationConfig


class TestIdempotency:
    """Test that fix application is idempotent (running twice produces no changes)."""

    @pytest.fixture
    def fix_engine(self):
        """Create a FixEngine instance."""
        config = ValidationConfig()
        return FixEngine(config)

    def _apply_fixes_and_verify_idempotency(
        self, file_path: Path, fix_engine: FixEngine, tmp_path: Path
    ) -> None:
        """Helper: Apply fixes twice and verify second pass produces no changes.

        Args:
            file_path: Path to fixture file
            fix_engine: FixEngine instance
            tmp_path: Temporary directory for test files
        """
        # Create a copy in temp directory to work with
        temp_file = tmp_path / file_path.name
        temp_file.write_text(file_path.read_text(encoding="utf-8"), encoding="utf-8")

        # First pass: Apply all fixes
        file1 = TwinCATFile.from_path(temp_file)

        fix_engine.apply_fixes(file1)
        file1.save()  # Save to temp_file (file1.filepath)
        content_after_first = file1.content

        # Second pass: Reload and apply fixes again
        file2 = TwinCATFile.from_path(temp_file)
        content_before_second = file2.content

        result2 = fix_engine.apply_fixes(file2)
        content_after_second = file2.content

        # IDEMPOTENCY ASSERTION: Second pass should produce no changes
        assert content_before_second == content_after_second, (
            f"Second fix pass changed content! This violates idempotency. "
            f"Applied fixes in second pass: {result2.applied_fixes}"
        )

        # BYTE-IDENTICAL ASSERTION: Output should be exactly the same
        assert content_after_first == content_after_second, (
            "Second pass produced different output bytes! " "Fix application is not deterministic."
        )

    def test_tabs_and_indentation_fixture_idempotent(
        self, tabs_and_bad_indent_file, fix_engine, tmp_path
    ):
        """Test idempotency on file with tabs and bad indentation."""
        self._apply_fixes_and_verify_idempotency(tabs_and_bad_indent_file, fix_engine, tmp_path)

    def test_mixed_case_guids_fixture_idempotent(self, mixed_case_guids_file, fix_engine, tmp_path):
        """Test idempotency on file with mixed-case GUIDs."""
        self._apply_fixes_and_verify_idempotency(mixed_case_guids_file, fix_engine, tmp_path)

    def test_valid_fb_fixture_idempotent(self, valid_tcpou, fix_engine, tmp_path):
        """Test idempotency on already-valid function block."""
        self._apply_fixes_and_verify_idempotency(valid_tcpou, fix_engine, tmp_path)

    def test_valid_function_fixture_idempotent(self, valid_function, fix_engine, tmp_path):
        """Test idempotency on valid FUNCTION."""
        self._apply_fixes_and_verify_idempotency(valid_function, fix_engine, tmp_path)

    def test_valid_program_fixture_idempotent(self, valid_program, fix_engine, tmp_path):
        """Test idempotency on valid PROGRAM."""
        self._apply_fixes_and_verify_idempotency(valid_program, fix_engine, tmp_path)

    def test_valid_dut_fixture_idempotent(self, valid_tcdut, fix_engine, tmp_path):
        """Test idempotency on valid DUT (struct)."""
        self._apply_fixes_and_verify_idempotency(valid_tcdut, fix_engine, tmp_path)

    def test_valid_gvl_fixture_idempotent(self, valid_tcgvl, fix_engine, tmp_path):
        """Test idempotency on valid GVL."""
        self._apply_fixes_and_verify_idempotency(valid_tcgvl, fix_engine, tmp_path)

    def test_valid_interface_fixture_idempotent(self, valid_tcio, fix_engine, tmp_path):
        """Test idempotency on valid interface."""
        self._apply_fixes_and_verify_idempotency(valid_tcio, fix_engine, tmp_path)

    def test_function_with_methods_idempotent(self, function_with_methods, fix_engine, tmp_path):
        """Test idempotency on FUNCTION with invalid methods."""
        self._apply_fixes_and_verify_idempotency(function_with_methods, fix_engine, tmp_path)

    def test_function_no_return_type_idempotent(
        self, function_no_return_type, fix_engine, tmp_path
    ):
        """Test idempotency on FUNCTION missing return type."""
        self._apply_fixes_and_verify_idempotency(function_no_return_type, fix_engine, tmp_path)


class TestIdempotencyAppliedFixes:
    """Test that specific fixes are idempotent."""

    @pytest.fixture
    def fix_engine(self):
        """Create a FixEngine instance."""
        config = ValidationConfig()
        return FixEngine(config)

    def test_tabs_fix_is_idempotent(self, tmp_path, fix_engine):
        """Test that tabs fix produces no changes on second pass."""
        # Create file with tabs
        content = '<?xml version="1.0"?>\n<TcPlcObject>\n\t<POU>\n\t\t<Declaration/>\n\t</POU>\n</TcPlcObject>\n'
        file_path = tmp_path / "test_tabs.TcPOU"
        file_path.write_text(content, encoding="utf-8")

        # First pass
        file1 = TwinCATFile.from_path(file_path)
        content_before_first = file1.content

        result1 = fix_engine.apply_fixes(file1, fix_ids=["tabs"])
        file1.save()

        # Verify tabs were fixed
        assert file1.content != content_before_first  # Content changed
        assert "tabs" in result1.applied_fixes

        # Second pass
        file2 = TwinCATFile.from_path(file_path)
        content_before_second = file2.content

        result2 = fix_engine.apply_fixes(file2, fix_ids=["tabs"])

        # Verify idempotent (no changes on second pass)
        assert file2.content == content_before_second  # Content unchanged
        assert len(result2.applied_fixes) == 0

    def test_guid_case_fix_is_idempotent(self, tmp_path, fix_engine):
        """Test that guid_case fix produces no changes on second pass."""
        # Create file with uppercase GUID (using Id attribute which the fix targets)
        content = '<?xml version="1.0"?>\n<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.0">\n  <POU Name="FB_Test" Id="{ABCD1234-5678-90AB-CDEF-1234567890AB}" SpecialFunc="None">\n    <Declaration/>\n  </POU>\n</TcPlcObject>\n'
        file_path = tmp_path / "test_guid.TcPOU"
        file_path.write_text(content, encoding="utf-8")

        # First pass
        file1 = TwinCATFile.from_path(file_path)
        content_before_first = file1.content

        result1 = fix_engine.apply_fixes(file1, fix_ids=["guid_case"])
        file1.save()

        # Verify GUIDs were lowercased
        assert file1.content != content_before_first  # Content changed
        assert "guid_case" in result1.applied_fixes

        # Second pass
        file2 = TwinCATFile.from_path(file_path)
        content_before_second = file2.content

        result2 = fix_engine.apply_fixes(file2, fix_ids=["guid_case"])

        # Verify idempotent (no changes on second pass)
        assert file2.content == content_before_second  # Content unchanged
        assert len(result2.applied_fixes) == 0

    def test_indentation_fix_is_idempotent(self, tmp_path, fix_engine):
        """Test that indentation fix produces no changes on second pass."""
        # Create file with bad indentation (3 spaces)
        content = '<?xml version="1.0"?>\n<TcPlcObject>\n   <POU>\n     <Declaration/>\n   </POU>\n</TcPlcObject>\n'
        file_path = tmp_path / "test_indent.TcPOU"
        file_path.write_text(content, encoding="utf-8")

        # First pass
        file1 = TwinCATFile.from_path(file_path)
        content_before_first = file1.content

        result1 = fix_engine.apply_fixes(file1, fix_ids=["indentation"])
        file1.save()

        # Verify indentation was fixed
        assert file1.content != content_before_first  # Content changed
        assert "indentation" in result1.applied_fixes

        # Second pass
        file2 = TwinCATFile.from_path(file_path)
        content_before_second = file2.content

        result2 = fix_engine.apply_fixes(file2, fix_ids=["indentation"])

        # Verify idempotent (no changes on second pass)
        assert file2.content == content_before_second  # Content unchanged
        assert len(result2.applied_fixes) == 0
