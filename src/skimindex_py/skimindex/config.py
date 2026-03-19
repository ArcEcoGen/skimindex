"""
Config module for skimindex — reads TOML configuration and provides access
to parsed values, genome section identification, and environment variable export.

The configuration file is expected at /config/skimindex.toml by default.
Environment variables take priority over config file values.

Section types:
  - [logging], [local_directories], [genbank]: reserved sections
  - [decontamination]: pipeline parameters
  - Genome sections: [name] with either:
    - 'taxon' key (downloadable via NCBI datasets)
    - 'taxid' AND 'divisions' keys (filtered from GenBank flat files)
"""

import os
import tomllib
from pathlib import Path
from typing import Any

from skimindex.log import loginfo, openlogfile, setloglevel


DEFAULT_CONFIG = Path(os.environ.get("SKIMINDEX_CONFIG", "/config/skimindex.toml"))

# Built-in defaults (priority: env > config file > these)
DEFAULTS = {
    ("directories", "genbank"): "/genbank",
    ("directories", "processed_data"): "/processed_data",
    ("genbank", "divisions"): "bct pln",
    ("decontamination", "kmer_size"): "29",
    ("decontamination", "frg_size"): "200",
    ("decontamination", "batches"): "20",
}

RESERVED_SECTIONS = {"logging", "local_directories", "genbank", "directories"}


class Config:
    """Parse and provide access to skimindex TOML configuration."""

    def __init__(self, path: Path = DEFAULT_CONFIG):
        self._path = Path(path)
        self._data: dict[str, dict[str, Any]] = {}
        self._ref_taxa: list[str] = []
        self._ref_genomes: list[str] = []

        if self._path.exists():
            self._load()
            self._identify_sections()
            self._export_env()
            self._apply_logging()

    def _load(self) -> None:
        """Load and parse TOML config file."""
        with open(self._path, "rb") as f:
            self._data = tomllib.load(f)

    def _identify_sections(self) -> None:
        """Identify reference taxa and genomes.

        ref_taxa: all sections with 'taxon' OR ('taxid' AND 'divisions')
        ref_genomes: sections with 'taxon' key (downloadable via NCBI datasets)
        """
        for section_name, section_content in self._data.items():
            if section_name in RESERVED_SECTIONS:
                continue

            has_taxon = "taxon" in section_content
            has_taxid = "taxid" in section_content
            has_divisions = "divisions" in section_content

            # ref_taxa: taxon sections OR (taxid+divisions sections)
            if has_taxon or (has_taxid and has_divisions):
                self._ref_taxa.append(section_name)
                # ref_genomes: only taxon-based sections (downloadable)
                if has_taxon:
                    self._ref_genomes.append(section_name)

    @property
    def ref_taxa(self) -> list[str]:
        """Read-only list of all reference taxa (taxon OR taxid+divisions)."""
        return self._ref_taxa.copy()

    @property
    def ref_genomes(self) -> list[str]:
        """Read-only list of reference genomes (taxon-based, downloadable via NCBI datasets)."""
        return self._ref_genomes.copy()

    @property
    def path(self) -> Path:
        """Read-only config file path."""
        return self._path

    @property
    def data(self) -> dict[str, dict[str, Any]]:
        """Read-only config data dictionary."""
        return self._data.copy()

    def _export_env(self) -> None:
        """
        Export config as environment variables: SKIMINDEX__{SECTION}__{KEY}=value.
        Pre-existing environment variables are never overwritten.
        Also exports SKIMINDEX__REF_TAXA and SKIMINDEX__REF_GENOMES.
        Called automatically in __init__.
        """
        for section, section_content in self._data.items():
            if section == "local_directories":
                # Derive container paths: SKIMINDEX__DIRECTORIES__{KEY} = /{key}
                for key in section_content:
                    var_name = f"SKIMINDEX__DIRECTORIES__{key.upper()}"
                    if var_name not in os.environ:
                        os.environ[var_name] = f"/{key}"
                continue

            if section == "directories":
                # Skip obsolete section
                continue

            # Export section keys
            for key, value in section_content.items():
                var_name = f"SKIMINDEX__{section.upper()}__{key.upper()}"
                if var_name not in os.environ:
                    os.environ[var_name] = str(value)

        # Export reference taxa/genomes lists
        if "SKIMINDEX__REF_TAXA" not in os.environ:
            os.environ["SKIMINDEX__REF_TAXA"] = " ".join(self._ref_taxa)
        if "SKIMINDEX__REF_GENOMES" not in os.environ:
            os.environ["SKIMINDEX__REF_GENOMES"] = " ".join(self._ref_genomes)

    def _apply_logging(self) -> None:
        """Apply [logging] section: set log level and open log file."""
        logging_section = self._data.get("logging", {})
        if not logging_section:
            return

        level = self.get("logging", "level", "INFO")
        setloglevel(level)

        # Only open a log file if the config file itself specifies one.
        # Environment variable overrides are still honoured via self.get(),
        # but we require the key to exist in the TOML so that a stray
        # SKIMINDEX__LOGGING__FILE env var doesn't silently hijack logging.
        if "file" not in logging_section:
            return

        def _bool(val: str) -> bool:
            return val.lower() in ("true", "1", "yes")

        logfile = self.get("logging", "file")
        mirror = _bool(self.get("logging", "mirror", "false"))
        everything = _bool(self.get("logging", "everything", "false"))
        openlogfile(logfile, mirror=mirror, everything=everything)

    def get(self, section: str, key: str, default: str = "") -> str:
        """
        Get config value (environment variable > config file > defaults).
        Returns the value as a string, or default if not found.

        Examples:
          config.get("decontamination", "kmer_size") → "29"
          config.get("unknown", "key", "fallback") → "fallback"
        """
        var_name = f"SKIMINDEX__{section.upper()}__{key.upper()}"

        # Priority: environment > config file > defaults
        if var_name in os.environ:
            return os.environ[var_name]

        val = self._data.get(section, {}).get(key)
        if val is not None:
            return str(val)

        # Check built-in defaults
        if (section, key) in DEFAULTS:
            return DEFAULTS[(section, key)]

        return default

    def sections(self) -> list[str]:
        """Return list of all section names in the config."""
        return list(self._data.keys())

    def __repr__(self) -> str:
        return f"Config(path={self._path}, sections={list(self._data.keys())})"


