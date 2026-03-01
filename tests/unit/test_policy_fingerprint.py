"""Tests for policy fingerprint determinism."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from twincat_validator.policy_context import compute_policy_fingerprint


def test_policy_fingerprint_is_order_independent():
    """Equivalent dicts with different key order should hash identically."""
    policy_a = {
        "enforce_override_super_call": True,
        "required_super_methods": ["M_Start", "M_Stop"],
        "nested": {"b": 2, "a": 1},
    }
    policy_b = {
        "nested": {"a": 1, "b": 2},
        "required_super_methods": ["M_Start", "M_Stop"],
        "enforce_override_super_call": True,
    }

    assert compute_policy_fingerprint(policy_a) == compute_policy_fingerprint(policy_b)


def test_policy_fingerprint_changes_when_policy_changes():
    """Any material policy change should produce a different fingerprint."""
    base = {"enforce_override_super_call": True, "max_interface_methods": 7}
    changed = {"enforce_override_super_call": False, "max_interface_methods": 7}

    assert compute_policy_fingerprint(base) != compute_policy_fingerprint(changed)
