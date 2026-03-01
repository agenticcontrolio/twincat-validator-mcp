"""Tests for knowledge_base.json structure and completeness."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest


class TestKnowledgeBaseStructure:
    """Tests for knowledge_base.json schema and content."""

    @pytest.fixture
    def knowledge_base(self):
        """Load knowledge_base.json."""
        kb_path = (
            Path(__file__).parent.parent.parent
            / "twincat_validator"
            / "config"
            / "knowledge_base.json"
        )
        with open(kb_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_knowledge_base_loads_successfully(self, knowledge_base):
        """Test knowledge base JSON is valid and loads."""
        assert knowledge_base is not None
        assert isinstance(knowledge_base, dict)

    def test_has_version_field(self, knowledge_base):
        """Test knowledge base has version field."""
        assert "version" in knowledge_base
        assert knowledge_base["version"] == "1.0.0"

    def test_has_knowledge_base_root(self, knowledge_base):
        """Test knowledge base has root 'knowledge_base' key."""
        assert "knowledge_base" in knowledge_base
        kb = knowledge_base["knowledge_base"]
        assert isinstance(kb, dict)
        assert "checks" in kb
        assert "fixes" in kb
        assert "concepts" in kb

    def test_all_checks_have_entries(self, knowledge_base):
        """Test all validation checks have knowledge base entries."""
        expected_checks = [
            "xml_structure",
            "guid_format",
            "guid_uniqueness",
            "indentation",
            "tabs",
            "file_ending",
            "property_var_blocks",
            "lineids_count",
            "element_ordering",
            "naming_conventions",
            "cdata_formatting",
            "excessive_blank_lines",
            "pou_structure",
            "extends_visibility",
            "override_marker",
            "override_signature",
            "interface_contract",
            "policy_interface_contract_integrity",
            "extends_cycle",
            "override_super_call",
            "inheritance_property_contract",
            "fb_init_signature",
            "fb_init_super_call",
            "this_pointer_consistency",
            "abstract_contract",
        ]

        checks = knowledge_base["knowledge_base"]["checks"]
        assert len(checks) >= len(expected_checks)

        for check_id in expected_checks:
            assert check_id in checks, f"Missing knowledge base entry for check: {check_id}"

    def test_all_fixes_have_entries(self, knowledge_base):
        """Test all 10 fixes have knowledge base entries."""
        expected_fixes = [
            "tabs",
            "guid_case",
            "file_ending",
            "newlines",
            "cdata",
            "var_blocks",
            "excessive_blanks",
            "indentation",
            "lineids",
            "override_attribute",  # Phase 5A
        ]

        fixes = knowledge_base["knowledge_base"]["fixes"]
        assert len(fixes) == 10

        for fix_id in expected_fixes:
            assert fix_id in fixes, f"Missing knowledge base entry for fix: {fix_id}"

    def test_check_entries_have_required_fields(self, knowledge_base):
        """Test each check entry has required fields."""
        checks = knowledge_base["knowledge_base"]["checks"]

        required_fields = ["explanation", "why_it_matters", "correct_examples", "common_mistakes"]

        for check_id, check_entry in checks.items():
            for field in required_fields:
                assert field in check_entry, f"Check '{check_id}' missing field: {field}"

            # Validate field types
            assert isinstance(check_entry["explanation"], str)
            assert isinstance(check_entry["why_it_matters"], str)
            assert isinstance(check_entry["correct_examples"], list)
            assert isinstance(check_entry["common_mistakes"], list)

            # Ensure non-empty
            assert len(check_entry["explanation"]) > 0
            assert len(check_entry["why_it_matters"]) > 0
            assert len(check_entry["correct_examples"]) > 0

    def test_fix_entries_have_required_fields(self, knowledge_base):
        """Test each fix entry has required fields."""
        fixes = knowledge_base["knowledge_base"]["fixes"]

        required_fields = ["explanation", "algorithm", "risk_assessment", "before_after"]

        for fix_id, fix_entry in fixes.items():
            for field in required_fields:
                assert field in fix_entry, f"Fix '{fix_id}' missing field: {field}"

            # Validate field types
            assert isinstance(fix_entry["explanation"], str)
            assert isinstance(fix_entry["algorithm"], str)
            assert isinstance(fix_entry["risk_assessment"], str)
            assert isinstance(fix_entry["before_after"], dict)

            # Ensure non-empty
            assert len(fix_entry["explanation"]) > 0
            assert len(fix_entry["algorithm"]) > 0

            # Validate before_after structure
            assert "before" in fix_entry["before_after"]
            assert "after" in fix_entry["before_after"]

    def test_correct_examples_have_structure(self, knowledge_base):
        """Test correct_examples have description and code fields."""
        checks = knowledge_base["knowledge_base"]["checks"]

        for check_id, check_entry in checks.items():
            for example in check_entry["correct_examples"]:
                assert "description" in example, f"Example in '{check_id}' missing description"
                assert "code" in example, f"Example in '{check_id}' missing code"
                assert isinstance(example["description"], str)
                assert isinstance(example["code"], str)

    def test_common_mistakes_have_structure(self, knowledge_base):
        """Test common_mistakes have mistake, code, and reason fields."""
        checks = knowledge_base["knowledge_base"]["checks"]

        for check_id, check_entry in checks.items():
            # Some checks may have no common_mistakes (acceptable)
            for mistake in check_entry.get("common_mistakes", []):
                assert "mistake" in mistake, f"Mistake in '{check_id}' missing 'mistake' field"
                assert "code" in mistake, f"Mistake in '{check_id}' missing 'code' field"
                assert "reason" in mistake, f"Mistake in '{check_id}' missing 'reason' field"

    def test_concepts_section_exists(self, knowledge_base):
        """Test concepts section has entries."""
        concepts = knowledge_base["knowledge_base"]["concepts"]
        assert len(concepts) >= 3  # At least 3 concepts

        # Check for expected concepts
        expected_concepts = [
            "guid_rules",
            "lineids_algorithm",
            "xml_structure",
            "indentation_rules",
            "property_syntax",
        ]

        for concept_id in expected_concepts:
            assert concept_id in concepts, f"Missing concept: {concept_id}"

    def test_concepts_have_required_fields(self, knowledge_base):
        """Test concept entries have required fields."""
        concepts = knowledge_base["knowledge_base"]["concepts"]

        for concept_id, concept_entry in concepts.items():
            assert "title" in concept_entry, f"Concept '{concept_id}' missing title"
            assert "content" in concept_entry, f"Concept '{concept_id}' missing content"
            assert (
                "learning_objectives" in concept_entry
            ), f"Concept '{concept_id}' missing learning_objectives"

            # Validate types
            assert isinstance(concept_entry["title"], str)
            assert isinstance(concept_entry["content"], str)
            assert isinstance(concept_entry["learning_objectives"], list)

            # Ensure non-empty
            assert len(concept_entry["title"]) > 0
            assert len(concept_entry["content"]) > 0
            assert len(concept_entry["learning_objectives"]) > 0

    def test_no_duplicate_check_ids(self, knowledge_base):
        """Test no duplicate check IDs."""
        checks = knowledge_base["knowledge_base"]["checks"]
        check_ids = list(checks.keys())
        assert len(check_ids) == len(set(check_ids)), "Duplicate check IDs found"

    def test_no_duplicate_fix_ids(self, knowledge_base):
        """Test no duplicate fix IDs."""
        fixes = knowledge_base["knowledge_base"]["fixes"]
        fix_ids = list(fixes.keys())
        assert len(fix_ids) == len(set(fix_ids)), "Duplicate fix IDs found"

    def test_explanations_are_educational(self, knowledge_base):
        """Test explanations are substantive (> 50 chars)."""
        checks = knowledge_base["knowledge_base"]["checks"]

        for check_id, check_entry in checks.items():
            explanation = check_entry["explanation"]
            assert (
                len(explanation) > 50
            ), f"Check '{check_id}' explanation too short (should be educational)"

    def test_json_formatting_is_valid(self):
        """Test JSON file is properly formatted (can be parsed)."""
        kb_path = (
            Path(__file__).parent.parent.parent
            / "twincat_validator"
            / "config"
            / "knowledge_base.json"
        )

        # Attempt to load - will raise exception if invalid
        with open(kb_path, "r", encoding="utf-8") as f:
            json.load(f)

        # If we get here, JSON is valid
        assert True
