"""Custom exceptions for the TwinCAT Validator package."""


class TwinCATValidatorError(Exception):
    """Base exception for all validator errors."""


class FileValidationError(TwinCATValidatorError):
    """Raised when file validation fails at the infrastructure level."""


class UnsupportedFileTypeError(FileValidationError):
    """Raised when file type is not .TcPOU, .TcIO, .TcDUT, or .TcGVL."""


class ConfigurationError(TwinCATValidatorError):
    """Raised when configuration is invalid or missing."""


class FixApplicationError(TwinCATValidatorError):
    """Raised when a fix cannot be applied."""


class CheckNotFoundError(TwinCATValidatorError):
    """Raised when a check ID is not recognized."""


class FixNotFoundError(TwinCATValidatorError):
    """Raised when a fix ID is not recognized."""


class PolicyResolutionError(TwinCATValidatorError):
    """Raised when effective policy or target path resolution fails."""


class PolicyEnforcementError(TwinCATValidatorError):
    """Raised when policy enforcement mode or policy constraints are invalid."""
