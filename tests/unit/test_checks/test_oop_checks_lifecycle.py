"""Tests for Phase 5A OOP checks: fb_exit_contract, dynamic_creation_attribute, pointer_delete_pairing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from twincat_validator.file_handler import TwinCATFile
from twincat_validator.validators.base import CheckRegistry
from twincat_validator.validators.oop_checks import (
    FbExitContractCheck,
    DynamicCreationAttributeCheck,
    PointerDeletePairingCheck,
)


def _ensure_phase5a_checks_registered() -> None:
    for check_class in (
        FbExitContractCheck,
        DynamicCreationAttributeCheck,
        PointerDeletePairingCheck,
    ):
        if check_class.check_id not in CheckRegistry.get_all_checks():
            CheckRegistry.register(check_class)


def _write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


class TestFbExitContractCheck:
    """Tests for FbExitContractCheck (Phase 5A)."""

    @classmethod
    def setup_class(cls):
        _ensure_phase5a_checks_registered()

    def test_pass_when_fb_exit_has_canonical_signature(self, tmp_path):
        _write_file(
            tmp_path / "FB_Good.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Good" Id="{a1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Good\n"
                "VAR\n  _pBuffer : POINTER TO INT;\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[_pBuffer := __NEW(INT);]]></ST></Implementation>\n"
                '    <Method Name="FB_exit" Id="{a1111111-1111-1111-1111-111111111112}">\n'
                "      <Declaration><![CDATA[METHOD FB_exit : BOOL\n"
                "VAR_INPUT\n  bInCopyCode : BOOL;\nEND_VAR\n"
                "]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[IF NOT bInCopyCode THEN\n"
                "  __DELETE(_pBuffer);\nEND_IF;\nFB_exit := TRUE;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = FbExitContractCheck().run(TwinCATFile(tmp_path / "FB_Good.TcPOU"))
        assert len(issues) == 0

    def test_warn_when_fb_uses_new_but_has_no_fb_exit(self, tmp_path):
        _write_file(
            tmp_path / "FB_NoExit.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_NoExit" Id="{b1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_NoExit\n"
                "VAR\n  _pData : POINTER TO INT;\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[_pData := __NEW(INT);]]></ST></Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = FbExitContractCheck().run(TwinCATFile(tmp_path / "FB_NoExit.TcPOU"))
        assert len(issues) == 1
        assert "uses __NEW() for dynamic allocation but has no FB_exit method" in issues[0].message

    def test_error_when_fb_exit_has_wrong_return_type(self, tmp_path):
        _write_file(
            tmp_path / "FB_BadReturn.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_BadReturn" Id="{c1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_BadReturn\nEND_VAR\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="FB_exit" Id="{c1111111-1111-1111-1111-111111111112}">\n'
                "      <Declaration><![CDATA[METHOD FB_exit\n"  # No return type
                "VAR_INPUT\n  bInCopyCode : BOOL;\nEND_VAR\n"
                "]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = FbExitContractCheck().run(TwinCATFile(tmp_path / "FB_BadReturn.TcPOU"))
        assert len(issues) == 1
        # Parser now supports methods without return type, so check reports actual error
        assert "incorrect return type" in issues[0].message.lower()
        assert "Expected: BOOL" in issues[0].message

    def test_error_when_fb_exit_has_wrong_parameter(self, tmp_path):
        _write_file(
            tmp_path / "FB_BadParam.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_BadParam" Id="{d1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_BadParam\nEND_VAR\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="FB_exit" Id="{d1111111-1111-1111-1111-111111111112}">\n'
                "      <Declaration><![CDATA[METHOD FB_exit : BOOL\n"
                "VAR_INPUT\n  nMode : INT;\nEND_VAR\n"  # Wrong parameter
                "]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[FB_exit := TRUE;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = FbExitContractCheck().run(TwinCATFile(tmp_path / "FB_BadParam.TcPOU"))
        assert len(issues) == 1
        assert "incorrect signature" in issues[0].message

    def test_ignore_new_in_comments(self, tmp_path):
        """Verify comment stripping - __NEW() in comments should not trigger."""
        _write_file(
            tmp_path / "FB_CommentedNew.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_CommentedNew" Id="{e1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_CommentedNew\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[\n"
                "(* Commented out: _pData := __NEW(INT); *)\n"
                "// Also commented: _pBuffer := __NEW(BYTE);\n"
                "]]></ST></Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = FbExitContractCheck().run(TwinCATFile(tmp_path / "FB_CommentedNew.TcPOU"))
        assert len(issues) == 0  # No real __NEW(), comments ignored

    def test_case_insensitive_signature_check(self, tmp_path):
        """Verify case normalization for FB_exit signature."""
        _write_file(
            tmp_path / "FB_MixedCase.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_MixedCase" Id="{f1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_MixedCase\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="FB_exit" Id="{f1111111-1111-1111-1111-111111111112}">\n'
                "      <Declaration><![CDATA[METHOD FB_exit : Bool\n"  # Mixed case
                "VAR_INPUT\n  bInCopyCode : BOOL;\nEND_VAR\n"
                "]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[FB_exit := TRUE;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = FbExitContractCheck().run(TwinCATFile(tmp_path / "FB_MixedCase.TcPOU"))
        # Should pass - "Bool" normalized to "BOOL"
        assert len(issues) == 0


class TestDynamicCreationAttributeCheck:
    """Tests for DynamicCreationAttributeCheck (Phase 5A)."""

    @classmethod
    def setup_class(cls):
        _ensure_phase5a_checks_registered()

    def test_pass_when_target_has_attribute(self, tmp_path):
        # Create target FB with attribute
        _write_file(
            tmp_path / "FB_Motor.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Motor" Id="{g1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[\n"
                "{attribute 'enable_dynamic_creation'}\n"
                "FUNCTION_BLOCK FB_Motor\nVAR\n  _speed : REAL;\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        # Create allocator
        _write_file(
            tmp_path / "FB_Controller.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Controller" Id="{g2222222-2222-2222-2222-222222222222}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Controller\n"
                "VAR\n  pMotor : POINTER TO FB_Motor;\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[pMotor := __NEW(FB_Motor);]]></ST></Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        issues = DynamicCreationAttributeCheck().run(TwinCATFile(tmp_path / "FB_Controller.TcPOU"))
        assert len(issues) == 0

    def test_error_when_target_lacks_attribute(self, tmp_path):
        # Create target FB WITHOUT attribute
        _write_file(
            tmp_path / "FB_Pump.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Pump" Id="{h1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Pump\n"  # NO attribute
                "VAR\n  _flow : REAL;\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        # Create allocator
        _write_file(
            tmp_path / "FB_System.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_System" Id="{h2222222-2222-2222-2222-222222222222}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_System\n"
                "VAR\n  pPump : POINTER TO FB_Pump;\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[pPump := __NEW(FB_Pump);]]></ST></Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )

        issues = DynamicCreationAttributeCheck().run(TwinCATFile(tmp_path / "FB_System.TcPOU"))
        assert len(issues) == 1
        assert "FB_Pump" in issues[0].message
        assert "enable_dynamic_creation" in issues[0].message
        assert issues[0].fix_available is False  # Cross-file issue, can't auto-fix

    def test_ignore_new_in_comments(self, tmp_path):
        """Verify comment stripping for dynamic creation check."""
        _write_file(
            tmp_path / "FB_Commented.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Commented" Id="{i1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Commented\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[\n"
                "(* Old code: pMotor := __NEW(FB_Motor); *)\n"
                "// TODO: pPump := __NEW(FB_Pump);\n"
                "]]></ST></Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = DynamicCreationAttributeCheck().run(TwinCATFile(tmp_path / "FB_Commented.TcPOU"))
        assert len(issues) == 0


class TestPointerDeletePairingCheck:
    """Tests for PointerDeletePairingCheck (Phase 5A)."""

    @classmethod
    def setup_class(cls):
        _ensure_phase5a_checks_registered()

    def test_pass_when_new_and_delete_paired_in_fb_exit(self, tmp_path):
        _write_file(
            tmp_path / "FB_Paired.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Paired" Id="{j1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Paired\n"
                "VAR\n  _pBuffer : POINTER TO INT;\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[_pBuffer := __NEW(INT);]]></ST></Implementation>\n"
                '    <Method Name="FB_exit" Id="{j1111111-1111-1111-1111-111111111112}">\n'
                "      <Declaration><![CDATA[METHOD FB_exit : BOOL\n"
                "VAR_INPUT\n  bInCopyCode : BOOL;\nEND_VAR\n"
                "]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[\n"
                "IF NOT bInCopyCode THEN\n"
                "  IF _pBuffer <> 0 THEN\n"
                "    __DELETE(_pBuffer);\n"
                "  END_IF;\n"
                "END_IF;\n"
                "FB_exit := TRUE;\n"
                "]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = PointerDeletePairingCheck().run(TwinCATFile(tmp_path / "FB_Paired.TcPOU"))
        assert len(issues) == 0

    def test_error_when_new_without_delete(self, tmp_path):
        _write_file(
            tmp_path / "FB_Leak.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Leak" Id="{k1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Leak\n"
                "VAR\n  _pData : POINTER TO BYTE;\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[_pData := __NEW(BYTE);]]></ST></Implementation>\n"
                '    <Method Name="FB_exit" Id="{k1111111-1111-1111-1111-111111111112}">\n'
                "      <Declaration><![CDATA[METHOD FB_exit : BOOL\n"
                "VAR_INPUT\n  bInCopyCode : BOOL;\nEND_VAR\n"
                "]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[FB_exit := TRUE;]]></ST></Implementation>\n"  # No __DELETE!
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = PointerDeletePairingCheck().run(TwinCATFile(tmp_path / "FB_Leak.TcPOU"))
        assert len(issues) == 1
        assert "_pData" in issues[0].message
        assert "lack matching __DELETE()" in issues[0].message

    def test_pass_when_delete_in_custom_cleanup_method(self, tmp_path):
        _write_file(
            tmp_path / "FB_CustomCleanup.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_CustomCleanup" Id="{l1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_CustomCleanup\n"
                "VAR\n  _pResource : POINTER TO INT;\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[_pResource := __NEW(INT);]]></ST></Implementation>\n"
                '    <Method Name="Dispose" Id="{l1111111-1111-1111-1111-111111111112}">\n'
                "      <Declaration><![CDATA[METHOD Dispose\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[\n"
                "IF _pResource <> 0 THEN\n"
                "  __DELETE(_pResource);\n"
                "  _pResource := 0;\n"
                "END_IF;\n"
                "]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = PointerDeletePairingCheck().run(TwinCATFile(tmp_path / "FB_CustomCleanup.TcPOU"))
        assert len(issues) == 0  # Dispose is a default cleanup method

    def test_error_when_no_cleanup_methods_exist(self, tmp_path):
        _write_file(
            tmp_path / "FB_NoCleanup.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_NoCleanup" Id="{m1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_NoCleanup\n"
                "VAR\n  _pItem : POINTER TO INT;\nEND_VAR\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[_pItem := __NEW(INT);]]></ST></Implementation>\n"
                "  </POU>\n"  # No FB_exit, no Dispose, no Cleanup
                "</TcPlcObject>\n"
            ),
        )
        issues = PointerDeletePairingCheck().run(TwinCATFile(tmp_path / "FB_NoCleanup.TcPOU"))
        assert len(issues) == 1
        assert "has no cleanup method" in issues[0].message
        assert "FB_exit" in issues[0].message

    def test_ignore_new_in_comments(self, tmp_path):
        """Verify comment stripping for pointer pairing check."""
        _write_file(
            tmp_path / "FB_OnlyComments.TcPOU",
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_OnlyComments" Id="{n1111111-1111-1111-1111-111111111111}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_OnlyComments\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[\n"
                "(* Legacy: _pOld := __NEW(ST_Data); *)\n"
                "// Future: _pNew := __NEW(ST_Buffer);\n"
                "]]></ST></Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
        )
        issues = PointerDeletePairingCheck().run(TwinCATFile(tmp_path / "FB_OnlyComments.TcPOU"))
        assert len(issues) == 0


class TestOopPolicyConfiguration:
    """Tests for OOP policy configuration normalization (Phase 5A)."""

    def test_normalize_oop_policy_with_phase_5a_keys(self):
        from twincat_validator.config_loader import ValidationConfig

        raw_policy = {
            "enforce_dynamic_creation_attribute": False,
            "enforce_pointer_delete_pairing": True,
            "enforce_fb_exit_contract": False,
            "cleanup_method_names": ["MyDispose", "MyCleanup"],
        }

        normalized = ValidationConfig._normalize_oop_policy(raw_policy)

        assert normalized["enforce_dynamic_creation_attribute"] is False
        assert normalized["enforce_pointer_delete_pairing"] is True
        assert normalized["enforce_fb_exit_contract"] is False
        assert normalized["cleanup_method_names"] == ["MyDispose", "MyCleanup"]
        # Check defaults still present
        assert "enforce_override_super_call" in normalized
        assert "allow_abstract_keyword" in normalized

    def test_normalize_oop_policy_defaults(self):
        from twincat_validator.config_loader import ValidationConfig

        normalized = ValidationConfig._normalize_oop_policy({})

        # Phase 5A defaults
        assert normalized["enforce_dynamic_creation_attribute"] is True
        assert normalized["enforce_pointer_delete_pairing"] is True
        assert normalized["enforce_fb_exit_contract"] is True
        assert normalized["cleanup_method_names"] == ["Dispose", "Cleanup"]
