"""
Download status inspection — no network calls.

Inspects local directories to report what has been downloaded and stamped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skimindex.config import config
from skimindex.datasets import datasets_for_source
from skimindex.sources import dataset_download_dir, source_dir
from skimindex.stamp import is_stamped


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DivisionStatus:
    name: str
    files_total: int
    files_stamped: int

    @property
    def complete(self) -> bool:
        return self.files_total > 0 and self.files_stamped == self.files_total


@dataclass
class GenBankStatus:
    configured_divisions: list[str]
    releases_on_disk: list[str]          # e.g. ["Release_261"]
    current_release: str | None          # most recent release found
    divisions: list[DivisionStatus]
    taxonomy_present: bool

    @property
    def complete(self) -> bool:
        return bool(self.current_release) and all(d.complete for d in self.divisions)


@dataclass
class DatasetStatus:
    name: str
    source: str
    output_dir: Path
    files_present: int
    files_stamped: int

    @property
    def complete(self) -> bool:
        return self.files_present > 0 and self.files_stamped == self.files_present

    @property
    def started(self) -> bool:
        return self.files_present > 0


@dataclass
class DownloadStatus:
    genbank: GenBankStatus
    ncbi: list[DatasetStatus]

    @property
    def complete(self) -> bool:
        return self.genbank.complete and all(d.complete for d in self.ncbi)


# ---------------------------------------------------------------------------
# GenBank inspection
# ---------------------------------------------------------------------------

def genbank_status() -> GenBankStatus:
    """Inspect GenBank download status from local disk (no network calls)."""
    gb_root = source_dir("genbank")
    configured_divisions = config().sources.get("genbank", {}).get("divisions", [])

    # Find Release_* directories
    releases = []
    if gb_root.exists():
        releases = sorted(
            [p.name for p in gb_root.iterdir() if p.is_dir() and p.name.startswith("Release_")],
            key=lambda n: float(n.split("_")[1]) if "_" in n else 0,
        )
    current_release = releases[-1] if releases else None

    # Per-division file counts in the current release
    division_statuses = []
    if current_release:
        fasta_root = gb_root / current_release / "fasta"
        for div in configured_divisions:
            div_dir = fasta_root / div
            if div_dir.exists():
                files = list(div_dir.glob("*.fasta.gz"))
                stamped = sum(1 for f in files if is_stamped(f))
                division_statuses.append(DivisionStatus(div, len(files), stamped))
            else:
                division_statuses.append(DivisionStatus(div, 0, 0))
    else:
        division_statuses = [DivisionStatus(div, 0, 0) for div in configured_divisions]

    # Taxonomy
    taxonomy_present = False
    if current_release:
        taxonomy_file = gb_root / current_release / "taxonomy" / "ncbi_taxonomy.tgz"
        taxonomy_present = taxonomy_file.exists()

    return GenBankStatus(
        configured_divisions=configured_divisions,
        releases_on_disk=releases,
        current_release=current_release,
        divisions=division_statuses,
        taxonomy_present=taxonomy_present,
    )


# ---------------------------------------------------------------------------
# NCBI inspection
# ---------------------------------------------------------------------------

def ncbi_dataset_status(dataset_name: str) -> DatasetStatus:
    """Inspect download status for a single NCBI dataset."""
    output_dir = dataset_download_dir(dataset_name)
    ds_cfg = config().datasets.get(dataset_name, {})
    source = ds_cfg.get("source", "ncbi")

    if not output_dir.exists():
        return DatasetStatus(dataset_name, source, output_dir, 0, 0)

    files = list(output_dir.glob("*.gbff.gz"))
    stamped = sum(1 for f in files if is_stamped(f))
    return DatasetStatus(dataset_name, source, output_dir, len(files), stamped)


def ncbi_status() -> list[DatasetStatus]:
    """Inspect download status for all configured NCBI datasets."""
    return [ncbi_dataset_status(name) for name in datasets_for_source("ncbi")]


# ---------------------------------------------------------------------------
# Combined status
# ---------------------------------------------------------------------------

def download_status() -> DownloadStatus:
    """Return combined download status for all sources (no network calls)."""
    return DownloadStatus(
        genbank=genbank_status(),
        ncbi=ncbi_status(),
    )


# ---------------------------------------------------------------------------
# Formatted output
# ---------------------------------------------------------------------------

def _ok(flag: bool) -> str:
    return "✓" if flag else "✗"


def _print_genbank_section(gb: GenBankStatus) -> None:
    print("=== GenBank ===")
    if gb.current_release:
        print(f"  Release : {gb.current_release}")
    else:
        print("  Release : not downloaded")
    print(f"  Taxonomy: {_ok(gb.taxonomy_present)}")
    if gb.divisions:
        print("  Divisions:")
        for div in gb.divisions:
            bar = f"{div.files_stamped}/{div.files_total}"
            print(f"    {_ok(div.complete)} {div.name:<6} {bar} files stamped")
    else:
        print("  Divisions: none configured")


def _print_ncbi_section(ncbi: list[DatasetStatus]) -> None:
    print("=== NCBI datasets ===")
    if ncbi:
        for ds in ncbi:
            bar = f"{ds.files_stamped}/{ds.files_present}"
            label = _ok(ds.complete) if ds.started else "-"
            print(f"  {label} {ds.name:<20} {bar} assemblies  ({ds.output_dir})")
    else:
        print("  No NCBI datasets configured.")


def print_genbank_status(status: GenBankStatus | None = None) -> None:
    """Print GenBank-only download status."""
    if status is None:
        status = genbank_status()
    _print_genbank_section(status)
    print()
    overall = "complete" if status.complete else "incomplete"
    print(f"Overall: {overall}")


def print_ncbi_status(statuses: list[DatasetStatus] | None = None) -> None:
    """Print NCBI-only download status."""
    if statuses is None:
        statuses = ncbi_status()
    _print_ncbi_section(statuses)
    print()
    overall = "complete" if all(d.complete for d in statuses) else "incomplete"
    print(f"Overall: {overall}")


def print_status(status: DownloadStatus | None = None) -> None:
    """Print a human-readable download status report to stdout."""
    if status is None:
        status = download_status()

    _print_genbank_section(status.genbank)
    print()
    _print_ncbi_section(status.ncbi)
    print()
    overall = "complete" if status.complete else "incomplete"
    print(f"Overall: {overall}")
