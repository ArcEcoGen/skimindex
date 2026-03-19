"""Unit tests for skimindex.config module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from skimindex.config import (
    Config,
    load,
    CONFIGURATION_SECTIONS,
    SECTION_PREFIXES,
    _env_key,
)


SAMPLE_TOML = b"""
[local_directories]
genbank = "genbank"
raw_data = "raw_data"
processed_data = "processed_data"
indexes = "indexes"
stamp = "stamp"
log = "log"

[processed_data]
directory = "processed_data"

[indexes]
directory = "indexes"

[stamp]
directory = "stamp"

[source.ncbi]
directory = "genbank"

[source.genbank]
directory = "genbank"
divisions = ["bct", "pln"]

[source.internal]
directory = "raw_data"

[role.decontamination]
directory = "decontamination"
run = "prepare_decontam"

[processing.split_test]
type = "split"
directory = "split"
size = 200
overlap = 28

[processing.prepare_test]
directory = "prepared"
steps = ["split_test"]

[data.human]
source = "ncbi"
role = "decontamination"
example = true
taxon = "human"

[data.fungi]
source = "genbank"
role = "decontamination"
example = true
by_species = false
divisions = ["pln"]
taxid = 4751

[data.plants]
source = "ncbi"
role = "decontamination"
example = false
taxon = "Spermatophyta"
"""


@pytest.fixture
def config_file(tmp_path):
    p = tmp_path / "skimindex.toml"
    p.write_bytes(SAMPLE_TOML)
    return p


@pytest.fixture
def cfg(config_file):
    return Config(config_file)


# ======================================================================
# Loading
# ======================================================================

class TestConfigLoading:
    def test_loads_without_error(self, cfg):
        assert cfg is not None

    def test_missing_file_is_empty(self, tmp_path):
        c = Config(tmp_path / "nonexistent.toml")
        assert c.data == {}
        assert c.ref_taxa == []
        assert c.ref_genomes == []

    def test_path_property(self, cfg, config_file):
        assert cfg.path == config_file

    def test_data_returns_copy(self, cfg):
        data = cfg.data
        data["injected"] = {}
        assert "injected" not in cfg.data


# ======================================================================
# Section type constants
# ======================================================================

class TestSectionConstants:
    def test_configuration_sections(self):
        assert "logging" in CONFIGURATION_SECTIONS
        assert "local_directories" in CONFIGURATION_SECTIONS
        assert "processed_data" in CONFIGURATION_SECTIONS
        assert "indexes" in CONFIGURATION_SECTIONS
        assert "stamp" in CONFIGURATION_SECTIONS

    def test_section_prefixes(self):
        assert "source" in SECTION_PREFIXES
        assert "role" in SECTION_PREFIXES
        assert "processing" in SECTION_PREFIXES
        assert "data" in SECTION_PREFIXES


# ======================================================================
# Typed section accessors
# ======================================================================

class TestTypedAccessors:
    def test_sources_keys(self, cfg):
        assert set(cfg.sources.keys()) == {"ncbi", "genbank", "internal"}

    def test_sources_content(self, cfg):
        assert cfg.sources["ncbi"]["directory"] == "genbank"
        assert cfg.sources["genbank"]["divisions"] == ["bct", "pln"]

    def test_roles_keys(self, cfg):
        assert "decontamination" in cfg.roles

    def test_roles_content(self, cfg):
        assert cfg.roles["decontamination"]["run"] == "prepare_decontam"

    def test_processing_keys(self, cfg):
        assert "split_test" in cfg.processing
        assert "prepare_test" in cfg.processing

    def test_processing_atomic(self, cfg):
        s = cfg.processing["split_test"]
        assert s["type"] == "split"
        assert s["size"] == 200

    def test_processing_composite(self, cfg):
        p = cfg.processing["prepare_test"]
        assert "steps" in p
        assert p["directory"] == "prepared"

    def test_datasets_keys(self, cfg):
        assert set(cfg.datasets.keys()) == {"human", "fungi", "plants"}

    def test_datasets_content(self, cfg):
        assert cfg.datasets["human"]["source"] == "ncbi"
        assert cfg.datasets["fungi"]["taxid"] == 4751

    def test_sources_returns_independent_copy(self, cfg):
        s = cfg.sources
        s["injected"] = {}
        assert "injected" not in cfg.sources


# ======================================================================
# ref_taxa / ref_genomes
# ======================================================================

class TestRefTaxaGenomes:
    def test_ref_taxa_includes_ncbi_and_genbank(self, cfg):
        # human + plants (ncbi) and fungi (genbank)
        assert "human" in cfg.ref_taxa
        assert "plants" in cfg.ref_taxa
        assert "fungi" in cfg.ref_taxa

    def test_ref_genomes_only_ncbi(self, cfg):
        assert "human" in cfg.ref_genomes
        assert "plants" in cfg.ref_genomes
        assert "fungi" not in cfg.ref_genomes

    def test_ref_taxa_returns_list_copy(self, cfg):
        taxa = cfg.ref_taxa
        taxa.append("injected")
        assert "injected" not in cfg.ref_taxa


# ======================================================================
# get() — dotted section names
# ======================================================================

class TestConfigGet:
    def test_get_root_section(self, cfg):
        assert cfg.get("role.decontamination", "run") == "prepare_decontam"

    def test_get_source_section(self, cfg):
        assert cfg.get("source.ncbi", "directory") == "genbank"

    def test_get_data_section(self, cfg):
        assert cfg.get("data.human", "taxon") == "human"

    def test_get_missing_returns_default(self, cfg):
        assert cfg.get("source.ncbi", "nonexistent", "fallback") == "fallback"

    def test_get_missing_section_returns_default(self, cfg):
        assert cfg.get("source.missing", "directory", "x") == "x"

    def test_env_var_overrides_config(self, cfg, monkeypatch):
        monkeypatch.setenv("SKIMINDEX__SOURCE__NCBI__DIRECTORY", "override")
        assert cfg.get("source.ncbi", "directory") == "override"

    def test_get_logging_level(self, cfg):
        # logging section has no level in SAMPLE_TOML — returns default
        assert cfg.get("logging", "level", "INFO") == "INFO"


# ======================================================================
# _env_key helper
# ======================================================================

class TestEnvKey:
    def test_flat_section(self):
        assert _env_key("logging", "level") == "SKIMINDEX__LOGGING__LEVEL"

    def test_dotted_section(self):
        assert _env_key("source.ncbi", "directory") == "SKIMINDEX__SOURCE__NCBI__DIRECTORY"

    def test_data_section(self):
        assert _env_key("data.human", "taxon") == "SKIMINDEX__DATA__HUMAN__TAXON"


# ======================================================================
# Path helpers
# ======================================================================

class TestPathHelpers:
    def test_root_default(self, cfg, monkeypatch):
        monkeypatch.delenv("SKIMINDEX_ROOT", raising=False)
        assert cfg.root == Path("/")

    def test_root_from_env(self, cfg, monkeypatch):
        monkeypatch.setenv("SKIMINDEX_ROOT", "/mnt/test")
        assert cfg.root == Path("/mnt/test")

    def test_source_dir(self, cfg, monkeypatch):
        monkeypatch.delenv("SKIMINDEX_ROOT", raising=False)
        assert cfg.source_dir("ncbi") == Path("/genbank")

    def test_source_dir_internal(self, cfg, monkeypatch):
        monkeypatch.delenv("SKIMINDEX_ROOT", raising=False)
        assert cfg.source_dir("internal") == Path("/raw_data")

    def test_processed_data_dir(self, cfg, monkeypatch):
        monkeypatch.delenv("SKIMINDEX_ROOT", raising=False)
        assert cfg.processed_data_dir() == Path("/processed_data")

    def test_indexes_dir(self, cfg, monkeypatch):
        monkeypatch.delenv("SKIMINDEX_ROOT", raising=False)
        assert cfg.indexes_dir() == Path("/indexes")

    def test_stamp_dir(self, cfg, monkeypatch):
        monkeypatch.delenv("SKIMINDEX_ROOT", raising=False)
        assert cfg.stamp_dir() == Path("/stamp")

    def test_raw_data_dir_is_internal_source(self, cfg, monkeypatch):
        monkeypatch.delenv("SKIMINDEX_ROOT", raising=False)
        assert cfg.raw_data_dir() == cfg.source_dir("internal")

    def test_root_prefix_applied(self, cfg, monkeypatch):
        monkeypatch.setenv("SKIMINDEX_ROOT", "/workspace")
        assert cfg.processed_data_dir() == Path("/workspace/processed_data")


# ======================================================================
# Environment variable export
# ======================================================================

_ENV_VARS_TO_CLEAN = [
    "SKIMINDEX_ROOT",
    "SKIMINDEX__SOURCE__NCBI__DIRECTORY",
    "SKIMINDEX__ROLE__DECONTAMINATION__RUN",
    "SKIMINDEX__DATA__HUMAN__TAXON",
    "SKIMINDEX__LOCAL_DIRECTORIES__GENBANK",
    "SKIMINDEX__REF_TAXA",
    "SKIMINDEX__REF_GENOMES",
    "SKIMINDEX__PROCESSED_DATA__DIRECTORY",
]


class TestEnvExport:
    @pytest.fixture(autouse=True)
    def clean_env(self, monkeypatch):
        for var in _ENV_VARS_TO_CLEAN:
            monkeypatch.delenv(var, raising=False)

    def test_source_ncbi_directory_exported(self, cfg):
        assert os.environ.get("SKIMINDEX__SOURCE__NCBI__DIRECTORY") == "genbank"

    def test_role_decontamination_run_exported(self, cfg):
        assert os.environ.get("SKIMINDEX__ROLE__DECONTAMINATION__RUN") == "prepare_decontam"

    def test_data_human_taxon_exported(self, cfg):
        assert os.environ.get("SKIMINDEX__DATA__HUMAN__TAXON") == "human"

    def test_local_directories_exported_as_mount_paths(self, cfg):
        assert os.environ.get("SKIMINDEX__LOCAL_DIRECTORIES__GENBANK") == "/genbank"

    def test_processed_data_directory_exported(self, cfg):
        assert os.environ.get("SKIMINDEX__PROCESSED_DATA__DIRECTORY") == "processed_data"

    def test_ref_taxa_exported(self, cfg):
        ref_taxa = os.environ.get("SKIMINDEX__REF_TAXA", "")
        assert "human" in ref_taxa
        assert "fungi" in ref_taxa

    def test_ref_genomes_exported(self, cfg):
        ref_genomes = os.environ.get("SKIMINDEX__REF_GENOMES", "")
        assert "human" in ref_genomes
        assert "fungi" not in ref_genomes

    def test_existing_env_var_not_overwritten(self, config_file, monkeypatch):
        monkeypatch.setenv("SKIMINDEX__SOURCE__NCBI__DIRECTORY", "kept")
        c = Config(config_file)
        assert c.get("source.ncbi", "directory") == "kept"


# ======================================================================
# Logging
# ======================================================================

_LOGGING_ENV_VARS = [
    "SKIMINDEX__LOGGING__LEVEL",
    "SKIMINDEX__LOGGING__FILE",
    "SKIMINDEX__LOGGING__MIRROR",
    "SKIMINDEX__LOGGING__EVERYTHING",
]


class TestApplyLogging:
    @pytest.fixture(autouse=True)
    def clean_logging_env(self, monkeypatch):
        for var in _LOGGING_ENV_VARS:
            monkeypatch.delenv(var, raising=False)

    def _write_toml(self, tmp_path, content: bytes) -> Path:
        p = tmp_path / "skimindex.toml"
        p.write_bytes(content)
        return p

    def test_openlogfile_called_with_config_values(self, tmp_path):
        logfile_path = tmp_path / "test.log"
        toml = f"""
