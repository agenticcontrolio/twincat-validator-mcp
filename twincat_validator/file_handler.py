"""TwinCATFile value object for encapsulating file operations."""

from __future__ import annotations

from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET

from .exceptions import UnsupportedFileTypeError


class TwinCATFile:
    """Immutable value object representing a TwinCAT XML file.

    Provides lazy loading and caching of parsed XML tree.
    All XML parsing ALWAYS uses self.content, never disk.
    This prevents data-mismatch bugs (Bug 2 from Phase 1).
    """

    def __init__(self, filepath: Path):
        """Initialize with file path.

        Args:
            filepath: Path to TwinCAT XML file
        """
        self.filepath = filepath
        self._content: Optional[str] = None
        self._lines: Optional[list[str]] = None
        self._xml_tree: Optional[ET.Element] = None
        self._pou_subtype: Optional[str] = None

    @property
    def content(self) -> str:
        """File content (lazy loaded).

        Returns:
            File content as string
        """
        if self._content is None:
            with open(self.filepath, "r", encoding="utf-8") as f:
                self._content = f.read()
        return self._content

    @content.setter
    def content(self, value: str):
        """Update content and invalidate caches.

        Args:
            value: New file content
        """
        self._content = value
        self._lines = None
        self._xml_tree = None
        # pou_subtype stays cached (doesn't change during fixes)

    @property
    def lines(self) -> list[str]:
        """File lines (lazy loaded, cached).

        Returns:
            List of lines (without newline characters)
        """
        if self._lines is None:
            self._lines = self.content.split("\n")
        return self._lines

    @property
    def suffix(self) -> str:
        """File extension.

        Returns:
            Extension string (.TcPOU, .TcIO, .TcDUT, .TcGVL)
        """
        return self.filepath.suffix

    @property
    def xml_tree(self) -> ET.Element:
        """Parsed XML tree (lazy loaded, cached).

        CRITICAL: Always parses from self.content, NEVER from disk.
        This prevents data-mismatch bugs where fixes see stale content.

        Returns:
            Parsed XML Element tree

        Raises:
            ET.ParseError: If XML is malformed
        """
        if self._xml_tree is None:
            self._xml_tree = ET.fromstring(self.content)
        return self._xml_tree

    @property
    def pou_subtype(self) -> Optional[str]:
        """POU subtype detection (cached).

        Returns:
            'function_block', 'function', 'program', or None
        """
        if self._pou_subtype is None:
            from .utils import detect_pou_subtype

            self._pou_subtype = detect_pou_subtype(self)
        return self._pou_subtype

    def save(self, create_backup: bool = False) -> Optional[Path]:
        """Write content to disk.

        Args:
            create_backup: If True, creates .bak file before writing

        Returns:
            Path to backup file if created, None otherwise
        """
        # CRITICAL: Load content BEFORE opening file in write mode
        # (opening in "w" mode truncates the file immediately)
        content_to_write = self.content

        backup_path = None
        if create_backup:
            backup_path = self.filepath.with_suffix(self.filepath.suffix + ".bak")
            # Read original from disk for backup
            with open(self.filepath, "r", encoding="utf-8") as f:
                backup_content = f.read()
            with open(backup_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(backup_content)

        # Write modified content
        with open(self.filepath, "w", encoding="utf-8", newline="\n") as f:
            f.write(content_to_write)

        return backup_path

    @classmethod
    def from_path(cls, path: Path) -> "TwinCATFile":
        """Factory method with validation.

        Args:
            path: Path to file

        Returns:
            TwinCATFile instance

        Raises:
            FileNotFoundError: If path doesn't exist
            UnsupportedFileTypeError: If extension not supported
        """
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        supported_extensions = [".TcPOU", ".TcIO", ".TcDUT", ".TcGVL"]
        if path.suffix not in supported_extensions:
            raise UnsupportedFileTypeError(
                f"Unsupported file type: {path.suffix}. "
                f"Supported types: {', '.join(supported_extensions)}"
            )

        return cls(path)
