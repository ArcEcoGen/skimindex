"""
Download module for managing dataset downloads via pure doit orchestration.

Provides complete doit pipeline for GenBank and reference genome downloads.

Submodules:
  - genbank: Download and process GenBank data using doit
  - refgenome: Download and process reference genomes from NCBI using doit

Usage (doit orchestration):
    # Download GenBank + all reference genomes:
    doit -f skimindex.download

    # Download only GenBank:
    doit -f skimindex.download genbank

    # Download only reference genomes:
    doit -f skimindex.download refgenomes

    # Download single reference genome section:
    doit -f skimindex.download.refgenome compress:human

Utilities:
    # List available GenBank divisions:
    from skimindex.download.genbank import list_divisions

    # List available reference genome sections:
    from skimindex.download.refgenome import list_sections
"""

from skimindex.config import config, task_config
from skimindex.log import loginfo

from . import genbank, refgenome

__all__ = ["genbank", "refgenome"]

# Reference the singleton config for use in this module
_CONFIG = config()


# ===== doit orchestration for complete pipeline =====


DOIT_CONFIG = {
    "default_tasks": ["complete"],
    "verbosity": 2,
}


def task_genbank():
    """Orchestrate GenBank division downloads via doit."""
    return {
        "actions": [
            lambda: loginfo("===== Starting GenBank downloads ====="),
        ],
        "task_dep": [
            "config",  # Ensure config is loaded first
            *[
                f"genbank:{task}"
                for task in [
                    "directories",
                    "taxonomy",
                    "download_gb_files",
                    "convert_to_fasta",
                    "downloads",
                ]
            ],
        ],
        "verbosity": 2,
    }


def task_refgenomes():
    """Orchestrate reference genome downloads via doit."""
    return {
        "actions": [
            lambda: loginfo("===== Starting reference genome downloads ====="),
        ],
        "task_dep": [
            "config",  # Ensure config is loaded first
            "refgenome:all",
        ],
        "verbosity": 2,
    }


def task_complete():
    """Complete orchestration: GenBank + all reference genomes."""
    return {
        "actions": [
            lambda: loginfo(
                "===== All downloads (GenBank + reference genomes) completed ====="
            ),
        ],
        "task_dep": ["genbank", "refgenomes"],
        "verbosity": 2,
    }
