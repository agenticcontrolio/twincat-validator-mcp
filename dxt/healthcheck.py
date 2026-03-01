#!/usr/bin/env python3
"""Health check script for TwinCAT Validator MCP extension.

This script verifies local prerequisites and that the stdio MCP server command
can start. It is intended for manual troubleshooting and CI checks.
"""

import subprocess
import sys
from pathlib import Path


def check_python_version():
    """Verify Python version is 3.11+."""
    version = sys.version_info
    if version < (3, 11):
        return False, f"Python {version.major}.{version.minor} found, requires 3.11+"
    return True, f"Python {version.major}.{version.minor}.{version.micro}"


def check_package_installed():
    """Verify twincat-validator-mcp package is installed."""
    try:
        import twincat_validator

        version = twincat_validator.__version__
        return True, f"Package installed: v{version}"
    except ImportError:
        return False, "Package not installed. Run: pip install twincat-validator-mcp"


def check_command_exists():
    """Verify twincat-validator-mcp command is available and startable.

    For stdio servers, a healthy process typically stays running waiting for
    input. A timeout or running process is considered success.
    """
    proc = None
    try:
        proc = subprocess.Popen(
            ["twincat-validator-mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            proc.wait(timeout=1.5)
            stderr = (proc.stderr.read() if proc.stderr else "")[:300].strip()
            if proc.returncode == 0:
                return True, "Command exits cleanly"
            return False, f"Command exited early with code {proc.returncode}: {stderr}"
        except subprocess.TimeoutExpired:
            return True, "Command started (running stdio server)"
    except FileNotFoundError:
        return False, "Command not found in PATH"
    except Exception as e:
        return False, f"Error: {e}"
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()


def check_config_files():
    """Verify config files exist in package."""
    try:
        import twincat_validator

        config_dir = Path(twincat_validator.__file__).parent / "config"

        required_files = [
            "validation_rules.json",
            "fix_capabilities.json",
            "naming_conventions.json",
            "knowledge_base.json",
        ]

        missing = [f for f in required_files if not (config_dir / f).exists()]

        if missing:
            return False, f"Missing config files: {', '.join(missing)}"
        return True, f"All {len(required_files)} config files present"
    except Exception as e:
        return False, f"Error checking config: {e}"


def main():
    """Run all health checks."""
    checks = [
        ("Python Version", check_python_version),
        ("Package Installation", check_package_installed),
        ("Command Availability", check_command_exists),
        ("Config Files", check_config_files),
    ]

    results = {}
    all_passed = True

    print("TwinCAT Validator MCP - Health Check")
    print("=" * 50)

    for name, check_func in checks:
        passed, message = check_func()
        results[name] = {"passed": passed, "message": message}

        status = "✅" if passed else "❌"
        print(f"{status} {name}: {message}")

        if not passed:
            all_passed = False

    print("=" * 50)

    if all_passed:
        print("✅ All checks passed! Extension is ready to use.")
        return 0
    else:
        print("❌ Some checks failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
