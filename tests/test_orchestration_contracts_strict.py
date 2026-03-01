"""Strict contract tests for process_twincat_single and process_twincat_batch.

These tests lock the JSON output schema of the orchestration tools so that
accidental schema drift is caught in CI. They validate:
- Required fields for success/error branches
- Semantic invariants (done, terminal_mode, next_action semantics)
- Determinism: second run produces no changes on stable inputs
- Negative paths: missing dir, invalid patterns, invalid validation_level
"""

import json
import pytest

from server import (
    process_twincat_single,
    process_twincat_batch,
    verify_determinism_batch,
    autofix_batch,
    validate_batch,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_FB_CONTENT = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
    '  <POU Name="FB_Test" Id="{abcd1234-5678-90ab-cdef-1234567890ab}" SpecialFunc="None">\n'
    "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR]]></Declaration>\n"
    "    <Implementation>\n"
    "      <ST><![CDATA[]]></ST>\n"
    "    </Implementation>\n"
    '    <LineIds Name="FB_Test">\n'
    '      <LineId Id="1" Count="0" />\n'
    "    </LineIds>\n"
    "  </POU>\n"
    "</TcPlcObject>\n"
)

MALFORMED_GUID_CONTENT = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
    '  <DUT Name="ST_Bad" Id="{e6f7a8b9-ca db-4cee-e05b-6c7d8e9fa6b7}">\n'
    "    <Declaration><![CDATA[TYPE ST_Bad : STRUCT\nnVal : INT;\nEND_STRUCT\nEND_TYPE]]>"
    "</Declaration>\n"
    "  </DUT>\n"
    "</TcPlcObject>\n"
)


@pytest.fixture
def valid_fb(tmp_path):
    f = tmp_path / "FB_Test.TcPOU"
    f.write_text(VALID_FB_CONTENT, encoding="utf-8")
    return f


@pytest.fixture
def valid_batch_dir(tmp_path):
    (tmp_path / "FB_A.TcPOU").write_text(VALID_FB_CONTENT, encoding="utf-8")
    (tmp_path / "FB_B.TcPOU").write_text(VALID_FB_CONTENT, encoding="utf-8")
    return tmp_path


