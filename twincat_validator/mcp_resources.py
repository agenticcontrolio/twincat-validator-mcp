"""MCP resource handlers for TwinCAT Validator.

All @mcp.resource(...) functions are defined and registered here.
Resources serve read-only configuration/knowledge data to MCP clients.
"""

import json

from twincat_validator._server_helpers import _resolve_policy_target_path
from twincat_validator.mcp_app import config, mcp


def register_resources() -> None:
    """Register all MCP resource handlers with the mcp instance."""

    @mcp.resource("validation-rules://")
    def get_validation_rules() -> str:
        """Get comprehensive list of all validation rules."""
        return json.dumps(config._validation_rules_raw, indent=2)

    @mcp.resource("fix-capabilities://")
    def get_fix_capabilities() -> str:
        """Get list of all auto-fixable issues and fix descriptions."""
        return json.dumps(config._fix_capabilities_raw, indent=2)

    @mcp.resource("naming-conventions://")
    def get_naming_conventions() -> str:
        """Get TwinCAT naming convention rules."""
        return json.dumps(config._naming_conventions_raw, indent=2)

    @mcp.resource("config://server-info")
    def get_server_info() -> str:
        """Get server information and capabilities."""
        return json.dumps(config.server_info, indent=2)

    @mcp.resource("knowledge-base://")
    def get_knowledge_base() -> str:
        """Get the complete TwinCAT validation knowledge base (Phase 3).

        Returns:
            JSON with explanations, examples, common mistakes, and TwinCAT concepts
        """
        return json.dumps(config._knowledge_base_raw, indent=2)

    @mcp.resource("knowledge-base://checks/{check_id}")
    def get_check_knowledge(check_id: str) -> str:
        """Get knowledge base entry for a specific check (Phase 3).

        Args:
            check_id: Check identifier (e.g., "guid_format", "indentation")

        Returns:
            JSON with explanation, why_it_matters, correct_examples, and common_mistakes
        """
        kb = config.get_check_knowledge(check_id)
        if not kb:
            return json.dumps(
                {
                    "success": False,
                    "error": f"No knowledge base entry for check '{check_id}'",
                    "check_id": check_id,
                },
                indent=2,
            )
        return json.dumps(kb, indent=2)

    @mcp.resource("knowledge-base://fixes/{fix_id}")
    def get_fix_knowledge(fix_id: str) -> str:
        """Get knowledge base entry for a specific fix (Phase 3).

        Args:
            fix_id: Fix identifier (e.g., "tabs", "guid_case")

        Returns:
            JSON with explanation, algorithm, risk_assessment, and before/after examples
        """
        kb = config.get_fix_knowledge(fix_id)
        if not kb:
            return json.dumps(
                {
                    "success": False,
                    "error": f"No knowledge base entry for fix '{fix_id}'",
                    "fix_id": fix_id,
                },
                indent=2,
            )
        return json.dumps(kb, indent=2)

    @mcp.resource("generation-contract://")
    def get_generation_contract_resource() -> str:
        """Get deterministic generation contracts for all supported TwinCAT file types."""
        return json.dumps(config.get_generation_contract(), indent=2)

    @mcp.resource("generation-contract://types/{file_type}")
    def get_generation_contract_by_type(file_type: str) -> str:
        """Get deterministic generation contract for a specific file type.

        Args:
            file_type: File type with or without leading dot (e.g. "TcPOU", ".TcPOU")
        """
        contract = config.get_file_type_contract(file_type)
        if not contract:
            return json.dumps(
                {
                    "success": False,
                    "error": f"No generation contract for file type '{file_type}'",
                    "file_type": file_type,
                    "supported_types": list(config.generation_contract.keys()),
                },
                indent=2,
            )
        return json.dumps(contract, indent=2)

    @mcp.resource("oop-policy://defaults")
    def get_oop_policy_defaults_resource() -> str:
        """Get default OOP validation policy from packaged config."""
        return json.dumps(config.get_oop_policy(), indent=2)

    @mcp.resource("oop-policy://effective/{target_path}")
    def get_effective_oop_policy_resource(target_path: str) -> str:
        """Get effective OOP policy for a file/directory target.

        For paths containing separators, prefer the get_effective_oop_policy tool.
        """
        policy_target = _resolve_policy_target_path(target_path)
        resolved = config.resolve_oop_policy(policy_target)
        return json.dumps(
            {
                "target_path": str(policy_target),
                "policy_source": resolved["source"],
                "policy": resolved["policy"],
            },
            indent=2,
        )
