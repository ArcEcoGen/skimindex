"""
Fragment splitting for decontamination index building.

Registers three atomic processing types:
  split         — obiscript(splitseqs.lua)       STREAM
  filter_n_only — obigrep(-v -s '^[n]+$')        STREAM
  distribute    — obidistribute(-Z -n N -p ...)  DIRECTORY

The TOML composite [processing.split_decontam] chains these three
via its 'steps' list and is executed by processing.build().

Public entry points
-------------------
list_sections()     → CSV of dataset names with role="decontamination"
process_split(...)  → run split_decontam on one or all datasets (returns 0/1)
"""

from pathlib import Path

from skimindex.config import config
from skimindex.datasets import datasets_for_role, dataset_config
from skimindex.log import logerror, loginfo, logwarning
from typing import Callable
from skimindex.processing.data import Data, DataKind, files_data, stream_data
from skimindex.processing.distribute import distribute      # noqa: F401 — triggers registration
from skimindex.processing.filter_n_only import filter_n_only  # noqa: F401 — triggers registration
from skimindex.processing.filter_taxid import filter_taxid    # noqa: F401 — triggers registration
from skimindex.processing.split import split                  # noqa: F401 — triggers registration
from skimindex.sources import dataset_download_dir, dataset_output_dir
from skimindex.stamp import needs_run, remove_if_not_stamped, stamp


# ---------------------------------------------------------------------------
# Helper — resolve split_decontam config
# ---------------------------------------------------------------------------

def _split_output_subdir() -> str:
    """Return the output subdirectory name from [processing.split_decontam]."""
    return config().processing.get("split_decontam", {}).get("directory", "split_decontam")


# ---------------------------------------------------------------------------
# Per-dataset split logic
# ---------------------------------------------------------------------------

def _split_genome_file(f: Path, genome_output_dir: Path, pipeline, dry_run: bool) -> bool:
    """Split a single genome file into fragments."""
    parts = f.name.split(".")
    genome_key = ".".join(parts[:-2]) if len(parts) > 2 else f.stem

    parts_dir = genome_output_dir / genome_key / _split_output_subdir()

    if not needs_run(parts_dir, f, dry_run=dry_run,
                     label=genome_key, action=f"split {f.name}"):
        return True

    loginfo(f"  [{genome_key}] Splitting...")
    remove_if_not_stamped(parts_dir)

    input_data = files_data(f, format=f.suffix.lstrip("."))
    if not pipeline(input_data, parts_dir, dry_run=dry_run):
        logerror(f"  [{genome_key}] Pipeline failed")
        return False

    stamp(parts_dir)
    return True


def _split_taxon_dataset(dataset_name: str, pipeline, dry_run: bool) -> bool:
    """Split a taxon-based dataset (per-genome FASTA/GBFF files)."""
    input_dir = dataset_download_dir(dataset_name)
    output_dir = dataset_output_dir(dataset_name)

    loginfo(f"Dataset       : {dataset_name} (taxon-based, per-genome)")
    loginfo(f"Input dir     : {input_dir}")

    if not input_dir.exists():
        logwarning(f"Input directory not found: {input_dir}")
        return True

    from skimindex.sequences import list_sequence_files
    input_files = list_sequence_files(input_dir, mode="absolute")
    if not input_files:
        logwarning(f"No sequence files found in {input_dir}")
        return True

    loginfo(f"Processing {len(input_files)} genome(s)...")
    errors = 0
    for f in input_files:
        if not _split_genome_file(f, output_dir, pipeline, dry_run):
            errors += 1
    return errors == 0


def _split_division_dataset(dataset_name: str, pipeline, dry_run: bool) -> bool:
    """Split a GenBank division dataset (filtered by taxid from flat files)."""
    from skimindex.decontamination.sections import genbank_base, latest_release

    ds = dataset_config(dataset_name)
    taxid     = ds.get("taxid")
    divisions = ds.get("divisions", [])

    if not taxid or not divisions:
        logerror(f"Dataset [{dataset_name}]: missing 'taxid' or 'divisions' in config")
        return False

    loginfo(f"Dataset       : {dataset_name} (division-based, per-division)")
    loginfo(f"TaxID         : {taxid}")
    loginfo(f"Divisions     : {divisions}")

    release_dir = latest_release(genbank_base())
    if not release_dir:
        logerror(f"No GenBank release directory found")
        return False

    taxonomy = release_dir / "taxonomy" / "ncbi_taxonomy.tgz"
    if not taxonomy.exists():
        logerror(f"Taxonomy file not found: {taxonomy}")
        return False

    loginfo(f"Taxonomy      : {taxonomy}")

    output_base = dataset_output_dir(dataset_name)
    subdir      = _split_output_subdir()
    errors = 0

    for div in divisions:
        div_dir = release_dir / "fasta" / div
        if not div_dir.exists():
            logwarning(f"Division directory not found: {div_dir}")
            continue

        parts_dir = output_base / div / subdir

        if not needs_run(parts_dir, taxonomy, div_dir,
                         dry_run=dry_run, label=div, action=f"split {div_dir}"):
            continue

        loginfo(f"  [{div}] Splitting...")
        remove_if_not_stamped(parts_dir)

        input_cmd = obigrep(
            "-t", str(taxonomy),
            "-r", str(taxid),
            "--no-order", "--update-taxid",
            str(div_dir),
        )
        input_data = stream_data(input_cmd, format="fasta")
        if not pipeline(input_data, parts_dir, dry_run=dry_run):
            logerror(f"  [{div}] Pipeline failed")
            errors += 1
            continue

        stamp(parts_dir)

    return errors == 0


def _split_dataset(dataset_name: str, pipeline, dry_run: bool) -> bool:
    """Dispatch to taxon or division split handler."""
    ds = dataset_config(dataset_name)
    if ds.get("source") == "ncbi":
        return _split_taxon_dataset(dataset_name, pipeline, dry_run)
    return _split_division_dataset(dataset_name, pipeline, dry_run)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_sections() -> str:
    """List dataset names with role='decontamination' as CSV."""
    return ",".join(datasets_for_role("decontamination"))


def process_split(
    sections: list[str] | None = None,
    dry_run: bool = False,
) -> int:
    """Run split_decontam on one or all decontamination datasets.

    Args:
        sections: Dataset names to process. None → all decontamination datasets.
        dry_run:  If True, show what would be done without executing.

    Returns:
        0 on success, 1 if any dataset failed.
    """
    from skimindex.processing import build

    if sections is None:
        sections = datasets_for_role("decontamination")

    if not sections:
        logwarning("No decontamination datasets configured")
        return 0

    # Build the pipeline once — shared across all datasets
    pipeline = build("split_decontam")

    loginfo(f"===== Split pipeline =====" + (" [DRY-RUN]" if dry_run else ""))
    loginfo(f"Processing {len(sections)} dataset(s)")

    errors = 0
    for dataset_name in sections:
        loginfo(f">>> Splitting: {dataset_name}")
        if _split_dataset(dataset_name, pipeline, dry_run=dry_run):
            loginfo(f"<<< {dataset_name} OK")
        else:
            logerror(f"<<< {dataset_name} FAILED")
            errors += 1

    if errors:
        logerror(f"===== {errors} dataset(s) failed =====")
        return 1

    loginfo("===== All datasets split successfully =====")
    return 0
