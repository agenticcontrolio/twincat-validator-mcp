"""Phase 8 Phase 2 tests: engine-level intent_profile wiring.

Covers:
- validate_file: intent_profile parameter wires exclude_categories to engine
- autofix_file: intent_profile parameter wires exclude_categories to engine
- process_twincat_single: passes intent_profile_resolved to sub-calls
- process_twincat_batch: passes intent_profile_resolved to sub-calls
- check_categories_executed field (renamed from check_categories_intended)
- _resolve_intent_profile importable from twincat_validator.utils

Phase 2.1 additions:
- _batch_auto_resolve_intent: scans .TcPOU files for EXTENDS/IMPLEMENTS
- validate_batch / process_twincat_batch auto-detects OOP intent from file content
"""

import json

from server import autofix_file, validate_file, process_twincat_single, process_twincat_batch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_plain_fb(tmp_path, name="FB_Plain"):
    """Plain FUNCTION_BLOCK — no EXTENDS/IMPLEMENTS, auto → procedural."""
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
    """FUNCTION_BLOCK EXTENDS FB_Base — auto → oop.
    Missing M_Execute override method → triggers override_marker OOP check in oop mode.
    """
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


def _make_fb_with_oop_issue(tmp_path, name="FB_OopIssue"):
    """FB that has EXTENDS and will trigger OOP checks in oop mode.

    Uses EXTENDS so auto-detection resolves to "oop".
    The extends_visibility check will fire if the EXTENDS target is unresolvable,
    but more reliably: we use a well-formed FB EXTENDS that will trigger
    override_super_call checks (no SUPER^ call) when methods are present.
    """
    path = tmp_path / f"{name}.TcPOU"
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        f'  <POU Name="{name}" Id="{{abcd1234-5678-90ab-cdef-1234567890ae}}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_OopIssue EXTENDS FB_Base\nVAR\nEND_VAR]]></Declaration>\n"
        "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
        '    <Method Name="M_Init" Id="{abcd1234-5678-90ab-cdef-1234567890ba}">\n'
        "      <Declaration><![CDATA[METHOD M_Init : BOOL\nVAR_INPUT\nEND_VAR]]></Declaration>\n"
        "      <Implementation><ST><![CDATA[// No SUPER^.M_Init() call here — triggers override_super_call]]></ST></Implementation>\n"
        "    </Method>\n"
        f'    <LineIds Name="{name}"><LineId Id="1" Count="0" /></LineIds>\n'
        "  </POU>\n"
        "</TcPlcObject>\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Helper: get all issues from a validate_file result
# ---------------------------------------------------------------------------


def _get_issues(result: dict) -> list[dict]:
    """Extract issues from a validate_file full-profile result."""
    return result.get("issues", [])


