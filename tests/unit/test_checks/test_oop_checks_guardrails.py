"""Tests for guardrail OOP checks: forbidden_abstract_attribute, hardcoded_dispatch."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from twincat_validator.file_handler import TwinCATFile
from twincat_validator.validators.oop_checks import (
    ForbiddenAbstractAttributeCheck,
    HardcodedDispatchCheck,
)


def _write_tcpou(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _wrap_tcpou(declaration: str, implementation: str = "", name: str = "FB_Test") -> str:
    """Build a minimal well-formed TcPOU XML string."""
    impl_block = (
        f"    <Implementation>\n      <ST><![CDATA[{implementation}]]></ST>\n    </Implementation>\n"
        if implementation is not None
        else ""
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        f'  <POU Name="{name}" Id="{{a0000000-0000-0000-0000-000000000001}}" SpecialFunc="None">\n'
        f"    <Declaration><![CDATA[{declaration}]]></Declaration>\n"
        f"{impl_block}"
        "  </POU>\n"
        "</TcPlcObject>\n"
    )


def _wrap_with_method(fb_decl: str, method_decl: str, method_impl: str = "") -> str:
    """Build a TcPOU with a nested Method element."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <POU Name="FB_Test" Id="{a0000000-0000-0000-0000-000000000001}" SpecialFunc="None">\n'
        f"    <Declaration><![CDATA[{fb_decl}]]></Declaration>\n"
        "    <Implementation>\n"
        "      <ST><![CDATA[]]></ST>\n"
        "    </Implementation>\n"
        '    <Method Name="Execute" Id="{b0000000-0000-0000-0000-000000000001}">\n'
        f"      <Declaration><![CDATA[{method_decl}]]></Declaration>\n"
        f"      <Implementation><ST><![CDATA[{method_impl}]]></ST></Implementation>\n"
        "    </Method>\n"
        "  </POU>\n"
        "</TcPlcObject>\n"
    )


# ---------------------------------------------------------------------------
# ForbiddenAbstractAttributeCheck
# ---------------------------------------------------------------------------


