"""
skimindex.sources — source registry and directory helpers.

A source ([source.X] in TOML) is an external data provider with a
configured directory under SKIMINDEX_ROOT.

Usage
-----
    from skimindex.sources import source_dir, dataset_download_dir

    genbank_root = source_dir("genbank")          # Path to genbank source root
    human_dir    = dataset_download_dir("human")  # Path to human dataset downloads
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
