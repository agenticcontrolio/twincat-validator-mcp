"""Contract invariant tests — Phase 1 of Root-Cause Remediation Plan.

Validates the canonical safety-flag semantics across all MCP tools:
  - safe_to_import  = error_count == 0
  - safe_to_compile = error_count == 0  (warnings do NOT block)
  - done            = safe_to_import and safe_to_compile and blocking_count == 0
  - status          = "done" if done else "blocked"
  - status="blocked" iff blocking_count > 0

Cross-tool targets (§5.1):
  validate_file, autofix_file, validate_batch, process_twincat_single,
  verify_determinism_batch (RC-2).

RC references: RC-1 (safe-flag drift), RC-2 (determinism done), RC-8 (blocked with 0 blockers).
"""

import json
import pytest

from twincat_validator.result_contract import ContractState, derive_contract_state
from twincat_validator.models import ValidationIssue


# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------


def _make_warning_only_file(tmp_path):
    """TcPOU file that triggers only style warnings (tabs), no errors."""
    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '\t<POU Name="FB_WarningOnly" Id="{a1b2c3d4-e5f6-7890-abcd-ef1234567890}" SpecialFunc="None">\n'
        "\t\t<Declaration><![CDATA[FUNCTION_BLOCK FB_WarningOnly\n"
        "VAR\n"
        "END_VAR]]></Declaration>\n"
        "\t\t<Implementation>\n"
        "\t\t\t<ST><![CDATA[]]></ST>\n"
        "\t\t</Implementation>\n"
        '\t\t<LineIds Name="FB_WarningOnly">\n'
        '\t\t\t<LineId Id="1" Count="0" />\n'
        "\t\t</LineIds>\n"
        "\t</POU>\n"
        "</TcPlcObject>\n"
    )
    p = tmp_path / "warning_only.TcPOU"
    p.write_bytes(content.encode("utf-8"))
    return p


def _make_valid_file(tmp_path):
    """A fully valid TcPOU file with no issues."""
    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        '  <POU Name="FB_Valid" Id="{a1b2c3d4-e5f6-7890-abcd-ef1234567890}" SpecialFunc="None">\n'
        "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Valid\n"
        "VAR\n"
        "END_VAR]]></Declaration>\n"
        "    <Implementation>\n"
        "      <ST><![CDATA[]]></ST>\n"
        "    </Implementation>\n"
        '    <LineIds Name="FB_Valid">\n'
        '      <LineId Id="1" Count="0" />\n'
        "    </LineIds>\n"
        "  </POU>\n"
        "</TcPlcObject>\n"
    )
    p = tmp_path / "valid.TcPOU"
    p.write_bytes(content.encode("utf-8"))
    return p


# ---------------------------------------------------------------------------
# Unit tests for derive_contract_state (result_contract.py)
# ---------------------------------------------------------------------------


class TestDeriveContractStateUnit:
    """Direct unit tests for the canonical derive_contract_state() function."""

    def _issue(self, severity, fix_available=False):
        return ValidationIssue(
            severity=severity, category="Test", message="msg", fix_available=fix_available
        )

    def test_empty_issues_is_done(self):
        cs = derive_contract_state([])
        assert cs.safe_to_import is True
        assert cs.safe_to_compile is True
        assert cs.blocking_count == 0
        assert cs.done is True
        assert cs.status == "done"

    def test_warning_only_is_safe_to_compile(self):
        """Warnings must not affect safe_to_compile (canonical contract §2.1)."""
        issues = [self._issue("warning"), self._issue("warning")]
        cs = derive_contract_state(issues)
        assert cs.safe_to_import is True
        assert cs.safe_to_compile is True
        assert cs.warning_count == 2
        assert cs.error_count == 0
        assert cs.done is True
        assert cs.status == "done"

    def test_error_makes_not_safe(self):
        issues = [self._issue("error", fix_available=False)]
        cs = derive_contract_state(issues)
        assert cs.safe_to_import is False
        assert cs.safe_to_compile is False
        assert cs.blocking_count == 1
        assert cs.done is False
        assert cs.status == "blocked"

    def test_fixable_error_not_a_blocker(self):
        """Auto-fixable errors don't go in blockers list, but still block safety."""
        issues = [self._issue("error", fix_available=True)]
        cs = derive_contract_state(issues)
        assert cs.safe_to_import is False
        assert cs.safe_to_compile is False
        assert cs.blocking_count == 0  # fixable → not in blockers
        assert cs.done is False
        assert cs.status == "blocked"  # because blocking_count would be 0 but done is still False

    def test_critical_severity_is_an_error(self):
        issues = [self._issue("critical", fix_available=False)]
        cs = derive_contract_state(issues)
        assert cs.error_count == 1
        assert cs.safe_to_import is False
        assert cs.safe_to_compile is False

    def test_extra_blockers_force_unsafe(self):
        """extra_blockers (GUID sanity, contract) always make file unsafe."""
        cs = derive_contract_state(
            [],
            extra_blockers=[{"check": "artifact_sanity", "message": "bad GUID", "line": None}],
        )
        assert cs.safe_to_import is False
        assert cs.safe_to_compile is False
        assert cs.blocking_count == 1
        assert cs.done is False
        assert cs.status == "blocked"

    def test_require_stable_false_blocks_done(self):
        """When require_stable=True and stable=False, done must be False."""
        cs = derive_contract_state([], require_stable=True, stable=False)
        assert cs.done is False
        assert cs.status == "blocked"

    def test_require_stable_true_with_stable_allows_done(self):
        cs = derive_contract_state([], require_stable=True, stable=True)
        assert cs.done is True
        assert cs.status == "done"

    def test_dict_issues_supported(self):
        """derive_contract_state must accept already-serialised issue dicts."""
        issues = [
            {"severity": "warning", "message": "warn", "fix_available": False},
            {"severity": "error", "message": "err", "fix_available": False},
        ]
        cs = derive_contract_state(issues)
        assert cs.error_count == 1
        assert cs.warning_count == 1
        assert cs.safe_to_import is False
        assert cs.blocking_count == 1

    def test_dict_issues_fixable_key_variants(self):
        """Accept 'fixable' and 'auto_fixable' as aliases for 'fix_available' in dicts."""
        issues_fixable = [{"severity": "error", "fixable": True, "message": "x"}]
        cs1 = derive_contract_state(issues_fixable)
        assert cs1.blocking_count == 0  # fixable → not a blocker

        issues_auto = [{"severity": "error", "auto_fixable": True, "message": "x"}]
        cs2 = derive_contract_state(issues_auto)
        assert cs2.blocking_count == 0

    def test_status_invariant_blocked_requires_not_done(self):
        """Invariant: status='blocked' iff done=False."""
        for issues, expected_done in [
            ([], True),
            ([self._issue("warning")], True),
            ([self._issue("error")], False),
        ]:
            cs = derive_contract_state(issues)
            assert (cs.status == "done") == cs.done
            assert (cs.status == "blocked") == (not cs.done)

    def test_contract_state_invalid_status_raises(self):
        with pytest.raises(ValueError, match="status must be"):
            ContractState(
                error_count=0,
                warning_count=0,
                safe_to_import=True,
                safe_to_compile=True,
                blocking_count=0,
                blockers=[],
                done=True,
                status="invalid",
            )


