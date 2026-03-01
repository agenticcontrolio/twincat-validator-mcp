"""Regression tests for policy-enforcement bypass attempts."""

import json

from server import autofix_file


def _write_contract_files(base_dir, disable_guard: bool = False) -> None:
    if disable_guard:
        (base_dir / ".twincat-validator.json").write_text(
            '{\n  "oop_policy": {"enforce_interface_contract_integrity": false}\n}\n',
            encoding="utf-8",
        )

    (base_dir / "I_MotorControl.TcIO").write_text(
        (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
            '  <Itf Name="I_MotorControl" Id="{a1111111-1111-1111-1111-111111111111}">\n'
            "    <Declaration><![CDATA[INTERFACE I_MotorControl\n]]></Declaration>\n"
            '    <Method Name="M_SetSpeed" Id="{a1111111-1111-1111-1111-111111111112}">\n'
            "      <Declaration><![CDATA[METHOD M_SetSpeed : BOOL\nVAR_INPUT\n"
            "  rSpeedRpm : LREAL;\nEND_VAR\n]]></Declaration>\n"
            "    </Method>\n"
            '    <Method Name="M_GetTelemetry" Id="{a1111111-1111-1111-1111-111111111113}">\n'
            "      <Declaration><![CDATA[METHOD M_GetTelemetry : BOOL\n]]></Declaration>\n"
            "    </Method>\n"
            "  </Itf>\n"
            "</TcPlcObject>\n"
        ),
        encoding="utf-8",
    )

    (base_dir / "FB_MotorBase.TcPOU").write_text(
        (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
            '  <POU Name="FB_MotorBase" Id="{a2222222-2222-2222-2222-222222222222}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK ABSTRACT FB_MotorBase\n]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <Method Name="M_SetSpeed" Id="{a2222222-2222-2222-2222-222222222223}">\n'
            "      <Declaration><![CDATA[METHOD ABSTRACT M_SetSpeed : BOOL\nVAR_INPUT\n"
            "  rSpeedRpm : LREAL;\nEND_VAR\n]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "    </Method>\n"
            '    <Method Name="M_GetTelemetry" Id="{a2222222-2222-2222-2222-222222222224}">\n'
            "      <Declaration><![CDATA[METHOD ABSTRACT M_GetTelemetry : BOOL\n]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "    </Method>\n"
            '    <LineIds Name="FB_MotorBase">\n'
            '      <LineId Id="1" Count="0" />\n'
            "    </LineIds>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        ),
        encoding="utf-8",
    )

    (base_dir / "FB_ServoMotor.TcPOU").write_text(
        (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
            '  <POU Name="FB_ServoMotor" Id="{a3333333-3333-3333-3333-333333333333}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_ServoMotor EXTENDS FB_MotorBase\n]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <LineIds Name="FB_ServoMotor">\n'
            '      <LineId Id="1" Count="0" />\n'
            "    </LineIds>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        ),
        encoding="utf-8",
    )


def test_strict_mode_blocks_contract_weakening(tmp_path):
    _write_contract_files(tmp_path, disable_guard=False)

    result = json.loads(
        autofix_file(
            str(tmp_path / "FB_MotorBase.TcPOU"),
            create_backup=False,
            profile="llm_strict",
            format_profile="twincat_canonical",
            strict_contract=True,
            intent_profile="oop",  # OOP contract enforcement test requires OOP checks
        )
    )

    assert result["success"] is True
    assert result["safe_to_import"] is False
    assert result["safe_to_compile"] is False
    policy_blockers = [b for b in result["blockers"] if b.get("check") == "policy_enforcement"]
    assert len(policy_blockers) >= 1
    assert policy_blockers[0].get("rule_id") == "enforce_interface_contract_integrity"
    assert policy_blockers[0].get("severity") == "error"
    assert policy_blockers[0].get("fixable") is False


def test_policy_override_can_disable_contract_weakening_guard(tmp_path):
    _write_contract_files(tmp_path, disable_guard=True)

    result = json.loads(
        autofix_file(
            str(tmp_path / "FB_MotorBase.TcPOU"),
            create_backup=False,
            profile="llm_strict",
            format_profile="twincat_canonical",
            strict_contract=True,
            intent_profile="oop",  # OOP contract enforcement test requires OOP checks
        )
    )

    policy_blockers = [b for b in result["blockers"] if b.get("check") == "policy_enforcement"]
    assert policy_blockers == []