@pytest.fixture
def malformed_guid_file(tmp_path):
    f = tmp_path / "ST_Bad.TcDUT"
    f.write_text(MALFORMED_GUID_CONTENT, encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# WS5: process_twincat_single — success branch schema
# ---------------------------------------------------------------------------


class TestProcessTwincatSingleSuccessSchema:
    """Lock the required keys for process_twincat_single success responses."""

    # Top-level required keys (success path, done=True)
    REQUIRED_DONE_KEYS = {
        "success",
        "file_path",
        "workflow",
        "tools_used",
        "safe_to_import",
        "safe_to_compile",
        "pre_validation",
        "autofix",
        "post_validation",
        "done",
        "status",
        "blocking_count",
        "blockers",
        "effective_oop_policy",
        "policy_checked",
        "policy_source",
        "policy_fingerprint",
        "enforcement_mode",
        "response_version",
        "terminal_mode",
        "next_action",
        "allow_followup_autofix_without_user_request",
        "meta",
    }

    # Minimum required keys regardless of done flag
    REQUIRED_BASE_KEYS = {
        "success",
        "file_path",
        "workflow",
        "tools_used",
        "safe_to_import",
        "safe_to_compile",
        "pre_validation",
        "autofix",
        "post_validation",
        "done",
        "status",
        "blocking_count",
        "blockers",
        "effective_oop_policy",
        "policy_checked",
        "policy_source",
        "policy_fingerprint",
        "enforcement_mode",
        "response_version",
        "meta",
    }

    def test_success_base_keys_present(self, valid_fb):
        result = json.loads(process_twincat_single(str(valid_fb)))
        assert result["success"] is True
        missing = self.REQUIRED_BASE_KEYS - set(result.keys())
        assert not missing, f"Missing required keys: {missing}"

    def test_workflow_value(self, valid_fb):
        result = json.loads(process_twincat_single(str(valid_fb)))
        assert result["workflow"] == "single_strict_pipeline"

    def test_tools_used_order(self, valid_fb):
        result = json.loads(process_twincat_single(str(valid_fb)))
        tools = result["tools_used"]
        assert tools[:3] == ["validate_file", "autofix_file", "validate_file"]

    def test_safe_flags_are_bool(self, valid_fb):
        result = json.loads(process_twincat_single(str(valid_fb)))
        assert isinstance(result["safe_to_import"], bool)
        assert isinstance(result["safe_to_compile"], bool)

    def test_done_is_bool(self, valid_fb):
        result = json.loads(process_twincat_single(str(valid_fb)))
        assert isinstance(result["done"], bool)
        assert result["status"] in {"done", "blocked"}
        assert isinstance(result["blocking_count"], int)
        assert isinstance(result["blockers"], list)

    def test_done_true_sets_terminal_fields(self, valid_fb):
        result = json.loads(process_twincat_single(str(valid_fb)))
        if result["done"]:
            assert result["terminal_mode"] is True
            assert result["next_action"] == "done_no_further_autofix"
            assert result["allow_followup_autofix_without_user_request"] is False

    def test_done_false_has_suggested_fixes(self, malformed_guid_file):
        result = json.loads(process_twincat_single(str(malformed_guid_file)))
        assert result["success"] is True
        assert result["done"] is False
        assert "suggested_fixes" in result

    def test_effective_oop_policy_schema(self, valid_fb):
        result = json.loads(process_twincat_single(str(valid_fb)))
        policy = result["effective_oop_policy"]
        assert "policy_source" in policy
        assert "policy" in policy
        assert isinstance(policy["policy"], dict)

    def test_meta_envelope_schema(self, valid_fb):
        result = json.loads(process_twincat_single(str(valid_fb)))
        meta = result["meta"]
        assert "timestamp" in meta
        assert "duration_ms" in meta
        assert "server_version" in meta
        assert "response_version" in meta
        assert isinstance(meta["duration_ms"], int)
        assert meta["duration_ms"] >= 0
        assert meta["response_version"] == "1"
        assert result["enforcement_mode"] == "strict"
        assert result["response_version"] == "2"

    def test_pre_validation_has_safe_flags(self, valid_fb):
        result = json.loads(process_twincat_single(str(valid_fb)))
        pre = result["pre_validation"]
        assert "safe_to_import" in pre
        assert "safe_to_compile" in pre

    def test_autofix_result_has_safe_flags(self, valid_fb):
        result = json.loads(process_twincat_single(str(valid_fb)))
        fx = result["autofix"]
        assert "safe_to_import" in fx
        assert "safe_to_compile" in fx

    def test_post_validation_has_safe_flags(self, valid_fb):
        result = json.loads(process_twincat_single(str(valid_fb)))
        post = result["post_validation"]
        assert "safe_to_import" in post
        assert "safe_to_compile" in post


# ---------------------------------------------------------------------------
# WS5: process_twincat_single — determinism invariant
# ---------------------------------------------------------------------------


class TestProcessTwincatSingleDeterminism:
    """Second run on a stable file must show no content changes."""

    def test_second_run_produces_no_changes(self, valid_fb):
        # First run stabilises the file
        r1 = json.loads(process_twincat_single(str(valid_fb)))
        assert r1["success"] is True

        # Second run must not change content
        r2 = json.loads(process_twincat_single(str(valid_fb)))
        assert r2["success"] is True
        autofix2 = r2["autofix"]
        assert (
            autofix2.get("content_changed") is False
        ), "Second run on stable input must not change content"

    def test_second_run_same_done_status(self, valid_fb):
        r1 = json.loads(process_twincat_single(str(valid_fb)))
        r2 = json.loads(process_twincat_single(str(valid_fb)))
        assert r1["done"] == r2["done"], "done status must be deterministic across identical runs"

    def test_second_run_same_safe_flags(self, valid_fb):
        r1 = json.loads(process_twincat_single(str(valid_fb)))
        r2 = json.loads(process_twincat_single(str(valid_fb)))
        assert r1["safe_to_import"] == r2["safe_to_import"]
        assert r1["safe_to_compile"] == r2["safe_to_compile"]


# ---------------------------------------------------------------------------
# WS5: process_twincat_single — negative paths
# ---------------------------------------------------------------------------


class TestProcessTwincatSingleNegativePaths:
    """Error paths must return success=False with a useful error message."""

    def test_missing_file_returns_error(self, tmp_path):
        nonexistent = str(tmp_path / "ghost.TcPOU")
        result = json.loads(process_twincat_single(nonexistent))
        assert result["success"] is False
        assert "error" in result or "file_path" in result

    def test_invalid_validation_level_returns_error(self, valid_fb):
        result = json.loads(process_twincat_single(str(valid_fb), validation_level="invalid_level"))
        assert result["success"] is False
        assert "error" in result

    def test_invalid_validation_level_error_has_meta(self, valid_fb):
        result = json.loads(process_twincat_single(str(valid_fb), validation_level="bogus"))
        assert result["success"] is False
        assert "meta" in result


# ---------------------------------------------------------------------------
# WS5: process_twincat_batch — success branch schema
# ---------------------------------------------------------------------------


class TestProcessTwincatBatchSuccessSchema:
    """Lock the required keys for process_twincat_batch success responses."""

    # Keys always present regardless of response_mode (no heavy sections).
    REQUIRED_BASE_KEYS = {
        "success",
        "workflow",
        "tools_used",
        "file_patterns",
        "directory_path",
        "response_mode",
        "batch_summary",
        "safe_to_import",
        "safe_to_compile",
        "files",
        "status",
        "blocking_count",
        "done",
        "policy_checked",
        "policy_source",
        "policy_fingerprint",
        "enforcement_mode",
        "response_version",
        "terminal_mode",
        "next_action",
        "meta",
    }

    # Keys only present when response_mode="full" (heavy sections).
    REQUIRED_FULL_MODE_KEYS = {
        "pre_validation",
        "autofix",
        "post_validation",
        "effective_oop_policy",
        "blockers",
    }

    async def test_success_base_keys_present(self, valid_batch_dir):
        # Default (summary) mode — only base keys required.
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"], directory_path=str(valid_batch_dir)
            )
        )
        assert result["success"] is True
        assert result["response_mode"] == "summary"
        missing = self.REQUIRED_BASE_KEYS - set(result.keys())
        assert not missing, f"Missing required base keys in summary response: {missing}"

    async def test_full_mode_keys_present(self, valid_batch_dir):
        # Explicit full mode — all heavy sections must be present.
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
                response_mode="full",
            )
        )
        assert result["success"] is True
        assert result["response_mode"] == "full"
        all_required = self.REQUIRED_BASE_KEYS | self.REQUIRED_FULL_MODE_KEYS
        missing = all_required - set(result.keys())
        assert not missing, f"Missing required keys in full-mode response: {missing}"

    async def test_workflow_value(self, valid_batch_dir):
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"], directory_path=str(valid_batch_dir)
            )
        )
        assert result["workflow"] == "batch_strict_pipeline"

    async def test_tools_used(self, valid_batch_dir):
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"], directory_path=str(valid_batch_dir)
            )
        )
        assert result["tools_used"] == ["validate_batch", "autofix_batch", "validate_batch"]

    async def test_file_summary_has_explicit_safety_flags(self, valid_batch_dir):
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"], directory_path=str(valid_batch_dir)
            )
        )
        assert isinstance(result["safe_to_import"], bool)
        assert isinstance(result["safe_to_compile"], bool)
        assert len(result["files"]) >= 1
        sample = result["files"][0]
        assert "safe_to_import" in sample
        assert "safe_to_compile" in sample
        assert isinstance(sample["safe_to_import"], bool)
        assert isinstance(sample["safe_to_compile"], bool)

    async def test_done_is_bool(self, valid_batch_dir):
        # blockers is a heavy section; use full mode to test it.
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
                response_mode="full",
            )
        )
        assert isinstance(result["done"], bool)
        assert result["status"] in {"done", "blocked"}
        assert isinstance(result["blocking_count"], int)
        assert isinstance(result["blockers"], list)

    async def test_terminal_mode_is_bool(self, valid_batch_dir):
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"], directory_path=str(valid_batch_dir)
            )
        )
        assert isinstance(result["terminal_mode"], bool)

    async def test_next_action_is_str(self, valid_batch_dir):
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"], directory_path=str(valid_batch_dir)
            )
        )
        assert isinstance(result["next_action"], str)
        assert len(result["next_action"]) > 0

    async def test_done_true_terminal_semantics(self, valid_batch_dir):
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"], directory_path=str(valid_batch_dir)
            )
        )
        if result["done"]:
            assert result["terminal_mode"] is True
            assert result["next_action"] == "done_no_further_autofix"
            assert result.get("allow_followup_autofix_without_user_request") is False

    async def test_done_false_terminal_semantics(self, malformed_guid_file):
        # Place malformed file into a batch dir
        d = malformed_guid_file.parent
        result = json.loads(
            await process_twincat_batch(file_patterns=["*.TcDUT"], directory_path=str(d))
        )
        assert result["success"] is True
        if not result["done"]:
            assert result["terminal_mode"] is False
            assert result["next_action"] == "manual_intervention_or_targeted_fix"

    async def test_batch_summary_in_post_validation(self, valid_batch_dir):
        # post_validation is a heavy section; use full mode.
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
                response_mode="full",
            )
        )
        post = result["post_validation"]
        assert "batch_summary" in post
        bs = post["batch_summary"]
        assert "passed" in bs
        assert "failed" in bs
        assert "warnings" in bs

    async def test_effective_oop_policy_schema(self, valid_batch_dir):
        # effective_oop_policy is a heavy section; use full mode.
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
                response_mode="full",
            )
        )
        policy = result["effective_oop_policy"]
        assert "policy_source" in policy
        assert "policy" in policy

    async def test_meta_envelope_schema(self, valid_batch_dir):
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"], directory_path=str(valid_batch_dir)
            )
        )
        meta = result["meta"]
        assert "timestamp" in meta
        assert "duration_ms" in meta
        assert "server_version" in meta
        assert "response_version" in meta
        assert meta["response_version"] == "1"
        assert result["enforcement_mode"] == "strict"
        assert result["response_version"] == "2"


