"""Unit tests for pure-Python logic in download modules (no network calls)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ──────────────────────────────────────────────
# refgenome.py — pure logic tests
# ──────────────────────────────────────────────

class TestRefgenomePureLogic:
    def test_safe_name_replaces_spaces(self):
        from skimindex.sources.download.ncbi import _safe_name
        assert _safe_name("Homo sapiens") == "Homo_sapiens"

    def test_safe_name_replaces_special_chars(self):
        from skimindex.sources.download.ncbi import _safe_name
        result = _safe_name("E. coli / O157:H7")
        assert "/" not in result
        assert ":" not in result

    def test_safe_name_collapses_multiple_underscores(self):
        from skimindex.sources.download.ncbi import _safe_name
        result = _safe_name("A  B   C")
        assert "__" not in result

    def test_safe_name_strips_leading_trailing_underscores(self):
        from skimindex.sources.download.ncbi import _safe_name
        result = _safe_name("  leading trailing  ")
        assert not result.startswith("_")
        assert not result.endswith("_")

    def test_get_accession_type_gcf_is_zero(self):
        from skimindex.sources.download.ncbi import _get_accession_type
        assert _get_accession_type("GCF_000001405.40") == 0

    def test_get_accession_type_gca_is_one(self):
        from skimindex.sources.download.ncbi import _get_accession_type
        assert _get_accession_type("GCA_000001405.40") == 1

    def test_get_genome_size_parses_int(self):
        from skimindex.sources.download.ncbi import _get_genome_size
        assembly = {"assembly_stats": {"total_sequence_length": "3000000000"}}
        assert _get_genome_size(assembly) == 3_000_000_000

    def test_get_genome_size_missing_returns_zero(self):
        from skimindex.sources.download.ncbi import _get_genome_size
        assert _get_genome_size({}) == 0

    def test_get_genome_size_invalid_string_returns_zero(self):
        from skimindex.sources.download.ncbi import _get_genome_size
        assembly = {"assembly_stats": {"total_sequence_length": "N/A"}}
        assert _get_genome_size(assembly) == 0

    def _make_assembly(self, accession, organism_name, genome_size):
        return {
            "accession": accession,
            "assembly_info": {
                "biosample": {
                    "description": {
                        "organism": {
                            "organism_name": organism_name,
                            "tax_id": 9606,
                        }
                    }
                }
            },
            "assembly_stats": {"total_sequence_length": str(genome_size)},
        }

    def test_filter_by_species_one_per_species(self):
        from skimindex.sources.download.ncbi import filter_assemblies_by_species
        assemblies = [
            self._make_assembly("GCF_001", "Homo sapiens", 3_000_000_000),
            self._make_assembly("GCA_002", "Homo sapiens", 2_800_000_000),
            self._make_assembly("GCF_003", "Mus musculus", 2_700_000_000),
        ]
        result = filter_assemblies_by_species(assemblies)
        accessions = {a["accession"] for a in result}
        # One per species, prefer GCF
        assert "GCF_001" in accessions
        assert "GCF_003" in accessions
        assert len(accessions) == 2

    def test_filter_by_genus_one_per_genus(self):
        from skimindex.sources.download.ncbi import filter_assemblies_by_genus
        assemblies = [
            self._make_assembly("GCF_001", "Homo sapiens", 3_000_000_000),
            self._make_assembly("GCF_002", "Homo neanderthalensis", 2_900_000_000),
            self._make_assembly("GCF_003", "Mus musculus", 2_700_000_000),
        ]
        result = filter_assemblies_by_genus(assemblies)
        genera = {a["accession"].split("_")[0] for a in result}
        # Only one Homo and one Mus
        assert len(result) == 2

    def test_filter_prefers_gcf_over_gca(self):
        from skimindex.sources.download.ncbi import filter_assemblies_by_species
        assemblies = [
            self._make_assembly("GCA_001", "Homo sapiens", 3_000_000_000),
            self._make_assembly("GCF_002", "Homo sapiens", 100),  # smaller but GCF
        ]
        result = filter_assemblies_by_species(assemblies)
        assert result[0]["accession"] == "GCF_002"

    def test_filter_prefers_larger_genome_among_same_source(self):
        from skimindex.sources.download.ncbi import filter_assemblies_by_species
        assemblies = [
            self._make_assembly("GCF_001", "Homo sapiens", 1_000_000),
            self._make_assembly("GCF_002", "Homo sapiens", 3_000_000_000),
        ]
        result = filter_assemblies_by_species(assemblies)
        assert result[0]["accession"] == "GCF_002"


# ──────────────────────────────────────────────
# genbank.py — pure logic tests
# ──────────────────────────────────────────────

class TestGenbankPureLogic:
    def test_get_ftp_listing_parses_bct_files(self):
        from skimindex.sources.download.genbank import get_ftp_listing
        fake_output = (
            "gbbct1.seq.gz  1234  2024\n"
            "gbbct2.seq.gz  5678  2024\n"
            "gbpln1.seq.gz  9999  2024\n"
            "other_file.txt  0  2024\n"
        )
        with patch("skimindex.sources.download.genbank.curl_download") as mock_curl:
            mock_curl.return_value = MagicMock(return_value=fake_output)
            result = get_ftp_listing(["bct"])
        assert "gbbct1.seq.gz" in result
        assert "gbbct2.seq.gz" in result
        assert "gbpln1.seq.gz" not in result
        assert "other_file.txt" not in result

    def test_get_ftp_listing_multi_division(self):
        from skimindex.sources.download.genbank import get_ftp_listing
        fake_output = (
            "gbbct1.seq.gz\n"
            "gbpln1.seq.gz\n"
            "gbvrl1.seq.gz\n"
        )
        with patch("skimindex.sources.download.genbank.curl_download") as mock_curl:
            mock_curl.return_value = MagicMock(return_value=fake_output)
            result = get_ftp_listing(["bct", "pln"])
        assert "gbbct1.seq.gz" in result
        assert "gbpln1.seq.gz" in result
        assert "gbvrl1.seq.gz" not in result

    def test_get_ftp_listing_returns_tuple(self):
        from skimindex.sources.download.genbank import get_ftp_listing
        with patch("skimindex.sources.download.genbank.curl_download") as mock_curl:
            mock_curl.return_value = MagicMock(return_value="gbbct1.seq.gz\n")
            result = get_ftp_listing(["bct"])
        assert isinstance(result, tuple)

    def test_get_ftp_listing_empty_on_error(self):
        from skimindex.sources.download.genbank import get_ftp_listing
        with patch("skimindex.sources.download.genbank.curl_download") as mock_curl:
            mock_curl.return_value = MagicMock(side_effect=RuntimeError("network error"))
            result = get_ftp_listing(["bct"])
        assert result == ()

    def test_list_divisions_from_config(self):
        from skimindex.sources.download.genbank import list_divisions
        mock_cfg = MagicMock()
        mock_cfg.sources = {"genbank": {"divisions": ["bct", "pln", "vrl"]}}
        with patch("skimindex.sources.download.genbank.config", return_value=mock_cfg):
            result = list_divisions()
        assert result == "bct,pln,vrl"

    def test_get_release_number_strips_whitespace(self):
        from skimindex.sources.download import genbank
        # Reset lru_cache to avoid interference between tests
        genbank.get_release_number.cache_clear()
        with patch("skimindex.sources.download.genbank.curl_download") as mock_curl:
            mock_curl.return_value = MagicMock(return_value="  261  \n")
            result = genbank.get_release_number()
        assert result == "261"
        genbank.get_release_number.cache_clear()

    def test_get_release_number_returns_unknown_on_error(self):
        from skimindex.sources.download import genbank
        genbank.get_release_number.cache_clear()
        with patch("skimindex.sources.download.genbank.curl_download") as mock_curl:
            mock_curl.return_value = MagicMock(side_effect=RuntimeError("fail"))
            result = genbank.get_release_number()
        assert result == "unknown"
        genbank.get_release_number.cache_clear()