[logging]
directory = "."
file = "{logfile_path.name}"
level = "WARNING"
mirror = true
everything = false
""".encode()
        p = self._write_toml(tmp_path, toml)
        with patch("skimindex.config.openlogfile") as mock_open, \
             patch("skimindex.config.setloglevel") as mock_level:
            c = Config(p)
            # Patch root to tmp_path so log_file() resolves correctly
            with patch.object(type(c), "root", new_callable=lambda: property(lambda self: tmp_path)):
                pass
        mock_level.assert_called_once_with("WARNING")
        mock_open.assert_called_once()

    def test_no_logging_section_does_not_call_openlogfile(self, tmp_path):
        toml = b"[processed_data]\ndirectory = \"processed_data\"\n"
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

    def test_mirror_false_by_default(self, tmp_path):
        toml = b"[logging]\nfile = \"test.log\"\n"
        p = self._write_toml(tmp_path, toml)
        with patch("skimindex.config.openlogfile") as mock_open, \
             patch("skimindex.config.setloglevel"):
            Config(p)
        _, kwargs = mock_open.call_args
        assert kwargs["mirror"] is False
        assert kwargs["everything"] is False


# ======================================================================
# sections() and repr
# ======================================================================

class TestMiscellaneous:
    def test_sections_returns_top_level_keys(self, cfg):
        sections = cfg.sections()
        assert "local_directories" in sections
        assert "source" in sections
        assert "role" in sections
        assert "data" in sections

    def test_repr_contains_path(self, cfg, config_file):
        assert str(config_file) in repr(cfg)
