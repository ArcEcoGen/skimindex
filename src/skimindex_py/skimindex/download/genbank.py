"""
GenBank download processor — pure Python, file-based robustness.

Orchestrates GenBank data downloads and processing:
- Downloads and caches GenBank release number
- Downloads FTP directory listing (fresh each run to catch updates)
- Downloads individual GenBank files
- Converts GBFF to FASTA format
- Downloads NCBI taxonomy

Uses stamp files for robustness: if interrupted, relaunching skips already-processed files.
"""

import os
import re
import shutil
from functools import lru_cache
from pathlib import Path
from typing import List

from skimindex.config import config
from skimindex.log import logerror, loginfo, logwarning
from skimindex.unix.compress import pigz_test
from skimindex.unix.download import curl_download
from skimindex.unix.obitools import obiconvert, obitaxonomy

# Constants
FTPNCBI = "ftp.ncbi.nlm.nih.gov"
GBURL = f"https://{FTPNCBI}/genbank"
GBRELEASE_URL = f"{GBURL}/GB_Release_Number"
TAXOURL = f"https://{FTPNCBI}/pub/taxonomy/taxdump.tar.gz"


def list_divisions() -> str:
    """List available GenBank divisions as CSV from config."""
    cfg = config()
    divisions = cfg.get("genbank", "divisions", "bct pln").split()
    return ",".join(divisions) if divisions else ""


def _get_genbank_base() -> Path:
    """Get the base GenBank directory from config."""
    cfg = config()
    return Path(cfg.get("directories", "genbank", "/genbank"))


@lru_cache(maxsize=1)
def get_release_number() -> str:
    """Fetch GenBank release number (cached in memory during program execution)."""
    try:
        result = curl_download(GBRELEASE_URL)()
        release = result.strip()
        loginfo(f"GenBank release number: {release}")
        return release
    except Exception as e:
        logerror(f"Failed to fetch GenBank release number: {e}")
        return "unknown"


def get_ftp_listing(divisions: List[str]) -> tuple:
    """Download and parse FTP listing to get GenBank filenames.

    Args:
        divisions: List of GenBank divisions to filter (e.g., ['bct', 'pln'])

    Returns:
        Tuple of filenames matching selected divisions.
        Always fetches fresh listing on each program run to catch GenBank updates.
    """
    try:
        loginfo(f"Downloading FTP listing from {GBURL}")
        output = curl_download(GBURL)()

        # Parse: extract filenames matching the pattern for selected divisions
        div_pattern = "|".join(divisions)
        pattern = re.compile(f"gb({div_pattern})[0-9]+\\.seq\\.gz")

        filenames = []
        for line in output.splitlines():
            match = pattern.search(line)
            if match:
                filenames.append(match.group(0))

        loginfo(
            f"Found {len(filenames)} GenBank files for divisions: {', '.join(divisions)}"
        )
        return tuple(filenames)
    except Exception as e:
        logerror(f"Failed to download FTP listing: {e}")
        return ()


