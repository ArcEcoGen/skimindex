"""
Unit tests for skimindex.sources.genbank.

Tests are derived from the specs in docs/directory-structure.md.
The filesystem is simulated with tmp_path + monkeypatch.
"""

import pytest
from pathlib import Path

import skimindex.sources.genbank as gb


@pytest.fixture
def genbank_root(tmp_path, monkeypatch):
    """Patch _genbank_root() to return a temporary directory."""
    monkeypatch.setattr(gb, "_genbank_root", lambda: tmp_path)
    return tmp_path


def make_release(root: Path, release: str) -> Path:
    """Create a minimal Release_{release} directory structure."""
    d = root / f"Release_{release}"
    (d / "fasta").mkdir(parents=True)
    (d / "taxonomy").mkdir(parents=True)
    return d


# ---------------------------------------------------------------------------
# available_releases
# ---------------------------------------------------------------------------

class TestAvailableReleases:

    def test_empty_root(self, genbank_root):
        assert gb.available_releases() == []

    def test_single_release(self, genbank_root):
        make_release(genbank_root, "270.0")
        assert gb.available_releases() == ["270.0"]

    def test_multiple_releases_sorted(self, genbank_root):
        for r in ("269.0", "271.0", "270.0"):
            make_release(genbank_root, r)
        assert gb.available_releases() == ["269.0", "270.0", "271.0"]

    def test_non_release_dirs_ignored(self, genbank_root):
        make_release(genbank_root, "270.0")
        (genbank_root / "taxonomy").mkdir()
        (genbank_root / "fasta").mkdir()
        assert gb.available_releases() == ["270.0"]

    def test_files_ignored(self, genbank_root):
        make_release(genbank_root, "270.0")
        (genbank_root / "Release_271.0").write_text("not a dir")
        assert gb.available_releases() == ["270.0"]

    def test_returns_release_name_not_dirname(self, genbank_root):
        make_release(genbank_root, "270.0")
        releases = gb.available_releases()
        assert releases == ["270.0"]
        assert not any(r.startswith("Release_") for r in releases)

    def test_decimal_sorting(self, genbank_root):
        # 9.0 < 10.0 numerically but "10.0" > "9.0" lexicographically
        for r in ("10.0", "9.0", "9.5"):
            make_release(genbank_root, r)
        assert gb.available_releases() == ["9.0", "9.5", "10.0"]


# ---------------------------------------------------------------------------
# latest_release
# ---------------------------------------------------------------------------

class TestLatestRelease:

    def test_single_release(self, genbank_root):
        make_release(genbank_root, "270.0")
        assert gb.latest_release() == "270.0"

    def test_returns_highest(self, genbank_root):
        for r in ("268.0", "269.0", "270.0"):
            make_release(genbank_root, r)
        assert gb.latest_release() == "270.0"

    def test_no_releases_raises(self, genbank_root):
        with pytest.raises(RuntimeError):
            gb.latest_release()


# ---------------------------------------------------------------------------
# release_dir
# ---------------------------------------------------------------------------

class TestReleaseDir:

    def test_constructs_path(self, genbank_root):
        assert gb.release_dir("270.0") == genbank_root / "Release_270.0"

    def test_different_release(self, genbank_root):
        assert gb.release_dir("268.0") == genbank_root / "Release_268.0"

    def test_returns_path(self, genbank_root):
        assert isinstance(gb.release_dir("270.0"), Path)


# ---------------------------------------------------------------------------
# taxonomy
# ---------------------------------------------------------------------------

class TestTaxonomy:

    def test_path_structure(self, genbank_root):
        expected = genbank_root / "Release_270.0" / "taxonomy" / "ncbi_taxonomy.tgz"
        assert gb.taxonomy("270.0") == expected

    def test_different_release(self, genbank_root):
        expected = genbank_root / "Release_268.0" / "taxonomy" / "ncbi_taxonomy.tgz"
        assert gb.taxonomy("268.0") == expected


# ---------------------------------------------------------------------------
# division_dir
# ---------------------------------------------------------------------------

class TestDivisionDir:

    def test_bct_division(self, genbank_root):
        expected = genbank_root / "Release_270.0" / "fasta" / "bct"
        assert gb.division_dir("270.0", "bct") == expected

    def test_pln_division(self, genbank_root):
        expected = genbank_root / "Release_270.0" / "fasta" / "pln"
        assert gb.division_dir("270.0", "pln") == expected

    def test_different_release(self, genbank_root):
        expected = genbank_root / "Release_268.0" / "fasta" / "bct"
        assert gb.division_dir("268.0", "bct") == expected

    def test_returns_path(self, genbank_root):
        assert isinstance(gb.division_dir("270.0", "bct"), Path)


# ---------------------------------------------------------------------------
# Integration: latest_release + release_dir + taxonomy + division_dir
# ---------------------------------------------------------------------------

class TestIntegration:

    def test_full_path_resolution(self, genbank_root):
        make_release(genbank_root, "270.0")
        rel = gb.latest_release()
        assert gb.release_dir(rel) == genbank_root / "Release_270.0"
        assert gb.taxonomy(rel) == genbank_root / "Release_270.0" / "taxonomy" / "ncbi_taxonomy.tgz"
        assert gb.division_dir(rel, "bct") == genbank_root / "Release_270.0" / "fasta" / "bct"
