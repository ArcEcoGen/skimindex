"""
GenBank download module using doit.

Orchestrates GenBank data downloads and processing:
- Downloads GenBank release number
- Caches FTP directory listing
- Identifies available divisions (bct, pln, pri, etc.)
- Downloads individual GenBank files
- Converts GBFF to FASTA format
- Downloads NCBI taxonomy

Tasks are defined as generators compatible with doit task system.

Usage:
    from skimindex.download.genbank import DOIT_CONFIG, task_*
    # Use with doit command: doit -f <this_module>

Environment variables (optional):
    SKIMINDEX__GENBANK__DIVISIONS: Space-separated division list (default: "bct pln")
"""

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional, List, Dict, Any

from plumbum import local

from skimindex.config import config
from skimindex.log import loginfo, logwarning, logerror
from skimindex.unix.download import curl
from skimindex.unix.obitools import obitaxonomy, obiconvert


# doit configuration
DOIT_CONFIG = {
    "default_tasks": ["downloads"],
    "verbosity": 2,
}

# Constants
FTPNCBI = "ftp.ncbi.nlm.nih.gov"
GBURL = f"https://{FTPNCBI}/genbank"
GBRELEASE_URL = f"{GBURL}/GB_Release_Number"
TAXOURL = f"https://{FTPNCBI}/pub/taxonomy/taxdump.tar.gz"

# Get GenBank divisions from config or environment, with fallback default
GBDIV = config().get("genbank", "divisions", "bct pln").split()


@lru_cache(maxsize=1)
def _get_release_number() -> str:
    """Fetch current GenBank release number (cached)."""
    try:
        result = curl("-s", GBRELEASE_URL)()
        return result.strip()
    except Exception as e:
        logerror(f"Failed to fetch GenBank release number: {e}")
        return "unknown"


def _get_ftp_listing(release: str) -> List[str]:
    """Get list of GenBank files from FTP."""
    listing_file = f"Release_{release}/.gb_listing"

    if Path(listing_file).exists():
        loginfo(f"Using cached FTP listing: {listing_file}")
        with open(listing_file) as f:
            return f.read().splitlines()

    try:
        loginfo(f"Downloading FTP listing from {GBURL}")
        output = curl("-s", "-L", GBURL)()

        Path(listing_file).parent.mkdir(parents=True, exist_ok=True)
        with open(listing_file, "w") as f:
            f.write(output)
        loginfo(f"Cached FTP listing: {listing_file}")
        return output.splitlines()
    except Exception as e:
        logerror(f"Failed to download FTP listing: {e}")
        return []


def _filter_gb_files(listing: List[str], divisions: List[str]) -> List[str]:
    """Filter GenBank files by selected divisions."""
    div_pattern = "|".join(divisions)
    pattern = re.compile(f"gb({div_pattern})[0-9]+\\.seq\\.gz")
    return [line for line in listing if pattern.search(line)]


# Task definitions
def task_directories():
    """Create necessary directories for GenBank download."""
    release = _get_release_number()

    directories = [
        f"Release_{release}",
        f"Release_{release}/fasta",
        f"Release_{release}/fasta_fgs",
        f"Release_{release}/stamp",
        f"Release_{release}/tmp",
        f"Release_{release}/depends",
    ]

    for directory in directories:
        yield {
            "name": directory,
            "actions": [lambda d=directory: Path(d).mkdir(parents=True, exist_ok=True)],
            "targets": [directory],
            "verbosity": 2,
        }


def task_taxonomy():
    """Download NCBI taxonomy."""
    release = _get_release_number()
    output_dir = f"Release_{release}/taxonomy"
    output_file = f"{output_dir}/ncbi_taxonomy.tgz"

    def download_taxonomy():
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        with local.cwd(output_dir):
            obitaxonomy("--download-ncbi", "--out", "ncbi_taxonomy.tgz")()

    return {
        "actions": [download_taxonomy],
        "targets": [output_file],
        "verbosity": 2,
    }


def task_download_gb_files():
    """Download individual GenBank files."""
    release = _get_release_number()
    listing = _get_ftp_listing(release)
    gb_files = _filter_gb_files(listing, GBDIV)

    for gb_file in gb_files:
        stamp_file = f"Release_{release}/stamp/{gb_file}.stamp"
        tmp_file = f"Release_{release}/tmp/{gb_file}"

        def download_file(tmp=tmp_file, stamp=stamp_file, url=f"{GBURL}/{gb_file}"):
            Path(tmp).parent.mkdir(parents=True, exist_ok=True)
            Path(stamp).parent.mkdir(parents=True, exist_ok=True)
            curl("-L", "-o", tmp, url)()
            Path(stamp).touch()

        yield {
            "name": gb_file,
            "actions": [download_file],
            "targets": [stamp_file],
            "verbosity": 1,
        }


def task_convert_to_fasta():
    """Convert downloaded GenBank files to FASTA format."""
    release = _get_release_number()
    listing = _get_ftp_listing(release)
    gb_files = _filter_gb_files(listing, GBDIV)

    for gb_file in gb_files:
        div = re.match(r"^gb(...).*$", gb_file).group(1)
        stamp_file = f"Release_{release}/stamp/{gb_file}.stamp"
        tmp_file = f"Release_{release}/tmp/{gb_file}"
        fasta_file = f"Release_{release}/fasta/{div}/{gb_file.replace('.seq.gz', '.fasta.gz')}"
        fasta_tmp = f"Release_{release}/tmp/{gb_file.replace('.seq.gz', '.fasta.gz')}"

        def convert_file(tmp=tmp_file, fasta=fasta_file, fasta_t=fasta_tmp, div_path=div):
            fasta_dir = f"Release_{release}/fasta/{div_path}"
            Path(fasta_dir).mkdir(parents=True, exist_ok=True)
            try:
                output = obiconvert("-Z", "--fasta-output", "--skip-empty", tmp)()
                with open(fasta_t, "w") as f:
                    f.write(output)
                Path(fasta_t).rename(fasta)
            finally:
                Path(tmp).unlink(missing_ok=True)

        yield {
            "name": f"fasta-{gb_file}",
            "actions": [convert_file],
            "file_dep": [stamp_file],
            "targets": [fasta_file],
            "verbosity": 1,
        }


def task_downloads():
    """Main download task - orchestrate all downloads."""
    return {
        "actions": [
            lambda: loginfo(f"GenBank downloads completed for divisions: {GBDIV}")
        ],
        "task_dep": ["taxonomy"],
        "verbosity": 2,
    }


# ===== GenBank utility functions =====


def list_divisions() -> str:
    """
    List configured GenBank divisions as CSV.

    Returns:
        Comma-separated string of division codes (e.g., "bct,pln")
    """
    divisions_str = os.environ.get("SKIMINDEX__GENBANK__DIVISIONS", "bct pln")
    return divisions_str.replace(" ", ",")