def download_and_process_genbank(release: str, divisions: List[str]) -> bool:
    """Download and convert GenBank files, one by one, robustly.

    Args:
        release: GenBank release number
        divisions: List of divisions to process

    Returns:
        True on success, False if any files failed.
    """
    genbank_base = _get_genbank_base()

    # Get listing (parse and filter by division)
    gb_files = get_ftp_listing(divisions)
    if not gb_files:
        logwarning(f"No GenBank files found for divisions: {', '.join(divisions)}")
        return True

    loginfo(
        f"Processing {len(gb_files)} GenBank files for divisions: {', '.join(divisions)}"
    )

    # Create directories
    (genbank_base / f"Release_{release}/stamp").mkdir(parents=True, exist_ok=True)
    (genbank_base / f"Release_{release}/fasta").mkdir(parents=True, exist_ok=True)
    (genbank_base / f"Release_{release}/tmp").mkdir(parents=True, exist_ok=True)

    # Process each file
    errors = 0
    failed_files = []
    for i, gb_file in enumerate(gb_files, 1):
        loginfo(f"[{i}/{len(gb_files)}] Processing {gb_file}")

        stamp_file = genbank_base / f"Release_{release}/stamp/{gb_file}.stamp"

        # Skip if already processed
        if stamp_file.exists():
            loginfo(f"  Already processed (stamp exists)")
            continue

        # Download and convert in one pipe: curl | obiconvert > tmp file, then move to final location
        try:
            div = re.match(r"^gb(...).*$", gb_file).group(1)
            fasta_dir = genbank_base / f"Release_{release}/fasta/{div}"
            fasta_file = fasta_dir / gb_file.replace(".seq.gz", ".fasta.gz")

            # Temporary file in tmp/ — atomic move on success
            tmp_file = (
                genbank_base
                / f"Release_{release}/tmp"
                / gb_file.replace(".seq.gz", ".fasta.gz")
            )

            fasta_dir.mkdir(parents=True, exist_ok=True)

            loginfo(f"  Downloading and converting to FASTA...")

            # Pipe: curl downloads -> obiconvert converts -> redirect to tmp file
            curl_cmd = curl_download(f"{GBURL}/{gb_file}")
            convert_cmd = obiconvert(
                "--batch-size", "1", "-Z", "--fasta-output", "--skip-empty"
            )

            ((curl_cmd | convert_cmd) > str(tmp_file))()

            # Atomic move from tmp to final location
            tmp_file.rename(fasta_file)

            loginfo(f"  Saved to {fasta_file}")
        except Exception as e:
            logerror(f"  Failed to download/convert {gb_file}: {e}")
            # Clean up partial tmp file
            tmp_file.unlink(missing_ok=True)
            failed_files.append((gb_file, str(e)))
            errors += 1
            continue

        # Mark as processed
        stamp_file.touch()

    # Clean up tmp directory
    tmp_dir = genbank_base / f"Release_{release}/tmp"
    shutil.rmtree(tmp_dir, ignore_errors=True)

    if errors > 0:
        logwarning(f"===== Summary: {errors} error(s) =====")
        for gb_file, error in failed_files:
            logwarning(f"  {gb_file}: {error}")
        logerror(f"Completed with {errors} error(s). Re-run to retry.")
        return False

    loginfo(f"✓ All {len(gb_files)} files processed successfully")
    return True


def download_taxonomy(release: str) -> bool:
    """Download NCBI taxonomy."""
    genbank_base = _get_genbank_base()
    output_dir = genbank_base / f"Release_{release}/taxonomy"
    output_file = output_dir / "ncbi_taxonomy.tgz"

    if output_file.exists():
        # Verify gzip integrity
        try:
            pigz_test(str(output_file))()
            loginfo(f"Taxonomy already downloaded: {output_file}")
            return True
        except Exception:
            logwarning(f"Taxonomy file corrupted: {output_file}, re-downloading...")
            output_file.unlink(missing_ok=True)

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        loginfo("Downloading NCBI taxonomy...")
        old_cwd = os.getcwd()
        try:
            os.chdir(str(output_dir))
            obitaxonomy("--download-ncbi", "--out", "ncbi_taxonomy.tgz")()
        finally:
            os.chdir(old_cwd)
        loginfo(f"Taxonomy saved: {output_file}")
        return True
    except Exception as e:
        logerror(f"Failed to download taxonomy: {e}")
        return False


def process_genbank(divisions: List[str] = None) -> int:
    """Main entry point: download release, taxonomy, and process GenBank files.

    Args:
        divisions: List of GenBank divisions to download (e.g., ['bct', 'pln']).
                  If None, uses config default.

    Returns:
        0 on success, 1 on failure.
    """
    # Use provided divisions or fall back to config
    if divisions is None:
        cfg = config()
        divisions = cfg.get("genbank", "divisions", "bct pln").split()

    loginfo(f"===== GenBank download pipeline =====")
    loginfo(f"Divisions: {', '.join(divisions)}")

    # Step 1: Get release number
    loginfo(">>> Step 1: Fetching GenBank release number")
    release = get_release_number()
    if release == "unknown":
        logerror("Step 1 failed — unable to get release number")
        return 1
    loginfo(f"<<< Step 1 OK (Release {release})")

    # Step 2: Download taxonomy
    loginfo(">>> Step 2: Downloading NCBI taxonomy")
    if not download_taxonomy(release):
        logerror("Step 2 failed")
        return 1
    loginfo("<<< Step 2 OK")

    # Step 3: Download and process GenBank files
    loginfo(f">>> Step 3: Downloading and processing {len(divisions)} division(s)")
    if not download_and_process_genbank(release, divisions):
        logerror("Step 3 failed")
        return 1
    loginfo("<<< Step 3 OK")

    loginfo("===== GenBank download complete =====")
    return 0
