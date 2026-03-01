"""Shared fixtures and helpers for TwinCAT Validator tests."""

import json
from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir():
    """Return path to the test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def valid_tcpou():
    """Return path to a valid .TcPOU fixture file."""
    return FIXTURES_DIR / "valid_fb.TcPOU"


@pytest.fixture
def valid_tcio():
    """Return path to a valid .TcIO fixture file."""
    return FIXTURES_DIR / "valid_interface.TcIO"


@pytest.fixture
def valid_tcdut():
    """Return path to a valid .TcDUT fixture file."""
    return FIXTURES_DIR / "valid_struct.TcDUT"


@pytest.fixture
def valid_tcgvl():
    """Return path to a valid .TcGVL fixture file."""
    return FIXTURES_DIR / "valid_gvl.TcGVL"


@pytest.fixture
def mixed_case_guids_file():
    """Return path to a .TcPOU with mixed-case GUIDs."""
    return FIXTURES_DIR / "mixed_case_guids.TcPOU"


@pytest.fixture
def tabs_and_bad_indent_file():
    """Return path to a .TcPOU with tabs and bad indentation."""
    return FIXTURES_DIR / "tabs_and_bad_indent.TcPOU"


@pytest.fixture
def valid_function():
    """Return path to a valid FUNCTION .TcPOU fixture file."""
    return FIXTURES_DIR / "valid_function.TcPOU"


@pytest.fixture
def valid_program():
    """Return path to a valid PROGRAM .TcPOU fixture file."""
    return FIXTURES_DIR / "valid_program.TcPOU"


@pytest.fixture
def function_with_methods():
    """Return path to an invalid FUNCTION (has methods) .TcPOU fixture."""
    return FIXTURES_DIR / "function_with_methods.TcPOU"


@pytest.fixture
def function_no_return_type():
    """Return path to a FUNCTION missing its return type."""
    return FIXTURES_DIR / "function_no_return_type.TcPOU"


@pytest.fixture
def tmp_tcpou(tmp_path):
    """Factory fixture: create a temp .TcPOU file with given content."""

    def _make(content: str, name: str = "FB_Temp.TcPOU") -> Path:
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        return p

    return _make


def parse_tool_result(result_json: str) -> dict:
    """Parse a JSON string returned by an MCP tool."""
    return json.loads(result_json)
