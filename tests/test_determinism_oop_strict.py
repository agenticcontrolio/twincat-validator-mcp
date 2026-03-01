"""Determinism regression tests for strict mode on OOP-heavy TwinCAT artifacts."""

import json

from server import autofix_file


def _write_oop_set(base_dir):
    (base_dir / "I_MotorDiagnostics.TcIO").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <Itf Name="I_MotorDiagnostics" Id="{ABCDEF01-2345-6789-ABCD-EF0123456789}">\n'
        "    <Declaration><![CDATA[INTERFACE I_MotorDiagnostics\n]]></Declaration>\n"
        '    <Method Name="M_ResetFaults" Id="{ABCDEF01-2345-6789-ABCD-EF0123456790}">\n'
        "      <Declaration><![CDATA[METHOD M_ResetFaults : BOOL\n]]></Declaration>\n"
        "    </Method>\n"
        "  </Itf>\n"
        "</TcPlcObject>\n",
        encoding="utf-8",
    )
    (base_dir / "FB_MotorBase.TcPOU").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <POU Name="FB_MotorBase" Id="{ABCDEF01-2345-6789-ABCD-EF0123456791}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_MotorBase IMPLEMENTS I_MotorDiagnostics\n"
        "VAR\n"
        "  nFaultCode : INT;\n"
        "END_VAR\n"
        "]]></Declaration>\n"
        "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
        '    <Method Name="M_ResetFaults" Id="{ABCDEF01-2345-6789-ABCD-EF0123456792}">\n'
        "      <Declaration><![CDATA[METHOD M_ResetFaults : BOOL\n]]></Declaration>\n"
        "      <Implementation><ST><![CDATA[nFaultCode := 0;\nM_ResetFaults := TRUE;]]></ST></Implementation>\n"
        "    </Method>\n"
        '    <LineIds Name="FB_MotorBase">\n      <LineId Id="7" Count="99" />\n    </LineIds>\n'
        '    <LineIds Name="FB_MotorBase.M_ResetFaults">\n      <LineId Id="2" Count="9" />\n    </LineIds>\n'
        "  </POU>\n"
        "</TcPlcObject>\n",
        encoding="utf-8",
    )
    (base_dir / "FB_MotorAdvanced.TcPOU").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <POU Name="FB_MotorAdvanced" Id="{ABCDEF01-2345-6789-ABCD-EF0123456793}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_MotorAdvanced EXTENDS FB_MotorBase\n]]></Declaration>\n"
        "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
        '    <Method Name="M_ResetFaults" Id="{ABCDEF01-2345-6789-ABCD-EF0123456794}">\n'
        "      <Declaration><![CDATA[{attribute 'override'}\nMETHOD M_ResetFaults : BOOL\n]]></Declaration>\n"
        "      <Implementation><ST><![CDATA[M_ResetFaults := SUPER^.M_ResetFaults();]]></ST></Implementation>\n"
        "    </Method>\n"
        '    <LineIds Name="FB_MotorAdvanced">\n      <LineId Id="8" Count="8" />\n    </LineIds>\n'
        '    <LineIds Name="FB_MotorAdvanced.M_ResetFaults">\n      <LineId Id="3" Count="3" />\n    </LineIds>\n'
        "  </POU>\n"
        "</TcPlcObject>\n",
        encoding="utf-8",
    )


def _strict_fix(path):
    return json.loads(
        autofix_file(
            str(path),
            create_backup=False,
            profile="llm_strict",
            format_profile="twincat_canonical",
            strict_contract=True,
            create_implicit_files=True,
            orchestration_hints=True,
        )
    )


def test_strict_oop_outputs_are_byte_identical_across_paths(tmp_path):
    """Same OOP input in different folders should converge to byte-identical outputs."""
    dir_a = tmp_path / "A Path"
    dir_b = tmp_path / "B_Path"
    dir_a.mkdir()
    dir_b.mkdir()
    _write_oop_set(dir_a)
    _write_oop_set(dir_b)

    for name in ("I_MotorDiagnostics.TcIO", "FB_MotorBase.TcPOU", "FB_MotorAdvanced.TcPOU"):
        result_a = _strict_fix(dir_a / name)
        result_b = _strict_fix(dir_b / name)
        assert result_a["success"] is True
        assert result_b["success"] is True

    for name in ("I_MotorDiagnostics.TcIO", "FB_MotorBase.TcPOU", "FB_MotorAdvanced.TcPOU"):
        content_a = (dir_a / name).read_text(encoding="utf-8")
        content_b = (dir_b / name).read_text(encoding="utf-8")
        assert content_a == content_b


def test_strict_oop_second_pass_is_idempotent(tmp_path):
    """Second strict pass on OOP-heavy files must not change bytes."""
    _write_oop_set(tmp_path)
    target = tmp_path / "FB_MotorAdvanced.TcPOU"

    first = _strict_fix(target)
    second = _strict_fix(target)

    assert first["success"] is True
    assert second["success"] is True
    assert second["content_changed"] is False
    assert first["content_fingerprint_after"] == second["content_fingerprint_after"]