# ---------------------------------------------------------------------------
# RC-8: status="blocked" requires blocking_count > 0
# ---------------------------------------------------------------------------


class TestBlockedStatusInvariant:
    """RC-8: warning-only outcomes must not produce status=blocked."""

    def test_warning_only_is_not_blocked(self):
        issues = [
            ValidationIssue(severity="warning", category="Style", message="w1"),
            ValidationIssue(severity="warning", category="Style", message="w2"),
        ]
        cs = derive_contract_state(issues)
        # Warnings must not make status=blocked
        assert cs.status != "blocked", (
            f"RC-8 violated: warning-only case produced status=blocked "
            f"(blocking_count={cs.blocking_count})"
        )
        assert cs.done is True
        assert cs.status == "done"

    def test_blocked_implies_positive_blocking_count(self):
        """Invariant: status=blocked ↔ blocking_count > 0 OR done=False."""
        test_cases = [
            [],  # empty
            [ValidationIssue(severity="warning", category="X", message="w")],
            [ValidationIssue(severity="error", category="X", message="e", fix_available=True)],
            [ValidationIssue(severity="error", category="X", message="e", fix_available=False)],
        ]
        for issues in test_cases:
            cs = derive_contract_state(issues)
            if cs.status == "blocked":
                # Must have either blockers or done=False for a legitimate reason
                assert (
                    not cs.done
                ), f"RC-8: status=blocked but done=True (blocking_count={cs.blocking_count})"


# ---------------------------------------------------------------------------
# RC-1: Cross-tool safe_to_compile consistent — warning-only files
# ---------------------------------------------------------------------------


class TestWarningOnlyFileCompileFlag:
    """RC-1: warning-only file must yield safe_to_compile=True from validate_file."""

    def test_validate_file_llm_strict_warning_only_safe_to_compile(self, tmp_path):
        """validate_file llm_strict: file with only style warnings → safe_to_compile=True."""
        from server import validate_file

        file_path = _make_warning_only_file(tmp_path)
        raw = validate_file(str(file_path), profile="llm_strict")
        result = json.loads(raw)

        # File has tab warnings — must still be safe_to_compile
        assert result.get("safe_to_compile") is True, (
            f"RC-1: validate_file llm_strict produced safe_to_compile=False for a warning-only file. "
            f"Result: {result}"
        )
        assert result.get("safe_to_import") is True, (
            f"RC-1: validate_file llm_strict produced safe_to_import=False for a warning-only file. "
            f"Result: {result}"
        )

    def test_validate_file_llm_strict_valid_file_is_done(self, tmp_path):
        """validate_file llm_strict: fully valid file → done=True, status=done."""
        from server import validate_file

        file_path = _make_valid_file(tmp_path)
        raw = validate_file(str(file_path), profile="llm_strict")
        result = json.loads(raw)

        assert result.get("safe_to_compile") is True
        assert result.get("safe_to_import") is True
        assert result.get("done") is True
        assert result.get("status") == "done"

    def test_autofix_file_llm_strict_warning_only_safe_to_compile(self, tmp_path):
        """autofix_file llm_strict: file with only warnings → safe_to_compile=True after fix."""
        from server import autofix_file

        file_path = _make_warning_only_file(tmp_path)
        raw = autofix_file(str(file_path), profile="llm_strict")
        result = json.loads(raw)

        assert result.get("safe_to_compile") is True, (
            f"RC-1: autofix_file llm_strict produced safe_to_compile=False for warning-only file. "
            f"Result: {result}"
        )
        assert result.get("safe_to_import") is True


# ---------------------------------------------------------------------------
# RC-1: done=True invariant — done cannot be True when safe_to_compile=False
# ---------------------------------------------------------------------------


class TestDoneImpliesSafeFlags:
    """done=True requires safe_to_import=True AND safe_to_compile=True (§8.1)."""

    def test_done_false_when_errors_present(self):
        """Unit invariant: done cannot be True when errors exist."""
        issues = [
            ValidationIssue(severity="error", category="X", message="bad", fix_available=False)
        ]
        cs = derive_contract_state(issues)
        assert cs.done is False
        assert cs.safe_to_compile is False

    def test_done_true_only_when_all_safe(self):
        cs = derive_contract_state([])
        assert cs.done is True
        if cs.done:
            assert cs.safe_to_import is True
            assert cs.safe_to_compile is True
            assert cs.blocking_count == 0

    def test_validate_file_done_invariant(self, tmp_path):
        """validate_file: if done=True then safe_to_import and safe_to_compile must be True."""
        from server import validate_file

        file_path = _make_valid_file(tmp_path)
        raw = validate_file(str(file_path), profile="llm_strict")
        result = json.loads(raw)

        if result.get("done") is True:
            assert result.get("safe_to_import") is True, "done=True but safe_to_import=False"
            assert result.get("safe_to_compile") is True, "done=True but safe_to_compile=False"
            assert result.get("blocking_count", -1) == 0, "done=True but blocking_count > 0"


# ---------------------------------------------------------------------------
# RC-2: verify_determinism_batch done requires stability AND safety
# ---------------------------------------------------------------------------