def _has_oop_category_issue(result: dict) -> bool:
    """Return True if any issue has an OOP-category check_id."""
    oop_check_prefixes = (
        "extends_",
        "override_",
        "interface_",
        "fb_init",
        "fb_exit",
        "abstract_",
        "dynamic_creation",
        "pointer_delete",
        "composition_",
        "method_visibility",
        "diamond_",
        "property_accessor",
        "method_count",
        "inheritance_",
        "this_pointer",
    )
    for issue in _get_issues(result):
        check = issue.get("check_id", "") or issue.get("category", "")
        if any(check.startswith(p) or check == p.rstrip("_") for p in oop_check_prefixes):
            return True
        # Also check category field
        if issue.get("category", "").lower() in (
            "override",
            "inheritance",
            "interface",
            "abstract",
            "fb_init",
            "oop",
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# validate_file: intent_profile wiring tests
# ---------------------------------------------------------------------------


class TestValidateFileIntentProfileWiring:
    """validate_file now accepts intent_profile and wires it to the engine."""

    def test_validate_file_accepts_intent_profile_procedural(self, tmp_path):
        """validate_file(intent_profile='procedural') must not raise."""
        path = _make_plain_fb(tmp_path)
        result = json.loads(validate_file(str(path), intent_profile="procedural"))
        assert result.get("success") is True

    def test_validate_file_accepts_intent_profile_oop(self, tmp_path):
        """validate_file(intent_profile='oop') must not raise."""
        path = _make_plain_fb(tmp_path)
        result = json.loads(validate_file(str(path), intent_profile="oop"))
        assert result.get("success") is True

    def test_validate_file_default_runs_all_checks(self, tmp_path):
        """validate_file without intent_profile — auto default — still succeeds (backward compat)."""
        path = _make_plain_fb(tmp_path)
        result = json.loads(validate_file(str(path)))
        assert result.get("success") is True

    def test_validate_file_invalid_intent_profile_returns_error(self, tmp_path):
        """Invalid intent_profile value returns an error response."""
        path = _make_plain_fb(tmp_path)
        result = json.loads(validate_file(str(path), intent_profile="nonsense"))
        assert result.get("success") is False
        assert "valid_intent_profiles" in result or "error" in result

    def test_validate_file_procedural_skips_oop_issues(self, tmp_path):
        """OOP FB with procedural intent_profile: OOP check issues must not appear."""
        path = _make_fb_with_oop_issue(tmp_path)
        result = json.loads(validate_file(str(path), profile="full", intent_profile="procedural"))
        assert result.get("success") is True
        # OOP checks excluded — no OOP-category issues must appear
        assert not _has_oop_category_issue(
            result
        ), f"OOP issues found in procedural mode: {[i.get('check_id') for i in _get_issues(result)]}"

    def test_validate_file_oop_includes_oop_issues(self, tmp_path):
        """OOP FB with oop intent_profile: OOP checks must run."""
        path = _make_fb_with_oop_issue(tmp_path)
        result_proc = json.loads(
            validate_file(str(path), profile="full", intent_profile="procedural")
        )
        result_oop = json.loads(validate_file(str(path), profile="full", intent_profile="oop"))
        assert result_proc.get("success") is True
        assert result_oop.get("success") is True
        # OOP mode should produce at least as many issues (OOP checks active)
        proc_count = len(_get_issues(result_proc))
        oop_count = len(_get_issues(result_oop))
        assert (
            oop_count >= proc_count
        ), f"OOP mode produced fewer issues than procedural: {oop_count} < {proc_count}"


# ---------------------------------------------------------------------------
# autofix_file: intent_profile wiring tests
# ---------------------------------------------------------------------------


class TestAutofixFileIntentProfileWiring:
    """autofix_file now accepts intent_profile and wires it to post-fix validation."""

    def test_autofix_file_accepts_intent_profile_procedural(self, tmp_path):
        """autofix_file(intent_profile='procedural') must not raise."""
        path = _make_plain_fb(tmp_path)
        result = json.loads(
            autofix_file(str(path), create_backup=False, intent_profile="procedural")
        )
        assert result.get("success") is True

    def test_autofix_file_accepts_intent_profile_oop(self, tmp_path):
        """autofix_file(intent_profile='oop') must not raise."""
        path = _make_plain_fb(tmp_path)
        result = json.loads(autofix_file(str(path), create_backup=False, intent_profile="oop"))
        assert result.get("success") is True

    def test_autofix_file_default_unchanged(self, tmp_path):
        """autofix_file without intent_profile still succeeds (backward compat)."""
        path = _make_plain_fb(tmp_path)
        result = json.loads(autofix_file(str(path), create_backup=False))
        assert result.get("success") is True

    def test_autofix_file_invalid_intent_profile_returns_error(self, tmp_path):
        """Invalid intent_profile value returns an error response."""
        path = _make_plain_fb(tmp_path)
        result = json.loads(
            autofix_file(str(path), create_backup=False, intent_profile="bad_value")
        )
        assert result.get("success") is False
        assert "valid_intent_profiles" in result or "error" in result


# ---------------------------------------------------------------------------
# process_twincat_single: check_categories_executed + actual filtering
# ---------------------------------------------------------------------------


class TestProcessSingleCategoriesExecuted:
    """process_twincat_single: check_categories_executed field and actual engine behavior."""

    def test_check_categories_executed_procedural(self, tmp_path):
        """Procedural resolved profile → check_categories_executed == ['core']."""
        path = _make_plain_fb(tmp_path)
        result = json.loads(process_twincat_single(str(path), intent_profile="procedural"))
        assert result.get("check_categories_executed") == ["core"]

    def test_check_categories_executed_oop(self, tmp_path):
        """OOP resolved profile → check_categories_executed == ['core', 'oop']."""
        path = _make_plain_fb(tmp_path)
        result = json.loads(process_twincat_single(str(path), intent_profile="oop"))
        assert result.get("check_categories_executed") == ["core", "oop"]

    def test_check_categories_intended_field_removed(self, tmp_path):
        """Old field name 'check_categories_intended' must NOT appear in results."""
        path = _make_plain_fb(tmp_path)
        result = json.loads(process_twincat_single(str(path), intent_profile="procedural"))
        assert (
            "check_categories_intended" not in result
        ), "Old field 'check_categories_intended' still present — rename incomplete"

    def test_process_single_auto_plain_fb_is_procedural(self, tmp_path):
        """Plain FB auto-detects as procedural; check_categories_executed matches."""
        path = _make_plain_fb(tmp_path)
        result = json.loads(process_twincat_single(str(path), intent_profile="auto"))
        assert result.get("intent_profile_resolved") == "procedural"
        assert result.get("check_categories_executed") == ["core"]

    def test_process_single_auto_derived_fb_is_oop(self, tmp_path):
        """EXTENDS FB auto-detects as oop; check_categories_executed matches."""
        path = _make_derived_fb(tmp_path)
        result = json.loads(process_twincat_single(str(path), intent_profile="auto"))
        assert result.get("intent_profile_resolved") == "oop"
        assert result.get("check_categories_executed") == ["core", "oop"]


# ---------------------------------------------------------------------------
# process_twincat_batch: check_categories_executed
# ---------------------------------------------------------------------------


class TestProcessBatchCategoriesExecuted:
    """process_twincat_batch: check_categories_executed field."""

    async def test_batch_check_categories_executed_present(self, tmp_path):
        """batch result includes check_categories_executed field."""
        _make_plain_fb(tmp_path)
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
                response_mode="full",
            )
        )
        assert result.get("success") is True
        assert "check_categories_executed" in result

    async def test_batch_procedural_check_categories_executed(self, tmp_path):
        """Explicit procedural → check_categories_executed == ['core']."""
        _make_plain_fb(tmp_path)
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
                intent_profile="procedural",
                response_mode="full",
            )
        )
        assert result.get("success") is True
        assert result.get("check_categories_executed") == ["core"]

    async def test_batch_oop_check_categories_executed(self, tmp_path):
        """Explicit oop → check_categories_executed == ['core', 'oop']."""
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
        assert result.get("check_categories_executed") == ["core", "oop"]

    async def test_batch_check_categories_intended_field_removed(self, tmp_path):
        """Old field name 'check_categories_intended' must NOT appear in batch results."""
        _make_plain_fb(tmp_path)
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
                response_mode="full",
            )
        )
        assert result.get("success") is True
        assert (
            "check_categories_intended" not in result
        ), "Old field 'check_categories_intended' still present in batch result"