def load(path: Path = DEFAULT_CONFIG) -> Config:
    """Load and return a Config instance."""
    return Config(path)


# ===== Module-level singleton (lazy initialization) =====

_CONFIG: Config | None = None


def config() -> Config:
    """
    Get the singleton Config instance (lazy initialization, read-only).

    The configuration is loaded on first access and cached for subsequent calls.

    Returns:
        Config: The read-only configuration singleton

    Example:
        cfg = config()
        ref_genomes = cfg.ref_genomes
    """
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = load()
    return _CONFIG


# ===== doit configuration task =====


def task_config():
    """Validate and display configuration (runs first, dependencies use it).

    This is a reusable doit task for all pipelines that depend on configuration.
    Validates and displays the singleton configuration.

    Can be imported and used from other modules:

        from skimindex.config import task_config
        # Then reference as a task dependency: "task_dep": ["config"]
    """
    def validate_config():
        cfg = config()
        loginfo("===== Configuration Loaded =====")
        loginfo(f"Config path: {cfg.path}")

        ref_taxa = cfg.ref_taxa
        ref_genomes = cfg.ref_genomes
        loginfo(f"Reference taxa: {', '.join(ref_taxa) if ref_taxa else '<none>'}")
        loginfo(f"Reference genomes: {', '.join(ref_genomes) if ref_genomes else '<none>'}")

        divisions = cfg.get("genbank", "divisions", "bct pln")
        loginfo(f"GenBank divisions: {divisions}")
        return True

    return {
        "actions": [validate_config],
        "verbosity": 2,
    }
