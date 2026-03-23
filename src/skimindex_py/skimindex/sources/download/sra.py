"""
SRA download processor — pure Python, file-based robustness.

Orchestrates SRA read downloads:
- Resolves run accessions ↔ biosample/experiment IDs via NCBI Entrez API
- Downloads .sra archives with prefetch into /scratch
- Converts to FASTQ with fasterq-dump
- Compresses to .fastq.gz with pigz into /sra/{directory}/{organism}/{biosample}/
- Cleans up scratch files

Datasets are driven by [data.X] blocks with source = "sra".
Uses stamp files for robustness: if interrupted, relaunching skips completed steps.

Accession types supported in `accessions` list (detected by prefix):
  SRR / ERR / DRR  — run accession  → direct metadata fetch
  SRX / ERX / DRX  — experiment     → all associated runs fetched
  (biosamples are handled via the separate `biosamples` config key)

Entrez API used:
  efetch runinfo CSV  — run/experiment → biosample + organism + layout
  esearch + efetch    — biosample/experiment → list of run accessions
"""

import csv
import functools
import io
import shutil
import urllib.request
from pathlib import Path
from typing import Any

from skimindex.datasets import dataset_config, datasets_for_source
from skimindex.log import logerror, loginfo, logwarning
from skimindex.sources.sra import (
    biosample_dir,
    run_output_paths,
    scratch_run_dir,
)
from skimindex.stamp import is_stamped, needs_run, stamp, unstamp
from skimindex.unix.compress import pigz
from skimindex.unix.sra import fasterq_dump_run, prefetch_run


# ---------------------------------------------------------------------------
# Entrez API helpers
# ---------------------------------------------------------------------------

_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _fetch_url(url: str) -> str:
    """Fetch a URL and return the response body as text."""
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read().decode("utf-8")


def _parse_runinfo_csv(text: str) -> list[dict[str, str]]:
    """Parse the NCBI SRA runinfo CSV format into a list of row dicts."""
    reader = csv.DictReader(io.StringIO(text))
    return [row for row in reader if row.get("Run")]


@functools.lru_cache(maxsize=None)
def fetch_run_metadata(run: str) -> dict[str, str]:
    """Fetch metadata for a single SRA run accession.

    Returns a dict with keys: Run, BioSample, ScientificName, LibraryLayout.
    Returns an empty dict on failure.
    """
    url = (
        f"{_EUTILS}/efetch.fcgi"
        f"?db=sra&id={run}&rettype=runinfo&retmode=text"
    )
    try:
        text = _fetch_url(url)
        rows = _parse_runinfo_csv(text)
        if rows:
            row = rows[0]
            return {
                "Run":            row.get("Run", run),
                "BioSample":      row.get("BioSample", ""),
                "ScientificName": row.get("ScientificName", row.get("Organism", "")),
                "LibraryLayout":  row.get("LibraryLayout", "SINGLE").upper(),
            }
    except Exception as e:
        logerror(f"[{run}] Failed to fetch run metadata: {e}")
    return {}


@functools.lru_cache(maxsize=None)
def fetch_biosample_runs(biosample: str) -> list[dict[str, str]]:
    """Fetch all SRA runs associated with a biosample accession.

    Returns a list of metadata dicts (same format as fetch_run_metadata).
    Returns an empty list on failure.
    """
    import json

    try:
        search_url = (
            f"{_EUTILS}/esearch.fcgi"
            f"?db=sra&term={biosample}&retmode=json&retmax=200"
        )
        search_text = _fetch_url(search_url)
        ids = json.loads(search_text).get("esearchresult", {}).get("idlist", [])
        if not ids:
            logwarning(f"[{biosample}] No SRA records found")
            return []

        uid_str = ",".join(ids)
        fetch_url = (
            f"{_EUTILS}/efetch.fcgi"
            f"?db=sra&id={uid_str}&rettype=runinfo&retmode=text"
        )
        text = _fetch_url(fetch_url)
        rows = _parse_runinfo_csv(text)
        return [
            {
                "Run":            row["Run"],
                "BioSample":      row.get("BioSample", biosample),
                "ScientificName": row.get("ScientificName", row.get("Organism", "")),
                "LibraryLayout":  row.get("LibraryLayout", "SINGLE").upper(),
            }
            for row in rows
            if row.get("Run")
        ]
    except Exception as e:
        logerror(f"[{biosample}] Failed to fetch biosample runs: {e}")
        return []


# ---------------------------------------------------------------------------
# Accession resolution
# ---------------------------------------------------------------------------

