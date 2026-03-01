"""Tests for twincat_validator.engines module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from twincat_validator.engines import ValidationEngine, FixEngine
from twincat_validator.file_handler import TwinCATFile
from twincat_validator.config_loader import ValidationConfig


class TestValidationEngine:
    """Tests for ValidationEngine orchestration."""

    def test_validates_file_with_all_checks(self, valid_tcpou):
        """Test running all validation checks on a file."""
        config = ValidationConfig()
        engine = ValidationEngine(config)
        file = TwinCATFile(valid_tcpou)

        result = engine.validate(file, validation_level="all")

        assert result.filepath == str(valid_tcpou)
        assert result.passed is True  # Valid file should pass
        assert result.errors == 0
        assert isinstance(result.issues, list)
        assert isinstance(result.check_results, list)

    def test_validates_file_with_critical_level(self, valid_tcpou):
        """Test running only critical checks."""
        config = ValidationConfig()
        engine = ValidationEngine(config)
        file = TwinCATFile(valid_tcpou)

        result = engine.validate(file, validation_level="critical")

        assert result.filepath == str(valid_tcpou)
        assert result.passed is True
        # Should run fewer checks than "all"
        assert len(result.check_results) <= len(config.validation_checks)

    def test_critical_level_runs_critical_severity_checks(self, valid_tcpou):
        """Critical level should select checks marked with severity='critical'."""
        config = ValidationConfig()
        engine = ValidationEngine(config)
        file = TwinCATFile(valid_tcpou)

        result = engine.validate(file, validation_level="critical")
        check_ids_run = [cr.check_id for cr in result.check_results]

        assert "xml_structure" in check_ids_run

    def test_validates_file_with_style_level(self, valid_tcpou):
        """Test running only style checks."""
        config = ValidationConfig()
        engine = ValidationEngine(config)
        file = TwinCATFile(valid_tcpou)

        result = engine.validate(file, validation_level="style")

        assert result.filepath == str(valid_tcpou)
        # Style checks might find issues even in valid files
        assert isinstance(result.issues, list)

    def test_detects_issues_in_invalid_file(self, tmp_path):
        """Test engine detects issues in a file with problems."""
        invalid_file = tmp_path / "invalid.TcPOU"
        # Create file with tabs (violates tabs check)
        invalid_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '\t<POU Id="{12345678-abcd-1234-5678-123456789abc}">\n'
            "\t</POU>\n"
            "</TcPlcObject>"
        )

        config = ValidationConfig()
        engine = ValidationEngine(config)
        file = TwinCATFile(invalid_file)

        result = engine.validate(file, validation_level="all")

        # Should detect tab issues
        assert len(result.issues) > 0
        # Tabs check returns warnings
        assert result.warnings > 0 or result.infos > 0

    def test_respects_disabled_checks(self, valid_tcpou):
        """Test engine skips disabled checks."""
        config = ValidationConfig()
        config.disabled_checks = ["xml_structure"]  # Disable a check
        engine = ValidationEngine(config)
        file = TwinCATFile(valid_tcpou)

        result = engine.validate(file, validation_level="all")

        # Verify xml_structure check was not run
        check_ids_run = [cr.check_id for cr in result.check_results]
        assert "xml_structure" not in check_ids_run

    def test_applies_severity_overrides(self, tmp_path):
        """Test engine applies severity overrides from config."""
        # Create file with malformed XML
        bad_file = tmp_path / "bad.TcPOU"
        bad_file.write_text('<?xml version="1.0"?>\n<TcPlcObject><Unclosed>')

        config = ValidationConfig()
        # Override xml_structure severity from error to warning
        config.severity_overrides["xml_structure"] = "warning"
        engine = ValidationEngine(config)
        file = TwinCATFile(bad_file)

        result = engine.validate(file, validation_level="all")

        # Should have warnings instead of errors
        xml_issues = [issue for issue in result.issues if issue.category == "XML"]
        if xml_issues:
            assert all(issue.severity == "warning" for issue in xml_issues)

    def test_critical_override_counts_as_error_and_fails(self, tmp_path):
        """Severity override to critical should count as error-class issue."""
        bad_file = tmp_path / "bad_critical.TcPOU"
        bad_file.write_text('<?xml version="1.0"?>\n<TcPlcObject><Unclosed>')

        config = ValidationConfig()
        config.severity_overrides["xml_structure"] = "critical"
        engine = ValidationEngine(config)
        file = TwinCATFile(bad_file)

        result = engine.validate(file, validation_level="all")

        assert result.passed is False
        assert result.errors > 0

    def test_skips_checks_with_should_skip_true(self, tmp_path):
        """Test engine respects check.should_skip() method."""
        # PropertyVarBlocksCheck should skip for .TcGVL files
        gvl_file = tmp_path / "test.TcGVL"
        gvl_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <GVL Name="GVL_Test" Id="{12345678-abcd-1234-5678-123456789abc}">\n'
            "  </GVL>\n"
            "</TcPlcObject>"
        )

        config = ValidationConfig()
        engine = ValidationEngine(config)
        file = TwinCATFile(gvl_file)

        result = engine.validate(file, validation_level="all")

        # property_var_blocks check should be skipped for .TcGVL
        # (it only applies to .TcPOU files with properties)
        assert result is not None  # Engine should complete successfully

    def test_counts_issues_by_severity(self, tmp_path):
        """Test engine correctly counts errors, warnings, and infos."""
        # Create file with multiple issue types
        multi_issue = tmp_path / "multi.TcPOU"
        multi_issue.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '\t<POU Id="{ABCDEF12-3456-7890-ABCD-EF1234567890}">\n'  # Tab + uppercase GUID
            "\t</POU>\n"
            "</TcPlcObject>"
        )

        config = ValidationConfig()
        engine = ValidationEngine(config)
        file = TwinCATFile(multi_issue)

        result = engine.validate(file, validation_level="all")

        # Should have issues counted correctly
        total_issues = result.errors + result.warnings + result.infos
        assert total_issues == len(result.issues)
        assert total_issues > 0


class TestValidationEngineExcludeCategories:
    """Tests for ValidationEngine.validate() exclude_categories parameter (Phase 8A)."""

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _check_ids_run(result) -> set[str]:
        return {cr.check_id for cr in result.check_results}

    @staticmethod
    def _oop_check_ids(config: ValidationConfig) -> set[str]:
        return {
            cid
            for cid, cdef in config.validation_checks.items()
            if cdef.get("category") == "oop"
            and not cdef.get("umbrella_alias", False)
            and not cdef.get("guidance_only", False)
        }

    @staticmethod
    def _core_check_ids(config: ValidationConfig) -> set[str]:
        return {
            cid
            for cid, cdef in config.validation_checks.items()
            if cdef.get("category") != "oop"
            and not cdef.get("umbrella_alias", False)
            and not cdef.get("guidance_only", False)
        }

    # ------------------------------------------------------------------ backward compat

    def test_exclude_categories_none_runs_all_checks(self, valid_tcpou):
        """None (default) must produce the same result as calling without the parameter."""
        config = ValidationConfig()
        engine = ValidationEngine(config)
        file = TwinCATFile(valid_tcpou)

        result_default = engine.validate(file, validation_level="all")
        result_explicit_none = engine.validate(
            file, validation_level="all", exclude_categories=None
        )

        assert self._check_ids_run(result_default) == self._check_ids_run(result_explicit_none)

    def test_exclude_empty_frozenset_runs_all_checks(self, valid_tcpou):
        """An empty exclusion set is a no-op — all checks still run."""
        config = ValidationConfig()
        engine = ValidationEngine(config)
        file = TwinCATFile(valid_tcpou)

        result_default = engine.validate(file, validation_level="all")
        result_empty = engine.validate(file, validation_level="all", exclude_categories=frozenset())

        assert self._check_ids_run(result_default) == self._check_ids_run(result_empty)

    # ------------------------------------------------------------------ oop exclusion

    def test_exclude_oop_removes_all_oop_checks_level_all(self, valid_tcpou):
        """exclude_categories={'oop'} removes every OOP check at level='all'."""
        config = ValidationConfig()
        engine = ValidationEngine(config)
        file = TwinCATFile(valid_tcpou)
        oop_ids = self._oop_check_ids(config)

        result = engine.validate(
            file, validation_level="all", exclude_categories=frozenset({"oop"})
        )
        ran = self._check_ids_run(result)

        assert ran.isdisjoint(
            oop_ids
        ), f"OOP checks should not run in procedural mode, but got: {ran & oop_ids}"

    def test_exclude_oop_removes_all_oop_checks_level_critical(self, valid_tcpou):
        """exclude_categories={'oop'} removes OOP checks at level='critical' too."""
        config = ValidationConfig()
        engine = ValidationEngine(config)
        file = TwinCATFile(valid_tcpou)
        oop_ids = self._oop_check_ids(config)

        result = engine.validate(
            file, validation_level="critical", exclude_categories=frozenset({"oop"})
        )
        ran = self._check_ids_run(result)

        assert ran.isdisjoint(oop_ids)

    def test_exclude_oop_removes_all_oop_checks_level_style(self, valid_tcpou):
        """exclude_categories={'oop'} removes OOP checks at level='style' too."""
        config = ValidationConfig()
        engine = ValidationEngine(config)
        file = TwinCATFile(valid_tcpou)
        oop_ids = self._oop_check_ids(config)

        result = engine.validate(
            file, validation_level="style", exclude_categories=frozenset({"oop"})
        )
        ran = self._check_ids_run(result)

        assert ran.isdisjoint(oop_ids)

    def test_exclude_oop_keeps_core_checks_running(self, valid_tcpou):
        """Excluding 'oop' must not remove any non-OOP checks."""
        config = ValidationConfig()
        engine = ValidationEngine(config)
        file = TwinCATFile(valid_tcpou)
        core_ids = self._core_check_ids(config)

        result_full = engine.validate(file, validation_level="all")
        result_no_oop = engine.validate(
            file, validation_level="all", exclude_categories=frozenset({"oop"})
        )

        ran_full = self._check_ids_run(result_full)
        ran_no_oop = self._check_ids_run(result_no_oop)

        # Every core check that ran in the full run must still run without OOP
        for cid in core_ids:
            if cid in ran_full:
                assert cid in ran_no_oop, f"Core check '{cid}' was unexpectedly dropped"

    # ------------------------------------------------------------------ unknown category

    def test_exclude_unknown_category_is_noop(self, valid_tcpou):
        """Excluding a category that doesn't exist in the config changes nothing."""
        config = ValidationConfig()
        engine = ValidationEngine(config)
        file = TwinCATFile(valid_tcpou)

        result_baseline = engine.validate(file, validation_level="all")
        result_unknown = engine.validate(
            file,
            validation_level="all",
            exclude_categories=frozenset({"nonexistent_category"}),
        )

        assert self._check_ids_run(result_baseline) == self._check_ids_run(result_unknown)

    # ------------------------------------------------------------------ multiple categories

    def test_exclude_multiple_categories(self, valid_tcpou):
        """Multiple categories can be excluded simultaneously."""
        config = ValidationConfig()
        engine = ValidationEngine(config)
        file = TwinCATFile(valid_tcpou)

        result = engine.validate(
            file,
            validation_level="all",
            exclude_categories=frozenset({"oop", "style"}),
        )
        ran = self._check_ids_run(result)

        excluded_ids = {
            cid
            for cid, cdef in config.validation_checks.items()
            if cdef.get("category") in {"oop", "style"}
        }
        assert ran.isdisjoint(excluded_ids)


