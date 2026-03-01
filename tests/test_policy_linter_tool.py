"""Contract tests for lint_oop_policy MCP tool."""

import json

from server import lint_oop_policy


def test_lint_oop_policy_defaults_when_no_policy_file(tmp_path):
    result = json.loads(lint_oop_policy(str(tmp_path), strict=True))
    assert result["success"] is True
    assert result["valid"] is True
    assert result["source"] == "defaults"
    assert result["policy_file"] is None
    assert result["unknown_keys"] == []
    assert result["type_errors"] == []
    assert isinstance(result["normalized_policy"], dict)


def test_lint_oop_policy_detects_unknown_and_type_errors_strict(tmp_path):
    (tmp_path / ".twincat-validator.json").write_text(
        (
            "{\n"
            '  "oop_policy": {\n'
            '    "enforce_override_super_call": "true",\n'
            '    "required_super_methods": ["M_Start"],\n'
            '    "not_a_real_key": 123\n'
            "  }\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    result = json.loads(lint_oop_policy(str(tmp_path), strict=True))
    assert result["success"] is True
    assert result["valid"] is False
    assert "not_a_real_key" in result["unknown_keys"]
    assert any(err["key"] == "enforce_override_super_call" for err in result["type_errors"])
    assert result["policy_file"] is not None


def test_lint_oop_policy_non_strict_reports_but_stays_valid(tmp_path):
    (tmp_path / ".twincat-validator.json").write_text(
        (
            "{\n"
            '  "oop_policy": {\n'
            '    "required_super_methods": ["M_Start"],\n'
            '    "bad_key": true\n'
            "  }\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    result = json.loads(lint_oop_policy(str(tmp_path), strict=False))
    assert result["success"] is True
    assert result["valid"] is True
    assert "bad_key" in result["unknown_keys"]
    assert result["parse_error"] is None
