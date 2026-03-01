"""Configuration loading and management for TwinCAT Validator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .exceptions import ConfigurationError


def _load_json_config(filename: str) -> dict[str, Any]:
    """Load configuration from JSON file in config/ directory.

    Args:
        filename: Name of config file (e.g., 'validation_rules.json')

    Returns:
        Parsed JSON content as dict

    Raises:
        ConfigurationError: If file not found or invalid JSON
    """
    # Config files are in the package's config/ folder
    config_path = Path(__file__).parent / "config" / filename
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise ConfigurationError(
            f"Configuration file not found: {config_path}\n"
            f"Please ensure the config/ directory contains {filename}"
        )
    except json.JSONDecodeError as e:
        raise ConfigurationError(f"Invalid JSON in {filename}: {e}")


class ValidationConfig:
    """Configuration manager for validation checks and fixes."""

    def __init__(self):
        """Load all configuration files eagerly."""
        # Load configurations from JSON files
        self._validation_rules_raw = _load_json_config("validation_rules.json")
        self._fix_capabilities_raw = _load_json_config("fix_capabilities.json")
        self._naming_conventions_raw = _load_json_config("naming_conventions.json")
        self._knowledge_base_raw = _load_json_config("knowledge_base.json")
        self._generation_contract_raw = _load_json_config("generation_contract.json")
        self._oop_policy_cache: dict[str, dict[str, Any]] = {}

        # Convert to expected format (map check IDs to check objects)
        self.validation_checks = {
            check["id"]: check for check in self._validation_rules_raw["checks"]
        }

        # Map old keys to new IDs for backward compatibility
        self.check_id_map = {
            "xml": "xml_structure",
            "guid_format": "guid_format",
            "guid_unique": "guid_uniqueness",
            "indentation": "indentation",
            "tabs": "tabs",
            "file_ending": "file_ending",
            "var_blocks": "property_var_blocks",
            "lineids": "lineids_count",
            "element_order": "element_ordering",
            "naming": "naming_conventions",
            "cdata": "cdata_formatting",
            "excessive_blanks": "excessive_blank_lines",
            "pou_structure": "pou_structure",
            "main_var_input_mutation": "main_var_input_mutation",
            "unsigned_loop_underflow": "unsigned_loop_underflow",
            "extends_visibility": "extends_visibility",
            "override_marker": "override_marker",
            "override_signature": "override_signature",
            "interface_contract": "interface_contract",
            "extends_cycle": "extends_cycle",
            "override_super_call": "override_super_call",
            "inheritance_property_contract": "inheritance_property_contract",
            "fb_init_signature": "fb_init_signature",
            "fb_init_super_call": "fb_init_super_call",
            "this_pointer_consistency": "this_pointer_consistency",
            "abstract_contract": "abstract_contract",
            "fb_exit_contract": "fb_exit_contract",
            "dynamic_creation_attribute": "dynamic_creation_attribute",
            "pointer_delete_pairing": "pointer_delete_pairing",
            "composition_depth": "composition_depth",
            "interface_segregation": "interface_segregation",
            "method_visibility_consistency": "method_visibility_consistency",
            "diamond_inheritance_warning": "diamond_inheritance_warning",
            "abstract_instantiation": "abstract_instantiation",
            "property_accessor_pairing": "property_accessor_pairing",
            "method_count": "method_count",
        }

        # Convert FIX_CAPABILITIES to dict mapped by fix ID
        self.fix_capabilities = {fix["id"]: fix for fix in self._fix_capabilities_raw["fixes"]}

        # Extract naming conventions (keep structure as-is)
        self.naming_conventions = self._naming_conventions_raw["file_types"]

        # Extract knowledge base (Phase 3)
        self.knowledge_base = self._knowledge_base_raw.get("knowledge_base", {})
        # Extract deterministic generation contracts (Phase 5A)
        self.generation_contract = self._generation_contract_raw.get("file_types", {})
        # Extract OOP policy defaults (Phase 6+)
        self.oop_policy_defaults = self._normalize_oop_policy(
            self._validation_rules_raw.get("oop_policy", {})
        )

        # SERVER_INFO derived from loaded configs
        self.server_info = {
            "name": "twincat-validator",
            "version": "1.0.0",
            "supported_file_types": [".TcPOU", ".TcIO", ".TcDUT", ".TcGVL"],
            "validation_checks": len(self.validation_checks),
            "auto_fix_capabilities": len(self.fix_capabilities),
            "author": "Jaime Calvente Mieres",
            "license": "MIT",
        }

        # Runtime configuration (can be modified via configure_validation tool)
        self.severity_overrides: dict[str, str] = {}
        self.disabled_checks: list[str] = []
        self.custom_naming_patterns: dict[str, Any] = {}

        # Supported extensions
        self.supported_extensions = [".TcPOU", ".TcIO", ".TcDUT", ".TcGVL"]

    @staticmethod
    def _normalize_oop_policy(raw_policy: Any) -> dict[str, Any]:
        """Normalize partial OOP policy dict into full policy object."""
        defaults = {
            # Phase 0 - Existing OOP policy
            "enforce_override_super_call": False,
            "required_super_methods": [],
            "enforce_fb_init_super_call": True,
            "enforce_this_pointer_consistency": True,
            "enforce_interface_contract_integrity": True,
            "allow_abstract_keyword": True,
            # Phase 5A - Critical safety
            "enforce_dynamic_creation_attribute": True,
            "enforce_pointer_delete_pairing": True,
            "enforce_fb_exit_contract": True,
            "cleanup_method_names": ["Dispose", "Cleanup"],
            # Phase 5B - Design quality
            "max_inheritance_depth": 4,
            "max_interface_methods": 7,
            "warn_diamond_inheritance": True,
            # Phase 5C.2 - Method count
            "max_methods_per_pou": 15,
            # Phase 5C.1 - Additional safety
            "allow_readonly_properties": True,
            "allow_writeonly_properties": False,
        }
        if not isinstance(raw_policy, dict):
            return defaults

        normalized = dict(defaults)

        # Phase 0 normalization
        if "enforce_override_super_call" in raw_policy:
            normalized["enforce_override_super_call"] = bool(
                raw_policy["enforce_override_super_call"]
            )
        if "required_super_methods" in raw_policy and isinstance(
            raw_policy["required_super_methods"], list
        ):
            normalized["required_super_methods"] = [
                str(v) for v in raw_policy["required_super_methods"] if str(v).strip()
            ]
        if "enforce_fb_init_super_call" in raw_policy:
            normalized["enforce_fb_init_super_call"] = bool(
                raw_policy["enforce_fb_init_super_call"]
            )
        if "enforce_this_pointer_consistency" in raw_policy:
            normalized["enforce_this_pointer_consistency"] = bool(
                raw_policy["enforce_this_pointer_consistency"]
            )
        if "enforce_interface_contract_integrity" in raw_policy:
            normalized["enforce_interface_contract_integrity"] = bool(
                raw_policy["enforce_interface_contract_integrity"]
            )
        if "allow_abstract_keyword" in raw_policy:
            normalized["allow_abstract_keyword"] = bool(raw_policy["allow_abstract_keyword"])

        # Phase 5A normalization
        if "enforce_dynamic_creation_attribute" in raw_policy:
            normalized["enforce_dynamic_creation_attribute"] = bool(
                raw_policy["enforce_dynamic_creation_attribute"]
            )
        if "enforce_pointer_delete_pairing" in raw_policy:
            normalized["enforce_pointer_delete_pairing"] = bool(
                raw_policy["enforce_pointer_delete_pairing"]
            )
        if "enforce_fb_exit_contract" in raw_policy:
            normalized["enforce_fb_exit_contract"] = bool(raw_policy["enforce_fb_exit_contract"])
        if "cleanup_method_names" in raw_policy and isinstance(
            raw_policy["cleanup_method_names"], list
        ):
            normalized["cleanup_method_names"] = [
                str(v) for v in raw_policy["cleanup_method_names"] if str(v).strip()
            ]

        # Phase 5B normalization
        if "max_inheritance_depth" in raw_policy:
            try:
                depth = int(raw_policy["max_inheritance_depth"])
                if depth > 0:
                    normalized["max_inheritance_depth"] = depth
            except (ValueError, TypeError):
                pass

        if "max_interface_methods" in raw_policy:
            try:
                methods = int(raw_policy["max_interface_methods"])
                if methods > 0:
                    normalized["max_interface_methods"] = methods
            except (ValueError, TypeError):
                pass

        # Phase 5C.2 normalization
        if "max_methods_per_pou" in raw_policy:
            try:
                max_m = int(raw_policy["max_methods_per_pou"])
                if max_m > 0:
                    normalized["max_methods_per_pou"] = max_m
            except (ValueError, TypeError):
                pass

        # Phase 5C.1 - Property accessor policy
        if "allow_readonly_properties" in raw_policy:
            if isinstance(raw_policy["allow_readonly_properties"], bool):
                normalized["allow_readonly_properties"] = raw_policy["allow_readonly_properties"]

        if "allow_writeonly_properties" in raw_policy:
            if isinstance(raw_policy["allow_writeonly_properties"], bool):
                normalized["allow_writeonly_properties"] = raw_policy["allow_writeonly_properties"]

        if "warn_diamond_inheritance" in raw_policy:
            normalized["warn_diamond_inheritance"] = bool(raw_policy["warn_diamond_inheritance"])

        return normalized

    def get_oop_policy(self, file_path: Path | None = None) -> dict[str, Any]:
        """Get OOP policy merged with nearest .twincat-validator.json override.

        Args:
            file_path: Optional file path used to search parent folders for
                project override file.
        """
        return self.resolve_oop_policy(file_path)["policy"]

    def resolve_oop_policy(self, file_path: Path | None = None) -> dict[str, Any]:
        """Resolve effective OOP policy and source metadata.

        Args:
            file_path: Optional file path used to search parent folders for
                project override file.

        Returns:
            Dict with:
            - policy: Effective merged OOP policy
            - source: 'defaults' or absolute path to .twincat-validator.json
        """
        if file_path is None:
            return {"policy": dict(self.oop_policy_defaults), "source": "defaults"}

        try:
            search_dir = file_path.parent
        except Exception:
            return {"policy": dict(self.oop_policy_defaults), "source": "defaults"}

        cache_key = str(search_dir.resolve())
        cached = self._oop_policy_cache.get(cache_key)
        if cached is not None:
            return {"policy": dict(cached["policy"]), "source": str(cached["source"])}

        merged_policy = dict(self.oop_policy_defaults)
        source = "defaults"
        for candidate_dir in [search_dir, *search_dir.parents]:
            candidate = candidate_dir / ".twincat-validator.json"
            if not candidate.exists():
                continue
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            raw_policy = data.get("oop_policy", {})
            merged_policy = self._normalize_oop_policy(raw_policy)
            source = str(candidate.resolve())
            break

        self._oop_policy_cache[cache_key] = {"policy": dict(merged_policy), "source": source}
        return {"policy": dict(merged_policy), "source": source}

    def _locate_policy_file(self, target_path: Path | None = None) -> Path | None:
        """Locate nearest .twincat-validator.json for a target path."""
        if target_path is None:
            start_dir = Path.cwd()
        else:
            start_dir = target_path if target_path.is_dir() else target_path.parent

        for candidate_dir in [start_dir, *start_dir.parents]:
            candidate = candidate_dir / ".twincat-validator.json"
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def _oop_policy_expected_types() -> dict[str, Any]:
        """Return expected types/constraints for known OOP policy keys."""
        return {
            "enforce_override_super_call": bool,
            "required_super_methods": list,
            "enforce_fb_init_super_call": bool,
            "enforce_this_pointer_consistency": bool,
            "enforce_interface_contract_integrity": bool,
            "allow_abstract_keyword": bool,
            "enforce_dynamic_creation_attribute": bool,
            "enforce_pointer_delete_pairing": bool,
            "enforce_fb_exit_contract": bool,
            "cleanup_method_names": list,
            "max_inheritance_depth": int,
            "max_interface_methods": int,
            "warn_diamond_inheritance": bool,
            "max_methods_per_pou": int,
            "allow_readonly_properties": bool,
            "allow_writeonly_properties": bool,
        }

    def lint_oop_policy(
        self,
        target_path: Path | None = None,
        *,
        strict: bool = True,
        policy_file: Path | None = None,
    ) -> dict[str, Any]:
        """Lint .twincat-validator.json OOP policy keys/types and return normalized result."""
        selected_policy_file = policy_file
        if selected_policy_file is None:
            selected_policy_file = self._locate_policy_file(target_path)

        expected_types = self._oop_policy_expected_types()
        known_keys = set(expected_types.keys())
        defaults = dict(self.oop_policy_defaults)

        result: dict[str, Any] = {
            "valid": True,
            "strict": bool(strict),
            "source": "defaults",
            "policy_file": None,
            "recognized_keys": [],
            "unknown_keys": [],
            "type_errors": [],
            "constraint_errors": [],
            "parse_error": None,
            "normalized_policy": defaults,
        }

        if selected_policy_file is None:
            return result

        result["policy_file"] = str(selected_policy_file.resolve())
        result["source"] = str(selected_policy_file.resolve())

        try:
            with open(selected_policy_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            result["valid"] = False
            result["parse_error"] = str(exc)
            if strict:
                return result
            return result

        raw_policy = data.get("oop_policy", {})
        if not isinstance(raw_policy, dict):
            result["valid"] = False
            result["type_errors"].append(
                {"key": "oop_policy", "expected": "object", "actual": type(raw_policy).__name__}
            )
            if strict:
                return result
            raw_policy = {}

        recognized = sorted(k for k in raw_policy.keys() if k in known_keys)
        unknown = sorted(k for k in raw_policy.keys() if k not in known_keys)
        result["recognized_keys"] = recognized
        result["unknown_keys"] = unknown

        type_errors: list[dict[str, str]] = []
        constraint_errors: list[dict[str, str]] = []

        for key in recognized:
            value = raw_policy[key]
            expected = expected_types[key]
            if expected is bool and not isinstance(value, bool):
                type_errors.append({"key": key, "expected": "bool", "actual": type(value).__name__})
                continue
            if expected is int and not isinstance(value, int):
                type_errors.append({"key": key, "expected": "int", "actual": type(value).__name__})
                continue
            if expected is list and not isinstance(value, list):
                type_errors.append({"key": key, "expected": "list", "actual": type(value).__name__})
                continue
            if key in ("required_super_methods", "cleanup_method_names") and isinstance(
                value, list
            ):
                bad_items = [type(v).__name__ for v in value if not isinstance(v, str)]
                if bad_items:
                    type_errors.append(
                        {
                            "key": key,
                            "expected": "list[str]",
                            "actual": f"list[{bad_items[0]}]",
                        }
                    )
            if key in ("max_inheritance_depth", "max_interface_methods", "max_methods_per_pou"):
                if isinstance(value, int) and value <= 0:
                    constraint_errors.append({"key": key, "error": "must be > 0"})

        result["type_errors"] = type_errors
        result["constraint_errors"] = constraint_errors

        # Reuse existing normalization for deterministic effective policy.
        result["normalized_policy"] = self._normalize_oop_policy(raw_policy)

        invalid = bool(unknown or type_errors or constraint_errors or result["parse_error"])
        result["valid"] = not invalid if strict else not bool(result["parse_error"])
        return result

    def get_check_config(self, check_id: str) -> dict[str, Any]:
        """Get configuration for a specific check.

        Args:
            check_id: Check identifier

        Returns:
            Check configuration dict

        Raises:
            KeyError: If check_id not found
        """
        return self.validation_checks[check_id]

    def get_fix_config(self, fix_id: str) -> dict[str, Any]:
        """Get configuration for a specific fix.

        Args:
            fix_id: Fix identifier

        Returns:
            Fix configuration dict

        Raises:
            KeyError: If fix_id not found
        """
        return self.fix_capabilities[fix_id]

    def is_check_disabled(self, check_id: str) -> bool:
        """Check if a validation check is disabled.

        Args:
            check_id: Check identifier

        Returns:
            True if check is disabled
        """
        return check_id in self.disabled_checks

    def get_check_severity(self, check_id: str) -> str:
        """Get severity for a check (respecting overrides).

        Args:
            check_id: Check identifier

        Returns:
            Severity level ('critical', 'error', 'warning', 'info')
        """
        if check_id in self.severity_overrides:
            return self.severity_overrides[check_id]
        return self.validation_checks[check_id]["severity"]

    def get_check_knowledge(self, check_id: str) -> dict[str, Any]:
        """Get knowledge base entry for a check (Phase 3).

        Args:
            check_id: Check identifier

        Returns:
            Knowledge base entry with explanation, examples, common mistakes.
            Empty dict if no knowledge base entry exists.
        """
        return self.knowledge_base.get("checks", {}).get(check_id, {})

    def get_fix_knowledge(self, fix_id: str) -> dict[str, Any]:
        """Get knowledge base entry for a fix (Phase 3).

        Args:
            fix_id: Fix identifier

        Returns:
            Knowledge base entry with explanation, algorithm, before/after.
            Empty dict if no knowledge base entry exists.
        """
        return self.knowledge_base.get("fixes", {}).get(fix_id, {})

    def get_generation_contract(self) -> dict[str, Any]:
        """Get deterministic generation contracts for all supported file types."""
        return self._generation_contract_raw

    def get_file_type_contract(self, file_suffix: str) -> dict[str, Any]:
        """Get deterministic generation contract for a specific file type.

        Args:
            file_suffix: File extension with or without leading dot (e.g. ".TcPOU", "TcPOU")

        Returns:
            Contract dict for the file type, or empty dict when unsupported.
        """
        normalized = file_suffix.strip()
        if not normalized:
            return {}
        if not normalized.startswith("."):
            normalized = f".{normalized}"
        return self.generation_contract.get(normalized, {})


_shared_config: ValidationConfig | None = None


def get_shared_config() -> ValidationConfig:
    """Get process-wide shared ValidationConfig instance.

    Used by server and enrichment-enabled validators so they all read from the
    same runtime configuration object.
    """
    global _shared_config
    if _shared_config is None:
        _shared_config = ValidationConfig()
    return _shared_config
