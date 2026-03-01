"""Tests for MCP prompt registration and rendering.

Each prompt must:
  (a) be registered with the MCP server
  (b) render without error given valid arguments
  (c) include key tool names or workflow instructions in output
"""

import asyncio
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mcp_server():
    """Import the server so all prompts are registered."""
    from twincat_validator.server import mcp

    return mcp


@pytest.fixture(scope="module")
def registered_prompt_names(mcp_server):
    """Return the set of registered prompt names."""
    return {p.name for p in mcp_server._prompt_manager.list_prompts()}


# ---------------------------------------------------------------------------
# B1 — All 8 prompts registered
# ---------------------------------------------------------------------------


EXPECTED_PROMPTS = {
    "validate_and_fix",
    "prepare_for_import",
    "check_oop_compliance",
    "batch_normalize",
    "check_naming_only",
    "fix_then_verify",
    "generate_and_validate",
    "explain_check",
}


def test_all_prompts_are_registered(registered_prompt_names):
    """Every prompt defined in prompts.py must appear in the MCP server's prompt list."""
    missing = EXPECTED_PROMPTS - registered_prompt_names
    assert not missing, f"Prompts defined but not registered: {missing}"


def test_no_unexpected_prompts(registered_prompt_names):
    """Prompt registry should not contain undocumented prompts."""
    extra = registered_prompt_names - EXPECTED_PROMPTS
    assert not extra, f"Unexpected prompts registered: {extra}"


def test_prompt_count(mcp_server):
    """Exactly 8 prompts must be registered (one per workflow)."""
    count = len(mcp_server._prompt_manager.list_prompts())
    assert count == 8, f"Expected 8 prompts, got {count}"


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------


def _render(mcp_server, name: str, args: dict) -> str:
    """Synchronously render a prompt and return the text of the first message."""
    messages = asyncio.get_event_loop().run_until_complete(
        mcp_server._prompt_manager.render_prompt(name, args)
    )
    assert messages, f"Prompt '{name}' returned no messages"
    content = messages[0].content
    # Content is a TextContent object with a .text attribute
    return content.text if hasattr(content, "text") else str(content)


# ---------------------------------------------------------------------------
# Per-prompt render + content tests
# ---------------------------------------------------------------------------


class TestValidateAndFixPrompt:
    def test_renders_without_error(self, mcp_server):
        text = _render(mcp_server, "validate_and_fix", {"file_path": "/tmp/FB_Test.TcPOU"})
        assert isinstance(text, str) and len(text) > 0

    def test_contains_validate_file_tool(self, mcp_server):
        text = _render(mcp_server, "validate_and_fix", {"file_path": "/tmp/FB_Test.TcPOU"})
        assert "validate_file" in text

    def test_contains_autofix_file_tool(self, mcp_server):
        text = _render(mcp_server, "validate_and_fix", {"file_path": "/tmp/FB_Test.TcPOU"})
        assert "autofix_file" in text

    def test_optional_level_defaults_to_all(self, mcp_server):
        text = _render(mcp_server, "validate_and_fix", {"file_path": "/tmp/FB_Test.TcPOU"})
        assert "'all'" in text

    def test_custom_level_respected(self, mcp_server):
        text = _render(
            mcp_server,
            "validate_and_fix",
            {"file_path": "/tmp/FB.TcPOU", "validation_level": "critical"},
        )
        assert "'critical'" in text


class TestPrepareForImportPrompt:
    def test_renders_without_error(self, mcp_server):
        text = _render(mcp_server, "prepare_for_import", {"file_path": "/tmp/FB_Test.TcPOU"})
        assert isinstance(text, str) and len(text) > 0

    def test_contains_validate_for_import_tool(self, mcp_server):
        text = _render(mcp_server, "prepare_for_import", {"file_path": "/tmp/FB_Test.TcPOU"})
        assert "validate_for_import" in text

    def test_contains_file_path_in_output(self, mcp_server):
        text = _render(mcp_server, "prepare_for_import", {"file_path": "/tmp/FB_Special.TcPOU"})
        assert "/tmp/FB_Special.TcPOU" in text