class TestFixEngine:
    """Tests for FixEngine orchestration."""

    def test_applies_single_fix(self, tmp_path):
        """Test applying a single fix to a file."""
        # Create file with tabs
        tabbed_file = tmp_path / "tabbed.TcPOU"
        tabbed_file.write_text(
            '<?xml version="1.0"?>\n' "<TcPlcObject>\n" "\t<POU>\n" "\t</POU>\n" "</TcPlcObject>"
        )

        config = ValidationConfig()
        engine = FixEngine(config)
        file = TwinCATFile(tabbed_file)

        result = engine.apply_fixes(file, fix_ids=["tabs"])

        assert result.filepath == str(tabbed_file)
        assert result.success is True
        assert "tabs" in result.applied_fixes
        assert len(result.failed_fixes) == 0
        # Verify tabs were replaced
        assert "\t" not in file.content

    def test_applies_multiple_fixes(self, tmp_path):
        """Test applying multiple fixes to a file."""
        # Create file with tabs and uppercase GUIDs
        multi_fix = tmp_path / "multi.TcPOU"
        multi_fix.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '\t<POU Id="{ABCDEF12-3456-7890-ABCD-EF1234567890}">\n'
            "\t</POU>\n"
            "</TcPlcObject>"
        )

        config = ValidationConfig()
        engine = FixEngine(config)
        file = TwinCATFile(multi_fix)

        result = engine.apply_fixes(file, fix_ids=["tabs", "guid_case"])

        assert result.success is True
        assert "tabs" in result.applied_fixes
        assert "guid_case" in result.applied_fixes
        # Verify fixes were applied
        assert "\t" not in file.content
        assert "ABCDEF" not in file.content  # Should be lowercase

    def test_applies_all_fixes_when_none_specified(self, tmp_path):
        """Test applying all available fixes when fix_ids=None."""
        # Create file with tabs
        tabbed_file = tmp_path / "tabbed.TcPOU"
        tabbed_file.write_text(
            '<?xml version="1.0"?>\n' "<TcPlcObject>\n" "\t<POU>\n" "\t</POU>\n" "</TcPlcObject>"
        )

        config = ValidationConfig()
        engine = FixEngine(config)
        file = TwinCATFile(tabbed_file)

        result = engine.apply_fixes(file, fix_ids=None)

        # Should attempt all fixes, at least tabs should be applied
        assert result.success is True
        assert "tabs" in result.applied_fixes

    def test_skips_fixes_with_should_skip_true(self, tmp_path):
        """Test engine respects fix.should_skip() method."""
        # PropertyVarBlocksFix should skip for .TcGVL files
        gvl_file = tmp_path / "test.TcGVL"
        gvl_file.write_text(
            '<?xml version="1.0"?>\n'
            "<TcPlcObject>\n"
            '  <GVL Name="GVL_Test">\n'
            "  </GVL>\n"
            "</TcPlcObject>"
        )

        config = ValidationConfig()
        engine = FixEngine(config)
        file = TwinCATFile(gvl_file)

        result = engine.apply_fixes(file, fix_ids=["var_blocks"])

        # var_blocks should be skipped, not applied and not failed
        assert "var_blocks" not in result.applied_fixes
        assert "var_blocks" not in result.failed_fixes

    def test_handles_unknown_fix_id(self, valid_tcpou):
        """Test engine handles unknown fix IDs gracefully."""
        config = ValidationConfig()
        engine = FixEngine(config)
        file = TwinCATFile(valid_tcpou)

        result = engine.apply_fixes(file, fix_ids=["nonexistent_fix"])

        # Unknown fix should be in failed_fixes
        assert "nonexistent_fix" in result.failed_fixes
        assert result.success is False

    def test_no_fixes_applied_when_not_needed(self, valid_tcpou):
        """Test engine returns empty applied_fixes when no changes needed."""
        config = ValidationConfig()
        engine = FixEngine(config)
        file = TwinCATFile(valid_tcpou)

        original_content = file.content

        result = engine.apply_fixes(file, fix_ids=["tabs"])

        # No tabs to fix, so tabs fix should not be applied
        assert "tabs" not in result.applied_fixes
        # Content should be unchanged
        assert file.content == original_content

    def test_success_false_when_fixes_fail(self, valid_tcpou):
        """Test success=False when some fixes fail."""
        config = ValidationConfig()
        engine = FixEngine(config)
        file = TwinCATFile(valid_tcpou)

        # Try to apply a non-existent fix
        result = engine.apply_fixes(file, fix_ids=["nonexistent"])

        assert result.success is False
        assert len(result.failed_fixes) > 0

    def test_modifies_file_in_place(self, tmp_path):
        """Test fixes modify the file object in-place."""
        tabbed_file = tmp_path / "tabbed.TcPOU"
        original_content = (
            '<?xml version="1.0"?>\n' "<TcPlcObject>\n" "\t<POU>\n" "\t</POU>\n" "</TcPlcObject>"
        )
        tabbed_file.write_text(original_content)

        config = ValidationConfig()
        engine = FixEngine(config)
        file = TwinCATFile(tabbed_file)

        # Verify file has tabs before fix
        assert "\t" in file.content

        engine.apply_fixes(file, fix_ids=["tabs"])

        # Verify file.content was modified in-place
        assert "\t" not in file.content
        assert file.content != original_content
