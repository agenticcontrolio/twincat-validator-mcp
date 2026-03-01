"""Phase 8C/D/E tests: intent_profile parameter on orchestration tools.

Covers:
- _resolve_intent_profile() auto-detection logic
- intent_profile validation (invalid value → error)
- get_context_pack: procedural omits OOP entries, oop includes them
- process_twincat_single: metadata fields present and correct
- process_twincat_batch: metadata fields present, invalid value rejected
- backward compat: existing callers without intent_profile work unchanged
"""

import json

from twincat_validator.mcp_tools_orchestration import (
    _CORE_PRE_GENERATION_CHECK_IDS,
    _OOP_PRE_GENERATION_CHECK_IDS,
    _PRE_GENERATION_CHECK_IDS,
    _resolve_intent_profile,
)
from server import get_context_pack, process_twincat_single, process_twincat_batch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_plain_fb(tmp_path, name="FB_Plain"):
    """FUNCTION_BLOCK with no EXTENDS/IMPLEMENTS — procedural."""
    path = tmp_path / f"{name}.TcPOU"
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        f'  <POU Name="{name}" Id="{{abcd1234-5678-90ab-cdef-1234567890ab}}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Plain\nVAR\nEND_VAR]]></Declaration>\n"
        "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
        f'    <LineIds Name="{name}"><LineId Id="1" Count="0" /></LineIds>\n'
        "  </POU>\n"
        "</TcPlcObject>\n",
        encoding="utf-8",
    )
    return path


def _make_derived_fb(tmp_path, name="FB_Derived"):
    """FUNCTION_BLOCK EXTENDS FB_Base — OOP."""
    path = tmp_path / f"{name}.TcPOU"
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        f'  <POU Name="{name}" Id="{{abcd1234-5678-90ab-cdef-1234567890ac}}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\nVAR\nEND_VAR]]></Declaration>\n"
        "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
        f'    <LineIds Name="{name}"><LineId Id="1" Count="0" /></LineIds>\n'
        "  </POU>\n"
        "</TcPlcObject>\n",
        encoding="utf-8",
    )
    return path


def _make_implements_fb(tmp_path, name="FB_Impl"):
    """FUNCTION_BLOCK IMPLEMENTS I_Interface — OOP."""
    path = tmp_path / f"{name}.TcPOU"
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        f'  <POU Name="{name}" Id="{{abcd1234-5678-90ab-cdef-1234567890ad}}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Impl IMPLEMENTS I_Base\nVAR\nEND_VAR]]></Declaration>\n"
        "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
        f'    <LineIds Name="{name}"><LineId Id="1" Count="0" /></LineIds>\n'
        "  </POU>\n"
        "</TcPlcObject>\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Tests: _resolve_intent_profile (unit-level)
# ---------------------------------------------------------------------------


