"""Validation check modules."""

import importlib
import pkgutil

from .base import BaseCheck, CheckRegistry


def _autoload_check_modules() -> None:
    """Import all *_checks modules in this package to trigger registration."""
    for _, module_name, _ in sorted(pkgutil.iter_modules(__path__), key=lambda item: item[1]):
        if module_name.endswith("_checks"):
            importlib.import_module(f"{__name__}.{module_name}")


_autoload_check_modules()

__all__ = ["BaseCheck", "CheckRegistry"]
