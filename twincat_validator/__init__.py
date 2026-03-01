"""TwinCAT Validator - Modular validation and auto-fix for TwinCAT XML files."""

from .models import ValidationIssue, CheckResult, ValidationResult, FixApplication
from .file_handler import TwinCATFile
from .config_loader import ValidationConfig
from .validators import BaseCheck, CheckRegistry
from .fixers import BaseFix, FixRegistry
from .engines import ValidationEngine, FixEngine
from .exceptions import (
    TwinCATValidatorError,
    FileValidationError,
    UnsupportedFileTypeError,
    ConfigurationError,
    FixApplicationError,
    CheckNotFoundError,
    FixNotFoundError,
    PolicyResolutionError,
    PolicyEnforcementError,
)
from .policy_context import ExecutionContext

__version__ = "1.0.0"

__all__ = [
    "ValidationIssue",
    "CheckResult",
    "ValidationResult",
    "FixApplication",
    "TwinCATFile",
    "ValidationConfig",
    "BaseCheck",
    "CheckRegistry",
    "BaseFix",
    "FixRegistry",
    "ValidationEngine",
    "FixEngine",
    "TwinCATValidatorError",
    "FileValidationError",
    "UnsupportedFileTypeError",
    "ConfigurationError",
    "FixApplicationError",
    "CheckNotFoundError",
    "FixNotFoundError",
    "PolicyResolutionError",
    "PolicyEnforcementError",
    "ExecutionContext",
]