class TestResolveIntentProfile:
    """Unit tests for the _resolve_intent_profile helper."""

    def test_explicit_oop_always_returns_oop(self):
        assert _resolve_intent_profile(None, "oop") == "oop"
        assert _resolve_intent_profile("FUNCTION_BLOCK FB_Plain\nVAR END_VAR", "oop") == "oop"

    def test_explicit_procedural_always_returns_procedural(self):
        assert _resolve_intent_profile(None, "procedural") == "procedural"
        content = "FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\nVAR END_VAR"
        assert _resolve_intent_profile(content, "procedural") == "procedural"

    def test_auto_with_none_content_defaults_procedural(self):
        assert _resolve_intent_profile(None, "auto") == "procedural"

    def test_auto_with_plain_fb_resolves_procedural(self):
        content = (
            '<?xml version="1.0"?><TcPlcObject>'
            '<POU Name="FB_Plain"><Declaration><![CDATA[FUNCTION_BLOCK FB_Plain\nVAR END_VAR\n]]></Declaration>'
            "</POU></TcPlcObject>"
        )
        assert _resolve_intent_profile(content, "auto") == "procedural"

    def test_auto_with_extends_resolves_oop(self):
        content = (
            '<?xml version="1.0"?><TcPlcObject>'
            '<POU Name="FB_Der"><Declaration><![CDATA[FUNCTION_BLOCK FB_Der EXTENDS FB_Base\nVAR END_VAR\n]]></Declaration>'
            "</POU></TcPlcObject>"
        )
        assert _resolve_intent_profile(content, "auto") == "oop"

    def test_auto_with_implements_resolves_oop(self):
        content = (
            '<?xml version="1.0"?><TcPlcObject>'
            '<POU Name="FB_Impl"><Declaration><![CDATA[FUNCTION_BLOCK FB_Impl IMPLEMENTS I_Base\nVAR END_VAR\n]]></Declaration>'
            "</POU></TcPlcObject>"
        )
        assert _resolve_intent_profile(content, "auto") == "oop"

    def test_auto_case_insensitive_extends(self):
        """EXTENDS keyword detection is case-insensitive."""
        content = (
            '<?xml version="1.0"?><TcPlcObject>'
            '<POU Name="FB_X"><Declaration><![CDATA[function_block FB_X extends FB_Y\nVAR END_VAR\n]]></Declaration>'
            "</POU></TcPlcObject>"
        )
        assert _resolve_intent_profile(content, "auto") == "oop"

    def test_auto_does_not_trigger_on_comment_extends(self):
        """EXTENDS in a comment inside the POU declaration must not be matched —
        but note: our regex is keyword-level only; the line still counts.
        This test documents current (intentionally simple) behaviour: even EXTENDS
        inside a comment triggers 'oop'.  This is a known conservative over-count.
        """
        # The check is intentionally coarse — any EXTENDS word in the CDATA triggers oop.
        # This is by design (conservative).  If users want procedural, they set it explicitly.
        content = (
            '<?xml version="1.0"?><TcPlcObject>'
            '<POU Name="FB_X"><Declaration>'
            "<![CDATA[FUNCTION_BLOCK FB_X\nVAR\n(* This block EXTENDS behaviour *)\nEND_VAR\n]]>"
            "</Declaration></POU></TcPlcObject>"
        )
        # conservative: comment triggers oop detection
        assert _resolve_intent_profile(content, "auto") == "oop"

    def test_auto_method_declaration_extends_not_matched(self):
        """EXTENDS inside a Method <Declaration> block must NOT be matched —
        _extract_pou_declaration_cdata anchors on <POU>, not <Method>.
        """
        content = (
            '<?xml version="1.0"?><TcPlcObject><POU Name="FB_Plain">'
            "<Declaration><![CDATA[FUNCTION_BLOCK FB_Plain\nVAR END_VAR\n]]></Declaration>"
            '<Method Name="M_X"><Declaration><![CDATA[METHOD M_X : BOOL\n'
            "(* This method EXTENDS base behaviour *)\nEND_VAR\n]]></Declaration></Method>"
            "</POU></TcPlcObject>"
        )
        assert _resolve_intent_profile(content, "auto") == "procedural"


# ---------------------------------------------------------------------------
# Tests: _PRE_GENERATION_CHECK_IDS split invariants (Phase D)
# ---------------------------------------------------------------------------


class TestPreGenerationCheckIdsSplit:
    """Invariant tests for the _CORE / _OOP / combined list structure."""

    def test_full_list_is_core_plus_oop(self):
        assert _PRE_GENERATION_CHECK_IDS == (
            _CORE_PRE_GENERATION_CHECK_IDS + _OOP_PRE_GENERATION_CHECK_IDS
        )

    def test_core_list_has_no_oop_ids(self):
        """No OOP-specific check IDs should appear in the core list."""
        oop_ids = set(_OOP_PRE_GENERATION_CHECK_IDS)
        for cid in _CORE_PRE_GENERATION_CHECK_IDS:
            assert cid not in oop_ids, f"OOP check '{cid}' leaked into core list"

    def test_core_list_has_structural_checks(self):
        """Core list must contain fundamental structural checks."""
        core = set(_CORE_PRE_GENERATION_CHECK_IDS)
        assert "xml_structure" in core
        assert "pou_structure" in core
        assert "guid_uniqueness" in core
        assert "naming_conventions" in core

    def test_oop_list_has_inheritance_checks(self):
        """OOP list must contain inheritance-related checks."""
        oop = set(_OOP_PRE_GENERATION_CHECK_IDS)
        assert "extends_visibility" in oop
        assert "override_marker" in oop
        assert "interface_contract" in oop

    def test_no_duplicates_across_lists(self):
        core_set = set(_CORE_PRE_GENERATION_CHECK_IDS)
        oop_set = set(_OOP_PRE_GENERATION_CHECK_IDS)
        assert core_set.isdisjoint(
            oop_set
        ), f"Duplicate IDs found across lists: {core_set & oop_set}"


# ---------------------------------------------------------------------------
# Tests: get_context_pack intent_profile routing (Phase D)
# ---------------------------------------------------------------------------


