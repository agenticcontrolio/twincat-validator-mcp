"""Canonical contract state derivation — single source of truth for safe flags.

All MCP tool handlers must derive safe_to_import, safe_to_compile, done, status,
blocking_count and blockers via derive_contract_state() instead of computing them
locally.  This ensures consistent safe-flag semantics across all tools.

Canonical definitions:
    error_count     = count(issues where severity in {"error", "critical"})
    safe_to_import  = (error_count == 0)
    safe_to_compile = (error_count == 0)   # warnings do NOT block compilation
    blocking_count  = count(unfixable issues where severity in {"error", "critical"})
    done            = safe_to_import and safe_to_compile and blocking_count == 0
    status          = "done" if done else "blocked"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Severity levels that count as errors (must mirror mcp_app.ERROR_SEVERITIES).
# Defined here to avoid a circular import with mcp_app.
_ERROR_SEVERITIES: frozenset[str] = frozenset({"error", "critical"})


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ContractState:
    """Immutable snapshot of canonical safety contract state for a file or batch."""

    error_count: int
    warning_count: int
    safe_to_import: bool
    safe_to_compile: bool
    blocking_count: int
    blockers: list[dict[str, Any]] = field(default_factory=list)
    done: bool = False
    status: str = "blocked"

    def __post_init__(self) -> None:
        if self.status not in ("done", "blocked"):
            raise ValueError(
                f"ContractState.status must be 'done' or 'blocked', got {self.status!r}"
            )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _issue_severity(issue: Any) -> str:
    """Extract severity from either a ValidationIssue object or a dict."""
    if isinstance(issue, dict):
        return str(issue.get("severity", ""))
    return str(getattr(issue, "severity", ""))


def _issue_fix_available(issue: Any) -> bool:
    """Extract fix_available from either a ValidationIssue object or a dict.

    Dicts may use "fix_available" (full profile) or "fixable" / "auto_fixable"
    (llm_strict profile).  We accept all three keys.
    """
    if isinstance(issue, dict):
        # Prefer the canonical key; fall back to legacy short keys.
        for key in ("fix_available", "auto_fixable", "fixable"):
            if key in issue:
                return bool(issue[key])
        return False
    return bool(getattr(issue, "fix_available", False))


def _issue_to_dict(issue: Any, profile: str) -> dict[str, Any]:
    """Convert a ValidationIssue object or dict to a blocker dict."""
    if isinstance(issue, dict):
        return issue
    # ValidationIssue has a to_dict() method
    if hasattr(issue, "to_dict"):
        return issue.to_dict(profile=profile)
    return {"message": str(issue)}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def derive_contract_state(
    issues: list[Any],
    *,
    extra_blockers: list[dict[str, Any]] | None = None,
    stable: bool = True,
    require_stable: bool = False,
    profile: str = "full",
) -> ContractState:
    """Compute canonical contract state from a list of validation issues.

    Args:
        issues: List of ValidationIssue objects or dicts.  Both are accepted
            so callers that work with already-serialised issue dicts (e.g.
            mcp_tools_batch) can use the same function.
        extra_blockers: Pre-built blocker dicts to append to the blockers list
            (e.g. GUID sanity violations, generation-contract violations).
            These always force safe_to_import=safe_to_compile=False when present.
        stable: Content-stability flag used only when require_stable=True.
            Defaults to True so single-file callers can ignore it.
        require_stable: If True, done also requires stable=True.  Set this
            when calling from verify_determinism_batch (RC-2 fix).
        profile: Output profile passed through to ValidationIssue.to_dict().

    Returns:
        ContractState with all canonical fields populated.
    """
    error_count = 0
    warning_count = 0
    blockers: list[dict[str, Any]] = []

    for issue in issues:
        sev = _issue_severity(issue)
        if sev in _ERROR_SEVERITIES:
            error_count += 1
            if not _issue_fix_available(issue):
                blockers.append(_issue_to_dict(issue, profile))
        elif sev == "warning":
            warning_count += 1

    # Append pre-built sanity / contract blockers (always unfixable by definition).
    if extra_blockers:
        blockers.extend(extra_blockers)
        # Sanity blockers indicate the file is broken regardless of issue list.
        error_count = max(error_count, len(extra_blockers))

    safe_to_import = error_count == 0
    safe_to_compile = error_count == 0  # warnings do NOT block compilation

    blocking_count = len(blockers)
    done = safe_to_import and safe_to_compile and blocking_count == 0
    if require_stable:
        done = done and stable

    status = "done" if done else "blocked"

    return ContractState(
        error_count=error_count,
        warning_count=warning_count,
        safe_to_import=safe_to_import,
        safe_to_compile=safe_to_compile,
        blocking_count=blocking_count,
        blockers=blockers,
        done=done,
        status=status,
    )


def aggregate_batch_contract(
    per_file_states: list[ContractState],
    *,
    failed_files_count: int = 0,
) -> ContractState:
    """Aggregate multiple per-file ContractStates into one batch-level state.

    Args:
        per_file_states: ContractState for each successfully processed file.
        failed_files_count: Number of files that failed to process entirely
            (e.g. XML parse errors before validation could run).

    Returns:
        Aggregated ContractState where safe flags are AND of all per-file flags.
    """
    if not per_file_states and failed_files_count == 0:
        # Empty batch — treat as done with no issues.
        return ContractState(
            error_count=0,
            warning_count=0,
            safe_to_import=False,
            safe_to_compile=False,
            blocking_count=0,
            blockers=[],
            done=False,
            status="blocked",
        )

    error_count = sum(s.error_count for s in per_file_states)
    warning_count = sum(s.warning_count for s in per_file_states)
    all_blockers: list[dict[str, Any]] = []
    for s in per_file_states:
        all_blockers.extend(s.blockers)

    safe_to_import = failed_files_count == 0 and all(s.safe_to_import for s in per_file_states)
    safe_to_compile = failed_files_count == 0 and all(s.safe_to_compile for s in per_file_states)
    blocking_count = len(all_blockers)
    done = safe_to_import and safe_to_compile and blocking_count == 0
    status = "done" if done else "blocked"

    return ContractState(
        error_count=error_count,
        warning_count=warning_count,
        safe_to_import=safe_to_import,
        safe_to_compile=safe_to_compile,
        blocking_count=blocking_count,
        blockers=all_blockers,
        done=done,
        status=status,
    )
