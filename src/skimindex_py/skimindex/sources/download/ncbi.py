"""
NCBI reference genome download processor — pure Python, file-based robustness.

Orchestrates NCBI reference genome downloads and processing:
- Downloads genome assemblies from NCBI by taxon
- Extracts GBFF files from ZIP archives
- Compresses per-accession: {scientific_name}-{accession}.gbff.gz

Datasets are driven by [data.X] blocks with source = "ncbi".
Uses stamp files for robustness: if interrupted, relaunching skips already-processed steps.
"""

import functools
import json
import re
import shutil
from pathlib import Path
from typing import Any

from skimindex.config import config
from skimindex.datasets import dataset_config, datasets_for_source
from skimindex.log import logerror, loginfo, logwarning
from skimindex.sources import dataset_download_dir
from skimindex.stamp import is_stamped, needs_run, stamp, stamp_gz, unstamp
from skimindex.unix.compress import pigz, unzip
from skimindex.unix.ncbi import datasets, datasets_summary_genome


def list_datasets() -> str:
    """List NCBI dataset names as CSV from config."""
    names = datasets_for_source("ncbi")
    return ",".join(names) if names else ""


def list_assemblies(
    taxon: str,
    assembly_level: str | None = None,
    reference: bool = False,
    assembly_source: str | None = None,
    assembly_version: str | None = None,
) -> list[dict[str, Any]]:
    """List genome assemblies for a taxon using NCBI datasets summary.

    Runs: datasets summary genome taxon <taxon> [flags]
    Returns the list of assembly reports.
    """
    cmd_args = ["taxon", taxon]

    if reference:
        cmd_args.append("--reference")
    if assembly_source:
        cmd_args.extend(["--assembly-source", assembly_source])
    if assembly_level:
        cmd_args.extend(["--assembly-level", assembly_level])
    if assembly_version:
        cmd_args.extend(["--assembly-version", assembly_version])

    loginfo(f"Listing assemblies for taxon '{taxon}'...")
    stdout = datasets_summary_genome(*cmd_args)()
    return json.loads(stdout).get("reports", [])


@functools.lru_cache(maxsize=None)
def _cached_list_assemblies(
    taxon: str,
    assembly_level: str | None,
    reference: bool,
    assembly_source: str | None,
    assembly_version: str | None,
) -> tuple:
    """Cached wrapper around list_assemblies() to avoid repeated NCBI API calls."""
    assemblies = list_assemblies(taxon, assembly_level, reference, assembly_source, assembly_version)
    return tuple(assemblies)


def list_taxids(
    taxon: str,
    assembly_level: str | None = None,
    reference: bool = False,
    assembly_source: str | None = None,
    assembly_version: str | None = None,
) -> list[int]:
    """List NCBI taxonomic IDs for assemblies matching the criteria."""
    assemblies = list_assemblies(taxon, assembly_level, reference, assembly_source, assembly_version)
    taxids = []
    for assembly in assemblies:
        biosample = assembly.get("assembly_info", {}).get("biosample", {})
        description = biosample.get("description", {})
        organism = description.get("organism", {})
        tax_id = organism.get("tax_id")
        if tax_id is not None:
            taxids.append(tax_id)
    return taxids


def _get_accession_type(accession: str) -> int:
    """Return priority for accession type: 0 for GCF (RefSeq), 1 for GCA (GenBank)."""
    return 0 if accession.startswith("GCF_") else 1


def _get_genome_size(assembly: dict[str, Any]) -> int:
    """Extract total sequence length from assembly stats."""
    stats = assembly.get("assembly_stats", {})
    total_length = stats.get("total_sequence_length", "0")
    try:
        return int(total_length)
    except (ValueError, TypeError):
        return 0