class TestForbiddenAbstractAttributeCheck:
    def test_attribute_abstract_on_method_inline_cdata(self, tmp_path):
        """Pattern on same line as CDATA opener is detected."""
        # The CDATA opener and attribute are on the same XML line
        content = _wrap_with_method(
            fb_decl="FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR",
            method_decl="{attribute 'abstract'}\nMETHOD Execute : BOOL\nVAR_INPUT\nEND_VAR",
        )
        _write_tcpou(tmp_path / "FB_Test.TcPOU", content)
        issues = ForbiddenAbstractAttributeCheck().run(TwinCATFile(tmp_path / "FB_Test.TcPOU"))
        assert len(issues) == 1
        assert "not valid TwinCAT 3 syntax" in issues[0].message

    def test_attribute_abstract_own_line(self, tmp_path):
        """Pattern on its own line inside CDATA is detected."""
        raw = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<TcPlcObject>\n"
            '  <Method Name="Execute">\n'
            "    <Declaration><![CDATA[\n"
            "{attribute 'abstract'}\n"
            "METHOD Execute : BOOL\n"
            "VAR_INPUT\nEND_VAR\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </Method>\n"
            "</TcPlcObject>\n"
        )
        _write_tcpou(tmp_path / "FB_Test.TcPOU", raw)
        issues = ForbiddenAbstractAttributeCheck().run(TwinCATFile(tmp_path / "FB_Test.TcPOU"))
        assert len(issues) == 1

    def test_attribute_abstract_double_quotes(self, tmp_path):
        """Double-quoted form {attribute \"abstract\"} is also detected."""
        content = _wrap_with_method(
            fb_decl="FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR",
            method_decl='{attribute "abstract"}\nMETHOD Execute : BOOL\nVAR_INPUT\nEND_VAR',
        )
        _write_tcpou(tmp_path / "FB_Test.TcPOU", content)
        issues = ForbiddenAbstractAttributeCheck().run(TwinCATFile(tmp_path / "FB_Test.TcPOU"))
        assert len(issues) == 1

    def test_attribute_abstract_extra_whitespace(self, tmp_path):
        """Extra whitespace inside the attribute pragma is still matched."""
        content = _wrap_with_method(
            fb_decl="FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR",
            method_decl="{attribute  'abstract'}\nMETHOD Execute : BOOL\nVAR_INPUT\nEND_VAR",
        )
        _write_tcpou(tmp_path / "FB_Test.TcPOU", content)
        issues = ForbiddenAbstractAttributeCheck().run(TwinCATFile(tmp_path / "FB_Test.TcPOU"))
        assert len(issues) == 1

    def test_multiple_occurrences_single_issue(self, tmp_path):
        """Multiple occurrences in separate CDATA blocks still produce exactly one issue."""
        raw = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<TcPlcObject>\n"
            '  <Method Name="A">\n'
            "    <Declaration><![CDATA[\n"
            "{attribute 'abstract'}\n"
            "METHOD A : BOOL\nVAR_INPUT\nEND_VAR\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </Method>\n"
            '  <Method Name="B">\n'
            "    <Declaration><![CDATA[\n"
            "{attribute 'abstract'}\n"
            "METHOD B : BOOL\nVAR_INPUT\nEND_VAR\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            "  </Method>\n"
            "</TcPlcObject>\n"
        )
        _write_tcpou(tmp_path / "FB_Test.TcPOU", raw)
        issues = ForbiddenAbstractAttributeCheck().run(TwinCATFile(tmp_path / "FB_Test.TcPOU"))
        assert len(issues) == 1
        assert "not valid TwinCAT 3 syntax" in issues[0].message

    def test_st_comment_no_false_positive(self, tmp_path):
        """Pattern inside an ST block comment must NOT trigger the check."""
        content = _wrap_with_method(
            fb_decl="FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR",
            method_decl="METHOD Execute : BOOL\nVAR_INPUT\nEND_VAR",
            method_impl="(* {attribute 'abstract'} is wrong, use METHOD ABSTRACT *)\n",
        )
        _write_tcpou(tmp_path / "FB_Test.TcPOU", content)
        issues = ForbiddenAbstractAttributeCheck().run(TwinCATFile(tmp_path / "FB_Test.TcPOU"))
        assert len(issues) == 0

    def test_line_comment_no_false_positive(self, tmp_path):
        """Pattern inside an ST line comment must NOT trigger the check."""
        content = _wrap_with_method(
            fb_decl="FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR",
            method_decl="METHOD Execute : BOOL\nVAR_INPUT\nEND_VAR",
            method_impl="// {attribute 'abstract'} should not be used here\n",
        )
        _write_tcpou(tmp_path / "FB_Test.TcPOU", content)
        issues = ForbiddenAbstractAttributeCheck().run(TwinCATFile(tmp_path / "FB_Test.TcPOU"))
        assert len(issues) == 0

    def test_method_abstract_keyword_no_error(self, tmp_path):
        """METHOD ABSTRACT keyword syntax does not trigger this check."""
        content = _wrap_with_method(
            fb_decl="FUNCTION_BLOCK ABSTRACT FB_Test\nVAR\nEND_VAR",
            method_decl="METHOD ABSTRACT Execute : BOOL\nVAR_INPUT\nEND_VAR",
        )
        _write_tcpou(tmp_path / "FB_Test.TcPOU", content)
        issues = ForbiddenAbstractAttributeCheck().run(TwinCATFile(tmp_path / "FB_Test.TcPOU"))
        assert len(issues) == 0

    def test_fb_abstract_keyword_no_error(self, tmp_path):
        """FUNCTION_BLOCK ABSTRACT keyword syntax does not trigger this check."""
        content = _wrap_tcpou("FUNCTION_BLOCK ABSTRACT FB_Test\nVAR\nEND_VAR")
        _write_tcpou(tmp_path / "FB_Test.TcPOU", content)
        issues = ForbiddenAbstractAttributeCheck().run(TwinCATFile(tmp_path / "FB_Test.TcPOU"))
        assert len(issues) == 0

    def test_override_attribute_no_false_positive(self, tmp_path):
        """{{attribute 'override'}} must not be flagged."""
        content = _wrap_with_method(
            fb_decl="FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR",
            method_decl="{attribute 'override'}\nMETHOD Execute : BOOL\nVAR_INPUT\nEND_VAR",
        )
        _write_tcpou(tmp_path / "FB_Test.TcPOU", content)
        issues = ForbiddenAbstractAttributeCheck().run(TwinCATFile(tmp_path / "FB_Test.TcPOU"))
        assert len(issues) == 0

    def test_non_tcpou_file_skipped(self, tmp_path):
        """Check skips .TcIO and .TcDUT files."""
        for suffix in (".TcIO", ".TcDUT", ".TcGVL"):
            fname = tmp_path / f"Test{suffix}"
            fname.write_text("{attribute 'abstract'}", encoding="utf-8")
            check = ForbiddenAbstractAttributeCheck()
            assert check.should_skip(TwinCATFile(fname)) is True

    def test_clean_file_no_issue(self, tmp_path):
        """Normal FB with no abstract patterns produces no issues."""
        content = _wrap_tcpou(
            "FUNCTION_BLOCK FB_Test\nVAR\n  nVal : INT;\nEND_VAR",
            "nVal := nVal + 1;",
        )
        _write_tcpou(tmp_path / "FB_Test.TcPOU", content)
        issues = ForbiddenAbstractAttributeCheck().run(TwinCATFile(tmp_path / "FB_Test.TcPOU"))
        assert len(issues) == 0

    def test_fix_suggestion_mentions_keyword(self, tmp_path):
        """fix_suggestion must mention METHOD ABSTRACT."""
        content = _wrap_with_method(
            fb_decl="FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR",
            method_decl="{attribute 'abstract'}\nMETHOD Execute : BOOL\nVAR_INPUT\nEND_VAR",
        )
        _write_tcpou(tmp_path / "FB_Test.TcPOU", content)
        issues = ForbiddenAbstractAttributeCheck().run(TwinCATFile(tmp_path / "FB_Test.TcPOU"))
        assert issues[0].fix_available is False
        assert "METHOD ABSTRACT" in issues[0].fix_suggestion


