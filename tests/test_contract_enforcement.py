"""Tests for generation-contract enforcement and skeleton generation tools."""

import json
import re

from server import autofix_file, extract_methods_to_xml, generate_skeleton


def test_autofix_strict_contract_fails_closed_on_missing_implementation(tmp_path):
    """strict_contract=True should stop and request regeneration."""
    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR]]></Declaration>\n"
        "  </POU>\n"
        "</TcPlcObject>\n"
    )
    file_path = tmp_path / "broken_contract.TcPOU"
    file_path.write_text(content, encoding="utf-8")

    result = json.loads(
        autofix_file(
            str(file_path),
            profile="llm_strict",
            create_backup=False,
            strict_contract=True,
        )
    )

    assert result["success"] is True
    assert result["contract_passed"] is False
    assert result["requires_regeneration"] is True
    assert result["safe_to_import"] is False
    assert result["safe_to_compile"] is False
    assert result["content_changed"] is False
    assert result["fixes_applied"] == []
    assert result["blocking_count"] == len(result["blockers"])
    assert len(result["contract_errors"]) >= 1


def test_autofix_without_strict_contract_keeps_v2_shape(tmp_path):
    """strict_contract=False keeps llm_strict minimal shape plus policy-proof v2 fields."""
    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '\t<POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR]]></Declaration>\n"
        "  </POU>\n"
        "</TcPlcObject>\n"
    )
    file_path = tmp_path / "legacy_shape.TcPOU"
    file_path.write_text(content, encoding="utf-8")

    result = json.loads(autofix_file(str(file_path), profile="llm_strict", create_backup=False))
    required_keys = {
        "success",
        "file_path",
        "safe_to_import",
        "safe_to_compile",
        "content_changed",
        "fixes_applied",
        "blocking_count",
        "blockers",
        "invalid_guid_count",
        "contract_violations",
        "policy_checked",
        "policy_source",
        "policy_fingerprint",
        "enforcement_mode",
        "response_version",
        "meta",
    }
    assert set(result.keys()) == required_keys


def test_autofix_fail_closed_on_malformed_guid_token(tmp_path):
    """Malformed GUID tokens must force safe flags false via artifact sanity pass."""
    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <DUT Name="ST_AlarmEntry" Id="{e6f7a8b9-ca db-4cee-e05b-6c7d8e9fa6b7}">\n'
        "    <Declaration><![CDATA[TYPE ST_AlarmEntry : STRUCT\n"
        "  nAlarmId : DINT;\n"
        "END_STRUCT\n"
        "END_TYPE]]></Declaration>\n"
        "  </DUT>\n"
        "</TcPlcObject>\n"
    )
    file_path = tmp_path / "ST_AlarmEntry.TcDUT"
    file_path.write_text(content, encoding="utf-8")

    result = json.loads(autofix_file(str(file_path), profile="llm_strict", create_backup=False))

    assert result["success"] is True
    assert result["invalid_guid_count"] >= 1
    assert result["safe_to_import"] is False
    assert result["safe_to_compile"] is False
    assert result["blocking_count"] >= 1
    assert any("malformed GUID token" in b.get("message", "") for b in result["blockers"])


def test_uppercase_guids_not_counted_as_malformed_after_canonicalization(tmp_path):
    """Uppercase-but-well-formed GUIDs are fixable and must NOT trigger malformed GUID blocker.

    Regression test for C5: _count_invalid_guid_tokens must use any-case pattern
    so uppercase GUIDs (which canonicalization auto-fixes) don't cause permanent
    safe_to_import=False.
    """
    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <POU Name="FB_UpperGuid" Id="{AABBCCDD-1234-5678-9ABC-DEF012345678}"'
        ' SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_UpperGuid\nVAR\nEND_VAR"
        "]]></Declaration>\n"
        "    <Implementation>\n"
        "      <ST><![CDATA[]]></ST>\n"
        "    </Implementation>\n"
        "  </POU>\n"
        "</TcPlcObject>\n"
    )
    file_path = tmp_path / "FB_UpperGuid.TcPOU"
    file_path.write_text(content, encoding="utf-8")

    result = json.loads(
        autofix_file(
            str(file_path),
            profile="llm_strict",
            create_backup=False,
            format_profile="twincat_canonical",
            strict_contract=True,
        )
    )

    assert result["success"] is True
    assert result["invalid_guid_count"] == 0, (
        f"Uppercase GUIDs should not be counted as malformed after canonicalization, "
        f"got invalid_guid_count={result['invalid_guid_count']}"
    )
    # No malformed GUID blockers
    guid_blockers = [
        b for b in result.get("blockers", []) if "malformed GUID" in b.get("message", "")
    ]
    assert len(guid_blockers) == 0, f"Got unexpected GUID blockers: {guid_blockers}"


