"""Phase 5A.3: Golden-file byte-stability tests."""

import hashlib
import json
from pathlib import Path

import pytest

from server import autofix_file


EXPECTED_GOLDEN_KEYS = {
    "tabs_and_bad_indent",
    "mixed_case_guids",
    "valid_fb",
    "valid_function",
    "valid_program",
    "valid_struct",
    "valid_gvl",
    "valid_interface",
}


class TestGoldenFileStability:
    """Test that autofix produces byte-identical outputs across runs."""

    @pytest.fixture
    def golden_dir(self):
        """Directory for golden output files."""
        return Path(__file__).parent / "golden"

    def _compute_hash(self, content: str) -> str:
        """Compute SHA256 hash of content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _get_golden_path(self, fixture_name: str, golden_dir: Path) -> Path:
        """Get path to golden file for a fixture."""
        return golden_dir / f"{fixture_name}.golden"

    def _run_mcp_autofix_and_get_content(self, fixture_path: Path, tmp_path: Path) -> str:
        """Run MCP autofix tool on a temp copy and return resulting file content."""
        temp_file = tmp_path / fixture_path.name
        temp_file.write_text(fixture_path.read_text(encoding="utf-8"), encoding="utf-8")

        result = json.loads(autofix_file(str(temp_file), create_backup=False, profile="llm_strict"))
        assert result["success"] is True, f"autofix_file failed for {fixture_path.name}: {result}"

        return temp_file.read_text(encoding="utf-8")

    def _assert_matches_golden(self, fixture_name: str, fixed_content: str, golden_dir: Path):
        golden_path = self._get_golden_path(fixture_name, golden_dir)
        assert golden_path.exists(), (
            f"Missing golden file for '{fixture_name}': {golden_path}. "
            "Golden baselines must be committed and never auto-generated in CI."
        )

        golden_content = golden_path.read_text(encoding="utf-8")
        assert fixed_content == golden_content, (
            f"Output changed for {fixture_name}!\n"
            f"Expected hash: {self._compute_hash(golden_content)}\n"
            f"Actual hash: {self._compute_hash(fixed_content)}"
        )

    def test_tabs_and_bad_indent_golden(self, tabs_and_bad_indent_file, tmp_path, golden_dir):
        fixed_content = self._run_mcp_autofix_and_get_content(tabs_and_bad_indent_file, tmp_path)
        self._assert_matches_golden("tabs_and_bad_indent", fixed_content, golden_dir)

    def test_mixed_case_guids_golden(self, mixed_case_guids_file, tmp_path, golden_dir):
        fixed_content = self._run_mcp_autofix_and_get_content(mixed_case_guids_file, tmp_path)
        self._assert_matches_golden("mixed_case_guids", fixed_content, golden_dir)

    def test_valid_fb_golden(self, valid_tcpou, tmp_path, golden_dir):
        fixed_content = self._run_mcp_autofix_and_get_content(valid_tcpou, tmp_path)
        self._assert_matches_golden("valid_fb", fixed_content, golden_dir)

    def test_valid_function_golden(self, valid_function, tmp_path, golden_dir):
        fixed_content = self._run_mcp_autofix_and_get_content(valid_function, tmp_path)
        self._assert_matches_golden("valid_function", fixed_content, golden_dir)

    def test_valid_program_golden(self, valid_program, tmp_path, golden_dir):
        fixed_content = self._run_mcp_autofix_and_get_content(valid_program, tmp_path)
        self._assert_matches_golden("valid_program", fixed_content, golden_dir)

    def test_valid_dut_golden(self, valid_tcdut, tmp_path, golden_dir):
        fixed_content = self._run_mcp_autofix_and_get_content(valid_tcdut, tmp_path)
        self._assert_matches_golden("valid_struct", fixed_content, golden_dir)

    def test_valid_gvl_golden(self, valid_tcgvl, tmp_path, golden_dir):
        fixed_content = self._run_mcp_autofix_and_get_content(valid_tcgvl, tmp_path)
        self._assert_matches_golden("valid_gvl", fixed_content, golden_dir)

    def test_valid_interface_golden(self, valid_tcio, tmp_path, golden_dir):
        fixed_content = self._run_mcp_autofix_and_get_content(valid_tcio, tmp_path)
        self._assert_matches_golden("valid_interface", fixed_content, golden_dir)


class TestHashStability:
    """Test that golden hashes are complete and stable."""

    @pytest.fixture
    def golden_dir(self):
        return Path(__file__).parent / "golden"

    def _load_registry(self, golden_dir: Path) -> dict[str, str]:
        registry_path = golden_dir / "hashes.json"
        assert registry_path.exists(), f"Missing hash registry: {registry_path}"
        with open(registry_path, encoding="utf-8") as f:
            return json.load(f)

    def test_hash_registry_has_exact_expected_keys(self, golden_dir):
        registry = self._load_registry(golden_dir)
        actual_keys = set(registry.keys())
        assert actual_keys == EXPECTED_GOLDEN_KEYS, (
            f"Hash registry keys mismatch.\n"
            f"Expected: {sorted(EXPECTED_GOLDEN_KEYS)}\n"
            f"Got: {sorted(actual_keys)}"
        )

        for key, value in registry.items():
            assert isinstance(value, str), f"Hash for {key} must be a string"
            assert len(value) == 64, f"Hash for {key} must be SHA256 hex (64 chars)"
            assert all(
                ch in "0123456789abcdef" for ch in value
            ), f"Hash for {key} contains non-hex characters: {value}"

    def test_hash_registry_matches_golden_files(self, golden_dir):
        registry = self._load_registry(golden_dir)
        for fixture_name in EXPECTED_GOLDEN_KEYS:
            golden_path = golden_dir / f"{fixture_name}.golden"
            assert golden_path.exists(), f"Missing golden file: {golden_path}"
            content = golden_path.read_text(encoding="utf-8")
            actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            assert registry[fixture_name] == actual_hash, (
                f"Hash mismatch for {fixture_name}. "
                f"Registry: {registry[fixture_name]}, Actual: {actual_hash}"
            )