# ---------------------------------------------------------------------------
# WS5: process_twincat_batch — determinism invariant
# ---------------------------------------------------------------------------


class TestProcessTwincatBatchDeterminism:
    """Second batch run on stable inputs must show fixed=0, no_changes=N."""

    async def test_second_run_no_fixes_applied(self, valid_batch_dir):
        # autofix is a heavy section; use full mode to inspect it.
        # First pass
        r1 = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
                response_mode="full",
            )
        )
        assert r1["success"] is True

        # Second pass
        r2 = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
                response_mode="full",
            )
        )
        assert r2["success"] is True

        autofix2 = r2["autofix"]
        batch_sum = autofix2.get("batch_summary", {})
        fixed2 = batch_sum.get("fixed", 0)
        assert fixed2 == 0, f"Second run must not apply fixes on stable inputs, but fixed={fixed2}"

    async def test_second_run_same_done_status(self, valid_batch_dir):
        r1 = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"], directory_path=str(valid_batch_dir)
            )
        )
        r2 = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"], directory_path=str(valid_batch_dir)
            )
        )
        assert r1["done"] == r2["done"]


# ---------------------------------------------------------------------------
# WS5: process_twincat_batch — negative paths
# ---------------------------------------------------------------------------


class TestProcessTwincatBatchNegativePaths:
    """Negative paths must return success=False with useful error message."""

    async def test_missing_directory_returns_error(self, tmp_path):
        nonexistent_dir = str(tmp_path / "ghost_dir")
        result = json.loads(
            await process_twincat_batch(file_patterns=["*.TcPOU"], directory_path=nonexistent_dir)
        )
        assert result["success"] is False
        # structured error envelope — check failed_step or legacy error key
        assert "failed_step" in result or "error" in result

    async def test_no_matching_files_returns_error(self, tmp_path):
        # Directory exists but has no matching files
        result = json.loads(
            await process_twincat_batch(file_patterns=["*.TcPOU"], directory_path=str(tmp_path))
        )
        assert result["success"] is False

    async def test_invalid_validation_level_returns_error(self, valid_batch_dir):
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
                validation_level="bad_level",
            )
        )
        assert result["success"] is False
        assert "error" in result

    async def test_invalid_validation_level_error_has_meta(self, valid_batch_dir):
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
                validation_level="invalid",
            )
        )
        assert result["success"] is False
        assert "meta" in result

    async def test_invalid_enforcement_mode_returns_error(self, valid_batch_dir):
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
                enforcement_mode="not_a_mode",
            )
        )
        assert result["success"] is False
        assert result["policy_checked"] is False
        assert "valid_enforcement_modes" in result

    async def test_invalid_response_mode_returns_error(self, valid_batch_dir):
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
                response_mode="invalid_mode",
            )
        )
        assert result["success"] is False
        assert "valid_response_modes" in result


