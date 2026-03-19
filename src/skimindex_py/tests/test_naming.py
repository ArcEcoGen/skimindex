"""
Unit tests for skimindex.naming.

Tests are derived from the specs in docs/directory-structure.md,
not from the implementation.
"""

import pytest
from pathlib import Path

from skimindex.naming import (
    canonical_species,
    genome_filename,
    genome_subdir,
    output_subdir_for,
    parse_division_path,
    parse_genome_path,
)


# ---------------------------------------------------------------------------
# canonical_species
# ---------------------------------------------------------------------------

class TestCanonicalSpecies:
    """Rules from directory-structure.md § File naming convention:
    1. Spaces → underscores
    2. Non-alphanumeric / non _ - . removed
    3. Rank markers preserved: subsp., var., x
    """

    def test_simple_species(self):
        assert canonical_species("Homo sapiens") == "Homo_sapiens"

    def test_genus_species(self):
        assert canonical_species("Arabidopsis thaliana") == "Arabidopsis_thaliana"

    def test_subspecies(self):
        assert canonical_species("Brassica rapa subsp. chinensis") == "Brassica_rapa_subsp._chinensis"

    def test_variety(self):
        assert canonical_species("Oryza sativa var. japonica") == "Oryza_sativa_var._japonica"

    def test_hybrid_species_x_species(self):
        assert canonical_species("Mentha aquatica x spicata") == "Mentha_aquatica_x_spicata"

    def test_hybrid_genus_level(self):
        assert canonical_species("Mentha x piperita") == "Mentha_x_piperita"

    def test_unicode_multiplication_sign_removed(self):
        # × (U+00D7) is not alphanumeric/_/- → removed
        assert canonical_species("Mentha × piperita") == "Mentha_piperita"

    def test_already_canonical(self):
        assert canonical_species("Homo_sapiens") == "Homo_sapiens"

    def test_parentheses_removed(self):
        assert canonical_species("Homo sapiens (human)") == "Homo_sapiens_human"

    def test_leading_trailing_stripped(self):
        assert canonical_species("_Homo sapiens_") == "Homo_sapiens"


# ---------------------------------------------------------------------------
# genome_filename
# ---------------------------------------------------------------------------

class TestGenomeFilename:
    """Level-0 canonical filename: {species}--{accession}.{ext}[.gz]"""

    def test_compressed(self):
        assert genome_filename("Homo_sapiens", "GCF_000001405.40", "gbff") \
            == "Homo_sapiens--GCF_000001405.40.gbff.gz"

    def test_uncompressed(self):
        assert genome_filename("Arabidopsis_thaliana", "GCA_946409825.1", "fasta",
                               compressed=False) \
            == "Arabidopsis_thaliana--GCA_946409825.1.fasta"

    def test_subspecies_name(self):
        assert genome_filename("Brassica_rapa_subsp._chinensis", "GCA_052186795.1", "gbff") \
            == "Brassica_rapa_subsp._chinensis--GCA_052186795.1.gbff.gz"

    def test_hybrid_name(self):
        assert genome_filename("Mentha_x_piperita", "GCA_123456789.1", "gbff") \
            == "Mentha_x_piperita--GCA_123456789.1.gbff.gz"

    def test_separator_is_double_dash(self):
        name = genome_filename("Homo_sapiens", "GCF_000001405.40", "gbff")
        assert "--" in name
        parts = name.split("--")
        assert parts[0] == "Homo_sapiens"
        assert parts[1].startswith("GCF_000001405.40")


# ---------------------------------------------------------------------------
# genome_subdir
# ---------------------------------------------------------------------------

class TestGenomeSubdir:
    """processed_data relative path: Species_name/accession"""

    def test_species_accession(self):
        assert genome_subdir("Homo_sapiens", "GCF_000001405.40") \
            == Path("Homo_sapiens/GCF_000001405.40")

    def test_default_accession(self):
        # level-0 source → accession directory is "default"
        assert genome_subdir("Homo_sapiens", "default") \
            == Path("Homo_sapiens/default")

    def test_returns_path(self):
        result = genome_subdir("Arabidopsis_thaliana", "GCA_946409825.1")
        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# parse_genome_path — level 0
