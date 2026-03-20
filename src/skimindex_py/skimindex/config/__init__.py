"""
Config module for skimindex — reads TOML configuration and provides typed
access to all sections, path helpers, and environment variable export.

The configuration file is expected at /config/skimindex.toml by default,
overridable via SKIMINDEX_CONFIG environment variable.

Section types (identified by TOML prefix):
  [local_directories], [logging], [processed_data], [indexes], [stamp]
      → root-level configuration sections
  [source.X]      → data origin parameters
  [role.X]        → data usage / pipeline parameters
  [processing.X]  → pipeline step definitions (atomic or composite)
  [data.X]        → dataset declarations (require source + role)

Environment variable schema:
  SKIMINDEX__LOGGING__LEVEL           (root section)
  SKIMINDEX__SOURCE__NCBI__DIRECTORY  (prefixed section)
  SKIMINDEX__DATA__HUMAN__TAXON       (prefixed section)
  SKIMINDEX__ROOT                     (mount root, default "/")
  SKIMINDEX__REF_TAXA                 (space-separated list)
  SKIMINDEX__REF_GENOMES              (space-separated list)
"""

import os
import shlex
import tomllib
from pathlib import Path
from typing import Any

from skimindex.log import openlogfile, setloglevel
from skimindex.config.validate import (  # noqa: E402 — after class definitions below
    ConfigError,
    ConfigValidationError,
    validate,
    validate_or_raise,
)


DEFAULT_CONFIG = Path(os.environ.get("SKIMINDEX_CONFIG", "/config/skimindex.toml"))

CONFIGURATION_SECTIONS = frozenset({
    "local_directories", "logging", "processed_data", "indexes", "stamp"
})
SECTION_PREFIXES = frozenset({"source", "role", "processing", "data"})


def _env_key(section: str, key: str) -> str:
    """Build the SKIMINDEX__ env var name for a section + key.

    Examples:
        _env_key("logging", "level")         → "SKIMINDEX__LOGGING__LEVEL"
        _env_key("source.ncbi", "directory") → "SKIMINDEX__SOURCE__NCBI__DIRECTORY"
    """
    section_part = section.upper().replace(".", "__")
    return f"SKIMINDEX__{section_part}__{key.upper()}"


