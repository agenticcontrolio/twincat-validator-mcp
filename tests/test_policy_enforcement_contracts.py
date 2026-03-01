"""Contract tests for policy-proof fields on OOP-sensitive MCP tools."""

import json
import pytest

from server import (
    autofix_batch,
    autofix_file,
    check_specific,
    generate_skeleton,
    process_twincat_batch,
    process_twincat_single,
    validate_batch,
    validate_file,
    validate_for_import,
)


REQUIRED_POLICY_FIELDS = {
    "policy_checked",
    "policy_source",
    "policy_fingerprint",
    "enforcement_mode",
    "response_version",
}


def _assert_policy_fields(payload: dict) -> None:
    missing = REQUIRED_POLICY_FIELDS - set(payload.keys())
    assert not missing, f"Missing policy-proof fields: {sorted(missing)}"


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


def test_validate_file_success_has_policy_proof(tmp_path):
    target = tmp_path / "FB_Test.TcPOU"
    _write_valid_fb(target)
    result = json.loads(validate_file(str(target), profile="llm_strict"))
    assert result["success"] is True
    _assert_policy_fields(result)


def test_validate_file_error_has_policy_proof():
    result = json.loads(validate_file("C:/does/not/exist/FB_X.TcPOU", profile="llm_strict"))
    assert result["success"] is False
    _assert_policy_fields(result)


def test_enforcement_mode_compat_is_explicit_and_emits_warning(tmp_path):
    target = tmp_path / "FB_Test.TcPOU"
    _write_valid_fb(target)
    result = json.loads(validate_file(str(target), profile="llm_strict", enforcement_mode="compat"))
    assert result["success"] is True
    assert result["enforcement_mode"] == "compat"
    assert "compat_warning" in result


def test_invalid_enforcement_mode_returns_structured_error(tmp_path):
    target = tmp_path / "FB_Test.TcPOU"
    _write_valid_fb(target)
    result = json.loads(
        validate_file(str(target), profile="llm_strict", enforcement_mode="invalid_mode")
    )
    assert result["success"] is False
    assert result["policy_checked"] is False
    assert result["response_version"] == "2"
    assert "valid_enforcement_modes" in result


def test_validate_for_import_and_check_specific_have_policy_proof(tmp_path):
    target = tmp_path / "FB_Test.TcPOU"
    _write_valid_fb(target)

    import_result = json.loads(validate_for_import(str(target)))
    assert import_result["success"] is True
    _assert_policy_fields(import_result)

    check_result = json.loads(check_specific(str(target), ["guid_format"]))
    assert check_result["success"] is True
    _assert_policy_fields(check_result)


def test_autofix_file_and_generate_skeleton_have_policy_proof(tmp_path):
    target = tmp_path / "FB_Test.TcPOU"
    _write_valid_fb(target)

    fix_result = json.loads(
        autofix_file(
            str(target),
            create_backup=False,
            profile="llm_strict",
            format_profile="twincat_canonical",
            strict_contract=True,
        )
    )
    assert fix_result["success"] is True
    _assert_policy_fields(fix_result)

    skeleton_result = json.loads(generate_skeleton("TcPOU", "function_block"))
    assert skeleton_result["success"] is True
    _assert_policy_fields(skeleton_result)


@pytest.mark.asyncio
async def test_batch_and_orchestration_tools_have_policy_proof(tmp_path):
    _write_valid_fb(tmp_path / "FB_A.TcPOU")
    _write_valid_fb(tmp_path / "FB_B.TcPOU")

    validate_result = json.loads(
        await validate_batch(file_patterns=["*.TcPOU"], directory_path=str(tmp_path))
    )
    assert validate_result["success"] is True
    _assert_policy_fields(validate_result)

    autofix_result = json.loads(
        await autofix_batch(file_patterns=["*.TcPOU"], directory_path=str(tmp_path))
    )
    assert autofix_result["success"] is True
    _assert_policy_fields(autofix_result)

    single_result = json.loads(process_twincat_single(str(tmp_path / "FB_A.TcPOU")))
    assert single_result["success"] is True
    _assert_policy_fields(single_result)

    orchestrated_batch_result = json.loads(
        await process_twincat_batch(file_patterns=["*.TcPOU"], directory_path=str(tmp_path))
    )
    assert orchestrated_batch_result["success"] is True
    _assert_policy_fields(orchestrated_batch_result)