def test_generate_skeleton_tcppou_function_block():
    """Tool should return canonical .TcPOU function block scaffold."""
    result = json.loads(generate_skeleton("TcPOU", "function_block"))
    assert result["success"] is True
    assert result["file_type"] == ".TcPOU"
    assert result["subtype"] == "function_block"
    assert "FUNCTION_BLOCK FB_Example" in result["skeleton"]
    assert "<Implementation>" in result["skeleton"]
    assert '<LineIds Name="FB_Example">' in result["skeleton"]


def test_generate_skeleton_tcppou_function_has_return_type():
    """Function subtype scaffold should include return type."""
    result = json.loads(generate_skeleton(".TcPOU", "function"))
    assert result["success"] is True
    assert "FUNCTION FUNC_Example : BOOL" in result["skeleton"]


def test_generate_skeleton_rejects_unknown_file_type():
    """Tool should reject unsupported file types."""
    result = json.loads(generate_skeleton(".TcXYZ"))
    assert result["success"] is False
    assert "Unsupported file type" in result["error"]


def test_generate_skeleton_tcio_uses_method_xml_nodes():
    """TcIO skeleton should use <Method> nodes, not inline END_METHOD declarations."""
    result = json.loads(generate_skeleton(".TcIO"))
    assert result["success"] is True
    skeleton = result["skeleton"]
    assert "<Method Name=" in skeleton
    assert "END_METHOD" not in skeleton


def test_autofix_can_create_missing_implicit_interface_file(tmp_path):
    """create_implicit_files=True should create missing I_* interface TcIO files."""
    fb_content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <POU Name="FB_WithI" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_WithI IMPLEMENTS I_Log\n"
        "END_FUNCTION_BLOCK]]></Declaration>\n"
        "    <Implementation>\n"
        "      <ST><![CDATA[]]></ST>\n"
        "    </Implementation>\n"
        '    <Method Name="M_Log" Id="{22345678-1234-1234-1234-123456789abc}">\n'
        "      <Declaration><![CDATA[METHOD M_Log : BOOL]]></Declaration>\n"
        "      <Implementation><ST><![CDATA[M_Log := TRUE;]]></ST></Implementation>\n"
        "    </Method>\n"
        '    <LineIds Name="FB_WithI">\n'
        '      <LineId Id="1" Count="0" />\n'
        "    </LineIds>\n"
        '    <LineIds Name="FB_WithI.M_Log">\n'
        '      <LineId Id="2" Count="0" />\n'
        "    </LineIds>\n"
        "  </POU>\n"
        "</TcPlcObject>\n"
    )
    fb_path = tmp_path / "FB_WithI.TcPOU"
    fb_path.write_text(fb_content, encoding="utf-8")

    result = json.loads(
        autofix_file(
            str(fb_path),
            profile="llm_strict",
            create_backup=False,
            create_implicit_files=True,
        )
    )

    interface_path = tmp_path / "I_Log.TcIO"
    assert interface_path.exists()
    interface_content = interface_path.read_text(encoding="utf-8")
    assert '<Itf Name="I_Log"' in interface_content
    assert "INTERFACE I_Log" in interface_content
    assert "<Method Name=" in interface_content
    assert "END_METHOD" not in interface_content
    assert "implicit_files_created" in result
    assert str(interface_path) in result["implicit_files_created"]


