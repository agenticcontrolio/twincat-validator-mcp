"""Tests for policy-proof response helpers."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from twincat_validator.mcp_responses import _tool_error, _with_meta, with_policy_proof
from twincat_validator.policy_context import ExecutionContext


def _sample_context() -> ExecutionContext:
    return ExecutionContext(
        target_path="",
        resolved_target_file="/tmp/__policy_target__.TcPOU",
        policy_source="defaults",
        effective_oop_policy={"enforce_override_super_call": True},
        policy_fingerprint="sha256:1234",
        policy_checked=True,
        enforcement_mode="strict",
        response_version="2",
    )


def test_with_policy_proof_adds_expected_fields():
    payload = {"success": True}
    result = with_policy_proof(payload, _sample_context())

    assert result["policy_checked"] is True
    assert result["policy_source"] == "defaults"
    assert result["policy_fingerprint"] == "sha256:1234"
    assert result["enforcement_mode"] == "strict"
    assert result["response_version"] == "2"


def test_tool_error_includes_policy_fields_when_context_provided():
    raw = _tool_error("boom", execution_context=_sample_context())
    data = json.loads(raw)

    assert data["success"] is False
    assert data["error"] == "boom"
    assert data["policy_checked"] is True
    assert data["response_version"] == "2"


def test_with_meta_includes_policy_fields_when_context_provided():
    raw = _with_meta({"success": True}, start_time=0.0, execution_context=_sample_context())
    data = json.loads(raw)

    assert data["success"] is True
    assert data["policy_source"] == "defaults"
    assert "meta" in data
    assert data["meta"]["response_version"] == "1"


def test_with_policy_proof_adds_compat_warning():
    ctx = ExecutionContext(
        target_path="",
        resolved_target_file="/tmp/__policy_target__.TcPOU",
        policy_source="unresolved",
        effective_oop_policy={},
        policy_fingerprint="sha256:abcd",
        policy_checked=False,
        enforcement_mode="compat",
        response_version="2",
    )
    payload = with_policy_proof({"success": True}, ctx)
    assert payload["enforcement_mode"] == "compat"
    assert "compat_warning" in payload
