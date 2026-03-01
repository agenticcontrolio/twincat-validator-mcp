"""
Tests for configuration loading and MCP resources
"""

import pytest
import json
from pathlib import Path


def test_config_files_exist():
    """Verify all config JSON files exist"""
    config_dir = Path(__file__).parent.parent / "twincat_validator" / "config"

    assert (config_dir / "validation_rules.json").exists(), "validation_rules.json missing"
    assert (config_dir / "fix_capabilities.json").exists(), "fix_capabilities.json missing"
    assert (config_dir / "naming_conventions.json").exists(), "naming_conventions.json missing"
    assert (config_dir / "generation_contract.json").exists(), "generation_contract.json missing"


def test_validation_rules_schema():
    """Verify validation_rules.json has correct schema"""
    config_path = (
        Path(__file__).parent.parent / "twincat_validator" / "config" / "validation_rules.json"
    )

    with open(config_path) as f:
        data = json.load(f)

    assert "checks" in data, "validation_rules.json must have 'checks' key"
    assert "oop_policy" in data, "validation_rules.json must have 'oop_policy' key"
    assert isinstance(data["checks"], list), "'checks' must be a list"
    assert len(data["checks"]) >= 12, "Expected at least 12 validation checks"

    # Verify each check has required fields
    for check in data["checks"]:
        assert "id" in check, "Each check must have 'id'"
        assert "name" in check, "Each check must have 'name'"
        assert "description" in check, "Each check must have 'description'"
        assert "severity" in check, "Each check must have 'severity'"
        assert "auto_fixable" in check, "Each check must have 'auto_fixable'"
        assert "category" in check, "Each check must have 'category'"

        # Verify types
        assert isinstance(check["id"], str)
        assert isinstance(check["name"], str)
        assert isinstance(check["description"], str)
        assert check["severity"] in ["critical", "error", "warning", "info"]
        assert isinstance(check["auto_fixable"], bool)
        assert isinstance(check["category"], str)

    oop_policy = data["oop_policy"]
    assert isinstance(oop_policy, dict), "'oop_policy' must be an object"
    required_oop_keys = [
        "enforce_override_super_call",
        "required_super_methods",
        "enforce_fb_init_super_call",
        "enforce_this_pointer_consistency",
        "enforce_interface_contract_integrity",
        "allow_abstract_keyword",
    ]
    for key in required_oop_keys:
        assert key in oop_policy, f"'oop_policy' missing key: {key}"


def test_fix_capabilities_schema():
    """Verify fix_capabilities.json has correct schema"""
    config_path = (
        Path(__file__).parent.parent / "twincat_validator" / "config" / "fix_capabilities.json"
    )

    with open(config_path) as f:
        data = json.load(f)

    assert "fixes" in data, "fix_capabilities.json must have 'fixes' key"
    assert isinstance(data["fixes"], list), "'fixes' must be a list"
    assert len(data["fixes"]) >= 7, "Expected at least 7 fix capabilities"

    # Verify each fix has required fields
    for fix in data["fixes"]:
        assert "id" in fix, "Each fix must have 'id'"
        assert "name" in fix, "Each fix must have 'name'"
        assert "description" in fix, "Each fix must have 'description'"
        assert "complexity" in fix, "Each fix must have 'complexity'"
        assert "safe" in fix, "Each fix must have 'safe'"
        assert "risk_level" in fix, "Each fix must have 'risk_level'"

        # Verify types
        assert isinstance(fix["id"], str)
        assert isinstance(fix["name"], str)
        assert isinstance(fix["description"], str)
        assert fix["complexity"] in ["simple", "medium", "complex"]
        assert isinstance(fix["safe"], bool)
        assert fix["risk_level"] in ["none", "low", "medium", "high"]


def test_naming_conventions_schema():
    """Verify naming_conventions.json has correct schema"""
    config_path = (
        Path(__file__).parent.parent / "twincat_validator" / "config" / "naming_conventions.json"
    )

    with open(config_path) as f:
        data = json.load(f)

    assert "file_types" in data, "naming_conventions.json must have 'file_types' key"
    file_types = data["file_types"]

    # Check required file types exist
    assert "TcPOU" in file_types
    assert "TcIO" in file_types
    assert "TcDUT" in file_types
    assert "TcGVL" in file_types

    # Verify each naming rule has required fields
    for file_type, conventions in file_types.items():
        for conv_name, conv_data in conventions.items():
            assert "prefix" in conv_data, f"{file_type}.{conv_name} must have 'prefix'"
            assert "pattern" in conv_data, f"{file_type}.{conv_name} must have 'pattern'"
            assert "examples" in conv_data, f"{file_type}.{conv_name} must have 'examples'"
            assert "description" in conv_data, f"{file_type}.{conv_name} must have 'description'"

            assert isinstance(conv_data["prefix"], str)
            assert isinstance(conv_data["pattern"], str)
            assert isinstance(conv_data["examples"], list)
            assert len(conv_data["examples"]) > 0
            assert isinstance(conv_data["description"], str)