# ---------------------------------------------------------------------------

class TestParseGenomePathLevel0:
    """Level-0: {Species_name}--{accession}.{ext}[.gz]
    Accession is always after the LAST '--'.
    """

    def test_gbff_gz(self):
        p = Path("Homo_sapiens--GCF_000001405.40.gbff.gz")
        assert parse_genome_path(p) == ("Homo_sapiens", "GCF_000001405.40", "gbff", True)

    def test_fasta_gz(self):
        p = Path("Arabidopsis_thaliana--GCA_946409825.1.fasta.gz")
        assert parse_genome_path(p) == ("Arabidopsis_thaliana", "GCA_946409825.1", "fasta", True)

    def test_uncompressed(self):
        p = Path("Arabidopsis_thaliana--GCA_946409825.1.fasta")
        assert parse_genome_path(p) == ("Arabidopsis_thaliana", "GCA_946409825.1", "fasta", False)

    def test_subspecies(self):
        p = Path("Brassica_rapa_subsp._chinensis--GCA_052186795.1.gbff.gz")
        assert parse_genome_path(p) == (
            "Brassica_rapa_subsp._chinensis", "GCA_052186795.1", "gbff", True
        )

    def test_hybrid(self):
        p = Path("Mentha_x_piperita--GCA_123456789.1.gbff.gz")
        assert parse_genome_path(p) == ("Mentha_x_piperita", "GCA_123456789.1", "gbff", True)

    def test_accession_is_after_last_double_dash(self):
        # if somehow species contained '--' (degenerate), accession is after last '--'
        p = Path("Genus_sp--extra--GCA_000001.1.gbff.gz")
        _, accession, _, _ = parse_genome_path(p)
        assert accession == "GCA_000001.1"

    def test_no_separator_raises(self):
        with pytest.raises(ValueError, match="--"):
            parse_genome_path(Path("Homo_sapiens_GCF_000001405.40.gbff.gz"))

    def test_unknown_extension_raises(self):
        with pytest.raises(ValueError):
            parse_genome_path(Path("Homo_sapiens--GCF_000001405.40.txt.gz"))


# ---------------------------------------------------------------------------
# parse_genome_path — level 1
# ---------------------------------------------------------------------------

class TestParseGenomePathLevel1:
    """Level-1: {Species_name}/{accession}.{ext}[.gz]"""

    def test_basic(self):
        p = Path("Homo_sapiens/GCF_000001405.40.gbff.gz")
        assert parse_genome_path(p) == ("Homo_sapiens", "GCF_000001405.40", "gbff", True)

    def test_second_accession(self):
        p = Path("Homo_sapiens/GCF_000001405.41.gbff.gz")
        assert parse_genome_path(p) == ("Homo_sapiens", "GCF_000001405.41", "gbff", True)

    def test_uncompressed(self):
        p = Path("Homo_sapiens/GCF_000001405.40.fasta")
        assert parse_genome_path(p) == ("Homo_sapiens", "GCF_000001405.40", "fasta", False)

    def test_subspecies_dir(self):
        p = Path("Brassica_rapa_subsp._chinensis/GCA_052186795.1.gbff.gz")
        assert parse_genome_path(p) == (
            "Brassica_rapa_subsp._chinensis", "GCA_052186795.1", "gbff", True
        )


# ---------------------------------------------------------------------------
# parse_genome_path — level 2
# ---------------------------------------------------------------------------

