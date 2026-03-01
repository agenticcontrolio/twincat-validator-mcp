"""Policy context models and resolver helpers.

This module is intentionally independent from MCP tool wiring so it can be
unit-tested without loading the full server stack.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Mapping

from twincat_validator.exceptions import PolicyEnforcementError, PolicyResolutionError

EnforcementMode = Literal["strict", "compat"]


@dataclass(frozen=True)
class ExecutionContext:
    """Resolved policy context attached to OOP-sensitive tool executions."""

    target_path: str
    resolved_target_file: str
    policy_source: str
    effective_oop_policy: dict[str, Any]
    policy_fingerprint: str
    policy_checked: bool
    enforcement_mode: EnforcementMode
    response_version: str


def compute_policy_fingerprint(policy: Mapping[str, Any]) -> str:
    """Compute a deterministic policy fingerprint from canonical JSON."""
    canonical = json.dumps(policy, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def resolve_execution_context(
    target_path: str,
    enforcement_mode: EnforcementMode,
    *,
    resolve_target_path: Callable[[str], Path],
    resolve_policy: Callable[[Path], Mapping[str, Any]],
    response_version: str = "2",
) -> ExecutionContext:
    """Resolve execution context with strict fail-closed semantics by default.

    Args:
        target_path: User-supplied file or directory path.
        enforcement_mode: "strict" or "compat".
        resolve_target_path: Function that maps target_path to policy lookup path.
        resolve_policy: Function that returns dict with keys "source" and "policy".
        response_version: Response schema version identifier.
    """
    if enforcement_mode not in ("strict", "compat"):
        raise PolicyEnforcementError(f"Invalid enforcement mode: {enforcement_mode}")

    raw_target = (target_path or "").strip()
    fallback_target = raw_target or str(Path.cwd() / "__policy_target__.TcPOU")

    try:
        resolved_target = resolve_target_path(target_path)
    except Exception as exc:
        if enforcement_mode == "strict":
            raise PolicyResolutionError(f"Failed to resolve target path: {target_path}") from exc
        return ExecutionContext(
            target_path=raw_target,
            resolved_target_file=fallback_target,
            policy_source="unresolved",
            effective_oop_policy={},
            policy_fingerprint=compute_policy_fingerprint({}),
            policy_checked=False,
            enforcement_mode="compat",
            response_version=response_version,
        )

    try:
        resolved = resolve_policy(resolved_target)
        policy = resolved["policy"]
        source = str(resolved["source"])
        if not isinstance(policy, dict):
            raise TypeError("Resolved policy must be a dict")
    except Exception as exc:
        if enforcement_mode == "strict":
            raise PolicyResolutionError(
                f"Failed to resolve OOP policy for: {resolved_target}"
            ) from exc
        return ExecutionContext(
            target_path=raw_target,
            resolved_target_file=str(resolved_target),
            policy_source="unresolved",
            effective_oop_policy={},
            policy_fingerprint=compute_policy_fingerprint({}),
            policy_checked=False,
            enforcement_mode="compat",
            response_version=response_version,
        )

    return ExecutionContext(
        target_path=raw_target,
        resolved_target_file=str(resolved_target),
        policy_source=source,
        effective_oop_policy=dict(policy),
        policy_fingerprint=compute_policy_fingerprint(policy),
        policy_checked=True,
        enforcement_mode=enforcement_mode,
        response_version=response_version,
    )
