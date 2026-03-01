#!/usr/bin/env python3
"""
TwinCAT Validator MCP Server — thin facade.

The real implementation lives in the sub-modules:
- mcp_app.py          — FastMCP instance, config, engines, constants
- mcp_responses.py    — response envelope helpers
- _server_helpers.py  — all private helper functions
- mcp_resources.py    — @mcp.resource handlers
- mcp_tools_validation.py — validate_file, validate_for_import, check_specific,
                              get_validation_summary, suggest_fixes
- mcp_tools_fix.py    — autofix_file, generate_skeleton, extract_methods_to_xml
- mcp_tools_batch.py  — validate_batch, autofix_batch
- mcp_tools_orchestration.py — process_twincat_single, process_twincat_batch,
                                verify_determinism_batch,
                                get_effective_oop_policy, lint_oop_policy

This facade re-registers all tools/resources by calling the register_*()
functions, then re-exports all public names so that:
  from twincat_validator.server import autofix_file
  from server import autofix_file
both continue to work.

MCP Tools:
- validate_file, autofix_file, validate_batch, autofix_batch
- process_twincat_single, process_twincat_batch, verify_determinism_batch
- get_effective_oop_policy, lint_oop_policy
- check_specific, validate_for_import, get_validation_summary
- suggest_fixes, generate_skeleton, extract_methods_to_xml
- get_effective_oop_policy
- lint_oop_policy

MCP Resources:
- validation-rules://, fix-capabilities://, naming-conventions://
- config://server-info, knowledge-base://, knowledge-base://checks/{check_id}
- knowledge-base://fixes/{fix_id}, generation-contract://
- generation-contract://types/{file_type}
- oop-policy://defaults, oop-policy://effective/{target_path}

Author: Jaime Calvente Mieres
License: MIT
Version: 1.0.0
"""

# ============================================================================
# SHARED STATE / CONSTANTS — re-exported for backward compatibility
# ============================================================================

from twincat_validator.mcp_app import (  # noqa: F401
    FIX_CAPABILITIES,
    NAMING_CONVENTIONS,
    SERVER_INFO,
    SUPPORTED_POU_SUBTYPES,
    VALID_FORMAT_PROFILES,
    VALID_PROFILES,
    VALIDATION_CHECKS,
    _LOOP_GUARD_STATE,
    config,
    fix_engine,
    mcp,
    validation_engine,
)

# ============================================================================
# RESPONSE HELPERS — re-exported for backward compatibility
# ============================================================================

from twincat_validator.mcp_responses import (  # noqa: F401
    _build_meta,
    _now_iso_utc,
    _tool_error,
    _with_meta,
)

# ============================================================================
# PRIVATE HELPERS — re-exported so tests / resources can import from server
# ============================================================================

from twincat_validator._server_helpers import (  # noqa: F401
    _artifact_sanity_violations,
    _build_contract_skeleton,
    _build_interface_skeleton,
    _build_interface_with_methods,
    _build_named_fb_skeleton,
    _build_pou_skeleton,
    _canonicalize_getter_declarations,
    _canonicalize_ids,
    _canonicalize_tcdut_layout,
    _canonicalize_tcio_layout,
    _canonicalize_tcpou_method_layout,
    _check_generation_contract,
    _compute_issue_fingerprint,
    _contract_element_has_attributes,
    _convert_engine_result_to_mcp_format,
    _count_invalid_guid_tokens,
    _create_missing_implicit_files,
    _derive_next_action,
    _deterministic_guid,
    _engine_issues_to_records,
    _ensure_tcplcobject_attrs,
    _extract_extended_base,
    _extract_implemented_interfaces,
    _extract_inline_methods_from_st,
    _extract_method_declarations_for_interface,
    _extract_structs_to_dut_files,
    _normalize_file_type,
    _normalize_interface_inline_methods,
    _normalize_line_endings_and_trailing_ws,
    _promote_inline_methods_to_xml,
    _rebuild_pou_lineids,
    _resolve_policy_target_path,
    _rewrite_id_attr_in_tag,
    _sha256_text,
    _to_pascal_case,
    _update_no_progress_count,
    _validate_file_path,
    _validate_format_profile,
    _validate_profile,
)

