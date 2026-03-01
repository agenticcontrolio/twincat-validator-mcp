"""Base classes for validation checks with auto-discovery registry."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..file_handler import TwinCATFile
    from ..models import ValidationIssue


class BaseCheck(ABC):
    """Abstract base class for all validation checks.

    Each check must define:
    - check_id: Unique identifier matching config/validation_rules.json
    - run(): Execute the check and return ValidationIssue list

    Optional:
    - should_skip(): Return True to skip this check for specific file types
    """

    check_id: str  # Must be set by subclass

    @abstractmethod
    def run(self, file: "TwinCATFile") -> list["ValidationIssue"]:
        """Execute the validation check.

        Args:
            file: TwinCATFile to validate

        Returns:
            List of ValidationIssue objects (empty if no issues found)
        """
        pass

    def should_skip(self, file: "TwinCATFile") -> bool:
        """Determine if this check should be skipped for the given file.

        Override this method for checks that only apply to certain file types
        or POU subtypes (e.g., property VAR blocks only for FUNCTIONs).

        Args:
            file: TwinCATFile to check

        Returns:
            True if check should be skipped, False otherwise (default)
        """
        return False


class CheckRegistry:
    """Registry for auto-discovering and managing validation checks.

    Usage:
        @CheckRegistry.register
        class MyCheck(BaseCheck):
            check_id = "my_check"
            def run(self, file):
                return []

        check = CheckRegistry.get_check("my_check")
        all_checks = CheckRegistry.get_all_checks()
    """

    _checks: dict[str, type[BaseCheck]] = {}

    @classmethod
    def register(cls, check_class: type[BaseCheck]) -> type[BaseCheck]:
        """Decorator to register a check class.

        Args:
            check_class: BaseCheck subclass to register

        Returns:
            The check_class unchanged (passthrough decorator)

        Raises:
            TypeError: If check_class is not a BaseCheck subclass
            ValueError: If check_id is missing, invalid, or already registered
        """
        if not issubclass(check_class, BaseCheck):
            raise TypeError(f"Check class {check_class.__name__} must inherit from BaseCheck")

        if not hasattr(check_class, "check_id"):
            raise ValueError(
                f"Check class {check_class.__name__} must define 'check_id' class attribute"
            )

        check_id = check_class.check_id
        if not isinstance(check_id, str) or not check_id.strip():
            raise ValueError(
                f"Check class {check_class.__name__} has invalid check_id: "
                "must be a non-empty string"
            )
        if check_id in cls._checks:
            raise ValueError(
                f"Check '{check_id}' is already registered by " f"{cls._checks[check_id].__name__}"
            )

        cls._checks[check_id] = check_class
        return check_class

    @classmethod
    def get_check(cls, check_id: str) -> type[BaseCheck]:
        """Retrieve a check class by ID.

        Args:
            check_id: Unique check identifier

        Returns:
            BaseCheck subclass

        Raises:
            CheckNotFoundError: If check_id not registered
        """
        from ..exceptions import CheckNotFoundError

        if check_id not in cls._checks:
            raise CheckNotFoundError(
                f"Check '{check_id}' not found. Available checks: "
                f"{', '.join(sorted(cls._checks.keys()))}"
            )
        return cls._checks[check_id]

    @classmethod
    def get_all_checks(cls) -> dict[str, type[BaseCheck]]:
        """Get all registered checks.

        Returns:
            Dict mapping check_id to check class
        """
        return cls._checks.copy()

    @classmethod
    def clear(cls) -> None:
        """Clear all registered checks.

        This is primarily for testing purposes to reset registry state.
        """
        cls._checks.clear()
