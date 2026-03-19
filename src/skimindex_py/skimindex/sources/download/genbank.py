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

from skimindex.config import config
from skimindex.log import logerror, loginfo, logwarning
from skimindex.sources import genbank as gb_source
from skimindex.stamp import needs_run, stamp
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
    divisions = config().sources.get("genbank", {}).get("divisions", [])
    return ",".join(divisions) if divisions else ""


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


def get_ftp_listing(divisions: list[str]) -> tuple:
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


def download_and_process_genbank(release: str, divisions: list[str], dry_run: bool = False) -> bool:
    """Download and convert GenBank files, grouped by division.

    Args:
        release: GenBank release number
        divisions: List of divisions to process
        dry_run: If True, show what would be done without executing

    Returns:
        True on success, False if any files failed.
    """
    gb_files = get_ftp_listing(divisions)
    if not gb_files:
        logwarning(f"No GenBank files found for divisions: {', '.join(divisions)}")
        return True

    loginfo(f"Processing {len(gb_files)} GenBank files for divisions: {', '.join(divisions)}")

    tmp_dir = gb_source.release_dir(release) / "tmp"
    if not dry_run:
        (gb_source.release_dir(release) / "fasta").mkdir(parents=True, exist_ok=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)

    # Group files by division
    division_groups: dict[str, list[str]] = {}
    for gb_file in gb_files:
        div = re.match(r"^gb(...).*$", gb_file).group(1)
        if div not in division_groups:
            division_groups[div] = []
        division_groups[div].append(gb_file)

    errors = 0
    failed_files = []
    total_files = len(gb_files)
    file_counter = 0

    for div in sorted(division_groups.keys()):
        div_files = division_groups[div]
        loginfo(f"Division [{div}] : {len(div_files)} file(s)")

        for gb_file in div_files:
            file_counter += 1
            loginfo(f"  [{file_counter}/{total_files}] {gb_file}")

            fasta_dir = gb_source.division_dir(release, div)
            fasta_file = fasta_dir / gb_file.replace(".seq.gz", ".fasta.gz")

            if not needs_run(fasta_file, dry_run=dry_run,
                             label=gb_file, action=f"download and convert {gb_file}"):
                continue

            try:
                tmp_file = tmp_dir / gb_file.replace(".seq.gz", ".fasta.gz")

                fasta_dir.mkdir(parents=True, exist_ok=True)

                loginfo(f"    Downloading and converting to FASTA...")

                curl_cmd = curl_download(f"{GBURL}/{gb_file}")
                convert_cmd = obiconvert(
                    "--batch-size", "1", "-Z", "--fasta-output", "--skip-empty"
                )

                ((curl_cmd | convert_cmd) > str(tmp_file))()

                tmp_file.rename(fasta_file)
                loginfo(f"    Saved to {fasta_file}")
            except Exception as e:
                logerror(f"    Failed to download/convert {gb_file}: {e}")
                tmp_file.unlink(missing_ok=True)
                failed_files.append((gb_file, str(e)))
                errors += 1
                continue

            stamp(fasta_file)

    shutil.rmtree(tmp_dir, ignore_errors=True)

    if errors > 0:
        logwarning(f"===== Summary: {errors} error(s) =====")
        for gb_file, error in failed_files:
            logwarning(f"  {gb_file}: {error}")
        logerror(f"Completed with {errors} error(s). Re-run to retry.")
        return False

    loginfo(f"✓ All {total_files} files processed successfully")
    return True


def download_taxonomy(release: str, dry_run: bool = False) -> bool:
    """Download NCBI taxonomy."""
    output_file = gb_source.taxonomy(release)
    output_dir = output_file.parent

    if output_file.exists():
        try:
            pigz_test(str(output_file))()
            loginfo(f"Taxonomy already downloaded: {output_file}")
            return True
        except Exception:
            logwarning(f"Taxonomy file corrupted: {output_file}, re-downloading...")
            output_file.unlink(missing_ok=True)

    if dry_run:
        loginfo(f"WOULD download NCBI taxonomy → {output_file}")
        return True

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


def process_genbank(divisions: list[str] | None = None, dry_run: bool = False) -> int:
    """Main entry point: download release, taxonomy, and process GenBank files.

    Args:
        divisions: List of GenBank divisions to download (e.g., ['bct', 'pln']).
                  If None, uses divisions from [source.genbank].divisions in config.
        dry_run: If True, show what would be done without executing.

    Returns:
        0 on success, 1 on failure.
    """
    if divisions is None:
        divisions = config().sources.get("genbank", {}).get("divisions", [])

    if not divisions:
        logwarning("No GenBank divisions configured in [source.genbank].divisions")
        return 0

    loginfo(f"===== GenBank download pipeline =====")
    loginfo(f"Divisions: {', '.join(divisions)}")

    loginfo(">>> Step 1: Fetching GenBank release number")
    release = get_release_number()
    if release == "unknown":
        logerror("Step 1 failed — unable to get release number")
        return 1
    loginfo(f"<<< Step 1 OK (Release {release})")

    loginfo(">>> Step 2: Downloading NCBI taxonomy")
    if not download_taxonomy(release, dry_run=dry_run):
        logerror("Step 2 failed")
        return 1
    loginfo("<<< Step 2 OK")

    loginfo(f">>> Step 3: Downloading and processing {len(divisions)} division(s)")
    if not download_and_process_genbank(release, divisions, dry_run=dry_run):
        logerror("Step 3 failed")
        return 1
    loginfo("<<< Step 3 OK")

    loginfo("===== GenBank download complete =====")
    return 0