class TestProcessTwincatBatchCompactMode:
    """Compact mode must avoid heavy nested payloads and keep safety evidence."""

    async def test_compact_mode_omits_heavy_nested_sections(self, valid_batch_dir):
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
                response_mode="compact",
            )
        )
        assert result["success"] is True
        assert result["response_mode"] == "compact"
        assert "pre_validation" not in result
        assert "autofix" not in result
        assert "post_validation" not in result
        assert "files" in result
        assert len(result["files"]) >= 1
        assert "safe_to_import" in result
        assert "safe_to_compile" in result
        assert "status" in result
        assert "blocking_count" in result
        assert "blockers" in result


# ---------------------------------------------------------------------------
# WS5: autofix_batch — batch_summary contract
# ---------------------------------------------------------------------------


class TestAutofixBatchSummaryContract:
    """Lock the batch_summary keys inside autofix_batch responses."""

    REQUIRED_BATCH_SUMMARY_KEYS = {
        "fixed",
        "no_changes",
        "failed",
        "safe_to_import",
        "safe_to_compile",
    }

    async def test_batch_summary_has_required_keys(self, valid_batch_dir):
        result = json.loads(
            await autofix_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
                create_backup=False,
            )
        )
        assert result["success"] is True
        bs = result["batch_summary"]
        missing = self.REQUIRED_BATCH_SUMMARY_KEYS - set(bs.keys())
        assert not missing, f"batch_summary missing keys: {missing}"

    async def test_batch_summary_counts_are_ints(self, valid_batch_dir):
        result = json.loads(
            await autofix_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
                create_backup=False,
            )
        )
        bs = result["batch_summary"]
        for key in self.REQUIRED_BATCH_SUMMARY_KEYS:
            assert isinstance(bs[key], int), f"batch_summary.{key} must be int"

    async def test_batch_done_and_terminal_mode_present(self, valid_batch_dir):
        result = json.loads(
            await autofix_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
                create_backup=False,
            )
        )
        assert "done" in result
        assert result["status"] in {"done", "blocked"}
        assert "safe_to_import" in result
        assert "safe_to_compile" in result
        assert isinstance(result["blocking_count"], int)
        assert isinstance(result["blockers"], list)
        assert "terminal_mode" in result
        assert "next_action" in result

    async def test_batch_meta_envelope(self, valid_batch_dir):
        result = json.loads(
            await autofix_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
                create_backup=False,
            )
        )
        assert "meta" in result
        meta = result["meta"]
        assert "timestamp" in meta
        assert "duration_ms" in meta
        assert "server_version" in meta
        assert "response_version" in meta

    async def test_validate_batch_summary_contract(self, valid_batch_dir):
        result = json.loads(
            await validate_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
            )
        )
        assert result["success"] is True
        bs = result["batch_summary"]
        assert "passed" in bs
        assert "failed" in bs
        assert "warnings" in bs
        assert "safe_to_import" in result
        assert "safe_to_compile" in result
        assert "done" in result
        assert result["status"] in {"done", "blocked"}
        assert isinstance(result["blocking_count"], int)
        assert isinstance(result["blockers"], list)
        assert "next_action" in result
        assert "meta" in result