class Config:
    """Parse and provide typed access to skimindex TOML configuration."""

    def __init__(self, path: Path = DEFAULT_CONFIG, *, apply_logging: bool = True,
                 export_env: bool = True):
        self._path = Path(path)
        self._raw: dict[str, Any] = {}

        if self._path.exists():
            self._load()
            if export_env:
                self._export_env()
            if apply_logging:
                self._apply_logging()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        try:
            with open(self._path, "rb") as f:
                self._raw = tomllib.load(f)
        except Exception as e:
            e.add_note(f"Config file: {self._path}")
            raise

    # ------------------------------------------------------------------
    # Typed section accessors
    # ------------------------------------------------------------------

    def _prefix_group(self, prefix: str) -> dict[str, dict[str, Any]]:
        """Return the dict of sub-sections under a given prefix, e.g. 'source'."""
        val = self._raw.get(prefix, {})
        if not isinstance(val, dict):
            return {}
        return {k: v for k, v in val.items() if isinstance(v, dict)}

    @property
    def sources(self) -> dict[str, dict[str, Any]]:
        """All [source.X] sections, keyed by X."""
        return self._prefix_group("source")

    @property
    def roles(self) -> dict[str, dict[str, Any]]:
        """All [role.X] sections, keyed by X."""
        return self._prefix_group("role")

    @property
    def processing(self) -> dict[str, dict[str, Any]]:
        """All [processing.X] sections, keyed by X."""
        return self._prefix_group("processing")

    @property
    def datasets(self) -> dict[str, dict[str, Any]]:
        """All [data.X] sections, keyed by X."""
        return self._prefix_group("data")

    @property
    def ref_taxa(self) -> list[str]:
        """Names of all datasets with source 'ncbi' or 'genbank'."""
        return [
            name for name, ds in self.datasets.items()
            if ds.get("source") in ("ncbi", "genbank")
        ]

    @property
    def ref_genomes(self) -> list[str]:
        """Names of all datasets with source 'ncbi' (downloadable via NCBI datasets CLI)."""
        return [
            name for name, ds in self.datasets.items()
            if ds.get("source") == "ncbi"
        ]

    # ------------------------------------------------------------------
    # Root-level config section helpers
    # ------------------------------------------------------------------

    def _config_section(self, name: str) -> dict[str, Any]:
        val = self._raw.get(name, {})
        return val if isinstance(val, dict) else {}

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    @property
    def root(self) -> Path:
        """Container/runtime root path from SKIMINDEX_ROOT env var (default '/')."""
        return Path(os.environ.get("SKIMINDEX_ROOT", "/"))

    def _local_dir(self, key: str) -> Path:
        """Resolve a [local_directories] key to its container mount path (root/<key>)."""
        return self.root / key

    def source_dir(self, name: str) -> Path:
        """Return the mount path for a named source (root / sources[name]["directory"])."""
        directory = self.sources.get(name, {}).get("directory", name)
        return self._local_dir(directory)

    def processed_data_dir(self) -> Path:
        """Return the processed data root (root / [processed_data].directory)."""
        directory = self._config_section("processed_data").get("directory", "processed_data")
        return self._local_dir(directory)

    def indexes_dir(self) -> Path:
        """Return the indexes root (root / [indexes].directory)."""
        directory = self._config_section("indexes").get("directory", "indexes")
        return self._local_dir(directory)

    def stamp_dir(self) -> Path:
        """Return the stamp root (root / [stamp].directory)."""
        directory = self._config_section("stamp").get("directory", "stamp")
        return self._local_dir(directory)

    def log_file(self) -> Path:
        """Return the log file path (root / [logging].directory / [logging].file)."""
        log_section = self._config_section("logging")
        directory = log_section.get("directory", "log")
        filename = log_section.get("file", "skimindex.log")
        return self._local_dir(directory) / filename

    def raw_data_dir(self) -> Path:
        """Return the internal/raw data root (source_dir('internal'))."""
        return self.source_dir("internal")

    # ------------------------------------------------------------------
    # Generic value accessor
    # ------------------------------------------------------------------

    def get(self, section: str, key: str, default: str = "") -> str:
        """Get a config value with precedence: env var > TOML > default.

        section may be dotted ("source.ncbi") for prefixed sections.

        Examples:
            config.get("logging", "level")          → "INFO"
            config.get("source.ncbi", "directory")  → "genbank"
            config.get("data.human", "taxon")       → "human"
        """
        var_name = _env_key(section, key)
        if var_name in os.environ:
            return os.environ[var_name]

        # Navigate nested TOML structure
        parts = section.split(".")
        node: Any = self._raw
        for part in parts:
            if not isinstance(node, dict):
                return default
            node = node.get(part)
            if node is None:
                return default

        if not isinstance(node, dict):
            return default
        val = node.get(key)
        return str(val) if val is not None else default

    # ------------------------------------------------------------------
    # Read-only data property (raw TOML)
    # ------------------------------------------------------------------

    @property
    def data(self) -> dict[str, Any]:
        """Read-only copy of the raw parsed TOML data."""
        return self._raw.copy()

    @property
    def path(self) -> Path:
        """Absolute path to the TOML configuration file."""
        return self._path

    def sections(self) -> list[str]:
        """Return all top-level section names."""
        return list(self._raw.keys())

    # ------------------------------------------------------------------
    # Environment variable export
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_value(value: Any) -> str:
        """Serialize a TOML value to a shell-safe string.

        - list  → space-separated items (e.g. ``["bct", "pln"]`` → ``"bct pln"``)
        - bool  → ``"true"`` / ``"false"`` (lowercase, TOML/shell convention)
        - other → ``str(value)``
        """
        if isinstance(value, list):
            return " ".join(str(v) for v in value)
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def env_vars(self) -> dict[str, str]:
        """Return all SKIMINDEX__ environment variables as a plain dict.

        Does not touch ``os.environ`` — suitable for inspection or shell export.
        Derived variables (REF_TAXA, REF_GENOMES) are included.
        """
        sv = self._serialize_value
        out: dict[str, str] = {}

        out["SKIMINDEX_ROOT"] = str(self.root)

        for section_name, section_content in self._raw.items():
            if not isinstance(section_content, dict):
                continue

            if section_name == "local_directories":
                for key in section_content:
                    out[f"SKIMINDEX__LOCAL_DIRECTORIES__{key.upper()}"] = f"/{key}"
                continue

            if section_name in CONFIGURATION_SECTIONS:
                for key, value in section_content.items():
                    out[_env_key(section_name, key)] = sv(value)
                continue

            if section_name in SECTION_PREFIXES:
                for sub_name, sub_content in section_content.items():
                    if not isinstance(sub_content, dict):
                        continue
                    for key, value in sub_content.items():
                        if isinstance(value, (dict, list)) and any(
                            isinstance(v, dict) for v in (value if isinstance(value, list) else [])
                        ):
                            continue  # skip steps arrays (list of inline tables)
                        out[_env_key(f"{section_name}.{sub_name}", key)] = sv(value)

        out["SKIMINDEX__REF_TAXA"]    = " ".join(self.ref_taxa)
        out["SKIMINDEX__REF_GENOMES"] = " ".join(self.ref_genomes)
        return out

    def dump_env(self) -> str:
        """Return a shell snippet that exports all SKIMINDEX__ variables.

        Variables already present in ``os.environ`` are skipped (pre-existing
        environment takes priority).  The output is safe to pass to
        ``eval`` in bash::

            eval "$(python3 -m skimindex.config)"
        """
        lines = []
        for var, value in self.env_vars().items():
            if var not in os.environ:
                lines.append(f"export {var}={shlex.quote(value)}")
        return "\n".join(lines)

    def _export_env(self) -> None:
        """Export all config values as SKIMINDEX__ env vars.

        Pre-existing env vars are never overwritten.
        """
        for var, value in self.env_vars().items():
            if var not in os.environ:
                os.environ[var] = value

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _apply_logging(self) -> None:
        log_section = self._config_section("logging")
        if not log_section:
            return

        level = self.get("logging", "level", "INFO")
        setloglevel(level)

        if "file" not in log_section:
            return

        def _bool(val: str) -> bool:
            return val.lower() in ("true", "1", "yes")

        logfile = str(self.log_file())
        mirror = _bool(self.get("logging", "mirror", "false"))
        everything = _bool(self.get("logging", "everything", "false"))
        openlogfile(logfile, mirror=mirror, everything=everything)

    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"Config(path={self._path}, sections={list(self._raw.keys())})"


# ======================================================================
# Module-level singleton
# ======================================================================

_CONFIG: Config | None = None


def load(path: Path = DEFAULT_CONFIG) -> Config:
    """Load and return a Config instance."""
    return Config(path)


def config() -> Config:
    """Get the module-level singleton Config (lazy-initialized)."""
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = load()
    return _CONFIG


# ======================================================================
# Module-level path convenience functions
# ======================================================================

def root() -> Path:
    """Return the container root path (SKIMINDEX_ROOT env var, default '/')."""
    return config().root


def source_dir(name: str) -> Path:
    """Return the mount path for a named source."""
    return config().source_dir(name)


def processed_data_dir() -> Path:
    """Return the processed data root."""
    return config().processed_data_dir()


def indexes_dir() -> Path:
    """Return the indexes root."""
    return config().indexes_dir()


def stamp_dir() -> Path:
    """Return the stamp root."""
    return config().stamp_dir()


def raw_data_dir() -> Path:
    """Return the internal/raw data root (source_dir('internal'))."""
    return config().raw_data_dir()