# ---------------------------------------------------------------------------
# HardcodedDispatchCheck
# ---------------------------------------------------------------------------


class TestHardcodedDispatchCheck:
    def test_two_literals_same_method_is_warning(self, tmp_path):
        """Two consecutive index calls on same array/method triggers warning."""
        content = _wrap_tcpou(
            "PROGRAM PRG_Test\nVAR\nEND_VAR",
            "arrUnits[1].M_Reset();\narrUnits[2].M_Reset();\n",
            name="PRG_Test",
        )
        _write_tcpou(tmp_path / "PRG_Test.TcPOU", content)
        issues = HardcodedDispatchCheck().run(TwinCATFile(tmp_path / "PRG_Test.TcPOU"))
        assert len(issues) == 1
        assert "Hardcoded array-index dispatch" in issues[0].message
        assert issues[0].severity == "warning"

    def test_three_literals_same_method_is_warning(self, tmp_path):
        """Three consecutive index calls also fire."""
        content = _wrap_tcpou(
            "PROGRAM PRG_Test\nVAR\nEND_VAR",
            "arrUnits[1].M_Reset();\narrUnits[2].M_Reset();\narrUnits[3].M_Reset();\n",
            name="PRG_Test",
        )
        _write_tcpou(tmp_path / "PRG_Test.TcPOU", content)
        issues = HardcodedDispatchCheck().run(TwinCATFile(tmp_path / "PRG_Test.TcPOU"))
        assert len(issues) == 1
        assert "3 literals" in issues[0].message

    def test_single_literal_no_warning(self, tmp_path):
        """A single indexed call (one literal) does not fire."""
        content = _wrap_tcpou(
            "PROGRAM PRG_Test\nVAR\nEND_VAR",
            "arrUnits[1].M_Reset();\n",
            name="PRG_Test",
        )
        _write_tcpou(tmp_path / "PRG_Test.TcPOU", content)
        issues = HardcodedDispatchCheck().run(TwinCATFile(tmp_path / "PRG_Test.TcPOU"))
        assert len(issues) == 0

    def test_different_methods_no_cross_contamination(self, tmp_path):
        """arr[1].M_A and arr[1].M_B with one literal each do not fire."""
        content = _wrap_tcpou(
            "PROGRAM PRG_Test\nVAR\nEND_VAR",
            "arrUnits[1].M_Start();\narrUnits[1].M_Stop();\n",
            name="PRG_Test",
        )
        _write_tcpou(tmp_path / "PRG_Test.TcPOU", content)
        issues = HardcodedDispatchCheck().run(TwinCATFile(tmp_path / "PRG_Test.TcPOU"))
        assert len(issues) == 0

    def test_different_array_bases_no_cross_contamination(self, tmp_path):
        """a[1].M_Do and b[2].M_Do use different bases — no flag."""
        content = _wrap_tcpou(
            "PROGRAM PRG_Test\nVAR\nEND_VAR",
            "arrMotors[1].M_Do();\narrPumps[2].M_Do();\n",
            name="PRG_Test",
        )
        _write_tcpou(tmp_path / "PRG_Test.TcPOU", content)
        issues = HardcodedDispatchCheck().run(TwinCATFile(tmp_path / "PRG_Test.TcPOU"))
        assert len(issues) == 0

    def test_variable_index_no_warning(self, tmp_path):
        """arr[i].M_Do() uses a variable index — not flagged."""
        content = _wrap_tcpou(
            "PROGRAM PRG_Test\nVAR\n  i : INT;\nEND_VAR",
            "FOR i := 1 TO 4 DO\n  arrUnits[i].M_Reset();\nEND_FOR\n",
            name="PRG_Test",
        )
        _write_tcpou(tmp_path / "PRG_Test.TcPOU", content)
        issues = HardcodedDispatchCheck().run(TwinCATFile(tmp_path / "PRG_Test.TcPOU"))
        assert len(issues) == 0

    def test_comment_stripped_before_scan(self, tmp_path):
        """Calls inside ST comments are not counted."""
        content = _wrap_tcpou(
            "PROGRAM PRG_Test\nVAR\nEND_VAR",
            (
                "// arrUnits[1].M_Reset();\n"
                "(* arrUnits[2].M_Reset(); *)\n"
                "arrUnits[1].M_Start();\n"
            ),
            name="PRG_Test",
        )
        _write_tcpou(tmp_path / "PRG_Test.TcPOU", content)
        issues = HardcodedDispatchCheck().run(TwinCATFile(tmp_path / "PRG_Test.TcPOU"))
        assert len(issues) == 0

    def test_method_body_also_scanned(self, tmp_path):
        """Hardcoded dispatch inside a method implementation is also caught."""
        content = _wrap_with_method(
            fb_decl="FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR",
            method_decl="METHOD M_RunAll : BOOL\nVAR_INPUT\nEND_VAR",
            method_impl="arrUnits[1].M_Reset();\narrUnits[2].M_Reset();\n",
        )
        _write_tcpou(tmp_path / "FB_Test.TcPOU", content)
        issues = HardcodedDispatchCheck().run(TwinCATFile(tmp_path / "FB_Test.TcPOU"))
        assert len(issues) == 1

    def test_non_tcpou_skipped(self, tmp_path):
        """Check skips non-.TcPOU files."""
        for suffix in (".TcIO", ".TcDUT", ".TcGVL"):
            fname = tmp_path / f"Test{suffix}"
            fname.write_text("arrUnits[1].M_Reset();\narrUnits[2].M_Reset();\n", encoding="utf-8")
            check = HardcodedDispatchCheck()
            assert check.should_skip(TwinCATFile(fname)) is True

    def test_clean_prg_no_warning(self, tmp_path):
        """Normal PRG with FOR-loop dispatch produces no issues."""
        content = _wrap_tcpou(
            "PROGRAM PRG_Test\nVAR\n  i : INT;\nEND_VAR",
            "FOR i := 1 TO nCount DO\n  arrUnits[i].M_Reset();\nEND_FOR\n",
            name="PRG_Test",
        )
        _write_tcpou(tmp_path / "PRG_Test.TcPOU", content)
        issues = HardcodedDispatchCheck().run(TwinCATFile(tmp_path / "PRG_Test.TcPOU"))
        assert len(issues) == 0

    def test_fix_suggestion_mentions_for_loop(self, tmp_path):
        """fix_suggestion must mention FOR loop pattern."""
        content = _wrap_tcpou(
            "PROGRAM PRG_Test\nVAR\nEND_VAR",
            "arrUnits[1].M_Reset();\narrUnits[2].M_Reset();\n",
            name="PRG_Test",
        )
        _write_tcpou(tmp_path / "PRG_Test.TcPOU", content)
        issues = HardcodedDispatchCheck().run(TwinCATFile(tmp_path / "PRG_Test.TcPOU"))
        assert issues[0].fix_available is False
        assert "FOR" in issues[0].fix_suggestion

    def test_guarded_unrolled_reset_dispatch_is_suppressed(self, tmp_path):
        """Explicit edge-gated unrolled reset dispatch is accepted as compatibility path."""
        content = _wrap_tcpou(
            "PROGRAM PRG_Test\nVAR\n  bRetryEdge : BOOL;\n  bRetryEdgePrev : BOOL;\nEND_VAR",
            (
                "IF bRetryEdge AND NOT bRetryEdgePrev THEN\n"
                "  arrUnits[1].M_Reset();\n"
                "  arrUnits[2].M_Reset();\n"
                "END_IF;\n"
            ),
            name="PRG_Test",
        )
        _write_tcpou(tmp_path / "PRG_Test.TcPOU", content)
        issues = HardcodedDispatchCheck().run(TwinCATFile(tmp_path / "PRG_Test.TcPOU"))
        assert len(issues) == 0

    def test_unrolled_non_reset_dispatch_not_suppressed(self, tmp_path):
        """Suppression is only for guarded M_Reset compatibility path."""
        content = _wrap_tcpou(
            "PROGRAM PRG_Test\nVAR\n  bRetryEdge : BOOL;\n  bRetryEdgePrev : BOOL;\nEND_VAR",
            (
                "IF bRetryEdge AND NOT bRetryEdgePrev THEN\n"
                "  arrUnits[1].M_Execute();\n"
                "  arrUnits[2].M_Execute();\n"
                "END_IF;\n"
            ),
            name="PRG_Test",
        )
        _write_tcpou(tmp_path / "PRG_Test.TcPOU", content)
        issues = HardcodedDispatchCheck().run(TwinCATFile(tmp_path / "PRG_Test.TcPOU"))
        assert len(issues) == 1
