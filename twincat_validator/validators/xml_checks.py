"""XML structure validation checks."""

import re
import xml.etree.ElementTree as ET

from .base import BaseCheck, CheckRegistry
from ..models import ValidationIssue
from ..file_handler import TwinCATFile
from ..config_loader import get_shared_config
from ..snippet_extractor import extract_xml_parse_error_context


def _get_config():
    """Get shared config instance."""
    return get_shared_config()


@CheckRegistry.register
class XmlStructureCheck(BaseCheck):
    """Validates that file contains well-formed XML.

    Extracted from server.py lines 421-426.
    """

    check_id = "xml_structure"

    @staticmethod
    def _expected_top_object_tag(file: TwinCATFile) -> str | None:
        """Map file extension to expected top-level TwinCAT object element."""
        return {
            ".TcPOU": "POU",
            ".TcIO": "Itf",
            ".TcDUT": "DUT",
            ".TcGVL": "GVL",
        }.get(file.suffix)

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        """Check if XML is well-formed.

        Args:
            file: TwinCATFile to validate

        Returns:
            List containing ValidationIssue if XML is malformed, empty list otherwise
        """
        try:
            # This triggers lazy loading and parsing via file.xml_tree property
            # Using the property ensures we're validating the cached tree
            root = file.xml_tree
        except ET.ParseError as e:
            # Get knowledge base entry (Phase 3)
            kb = _get_config().get_check_knowledge("xml_structure")

            # Extract correct example (Phase 3)
            correct_example = None
            if kb.get("correct_examples"):
                correct_example = kb["correct_examples"][0].get("code")

            # Extract parse error context (Phase 3)
            error_message = str(e)
            code_snippet = extract_xml_parse_error_context(file.content, error_message)

            return [
                ValidationIssue(
                    severity="error",
                    category="XML",
                    message=f"XML parse error: {e}",
                    fix_available=False,
                    code_snippet=code_snippet,
                    explanation=kb.get("explanation"),
                    correct_example=correct_example,
                )
            ]

        expected_tag = self._expected_top_object_tag(file)
        if expected_tag:
            actual = None
            for child in root:
                if isinstance(child.tag, str):
                    actual = child.tag
                    break
            if actual != expected_tag:
                return [
                    ValidationIssue(
                        severity="error",
                        category="XML",
                        message=(
                            f"File type {file.suffix} expects <{expected_tag}> "
                            f"as top-level object, found <{actual}>."
                        ),
                        fix_available=False,
                        fix_suggestion=(
                            f"Use .{file.suffix[1:]} content with " f"<{expected_tag}> root object."
                        ),
                    )
                ]

        if file.suffix == ".TcIO":
            has_method_nodes = "<Method " in file.content
            declaration_match = re.search(
                r"(?is)<Itf\b[^>]*>.*?<Declaration><!\[CDATA\[(.*?)\]\]></Declaration>",
                file.content,
            )
            interface_declaration = declaration_match.group(1) if declaration_match else ""
            has_inline_method_text = bool(
                re.search(
                    r"(?im)^\s*METHOD\s+[A-Za-z_][A-Za-z0-9_]*",
                    interface_declaration,
                )
            )
            if has_method_nodes and has_inline_method_text:
                return [
                    ValidationIssue(
                        severity="error",
                        category="XML",
                        message=(
                            "Interface uses mixed method declaration styles "
                            "(inline METHOD text plus <Method> XML nodes)."
                        ),
                        fix_available=False,
                        fix_suggestion=(
                            "Use one style only; prefer <Method> XML nodes and keep "
                            "INTERFACE declaration header-only."
                        ),
                    )
                ]

        return []
