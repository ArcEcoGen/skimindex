"""Unit tests for skimindex.config module."""

import os
from pathlib import Path
from unittest.mock import patch, call

import pytest

from skimindex.config import Config, load, RESERVED_SECTIONS


SAMPLE_TOML = b"""
[directories]
genbank = "/data/genbank"

[genbank]
divisions = "bct pln vrl"

[decontamination]
kmer_size = "31"
frg_size = "150"

[plants]
taxon = "Spermatophyta"

[bacteria]
taxon = "Bacteria"
one_per = "genus"

[custom_section]
taxid = "1234"
divisions = "bct"
"""


@pytest.fixture
def config_file(tmp_path):
    """Write a sample TOML config and return its path."""
    p = tmp_path / "skimindex.toml"
    p.write_bytes(SAMPLE_TOML)
    return p


@pytest.fixture
def cfg(config_file):
    """Return a Config loaded from the sample TOML."""
    return Config(config_file)


class TestConfigLoading:
    def test_config_loads_without_error(self, cfg):
        assert cfg is not None

    def test_config_missing_file_is_empty(self, tmp_path):
        missing = tmp_path / "nonexistent.toml"
        c = Config(missing)
        assert c.data == {}
        assert c.ref_taxa == []
        assert c.ref_genomes == []

    def test_config_path_property(self, cfg, config_file):
        assert cfg.path == config_file

    def test_config_data_returns_copy(self, cfg):
        data = cfg.data
        data["injected"] = {}
        assert "injected" not in cfg.data


class TestSectionIdentification:
    def test_taxon_sections_in_ref_genomes(self, cfg):
        assert "plants" in cfg.ref_genomes
        assert "bacteria" in cfg.ref_genomes

    def test_taxon_sections_in_ref_taxa(self, cfg):
        assert "plants" in cfg.ref_taxa
        assert "bacteria" in cfg.ref_taxa

    def test_taxid_divisions_section_in_ref_taxa(self, cfg):
        assert "custom_section" in cfg.ref_taxa

    def test_taxid_divisions_section_not_in_ref_genomes(self, cfg):
        assert "custom_section" not in cfg.ref_genomes

    def test_reserved_sections_not_in_ref_taxa(self, cfg):
        for section in RESERVED_SECTIONS:
            assert section not in cfg.ref_taxa

    def test_decontamination_not_in_ref_taxa(self, cfg):
        assert "decontamination" not in cfg.ref_taxa

    def test_ref_taxa_returns_copy(self, cfg):
        taxa = cfg.ref_taxa
        taxa.append("injected")
        assert "injected" not in cfg.ref_taxa


class TestConfigGet:
    def test_get_value_from_config(self, cfg):
        assert cfg.get("decontamination", "kmer_size") == "31"

    def test_get_default_when_missing(self, cfg):
        assert cfg.get("nonexistent", "key", "fallback") == "fallback"

    def test_get_builtin_default(self, cfg):
        # decontamination.batches is not in SAMPLE_TOML, uses DEFAULTS
        result = cfg.get("decontamination", "batches")
        assert result == "20"

    def test_get_env_overrides_config(self, cfg, monkeypatch):
        monkeypatch.setenv("SKIMINDEX__DECONTAMINATION__KMER_SIZE", "99")
        assert cfg.get("decontamination", "kmer_size") == "99"

    def test_get_directories_from_config(self, cfg):
        assert cfg.get("directories", "genbank") == "/data/genbank"


class TestConfigSections:
    def test_sections_returns_all_keys(self, cfg):
        sections = cfg.sections()
        assert "plants" in sections
        assert "bacteria" in sections
        assert "genbank" in sections
        assert "decontamination" in sections


class TestConfigRepr:
    def test_repr_contains_path(self, cfg, config_file):
        r = repr(cfg)
        assert str(config_file) in r


_LOGGING_ENV_VARS = [
    "SKIMINDEX__LOGGING__LEVEL",
    "SKIMINDEX__LOGGING__FILE",
    "SKIMINDEX__LOGGING__MIRROR",
    "SKIMINDEX__LOGGING__EVERYTHING",
]


class TestApplyLogging:
    @pytest.fixture(autouse=True)
    def clean_logging_env(self, monkeypatch):
        """Prevent logging env vars from leaking between tests."""
        for var in _LOGGING_ENV_VARS:
            monkeypatch.delenv(var, raising=False)

    def _write_toml(self, tmp_path, content: bytes) -> Path:
        p = tmp_path / "skimindex.toml"
        p.write_bytes(content)
        return p

    def test_openlogfile_called_with_config_values(self, tmp_path):
        logfile = str(tmp_path / "test.log")
        toml = f"""
[logging]
level = "WARNING"
file = "{logfile}"
mirror = true
everything = false
""".encode()
        p = self._write_toml(tmp_path, toml)
        with patch("skimindex.config.openlogfile") as mock_open, \
             patch("skimindex.config.setloglevel") as mock_level:
            Config(p)
        mock_level.assert_called_once_with("WARNING")
        mock_open.assert_called_once_with(logfile, mirror=True, everything=False)

    def test_no_logging_section_does_not_call_openlogfile(self, tmp_path):
        toml = b"[decontamination]\nkmer_size = 29\n"
        p = self._write_toml(tmp_path, toml)
        with patch("skimindex.config.openlogfile") as mock_open:
            Config(p)
        mock_open.assert_not_called()

    def test_logging_section_without_file_does_not_call_openlogfile(self, tmp_path):
        toml = b"[logging]\nlevel = \"DEBUG\"\n"
        p = self._write_toml(tmp_path, toml)
        with patch("skimindex.config.openlogfile") as mock_open, \
             patch("skimindex.config.setloglevel"):
            Config(p)
        mock_open.assert_not_called()

    def test_env_var_overrides_config_logfile(self, tmp_path, monkeypatch):
        logfile_config = str(tmp_path / "config.log")
        logfile_env = str(tmp_path / "env.log")
        toml = f"""
[logging]
file = "{logfile_config}"
""".encode()
        p = self._write_toml(tmp_path, toml)
        monkeypatch.setenv("SKIMINDEX__LOGGING__FILE", logfile_env)
        with patch("skimindex.config.openlogfile") as mock_open, \
             patch("skimindex.config.setloglevel"):
            Config(p)
        mock_open.assert_called_once()
        assert mock_open.call_args.args[0] == logfile_env

    def test_mirror_false_by_default(self, tmp_path):
        logfile = str(tmp_path / "test.log")
        toml = f'[logging]\nfile = "{logfile}"\n'.encode()
        p = self._write_toml(tmp_path, toml)
        with patch("skimindex.config.openlogfile") as mock_open, \
             patch("skimindex.config.setloglevel"):
            Config(p)
        _, kwargs = mock_open.call_args
        assert kwargs["mirror"] is False
        assert kwargs["everything"] is False