_RUN_PREFIXES = ("SRR", "ERR", "DRR")
_EXPERIMENT_PREFIXES = ("SRX", "ERX", "DRX")


def _is_run(accession: str) -> bool:
    return accession.upper().startswith(_RUN_PREFIXES)


def _is_experiment(accession: str) -> bool:
    return accession.upper().startswith(_EXPERIMENT_PREFIXES)


def resolve_dataset_runs(dataset_name: str) -> list[dict[str, str]]:
    """Resolve all runs for a dataset from its accessions + biosamples config.

    `accessions` may contain:
      - Run accessions (SRR/ERR/DRR) — biosample and organism looked up directly
      - Experiment accessions (SRX/ERX/DRX) — all associated runs discovered

    `biosamples` may contain biosample IDs (SAMEA/ERS/SRS) — all associated
    runs discovered.

    Returns deduplicated list of metadata dicts.
    """
    ds = dataset_config(dataset_name)
    accessions: list[str]    = ds.get("accessions", []) or []
    biosample_ids: list[str] = ds.get("biosamples", []) or []

    seen: set[str] = set()
    results: list[dict[str, str]] = []

    for acc in accessions:
        if _is_experiment(acc):
            loginfo(f"[{dataset_name}] Resolving experiment {acc}...")
            for meta in fetch_biosample_runs(acc):
                run = meta["Run"]
                if run not in seen:
                    seen.add(run)
                    results.append(meta)
        elif _is_run(acc):
            if acc in seen:
                continue
            meta = fetch_run_metadata(acc)
            if meta:
                seen.add(acc)
                results.append(meta)
            else:
                logwarning(f"[{dataset_name}] Could not resolve metadata for run {acc}")
        else:
            logwarning(
                f"[{dataset_name}] Unrecognised accession prefix: {acc!r} "
                f"(expected SRR/ERR/DRR for runs or SRX/ERX/DRX for experiments)"
            )

    for biosample in biosample_ids:
        for meta in fetch_biosample_runs(biosample):
            run = meta["Run"]
            if run not in seen:
                seen.add(run)
                results.append(meta)

    loginfo(f"[{dataset_name}] Resolved {len(results)} run(s)")
    return results


# ---------------------------------------------------------------------------
# Per-step functions
# ---------------------------------------------------------------------------

def _prefetch_run(run: str, scratch: Path, stamp_key: Path) -> bool:
    """Download .sra archive for *run* into scratch. Skip if stamped and file present."""
    if is_stamped(stamp_key):
        sra_candidates = list(scratch.glob(f"**/{run}.sra"))
        if sra_candidates:
            loginfo(f"    [{run}] Already downloaded (stamp exists)")
            return True
        logwarning(f"    [{run}] Stamp exists but .sra file missing — re-downloading")
        unstamp(stamp_key)
    # Remove stale lock files left by a previously interrupted prefetch
    for lock in scratch.glob("*.sra.lock"):
        loginfo(f"    [{run}] Removing stale lock: {lock.name}")
        lock.unlink(missing_ok=True)
    try:
        loginfo(f"    [{run}] Downloading with prefetch...")
        scratch.mkdir(parents=True, exist_ok=True)
        prefetch_run(run, str(scratch.parent))()
        stamp(stamp_key)
        loginfo(f"    [{run}] Download complete")
        return True
    except Exception as e:
        logerror(f"    [{run}] prefetch failed: {e}")
        shutil.rmtree(scratch, ignore_errors=True)
        return False


def _fasterq_dump_run(run: str, scratch: Path, stamp_key: Path, threads: int) -> bool:
    """Convert .sra archive to FASTQ files. Skip if stamped."""
    if is_stamped(stamp_key):
        loginfo(f"    [{run}] Already converted (stamp exists)")
        return True
    sra_file = scratch / f"{run}.sra"
    if not sra_file.exists():
        # prefetch may store it in a subdirectory
        candidates = list(scratch.glob(f"**/{run}.sra"))
        if not candidates:
            logerror(f"    [{run}] .sra file not found in {scratch}")
            return False
        sra_file = candidates[0]
    try:
        loginfo(f"    [{run}] Converting with fasterq-dump (threads={threads})...")
        fasterq_dump_run(str(sra_file), str(scratch), threads=threads)()
        stamp(stamp_key)
        loginfo(f"    [{run}] Conversion complete")
        return True
    except Exception as e:
        logerror(f"    [{run}] fasterq-dump failed: {e}")
        unstamp(stamp_key)
        return False