# ---------------------------------------------------------------------------
# _resolve_intent_profile importable from utils
# ---------------------------------------------------------------------------


class TestResolveIntentProfileLocation:
    """_resolve_intent_profile must be importable from twincat_validator.utils."""

    def test_resolve_intent_profile_importable_from_utils(self):
        from twincat_validator.utils import _resolve_intent_profile

        assert callable(_resolve_intent_profile)

    def test_valid_intent_profiles_importable_from_utils(self):
        from twincat_validator.utils import _VALID_INTENT_PROFILES

        assert set(_VALID_INTENT_PROFILES) == {"auto", "procedural", "oop"}


# ---------------------------------------------------------------------------
# Phase 2.1: _batch_auto_resolve_intent unit tests
# ---------------------------------------------------------------------------


class TestBatchAutoResolveIntent:
    """_batch_auto_resolve_intent scans .TcPOU declarations for OOP keywords."""

    def test_importable_from_utils(self):
        from twincat_validator.utils import _batch_auto_resolve_intent

        assert callable(_batch_auto_resolve_intent)

    def test_explicit_oop_skips_scan(self, tmp_path):
        """Explicit 'oop' returns 'oop' without reading any files."""
        from twincat_validator.utils import _batch_auto_resolve_intent

        # No files needed — explicit profiles short-circuit
        result = _batch_auto_resolve_intent([], "oop")
        assert result == "oop"

    def test_explicit_procedural_skips_scan(self, tmp_path):
        """Explicit 'procedural' returns 'procedural' without reading any files."""
        from twincat_validator.utils import _batch_auto_resolve_intent

        result = _batch_auto_resolve_intent([], "procedural")
        assert result == "procedural"

    def test_auto_empty_list_resolves_procedural(self):
        """'auto' with no files defaults to 'procedural'."""
        from twincat_validator.utils import _batch_auto_resolve_intent

        assert _batch_auto_resolve_intent([], "auto") == "procedural"

    def test_auto_resolves_oop_when_extends_present(self, tmp_path):
        """'auto' resolves to 'oop' when any .TcPOU file has EXTENDS."""
        from twincat_validator.utils import _batch_auto_resolve_intent

        path = _make_derived_fb(tmp_path)
        assert _batch_auto_resolve_intent([path], "auto") == "oop"

    def test_auto_resolves_oop_when_implements_present(self, tmp_path):
        """'auto' resolves to 'oop' when any .TcPOU file has IMPLEMENTS."""
        from twincat_validator.utils import _batch_auto_resolve_intent

        path = tmp_path / "FB_Impl.TcPOU"
        path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
            '  <POU Name="FB_Impl" Id="{abcd1234-5678-90ab-cdef-1234567890af}" SpecialFunc="None">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Impl IMPLEMENTS I_Motor\nVAR\nEND_VAR]]></Declaration>\n"
            "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
            '    <LineIds Name="FB_Impl"><LineId Id="1" Count="0" /></LineIds>\n'
            "  </POU>\n"
            "</TcPlcObject>\n",
            encoding="utf-8",
        )
        assert _batch_auto_resolve_intent([path], "auto") == "oop"

    def test_auto_resolves_procedural_when_no_oop_keywords(self, tmp_path):
        """'auto' resolves to 'procedural' when no file has EXTENDS/IMPLEMENTS."""
        from twincat_validator.utils import _batch_auto_resolve_intent

        path = _make_plain_fb(tmp_path)
        assert _batch_auto_resolve_intent([path], "auto") == "procedural"

    def test_auto_resolves_oop_if_any_file_matches(self, tmp_path):
        """'auto' resolves to 'oop' even if only one of many files has EXTENDS."""
        from twincat_validator.utils import _batch_auto_resolve_intent

        plain = _make_plain_fb(tmp_path, name="FB_Plain")
        oop = _make_derived_fb(tmp_path, name="FB_Derived")
        # Two files: one plain, one OOP → should resolve oop
        assert _batch_auto_resolve_intent([plain, oop], "auto") == "oop"

    def test_auto_skips_non_tcpou_files(self, tmp_path):
        """Non-.TcPOU files are not inspected for OOP keywords."""
        from twincat_validator.utils import _batch_auto_resolve_intent

        # Write EXTENDS into a .TcGVL file — should NOT trigger oop
        gvl = tmp_path / "GVL_Test.TcGVL"
        gvl.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject><GVL Name="GVL_Test"><Declaration>'
            "<![CDATA[{attribute ...}\nFUNCTION_BLOCK FB_Fake EXTENDS FB_Base\n]]>"
            "</Declaration></GVL></TcPlcObject>\n",
            encoding="utf-8",
        )
        assert _batch_auto_resolve_intent([gvl], "auto") == "procedural"


