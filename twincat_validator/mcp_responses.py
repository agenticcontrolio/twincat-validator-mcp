"""MCP response envelope helpers.

Provides the standard JSON envelope construction for all MCP tool responses:
- _tool_error: consistent error response
- _now_iso_utc: UTC timestamp string
- _build_meta: standard meta dict
- _with_meta: serialize payload dict with meta appended
- with_policy_proof: inject policy-enforcement proof fields
"""

import json
import time
from datetime import datetime
from typing import Optional

from twincat_validator.mcp_app import POLICY_RESPONSE_VERSION, SERVER_INFO
from twincat_validator.policy_context import ExecutionContext


def _tool_error(
    message: str,
    file_path: Optional[str] = None,
    start_time: Optional[float] = None,
    execution_context: Optional[ExecutionContext] = None,
    **extra: object,
) -> str:
    """Return a JSON-serialised error envelope with a consistent contract.

    Every MCP tool error response must use this helper so callers can rely on
    a single, predictable shape:  {"success": false, "error": "...", ["file_path": "..."]}
    When start_time is provided, a meta envelope is included.
    """
    payload: dict[str, object] = {"success": False, "error": message}
    if file_path is not None:
        payload["file_path"] = file_path
    payload.update(extra)
    if execution_context is not None:
        payload = with_policy_proof(payload, execution_context)
    if start_time is not None:
        payload["meta"] = _build_meta(start_time)
    return json.dumps(payload)


def _now_iso_utc() -> str:
    """Return current UTC time as ISO-8601 string (e.g. '2026-02-21T12:34:56Z')."""
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_meta(start_time: float) -> dict[str, object]:
    """Build the standard meta envelope dict from a monotonic start time."""
    return {
        "timestamp": _now_iso_utc(),
        "duration_ms": round((time.monotonic() - start_time) * 1000),
        "server_version": SERVER_INFO.get("version", "1.0.0"),
        "response_version": "1",
    }


def with_policy_proof(payload: dict[str, object], ctx: ExecutionContext) -> dict[str, object]:
    """Attach policy-enforcement proof fields to a response payload."""
    payload["policy_checked"] = bool(ctx.policy_checked)
    payload["policy_source"] = ctx.policy_source
    payload["policy_fingerprint"] = ctx.policy_fingerprint
    payload["enforcement_mode"] = ctx.enforcement_mode
    payload["response_version"] = POLICY_RESPONSE_VERSION
    if ctx.enforcement_mode == "compat":
        payload["compat_warning"] = (
            "compat mode enabled: policy enforcement may use fallback behavior; "
            "strict mode is recommended for publish-grade validation."
        )
    return payload


def unresolved_policy_fields(enforcement_mode: str) -> dict[str, object]:
    """Return standard policy fields for fail-closed resolution errors."""
    return {
        "policy_checked": False,
        "enforcement_mode": enforcement_mode,
        "response_version": POLICY_RESPONSE_VERSION,
    }


def _with_meta(
    payload: dict[str, object],
    start_time: float,
    execution_context: Optional[ExecutionContext] = None,
) -> str:
    """Serialize payload dict to JSON with a meta envelope appended."""
    if execution_context is not None:
        payload = with_policy_proof(payload, execution_context)
    payload["meta"] = _build_meta(start_time)
    return json.dumps(payload, indent=2)
