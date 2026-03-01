"""Contract tests for issue location fields in MCP responses."""

import json

from server import check_specific, validate_file


def _write_bad_file(path):
    path.write_text(
        (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1">\n'
            '  <POU Name="FB_Test" Id="{abcd1234-5678-90ab-cdef-1234567890ab}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test\n"
            "VAR_INPUT\n"
            "  bResetAll : BOOL;\n"
            "END_VAR\n"
            "END_FUNCTION_BLOCK\n"
            "]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[\n"
            "\tbResetAll := FALSE;\n"
            "FOR i := 0 TO nCount - 1 DO\n"
            "END_FOR;\n"
            "]]></ST></Implementation>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        ),
        encoding="utf-8",
    )


def test_validate_file_issues_have_line_and_column_fields(tmp_path):
    bad = tmp_path / "FB_Test.TcPOU"
    _write_bad_file(bad)

    result = json.loads(validate_file(str(bad), profile="full"))
    assert result["success"] is True
    assert isinstance(result["issues"], list)
    assert len(result["issues"]) > 0
    for issue in result["issues"]:
        assert "line_num" in issue
        assert "column" in issue
        assert "known_limitation" in issue
        assert isinstance(issue["line_num"], int)
        assert issue["line_num"] >= 1


def test_check_specific_issues_have_line_and_column_fields(tmp_path):
    bad = tmp_path / "FB_Test.TcPOU"
    _write_bad_file(bad)

    result = json.loads(
        check_specific(
            str(bad),
            ["tabs", "main_var_input_mutation", "unsigned_loop_underflow"],
        )
    )
    assert result["success"] is True
    assert isinstance(result["issues"], list)
    assert len(result["issues"]) > 0
    for issue in result["issues"]:
        assert "line_num" in issue
        assert "column" in issue
        assert "known_limitation" in issue
        assert isinstance(issue["line_num"], int)
        assert issue["line_num"] >= 1
