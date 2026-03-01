"""GUID validation checks."""

import re
from collections import Counter

from .base import BaseCheck, CheckRegistry
from ..models import ValidationIssue
from ..file_handler import TwinCATFile
from ..config_loader import get_shared_config
from ..snippet_extractor import extract_first_occurrence_snippet


def _get_config():
    """Get shared config instance."""
    return get_shared_config()


@CheckRegistry.register
class GuidFormatCheck(BaseCheck):
    """Validates GUID format - must be lowercase hex only.

    Extracted from server.py lines 428-466 (check_guid_validity method).
    """

    check_id = "guid_format"

    @staticmethod
    def _find_placeholder_guids(content: str) -> list[str]:
        """Find obvious placeholder GUID tokens/patterns."""
        placeholders: list[str] = []

        placeholders.extend(re.findall(r"GENERATE-NEW-GUID", content))

        guid_any_case_pattern = (
            r'Id="\{('
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\}"'
        )
        guid_any_case = re.findall(guid_any_case_pattern, content)
        for guid in guid_any_case:
            compact = guid.replace("-", "").lower()
            # Reject repeated-char placeholders like aaaa..., 1111..., 0000...
            if len(set(compact)) == 1:
                placeholders.append(guid)

        return placeholders

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        """Check GUID format validity - must be lowercase hex only.

        Args:
            file: TwinCATFile to validate

        Returns:
            List of ValidationIssue objects for GUID format problems
        """
        issues = []

        # Check for placeholder GUIDs/tokens
        placeholder_guids = self._find_placeholder_guids(file.content)
        if placeholder_guids:
            # Get knowledge base entry (Phase 3)
            kb = _get_config().get_check_knowledge("guid_format")

            # Extract correct example (Phase 3)
            correct_example = None
            if kb.get("correct_examples"):
                correct_example = kb["correct_examples"][0].get("code")

            issues.append(
                ValidationIssue(
                    severity="error",
                    category="GUID",
                    message=(
                        f"Found {len(placeholder_guids)} placeholder GUID(s). "
                        "Replace with unique GUIDs."
                    ),
                    fix_available=False,
                    fix_suggestion="Generate unique GUIDs for all placeholder entries",
                    code_snippet=extract_first_occurrence_snippet(
                        file.content, placeholder_guids[0], context_lines=1
                    ),
                    explanation=kb.get("explanation"),
                    correct_example=correct_example,
                )
            )
            # Return early - placeholders are more critical than case issues
            return issues

        # Check malformed GUID syntax in Id="{...}" attributes.
        # This catches tokens like spaces or invalid separators, e.g. "{e6f7...-ca db-...}".
        guid_token_pattern = re.compile(r'Id="\{([^"]+)\}"')
        strict_guid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )
        any_case_guid_pattern_compiled = re.compile(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
        )
        malformed_tokens: list[str] = []
        for guid_token in guid_token_pattern.findall(file.content):
            if strict_guid_pattern.match(guid_token):
                continue
            if any_case_guid_pattern_compiled.match(guid_token):
                # Uppercase issue is handled below with explicit guidance.
                continue
            malformed_tokens.append(guid_token)

        if malformed_tokens:
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="GUID",
                    message=(
                        f"Found {len(malformed_tokens)} malformed GUID token(s) "
                        "in Id attributes."
                    ),
                    fix_available=False,
                    fix_suggestion=(
                        "Use GUID format: {xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx} "
                        "with lowercase hex only."
                    ),
                    code_snippet=extract_first_occurrence_snippet(
                        file.content, malformed_tokens[0], context_lines=1
                    ),
                )
            )
            return issues

        # Check GUID format - LOWERCASE hex only (a-f, 0-9)
        guid_pattern = r'Id="\{([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\}"'
        # Match any-case GUID-shaped Id attributes (excludes numeric IDs like LineId Id="9")
        any_case_guid_pattern = (
            r'Id="\{[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\}"'
        )

        all_guids = re.findall(any_case_guid_pattern, file.content)
        valid_guids = re.findall(guid_pattern, file.content)

        # Check for uppercase letters in GUIDs (any GUID with uppercase chars)
        # all_guids matches any-case GUIDs; valid_guids matches lowercase-only.
        # The difference gives us GUIDs that contain at least one uppercase character.
        uppercase_count = len(all_guids) - len(valid_guids)
        if uppercase_count > 0:
            # Get knowledge base entry (Phase 3)
            kb = _get_config().get_check_knowledge("guid_format")

            # Extract correct example (Phase 3)
            correct_example = None
            if kb.get("correct_examples"):
                correct_example = kb["correct_examples"][0].get("code")

            # Find first uppercase GUID for snippet
            first_uppercase_guid = None
            for match in re.finditer(any_case_guid_pattern, file.content):
                guid_text = match.group(0)
                # Check if it contains uppercase (not all lowercase)
                if guid_text != guid_text.lower():
                    first_uppercase_guid = match.group(0)
                    break

            # Extract snippet showing the first uppercase GUID
            code_snippet = None
            if first_uppercase_guid:
                code_snippet = extract_first_occurrence_snippet(
                    file.content, first_uppercase_guid, context_lines=1
                )

            issues.append(
                ValidationIssue(
                    severity="error",
                    category="GUID",
                    message=(
                        f"Found {uppercase_count} GUID(s) with uppercase letters. "
                        "TwinCAT requires lowercase hex only (a-f, 0-9)"
                    ),
                    fix_available=True,
                    fix_suggestion=(
                        "Convert all GUIDs to lowercase: " "{xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx}"
                    ),
                    code_snippet=code_snippet,
                    explanation=kb.get("explanation"),
                    correct_example=correct_example,
                )
            )

        return issues


@CheckRegistry.register
class GuidUniquenessCheck(BaseCheck):
    """Validates that all GUIDs are unique within the file.

    Extracted from server.py lines 471-487 (check_guid_uniqueness method).
    """

    check_id = "guid_uniqueness"

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        """Check for duplicate GUIDs - only checks lowercase hex.

        Args:
            file: TwinCATFile to validate

        Returns:
            List of ValidationIssue objects for each duplicate GUID
        """
        issues = []

        # Only match lowercase GUIDs (proper format)
        guid_pattern = r'Id="\{([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\}"'
        guids = re.findall(guid_pattern, file.content)

        duplicates = [guid for guid, count in Counter(guids).items() if count > 1]

        if duplicates:
            for guid in duplicates:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="GUID",
                        message=f"Duplicate GUID: {{{guid}}}",
                        fix_available=False,
                        fix_suggestion="Generate unique GUID for this element",
                    )
                )

        return issues
