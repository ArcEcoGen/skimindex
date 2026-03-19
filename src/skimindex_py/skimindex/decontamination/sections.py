"""
Directory helpers shared across skimindex pipeline modules.

Centralises the repeated config lookups for genbank/processed_data
directories and section-relative paths.

Key functions
-------------
genbank_base() -> Path
    Root GenBank directory from config (directories.genbank).

section_rel_dir(section) -> str
    Relative directory name for a section (config key or section.lower()).

section_dirs(section) -> dict | None
    Convenience: load both input (genbank) and output (processed_data)
    paths for a section in one call.  Returns None if section not in config.

latest_release(genbank_root) -> Path | None
    Find the most recent Release_* directory under *genbank_root*.
"""

from pathlib import Path
from typing import Any

from skimindex.config import config, processed_data_dir
from skimindex.log import logerror


def genbank_base() -> Path:
    """Return the root GenBank directory from config."""
    return Path(config().get("directories", "genbank", "/genbank"))


def section_rel_dir(section: str) -> str:
    """Return the relative directory name for *section*.

    Reads ``directory`` from the section's config block; falls back to
    ``section.lower()`` if not set.
    """
    section_data = config().data.get(section, {})
    return section_data.get("directory", section.lower())


def section_dirs(section: str) -> dict[str, Any] | None:
    """Load input/output directories for *section* from config.

    Returns a dict with:
        rel_dir       — relative directory name
        input_dir     — <genbank_base>/<rel_dir>
        fragments_dir — <processed_data_dir>/<rel_dir>
        section_data  — raw section dict from config

    Returns None if the section is not found in config.
    """
    cfg = config()
    section_data = cfg.data.get(section, {})

    if not section_data:
        logerror(f"Section [{section}] not found in config")
        return None

    rel_dir = section_data.get("directory", section.lower())

    return {
        "rel_dir": rel_dir,
        "input_dir": genbank_base() / rel_dir,
        "fragments_dir": processed_data_dir() / rel_dir,
        "section_data": section_data,
    }


def latest_release(genbank_root: Path) -> Path | None:
    """Find the most recent Release_* directory under *genbank_root*.

    Returns the Path to the latest release directory, or None if none found.
    """
    try:
        releases = sorted(
            genbank_root.glob("Release_*"),
            key=lambda p: float(p.name.split("_")[1]) if "_" in p.name else 0,
        )
        return releases[-1] if releases else None
    except Exception as e:
        logerror(f"Error finding release directory: {e}")
        return None