def test_autofix_can_create_missing_implicit_extends_base_file(tmp_path):
    """create_implicit_files=True should create missing EXTENDS base .TcPOU file."""
    fb_content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <POU Name="FB_Derived" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\n"
        "END_FUNCTION_BLOCK]]></Declaration>\n"
        "    <Implementation>\n"
        "      <ST><![CDATA[]]></ST>\n"
        "    </Implementation>\n"
        '    <LineIds Name="FB_Derived">\n'
        '      <LineId Id="1" Count="0" />\n'
        "    </LineIds>\n"
        "  </POU>\n"
        "</TcPlcObject>\n"
    )
    fb_path = tmp_path / "FB_Derived.TcPOU"
    fb_path.write_text(fb_content, encoding="utf-8")

    result = json.loads(
        autofix_file(
            str(fb_path),
            profile="llm_strict",
            create_backup=False,
            create_implicit_files=True,
        )
    )

    base_path = tmp_path / "FB_Base.TcPOU"
    assert base_path.exists()
    base_content = base_path.read_text(encoding="utf-8")
    assert '<POU Name="FB_Base"' in base_content
    assert "FUNCTION_BLOCK FB_Base" in base_content
    assert '<LineIds Name="FB_Base">' in base_content
    assert "implicit_files_created" in result
    assert str(base_path) in result["implicit_files_created"]


def test_autofix_orchestration_hints_include_next_action(tmp_path):
    """orchestration_hints=True should include loop-guard action fields."""
    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <POU Name="FB_Looping" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Looping\n"
        "END_FUNCTION_BLOCK]]></Declaration>\n"
        "    <Implementation>\n"
        "      <ST><![CDATA[METHOD Run : BOOL\nRun := TRUE;\nEND_METHOD\n]]></ST>\n"
        "    </Implementation>\n"
        '    <LineIds Name="FB_Looping">\n'
        '      <LineId Id="1" Count="0" />\n'
        "    </LineIds>\n"
        "  </POU>\n"
        "</TcPlcObject>\n"
    )
    file_path = tmp_path / "looping.TcPOU"
    file_path.write_text(content, encoding="utf-8")

    result = json.loads(
        autofix_file(
            str(file_path),
            profile="llm_strict",
            create_backup=False,
            orchestration_hints=True,
        )
    )

    assert "next_action" in result
    assert "terminal" in result
    assert "no_change_detected" in result
    assert "content_fingerprint_before" in result
    assert "content_fingerprint_after" in result
    assert "issue_fingerprint" in result
    assert "no_progress_count" in result
    assert isinstance(result["no_progress_count"], int)
    assert result["next_action"] in {
        "extract_methods_to_xml",
        "rerun_autofix",
        "stop_and_report",
        "manual_intervention",
    }


def test_extract_methods_to_xml_promotes_inline_methods(tmp_path):
    """extract_methods_to_xml should convert inline METHOD blocks into <Method> XML nodes."""
    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <POU Name="FB_Convert" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Convert\n"
        "END_FUNCTION_BLOCK]]></Declaration>\n"
        "    <Implementation>\n"
        "      <ST><![CDATA[METHOD TestMethod : BOOL\nTestMethod := TRUE;\nEND_METHOD\n]]></ST>\n"
        "    </Implementation>\n"
        '    <LineIds Name="FB_Convert">\n'
        '      <LineId Id="1" Count="0" />\n'
        "    </LineIds>\n"
        "  </POU>\n"
        "</TcPlcObject>\n"
    )
    file_path = tmp_path / "convert.TcPOU"
    file_path.write_text(content, encoding="utf-8")

    result = json.loads(extract_methods_to_xml(str(file_path), create_backup=False))
    assert result["success"] is True
    assert result["content_changed"] is True
    assert result["methods_extracted"] >= 1

    updated = file_path.read_text(encoding="utf-8")
    assert '<Method Name="TestMethod">' in updated
    assert "METHOD TestMethod : BOOL" in updated


def test_autofix_can_extract_inline_struct_to_dut(tmp_path):
    """create_implicit_files=True should externalize inline STRUCT to .TcDUT."""
    fb_content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <POU Name="FB_WithStruct" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_WithStruct\n"
        "VAR\n"
        "  aHistory : ARRAY[1..10] OF STRUCT\n"
        "    nCode : DINT;\n"
        "  END_STRUCT;\n"
        "END_VAR]]></Declaration>\n"
        "    <Implementation>\n"
        "      <ST><![CDATA[]]></ST>\n"
        "    </Implementation>\n"
        '    <LineIds Name="FB_WithStruct">\n'
        '      <LineId Id="1" Count="0" />\n'
        "    </LineIds>\n"
        "  </POU>\n"
        "</TcPlcObject>\n"
    )
    fb_path = tmp_path / "FB_WithStruct.TcPOU"
    fb_path.write_text(fb_content, encoding="utf-8")

    result = json.loads(
        autofix_file(
            str(fb_path),
            profile="llm_strict",
            create_backup=False,
            create_implicit_files=True,
        )
    )

    dut_path = tmp_path / "ST_HistoryEntry.TcDUT"
    assert dut_path.exists()
    dut_content = dut_path.read_text(encoding="utf-8")
    assert "TYPE ST_HistoryEntry : STRUCT" in dut_content
    assert "nCode : DINT;" in dut_content

    updated_fb = fb_path.read_text(encoding="utf-8")
    assert "aHistory : ARRAY[1..10] OF ST_HistoryEntry;" in updated_fb
    assert "implicit_files_created" in result
    assert str(dut_path) in result["implicit_files_created"]