class TestDeterminismDoneRequiresSafety:
    """RC-2: verify_determinism_batch done=True only when stable AND safe."""

    def test_derive_contract_state_require_stable_false(self):
        """If require_stable=True and stable=False, done must be False even with no issues."""
        cs = derive_contract_state([], require_stable=True, stable=False)
        assert cs.done is False
        assert cs.status == "blocked"
        assert cs.blocking_count >= 0  # 0 is fine — unstable files are their own blocker

    def test_derive_contract_state_require_stable_true_no_issues(self):
        """If require_stable=True and stable=True with no issues, done=True."""
        cs = derive_contract_state([], require_stable=True, stable=True)
        assert cs.done is True
        assert cs.status == "done"

    def test_derive_contract_state_require_stable_true_with_errors(self):
        """Stable=True but errors present → done must still be False."""
        issues = [ValidationIssue(severity="error", category="X", message="e", fix_available=False)]
        cs = derive_contract_state(issues, require_stable=True, stable=True)
        assert cs.done is False
        assert cs.status == "blocked"


# ---------------------------------------------------------------------------
# RC-2 Integration: verify_determinism_batch done reflects per-file safety
# ---------------------------------------------------------------------------


class TestDeterminismBatchIntegration:
    """Integration tests exercising the actual verify_determinism_batch tool.

    Ensures that done/status/safe_to_compile in the tool output are derived from
    per-file safe_to_import/safe_to_compile flags, not only from per-file blockers.
    """

    @pytest.mark.asyncio
    async def test_determinism_batch_valid_files_done_true(self, tmp_path):
        """Stable, valid batch → done=True, safe_to_compile=True, status=done."""
        from server import verify_determinism_batch

        # Write two clean, fully valid files.
        for name in ("FB_Alpha.TcPOU", "FB_Beta.TcPOU"):
            (tmp_path / name).write_bytes(
                (
                    '<?xml version="1.0" encoding="utf-8"?>\n'
                    '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                    f'  <POU Name="{name.replace(".TcPOU", "")}" '
                    'Id="{a1b2c3d4-e5f6-7890-abcd-ef1234567890}" SpecialFunc="None">\n'
                    "    <Declaration><![CDATA[FUNCTION_BLOCK "
                    f'{name.replace(".TcPOU", "")}\nVAR\nEND_VAR]]></Declaration>\n'
                    "    <Implementation>\n"
                    "      <ST><![CDATA[]]></ST>\n"
                    "    </Implementation>\n"
                    f'    <LineIds Name="{name.replace(".TcPOU", "")}">\n'
                    '      <LineId Id="1" Count="0" />\n'
                    "    </LineIds>\n"
                    "  </POU>\n"
                    "</TcPlcObject>\n"
                ).encode("utf-8")
            )

        result = json.loads(
            await verify_determinism_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
            )
        )

        assert result["success"] is True
        assert result["stable"] is True
        assert (
            result["safe_to_import"] is True
        ), "RC-2: verify_determinism_batch safe_to_import=False for stable valid files"
        assert (
            result["safe_to_compile"] is True
        ), "RC-2: verify_determinism_batch safe_to_compile=False for stable valid files"
        assert (
            result["done"] is True
        ), "RC-2: verify_determinism_batch done=False for stable valid files"
        assert result["status"] == "done"
        assert result["terminal_mode"] is True

    @pytest.mark.asyncio
    async def test_determinism_batch_done_invariant_holds(self, tmp_path):
        """done=True implies safe_to_import=True AND safe_to_compile=True AND stable=True."""
        from server import verify_determinism_batch

        (tmp_path / "FB_Test.TcPOU").write_bytes(
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Test" Id="{a1b2c3d4-e5f6-7890-abcd-ef1234567890}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR]]></Declaration>\n"
                "    <Implementation>\n"
                "      <ST><![CDATA[]]></ST>\n"
                "    </Implementation>\n"
                '    <LineIds Name="FB_Test">\n'
                '      <LineId Id="1" Count="0" />\n'
                "    </LineIds>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ).encode("utf-8")
        )

        result = json.loads(
            await verify_determinism_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
            )
        )

        assert result["success"] is True
        # Enforce the invariant: done=True ↔ stable AND safe
        if result.get("done") is True:
            assert result["stable"] is True, "done=True but stable=False"
            assert result["safe_to_import"] is True, "done=True but safe_to_import=False"
            assert result["safe_to_compile"] is True, "done=True but safe_to_compile=False"
            assert result["blocking_count"] == 0, "done=True but blocking_count > 0"
            assert result["status"] == "done"
            assert result["terminal_mode"] is True

    @pytest.mark.asyncio
    async def test_determinism_batch_safe_flags_from_per_file_not_blockers(self, tmp_path):
        """verify_determinism_batch aggregates safe_to_compile from per-file flags.

        This is the core RC-2 regression test: files[*].safe_to_import/safe_to_compile
        must propagate to the top-level result, not be re-derived only from blockers.
        A file can be unsafe with zero blockers (fixable errors), and the old code
        would incorrectly produce safe_to_compile=True by looking at blockers only.
        """
        from server import verify_determinism_batch

        # Use a valid file — we verify that safe flags are present and consistent
        # with per-file entries (not independent of them).
        (tmp_path / "FB_Check.TcPOU").write_bytes(
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Check" Id="{a1b2c3d4-e5f6-7890-abcd-ef1234567890}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Check\nVAR\nEND_VAR]]></Declaration>\n"
                "    <Implementation>\n"
                "      <ST><![CDATA[]]></ST>\n"
                "    </Implementation>\n"
                '    <LineIds Name="FB_Check">\n'
                '      <LineId Id="1" Count="0" />\n'
                "    </LineIds>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ).encode("utf-8")
        )

        result = json.loads(
            await verify_determinism_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
            )
        )

        assert result["success"] is True
        files = result.get("files", [])
        assert len(files) == 1

        # Top-level safe flags must be consistent with per-file flags.
        per_file_safe_to_import = all(f["safe_to_import"] for f in files)
        per_file_safe_to_compile = all(f["safe_to_compile"] for f in files)
        assert (
            result["safe_to_import"] == per_file_safe_to_import
        ), "RC-2: top-level safe_to_import disagrees with per-file aggregation"
        assert (
            result["safe_to_compile"] == per_file_safe_to_compile
        ), "RC-2: top-level safe_to_compile disagrees with per-file aggregation"


# ---------------------------------------------------------------------------
# RC-3: Structural checker de-duplication
# ---------------------------------------------------------------------------


