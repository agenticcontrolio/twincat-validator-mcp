"""Contract tests for get_context_pack tool and include_knowledge_hints flag.

Tests validate:
- Schema lock for get_context_pack responses
- Pre-generation stage returns curated entries
- Troubleshooting stage requires check_ids
- max_entries truncation
- include_examples toggle
- Missing/unknown check_id handling
- Policy resolution with target_path
- include_knowledge_hints on process_twincat_single and process_twincat_batch
"""

import json
import pytest

from server import get_context_pack, process_twincat_single, process_twincat_batch


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
def malformed_guid_file(tmp_path):
    f = tmp_path / "ST_Bad.TcDUT"
    f.write_text(MALFORMED_GUID_CONTENT, encoding="utf-8")
    return f


@pytest.fixture
def valid_batch_dir(tmp_path):
    (tmp_path / "FB_A.TcPOU").write_text(VALID_FB_CONTENT, encoding="utf-8")
    (tmp_path / "FB_B.TcPOU").write_text(VALID_FB_CONTENT, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Schema lock
# ---------------------------------------------------------------------------


class TestGetContextPackSchemaLock:
    REQUIRED_KEYS = {
        "success",
        "context_pack_version",
        "stage",
        "entries_requested",
        "entries_returned",
        "max_entries",
        "truncated",
        "effective_oop_policy",
        "entries",
        "missing_check_ids",
        "meta",
    }

    REQUIRED_ENTRY_KEYS = {
        "check_id",
        "name",
        "severity",
        "category",
        "auto_fixable",
    }

    def test_required_keys_present(self):
        result = json.loads(get_context_pack())
        assert result["success"] is True
        missing = self.REQUIRED_KEYS - set(result.keys())
        assert not missing, f"Missing keys: {missing}"

    def test_entry_shape(self):
        result = json.loads(get_context_pack())
        assert len(result["entries"]) > 0
        for entry in result["entries"]:
            missing = self.REQUIRED_ENTRY_KEYS - set(entry.keys())
            assert not missing, f"Entry {entry.get('check_id')} missing keys: {missing}"

    def test_context_pack_version(self):
        result = json.loads(get_context_pack())
        assert result["context_pack_version"] == "1"

    def test_meta_envelope(self):
        result = json.loads(get_context_pack())
        meta = result["meta"]
        assert "timestamp" in meta
        assert "duration_ms" in meta
        assert "server_version" in meta
        assert isinstance(meta["duration_ms"], int)


# ---------------------------------------------------------------------------
# Pre-generation stage
# ---------------------------------------------------------------------------


class TestGetContextPackPreGeneration:
    def test_default_returns_success(self):
        result = json.loads(get_context_pack())
        assert result["success"] is True
        assert result["stage"] == "pre_generation"

    def test_entries_from_curated_list(self):
        result = json.loads(get_context_pack(max_entries=20))
        check_ids = [e["check_id"] for e in result["entries"]]
        # Must start with xml_structure (highest priority)
        assert check_ids[0] == "xml_structure"
        # All should be from the curated list
        from twincat_validator.mcp_tools_orchestration import _PRE_GENERATION_CHECK_IDS

        for cid in check_ids:
            assert cid in _PRE_GENERATION_CHECK_IDS

    def test_max_entries_truncation(self):
        result = json.loads(get_context_pack(max_entries=3))
        assert result["entries_returned"] == 3
        assert result["truncated"] is True

    def test_default_max_entries(self):
        result = json.loads(get_context_pack())
        assert result["max_entries"] == 10
        assert result["entries_returned"] <= 10

    def test_entries_have_kb_fields(self):
        result = json.loads(get_context_pack(max_entries=5))
        for entry in result["entries"]:
            if "explanation" in entry:
                assert isinstance(entry["explanation"], str)
                assert isinstance(entry["why_it_matters"], str)

    def test_oop_policy_present(self):
        result = json.loads(get_context_pack())
        assert "effective_oop_policy" in result
        policy_block = result["effective_oop_policy"]
        assert "policy_source" in policy_block
        assert "policy" in policy_block
        assert isinstance(policy_block["policy"], dict)

    def test_deterministic_order(self):
        r1 = json.loads(get_context_pack())
        r2 = json.loads(get_context_pack())
        ids1 = [e["check_id"] for e in r1["entries"]]
        ids2 = [e["check_id"] for e in r2["entries"]]
        assert ids1 == ids2

    def test_include_examples_false(self):
        result = json.loads(get_context_pack(include_examples=False))
        for entry in result["entries"]:
            assert "correct_examples" not in entry
            assert "common_mistakes" not in entry

    def test_include_examples_true_default(self):
        result = json.loads(get_context_pack(max_entries=5))
        # At least some entries should have examples if KB is populated
        has_examples = any("correct_examples" in e for e in result["entries"])
        assert has_examples


# ---------------------------------------------------------------------------
# Troubleshooting stage
# ---------------------------------------------------------------------------


class TestGetContextPackTroubleshooting:
    def test_requires_explicit_intent_profile(self):
        result = json.loads(get_context_pack(stage="troubleshooting", check_ids=["guid_format"]))
        assert result["success"] is False
        assert "intent_profile is required for troubleshooting stage" in result.get("error", "")

    def test_requires_check_ids(self):
        result = json.loads(get_context_pack(stage="troubleshooting", intent_profile="oop"))
        assert result["success"] is False
        assert "check_ids" in result.get("error", "")

    def test_returns_requested_entries(self):
        result = json.loads(
            get_context_pack(
                stage="troubleshooting",
                check_ids=["guid_format"],
                intent_profile="oop",
            )
        )
        assert result["success"] is True
        assert result["stage"] == "troubleshooting"
        assert len(result["entries"]) == 1
        assert result["entries"][0]["check_id"] == "guid_format"

    def test_unknown_check_id(self):
        result = json.loads(
            get_context_pack(
                stage="troubleshooting",
                check_ids=["nonexistent_check_xyz"],
                intent_profile="oop",
            )
        )
        assert result["success"] is True
        assert "nonexistent_check_xyz" in result["missing_check_ids"]
        assert len(result["entries"]) == 0

    def test_mixed_valid_and_invalid(self):
        result = json.loads(
            get_context_pack(
                stage="troubleshooting",
                check_ids=["guid_format", "nonexistent_check_xyz"],
                intent_profile="oop",
            )
        )
        assert result["success"] is True
        assert len(result["entries"]) == 1
        assert result["entries"][0]["check_id"] == "guid_format"
        assert "nonexistent_check_xyz" in result["missing_check_ids"]

    def test_deduplication(self):
        result = json.loads(
            get_context_pack(
                stage="troubleshooting",
                check_ids=["guid_format", "guid_format", "guid_format"],
                intent_profile="oop",
            )
        )
        assert result["success"] is True
        assert len(result["entries"]) == 1

    def test_empty_check_ids(self):
        result = json.loads(
            get_context_pack(
                stage="troubleshooting",
                check_ids=[],
            )
        )
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Policy resolution
# ---------------------------------------------------------------------------


class TestGetContextPackPolicyResolution:
    def test_target_path_resolves_policy(self, valid_fb):
        result = json.loads(get_context_pack(target_path=str(valid_fb)))
        assert result["success"] is True
        assert "effective_oop_policy" in result
        # With target_path, policy proof fields should be present
        assert "policy_checked" in result

    def test_no_target_path_uses_defaults(self):
        result = json.loads(get_context_pack())
        assert result["effective_oop_policy"]["policy_source"] == "defaults"

    def test_invalid_enforcement_mode(self):
        result = json.loads(get_context_pack(enforcement_mode="invalid_mode"))
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestGetContextPackEdgeCases:
    def test_invalid_stage(self):
        result = json.loads(get_context_pack(stage="invalid_stage"))
        assert result["success"] is False
        assert "valid_stages" in result

    def test_max_entries_negative_defaults(self):
        result = json.loads(get_context_pack(max_entries=-1))
        assert result["success"] is True
        assert result["max_entries"] == 10  # default

    def test_max_entries_zero_defaults(self):
        result = json.loads(get_context_pack(max_entries=0))
        assert result["success"] is True
        assert result["max_entries"] == 10  # default


# ---------------------------------------------------------------------------
# include_knowledge_hints on orchestration tools
# ---------------------------------------------------------------------------


class TestIncludeKnowledgeHints:
    def test_single_default_no_hints(self, valid_fb):
        result = json.loads(process_twincat_single(str(valid_fb)))
        assert "recommended_check_ids" not in result

    def test_single_hints_true_done(self, valid_fb):
        result = json.loads(
            process_twincat_single(
                str(valid_fb),
                include_knowledge_hints=True,
            )
        )
        # File is valid → done=True → no recommended_check_ids
        assert result["done"] is True
        assert "recommended_check_ids" not in result

    def test_single_hints_true_blocked(self, malformed_guid_file):
        result = json.loads(
            process_twincat_single(
                str(malformed_guid_file),
                include_knowledge_hints=True,
            )
        )
        if not result["done"]:
            assert "recommended_check_ids" in result
            assert isinstance(result["recommended_check_ids"], list)

    async def test_batch_default_no_hints(self, valid_batch_dir):
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
            )
        )
        assert "recommended_check_ids" not in result

    async def test_batch_hints_true_done(self, valid_batch_dir):
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(valid_batch_dir),
                include_knowledge_hints=True,
            )
        )
        # All valid → done=True → no recommended_check_ids
        assert result["done"] is True
        assert "recommended_check_ids" not in result
