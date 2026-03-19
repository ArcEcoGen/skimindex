"""Unit tests for skimindex.sequences module."""

import pytest
from pathlib import Path

from skimindex.sequences import list_sequence_files, species_list, genome_species_list, SEQUENCE_EXTENSIONS


@pytest.fixture()
def seq_dir(tmp_path):
    """Create a directory with a mix of sequence files."""
    d = tmp_path / "Plants"
    d.mkdir()

    # Uncompressed files
    (d / "Arabidopsis_thaliana-GCA_000001735.1.fasta").touch()
    (d / "Homo_sapiens-GCF_000001405.40.gbff").touch()

    # Compressed files
    (d / "Oryza_sativa-GCA_000004655.2.fasta.gz").touch()
    (d / "Zea_mays-GCA_000005005.6.gbff.gz").touch()

    # Non-sequence file — should be ignored
    (d / "readme.txt").touch()

    return d


@pytest.fixture()
def nested_dir(tmp_path):
    """Create a nested directory structure."""
    root = tmp_path / "Genomes"
    root.mkdir()
    (root / "human.fasta").touch()
    sub = root / "sub"
    sub.mkdir()
    (sub / "mouse.fasta").touch()
    return root


# ---------------------------------------------------------------------------
# Mode tests
# ---------------------------------------------------------------------------

class TestModes:
    def test_relative_mode(self, seq_dir):
        files = list_sequence_files(seq_dir, mode="relative")
        assert all(not f.is_absolute() for f in files)
        names = [f.name for f in files]
        assert "Arabidopsis_thaliana-GCA_000001735.1.fasta" in names

    def test_absolute_mode(self, seq_dir):
        files = list_sequence_files(seq_dir, mode="absolute")
        assert all(f.is_absolute() for f in files)

    def test_prefixed_mode(self, seq_dir):
        files = list_sequence_files(seq_dir, mode="prefixed")
        assert all(str(f).startswith("Plants/") for f in files)

    def test_invalid_mode(self, seq_dir):
        with pytest.raises(ValueError, match="mode must be"):
            list_sequence_files(seq_dir, mode="invalid")


# ---------------------------------------------------------------------------
# Compressed / uncompressed flags
# ---------------------------------------------------------------------------

class TestCompressionFlags:
    def test_compressed_only(self, seq_dir):
        files = list_sequence_files(seq_dir, compressed=True, uncompressed=False)
        assert all(str(f).endswith(".gz") for f in files)
        assert len(files) == 2

    def test_uncompressed_only(self, seq_dir):
        files = list_sequence_files(seq_dir, compressed=False, uncompressed=True)
        assert all(not str(f).endswith(".gz") for f in files)
        assert len(files) == 2

    def test_both(self, seq_dir):
        files = list_sequence_files(seq_dir)
        assert len(files) == 4

    def test_neither(self, seq_dir):
        files = list_sequence_files(seq_dir, compressed=False, uncompressed=False)
        assert files == []


# ---------------------------------------------------------------------------
# Recursive flag
# ---------------------------------------------------------------------------

class TestRecursive:
    def test_non_recursive(self, nested_dir):
        files = list_sequence_files(nested_dir, compressed=False)
        names = [f.name for f in files]
        assert "human.fasta" in names
        assert "mouse.fasta" not in names

    def test_recursive(self, nested_dir):
        files = list_sequence_files(nested_dir, recursive=True, compressed=False)
        names = [f.name for f in files]
        assert "human.fasta" in names
        assert "mouse.fasta" in names


# ---------------------------------------------------------------------------
# Custom extensions
# ---------------------------------------------------------------------------

class TestCustomExtensions:
    def test_custom_ext(self, tmp_path):
        (tmp_path / "data.fa").touch()
        (tmp_path / "data.fasta").touch()
        files = list_sequence_files(tmp_path, extensions=(".fa",), compressed=False)
        names = [f.name for f in files]
        assert "data.fa" in names
        assert "data.fasta" not in names


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestErrors:
    def test_missing_directory(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            list_sequence_files(tmp_path / "nonexistent")


# ---------------------------------------------------------------------------
# Sorting and deduplication
# ---------------------------------------------------------------------------

class TestSorting:
    def test_sorted_output(self, seq_dir):
        files = list_sequence_files(seq_dir)
        names = [f.name for f in files]
        assert names == sorted(names)

    def test_no_duplicates(self, seq_dir):
        files = list_sequence_files(seq_dir)
        assert len(files) == len(set(files))


# ---------------------------------------------------------------------------
# Non-sequence files are excluded
# ---------------------------------------------------------------------------

class TestExclusion:
    def test_txt_excluded(self, seq_dir):
        files = list_sequence_files(seq_dir)
        assert all(f.suffix != ".txt" for f in files)

    def test_gz_txt_excluded(self, tmp_path):
        (tmp_path / "notes.txt.gz").touch()
        (tmp_path / "data.fasta.gz").touch()
        files = list_sequence_files(tmp_path)
        names = [f.name for f in files]
        assert "notes.txt.gz" not in names
        assert "data.fasta.gz" in names


# ---------------------------------------------------------------------------
# species_list tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def genome_dir(tmp_path):
    """Simulate a genome dataset: genomes_15x/species/{Species}/{individual}/"""
    root = tmp_path / "genomes_15x"
    species_root = root / "species"
    for sp in ("Betula_nana", "Betula_pubescens", "Salix_alba"):
        ind = species_root / sp / "IND-001"
        ind.mkdir(parents=True)
        (ind / "sample_R1.fastq.gz").touch()
    # Empty species directory (no individuals yet)
    (species_root / "Potamogeton").mkdir()
    # Non-species subdirectory — should not appear
    (root / "hybrid" / "IND-002").mkdir(parents=True)
    return root


class TestSpeciesList:
    def test_returns_all_species(self, genome_dir):
        result = species_list(genome_dir)
        assert set(result.keys()) == {"Betula nana", "Betula pubescens", "Salix alba", "Potamogeton"}

    def test_sorted_keys(self, genome_dir):
        result = species_list(genome_dir)
        assert list(result.keys()) == sorted(result.keys())

    def test_relative_mode(self, genome_dir):
        result = species_list(genome_dir, mode="relative")
        assert result["Betula nana"] == Path("species/Betula_nana")

    def test_absolute_mode(self, genome_dir):
        result = species_list(genome_dir, mode="absolute")
        assert result["Betula nana"].is_absolute()
        assert result["Betula nana"].name == "Betula_nana"

    def test_prefixed_mode(self, genome_dir):
        result = species_list(genome_dir, mode="prefixed")
        assert result["Betula nana"] == Path("genomes_15x/species/Betula_nana")

    def test_hybrid_dir_excluded(self, genome_dir):
        result = species_list(genome_dir)
        assert "hybrid" not in result

    def test_missing_species_dir_returns_empty(self, tmp_path):
        root = tmp_path / "genomes_15x"
        root.mkdir()
        result = species_list(root)
        assert result == {}

    def test_missing_directory_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            species_list(tmp_path / "nonexistent")

    def test_invalid_mode_raises(self, genome_dir):
        with pytest.raises(ValueError):
            species_list(genome_dir, mode="bad")