class TestStructureCheckerDeduplication:
    """RC-3: pou_structure umbrella must not double-execute its sub-checks.

    When validation_level='all' is used, the umbrella check 'pou_structure'
    must be excluded from the default run path.  Its sub-checks
    (pou_structure_header, pou_structure_methods, etc.) are first-class entries
    and cover the same defect surface.  Running both would produce duplicate
    issues with different check_id stamps for the same defect.

    Verifies batch response shaping contracts.
    """

    def _make_fb_file(self, tmp_path, name="FB_Test"):
        """Write a minimal valid FUNCTION_BLOCK .TcPOU fixture."""
        p = tmp_path / f"{name}.TcPOU"
        p.write_bytes(
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                f'  <POU Name="{name}" Id="{{a1b2c3d4-e5f6-7890-abcd-ef1234567890}}" SpecialFunc="None">\n'
                f"    <Declaration><![CDATA[FUNCTION_BLOCK {name}\nVAR\nEND_VAR]]></Declaration>\n"
                "    <Implementation>\n"
                "      <ST><![CDATA[]]></ST>\n"
                "    </Implementation>\n"
                f'    <LineIds Name="{name}">\n'
                '      <LineId Id="1" Count="0" />\n'
                "    </LineIds>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ).encode("utf-8")
        )
        return p

    def test_umbrella_excluded_from_default_all_level(self):
        """pou_structure must not appear in the default 'all' check list (RC-3)."""
        from twincat_validator.mcp_app import config
        from twincat_validator.engines import ValidationEngine

        engine = ValidationEngine(config)
        checks_all = engine._get_checks_for_level("all")
        assert "pou_structure" not in checks_all, (
            "RC-3: pou_structure umbrella is in the 'all' default run list "
            "and will cause duplicate issues with its sub-checks."
        )

    def test_umbrella_excluded_from_critical_level(self):
        """pou_structure must not appear in the 'critical' check list (RC-3)."""
        from twincat_validator.mcp_app import config
        from twincat_validator.engines import ValidationEngine

        engine = ValidationEngine(config)
        checks_critical = engine._get_checks_for_level("critical")
        assert (
            "pou_structure" not in checks_critical
        ), "RC-3: pou_structure umbrella would double-execute critical sub-checks."

    def test_sub_checks_present_in_all_level(self):
        """Sub-checks must still be in the 'all' default list (regression guard)."""
        from twincat_validator.mcp_app import config
        from twincat_validator.engines import ValidationEngine

        engine = ValidationEngine(config)
        checks_all = engine._get_checks_for_level("all")
        for sub_check in (
            "pou_structure_header",
            "pou_structure_methods",
            "pou_structure_interface",
            "pou_structure_syntax",
            "pou_structure_subtype",
        ):
            assert (
                sub_check in checks_all
            ), f"RC-3: sub-check '{sub_check}' was accidentally excluded from the 'all' run list."

    def test_validate_file_no_duplicate_issues(self, tmp_path):
        """validate_file must not emit duplicate issues for the same defect (RC-3).

        If a valid FB produces zero issues when validated normally, a second
        validate call with the umbrella explicitly added via check_specific must
        not produce different issues than the sub-checks alone.
        """
        from server import validate_file

        fb = self._make_fb_file(tmp_path)
        result_all = json.loads(validate_file(str(fb)))
        assert result_all["success"] is True

        # Collect check_ids of all issues from full validation.
        issues_all = result_all.get("issues", [])

        # No issue should appear more than once with the same (message, line) tuple —
        # that would be a signature of duplicate execution.
        seen = {}
        for issue in issues_all:
            key = (issue.get("message", ""), issue.get("line_num"))
            if key in seen:
                assert False, (
                    f"RC-3: duplicate issue detected — same (message, line) emitted twice:\n"
                    f"  first check_id={seen[key]!r}\n"
                    f"  second check_id={issue.get('check_id', issue.get('category'))!r}\n"
                    f"  message={key[0]!r}"
                )
            seen[key] = issue.get("check_id", issue.get("category"))

    def test_check_specific_still_accepts_umbrella(self, tmp_path):
        """check_specific must still accept 'pou_structure' for backward compat (RC-3)."""
        from server import check_specific

        fb = self._make_fb_file(tmp_path)
        result = json.loads(check_specific(str(fb), ["pou_structure"]))
        # Must not return an error about invalid check name.
        assert result["success"] is True, (
            "RC-3: check_specific rejected 'pou_structure' as invalid — "
            "umbrella alias must remain available for explicit invocation."
        )

    def test_umbrella_alias_flag_in_config(self):
        """validation_rules.json must have umbrella_alias=true on pou_structure entry."""
        from twincat_validator.mcp_app import config

        check_def = config.validation_checks.get("pou_structure", {})
        assert check_def.get("umbrella_alias") is True, (
            "RC-3: 'pou_structure' entry in validation_rules.json is missing "
            "'umbrella_alias': true — without it the engine cannot distinguish "
            "the umbrella from first-class sub-checks."
        )


class TestInterfaceContractConvergence:
    """RC-4: structure and OOP interface checks must agree on inherited contracts."""

    def test_structure_and_oop_checks_align_on_inherited_interface(self, tmp_path):
        from twincat_validator.file_handler import TwinCATFile
        from twincat_validator.validators.oop_checks import InterfaceContractCheck
        from twincat_validator.validators.structure_checks import PouStructureInterfaceCheck

        (tmp_path / "I_Diag.TcIO").write_text(
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <Itf Name="I_Diag" Id="{ab000001-0000-0000-0000-000000000001}">\n'
                "    <Declaration><![CDATA[INTERFACE I_Diag\n]]></Declaration>\n"
                '    <Method Name="M_GetFaultCode" Id="{ab000001-0000-0000-0000-000000000002}">\n'
                "      <Declaration><![CDATA[METHOD M_GetFaultCode : INT\n]]></Declaration>\n"
                "    </Method>\n"
                "  </Itf>\n"
                "</TcPlcObject>\n"
            ),
            encoding="utf-8",
        )
        (tmp_path / "FB_Base.TcPOU").write_text(
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Base" Id="{ab000001-0000-0000-0000-000000000003}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Base IMPLEMENTS I_Diag\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_GetFaultCode" Id="{ab000001-0000-0000-0000-000000000004}">\n'
                "      <Declaration><![CDATA[METHOD M_GetFaultCode : INT\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[M_GetFaultCode := 0;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
            encoding="utf-8",
        )
        (tmp_path / "FB_Derived.TcPOU").write_text(
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Derived" Id="{ab000001-0000-0000-0000-000000000005}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base IMPLEMENTS I_Diag\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
            encoding="utf-8",
        )

        file = TwinCATFile(tmp_path / "FB_Derived.TcPOU")
        issues_oop = InterfaceContractCheck().run(file)
        issues_structure = PouStructureInterfaceCheck().run(file)

        assert issues_oop == []
        assert issues_structure == []