def test_autofix_normalizes_tcio_inline_methods_to_method_nodes(tmp_path):
    """autofix should normalize TcIO inline METHOD declarations into <Method> nodes."""
    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <Itf Name="I_Record" Id="{12345678-1234-1234-1234-123456789abc}">\n'
        "    <Declaration><![CDATA[INTERFACE I_Record\n"
        "METHOD M_AddAlarm : BOOL\n"
        "VAR_INPUT\n"
        "  nAlarmId : DINT;\n"
        "END_VAR\n"
        "METHOD M_GetCount : UINT\n"
        "END_INTERFACE]]></Declaration>\n"
        "  </Itf>\n"
        "</TcPlcObject>\n"
    )
    io_path = tmp_path / "I_Record.TcIO"
    io_path.write_text(content, encoding="utf-8")

    result = json.loads(autofix_file(str(io_path), profile="llm_strict", create_backup=False))

    updated = io_path.read_text(encoding="utf-8")
    assert result["content_changed"] is True
    assert '<Method Name="M_AddAlarm"' in updated
    assert '<Method Name="M_GetCount"' in updated
    assert "END_INTERFACE]]></Declaration>" not in updated
    assert "<Declaration><![CDATA[INTERFACE I_Record\n]]></Declaration>" in updated
    assert "<Declaration><![CDATA[METHOD M_GetCount : UINT\n]]></Declaration>" in updated


def test_autofix_canonicalizes_tcio_method_declarations(tmp_path):
    """autofix should normalize compact TcIO method declarations and empty VAR_INPUT."""
    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <Itf Name="I_Record" Id="{12345678-1234-1234-1234-123456789abc}">\n'
        "    <Declaration><![CDATA[INTERFACE I_Record\nEND_INTERFACE]]></Declaration>\n"
        '    <Method Name="M_GetCount" Id="{22345678-1234-1234-1234-123456789abc}">\n'
        "      <Declaration><![CDATA[METHOD M_GetCount : UINT\nVAR_INPUT\nEND_VAR]]></Declaration>\n"
        "    </Method>\n"
        "  </Itf>\n"
        "</TcPlcObject>\n"
    )
    io_path = tmp_path / "I_Record.TcIO"
    io_path.write_text(content, encoding="utf-8")

    result = json.loads(autofix_file(str(io_path), profile="llm_strict", create_backup=False))
    updated = io_path.read_text(encoding="utf-8")

    assert result["success"] is True
    assert "<Declaration><![CDATA[INTERFACE I_Record\n]]></Declaration>" in updated
    assert "END_INTERFACE" not in updated
    assert "VAR_INPUT\nEND_VAR" not in updated
    assert "<Declaration><![CDATA[METHOD M_GetCount : UINT\n]]></Declaration>" in updated


def test_autofix_canonicalizes_tcdut_and_removes_lineids(tmp_path):
    """autofix should remove DUT LineIds and normalize TYPE declaration layout."""
    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <DUT Name="ST_AlarmEntry" Id="{12345678-90ab-cdef-1234-567890abcdef}">\n'
        "    <Declaration><![CDATA[TYPE ST_AlarmEntry :\n"
        "STRUCT\n"
        "  nAlarmId : DINT;\n"
        "END_STRUCT\n"
        "END_TYPE\n"
        "]]></Declaration>\n"
        '    <LineIds Name="ST_AlarmEntry">\n'
        '      <LineId Id="1" Count="0" />\n'
        "    </LineIds>\n"
        "  </DUT>\n"
        "</TcPlcObject>\n"
    )
    dut_path = tmp_path / "ST_AlarmEntry.TcDUT"
    dut_path.write_text(content, encoding="utf-8")

    result = json.loads(autofix_file(str(dut_path), profile="llm_strict", create_backup=False))
    updated = dut_path.read_text(encoding="utf-8")

    assert result["success"] is True
    assert result["content_changed"] is True
    assert "<LineIds Name=" not in updated
    assert "TYPE ST_AlarmEntry : STRUCT" in updated


