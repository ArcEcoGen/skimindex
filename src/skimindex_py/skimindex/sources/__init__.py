"""
skimindex.sources — source registry and directory helpers.

A source ([source.X] in TOML) is an external data provider with a
configured directory under SKIMINDEX_ROOT.

Usage
-----
    from skimindex.sources import (
        source_dir, dataset_download_dir,
        output_dir, dataset_output_dir,
    )

    genbank_root  = source_dir("genbank")
    human_dl_dir  = dataset_download_dir("human")
    decontam_root = output_dir("role", "decontamination")
    human_out_dir = dataset_output_dir("human")
"""

from pathlib import Path

from skimindex.config import config
from skimindex.datasets import dataset_config


def source_dir(source: str) -> Path:
    """Root directory for a named source.

    Reads [source.<name>].directory and resolves against SKIMINDEX_ROOT.

    Example:
        source_dir("genbank") → Path("/data/genbank")
        source_dir("ncbi")    → Path("/data/genbank")  # shares dir with genbank
    """
    return config().source_dir(source)


def dataset_download_dir(dataset_name: str) -> Path:
    """Download output directory for a named dataset.

    Resolves: source_dir(dataset.source) / dataset.directory
    where dataset.directory defaults to dataset_name if not set.

    Example:
        dataset_download_dir("human")       → Path("/data/genbank/human")
        dataset_download_dir("betula_nana") → Path("/data/raw_data/Betula_nana")
    """
    ds = dataset_config(dataset_name)
    source = ds.get("source", "ncbi")
    directory = ds.get("directory", dataset_name)
    return source_dir(source) / directory


def output_dir(section_kind: str, section_name: str) -> Path:
    """Processing output directory for a named config section.

    Reads the section's 'directory' key and resolves it under the
    appropriate root for the section kind:
      - "role"  → processed_data_dir() / section.directory
      - "index" → indexes_dir()        / section.directory

    Args:
        section_kind: "role" or "index"
        section_name: Name of the sub-section, e.g. "decontamination"

    Examples:
        output_dir("role", "decontamination") → /processed_data/decontamination
        output_dir("role", "genomes")         → /processed_data/genomes_15x
    """
    cfg = config()
    sections: dict = getattr(cfg, section_kind + "s", {})
    directory = sections.get(section_name, {}).get("directory", section_name)
    if section_kind == "role":
        return cfg.processed_data_dir() / directory
    if section_kind == "index":
        return cfg.indexes_dir() / directory
    raise ValueError(f"Unknown section_kind: {section_kind!r}. Expected 'role' or 'index'.")


def dataset_output_dir(dataset_name: str) -> Path:
    """Processing output directory for a dataset, resolved under its role.

    Resolves: output_dir("role", dataset.role) / dataset.directory

    Example:
        dataset_output_dir("human")  → /processed_data/decontamination/human
        dataset_output_dir("plants") → /processed_data/decontamination/Plants
    """
    ds = dataset_config(dataset_name)
    role = ds.get("role", "")
    directory = ds.get("directory", dataset_name)
    return output_dir("role", role) / directory
