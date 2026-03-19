"""
skimindex.datasets — enumeration and access of [data.X] config blocks.

Each dataset binds a source (ncbi, genbank, internal) to a role
(decontamination, genomes, genome_skims) with download and processing parameters.

Usage
-----
    from skimindex.datasets import datasets_for_source, dataset_config

    # All NCBI datasets configured for download
    for name in datasets_for_source("ncbi"):
        cfg = dataset_config(name)
        taxon = cfg["taxon"]
"""

from typing import Any

from skimindex.config import config


def all_datasets() -> dict[str, dict[str, Any]]:
    """Return all [data.X] sections keyed by dataset name."""
    return config().datasets


def datasets_for_source(source: str) -> list[str]:
    """Return dataset names whose source matches *source*.

    Example:
        datasets_for_source("ncbi")    → ["human", "fungi"]
        datasets_for_source("genbank") → ["bacteria"]
    """
    return [
        name for name, ds in all_datasets().items()
        if ds.get("source") == source
    ]


def datasets_for_role(role: str) -> list[str]:
    """Return dataset names whose role matches *role*.

    Example:
        datasets_for_role("decontamination") → ["human", "bacteria"]
    """
    return [
        name for name, ds in all_datasets().items()
        if ds.get("role") == role
    ]


def dataset_config(name: str) -> dict[str, Any]:
    """Return the config dict for a single dataset (empty dict if not found).

    Example:
        dataset_config("human") → {"source": "ncbi", "role": "decontamination",
                                    "taxon": "human", "example": True}
    """
    return all_datasets().get(name, {})
