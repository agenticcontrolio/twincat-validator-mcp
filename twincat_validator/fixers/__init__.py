"""Auto-fix modules."""

import importlib
import pkgutil

from .base import BaseFix, FixRegistry


def _autoload_fix_modules() -> None:
    """Import all *_fixes modules in this package to trigger registration."""
    for _, module_name, _ in sorted(pkgutil.iter_modules(__path__), key=lambda item: item[1]):
        if module_name.endswith("_fixes"):
            importlib.import_module(f"{__name__}.{module_name}")


_autoload_fix_modules()

__all__ = ["BaseFix", "FixRegistry"]
