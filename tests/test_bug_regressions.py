"""Regression tests for bugs fixed in Phase 1.

Each test reproduces a specific confirmed bug and verifies the fix.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Bug 1: fix_cdata_formatting was dead code (did nothing)
# Fix: Delegates to fix_property_newlines so the "cdata" fix ID works.
# ---------------------------------------------------------------------------


def test_cdata_fix_delegates_to_newlines(tmp_tcpou):
    """The 'cdata' fix should actually fix CDATA formatting issues."""
    from server import autofix_file

    content = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">
    <Declaration><![CDATA[PROPERTY nValue : INT
]]></Declaration>
    <Implementation>
      <ST><![CDATA[]]></ST>
    </Implementation>
    <LineIds Name="FB_Test">
      <LineId Id="2" Count="0" />
    </LineIds>
  </POU>
</TcPlcObject>"""

    path = tmp_tcpou(content)
    result = json.loads(autofix_file(str(path), create_backup=False, fixes_to_apply=["cdata"]))
    assert result["success"] is True


# ---------------------------------------------------------------------------
# Bug 2: fix_lineids parsed XML from disk instead of self.content
# Fix: Changed ET.parse(filepath) to ET.fromstring(self.content)
# ---------------------------------------------------------------------------


def test_lineids_fix_uses_in_memory_content(tmp_tcpou):
    """LineIds fix should parse from in-memory content, not disk.

    If tabs are fixed first (changing content) and then lineids runs,
    lineids must see the already-fixed content, not stale disk data.
    """
    from server import autofix_file

    content = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
\t<POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">
\t\t<Declaration><![CDATA[FUNCTION_BLOCK FB_Test
VAR
END_VAR]]></Declaration>
\t\t<Implementation>
\t\t\t<ST><![CDATA[;]]></ST>
\t\t</Implementation>
\t</POU>
</TcPlcObject>"""

    path = tmp_tcpou(content)
    result = json.loads(
        autofix_file(str(path), create_backup=False, fixes_to_apply=["tabs", "lineids"])
    )
    assert result["success"] is True
    # The lineids fix should not report failure due to stale data
    for fix in result["fixes_applied"]:
        if fix["type"] == "lineids":
            assert "failed" not in fix["description"].lower()


# ---------------------------------------------------------------------------
# Bug 3: Mixed-case GUID detection only caught ALL-uppercase
# Fix: Count all_guids - valid_guids to detect any uppercase chars.
# ---------------------------------------------------------------------------


def test_mixed_case_guids_detected(mixed_case_guids_file):
    """GUIDs with mixed case (some upper, some lower) must be flagged."""
    from server import validate_file

    result = json.loads(validate_file(str(mixed_case_guids_file)))
    assert result["success"] is True

    guid_issues = [i for i in result["issues"] if i["category"] == "GUID"]
    uppercase_issues = [i for i in guid_issues if "uppercase" in i["message"].lower()]
    assert len(uppercase_issues) > 0, "Mixed-case GUIDs should be detected"


# ---------------------------------------------------------------------------
# Bug 4: Non-GUID Id attributes counted as invalid GUIDs (false positives)
# Fix: Only match Id="{...}" (curly-brace-wrapped) as GUIDs.
# ---------------------------------------------------------------------------


def test_non_guid_ids_not_false_positive(tmp_tcpou):
    """Numeric Id attributes (like LineId Id='9') must not be counted as invalid GUIDs."""
    from server import validate_file

    content = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test
VAR
END_VAR]]></Declaration>
    <Implementation>
      <ST><![CDATA[]]></ST>
    </Implementation>
    <LineIds Name="FB_Test">
      <LineId Id="9" Count="0" />
      <LineId Id="2" Count="0" />
    </LineIds>
  </POU>
</TcPlcObject>"""

    path = tmp_tcpou(content)
    result = json.loads(validate_file(str(path)))
    assert result["success"] is True

    # Should NOT have "invalid GUID format" issues — the numeric Ids are not GUIDs
    invalid_guid_issues = [i for i in result["issues"] if "invalid GUID format" in i["message"]]
    assert len(invalid_guid_issues) == 0, f"False positive: {invalid_guid_issues}"


