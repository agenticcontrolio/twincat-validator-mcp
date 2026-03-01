"""
Smoke tests for TwinCAT Validator MCP Server

These tests verify basic functionality:
1. Server can be imported
2. Main function exists and is callable
3. Server can list its tools
4. Basic validation works
"""

import pytest
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "twincat_validator"))


def test_server_imports():
    """Test that server module can be imported."""
    from server import mcp, main

    assert mcp is not None
    assert main is not None
    assert callable(main)


def test_server_has_tools():
    """Test that server has registered MCP tools."""

    # Simple check - verify key tool functions exist
    from server import (
        validate_file,
        autofix_file,
        get_validation_summary,
        generate_skeleton,
        extract_methods_to_xml,
    )

    assert callable(validate_file)
    assert callable(autofix_file)
    assert callable(get_validation_summary)
    assert callable(generate_skeleton)
    assert callable(extract_methods_to_xml)


def test_server_has_resources():
    """Test that server has registered MCP resources."""
    from server import mcp

    # Verify the server object exists - resources are registered via decorators
    assert mcp is not None


def test_validation_rules_constant():
    """Test that VALIDATION_CHECKS constant exists."""
    from server import VALIDATION_CHECKS

    assert VALIDATION_CHECKS is not None
    assert isinstance(VALIDATION_CHECKS, dict)
    assert len(VALIDATION_CHECKS) >= 10, "Expected at least 10 validation checks"

    # Check for key validation rules
    expected_checks = ["guid_format", "indentation", "tabs", "file_ending"]
    for check in expected_checks:
        assert check in VALIDATION_CHECKS, f"Missing validation check: {check}"


def test_validate_with_sample_file():
    """Test validation with a sample TwinCAT file."""
    from server import validate_file

    # Create a simple valid TwinCAT POU for testing
    sample_content = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test
VAR_INPUT
  bEnable : BOOL;
END_VAR]]></Declaration>
    <Implementation>
      <ST><![CDATA[]]></ST>
    </Implementation>
    <LineIds Name="FB_Test">
      <LineId Id="2" Count="0" />
    </LineIds>
  </POU>
</TcPlcObject>"""

    # Write to temp file
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".TcPOU", delete=False, encoding="utf-8"
    ) as f:
        f.write(sample_content)
        temp_path = f.name

    try:
        result_json = validate_file(temp_path)
        result = json.loads(result_json)

        assert result["success"] is True
        assert "validation_status" in result
        assert "issues" in result
        assert "summary" in result

        # Validation status should be one of: passed, failed, warnings
        assert result["validation_status"] in ["passed", "failed", "warnings"]
    finally:
        # Cleanup
        Path(temp_path).unlink(missing_ok=True)


def test_autofix_capability():
    """Test that autofix can be called."""
    from server import autofix_file

    # Create a file with tabs (fixable issue)
    sample_content = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
\t<POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789abc}">
\t\t<Declaration><![CDATA[TEST]]></Declaration>
\t</POU>
</TcPlcObject>"""

    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".TcPOU", delete=False, encoding="utf-8"
    ) as f:
        f.write(sample_content)
        temp_path = f.name

    try:
        result_json = autofix_file(temp_path)
        result = json.loads(result_json)

        assert result["success"] is True
        assert "fixes_applied" in result
        assert "validation_after_fix" in result
        assert "content_changed" in result
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_invalid_file_handling():
    """Test that invalid file paths are handled gracefully."""
    from server import validate_file

    result_json = validate_file("nonexistent_file.TcPOU")
    result = json.loads(result_json)

    assert result["success"] is False
    assert "error" in result


if __name__ == "__main__":
    # Run with pytest
    pytest.main([__file__, "-v"])