def test_autofix_canonicalizes_tcpou_method_empty_var_block(tmp_path):
    """autofix should remove empty local VAR blocks in .TcPOU method declarations."""
    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <POU Name="FB_Test" Id="{12345678-90ab-cdef-1234-567890abcdef}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test\n"
        "VAR\n"
        "END_VAR\n"
        "]]></Declaration>\n"
        "    <Implementation>\n"
        "      <ST><![CDATA[]]></ST>\n"
        "    </Implementation>\n"
        '    <Method Name="M_GetCount" Id="{22345678-1234-1234-1234-123456789abc}">\n'
        "      <Declaration><![CDATA[METHOD M_GetCount : UINT\n"
        "VAR\n"
        "END_VAR]]></Declaration>\n"
        "      <Implementation>\n"
        "        <ST><![CDATA[M_GetCount := 0;]]></ST>\n"
        "      </Implementation>\n"
        "    </Method>\n"
        '    <LineIds Name="FB_Test">\n'
        '      <LineId Id="1" Count="0" />\n'
        "    </LineIds>\n"
        '    <LineIds Name="FB_Test.M_GetCount">\n'
        '      <LineId Id="2" Count="1" />\n'
        "    </LineIds>\n"
        "  </POU>\n"
        "</TcPlcObject>\n"
    )
    pou_path = tmp_path / "FB_Test.TcPOU"
    pou_path.write_text(content, encoding="utf-8")

    result = json.loads(autofix_file(str(pou_path), profile="llm_strict", create_backup=False))
    updated = pou_path.read_text(encoding="utf-8")

    assert result["success"] is True
    assert result["content_changed"] is True
    assert "METHOD M_GetCount : UINT\nVAR\nEND_VAR" not in updated
    assert "<Declaration><![CDATA[METHOD M_GetCount : UINT\n]]></Declaration>" in updated


def test_autofix_does_not_force_end_if_semicolon(tmp_path):
    """autofix should not force semicolons on END_IF block terminators."""
    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <POU Name="FB_Test" Id="{12345678-90ab-cdef-1234-567890abcdef}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test\n"
        "VAR\n"
        "END_VAR\n"
        "]]></Declaration>\n"
        "    <Implementation>\n"
        "      <ST><![CDATA[]]></ST>\n"
        "    </Implementation>\n"
        '    <Method Name="M_Run" Id="{22345678-1234-1234-1234-123456789abc}">\n'
        "      <Declaration><![CDATA[METHOD M_Run : BOOL\n"
        "]]></Declaration>\n"
        "      <Implementation>\n"
        "        <ST><![CDATA[IF TRUE THEN\n"
        "  M_Run := TRUE;\n"
        "END_IF\n"
        "]]></ST>\n"
        "      </Implementation>\n"
        "    </Method>\n"
        '    <LineIds Name="FB_Test">\n'
        '      <LineId Id="1" Count="0" />\n'
        "    </LineIds>\n"
        '    <LineIds Name="FB_Test.M_Run">\n'
        '      <LineId Id="2" Count="0" />\n'
        "    </LineIds>\n"
        "  </POU>\n"
        "</TcPlcObject>\n"
    )
    pou_path = tmp_path / "FB_Test.TcPOU"
    pou_path.write_text(content, encoding="utf-8")

    result = json.loads(autofix_file(str(pou_path), profile="llm_strict", create_backup=False))
    updated = pou_path.read_text(encoding="utf-8")

    assert result["success"] is True
    assert result["content_changed"] is False
    assert "END_IF\n" in updated
    assert "END_IF;" not in updated


