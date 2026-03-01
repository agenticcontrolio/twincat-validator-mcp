"""Tests for policy execution context resolution."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from twincat_validator.exceptions import PolicyEnforcementError, PolicyResolutionError
from twincat_validator.policy_context import resolve_execution_context


def test_resolve_execution_context_strict_success():
    """Strict mode should resolve policy and mark policy_checked=true."""

    def _resolve_target(_: str) -> Path:
        return Path("/tmp/project/__policy_target__.TcPOU")

    def _resolve_policy(_: Path) -> dict:
        return {
            "source": "defaults",
            "policy": {
                "enforce_override_super_call": True,
                "required_super_methods": ["M_Start", "M_Stop"],
            },
        }

    ctx = resolve_execution_context(
        target_path="",
        enforcement_mode="strict",
        resolve_target_path=_resolve_target,
        resolve_policy=_resolve_policy,
    )

    assert ctx.policy_checked is True
    assert ctx.policy_source == "defaults"
    assert ctx.enforcement_mode == "strict"
    assert ctx.response_version == "2"
    assert ctx.policy_fingerprint.startswith("sha256:")


def test_resolve_execution_context_strict_fails_closed_on_resolution_error():
    """Strict mode must fail closed when target resolution fails."""

    def _resolve_target(_: str) -> Path:
        raise FileNotFoundError("missing")

    with pytest.raises(PolicyResolutionError):
        resolve_execution_context(
            target_path="/missing/path",
            enforcement_mode="strict",
            resolve_target_path=_resolve_target,
            resolve_policy=lambda _p: {"source": "defaults", "policy": {}},
        )


def test_resolve_execution_context_compat_falls_back_when_policy_resolution_fails():
    """Compat mode may return unresolved context instead of raising."""

    def _resolve_target(_: str) -> Path:
        return Path("/tmp/project/__policy_target__.TcPOU")

    def _resolve_policy(_: Path) -> dict:
        raise RuntimeError("bad config")

    ctx = resolve_execution_context(
        target_path="/tmp/project",
        enforcement_mode="compat",
        resolve_target_path=_resolve_target,
        resolve_policy=_resolve_policy,
    )

    assert ctx.policy_checked is False
    assert ctx.policy_source == "unresolved"
    assert ctx.enforcement_mode == "compat"
    assert ctx.effective_oop_policy == {}


def test_resolve_execution_context_rejects_invalid_mode():
    """Unknown enforcement modes should fail fast."""
    with pytest.raises(PolicyEnforcementError):
        resolve_execution_context(
            target_path="",
            enforcement_mode="invalid",  # type: ignore[arg-type]
            resolve_target_path=lambda _t: Path("/tmp/x.TcPOU"),
            resolve_policy=lambda _p: {"source": "defaults", "policy": {}},
        )
