"""Tests for twincat_validator.validators.base module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from twincat_validator.validators.base import BaseCheck, CheckRegistry
from twincat_validator.exceptions import CheckNotFoundError


class TestBaseCheck:
    """Tests for BaseCheck abstract class."""

    def test_cannot_instantiate_base_check_directly(self):
        """Test BaseCheck is abstract and cannot be instantiated."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            BaseCheck()

    def test_must_implement_run_method(self):
        """Test subclass must implement run() method."""

        class IncompleteCheck(BaseCheck):
            check_id = "incomplete"

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteCheck()

    def test_should_skip_defaults_to_false(self):
        """Test default should_skip() returns False."""

        class TestCheck(BaseCheck):
            check_id = "test"

            def run(self, file):
                return []

        check = TestCheck()
        # Pass a mock file object
        assert check.should_skip(None) is False

    def test_can_override_should_skip(self):
        """Test should_skip() can be overridden."""

        class ConditionalCheck(BaseCheck):
            check_id = "conditional"

            def run(self, file):
                return []

            def should_skip(self, file):
                return file.suffix == ".TcIO"

        check = ConditionalCheck()

        # Mock file with .TcPOU suffix
        class MockFile:
            suffix = ".TcPOU"

        assert check.should_skip(MockFile()) is False

        # Mock file with .TcIO suffix
        class MockFileIO:
            suffix = ".TcIO"

        assert check.should_skip(MockFileIO()) is True


class TestCheckRegistry:
    """Tests for CheckRegistry auto-discovery."""

    def setup_method(self):
        """Clear registry before each test to ensure isolation."""
        CheckRegistry.clear()

    def teardown_method(self):
        """Re-import validators to restore real checks after test isolation."""
        CheckRegistry.clear()
        # Re-import to restore real checks (like XmlStructureCheck)
        import twincat_validator.validators  # noqa: F401

    def test_register_check_class(self):
        """Test registering a check class."""

        @CheckRegistry.register
        class TestCheck(BaseCheck):
            check_id = "test_check"

            def run(self, file):
                return []

        assert "test_check" in CheckRegistry.get_all_checks()
        assert CheckRegistry.get_check("test_check") == TestCheck

    def test_register_returns_class_unchanged(self):
        """Test register decorator returns class unchanged (passthrough)."""

        @CheckRegistry.register
        class TestCheck(BaseCheck):
            check_id = "test"

            def run(self, file):
                return []

        # Should be able to instantiate normally
        instance = TestCheck()
        assert isinstance(instance, BaseCheck)

    def test_register_raises_on_missing_check_id(self):
        """Test registering a check without check_id raises ValueError."""

        with pytest.raises(ValueError, match="must define 'check_id'"):

            @CheckRegistry.register
            class InvalidCheck(BaseCheck):
                def run(self, file):
                    return []

    def test_register_raises_on_duplicate_check_id(self):
        """Test registering duplicate check_id raises ValueError."""

        @CheckRegistry.register
        class FirstCheck(BaseCheck):
            check_id = "duplicate"

            def run(self, file):
                return []

        with pytest.raises(ValueError, match="already registered"):

            @CheckRegistry.register
            class SecondCheck(BaseCheck):
                check_id = "duplicate"

                def run(self, file):
                    return []

    def test_register_raises_on_non_basecheck_subclass(self):
        """Test registering non-BaseCheck class raises TypeError."""

        with pytest.raises(TypeError, match="must inherit from BaseCheck"):

            class NotACheck:
                check_id = "not_a_check"

            CheckRegistry.register(NotACheck)

    def test_register_raises_on_empty_check_id(self):
        """Test registering with empty check_id raises ValueError."""

        with pytest.raises(ValueError, match="must be a non-empty string"):

            @CheckRegistry.register
            class EmptyCheckIdCheck(BaseCheck):
                check_id = ""

                def run(self, file):
                    return []

    def test_register_raises_on_whitespace_check_id(self):
        """Test registering with whitespace-only check_id raises ValueError."""

        with pytest.raises(ValueError, match="must be a non-empty string"):

            @CheckRegistry.register
            class WhitespaceCheckIdCheck(BaseCheck):
                check_id = "   "

                def run(self, file):
                    return []

    def test_register_raises_on_non_string_check_id(self):
        """Test registering with non-string check_id raises ValueError."""

        with pytest.raises(ValueError, match="must be a non-empty string"):

            @CheckRegistry.register
            class NonStringCheckIdCheck(BaseCheck):
                check_id = 123

                def run(self, file):
                    return []

    def test_get_check_retrieves_registered_check(self):
        """Test get_check() retrieves a registered check class."""

        @CheckRegistry.register
        class TestCheck(BaseCheck):
            check_id = "retrieval_test"

            def run(self, file):
                return []

        retrieved = CheckRegistry.get_check("retrieval_test")
        assert retrieved == TestCheck

    def test_get_check_raises_on_unknown_check_id(self):
        """Test get_check() raises CheckNotFoundError for unknown ID."""

        with pytest.raises(CheckNotFoundError, match="Check 'unknown' not found"):
            CheckRegistry.get_check("unknown")

    def test_get_check_error_lists_available_checks(self):
        """Test CheckNotFoundError includes list of available checks."""

        @CheckRegistry.register
        class CheckA(BaseCheck):
            check_id = "check_a"

            def run(self, file):
                return []

        @CheckRegistry.register
        class CheckB(BaseCheck):
            check_id = "check_b"

            def run(self, file):
                return []

        with pytest.raises(CheckNotFoundError, match="check_a, check_b"):
            CheckRegistry.get_check("nonexistent")

    def test_get_all_checks_returns_dict(self):
        """Test get_all_checks() returns dict of all registered checks."""

        @CheckRegistry.register
        class Check1(BaseCheck):
            check_id = "one"

            def run(self, file):
                return []

        @CheckRegistry.register
        class Check2(BaseCheck):
            check_id = "two"

            def run(self, file):
                return []

        all_checks = CheckRegistry.get_all_checks()
        assert isinstance(all_checks, dict)
        assert len(all_checks) == 2
        assert all_checks["one"] == Check1
        assert all_checks["two"] == Check2

    def test_get_all_checks_returns_copy(self):
        """Test get_all_checks() returns a copy, not the internal dict."""

        @CheckRegistry.register
        class TestCheck(BaseCheck):
            check_id = "test"

            def run(self, file):
                return []

        checks = CheckRegistry.get_all_checks()
        checks["fake"] = None

        # Should not affect internal registry
        assert "fake" not in CheckRegistry.get_all_checks()

    def test_clear_removes_all_checks(self):
        """Test clear() removes all registered checks."""

        @CheckRegistry.register
        class Check1(BaseCheck):
            check_id = "one"

            def run(self, file):
                return []

        @CheckRegistry.register
        class Check2(BaseCheck):
            check_id = "two"

            def run(self, file):
                return []

        assert len(CheckRegistry.get_all_checks()) == 2

        CheckRegistry.clear()

        assert len(CheckRegistry.get_all_checks()) == 0

    def test_multiple_registrations_in_sequence(self):
        """Test registering multiple checks in sequence works correctly."""
        check_classes = []

        for i in range(5):

            @CheckRegistry.register
            class DynamicCheck(BaseCheck):
                check_id = f"check_{i}"

                def run(self, file):
                    return []

            check_classes.append(DynamicCheck)

        all_checks = CheckRegistry.get_all_checks()
        assert len(all_checks) == 5
        for i in range(5):
            assert f"check_{i}" in all_checks