class TestCheckOopCompliancePrompt:
    def test_renders_without_error(self, mcp_server):
        text = _render(mcp_server, "check_oop_compliance", {"file_path": "/tmp/FB_Test.TcPOU"})
        assert isinstance(text, str) and len(text) > 0

    def test_contains_validate_file_tool(self, mcp_server):
        text = _render(mcp_server, "check_oop_compliance", {"file_path": "/tmp/FB_Test.TcPOU"})
        assert "validate_file" in text

    def test_contains_check_specific_tool(self, mcp_server):
        text = _render(mcp_server, "check_oop_compliance", {"file_path": "/tmp/FB_Test.TcPOU"})
        assert "check_specific" in text

    def test_lists_oop_checks(self, mcp_server):
        text = _render(mcp_server, "check_oop_compliance", {"file_path": "/tmp/FB_Test.TcPOU"})
        assert "override_marker" in text
        assert "composition_depth" in text


class TestBatchNormalizePrompt:
    def test_renders_without_error(self, mcp_server):
        text = _render(mcp_server, "batch_normalize", {"directory_path": "/tmp/plc"})
        assert isinstance(text, str) and len(text) > 0

    def test_contains_autofix_batch_tool(self, mcp_server):
        text = _render(mcp_server, "batch_normalize", {"directory_path": "/tmp/plc"})
        assert "autofix_batch" in text

    def test_contains_twincat_canonical_profile(self, mcp_server):
        text = _render(mcp_server, "batch_normalize", {"directory_path": "/tmp/plc"})
        assert "twincat_canonical" in text


class TestCheckNamingOnlyPrompt:
    def test_renders_without_error(self, mcp_server):
        text = _render(mcp_server, "check_naming_only", {"file_path": "/tmp/FB_Test.TcPOU"})
        assert isinstance(text, str) and len(text) > 0

    def test_contains_check_specific_tool(self, mcp_server):
        text = _render(mcp_server, "check_naming_only", {"file_path": "/tmp/FB_Test.TcPOU"})
        assert "check_specific" in text

    def test_lists_naming_prefixes(self, mcp_server):
        text = _render(mcp_server, "check_naming_only", {"file_path": "/tmp/FB_Test.TcPOU"})
        assert "FB_" in text
        assert "I_" in text


class TestFixThenVerifyPrompt:
    def test_renders_without_error(self, mcp_server):
        text = _render(mcp_server, "fix_then_verify", {"file_path": "/tmp/FB_Test.TcPOU"})
        assert isinstance(text, str) and len(text) > 0

    def test_contains_autofix_file_tool(self, mcp_server):
        text = _render(mcp_server, "fix_then_verify", {"file_path": "/tmp/FB_Test.TcPOU"})
        assert "autofix_file" in text

    def test_contains_validate_file_tool(self, mcp_server):
        text = _render(mcp_server, "fix_then_verify", {"file_path": "/tmp/FB_Test.TcPOU"})
        assert "validate_file" in text

    def test_contains_pass_fail_verdict(self, mcp_server):
        text = _render(mcp_server, "fix_then_verify", {"file_path": "/tmp/FB_Test.TcPOU"})
        assert "PASS" in text
        assert "FAIL" in text


class TestGenerateAndValidatePrompt:
    def test_renders_without_error(self, mcp_server):
        text = _render(mcp_server, "generate_and_validate", {"file_type": "TcPOU"})
        assert isinstance(text, str) and len(text) > 0

    def test_contains_generate_skeleton_tool(self, mcp_server):
        text = _render(mcp_server, "generate_and_validate", {"file_type": "TcPOU"})
        assert "generate_skeleton" in text

    def test_contains_validate_file_tool(self, mcp_server):
        text = _render(mcp_server, "generate_and_validate", {"file_type": "TcPOU"})
        assert "validate_file" in text

    def test_output_path_included_when_provided(self, mcp_server):
        text = _render(
            mcp_server,
            "generate_and_validate",
            {"file_type": "TcPOU", "output_path": "/tmp/FB_New.TcPOU"},
        )
        assert "/tmp/FB_New.TcPOU" in text


class TestExplainCheckPrompt:
    def test_renders_without_error(self, mcp_server):
        text = _render(mcp_server, "explain_check", {"check_id": "guid_format"})
        assert isinstance(text, str) and len(text) > 0

    def test_contains_check_id_in_output(self, mcp_server):
        text = _render(mcp_server, "explain_check", {"check_id": "override_marker"})
        assert "override_marker" in text

    def test_contains_knowledge_base_uri(self, mcp_server):
        text = _render(mcp_server, "explain_check", {"check_id": "guid_format"})
        assert "knowledge-base://checks/guid_format" in text