def test_autofix_strips_end_if_semicolon_when_present(tmp_path):
    """autofix should canonicalize END_IF; to END_IF in ST blocks."""
    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <POU Name="FB_Test2" Id="{12345678-90ab-cdef-1234-567890abcdee}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test2\n"
        "VAR\n"
        "END_VAR\n"
        "]]></Declaration>\n"
        "    <Implementation>\n"
        "      <ST><![CDATA[]]></ST>\n"
        "    </Implementation>\n"
        '    <Method Name="M_Run" Id="{22345678-1234-1234-1234-123456789abd}">\n'
        "      <Declaration><![CDATA[METHOD M_Run : BOOL\n"
        "]]></Declaration>\n"
        "      <Implementation>\n"
        "        <ST><![CDATA[IF TRUE THEN\n"
        "  M_Run := TRUE;\n"
        "END_IF;\n"
        "]]></ST>\n"
        "      </Implementation>\n"
        "    </Method>\n"
        '    <LineIds Name="FB_Test2">\n'
        '      <LineId Id="1" Count="0" />\n'
        "    </LineIds>\n"
        '    <LineIds Name="FB_Test2.M_Run">\n'
        '      <LineId Id="2" Count="0" />\n'
        "    </LineIds>\n"
        "  </POU>\n"
        "</TcPlcObject>\n"
    )
    pou_path = tmp_path / "FB_Test2.TcPOU"
    pou_path.write_text(content, encoding="utf-8")

    result = json.loads(autofix_file(str(pou_path), profile="llm_strict", create_backup=False))
    updated = pou_path.read_text(encoding="utf-8")

    assert result["success"] is True
    assert result["content_changed"] is True
    assert "END_IF;\n" not in updated
    assert "END_IF\n" in updated


def test_autofix_canonicalizes_tcpou_duplicate_lineids_entries(tmp_path):
    """autofix should collapse duplicate LineId entries in each LineIds block."""
    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <POU Name="FB_Test" Id="{12345678-90ab-cdef-1234-567890abcdef}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test\n"
        "VAR\n"
        "END_VAR\n"
        "]]></Declaration>\n"
        "    <Implementation>\n"
        "      <ST><![CDATA[]]></ST>\n"
        "    </Implementation>\n"
        '    <Method Name="M_Run" Id="{22345678-1234-1234-1234-123456789abc}">\n'
        "      <Declaration><![CDATA[METHOD M_Run : BOOL\n"
        "]]></Declaration>\n"
        "      <Implementation>\n"
        "        <ST><![CDATA[M_Run := TRUE;]]></ST>\n"
        "      </Implementation>\n"
        "    </Method>\n"
        '    <LineIds Name="FB_Test">\n'
        '      <LineId Id="1" Count="0" />\n'
        "    </LineIds>\n"
        '    <LineIds Name="FB_Test.M_Run">\n'
        '      <LineId Id="3" Count="2" />\n'
        '      <LineId Id="2" Count="0" />\n'
        "    </LineIds>\n"
        "  </POU>\n"
        "</TcPlcObject>\n"
    )
    pou_path = tmp_path / "FB_Test.TcPOU"
    pou_path.write_text(content, encoding="utf-8")

    result = json.loads(autofix_file(str(pou_path), profile="llm_strict", create_backup=False))
    updated = pou_path.read_text(encoding="utf-8")

    assert result["success"] is True
    assert result["content_changed"] is True
    assert (
        '<LineIds Name="FB_Test.M_Run">\n      <LineId Id="3" Count="2" />\n    </LineIds>'
        in updated
    )
    assert (
        '<LineIds Name="FB_Test.M_Run">\n      <LineId Id="3" Count="2" />\n      <LineId Id="2" Count="0" />\n    </LineIds>'
        not in updated
    )