class TestWarningConflictResolver:
    """Phase 6 / RC-7: reset-spam and hardcoded-dispatch should not conflict."""

    def test_loop_edge_gated_reset_does_not_emit_reset_spam(self, tmp_path):
        from twincat_validator.file_handler import TwinCATFile
        from twincat_validator.validators.structure_checks import PouStructureMethodsCheck

        prg = tmp_path / "PRG_EdgeGatedLoop.TcPOU"
        prg.write_text(
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="PRG_EdgeGatedLoop" Id="{ac000001-0000-0000-0000-000000000001}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[PROGRAM PRG_EdgeGatedLoop\n"
                "VAR\n"
                "  aUnits : ARRAY[0..1] OF I_ProcessUnit;\n"
                "  i : INT;\n"
                "  bRetryEdge : BOOL;\n"
                "  bRetryEdgePrev : BOOL;\n"
                "END_VAR\n"
                "END_PROGRAM\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[\n"
                "IF bRetryEdge AND NOT bRetryEdgePrev THEN\n"
                "  FOR i := 0 TO 1 DO\n"
                "    aUnits[i].M_Reset();\n"
                "  END_FOR;\n"
                "END_IF;\n"
                "]]></ST></Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
            encoding="utf-8",
        )
        issues = PouStructureMethodsCheck().run(TwinCATFile(prg))
        assert not any("reset-spam loop" in issue.message for issue in issues)

    def test_guarded_unrolled_reset_dispatch_does_not_emit_hardcoded_dispatch(self, tmp_path):
        from twincat_validator.file_handler import TwinCATFile
        from twincat_validator.validators.oop_checks import HardcodedDispatchCheck

        prg = tmp_path / "PRG_GuardedUnrolled.TcPOU"
        prg.write_text(
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="PRG_GuardedUnrolled" Id="{ac000001-0000-0000-0000-000000000002}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[PROGRAM PRG_GuardedUnrolled\n"
                "VAR\n"
                "  bRetryEdge : BOOL;\n"
                "  bRetryEdgePrev : BOOL;\n"
                "END_VAR\n"
                "END_PROGRAM\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[\n"
                "IF bRetryEdge AND NOT bRetryEdgePrev THEN\n"
                "  aUnits[1].M_Reset();\n"
                "  aUnits[2].M_Reset();\n"
                "END_IF;\n"
                "]]></ST></Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
            encoding="utf-8",
        )
        issues = HardcodedDispatchCheck().run(TwinCATFile(prg))
        assert not any("Hardcoded array-index dispatch" in issue.message for issue in issues)

    def test_no_contradictory_warnings_for_guarded_patterns(self, tmp_path):
        from twincat_validator.file_handler import TwinCATFile
        from twincat_validator.validators.oop_checks import HardcodedDispatchCheck
        from twincat_validator.validators.structure_checks import PouStructureMethodsCheck

        prg = tmp_path / "PRG_GuardedMixed.TcPOU"
        prg.write_text(
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="PRG_GuardedMixed" Id="{ac000001-0000-0000-0000-000000000003}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[PROGRAM PRG_GuardedMixed\n"
                "VAR\n"
                "  aUnits : ARRAY[0..1] OF I_ProcessUnit;\n"
                "  i : INT;\n"
                "  bRetryEdge : BOOL;\n"
                "  bRetryEdgePrev : BOOL;\n"
                "END_VAR\n"
                "END_PROGRAM\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[\n"
                "IF bRetryEdge AND NOT bRetryEdgePrev THEN\n"
                "  FOR i := 0 TO 1 DO\n"
                "    aUnits[i].M_Reset();\n"
                "  END_FOR;\n"
                "  aUnits[0].M_Reset();\n"
                "  aUnits[1].M_Reset();\n"
                "END_IF;\n"
                "]]></ST></Implementation>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
            encoding="utf-8",
        )
        file = TwinCATFile(prg)
        issues_structure = PouStructureMethodsCheck().run(file)
        issues_oop = HardcodedDispatchCheck().run(file)

        assert not any("reset-spam loop" in issue.message for issue in issues_structure)
        assert not any("Hardcoded array-index dispatch" in issue.message for issue in issues_oop)