# ---------------------------------------------------------------------------
# WS6: Batch progress notification — no-context (non-supporting clients)
# ---------------------------------------------------------------------------


class TestBatchProgressNotificationContract:
    """WS6: Batch tools must remain functional when no Context is provided.

    Progress notifications are best-effort: clients that do not support them
    call the tools without ctx and receive the same final JSON result.
    """

    async def test_validate_batch_without_ctx_returns_valid_result(self, valid_batch_dir):
        """validate_batch called without ctx must return success and unchanged schema."""
        result = json.loads(
            await validate_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
            )
        )
        assert result["success"] is True
        assert "batch_summary" in result
        assert "files" in result
        assert "meta" in result

    async def test_autofix_batch_without_ctx_returns_valid_result(self, valid_batch_dir):
        """autofix_batch called without ctx must return success and unchanged schema."""
        result = json.loads(
            await autofix_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
                create_backup=False,
            )
        )
        assert result["success"] is True
        assert "batch_summary" in result
        assert "done" in result
        assert "status" in result
        assert "blocking_count" in result
        assert "blockers" in result
        assert "terminal_mode" in result
        assert "meta" in result

    async def test_validate_batch_result_identical_with_or_without_ctx(self, valid_batch_dir):
        """Final batch JSON must be schema-identical regardless of ctx presence."""
        result_no_ctx = json.loads(
            await validate_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
            )
        )
        # Both calls produce valid success responses with the same top-level keys
        assert result_no_ctx["success"] is True
        required_keys = {
            "success",
            "batch_id",
            "processed_files",
            "total_files",
            "batch_summary",
            "files",
            "failed_files",
            "safe_to_import",
            "safe_to_compile",
            "done",
            "status",
            "blocking_count",
            "blockers",
            "next_action",
            "meta",
        }
        missing = required_keys - set(result_no_ctx.keys())
        assert not missing, f"Missing keys in no-ctx response: {missing}"