# ============================================================================
# REGISTER ALL RESOURCES AND TOOLS
# ============================================================================

from twincat_validator.mcp_resources import register_resources
from twincat_validator.mcp_tools_validation import register_validation_tools
from twincat_validator.mcp_tools_fix import register_fix_tools
from twincat_validator.mcp_tools_batch import register_batch_tools
from twincat_validator.mcp_tools_orchestration import register_orchestration_tools

register_resources()
register_validation_tools()
register_fix_tools()
register_batch_tools()
register_orchestration_tools()

# ============================================================================
# RE-EXPORT REGISTERED TOOL CALLABLES
# ============================================================================
# FastMCP stores tool functions in mcp._tool_manager; to allow callers to do:
#   from twincat_validator.server import autofix_file
# we retrieve the underlying Python function objects from the registered tools.


def _get_tool_fn(name: str):
    """Retrieve the raw Python callable for a registered MCP tool by name."""
    tools = mcp._tool_manager._tools  # type: ignore[attr-defined]
    return tools[name].fn


autofix_file = _get_tool_fn("autofix_file")
validate_file = _get_tool_fn("validate_file")
validate_for_import = _get_tool_fn("validate_for_import")
check_specific = _get_tool_fn("check_specific")
get_validation_summary = _get_tool_fn("get_validation_summary")
suggest_fixes = _get_tool_fn("suggest_fixes")
generate_skeleton = _get_tool_fn("generate_skeleton")
extract_methods_to_xml = _get_tool_fn("extract_methods_to_xml")
validate_batch = _get_tool_fn("validate_batch")
autofix_batch = _get_tool_fn("autofix_batch")
process_twincat_single = _get_tool_fn("process_twincat_single")
process_twincat_batch = _get_tool_fn("process_twincat_batch")
verify_determinism_batch = _get_tool_fn("verify_determinism_batch")
get_effective_oop_policy = _get_tool_fn("get_effective_oop_policy")
lint_oop_policy = _get_tool_fn("lint_oop_policy")
get_context_pack = _get_tool_fn("get_context_pack")


def _get_resource_fn(uri: str):
    """Retrieve the raw Python callable for a registered MCP resource by URI."""
    resources = mcp._resource_manager._resources  # type: ignore[attr-defined]
    return resources[uri].fn


def _get_template_fn(uri_template: str):
    """Retrieve the raw Python callable for a registered MCP resource template by URI template."""
    templates = mcp._resource_manager._templates  # type: ignore[attr-defined]
    return templates[uri_template].fn


get_validation_rules = _get_resource_fn("validation-rules://")
get_fix_capabilities = _get_resource_fn("fix-capabilities://")
get_naming_conventions = _get_resource_fn("naming-conventions://")
get_server_info = _get_resource_fn("config://server-info")
get_knowledge_base = _get_resource_fn("knowledge-base://")
get_generation_contract_resource = _get_resource_fn("generation-contract://")
get_oop_policy_defaults_resource = _get_resource_fn("oop-policy://defaults")
get_check_knowledge = _get_template_fn("knowledge-base://checks/{check_id}")
get_fix_knowledge = _get_template_fn("knowledge-base://fixes/{fix_id}")
get_generation_contract_by_type = _get_template_fn("generation-contract://types/{file_type}")
get_effective_oop_policy_resource = _get_template_fn("oop-policy://effective/{target_path}")

# ============================================================================
# SERVER STARTUP
# ============================================================================


def main():
    """Entry point for console script and python -m invocation."""
    import logging

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)
    logger.info(f"Starting {config.server_info['name']} v{config.server_info['version']}")
    logger.info(f"Supported file types: {', '.join(config.server_info['supported_file_types'])}")
    logger.info(f"Validation checks: {config.server_info['validation_checks']}")
    logger.info(f"Auto-fix capabilities: {config.server_info['auto_fix_capabilities']}")
    logger.info("Server ready to accept connections")

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
