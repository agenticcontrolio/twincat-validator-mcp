"""Tests for twincat_validator.fixers.base module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from twincat_validator.fixers.base import BaseFix, FixRegistry
from twincat_validator.exceptions import FixNotFoundError


class TestBaseFix:
    """Tests for BaseFix abstract class."""

    def test_cannot_instantiate_base_fix_directly(self):
        """Test BaseFix is abstract and cannot be instantiated."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            BaseFix()

    def test_must_implement_apply_method(self):
        """Test subclass must implement apply() method."""

        class IncompleteFix(BaseFix):
            fix_id = "incomplete"

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteFix()

    def test_should_skip_defaults_to_false(self):
        """Test default should_skip() returns False."""

        class TestFix(BaseFix):
            fix_id = "test"

            def apply(self, file):
                return True

        fix = TestFix()
        # Pass a mock file object
        assert fix.should_skip(None) is False

    def test_can_override_should_skip(self):
        """Test should_skip() can be overridden."""

        class ConditionalFix(BaseFix):
            fix_id = "conditional"

            def apply(self, file):
                return True

            def should_skip(self, file):
                return file.suffix == ".TcIO"

        fix = ConditionalFix()

        # Mock file with .TcPOU suffix
        class MockFile:
            suffix = ".TcPOU"

        assert fix.should_skip(MockFile()) is False

        # Mock file with .TcIO suffix
        class MockFileIO:
            suffix = ".TcIO"

        assert fix.should_skip(MockFileIO()) is True


class TestFixRegistry:
    """Tests for FixRegistry auto-discovery."""

    def setup_method(self):
        """Clear registry before each test to ensure isolation."""
        FixRegistry.clear()

    def teardown_method(self):
        """Clear registry after each test."""
        FixRegistry.clear()

    def test_register_fix_class(self):
        """Test registering a fix class."""

        @FixRegistry.register
        class TestFix(BaseFix):
            fix_id = "test_fix"

            def apply(self, file):
                return True

        assert "test_fix" in FixRegistry.get_all_fixes()
        assert FixRegistry.get_fix("test_fix") == TestFix

    def test_register_returns_class_unchanged(self):
        """Test register decorator returns class unchanged (passthrough)."""

        @FixRegistry.register
        class TestFix(BaseFix):
            fix_id = "test"

            def apply(self, file):
                return True

        # Should be able to instantiate normally
        instance = TestFix()
        assert isinstance(instance, BaseFix)

    def test_register_raises_on_missing_fix_id(self):
        """Test registering a fix without fix_id raises ValueError."""

        with pytest.raises(ValueError, match="must define 'fix_id'"):

            @FixRegistry.register
            class InvalidFix(BaseFix):
                def apply(self, file):
                    return True

    def test_register_raises_on_duplicate_fix_id(self):
        """Test registering duplicate fix_id raises ValueError."""

        @FixRegistry.register
        class FirstFix(BaseFix):
            fix_id = "duplicate"

            def apply(self, file):
                return True

        with pytest.raises(ValueError, match="already registered"):

            @FixRegistry.register
            class SecondFix(BaseFix):
                fix_id = "duplicate"

                def apply(self, file):
                    return True

    def test_register_raises_on_non_basefix_subclass(self):
        """Test registering non-BaseFix class raises TypeError."""

        with pytest.raises(TypeError, match="must inherit from BaseFix"):

            class NotAFix:
                fix_id = "not_a_fix"

            FixRegistry.register(NotAFix)

    def test_register_raises_on_empty_fix_id(self):
        """Test registering with empty fix_id raises ValueError."""

        with pytest.raises(ValueError, match="must be a non-empty string"):

            @FixRegistry.register
            class EmptyFixIdFix(BaseFix):
                fix_id = ""

                def apply(self, file):
                    return True

    def test_register_raises_on_whitespace_fix_id(self):
        """Test registering with whitespace-only fix_id raises ValueError."""

        with pytest.raises(ValueError, match="must be a non-empty string"):

            @FixRegistry.register
            class WhitespaceFixIdFix(BaseFix):
                fix_id = "   "

                def apply(self, file):
                    return True

    def test_register_raises_on_non_string_fix_id(self):
        """Test registering with non-string fix_id raises ValueError."""

        with pytest.raises(ValueError, match="must be a non-empty string"):

            @FixRegistry.register
            class NonStringFixIdFix(BaseFix):
                fix_id = 123

                def apply(self, file):
                    return True

    def test_get_fix_retrieves_registered_fix(self):
        """Test get_fix() retrieves a registered fix class."""

        @FixRegistry.register
        class TestFix(BaseFix):
            fix_id = "retrieval_test"

            def apply(self, file):
                return True

        retrieved = FixRegistry.get_fix("retrieval_test")
        assert retrieved == TestFix

    def test_get_fix_raises_on_unknown_fix_id(self):
        """Test get_fix() raises FixNotFoundError for unknown ID."""

        with pytest.raises(FixNotFoundError, match="Fix 'unknown' not found"):
            FixRegistry.get_fix("unknown")

    def test_get_fix_error_lists_available_fixes(self):
        """Test FixNotFoundError includes list of available fixes."""

        @FixRegistry.register
        class FixA(BaseFix):
            fix_id = "fix_a"

            def apply(self, file):
                return True

        @FixRegistry.register
        class FixB(BaseFix):
            fix_id = "fix_b"

            def apply(self, file):
                return True

        with pytest.raises(FixNotFoundError, match="fix_a, fix_b"):
            FixRegistry.get_fix("nonexistent")

    def test_get_all_fixes_returns_dict(self):
        """Test get_all_fixes() returns dict of all registered fixes."""

        @FixRegistry.register
        class Fix1(BaseFix):
            fix_id = "one"

            def apply(self, file):
                return True

        @FixRegistry.register
        class Fix2(BaseFix):
            fix_id = "two"

            def apply(self, file):
                return True

        all_fixes = FixRegistry.get_all_fixes()
        assert isinstance(all_fixes, dict)
        assert len(all_fixes) == 2
        assert all_fixes["one"] == Fix1
        assert all_fixes["two"] == Fix2

    def test_get_all_fixes_returns_copy(self):
        """Test get_all_fixes() returns a copy, not the internal dict."""

        @FixRegistry.register
        class TestFix(BaseFix):
            fix_id = "test"

            def apply(self, file):
                return True

        fixes = FixRegistry.get_all_fixes()
        fixes["fake"] = None

        # Should not affect internal registry
        assert "fake" not in FixRegistry.get_all_fixes()

    def test_clear_removes_all_fixes(self):
        """Test clear() removes all registered fixes."""

        @FixRegistry.register
        class Fix1(BaseFix):
            fix_id = "one"

            def apply(self, file):
                return True

        @FixRegistry.register
        class Fix2(BaseFix):
            fix_id = "two"

            def apply(self, file):
                return True

        assert len(FixRegistry.get_all_fixes()) == 2

        FixRegistry.clear()

        assert len(FixRegistry.get_all_fixes()) == 0

    def test_multiple_registrations_in_sequence(self):
        """Test registering multiple fixes in sequence works correctly."""
        fix_classes = []

        for i in range(5):

            @FixRegistry.register
            class DynamicFix(BaseFix):
                fix_id = f"fix_{i}"

                def apply(self, file):
                    return True

            fix_classes.append(DynamicFix)

        all_fixes = FixRegistry.get_all_fixes()
        assert len(all_fixes) == 5
        for i in range(5):
            assert f"fix_{i}" in all_fixes
