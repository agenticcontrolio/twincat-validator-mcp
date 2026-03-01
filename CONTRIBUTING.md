# Contributing to TwinCAT Validator MCP Server

Thank you for your interest in contributing to the TwinCAT Validator MCP Server! This document provides guidelines for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Coding Standards](#coding-standards)
- [Adding New Validation Checks](#adding-new-validation-checks)
- [Adding New Auto-fixes](#adding-new-auto-fixes)

## Code of Conduct

This project adheres to a code of conduct based on respect, professionalism, and inclusivity. By participating, you are expected to uphold this code.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/twincat-validator-mcp.git`
3. Add upstream remote: `git remote add upstream https://github.com/agenticcontrolio/twincat-validator-mcp.git`

## Development Setup

### Prerequisites

- Python 3.11 or higher
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/agenticcontrolio/twincat-validator-mcp.git
cd twincat-validator-mcp

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode with dev dependencies
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_smoke_twincat.py -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html
```

## Project Structure

```
twincat_validator/               # Main package
├── server.py                    # MCP tools, resources, and prompts (FastMCP)
├── prompts.py                   # 8 MCP prompt workflow templates
├── models.py                    # Data models (ValidationIssue, CheckResult, etc.)
├── engines.py                   # ValidationEngine and FixEngine orchestrators
├── file_handler.py              # TwinCATFile value object (lazy load, save)
├── config_loader.py             # ValidationConfig: loads JSON config at startup
├── snippet_extractor.py         # Phase 3 code-snippet extraction utilities
├── utils.py                     # POU subtype detection helpers
├── exceptions.py                # Custom exceptions (CheckNotFoundError, etc.)
├── config/                      # JSON configuration files
│   ├── validation_rules.json    # 34 check definitions + OOP policy defaults
│   ├── fix_capabilities.json    # 9 fix definitions with deterministic order
│   ├── naming_conventions.json  # TwinCAT naming patterns (FB_, I_, E_, etc.)
│   ├── knowledge_base.json      # LLM-friendly explanations for all checks/fixes
│   └── generation_contract.json # Canonical skeleton contracts per file type
├── validators/                  # 34 modular validation checks
│   ├── base.py                  # BaseCheck ABC + CheckRegistry
│   ├── xml_checks.py
│   ├── guid_checks.py
│   ├── style_checks.py
│   ├── structure_checks.py
│   ├── naming_checks.py
│   └── oop_checks.py            # 21 OOP checks (Phases 5A–5C)
└── fixers/                      # 9 modular auto-fix operations
    ├── base.py                  # BaseFix ABC + FixRegistry
    ├── simple_fixes.py
    ├── structural_fixes.py
    └── complex_fixes.py
server.py                        # Root shim (backward-compat re-export only)
tests/                           # Test suite (593 tests)
├── conftest.py
├── golden/                      # Golden-file regression baselines
├── fixtures/                    # Sample TwinCAT files for testing
├── unit/test_checks/            # Per-check unit tests
└── test_*.py                    # Integration and smoke tests
pyproject.toml                   # Package configuration
tox.ini                          # Test automation (py311, py312, lint, type)
```

## Making Changes

### Branch Naming

- Feature: `feature/description-of-feature`
- Bugfix: `bugfix/description-of-bug`
- Documentation: `docs/description-of-change`
- Refactor: `refactor/description-of-refactor`

### Commit Messages

Follow conventional commits format:

```
type(scope): brief description

Longer explanation if needed.

Fixes #123
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Examples:

```
feat(validation): add support for .TcNLN file validation
fix(guid): handle malformed GUID edge case
docs(readme): add installation troubleshooting section
test(autofix): add test for tab replacement
```

## Testing

### Test Requirements

- All new features must include tests
- Bug fixes should include regression tests
- Tests should be clear and well-documented
- Aim for high test coverage (>80%)

### Test Structure

```python
def test_feature_name():
    """Test that feature works correctly under normal conditions."""
    # Arrange
    input_data = create_test_data()

    # Act
    result = function_under_test(input_data)

    # Assert
    assert result == expected_output
```

### Running Specific Tests

```bash
# Run single test
pytest tests/test_smoke_twincat.py::test_validate_with_sample_file -v

# Run tests matching pattern
pytest -k "guid" -v

# Run with output
pytest -v -s
```

## Submitting Changes

1. **Ensure all tests pass**: `pytest tests/ -v`
2. **Format code**: `black . --line-length=100`
3. **Lint code**: `ruff check .`
4. **Type check** (if applicable): `mypy twincat_validator/server.py --ignore-missing-imports --follow-imports=skip`
5. **Update CHANGELOG.md** with your changes
6. **Push to your fork**
7. **Create Pull Request** with clear description

### Pull Request Template

```markdown
## Description

Brief description of the changes

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing

- [ ] All tests pass
- [ ] New tests added
- [ ] Manual testing completed

## Checklist

- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex logic
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
```

## Coding Standards

### Python Style

- Follow PEP 8
- Use type hints where appropriate
- Line length: 100 characters (Black default)
- Use descriptive variable names
- Add docstrings to all functions/classes

### Documentation

- All public functions must have docstrings
- Use Google-style docstrings:

```python
def validate_file(file_path: str, validation_level: str = "all") -> str:
    """
    Validate a single TwinCAT file.

    Args:
        file_path: Absolute path to TwinCAT file
        validation_level: Validation strictness level ("all", "critical", "style")

    Returns:
        JSON string with validation results

    Raises:
        FileNotFoundError: If file does not exist
        ValueError: If validation_level is invalid

    Example:
        >>> result = validate_file("/path/to/file.TcPOU", "all")
        >>> data = json.loads(result)
    """
```

### Code Organization

- Keep functions focused and single-purpose
- Use private methods (prefix with `_`) for internal helpers
- Separate concerns (validation logic vs. MCP tool logic)
- Keep files under 1500 lines

## Adding New Validation Checks

Checks use a registry-based pattern. No central dispatch method needs to be edited.

### 1. Add to `config/validation_rules.json`

```json
{
  "id": "new_check_id",
  "name": "Human Readable Name",
  "description": "What this check validates",
  "severity": "warning",
  "auto_fixable": false,
  "category": "structure"
}
```

### 2. Implement a check class in the appropriate `validators/*.py` file

```python
from twincat_validator.validators.base import BaseCheck, CheckRegistry
from twincat_validator.models import ValidationIssue
from twincat_validator.file_handler import TwinCATFile

@CheckRegistry.register
class NewFeatureCheck(BaseCheck):
    check_id = "new_check_id"

    def should_skip(self, file: TwinCATFile) -> bool:
        return file.suffix != ".TcPOU"  # or False to run on all types

    def run(self, file: TwinCATFile) -> list[ValidationIssue]:
        issues = []
        # Implement validation logic
        if issue_detected:
            issues.append(ValidationIssue(
                severity="warning",
                category="Structure",
                message="Issue description",
                line_num=line_number,
                fix_available=False,
                fix_suggestion="How to fix",
            ))
        return issues
```

The `@CheckRegistry.register` decorator auto-registers the check — no central file to edit.

### 3. Add knowledge base entry in `config/knowledge_base.json` (optional but recommended)

Add an entry under `"checks"` keyed by the `check_id` with `explanation`, `why_it_matters`,
`correct_examples`, `common_mistakes`, and `fix_suggestion` fields.

### 4. Add Tests

```python
def test_new_check_detects_issue():
    """Test that new_check_id fires on a file with the violation."""
    from twincat_validator.validators.your_module import NewFeatureCheck
    file = TwinCATFile.from_path(Path("tests/fixtures/your_fixture.TcPOU"))
    issues = NewFeatureCheck().run(file)
    assert any("Issue description" in i.message for i in issues)

def test_new_check_passes_clean_file():
    """Test that new_check_id does not fire on a clean file."""
    file = TwinCATFile.from_path(Path("tests/fixtures/clean_fixture.TcPOU"))
    assert NewFeatureCheck().run(file) == []
```

## Adding New Auto-fixes

Fixes use the same registry-based pattern. No central dispatch method needs to be edited.

### 1. Add to `config/fix_capabilities.json`

```json
{
  "id": "new_fix_id",
  "name": "Human Readable Name",
  "description": "What this fix does",
  "complexity": "simple",
  "safe": true,
  "risk_level": "none",
  "order": 10
}
```

The `order` field controls deterministic fix execution sequence (lower = earlier).

### 2. Implement a fix class in the appropriate `fixers/*.py` file

```python
from twincat_validator.fixers.base import BaseFix, FixRegistry
from twincat_validator.file_handler import TwinCATFile

@FixRegistry.register
class NewFix(BaseFix):
    fix_id = "new_fix_id"

    def apply(self, file: TwinCATFile) -> bool:
        original = file.content
        new_content = original.replace(...)  # implement fix
        if new_content != original:
            file.content = new_content
            return True
        return False
```

The `@FixRegistry.register` decorator auto-registers the fix — no central file to edit.

### 3. Add Tests

```python
def test_new_fix_applies():
    """Test that new_fix_id changes content when violation present."""
    from twincat_validator.fixers.your_module import NewFix
    file = TwinCATFile.from_path(Path("tests/fixtures/unfixed_fixture.TcPOU"))
    changed = NewFix().apply(file)
    assert changed is True

def test_new_fix_is_idempotent():
    """Test that running the fix twice produces no second change."""
    file = TwinCATFile.from_path(Path("tests/fixtures/unfixed_fixture.TcPOU"))
    NewFix().apply(file)
    assert NewFix().apply(file) is False
```

## Release Process

Releases are managed by project maintainers:

1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Create git tag: `git tag -a v1.0.1 -m "Release v1.0.1"`
4. Push tag: `git push origin v1.0.1`
5. Build and publish to PyPI

## Questions?

- Open an issue for bugs or feature requests
- Start a discussion for questions or ideas
- Check existing issues before creating new ones

Thank you for contributing! 🚀