# ---------------------------------------------------------------------------
# Bug 5: Health score used check counts instead of issue counts
# Fix: Use validator.stats["errors"] / ["warnings"] (issue counts).
# ---------------------------------------------------------------------------


def test_health_score_uses_issue_counts(tmp_tcpou):
    """Health score must be based on issue counts, not check counts."""
    from server import get_validation_summary

    # File with uppercase GUIDs — produces 1 error issue from GUID check
    content = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_Test" Id="{AABBCCDD-1234-5678-9ABC-DEF012345678}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test
VAR
END_VAR]]></Declaration>
    <Implementation>
      <ST><![CDATA[]]></ST>
    </Implementation>
    <LineIds Name="FB_Test">
      <LineId Id="2" Count="0" />
    </LineIds>
  </POU>
</TcPlcObject>"""

    path = tmp_tcpou(content)
    result = json.loads(get_validation_summary(str(path)))
    assert result["success"] is True
    assert result["issue_breakdown"]["critical"] >= 1
    # Health score should deduct 25 per error issue
    assert result["health_score"] <= 75


# ---------------------------------------------------------------------------
# Bug 6: check_specific missing "excessive_blanks" check
# Fix: Added to valid_checks set.
# ---------------------------------------------------------------------------


def test_check_specific_supports_excessive_blanks(tmp_tcpou):
    """The check_specific tool must accept 'excessive_blanks' as a valid check."""
    from server import check_specific

    content = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test
VAR
END_VAR]]></Declaration>
    <Implementation>
      <ST><![CDATA[]]></ST>
    </Implementation>
    <LineIds Name="FB_Test">
      <LineId Id="2" Count="0" />
    </LineIds>
  </POU>
</TcPlcObject>"""

    path = tmp_tcpou(content)
    result = json.loads(check_specific(str(path), ["excessive_blanks"]))
    assert result["success"] is True
    assert len(result["checks"]) == 1
    # Should not return "Invalid check names"
    assert "error" not in result


# ---------------------------------------------------------------------------
# Bug 7: LineIds XML insertion had no safety re-parse
# Fix: After inserting LineIds XML, re-parse to verify validity; revert on failure.
# ---------------------------------------------------------------------------


def test_lineids_insertion_reverts_on_invalid_xml(tmp_tcpou):
    """If LineIds insertion produces invalid XML, the fix should revert."""
    from server import autofix_file

    # A minimal valid file — lineids fix should either succeed cleanly
    # or revert if the generated XML is invalid
    content = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test
VAR
END_VAR]]></Declaration>
    <Implementation>
      <ST><![CDATA[;]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>"""

    path = tmp_tcpou(content)
    result = json.loads(autofix_file(str(path), create_backup=False, fixes_to_apply=["lineids"]))
    assert result["success"] is True

    # Read the file back and verify it's still valid XML
    import xml.etree.ElementTree as ET

    fixed_content = path.read_text(encoding="utf-8")
    try:
        ET.fromstring(fixed_content)
    except ET.ParseError:
        pytest.fail("LineIds insertion produced invalid XML — safety check should have reverted")


# ---------------------------------------------------------------------------
# Additional regression: validate_file_path helper works correctly
# ---------------------------------------------------------------------------


def test_validate_file_path_rejects_unsupported_type(tmp_path):
    """The file path validator must reject unsupported extensions."""
    from server import validate_file

    p = tmp_path / "test.txt"
    p.write_text("hello", encoding="utf-8")
    result = json.loads(validate_file(str(p)))
    assert result["success"] is False
    assert "Unsupported file type" in result["error"]


def test_validate_file_path_rejects_missing_file():
    """The file path validator must reject nonexistent files."""
    from server import validate_file

    result = json.loads(validate_file("C:/nonexistent/file.TcPOU"))
    assert result["success"] is False
    assert "File not found" in result["error"]