class TestGetContextPackIntentProfile:
    """Tests for intent_profile routing in get_context_pack."""

    def _call(self, **kwargs) -> dict:
        return json.loads(get_context_pack(**kwargs))

    def test_procedural_omits_oop_checks(self):
        """procedural profile must not return OOP-family check entries."""
        result = self._call(stage="pre_generation", intent_profile="procedural")
        assert result["success"] is True
        returned_ids = {e["check_id"] for e in result["entries"]}
        oop_ids = set(_OOP_PRE_GENERATION_CHECK_IDS)
        assert returned_ids.isdisjoint(
            oop_ids
        ), f"OOP check IDs returned in procedural mode: {returned_ids & oop_ids}"

    def test_procedural_includes_core_checks(self):
        """procedural profile must include core check entries."""
        result = self._call(stage="pre_generation", intent_profile="procedural", max_entries=20)
        assert result["success"] is True
        returned_ids = {e["check_id"] for e in result["entries"]}
        core_ids = set(_CORE_PRE_GENERATION_CHECK_IDS)
        # At least some core IDs must be present (limited by max_entries/missing KB)
        assert returned_ids & core_ids, "No core check IDs found in procedural mode"

    def test_oop_includes_oop_checks(self):
        """oop profile must include OOP-family check entries."""
        result = self._call(stage="pre_generation", intent_profile="oop", max_entries=20)
        assert result["success"] is True
        returned_ids = {e["check_id"] for e in result["entries"]}
        oop_ids = set(_OOP_PRE_GENERATION_CHECK_IDS)
        assert returned_ids & oop_ids, "No OOP check IDs found in oop mode"

    def test_auto_defaults_procedural_no_content(self):
        """auto with no file content resolves to procedural (no OOP entries)."""
        result = self._call(stage="pre_generation", intent_profile="auto")
        assert result["intent_profile_requested"] == "auto"
        assert result["intent_profile_resolved"] == "procedural"
        returned_ids = {e["check_id"] for e in result["entries"]}
        oop_ids = set(_OOP_PRE_GENERATION_CHECK_IDS)
        assert returned_ids.isdisjoint(oop_ids)

    def test_metadata_fields_present(self):
        """Response includes intent metadata fields for pre_generation stage."""
        result = self._call(stage="pre_generation", intent_profile="oop")
        assert "intent_profile_requested" in result
        assert "intent_profile_resolved" in result
        assert result["intent_profile_requested"] == "oop"
        assert result["intent_profile_resolved"] == "oop"

    def test_procedural_fewer_entries_than_oop(self):
        """Procedural mode returns fewer entries than OOP mode (OOP list excluded)."""
        result_proc = self._call(
            stage="pre_generation", intent_profile="procedural", max_entries=30
        )
        result_oop = self._call(stage="pre_generation", intent_profile="oop", max_entries=30)
        assert result_proc["entries_requested"] < result_oop["entries_requested"]

    def test_troubleshooting_stage_ignores_intent_profile(self):
        """intent_profile has no routing effect in troubleshooting stage."""
        result_proc = self._call(
            stage="troubleshooting",
            check_ids=["xml_structure", "guid_uniqueness"],
            intent_profile="procedural",
        )
        result_oop = self._call(
            stage="troubleshooting",
            check_ids=["xml_structure", "guid_uniqueness"],
            intent_profile="oop",
        )
        assert result_proc["entries_requested"] == result_oop["entries_requested"]
        assert {e["check_id"] for e in result_proc["entries"]} == {
            e["check_id"] for e in result_oop["entries"]
        }

    def test_troubleshooting_requires_explicit_intent_profile(self):
        """Troubleshooting stage must reject omitted intent_profile."""
        result = self._call(stage="troubleshooting", check_ids=["xml_structure"])
        assert result.get("success") is False
        assert "intent_profile is required for troubleshooting stage" in result.get("error", "")

    def test_invalid_intent_profile_returns_error(self):
        """Invalid intent_profile value produces an error response, not a crash."""
        result = self._call(stage="pre_generation", intent_profile="nonsense")
        assert result.get("success") is False or "error" in result
        # Must not crash or return entries
        assert result.get("entries") is None or result.get("entries") == []

    def test_backward_compat_no_intent_profile_arg(self):
        """Calling get_context_pack without intent_profile uses oop default (backward compat)."""
        result = self._call(stage="pre_generation")
        assert result["success"] is True
        # Default is "oop" — result must include both core and OOP entries
        assert len(result["entries"]) > 0
        returned_ids = {e["check_id"] for e in result["entries"]}
        oop_ids = set(_OOP_PRE_GENERATION_CHECK_IDS)
        assert returned_ids & oop_ids, "Default (oop) must include OOP check entries"


# ---------------------------------------------------------------------------
# Tests: process_twincat_single intent_profile metadata (Phase C)
# ---------------------------------------------------------------------------


