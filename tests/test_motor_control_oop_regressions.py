"""Regression tests for motor-control OOP workflows under MCP orchestration."""

import json

from server import autofix_file, check_specific


def test_pou_structure_interface_ignores_override_attribute_lines(tmp_path):
    """Interface signature comparison should parse declarations with pragma lines."""
    (tmp_path / "I_MotorControl.TcIO").write_text(
        (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
            '  <Itf Name="I_MotorControl" Id="{11111111-1111-1111-1111-111111111111}">\n'
            "    <Declaration><![CDATA[INTERFACE I_MotorControl\n]]></Declaration>\n"
            '    <Method Name="M_SetSpeed" Id="{11111111-1111-1111-1111-111111111112}">\n'
            "      <Declaration><![CDATA[METHOD M_SetSpeed : BOOL\nVAR_INPUT\n"
            "  rSpeedRpm : LREAL;\nEND_VAR\n]]></Declaration>\n"
            "    </Method>\n"
            "  </Itf>\n"
            "</TcPlcObject>\n"
        ),
        encoding="utf-8",
    )
    fb_path = tmp_path / "FB_ServoMotor.TcPOU"
    fb_path.write_text(
        (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
            '  <POU Name="FB_ServoMotor" Id="{22222222-2222-2222-2222-222222222222}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_ServoMotor IMPLEMENTS I_MotorControl\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_SetSpeed" Id="{22222222-2222-2222-2222-222222222223}">\n'
            "      <Declaration><![CDATA[{attribute 'override'}\nMETHOD M_SetSpeed : BOOL\nVAR_INPUT\n"
            "  rSpeedRpm : LREAL;\nEND_VAR\n]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[M_SetSpeed := TRUE;]]></ST></Implementation>\n"
            "    </Method>\n"
            '    <LineIds Name="FB_ServoMotor">\n      <LineId Id="1" Count="0" />\n    </LineIds>\n'
            '    <LineIds Name="FB_ServoMotor.M_SetSpeed">\n      <LineId Id="2" Count="0" />\n    </LineIds>\n'
            "  </POU>\n"
            "</TcPlcObject>\n"
        ),
        encoding="utf-8",
    )

    result = json.loads(check_specific(str(fb_path), ["pou_structure_interface"]))
    assert result["success"] is True
    assert result["issues"] == []


def test_canonical_autofix_keeps_method_var_input_and_rebuilds_abstract_lineids(tmp_path):
    """Canonical autofix must preserve method VAR_INPUT params and emit abstract method LineIds."""
    base_path = tmp_path / "FB_MotorBase.TcPOU"
    base_path.write_text(
        (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
            '  <POU Name="FB_MotorBase" Id="{33333333-3333-3333-3333-333333333333}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK ABSTRACT FB_MotorBase\n]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_SetSpeed" Id="{33333333-3333-3333-3333-333333333334}">\n'
            "      <Declaration><![CDATA[METHOD ABSTRACT M_SetSpeed : BOOL\nVAR_INPUT\n"
            "  rSpeedRpm : LREAL;\nEND_VAR\n]]></Declaration>\n"
            "    </Method>\n"
            '    <Method Name="M_GetTelemetry" Id="{33333333-3333-3333-3333-333333333335}">\n'
            "      <Declaration><![CDATA[METHOD ABSTRACT M_GetTelemetry : BOOL\n]]></Declaration>\n"
            "    </Method>\n"
            '    <LineIds Name="FB_MotorBase">\n      <LineId Id="7" Count="9" />\n    </LineIds>\n'
            "  </POU>\n"
            "</TcPlcObject>\n"
        ),
        encoding="utf-8",
    )

    result = json.loads(
        autofix_file(
            str(base_path),
            create_backup=False,
            profile="llm_strict",
            format_profile="twincat_canonical",
            strict_contract=False,
            enforcement_mode="strict",
        )
    )
    assert result["success"] is True

    updated = base_path.read_text(encoding="utf-8")
    assert "VAR_INPUT\n  rSpeedRpm : LREAL;\nEND_VAR" in updated
    assert '<LineIds Name="FB_MotorBase.M_SetSpeed">' in updated
    assert '<LineIds Name="FB_MotorBase.M_GetTelemetry">' in updated