def _compress_run(
    run: str,
    scratch: Path,
    output_paths: list[Path],
    paired: bool,
) -> bool:
    """Compress FASTQ files to .fastq.gz in the final output directory."""
    if is_stamped(output_paths[-1]):
        loginfo(f"    [{run}] Already compressed (stamp exists)")
        return True

    fastq_files: list[Path]
    if paired:
        fastq_files = [scratch / f"{run}_1.fastq", scratch / f"{run}_2.fastq"]
    else:
        fastq_files = [scratch / f"{run}.fastq"]

    missing = [f for f in fastq_files if not f.exists()]
    if missing:
        logerror(f"    [{run}] FASTQ not found: {missing}")
        return False

    try:
        loginfo(f"    [{run}] Compressing {len(fastq_files)} file(s) with pigz...")
        for fastq, out in zip(fastq_files, output_paths):
            out.parent.mkdir(parents=True, exist_ok=True)
            pigz("-f", "-k", str(fastq))()
            gz = Path(str(fastq) + ".gz")
            shutil.move(str(gz), out)
        stamp(output_paths[-1])
        loginfo(f"    [{run}] Compression complete")
        return True
    except Exception as e:
        logerror(f"    [{run}] Compression failed: {e}")
        for out in output_paths:
            out.unlink(missing_ok=True)
            unstamp(out)
        return False


# ---------------------------------------------------------------------------
# Dataset processor
# ---------------------------------------------------------------------------

def process_sra_dataset(
    dataset_name: str,
    dry_run: bool = False,
) -> bool:
    """Download and process a single SRA dataset, run by run.

    Returns True on success, False if any run failed.
    """
    loginfo(f"===== Processing SRA dataset: {dataset_name} =====")

    ds = dataset_config(dataset_name)
    threads = int(ds.get("threads", 4))

    runs = resolve_dataset_runs(dataset_name)
    if not runs:
        logwarning(f"[{dataset_name}] No runs resolved — check accessions/biosamples in config")
        return True

    errors = 0
    total = len(runs)

    for i, meta in enumerate(runs, 1):
        run       = meta["Run"]
        biosample = meta["BioSample"]
        organism  = meta["ScientificName"] or "unknown"
        paired    = meta["LibraryLayout"] == "PAIRED"

        loginfo(f"[{dataset_name}] [{i}/{total}] {run} — {organism} ({biosample})")

        out_paths = run_output_paths(dataset_name, organism, biosample, run, paired)
        scratch   = scratch_run_dir(run)

        # All output files already present and stamped → skip
        if not needs_run(out_paths[-1], dry_run=dry_run,
                         label=run, action=f"download+convert+compress {run}"):
            continue

        if dry_run:
            loginfo(f"    [{run}] Would download → {out_paths}")
            continue

        # Virtual stamp keys for intermediate steps — anchored in the data tree
        # so _stamp_path() mirrors them correctly under /stamp/ (no double nesting)
        bs_dir     = out_paths[-1].parent
        dl_stamp   = bs_dir / f"{run}.download"
        conv_stamp = bs_dir / f"{run}.convert"

        ok = _prefetch_run(run, scratch, dl_stamp)
        if ok:
            ok = _fasterq_dump_run(run, scratch, conv_stamp, threads)
        if ok:
            ok = _compress_run(run, scratch, out_paths, paired)

        # Always clean up scratch regardless of success
        shutil.rmtree(scratch, ignore_errors=True)

        if not ok:
            errors += 1

    if errors:
        logerror(f"[{dataset_name}] {errors}/{total} run(s) failed")
        return False

    loginfo(f"[{dataset_name}] ✓ All {total} runs processed successfully")
    return True


def list_datasets() -> str:
    """List SRA dataset names as CSV from config."""
    names = datasets_for_source("sra")
    return ",".join(names) if names else ""


def process_sra(
    dataset_names: list[str] | None = None,
    dry_run: bool = False,
) -> int:
    """Main entry point: process SRA datasets.

    Returns 0 on success, 1 if any dataset failed.
    """
    if dataset_names is None:
        dataset_names = datasets_for_source("sra")

    if not dataset_names:
        logwarning('No SRA datasets configured (no [data.X] with source = "sra")')
        return 0

    loginfo(f"Processing {len(dataset_names)} SRA dataset(s)")

    errors = 0
    for name in dataset_names:
        if not process_sra_dataset(name, dry_run=dry_run):
            errors += 1

    if errors:
        logerror(f"===== {errors} SRA dataset(s) failed =====")
        return 1

    loginfo("===== All SRA datasets processed successfully =====")
    return 0
