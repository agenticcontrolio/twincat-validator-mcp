"""Tests for orchestration MCP tools (single and batch pipelines)."""

import json
import pytest

from server import (
    process_twincat_single,
    process_twincat_batch,
    validate_batch,
    verify_determinism_batch,
)


def _write_valid_fb(path):
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <POU Name="FB_Test" Id="{abcd1234-5678-90ab-cdef-1234567890ab}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR]]></Declaration>\n"
        "    <Implementation>\n"
        "      <ST><![CDATA[]]></ST>\n"
        "    </Implementation>\n"
        '    <LineIds Name="FB_Test">\n'
        '      <LineId Id="1" Count="0" />\n'
        "    </LineIds>\n"
        "  </POU>\n"
        "</TcPlcObject>\n",
        encoding="utf-8",
    )


def test_process_twincat_single_pipeline(tmp_path):
    """Single-file orchestration should run validate->autofix->validate."""
    file_path = tmp_path / "FB_Test.TcPOU"
    _write_valid_fb(file_path)

    result = json.loads(process_twincat_single(str(file_path)))

    assert result["success"] is True
    assert result["workflow"] == "single_strict_pipeline"
    assert result["tools_used"][:3] == ["validate_file", "autofix_file", "validate_file"]
    assert "pre_validation" in result
    assert "autofix" in result
    assert "post_validation" in result
    assert isinstance(result["safe_to_import"], bool)
    assert isinstance(result["safe_to_compile"], bool)
    assert isinstance(result["done"], bool)
    assert "effective_oop_policy" in result
    assert "policy_source" in result["effective_oop_policy"]
    assert "policy" in result["effective_oop_policy"]
    assert "policy_checked" in result
    assert "policy_source" in result
    assert "policy_fingerprint" in result
    assert result["enforcement_mode"] == "strict"
    assert result["response_version"] == "2"
    if result["done"]:
        assert result["terminal_mode"] is True
        assert result["next_action"] == "done_no_further_autofix"
        assert result["allow_followup_autofix_without_user_request"] is False


def test_process_twincat_single_reports_unsafe_with_malformed_guid(tmp_path):
    """Single-file orchestration should fail closed on malformed GUID tokens."""
    file_path = tmp_path / "ST_Bad.TcDUT"
    file_path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <DUT Name="ST_Bad" Id="{e6f7a8b9-ca db-4cee-e05b-6c7d8e9fa6b7}">\n'
        "    <Declaration><![CDATA[TYPE ST_Bad : STRUCT\n"
        "nVal : INT;\n"
        "END_STRUCT\n"
        "END_TYPE]]></Declaration>\n"
        "  </DUT>\n"
        "</TcPlcObject>\n",
        encoding="utf-8",
    )

    result = json.loads(process_twincat_single(str(file_path)))

    assert result["success"] is True
    assert result["done"] is False
    assert result["safe_to_import"] is False
    assert result["safe_to_compile"] is False
    assert "suggested_fixes" in result


async def test_process_twincat_batch_pipeline(tmp_path):
    """Batch orchestration should run validate_batch->autofix_batch->validate_batch."""
    _write_valid_fb(tmp_path / "FB_A.TcPOU")
    _write_valid_fb(tmp_path / "FB_B.TcPOU")

    # Use full mode to verify all detail sections are available.
    result = json.loads(
        await process_twincat_batch(
            file_patterns=["*.TcPOU"],
            directory_path=str(tmp_path),
            response_mode="full",
        )
    )

    assert result["success"] is True
    assert result["workflow"] == "batch_strict_pipeline"
    assert result["tools_used"] == ["validate_batch", "autofix_batch", "validate_batch"]
    assert "pre_validation" in result
    assert "autofix" in result
    assert "post_validation" in result
    assert isinstance(result["done"], bool)
    assert "terminal_mode" in result
    assert "next_action" in result
    assert "effective_oop_policy" in result
    assert "policy_source" in result["effective_oop_policy"]
    assert "policy" in result["effective_oop_policy"]
    assert "policy_checked" in result
    assert "policy_source" in result
    assert "policy_fingerprint" in result
    assert result["enforcement_mode"] == "strict"
    assert result["response_version"] == "2"
    if result["done"]:
        assert result["terminal_mode"] is True
        assert result["next_action"] == "done_no_further_autofix"
        assert result["allow_followup_autofix_without_user_request"] is False


@pytest.mark.asyncio
async def test_validate_batch_includes_flat_safety_fields(tmp_path):
    _write_valid_fb(tmp_path / "FB_A.TcPOU")
    result = json.loads(
        await validate_batch(file_patterns=["*.TcPOU"], directory_path=str(tmp_path))
    )
    assert result["success"] is True
    assert "files" in result
    assert len(result["files"]) == 1
    item = result["files"][0]
    assert "safe_to_import" in item
    assert "safe_to_compile" in item
    assert "blocking_count" in item
    assert "blockers" in item


@pytest.mark.asyncio
async def test_verify_determinism_batch_contract(tmp_path):
    _write_valid_fb(tmp_path / "FB_A.TcPOU")
    _write_valid_fb(tmp_path / "FB_B.TcPOU")
    result = json.loads(
        await verify_determinism_batch(file_patterns=["*.TcPOU"], directory_path=str(tmp_path))
    )
    assert result["success"] is True
    assert result["workflow"] == "determinism_batch"
    assert result["tools_used"] == ["process_twincat_batch", "process_twincat_batch"]
    assert "files" in result
    assert "stable" in result
    assert "first_pass_summary" in result
    assert "second_pass_summary" in result
    for item in result["files"]:
        assert "content_changed_first_pass" in item
        assert "content_changed_second_pass" in item
        assert "stable" in item


def test_process_twincat_single_compat_mode_emits_warning(tmp_path):
    file_path = tmp_path / "FB_Test.TcPOU"
    _write_valid_fb(file_path)

    result = json.loads(process_twincat_single(str(file_path), enforcement_mode="compat"))
    assert result["success"] is True
    assert result["enforcement_mode"] == "compat"
    assert "compat_warning" in result


@pytest.mark.asyncio
async def test_process_twincat_batch_invalid_enforcement_mode_returns_error(tmp_path):
    _write_valid_fb(tmp_path / "FB_A.TcPOU")
    result = json.loads(
        await process_twincat_batch(
            file_patterns=["*.TcPOU"],
            directory_path=str(tmp_path),
            enforcement_mode="invalid_mode",
        )
    )
    assert result["success"] is False
    assert result["policy_checked"] is False
    assert "valid_enforcement_modes" in result