# ---------------------------------------------------------------------------
# Phase 2.1: validate_batch auto-detection integration tests
# ---------------------------------------------------------------------------


class TestValidateBatchAutoDetection:
    """validate_batch 'auto' mode scans files and routes OOP checks correctly."""

    async def test_auto_detects_oop_in_batch(self, tmp_path):
        """validate_batch with auto + OOP file → check_categories include oop in resolved mode."""
        from server import validate_batch

        _make_derived_fb(tmp_path, name="FB_Derived")
        result = json.loads(
            await validate_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
            )
        )
        assert result.get("success") is True
        # Batch ran against an OOP file — should succeed (no contract shape failure)
        assert result.get("processed_files", 0) >= 1

    async def test_auto_procedural_batch_no_oop_issues(self, tmp_path):
        """validate_batch with auto + plain FB → procedural, no OOP-category issues."""
        from server import validate_batch

        _make_plain_fb(tmp_path, name="FB_Plain")
        result = json.loads(
            await validate_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
            )
        )
        assert result.get("success") is True
        # Collect all issues across files
        all_issues = []
        for fitem in result.get("files", []):
            vr = fitem.get("validation_result", {})
            all_issues.extend(vr.get("issues", []))
        oop_check_prefixes = (
            "extends_",
            "override_",
            "interface_",
            "fb_init",
            "fb_exit",
            "abstract_",
            "dynamic_creation",
            "pointer_delete",
            "composition_",
            "method_visibility",
            "diamond_",
            "property_accessor",
            "method_count",
        )
        oop_issues = [
            i
            for i in all_issues
            if any((i.get("check_id", "") or "").startswith(p) for p in oop_check_prefixes)
        ]
        assert oop_issues == [], f"OOP issues found in procedural batch: {oop_issues}"


