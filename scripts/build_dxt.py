#!/usr/bin/env python3
"""Build script for TwinCAT Validator Claude Desktop Extension (.dxt).

Creates a .dxt package from the dxt/ directory for distribution.
"""

import json
import re
import zipfile
from pathlib import Path


def get_project_version(pyproject_path: Path) -> str:
    """Extract project version from pyproject.toml without external deps."""
    text = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    if not match:
        raise ValueError("Could not find [project].version in pyproject.toml")
    return match.group(1)


def validate_manifest(manifest_path: Path, dxt_dir: Path) -> dict:
    """Validate manifest.json structure."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    required_fields = ["name", "version", "description", "author", "mcp"]
    missing = [f for f in required_fields if f not in manifest]

    if missing:
        raise ValueError(f"manifest.json missing required fields: {', '.join(missing)}")

    # Verify MCP command exists
    if "command" not in manifest["mcp"]:
        raise ValueError("manifest.json missing mcp.command")

    # Verify required icon path exists
    icon_path = manifest.get("icon")
    if not icon_path:
        raise ValueError("manifest.json missing icon")
    if not (dxt_dir / icon_path).exists():
        raise ValueError(f"manifest icon not found: {icon_path}")

    return manifest


def normalize_manifest(manifest: dict, project_version: str) -> dict:
    """Synchronize manifest version/pip package pin with project version."""
    result = dict(manifest)
    result["version"] = project_version

    requirements = dict(result.get("requirements", {}))
    pip_package = requirements.get("pip_package", "twincat-validator-mcp")
    package_name = pip_package.split("==")[0]
    requirements["pip_package"] = f"{package_name}=={project_version}"
    result["requirements"] = requirements

    return result


def build_dxt(project_root: Path, output_dir: Path):
    """Build .dxt package."""
    dxt_dir = project_root / "dxt"
    if not dxt_dir.exists():
        raise FileNotFoundError(f"DXT directory not found: {dxt_dir}")

    # Validate and normalize manifest
    manifest_path = dxt_dir / "manifest.json"
    manifest = validate_manifest(manifest_path, dxt_dir)
    project_version = get_project_version(project_root / "pyproject.toml")
    manifest = normalize_manifest(manifest, project_version)

    version = manifest["version"]
    name = manifest["name"].lower().replace(" ", "-")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Output filename
    output_file = output_dir / f"{name}-{version}.dxt"

    print(f"Building {output_file.name}...")

    # Create zip archive
    with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as zipf:
        # Add all files from dxt/ directory
        for file_path in dxt_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(dxt_dir)
                if arcname.as_posix() == "manifest.json":
                    # Write normalized manifest instead of raw checked-in file.
                    zipf.writestr(
                        "manifest.json",
                        json.dumps(manifest, indent=2) + "\n",
                    )
                else:
                    zipf.write(file_path, arcname)
                print(f"  Added: {arcname}")

    file_size = output_file.stat().st_size / 1024  # KB
    print(f"\n[OK] Successfully built: {output_file}")
    print(f"     Size: {file_size:.1f} KB")
    print(f"     Version: {version}")

    return output_file


def main():
    """Build DXT package."""
    project_root = Path(__file__).parent.parent
    output_dir = project_root / "dist"

    try:
        dxt_file = build_dxt(project_root, output_dir)
        print("\nPackage ready for distribution:")
        print(f"   {dxt_file}")
        return 0
    except Exception as e:
        print(f"\n[ERROR] Build failed: {e}")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
