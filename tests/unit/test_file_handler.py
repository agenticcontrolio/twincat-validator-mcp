"""Tests for twincat_validator.file_handler module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from twincat_validator.file_handler import TwinCATFile
from twincat_validator.exceptions import UnsupportedFileTypeError
import pytest


class TestTwinCATFile:
    """Tests for TwinCATFile class."""

    def test_lazy_content_loading(self, valid_tcpou):
        """Test content is loaded lazily on first access."""
        file = TwinCATFile(valid_tcpou)

        # Content should not be loaded yet
        assert file._content is None

        # Access content triggers loading
        content = file.content
        assert content is not None
        assert file._content is not None
        assert len(content) > 0

    def test_lazy_xml_tree_loading(self, valid_tcpou):
        """Test XML tree is parsed lazily on first access."""
        file = TwinCATFile(valid_tcpou)

        # XML tree should not be parsed yet
        assert file._xml_tree is None

        # Access xml_tree triggers parsing from content
        tree = file.xml_tree
        assert tree is not None
        assert file._xml_tree is not None
        assert tree.tag == "TcPlcObject"

    def test_content_setter_invalidates_caches(self, valid_tcpou):
        """Test setting content invalidates lines and xml_tree caches."""
        file = TwinCATFile(valid_tcpou)

        # Load caches
        _ = file.lines
        _ = file.xml_tree
        assert file._lines is not None
        assert file._xml_tree is not None

        # Update content
        new_content = '<?xml version="1.0"?>\n<TcPlcObject></TcPlcObject>'
        file.content = new_content

        # Caches should be invalidated
        assert file._lines is None
        assert file._xml_tree is None
        assert file.content == new_content

    def test_lines_property(self, valid_tcpou):
        """Test lines property splits content correctly."""
        file = TwinCATFile(valid_tcpou)

        lines = file.lines
        assert isinstance(lines, list)
        assert len(lines) > 0
        assert all(isinstance(line, str) for line in lines)

    def test_suffix_property(self, valid_tcpou):
        """Test suffix property returns file extension."""
        file = TwinCATFile(valid_tcpou)
        assert file.suffix == ".TcPOU"

    def test_pou_subtype_detection(self, valid_tcpou):
        """Test POU subtype is detected correctly."""
        file = TwinCATFile(valid_tcpou)
        assert file.pou_subtype == "function_block"

    def test_pou_subtype_cached(self, valid_tcpou):
        """Test POU subtype is cached after first detection."""
        file = TwinCATFile(valid_tcpou)

        # First access triggers detection
        subtype1 = file.pou_subtype
        # Second access uses cache
        subtype2 = file.pou_subtype

        assert subtype1 == subtype2
        assert subtype1 == "function_block"

    def test_from_path_factory(self, valid_tcpou):
        """Test from_path factory method with validation."""
        file = TwinCATFile.from_path(valid_tcpou)
        assert isinstance(file, TwinCATFile)
        assert file.filepath == valid_tcpou

    def test_from_path_raises_on_missing_file(self, tmp_path):
        """Test from_path raises FileNotFoundError for missing file."""
        missing_file = tmp_path / "nonexistent.TcPOU"

        with pytest.raises(FileNotFoundError, match="File not found"):
            TwinCATFile.from_path(missing_file)

    def test_from_path_raises_on_unsupported_extension(self, tmp_path):
        """Test from_path raises UnsupportedFileTypeError for wrong extension."""
        bad_file = tmp_path / "test.txt"
        bad_file.write_text("content")

        with pytest.raises(UnsupportedFileTypeError, match="Unsupported file type"):
            TwinCATFile.from_path(bad_file)

    def test_save_without_backup(self, tmp_path):
        """Test save() writes content to disk without backup."""
        test_file = tmp_path / "test.TcPOU"
        test_file.write_text("original content")

        file = TwinCATFile(test_file)
        file.content = "modified content"

        backup_path = file.save(create_backup=False)

        assert backup_path is None
        assert test_file.read_text() == "modified content"

    def test_save_without_preloading_content(self, tmp_path):
        """Test save() works even when content was never accessed or set."""
        test_file = tmp_path / "test.TcPOU"
        test_file.write_text("original content")

        file = TwinCATFile(test_file)
        backup_path = file.save(create_backup=False)

        assert backup_path is None
        assert test_file.read_text() == "original content"

    def test_save_with_backup(self, tmp_path):
        """Test save() creates backup file when requested."""
        test_file = tmp_path / "test.TcPOU"
        test_file.write_text("original content")

        file = TwinCATFile(test_file)
        file.content = "modified content"

        backup_path = file.save(create_backup=True)

        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.name == "test.TcPOU.bak"
        assert backup_path.read_text() == "original content"
        assert test_file.read_text() == "modified content"