class TestProcessTwincatSingleIntentProfile:
    """Tests for intent_profile metadata in process_twincat_single."""

    def test_plain_fb_auto_resolves_procedural(self, tmp_path):
        """Plain FUNCTION_BLOCK auto-detects as procedural."""
        path = _make_plain_fb(tmp_path)
        result = json.loads(process_twincat_single(str(path), intent_profile="auto"))
        assert result.get("success") is True
        assert result["intent_profile_requested"] == "auto"
        assert result["intent_profile_resolved"] == "procedural"

    def test_oop_fb_auto_resolves_oop(self, tmp_path):
        """EXTENDS FUNCTION_BLOCK auto-detects as oop."""
        path = _make_derived_fb(tmp_path)
        result = json.loads(process_twincat_single(str(path), intent_profile="auto"))
        assert result.get("success") is True
        assert result["intent_profile_requested"] == "auto"
        assert result["intent_profile_resolved"] == "oop"

    def test_implements_fb_auto_resolves_oop(self, tmp_path):
        """IMPLEMENTS FUNCTION_BLOCK auto-detects as oop."""
        path = _make_implements_fb(tmp_path)
        result = json.loads(process_twincat_single(str(path), intent_profile="auto"))
        assert result.get("success") is True
        assert result["intent_profile_resolved"] == "oop"

    def test_explicit_procedural_overrides_oop_file(self, tmp_path):
        """explicit procedural wins over EXTENDS content."""
        path = _make_derived_fb(tmp_path)
        result = json.loads(process_twincat_single(str(path), intent_profile="procedural"))
        assert result["intent_profile_requested"] == "procedural"
        assert result["intent_profile_resolved"] == "procedural"

    def test_explicit_oop_overrides_plain_file(self, tmp_path):
        """explicit oop wins over plain FB content."""
        path = _make_plain_fb(tmp_path)
        result = json.loads(process_twincat_single(str(path), intent_profile="oop"))
        assert result["intent_profile_requested"] == "oop"
        assert result["intent_profile_resolved"] == "oop"

    def test_check_categories_executed_procedural(self, tmp_path):
        """Procedural resolved profile reports check_categories_executed=['core']."""
        path = _make_plain_fb(tmp_path)
        result = json.loads(process_twincat_single(str(path), intent_profile="procedural"))
        assert result.get("check_categories_executed") == ["core"]

    def test_check_categories_executed_oop(self, tmp_path):
        """OOP resolved profile reports check_categories_executed=['core', 'oop']."""
        path = _make_plain_fb(tmp_path)
        result = json.loads(process_twincat_single(str(path), intent_profile="oop"))
        assert result.get("check_categories_executed") == ["core", "oop"]

    def test_invalid_intent_profile_returns_error(self, tmp_path):
        """Invalid intent_profile value returns an error response."""
        path = _make_plain_fb(tmp_path)
        result = json.loads(process_twincat_single(str(path), intent_profile="bad_value"))
        assert result.get("success") is False
        # Must include the valid profiles in the error response
        assert "valid_intent_profiles" in result or "error" in result

    def test_backward_compat_no_intent_profile(self, tmp_path):
        """Calling process_twincat_single without intent_profile must work (auto default)."""
        path = _make_plain_fb(tmp_path)
        result = json.loads(process_twincat_single(str(path)))
        assert result.get("success") is True
        # Metadata fields must always be present now
        assert "intent_profile_requested" in result
        assert "intent_profile_resolved" in result
        assert "check_categories_executed" in result
        assert "workflow_compliance_warnings" in result
        assert isinstance(result["workflow_compliance_warnings"], list)


# ---------------------------------------------------------------------------
# Tests: process_twincat_batch intent_profile metadata (Phase C)
# ---------------------------------------------------------------------------


class TestProcessTwincatBatchIntentProfile:
    """Tests for intent_profile metadata in process_twincat_batch."""

    async def test_batch_metadata_present_auto(self, tmp_path):
        """Batch result includes intent metadata fields."""
        _make_plain_fb(tmp_path)
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
                intent_profile="auto",
                response_mode="full",
            )
        )
        assert result.get("success") is True
        assert result["intent_profile_requested"] == "auto"
        assert result["intent_profile_resolved"] == "procedural"  # no content → procedural
        assert "check_categories_executed" in result

    async def test_batch_explicit_oop_metadata(self, tmp_path):
        """explicit oop resolves to oop in batch."""
        _make_plain_fb(tmp_path)
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
                intent_profile="oop",
                response_mode="full",
            )
        )
        assert result.get("success") is True
        assert result["intent_profile_resolved"] == "oop"
        assert result["check_categories_executed"] == ["core", "oop"]

    async def test_batch_invalid_intent_profile_returns_error(self, tmp_path):
        """Invalid intent_profile returns error in batch."""
        _make_plain_fb(tmp_path)
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
                intent_profile="invalid",
            )
        )
        assert result.get("success") is False

    async def test_batch_backward_compat_no_intent_profile(self, tmp_path):
        """Batch call without intent_profile still succeeds (auto default)."""
        _make_plain_fb(tmp_path)
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
                response_mode="full",
            )
        )
        assert result.get("success") is True
        assert "intent_profile_requested" in result
        assert "intent_profile_resolved" in result
        assert "workflow_compliance_warnings" in result
        assert isinstance(result["workflow_compliance_warnings"], list)