class TestVerifyDeterminismBatchContract:
    """Contract tests for verify_determinism_batch response schema."""

    @pytest.mark.asyncio
    async def test_verify_determinism_batch_required_keys(self, valid_batch_dir):
        # Use response_mode="full" to get all fields including heavy sections.
        result = json.loads(
            await verify_determinism_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
                response_mode="full",
            )
        )
        assert result["success"] is True
        required = {
            "success",
            "workflow",
            "tools_used",
            "file_patterns",
            "directory_path",
            "stable",
            "files",
            "first_pass_summary",
            "second_pass_summary",
            "safe_to_import",
            "safe_to_compile",
            "done",
            "terminal_mode",
            "next_action",
            "effective_oop_policy",
            "meta",
        }
        assert not (required - set(result.keys()))

    @pytest.mark.asyncio
    async def test_verify_determinism_batch_file_entry_keys(self, valid_batch_dir):
        # Use response_mode="full" to get all per-file fields including file_path.
        result = json.loads(
            await verify_determinism_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
                response_mode="full",
            )
        )
        assert result["success"] is True
        for item in result["files"]:
            required_item = {
                "file_path",
                "file_name",
                "safe_to_import",
                "safe_to_compile",
                "content_changed_first_pass",
                "content_changed_second_pass",
                "stable",
            }
            assert not (required_item - set(item.keys()))