def test_generation_contract_schema():
    """Verify generation_contract.json has expected deterministic schema."""
    config_path = (
        Path(__file__).parent.parent / "twincat_validator" / "config" / "generation_contract.json"
    )

    with open(config_path) as f:
        data = json.load(f)

    assert "version" in data
    assert "file_types" in data
    assert isinstance(data["file_types"], dict)

    expected_types = [".TcPOU", ".TcIO", ".TcDUT", ".TcGVL"]
    for file_type in expected_types:
        assert file_type in data["file_types"]
        contract = data["file_types"][file_type]
        assert "required_elements" in contract
        assert "required_attributes" in contract
        assert "forbidden_patterns" in contract
        assert "generation_rules" in contract
        assert "minimal_skeleton" in contract


def test_server_loads_configs():
    """Verify server.py can import and load configs without errors"""
    # This will raise if configs are malformed
    from server import (
        FIX_CAPABILITIES,
        NAMING_CONVENTIONS,
        SERVER_INFO,
        VALIDATION_CHECKS,
        get_generation_contract_by_type,
        get_generation_contract_resource,
        get_effective_oop_policy,
        get_oop_policy_defaults_resource,
    )

    # Verify configs are loaded
    assert len(VALIDATION_CHECKS) >= 12, "VALIDATION_CHECKS should have at least 12 entries"
    assert len(FIX_CAPABILITIES) >= 7, "FIX_CAPABILITIES should have at least 7 entries"
    assert len(NAMING_CONVENTIONS) >= 4, "NAMING_CONVENTIONS should have at least 4 file types"

    # Verify SERVER_INFO is correctly derived
    assert SERVER_INFO["validation_checks"] == len(VALIDATION_CHECKS)
    assert SERVER_INFO["auto_fix_capabilities"] == len(FIX_CAPABILITIES)

    generation_contract = json.loads(get_generation_contract_resource())
    assert "file_types" in generation_contract
    assert ".TcPOU" in generation_contract["file_types"]

    pou_contract = json.loads(get_generation_contract_by_type("TcPOU"))
    assert "required_elements" in pou_contract

    oop_defaults = json.loads(get_oop_policy_defaults_resource())
    assert "required_super_methods" in oop_defaults
    assert "enforce_override_super_call" in oop_defaults

    oop_effective = json.loads(get_effective_oop_policy(""))
    assert oop_effective.get("success") is True
    assert "policy" in oop_effective
    assert "policy_source" in oop_effective


def test_check_ids_are_unique():
    """Verify all validation check IDs are unique"""
    config_path = (
        Path(__file__).parent.parent / "twincat_validator" / "config" / "validation_rules.json"
    )

    with open(config_path) as f:
        data = json.load(f)

    check_ids = [check["id"] for check in data["checks"]]
    assert len(check_ids) == len(set(check_ids)), "Duplicate check IDs found"


def test_fix_ids_are_unique():
    """Verify all fix IDs are unique"""
    config_path = (
        Path(__file__).parent.parent / "twincat_validator" / "config" / "fix_capabilities.json"
    )

    with open(config_path) as f:
        data = json.load(f)

    fix_ids = [fix["id"] for fix in data["fixes"]]
    assert len(fix_ids) == len(set(fix_ids)), "Duplicate fix IDs found"


def test_check_id_format():
    """Verify check IDs follow snake_case convention"""
    config_path = (
        Path(__file__).parent.parent / "twincat_validator" / "config" / "validation_rules.json"
    )

    with open(config_path) as f:
        data = json.load(f)

    for check in data["checks"]:
        check_id = check["id"]
        # Should be snake_case (lowercase with underscores)
        assert check_id.islower() or "_" in check_id, f"Check ID '{check_id}' should be snake_case"
        assert " " not in check_id, f"Check ID '{check_id}' should not contain spaces"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