def test_autofix_format_profile_twincat_canonical_rebuilds_lineids_and_is_stable(tmp_path):
    """Canonical format profile should rebuild deterministic LineIds and be idempotent."""
    content = (
        '<?xml version="1.0" encoding="utf-8"?>\r\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\r\n'
        '  <POU Name="FB_Test" Id="{12345678-90ab-cdef-1234-567890abcdef}" SpecialFunc="None">\r\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test\r\n"
        "VAR\r\n"
        "END_VAR\r\n"
        "]]></Declaration>\r\n"
        "    <Implementation>\r\n"
        "      <ST><![CDATA[]]></ST>\r\n"
        "    </Implementation>\r\n"
        '    <Method Name="M_Run" Id="{22345678-1234-1234-1234-123456789abc}">\r\n'
        "      <Declaration><![CDATA[METHOD M_Run : BOOL\r\n"
        "]]></Declaration>\r\n"
        "      <Implementation>\r\n"
        "        <ST><![CDATA[IF TRUE THEN\r\n"
        "M_Run := TRUE\r\n"
        "END_IF\r\n"
        "]]></ST>\r\n"
        "      </Implementation>\r\n"
        "    </Method>\r\n"
        '    <LineIds Name="FB_Test">\r\n'
        '      <LineId Id="3" Count="7" />\r\n'
        "    </LineIds>\r\n"
        '    <LineIds Name="FB_Test.M_Run">\r\n'
        '      <LineId Id="5" Count="8" />\r\n'
        '      <LineId Id="2" Count="0" />\r\n'
        "    </LineIds>\r\n"
        "  </POU>\r\n"
        "</TcPlcObject>\r\n"
    )
    pou_path = tmp_path / "FB_Test.TcPOU"
    pou_path.write_text(content, encoding="utf-8", newline="")

    result1 = json.loads(
        autofix_file(
            str(pou_path),
            profile="llm_strict",
            create_backup=False,
            format_profile="twincat_canonical",
        )
    )
    updated1 = pou_path.read_text(encoding="utf-8")
    result2 = json.loads(
        autofix_file(
            str(pou_path),
            profile="llm_strict",
            create_backup=False,
            format_profile="twincat_canonical",
        )
    )
    updated2 = pou_path.read_text(encoding="utf-8")

    assert result1["success"] is True
    assert result2["success"] is True
    assert "\r\n" not in updated1
    assert "END_IF\n" in updated1
    assert '<LineIds Name="FB_Test">\n      <LineId Id="1" Count="0" />\n    </LineIds>' in updated1
    assert (
        '<LineIds Name="FB_Test.M_Run">\n      <LineId Id="2" Count="2" />\n    </LineIds>'
        in updated1
    )
    assert updated1 == updated2


def test_autofix_format_profile_twincat_canonical_rewrites_placeholder_guids(tmp_path):
    """Canonical format profile should replace placeholder/repeated GUIDs deterministically."""
    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <POU Name="FB_Test" Id="{00000000-0000-0000-0000-000000000000}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test\n"
        "END_FUNCTION_BLOCK\n"
        "]]></Declaration>\n"
        "    <Implementation>\n"
        "      <ST><![CDATA[]]></ST>\n"
        "    </Implementation>\n"
        '    <Method Name="M_Run" Id="{00000000-0000-0000-0000-000000000000}">\n'
        "      <Declaration><![CDATA[METHOD M_Run : BOOL\n"
        "]]></Declaration>\n"
        "      <Implementation>\n"
        "        <ST><![CDATA[M_Run := TRUE;]]></ST>\n"
        "      </Implementation>\n"
        "    </Method>\n"
        '    <LineIds Name="FB_Test">\n'
        '      <LineId Id="1" Count="0" />\n'
        "    </LineIds>\n"
        "  </POU>\n"
        "</TcPlcObject>\n"
    )
    pou_path = tmp_path / "FB_Test.TcPOU"
    pou_path.write_text(content, encoding="utf-8")

    result = json.loads(
        autofix_file(
            str(pou_path),
            profile="llm_strict",
            create_backup=False,
            format_profile="twincat_canonical",
        )
    )
    updated = pou_path.read_text(encoding="utf-8")

    assert result["success"] is True
    assert "{00000000-0000-0000-0000-000000000000}" not in updated
    assert re.search(
        r'Id="\{[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}"',
        updated,
    )


def test_autofix_canonical_injects_missing_tcplcobject_productversion(tmp_path):
    """Canonical profile should inject missing TcPlcObject ProductVersion."""
    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1">\n'
        '  <DUT Name="ST_Test" Id="{12345678-90ab-cdef-1234-567890abcdef}">\n'
        "    <Declaration><![CDATA[TYPE ST_Test : STRUCT\n"
        "  nValue : INT;\n"
        "END_STRUCT\n"
        "END_TYPE\n"
        "]]></Declaration>\n"
        "  </DUT>\n"
        "</TcPlcObject>\n"
    )
    dut_path = tmp_path / "ST_Test.TcDUT"
    dut_path.write_text(content, encoding="utf-8")

    result = json.loads(
        autofix_file(
            str(dut_path),
            profile="llm_strict",
            create_backup=False,
            format_profile="twincat_canonical",
        )
    )
    updated = dut_path.read_text(encoding="utf-8")

    assert result["success"] is True
    assert 'ProductVersion="3.1.4024.12"' in updated