def filter_assemblies_by_species(assemblies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter assemblies to keep only one per species.

    Selection criteria: prefer RefSeq (GCF_), then larger genome.
    """
    species_groups: dict[str, list] = {}
    for assembly in assemblies:
        name = _get_organism_name_from_report(assembly)
        if name:
            species_groups.setdefault(name, []).append(assembly)

    return [
        sorted(lst, key=lambda a: (_get_accession_type(a.get("accession", "")), -_get_genome_size(a)))[0]
        for lst in species_groups.values()
    ]


def filter_assemblies_by_genus(assemblies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter assemblies to keep only one per genus.

    Selection criteria: prefer RefSeq (GCF_), then larger genome.
    """
    genus_groups: dict[str, list] = {}
    for assembly in assemblies:
        name = _get_organism_name_from_report(assembly)
        if name:
            genus = name.split()[0]
            genus_groups.setdefault(genus, []).append(assembly)

    return [
        sorted(lst, key=lambda a: (_get_accession_type(a.get("accession", "")), -_get_genome_size(a)))[0]
        for lst in genus_groups.values()
    ]


def filter_assemblies_no_hybrids(assemblies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove hybrid organisms (names containing ' x ') from the assembly list."""
    return [
        a for a in assemblies
        if not re.search(r'\bx\b', _get_organism_name_from_report(a), re.IGNORECASE)
    ]


def query_assemblies(
    taxon: str,
    assembly_level: str | None = None,
    reference: bool = False,
    assembly_source: str | None = None,
    assembly_version: str | None = None,
    one_per: str | None = None,
) -> int:
    """List assemblies for a taxon, apply filters, print summary.

    Returns exit code 0 (always succeeds as a query operation).
    """
    assemblies = list_assemblies(taxon, assembly_level, reference, assembly_source, assembly_version)
    if one_per == "species":
        assemblies = filter_assemblies_by_species(assemblies)
    elif one_per == "genus":
        assemblies = filter_assemblies_by_genus(assemblies)
    print(f"Found {len(assemblies)} assemblies")
    for asm in assemblies:
        accession = asm.get("accession", "N/A")
        organism = _get_organism_name_from_report(asm)
        size = asm.get("assembly_stats", {}).get("total_sequence_length", "0")
        print(f"  {accession} - {organism} ({size} bp)")
    return 0


def _taxon_key(organism_name: str, one_per: str) -> str:
    """Return genus or species key for an organism name."""
    parts = _safe_name(organism_name).split("_")
    if one_per == "genus":
        return parts[0]
    if one_per == "species" and len(parts) >= 2:
        return f"{parts[0]}_{parts[1]}"
    return _safe_name(organism_name)


def _covered_taxa(output_dir: Path, one_per: str) -> set:
    """Return the set of genera or species already present in *output_dir*."""
    covered = set()
    for f in output_dir.glob("*.gbff.gz"):
        m = re.search(r"^(.+?)-(?:GCF|GCA)_", f.name)
        if not m:
            continue
        parts = m.group(1).split("_")
        if one_per == "genus":
            covered.add(parts[0])
        elif one_per == "species" and len(parts) >= 2:
            covered.add(f"{parts[0]}_{parts[1]}")
    return covered


def _get_organism_name_from_report(assembly: dict[str, Any]) -> str:
    """Extract organism name from a datasets summary report dict."""
    name = assembly.get("organism", {}).get("organism_name", "")
    if not name:
        biosample = assembly.get("assembly_info", {}).get("biosample", {})
        name = biosample.get("description", {}).get("organism", {}).get("organism_name", "")
    return name or assembly.get("accession", "unknown")


def _safe_name(organism: str) -> str:
    """Convert organism name to safe filename."""
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", organism)
    safe = re.sub(r"_+", "_", safe)
    return safe.strip("_")


def _download_accession(accession: str, zip_file: Path, stamp_key: Path) -> bool:
    """Download a single accession ZIP. Skip if stamp exists."""
    if is_stamped(stamp_key):
        loginfo(f"    [{accession}] Already downloaded (stamp exists)")
        return True
    try:
        loginfo(f"    [{accession}] Downloading...")
        zip_file.parent.mkdir(parents=True, exist_ok=True)
        datasets(
            "download", "genome", "accession", accession,
            "--include", "gbff",
            "--filename", str(zip_file),
        )()
        stamp(stamp_key)
        loginfo(f"    [{accession}] Download complete")
        return True
    except Exception as e:
        logerror(f"    [{accession}] Download failed: {e}")
        zip_file.unlink(missing_ok=True)
        return False


def _extract_accession(
    accession: str, zip_file: Path, work_dir: Path, stamp_key: Path, dl_stamp_key: Path
) -> bool:
    """Extract a single accession ZIP. On failure, removes ZIP and dl_stamp to force re-download."""
    if is_stamped(stamp_key):
        loginfo(f"    [{accession}] Already extracted")
        return True
    if not zip_file.exists():
        logerror(f"    [{accession}] ZIP not found: {zip_file}")
        return False
    try:
        loginfo(f"    [{accession}] Extracting...")
        work_dir.mkdir(parents=True, exist_ok=True)
        unzip("-o", "-d", str(work_dir), str(zip_file))()
        stamp(stamp_key)
        zip_file.unlink(missing_ok=True)
        loginfo(f"    [{accession}] Extraction complete")
        return True
    except Exception as e:
        logerror(f"    [{accession}] Extract failed: {e}")
        zip_file.unlink(missing_ok=True)
        unstamp(dl_stamp_key)
        return False


def _compress_accession(
    accession: str, organism_name: str, work_dir: Path, output_path: Path, out_file: Path
) -> bool:
    """Compress GBFF files for one accession and stamp the output gz file."""
    if is_stamped(out_file):
        loginfo(f"    [{accession}] Already compressed")
        return True
    if out_file.exists():
        loginfo(f"    [{accession}] Output exists, verifying integrity...")
        if stamp_gz(out_file):
            return True
        logwarning(f"    [{accession}] Integrity check failed, re-compressing...")
        out_file.unlink(missing_ok=True)

    dataset_dir = work_dir / "ncbi_dataset" / "data" / accession
    if not dataset_dir.exists():
        logerror(f"    [{accession}] Dataset dir not found: {dataset_dir}")
        return False

    loginfo(f"    [{accession}] Compressing...")
    ok = _consolidate_accession(dataset_dir, organism_name, out_file)
    if ok:
        ok = stamp_gz(out_file)
        if ok:
            shutil.rmtree(work_dir, ignore_errors=True)
            loginfo(f"    [{accession}] Compression complete")
        else:
            logerror(f"    [{accession}] Integrity check failed after compression")
    return ok


def _consolidate_accession(accession_dir: Path, organism: str, out_file: Path) -> bool:
    """Consolidate and compress GBFF files for an accession."""
    try:
        gbff_files = list(accession_dir.glob("**/*.gbff"))
        if not gbff_files:
            logerror(f"No .gbff files found in {accession_dir}")
            return False

        if len(gbff_files) == 1:
            gbff_file = gbff_files[0]
            pigz("-f", "-k", str(gbff_file))()
            Path(str(gbff_file) + ".gz").rename(out_file)
            return True

        temp_gbff = accession_dir / "consolidated.gbff"
        try:
            with open(temp_gbff, "wb") as out_f:
                for gbff_file in sorted(gbff_files):
                    with open(gbff_file, "rb") as in_f:
                        out_f.write(in_f.read())
            pigz("-f", "-k", str(temp_gbff))()
            Path(str(temp_gbff) + ".gz").rename(out_file)
            return True
        finally:
            temp_gbff.unlink(missing_ok=True)
    except Exception as e:
        logerror(f"Error consolidating {accession_dir}: {e}")
        return False


def _load_dataset_config(dataset_name: str) -> dict[str, Any]:
    """Load download parameters for an NCBI dataset from config."""
    try:
        ds = dataset_config(dataset_name)
        taxon = ds.get("taxon")
        if not taxon:
            logerror(f"Dataset [{dataset_name}]: 'taxon' is not defined in config.")
            return {}

        output_dir = dataset_download_dir(dataset_name)
        reference = str(ds.get("reference", "false")).lower() == "true"
        one_per = ds.get("one_per", "").lower()

        return {
            "taxon": taxon,
            "output_dir": output_dir,
            "reference": reference,
            "assembly_source": ds.get("assembly_source"),
            "assembly_level": ds.get("assembly_level"),
            "assembly_version": ds.get("assembly_version"),
            "one_per": one_per,
        }
    except Exception as e:
        logerror(f"Error loading dataset [{dataset_name}]: {e}")
        return {}


def process_ncbi_dataset(
    dataset_name: str,
    one_per: str | None = None,
    dry_run: bool = False,
) -> bool:
    """Download and process a single NCBI dataset, accession by accession.

    Returns True on success, False if any step failed.
    """
    loginfo(f"===== Processing NCBI dataset: {dataset_name} =====")

    config_vals = _load_dataset_config(dataset_name)
    if not config_vals:
        logerror(f"Dataset [{dataset_name}] configuration not found")
        return False

    taxon = config_vals["taxon"]
    output_dir = config_vals["output_dir"]
    reference = config_vals["reference"]
    assembly_source = config_vals.get("assembly_source")
    assembly_level = config_vals.get("assembly_level")
    assembly_version = config_vals.get("assembly_version")
    one_per = one_per if one_per is not None else config_vals.get("one_per", "")

    work_base = output_dir / ".work"
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    loginfo(f"[{dataset_name}] Taxon: {taxon}")
    loginfo(f"[{dataset_name}] Output: {output_dir}")

    assemblies = list(_cached_list_assemblies(taxon, assembly_level, reference, assembly_source, assembly_version))
    if not assemblies:
        logwarning(f"[{dataset_name}] No assemblies found for taxon '{taxon}'")
        return True

    if one_per == "species":
        assemblies = filter_assemblies_by_species(assemblies)
        loginfo(f"[{dataset_name}] Filtered to {len(assemblies)} assemblies (one per species)")
    elif one_per == "genus":
        assemblies = filter_assemblies_by_genus(assemblies)
        loginfo(f"[{dataset_name}] Filtered to {len(assemblies)} assemblies (one per genus)")
    else:
        loginfo(f"[{dataset_name}] Processing {len(assemblies)} assemblies")

    before = len(assemblies)
    assemblies = filter_assemblies_no_hybrids(assemblies)
    if len(assemblies) < before:
        loginfo(f"[{dataset_name}] Removed {before - len(assemblies)} hybrid(s), {len(assemblies)} remaining")

    if one_per in ("genus", "species") and output_dir.exists():
        covered = _covered_taxa(output_dir, one_per)
        if covered:
            before = len(assemblies)
            assemblies = [a for a in assemblies
                          if _taxon_key(_get_organism_name_from_report(a), one_per) not in covered]
            skipped = before - len(assemblies)
            if skipped:
                loginfo(f"[{dataset_name}] {skipped} {one_per}(s) already on disk, {len(assemblies)} new")

    accession_map = {
        asm["accession"]: _get_organism_name_from_report(asm)
        for asm in assemblies
        if asm.get("accession")
    }

    total = len(accession_map)
    max_retries = 3
    errors = 0

    for attempt in range(1, max_retries + 1):
        errors = 0
        failed_accessions = []

        for i, (accession, organism_name) in enumerate(accession_map.items(), 1):
            work_dir = work_base / accession
            zip_file = work_dir / "download.zip"
            dl_stamp = work_base / accession / "download"
            ext_stamp = work_base / accession / "extract"
            safe_name_str = _safe_name(organism_name)
            final_output = output_dir / f"{safe_name_str}-{accession}.gbff.gz"

            if not needs_run(final_output, dry_run=dry_run,
                             label=accession, action=f"download {accession}"):
                continue

            loginfo(f"[{dataset_name}] [{i}/{total}] {accession} — {organism_name}")

            if not _download_accession(accession, zip_file, dl_stamp):
                errors += 1
                failed_accessions.append(accession)
                continue
            if not _extract_accession(accession, zip_file, work_dir, ext_stamp, dl_stamp):
                errors += 1
                failed_accessions.append(accession)
                continue
            if not _compress_accession(accession, organism_name, work_dir, output_dir, final_output):
                errors += 1
                failed_accessions.append(accession)

        if errors == 0:
            break
        if attempt < max_retries:
            logwarning(f"[{dataset_name}] Attempt {attempt}/{max_retries}: {errors} failed, retrying...")
        else:
            logerror(f"[{dataset_name}] {errors} accession(s) still failing after {max_retries} attempts")

    shutil.rmtree(work_base, ignore_errors=True)

    if errors:
        logerror(f"[{dataset_name}] {errors}/{total} accession(s) failed")
        return False

    loginfo(f"[{dataset_name}] ✓ All {total} accessions processed successfully")
    return True


def process_ncbi(
    dataset_names: list[str] | None = None,
    one_per: str | None = None,
    dry_run: bool = False,
) -> int:
    """Main entry point: process NCBI reference genome datasets.

    Args:
        dataset_names: Dataset names to process. If None, uses all datasets
                       with source="ncbi" from config.
        one_per: Override one_per setting ("species", "genus", or None).
        dry_run: If True, show what would be done without executing.

    Returns:
        0 on success, 1 if any dataset failed.
    """
    if dataset_names is None:
        dataset_names = datasets_for_source("ncbi")

    if not dataset_names:
        logwarning("No NCBI datasets configured (no [data.X] with source = \"ncbi\")")
        return 0

    loginfo(f"Processing {len(dataset_names)} NCBI dataset(s)")

    errors = 0
    for name in dataset_names:
        if not process_ncbi_dataset(name, one_per=one_per, dry_run=dry_run):
            errors += 1

    if errors > 0:
        logerror(f"===== {errors} dataset(s) failed =====")
        return 1

    loginfo("===== All NCBI datasets processed successfully =====")
    return 0
