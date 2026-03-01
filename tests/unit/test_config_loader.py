"""Tests for twincat_validator.config_loader module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from twincat_validator.config_loader import ValidationConfig, _load_json_config, get_shared_config
from twincat_validator.exceptions import ConfigurationError


class TestLoadJsonConfig:
    """Tests for _load_json_config helper function."""

    def test_loads_validation_rules_successfully(self):
        """Test loading validation_rules.json."""
        config = _load_json_config("validation_rules.json")
        assert isinstance(config, dict)
        assert "checks" in config

    def test_loads_fix_capabilities_successfully(self):
        """Test loading fix_capabilities.json."""
        config = _load_json_config("fix_capabilities.json")
        assert isinstance(config, dict)
        assert "fixes" in config

    def test_loads_naming_conventions_successfully(self):
        """Test loading naming_conventions.json."""
        config = _load_json_config("naming_conventions.json")
        assert isinstance(config, dict)
        assert "file_types" in config

    def test_loads_knowledge_base_successfully(self):
        """Test loading knowledge_base.json."""
        config = _load_json_config("knowledge_base.json")
        assert isinstance(config, dict)
        assert "knowledge_base" in config

    def test_loads_generation_contract_successfully(self):
        """Test loading generation_contract.json."""
        config = _load_json_config("generation_contract.json")
        assert isinstance(config, dict)
        assert "file_types" in config

    def test_raises_on_nonexistent_file(self):
        """Test raises ConfigurationError for missing file."""
        with pytest.raises(ConfigurationError, match="not found"):
            _load_json_config("nonexistent.json")


class TestValidationConfig:
    """Tests for ValidationConfig class."""

    def test_initializes_successfully(self):
        """Test ValidationConfig initializes without error."""
        config = ValidationConfig()
        assert config is not None

    def test_loads_all_validation_checks(self):
        """Test all validation checks are loaded."""
        config = ValidationConfig()
        assert len(config.validation_checks) >= 13

        expected_check_ids = [
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

        for check_id in expected_check_ids:
            assert check_id in config.validation_checks

    def test_loads_all_fix_capabilities(self):
        """Test all fix capabilities are loaded."""
        config = ValidationConfig()
        assert len(config.fix_capabilities) == 10

        expected_fix_ids = [
            "tabs",
            "guid_case",
            "file_ending",
            "newlines",
            "cdata",
            "var_blocks",
            "excessive_blanks",
            "indentation",
            "lineids",
        ]

        for fix_id in expected_fix_ids:
            assert fix_id in config.fix_capabilities

    def test_loads_naming_conventions(self):
        """Test naming conventions are loaded."""
        config = ValidationConfig()
        assert config.naming_conventions is not None
        assert isinstance(config.naming_conventions, dict)

    def test_loads_knowledge_base(self):
        """Test knowledge base is loaded (Phase 3)."""
        config = ValidationConfig()
        assert config.knowledge_base is not None
        assert isinstance(config.knowledge_base, dict)
        assert "checks" in config.knowledge_base
        assert "fixes" in config.knowledge_base
        assert "concepts" in config.knowledge_base

    def test_loads_generation_contract(self):
        """Test generation contract is loaded."""
        config = ValidationConfig()
        assert config.generation_contract is not None
        assert isinstance(config.generation_contract, dict)
        assert ".TcPOU" in config.generation_contract
        assert ".TcIO" in config.generation_contract
        assert ".TcDUT" in config.generation_contract
        assert ".TcGVL" in config.generation_contract

    def test_get_check_config_returns_correct_data(self):
        """Test get_check_config retrieves check configuration."""
        config = ValidationConfig()
        check = config.get_check_config("xml_structure")
        assert check["id"] == "xml_structure"
        assert "name" in check
        assert "description" in check

    def test_get_fix_config_returns_correct_data(self):
        """Test get_fix_config retrieves fix configuration."""
        config = ValidationConfig()
        fix = config.get_fix_config("tabs")
        assert fix["id"] == "tabs"
        assert "name" in fix
        assert "description" in fix

    def test_get_check_knowledge_returns_enrichment_data(self):
        """Test get_check_knowledge returns Phase 3 enrichment data."""
        config = ValidationConfig()
        kb = config.get_check_knowledge("xml_structure")

        assert isinstance(kb, dict)
        assert "explanation" in kb
        assert "why_it_matters" in kb
        assert "correct_examples" in kb
        assert "common_mistakes" in kb

    def test_get_check_knowledge_returns_empty_for_unknown_check(self):
        """Test get_check_knowledge returns empty dict for unknown check."""
        config = ValidationConfig()
        kb = config.get_check_knowledge("nonexistent_check")
        assert kb == {}

    def test_get_fix_knowledge_returns_enrichment_data(self):
        """Test get_fix_knowledge returns Phase 3 enrichment data."""
        config = ValidationConfig()
        kb = config.get_fix_knowledge("tabs")

        assert isinstance(kb, dict)
        assert "explanation" in kb
        assert "algorithm" in kb
        assert "risk_assessment" in kb
        assert "before_after" in kb

    def test_get_fix_knowledge_returns_empty_for_unknown_fix(self):
        """Test get_fix_knowledge returns empty dict for unknown fix."""
        config = ValidationConfig()
        kb = config.get_fix_knowledge("nonexistent_fix")
        assert kb == {}

    def test_get_generation_contract_returns_full_payload(self):
        """Test get_generation_contract returns raw contract payload."""
        config = ValidationConfig()
        payload = config.get_generation_contract()

        assert isinstance(payload, dict)
        assert "version" in payload
        assert "file_types" in payload
        assert ".TcPOU" in payload["file_types"]

    def test_get_file_type_contract_accepts_dot_or_no_dot(self):
        """Test get_file_type_contract normalizes file extension input."""
        config = ValidationConfig()
        with_dot = config.get_file_type_contract(".TcPOU")
        without_dot = config.get_file_type_contract("TcPOU")

        assert with_dot == without_dot
        assert "required_elements" in with_dot

    def test_get_file_type_contract_returns_empty_for_unknown_type(self):
        """Test get_file_type_contract returns empty dict for unsupported extension."""
        config = ValidationConfig()
        assert config.get_file_type_contract(".TcXYZ") == {}

    def test_oop_policy_defaults_loaded(self):
        """Test OOP policy defaults are loaded from validation rules."""
        config = ValidationConfig()
        policy = config.get_oop_policy()
        assert policy["enforce_override_super_call"] is False
        assert policy["required_super_methods"] == []
        assert policy["enforce_fb_init_super_call"] is True
        assert policy["enforce_this_pointer_consistency"] is True
        assert policy["enforce_interface_contract_integrity"] is True
        assert policy["allow_abstract_keyword"] is True

    def test_get_oop_policy_applies_project_override(self, tmp_path):
        """Test per-project .twincat-validator.json overrides default OOP policy."""
        config = ValidationConfig()
        (tmp_path / ".twincat-validator.json").write_text(
            (
                "{\n"
                '  "oop_policy": {\n'
                '    "enforce_override_super_call": false,\n'
                '    "required_super_methods": ["M_Start"],\n'
                '    "allow_abstract_keyword": false\n'
                "  }\n"
                "}\n"
            ),
            encoding="utf-8",
        )
        target = tmp_path / "FB_Test.TcPOU"
        target.write_text("", encoding="utf-8")
        policy = config.get_oop_policy(target)
        assert policy["enforce_override_super_call"] is False
        assert policy["required_super_methods"] == ["M_Start"]
        assert policy["allow_abstract_keyword"] is False
        # Unspecified keys should still come from defaults.
        assert policy["enforce_fb_init_super_call"] is True

    def test_resolve_oop_policy_includes_source_metadata(self, tmp_path):
        """Test resolve_oop_policy returns policy and source path metadata."""
        config = ValidationConfig()
        (tmp_path / ".twincat-validator.json").write_text(
            '{\n  "oop_policy": {"required_super_methods": ["M_Start"]}\n}\n',
            encoding="utf-8",
        )
        target = tmp_path / "FB_Test.TcPOU"
        target.write_text("", encoding="utf-8")
        resolved = config.resolve_oop_policy(target)
        assert "policy" in resolved
        assert "source" in resolved
        assert resolved["policy"]["required_super_methods"] == ["M_Start"]
        assert str(tmp_path / ".twincat-validator.json") in resolved["source"]

    def test_knowledge_base_has_all_checks(self):
        """Test knowledge base has entries for all checks."""
        config = ValidationConfig()
        checks_kb = config.knowledge_base.get("checks", {})

        # All checks should have knowledge base entries
        assert len(checks_kb) == len(config.validation_checks)

        for check_id in config.validation_checks.keys():
            assert check_id in checks_kb, f"Missing knowledge base entry for check: {check_id}"

    def test_knowledge_base_has_all_fixes(self):
        """Test knowledge base has entries for all fixes."""
        config = ValidationConfig()
        fixes_kb = config.knowledge_base.get("fixes", {})

        # All 9 fixes should have knowledge base entries
        assert len(fixes_kb) == 10

        for fix_id in config.fix_capabilities.keys():
            assert fix_id in fixes_kb, f"Missing knowledge base entry for fix: {fix_id}"

    def test_server_info_populated(self):
        """Test server info is populated."""
        config = ValidationConfig()
        assert config.server_info["name"] == "twincat-validator"
        assert config.server_info["version"] == "1.0.0"
        assert len(config.server_info["supported_file_types"]) == 4
        assert config.server_info["validation_checks"] == len(config.validation_checks)
        assert config.server_info["auto_fix_capabilities"] == 10

    def test_severity_overrides_initially_empty(self):
        """Test severity_overrides starts empty."""
        config = ValidationConfig()
        assert config.severity_overrides == {}

    def test_disabled_checks_initially_empty(self):
        """Test disabled_checks starts empty."""
        config = ValidationConfig()
        assert config.disabled_checks == []

    def test_is_check_disabled_returns_false_initially(self):
        """Test is_check_disabled returns False initially."""
        config = ValidationConfig()
        assert config.is_check_disabled("xml_structure") is False

    def test_is_check_disabled_returns_true_when_disabled(self):
        """Test is_check_disabled returns True when check is disabled."""
        config = ValidationConfig()
        config.disabled_checks = ["xml_structure"]
        assert config.is_check_disabled("xml_structure") is True

    def test_get_check_severity_returns_default_severity(self):
        """Test get_check_severity returns default severity."""
        config = ValidationConfig()
        severity = config.get_check_severity("xml_structure")
        assert severity in ["critical", "error", "warning", "info"]

    def test_get_check_severity_respects_overrides(self):
        """Test get_check_severity respects severity overrides."""
        config = ValidationConfig()
        config.severity_overrides["xml_structure"] = "warning"
        assert config.get_check_severity("xml_structure") == "warning"


class TestSharedConfig:
    """Tests for shared ValidationConfig accessor."""

    def test_get_shared_config_returns_singleton(self):
        """Shared config accessor should return the same instance per process."""
        config_a = get_shared_config()
        config_b = get_shared_config()
        assert config_a is config_b

    def test_shared_config_is_fully_initialized(self):
        """Shared config should expose loaded check/fix/knowledge data."""
        config = get_shared_config()
        assert len(config.validation_checks) >= 13
        assert len(config.fix_capabilities) == 10
        assert "checks" in config.knowledge_base
        assert ".TcPOU" in config.generation_contract