def test_autofix_canonical_guids_are_unique_across_files(tmp_path):
    """Canonical GUID rewrite should avoid cross-file collisions for same symbol names."""
    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <POU Name="__NAME__" Id="{00000000-0000-0000-0000-000000000000}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK __NAME__\n"
        "END_FUNCTION_BLOCK\n"
        "]]></Declaration>\n"
        "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
        '    <Method Name="M_Run" Id="{00000000-0000-0000-0000-000000000000}">\n'
        "      <Declaration><![CDATA[METHOD M_Run : BOOL\n]]></Declaration>\n"
        "      <Implementation><ST><![CDATA[M_Run := TRUE;]]></ST></Implementation>\n"
        "    </Method>\n"
        '    <LineIds Name="__NAME__">\n'
        '      <LineId Id="1" Count="0" />\n'
        "    </LineIds>\n"
        "  </POU>\n"
        "</TcPlcObject>\n"
    )
    path_a = tmp_path / "FB_A.TcPOU"
    path_b = tmp_path / "FB_B.TcPOU"
    path_a.write_text(content.replace("__NAME__", "FB_A"), encoding="utf-8")
    path_b.write_text(content.replace("__NAME__", "FB_B"), encoding="utf-8")

    result_a = json.loads(
        autofix_file(
            str(path_a),
            profile="llm_strict",
            create_backup=False,
            format_profile="twincat_canonical",
        )
    )
    result_b = json.loads(
        autofix_file(
            str(path_b),
            profile="llm_strict",
            create_backup=False,
            format_profile="twincat_canonical",
        )
    )

    assert result_a["success"] is True
    assert result_b["success"] is True

    updated_a = path_a.read_text(encoding="utf-8")
    updated_b = path_b.read_text(encoding="utf-8")

    ids_a = set(re.findall(r'Id="(\{[0-9a-f-]+\})"', updated_a))
    ids_b = set(re.findall(r'Id="(\{[0-9a-f-]+\})"', updated_b))
    assert ids_a.isdisjoint(ids_b)


def test_orchestration_hints_stop_after_repeated_no_progress(tmp_path):
    """After repeated identical unchanged runs, hints should force terminal stop."""
    malformed = '<?xml version="1.0"?>\n<TcPlcObject>\n<POU>\n'
    bad_path = tmp_path / "loop.TcPOU"
    bad_path.write_text(malformed, encoding="utf-8")

    first = json.loads(
        autofix_file(
            str(bad_path),
            profile="llm_strict",
            create_backup=False,
            orchestration_hints=True,
        )
    )
    second = json.loads(
        autofix_file(
            str(bad_path),
            profile="llm_strict",
            create_backup=False,
            orchestration_hints=True,
        )
    )
    third = json.loads(
        autofix_file(
            str(bad_path),
            profile="llm_strict",
            create_backup=False,
            orchestration_hints=True,
        )
    )

    assert first["no_progress_count"] == 0
    assert second["no_progress_count"] >= 1
    assert third["no_progress_count"] >= 2
    assert third["next_action"] == "stop_and_report"
    assert third["terminal"] is True


def test_autofix_tcdut_tab_roundtrip_is_stable(tmp_path):
    """autofix canonical should remove tabs in DUT and remain stable on second pass."""
    dut_content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <DUT Name="ST_Tabbed" Id="{12345678-90ab-cdef-1234-567890abcdef}">\n'
        "    <Declaration><![CDATA[TYPE ST_Tabbed : STRUCT\n"
        "\tnStartCount : UDINT;\n"
        "\tnFaultCount : UDINT;\n"
        "END_STRUCT\n"
        "END_TYPE\n"
        "]]></Declaration>\n"
        "  </DUT>\n"
        "</TcPlcObject>\n"
    )
    dut_path = tmp_path / "ST_Tabbed.TcDUT"
    dut_path.write_text(dut_content, encoding="utf-8")

    first = json.loads(
        autofix_file(
            str(dut_path),
            profile="llm_strict",
            create_backup=False,
            format_profile="twincat_canonical",
        )
    )
    second = json.loads(
        autofix_file(
            str(dut_path),
            profile="llm_strict",
            create_backup=False,
            format_profile="twincat_canonical",
        )
    )

    final_text = dut_path.read_text(encoding="utf-8")
    assert "\t" not in final_text
    assert first["success"] is True
    assert second["success"] is True
    assert second["content_changed"] is False
