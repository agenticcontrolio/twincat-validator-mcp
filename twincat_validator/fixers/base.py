"""Base classes for auto-fix operations with auto-discovery registry."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..file_handler import TwinCATFile


class BaseFix(ABC):
    """Abstract base class for all auto-fix operations.

    Each fix must define:
    - fix_id: Unique identifier matching config/fix_capabilities.json
    - apply(): Execute the fix and return success boolean

    Optional:
    - should_skip(): Return True to skip this fix for specific file types
    """

    fix_id: str  # Must be set by subclass

    @abstractmethod
    def apply(self, file: "TwinCATFile") -> bool:
        """Apply the fix to the file.

        Args:
            file: TwinCATFile to modify (modifies file.content in-place)

        Returns:
            True if fix was applied successfully, False otherwise
        """
        pass

    def should_skip(self, file: "TwinCATFile") -> bool:
        """Determine if this fix should be skipped for the given file.

        Override this method for fixes that only apply to certain file types
        (e.g., property VAR block fixes only for .TcPOU with properties).

        Args:
            file: TwinCATFile to check

        Returns:
            True if fix should be skipped, False otherwise (default)
        """
        return False


class FixRegistry:
    """Registry for auto-discovering and managing auto-fix operations.

    Usage:
        @FixRegistry.register
        class MyFix(BaseFix):
            fix_id = "my_fix"
            def apply(self, file):
                return True

        fix = FixRegistry.get_fix("my_fix")
        all_fixes = FixRegistry.get_all_fixes()
    """

    _fixes: dict[str, type[BaseFix]] = {}

    @classmethod
    def register(cls, fix_class: type[BaseFix]) -> type[BaseFix]:
        """Decorator to register a fix class.

        Args:
            fix_class: BaseFix subclass to register

        Returns:
            The fix_class unchanged (passthrough decorator)

        Raises:
            TypeError: If fix_class is not a BaseFix subclass
            ValueError: If fix_id is missing, invalid, or already registered
        """
        if not issubclass(fix_class, BaseFix):
            raise TypeError(f"Fix class {fix_class.__name__} must inherit from BaseFix")

        if not hasattr(fix_class, "fix_id"):
            raise ValueError(f"Fix class {fix_class.__name__} must define 'fix_id' class attribute")

        fix_id = fix_class.fix_id
        if not isinstance(fix_id, str) or not fix_id.strip():
            raise ValueError(
                f"Fix class {fix_class.__name__} has invalid fix_id: " "must be a non-empty string"
            )
        if fix_id in cls._fixes:
            raise ValueError(
                f"Fix '{fix_id}' is already registered by {cls._fixes[fix_id].__name__}"
            )

        cls._fixes[fix_id] = fix_class
        return fix_class

    @classmethod
    def get_fix(cls, fix_id: str) -> type[BaseFix]:
        """Retrieve a fix class by ID.

        Args:
            fix_id: Unique fix identifier

        Returns:
            BaseFix subclass

        Raises:
            FixNotFoundError: If fix_id not registered
        """
        from ..exceptions import FixNotFoundError

        if fix_id not in cls._fixes:
            raise FixNotFoundError(
                f"Fix '{fix_id}' not found. Available fixes: "
                f"{', '.join(sorted(cls._fixes.keys()))}"
            )
        return cls._fixes[fix_id]

    @classmethod
    def get_all_fixes(cls) -> dict[str, type[BaseFix]]:
        """Get all registered fixes.

        Returns:
            Dict mapping fix_id to fix class
        """
        return cls._fixes.copy()

    @classmethod
    def clear(cls) -> None:
        """Clear all registered fixes.

        This is primarily for testing purposes to reset registry state.
        """
        cls._fixes.clear()