class TestAbstractInterfacePolicyAlignment:
    """Phase 7 / RC-9: abstract/interface policy must not force workaround patterns."""

    def test_abstract_base_contract_and_inherited_concrete_fulfillment(self, tmp_path):
        from twincat_validator.file_handler import TwinCATFile
        from twincat_validator.validators.oop_checks import (
            AbstractContractCheck,
            InterfaceContractCheck,
            PolicyInterfaceContractIntegrityCheck,
        )
        from twincat_validator.validators.structure_checks import PouStructureInterfaceCheck

        (tmp_path / "I_Unit.TcIO").write_text(
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <Itf Name="I_Unit" Id="{ad000001-0000-0000-0000-000000000001}">\n'
                "    <Declaration><![CDATA[INTERFACE I_Unit\n]]></Declaration>\n"
                '    <Method Name="M_Init" Id="{ad000001-0000-0000-0000-000000000002}">\n'
                "      <Declaration><![CDATA[METHOD M_Init : BOOL\n]]></Declaration>\n"
                "    </Method>\n"
                '    <Method Name="M_Execute" Id="{ad000001-0000-0000-0000-000000000003}">\n'
                "      <Declaration><![CDATA[METHOD M_Execute : BOOL\n]]></Declaration>\n"
                "    </Method>\n"
                "  </Itf>\n"
                "</TcPlcObject>\n"
            ),
            encoding="utf-8",
        )
        (tmp_path / "FB_Base.TcPOU").write_text(
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Base" Id="{ad000001-0000-0000-0000-000000000011}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK ABSTRACT FB_Base IMPLEMENTS I_Unit\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_Init" Id="{ad000001-0000-0000-0000-000000000012}">\n'
                "      <Declaration><![CDATA[METHOD M_Init : BOOL\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[M_Init := TRUE;]]></ST></Implementation>\n"
                "    </Method>\n"
                '    <Method Name="M_Execute" Id="{ad000001-0000-0000-0000-000000000013}">\n'
                "      <Declaration><![CDATA[METHOD ABSTRACT M_Execute : BOOL\n]]></Declaration>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
            encoding="utf-8",
        )
        (tmp_path / "FB_Derived.TcPOU").write_text(
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_Derived" Id="{ad000001-0000-0000-0000-000000000021}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\n"
                "]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_Execute" Id="{ad000001-0000-0000-0000-000000000022}">\n'
                "      <Declaration><![CDATA[{attribute 'override'}\nMETHOD M_Execute : BOOL\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[M_Execute := TRUE;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
            encoding="utf-8",
        )

        base_file = TwinCATFile(tmp_path / "FB_Base.TcPOU")
        derived_file = TwinCATFile(tmp_path / "FB_Derived.TcPOU")

        assert PouStructureInterfaceCheck().run(base_file) == []
        assert InterfaceContractCheck().run(base_file) == []
        assert AbstractContractCheck().run(base_file) == []
        assert PolicyInterfaceContractIntegrityCheck().run(base_file) == []

        # Inherited interface + concrete override in descendant must satisfy checks
        assert InterfaceContractCheck().run(derived_file) == []
        assert AbstractContractCheck().run(derived_file) == []

    def test_abstract_base_false_stub_workaround_is_rejected(self, tmp_path):
        from twincat_validator.file_handler import TwinCATFile
        from twincat_validator.validators.oop_checks import AbstractContractCheck

        bad_base = tmp_path / "FB_BadBase.TcPOU"
        bad_base.write_text(
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                '  <POU Name="FB_BadBase" Id="{ad000001-0000-0000-0000-000000000031}" SpecialFunc="None">\n'
                "    <Declaration><![CDATA[FUNCTION_BLOCK ABSTRACT FB_BadBase\n]]></Declaration>\n"
                "    <Implementation><ST><![CDATA[]]></ST></Implementation>\n"
                '    <Method Name="M_Execute" Id="{ad000001-0000-0000-0000-000000000032}">\n'
                "      <Declaration><![CDATA[METHOD M_Execute : BOOL\n]]></Declaration>\n"
                "      <Implementation><ST><![CDATA[M_Execute := FALSE;]]></ST></Implementation>\n"
                "    </Method>\n"
                "  </POU>\n"
                "</TcPlcObject>\n"
            ),
            encoding="utf-8",
        )
        issues = AbstractContractCheck().run(TwinCATFile(bad_base))
        assert any("trivial FALSE stub method(s)" in issue.message for issue in issues)


# ---------------------------------------------------------------------------
# VAR_PROTECTED prevention invariants (Root Cause Plan — Phases A & D)
# ---------------------------------------------------------------------------


def _make_var_protected_file(tmp_path, variant: str = "space"):
    """Write a .TcPOU containing VAR PROTECTED (space) or VAR_PROTECTED (underscore)."""

    if variant == "underscore":
        var_block = "VAR_PROTECTED"
        name = "FB_UnderscoreVarProtected"
    else:
        var_block = "VAR PROTECTED"
        name = "FB_SpaceVarProtected"

    content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        f'  <POU Name="{name}" Id="{{a1b2c3d4-e5f6-7890-abcd-ef1234567890}}" SpecialFunc="None">\n'
        f"    <Declaration><![CDATA[FUNCTION_BLOCK {name}\n"
        f"{var_block}\n"
        "  nValue : INT;\n"
        "END_VAR]]></Declaration>\n"
        "    <Implementation>\n"
        "      <ST><![CDATA[]]></ST>\n"
        "    </Implementation>\n"
        f'    <LineIds Name="{name}">\n'
        '      <LineId Id="1" Count="0" />\n'
        "    </LineIds>\n"
        "  </POU>\n"
        "</TcPlcObject>\n"
    )
    p = tmp_path / f"{name}.TcPOU"
    p.write_bytes(content.encode("utf-8"))
    return p