class TestParseGenomePathLevel2:
    """Level-2: {Species_name}/{accession}/*.<ext>[.gz]
    Accession comes from the directory, not the filename.
    """

    def test_basic(self):
        p = Path("Homo_sapiens/GCF_000001405.40/sequence.gbff.gz")
        assert parse_genome_path(p) == ("Homo_sapiens", "GCF_000001405.40", "gbff", True)

    def test_different_filename(self):
        p = Path("Homo_sapiens/GCF_000001405.40/chr1.fasta.gz")
        assert parse_genome_path(p) == ("Homo_sapiens", "GCF_000001405.40", "fasta", True)

    def test_second_accession(self):
        p = Path("Homo_sapiens/GCF_000001405.41/sequence.gbff.gz")
        assert parse_genome_path(p) == ("Homo_sapiens", "GCF_000001405.41", "gbff", True)

    def test_uncompressed(self):
        p = Path("Homo_sapiens/GCF_000001405.40/sequence.fasta")
        assert parse_genome_path(p) == ("Homo_sapiens", "GCF_000001405.40", "fasta", False)


# ---------------------------------------------------------------------------
# output_subdir_for
# ---------------------------------------------------------------------------

class TestOutputSubdirFor:
    """processed_data relative subdir from any source level.

    Level 0 → Species_name/accession
    Level 1 → Species_name/accession
    Level 2 → Species_name/accession
    """

    def test_level0_uses_accession(self):
        p = Path("Homo_sapiens--GCF_000001405.40.gbff.gz")
        assert output_subdir_for(p) == Path("Homo_sapiens/GCF_000001405.40")

    def test_level1_uses_accession(self):
        p = Path("Homo_sapiens/GCF_000001405.40.gbff.gz")
        assert output_subdir_for(p) == Path("Homo_sapiens/GCF_000001405.40")

    def test_level2_uses_accession(self):
        p = Path("Homo_sapiens/GCF_000001405.40/sequence.gbff.gz")
        assert output_subdir_for(p) == Path("Homo_sapiens/GCF_000001405.40")

    def test_level1_and_level2_same_result(self):
        l1 = Path("Homo_sapiens/GCF_000001405.40.gbff.gz")
        l2 = Path("Homo_sapiens/GCF_000001405.40/sequence.gbff.gz")
        assert output_subdir_for(l1) == output_subdir_for(l2)


# ---------------------------------------------------------------------------
# parse_division_path
# ---------------------------------------------------------------------------

class TestParseDivisionPath:
    """Non-species-organised GenBank: Release_{N}/fasta/{division}/filename"""

    def test_bct_division(self):
        p = Path("Release_270/fasta/bct/gbbct1.fasta.gz")
        assert parse_division_path(p) == ("bct", "gbbct1.fasta.gz", "fasta", True)

    def test_pln_division(self):
        p = Path("Release_270/fasta/pln/gbpln1.fasta.gz")
        assert parse_division_path(p) == ("pln", "gbpln1.fasta.gz", "fasta", True)

    def test_different_release(self):
        p = Path("Release_261/fasta/bct/gbbct1.fasta.gz")
        division, _, _, _ = parse_division_path(p)
        assert division == "bct"

    def test_uncompressed(self):
        p = Path("Release_270/fasta/bct/gbbct1.fasta")
        assert parse_division_path(p) == ("bct", "gbbct1.fasta", "fasta", False)

    def test_wrong_structure_raises(self):
        with pytest.raises(ValueError):
            parse_division_path(Path("fasta/bct/gbbct1.fasta.gz"))

    def test_missing_fasta_level_raises(self):
        with pytest.raises(ValueError):
            parse_division_path(Path("Release_270/bct/gbbct1.fasta.gz"))


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip:
    """parse → build → parse must be identity."""

    def test_level0_roundtrip(self):
        original = "Arabidopsis_thaliana--GCA_946409825.1.gbff.gz"
        species, accession, ext, compressed = parse_genome_path(Path(original))
        rebuilt = genome_filename(species, accession, ext, compressed)
        assert rebuilt == original

    def test_subdir_roundtrip(self):
        species, accession = "Homo_sapiens", "GCF_000001405.40"
        subdir = genome_subdir(species, accession)
        assert subdir.parts == (species, accession)