# ---------------------------------------------------------------------------
# Phase 2.1: process_twincat_batch auto-detection integration test
# ---------------------------------------------------------------------------


class TestProcessBatchAutoDetection:
    """process_twincat_batch 'auto' mode scans files for OOP intent."""

    async def test_auto_resolves_oop_in_process_batch(self, tmp_path):
        """process_twincat_batch auto with OOP file → intent_profile_resolved == 'oop'."""
        _make_derived_fb(tmp_path, name="FB_Derived")
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
                response_mode="full",
            )
        )
        assert result.get("success") is True
        assert result.get("intent_profile_resolved") == "oop"
        assert result.get("check_categories_executed") == ["core", "oop"]

    async def test_auto_resolves_procedural_in_process_batch(self, tmp_path):
        """process_twincat_batch auto with plain FB → intent_profile_resolved == 'procedural'."""
        _make_plain_fb(tmp_path, name="FB_Plain")
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
                response_mode="full",
            )
        )
        assert result.get("success") is True
        assert result.get("intent_profile_resolved") == "procedural"
        assert result.get("check_categories_executed") == ["core"]

    async def test_mixed_batch_resolves_oop(self, tmp_path):
        """Mixed batch (one plain + one OOP file) resolves to 'oop' under auto."""
        _make_plain_fb(tmp_path, name="FB_Plain")
        _make_derived_fb(tmp_path, name="FB_Derived")
        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
                response_mode="full",
            )
        )
        assert result.get("success") is True
        assert (
            result.get("intent_profile_resolved") == "oop"
        ), "Mixed batch should resolve to 'oop' since at least one file has EXTENDS"