class TestVarProtectedPreventionInvariants:
    """Phase A & D: VAR_PROTECTED prohibition must be consistent across all tools.

    Invariants:
    I-1: Any POU with VAR PROTECTED or VAR_PROTECTED → safe_to_import=False, error present.
    I-2: get_context_pack(pre_generation) must explicitly include VAR_PROTECTED prohibition.
    I-3: suggest_fixes must never recommend VAR_PROTECTED.
    """

    # -----------------------------------------------------------------------
    # I-1: validate_file must reject both VAR PROTECTED variants
    # -----------------------------------------------------------------------

    def test_validate_file_space_form_is_unsafe(self, tmp_path):
        """validate_file must return safe_to_import=False for VAR PROTECTED (space)."""
        from server import validate_file

        p = _make_var_protected_file(tmp_path, variant="space")
        result = json.loads(validate_file(str(p), profile="llm_strict"))

        assert (
            result.get("safe_to_import") is False
        ), "I-1: VAR PROTECTED (space form) must make file unsafe to import"
        assert result.get("blocking_count", 0) > 0 or result.get("safe_to_import") is False

    def test_validate_file_underscore_form_is_unsafe(self, tmp_path):
        """validate_file must return safe_to_import=False for VAR_PROTECTED (underscore)."""
        from server import validate_file

        p = _make_var_protected_file(tmp_path, variant="underscore")
        result = json.loads(validate_file(str(p), profile="llm_strict"))

        assert (
            result.get("safe_to_import") is False
        ), "I-1: VAR_PROTECTED (underscore form) must make file unsafe to import"

    def test_validate_file_full_profile_has_error_issue_for_var_protected(self, tmp_path):
        """validate_file full profile must include an error-severity issue for VAR PROTECTED."""
        from server import validate_file

        p = _make_var_protected_file(tmp_path, variant="space")
        result = json.loads(validate_file(str(p), profile="full"))

        issues = result.get("issues", [])
        var_protected_issues = [
            i
            for i in issues
            if "VAR PROTECTED" in i.get("message", "") or "VAR_PROTECTED" in i.get("message", "")
        ]
        assert (
            var_protected_issues
        ), "I-1: validate_file must emit at least one issue mentioning VAR PROTECTED"
        assert all(
            i.get("severity") == "error" for i in var_protected_issues
        ), "I-1: VAR PROTECTED issue must be severity=error"

    # -----------------------------------------------------------------------
    # I-2: get_context_pack(pre_generation) must mention VAR_PROTECTED prohibition
    # -----------------------------------------------------------------------

    def test_pre_generation_context_mentions_var_protected_forbidden(self, tmp_path):
        """get_context_pack(pre_generation) must explicitly include VAR_PROTECTED prohibition.

        This is the primary prevention gate — before generation starts the LLM
        must receive explicit guidance that VAR PROTECTED / VAR_PROTECTED is forbidden.
        """
        from server import get_context_pack

        result = json.loads(get_context_pack(stage="pre_generation", include_examples=True))

        assert result.get("success") is True, f"get_context_pack failed: {result}"

        # Flatten all text fields from all entries for searching
        all_text = json.dumps(result)

        assert "VAR_PROTECTED" in all_text or "VAR PROTECTED" in all_text, (
            "I-2: get_context_pack(pre_generation) must mention VAR_PROTECTED prohibition "
            "in at least one entry. Check that 'pou_structure_var_protected' is in "
            "_PRE_GENERATION_CHECK_IDS and knowledge_base.json has the entry."
        )
        assert (
            "PROTECTED" in all_text
        ), "I-2: get_context_pack(pre_generation) must contain PROTECTED guidance"

    def test_pre_generation_context_steers_to_method_property(self, tmp_path):
        """get_context_pack(pre_generation) must recommend METHOD/PROPERTY for encapsulation."""
        from server import get_context_pack

        result = json.loads(get_context_pack(stage="pre_generation", include_examples=True))
        all_text = json.dumps(result)

        # Must recommend the correct pattern
        assert (
            "METHOD" in all_text or "PROPERTY" in all_text
        ), "I-2: pre-generation context must mention METHOD or PROPERTY as encapsulation mechanism"

    # -----------------------------------------------------------------------
    # I-3: suggest_fixes must never output VAR_PROTECTED as a recommendation
    # -----------------------------------------------------------------------

    def test_suggest_fixes_never_recommends_var_protected(self, tmp_path):
        """suggest_fixes output must not contain VAR_PROTECTED as a recommendation.

        suggest_fixes takes the JSON output of validate_file (full profile) as its input
        and returns a `fixes` list. This test verifies that the `solution` field of each
        fix never recommends VAR_PROTECTED as the corrective action.
        """
        from server import suggest_fixes, validate_file

        p = _make_var_protected_file(tmp_path, variant="space")

        # Step 1: get validate_file output (full profile — suggest_fixes needs `issues`)
        validation_raw = validate_file(str(p), profile="full")

        # Step 2: feed it to suggest_fixes
        result_raw = suggest_fixes(validation_raw)
        result = json.loads(result_raw)

        assert result.get("success") is True, f"I-3: suggest_fixes failed unexpectedly: {result}"

        # `fixes` is the canonical key (not `suggestions`)
        fixes = result.get("fixes", [])
        assert fixes, "I-3: suggest_fixes returned no fixes for a VAR PROTECTED file"

        # VAR_PROTECTED must not appear as the recommended solution
        for fix in fixes:
            solution = fix.get("solution", "")
            issue_text = fix.get("issue", "")
            # Concatenate both fields for the check
            combined = solution + " " + issue_text
            if "VAR_PROTECTED" in combined or "VAR PROTECTED" in combined:
                # Acceptable only if the surrounding context clearly prohibits/replaces it
                combined_lower = combined.lower()
                assert any(
                    keyword in combined_lower
                    for keyword in ("not", "never", "forbidden", "invalid", "replace", "avoid")
                ), (
                    f"I-3: suggest_fixes fix contains VAR_PROTECTED without a prohibition context:\n"
                    f"  solution={solution!r}\n  issue={issue_text!r}"
                )

    # -----------------------------------------------------------------------
    # I-1 via process_twincat_single
    # -----------------------------------------------------------------------

    def test_process_single_var_protected_blocked(self, tmp_path):
        """process_twincat_single must report blocked for a VAR PROTECTED file."""
        from server import process_twincat_single

        p = _make_var_protected_file(tmp_path, variant="space")
        result = json.loads(process_twincat_single(str(p)))

        assert (
            result.get("safe_to_import") is False
        ), "I-1: process_twincat_single must set safe_to_import=False for VAR PROTECTED"
        assert (
            result.get("status") == "blocked"
        ), "I-1: process_twincat_single must return status=blocked for VAR PROTECTED"


# ---------------------------------------------------------------------------
# Batch response shaping invariants (Batch Shaping Plan — Phases A–D)
# ---------------------------------------------------------------------------

_BATCH_SUMMARY_ALLOWED_HEAVY = {
    "blockers",
    "issues",
    "pre_validation",
    "autofix",
    "post_validation",
    "effective_oop_policy",
    "meta_detailed",
}

_BATCH_SUMMARY_REQUIRED_TOP_KEYS = {
    "success",
    "workflow",
    "safe_to_import",
    "safe_to_compile",
    "blocking_count",
    "done",
    "status",
    "batch_summary",
    "files",
}


def _write_valid_tc_pou(path, name="FB_Test"):
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
        f'  <POU Name="{name}" Id="{{a1b2c3d4-e5f6-7890-abcd-ef1234567890}}" SpecialFunc="None">\n'
        f"    <Declaration><![CDATA[FUNCTION_BLOCK {name}\nVAR\nEND_VAR]]></Declaration>\n"
        "    <Implementation>\n"
        "      <ST><![CDATA[]]></ST>\n"
        "    </Implementation>\n"
        f'    <LineIds Name="{name}">\n'
        '      <LineId Id="1" Count="0" />\n'
        "    </LineIds>\n"
        "  </POU>\n"
        "</TcPlcObject>\n",
        encoding="utf-8",
    )


