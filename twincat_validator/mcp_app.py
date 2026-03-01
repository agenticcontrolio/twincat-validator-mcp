"""MCP application instance and shared server state.

This module creates the FastMCP instance and initializes all shared objects
(config, validation engine, fix engine) that tool and resource modules import.

Import order:
    mcp_app  ← no dependencies on other mcp_* modules
    mcp_responses  ← no dependencies on other mcp_* modules
    mcp_tools_*  ← depend on mcp_app and mcp_responses
    mcp_resources  ← depend on mcp_app
    server  ← facade, imports all of the above
"""

from mcp.server.fastmcp import FastMCP

from twincat_validator import ValidationEngine, FixEngine, TwinCATFile, CheckRegistry  # noqa: F401
from twincat_validator.config_loader import get_shared_config
from twincat_validator.exceptions import (  # noqa: F401
    UnsupportedFileTypeError,
    ConfigurationError,
    CheckNotFoundError,
)

# ============================================================================
# MCP SERVER INSTANCE
# ============================================================================

mcp = FastMCP("TwinCAT Validator", dependencies=[])

# Register MCP prompts (workflow templates for LLM clients)
from twincat_validator.prompts import register_prompts  # noqa: E402

register_prompts(mcp)

# ============================================================================
# SHARED STATE
# ============================================================================

# Initialize configuration and engines at module level (singleton pattern)
config = get_shared_config()
validation_engine = ValidationEngine(config)
fix_engine = FixEngine(config)

# ============================================================================
# CONSTANTS
# ============================================================================

VALIDATION_CHECKS = config.validation_checks
FIX_CAPABILITIES = config.fix_capabilities
NAMING_CONVENTIONS = config.naming_conventions
SERVER_INFO = config.server_info
VALID_PROFILES = ("full", "llm_strict")
VALID_FORMAT_PROFILES = ("default", "twincat_canonical")
ERROR_SEVERITIES = ("error", "critical")
SUPPORTED_POU_SUBTYPES = ("function_block", "function", "program")
DEFAULT_ENFORCEMENT_MODE = "strict"
POLICY_RESPONSE_VERSION = "2"

# Best-effort in-memory loop guard state for orchestration hints.
_LOOP_GUARD_STATE: dict[str, dict[str, object]] = {}