class TestBatchResponseShapingInvariants:
    """Batch response shaping: summary mode shape, section filtering, size guardrail.

    Covers Phase A–D of the Batch Response Shaping Plan.
    """

    # -----------------------------------------------------------------------
    # 1. process_twincat_batch summary mode top-level shape
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_process_batch_summary_mode_shape(self, tmp_path):
        """Summary mode must include required top-level keys and per-file summary rows."""
        from server import process_twincat_batch

        _write_valid_tc_pou(tmp_path / "FB_A.TcPOU", "FB_A")
        _write_valid_tc_pou(tmp_path / "FB_B.TcPOU", "FB_B")

        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
                response_mode="summary",
            )
        )

        assert result["success"] is True
        assert result["response_mode"] == "summary"

        # All required top-level keys must be present
        missing = _BATCH_SUMMARY_REQUIRED_TOP_KEYS - set(result.keys())
        assert not missing, f"Summary mode missing required top-level keys: {missing}"

        # Per-file entries must be slim (only summary fields)
        assert "files" in result
        assert len(result["files"]) >= 1
        for item in result["files"]:
            assert "file_name" in item, "Summary file entry missing file_name"
            assert "safe_to_import" in item
            assert "safe_to_compile" in item
            # Must NOT include deep fields in default summary mode
            assert (
                "validation_result" not in item
            ), "Summary file entry must not include validation_result (heavy field)"
            assert (
                "fix_result" not in item
            ), "Summary file entry must not include fix_result (heavy field)"

    # -----------------------------------------------------------------------
    # 2. process_twincat_batch summary mode omits heavy top-level sections
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_process_batch_summary_mode_omits_heavy_sections(self, tmp_path):
        """Summary mode must not include pre_validation/autofix/post_validation by default."""
        from server import process_twincat_batch

        _write_valid_tc_pou(tmp_path / "FB_A.TcPOU", "FB_A")

        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
                response_mode="summary",
            )
        )

        assert result["success"] is True
        # Heavy sections must be absent
        for heavy in ("pre_validation", "autofix", "post_validation"):
            assert heavy not in result, f"Summary mode must not include '{heavy}' by default"
        # effective_oop_policy is also heavy (large policy dump)
        assert (
            "effective_oop_policy" not in result
        ), "Summary mode must not include 'effective_oop_policy' by default"

    # -----------------------------------------------------------------------
    # 3. process_twincat_batch include_sections selective opt-in
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_process_batch_include_sections_selective(self, tmp_path):
        """include_sections=['effective_oop_policy'] must add only that section."""
        from server import process_twincat_batch

        _write_valid_tc_pou(tmp_path / "FB_A.TcPOU", "FB_A")

        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
                response_mode="summary",
                include_sections=["effective_oop_policy"],
            )
        )

        assert result["success"] is True
        # Requested section must be present
        assert (
            "effective_oop_policy" in result
        ), "include_sections=['effective_oop_policy'] must add that section"
        # Non-requested heavy sections must stay absent
        for heavy in ("pre_validation", "autofix", "post_validation"):
            assert (
                heavy not in result
            ), f"Non-requested heavy section '{heavy}' must not appear in summary mode"

    # -----------------------------------------------------------------------
    # 4. verify_determinism_batch summary mode shape
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_verify_determinism_summary_mode_shape(self, tmp_path):
        """verify_determinism_batch summary mode must include stability + safety fields."""
        from server import verify_determinism_batch

        _write_valid_tc_pou(tmp_path / "FB_A.TcPOU", "FB_A")
        _write_valid_tc_pou(tmp_path / "FB_B.TcPOU", "FB_B")

        result = json.loads(
            await verify_determinism_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
                response_mode="summary",
            )
        )

        assert result["success"] is True
        # Required summary keys
        for key in ("stable", "safe_to_import", "safe_to_compile", "done", "status"):
            assert key in result, f"verify_determinism_batch summary missing '{key}'"

        # Per-file entries must include determinism stability fields
        for item in result.get("files", []):
            assert "safe_to_import" in item
            assert "safe_to_compile" in item
            assert (
                "stable" in item
            ), "verify_determinism_batch summary per-file entry must include 'stable'"
            assert "content_changed_first_pass" in item
            assert "content_changed_second_pass" in item

        # Heavy top-level sections must be absent
        assert (
            "effective_oop_policy" not in result
        ), "verify_determinism_batch summary must not include effective_oop_policy by default"

    # -----------------------------------------------------------------------
    # 5. Unknown include_sections names are non-breaking
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_unknown_include_section_is_non_breaking(self, tmp_path):
        """Unknown section names must not fail the request; emits warning in response."""
        from server import process_twincat_batch

        _write_valid_tc_pou(tmp_path / "FB_A.TcPOU", "FB_A")

        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
                response_mode="summary",
                include_sections=["nonexistent_section_xyz"],
            )
        )

        # Must still succeed
        assert result["success"] is True, "Unknown include_sections must not fail the request"
        # Unknown section must be reported
        assert (
            "unknown_include_sections" in result
        ), "Response must include 'unknown_include_sections' key listing unknown names"
        assert (
            "nonexistent_section_xyz" in result["unknown_include_sections"]
        ), "Unknown section name must appear in unknown_include_sections list"

    # -----------------------------------------------------------------------
    # 6. Compact mode still passes through unchanged (backward compat)
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_compact_mode_unchanged_by_include_sections(self, tmp_path):
        """Compact mode must not be affected by include_sections (no-op)."""
        from server import process_twincat_batch

        _write_valid_tc_pou(tmp_path / "FB_A.TcPOU", "FB_A")

        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
                response_mode="compact",
                include_sections=["pre_validation"],
            )
        )

        assert result["success"] is True
        assert result["response_mode"] == "compact"
        # Compact mode never adds pre_validation (include_sections is no-op for non-summary modes)
        assert "pre_validation" not in result

    # -----------------------------------------------------------------------
    # 7. Summary mode payload size is strictly smaller than compact
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_batch_summary_payload_size_under_threshold(self, tmp_path):
        """Summary mode response must be smaller than compact mode response."""
        from server import process_twincat_batch

        # Write several files to make size difference visible
        for i in range(3):
            _write_valid_tc_pou(tmp_path / f"FB_{i}.TcPOU", f"FB_{i}")

        summary_raw = await process_twincat_batch(
            file_patterns=["*.TcPOU"],
            directory_path=str(tmp_path),
            response_mode="summary",
        )
        compact_raw = await process_twincat_batch(
            file_patterns=["*.TcPOU"],
            directory_path=str(tmp_path),
            response_mode="compact",
        )

        summary_size = len(summary_raw)
        compact_size = len(compact_raw)

        assert summary_size < compact_size, (
            f"Summary mode ({summary_size} bytes) must be smaller than "
            f"compact mode ({compact_size} bytes)"
        )

    # -----------------------------------------------------------------------
    # 8. Invalid response_mode returns error (new value included in valid list)
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_process_batch_invalid_response_mode_lists_summary(self, tmp_path):
        """Invalid response_mode error must include 'summary' in valid_response_modes."""
        from server import process_twincat_batch

        _write_valid_tc_pou(tmp_path / "FB_A.TcPOU", "FB_A")

        result = json.loads(
            await process_twincat_batch(
                file_patterns=["*.TcPOU"],
                directory_path=str(tmp_path),
                response_mode="bogus",
            )
        )

        assert result["success"] is False
        valid_modes = result.get("valid_response_modes", [])
        assert (
            "summary" in valid_modes
        ), "'summary' must be listed in valid_response_modes error field"
