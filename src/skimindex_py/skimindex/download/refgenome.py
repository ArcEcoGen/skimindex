"""
Reference genome download processor — pure Python, file-based robustness.

Orchestrates NCBI reference genome downloads and processing:
- Downloads genome assemblies from NCBI by taxon
- Extracts GBFF files from ZIP archives
- Compresses per-accession: {scientific_name}-{accession}.gbff.gz

Uses stamp files for robustness: if interrupted, relaunching skips already-processed steps.
"""

import functools
import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from skimindex.config import config
from skimindex.log import logerror, loginfo, logwarning
from skimindex.sections import genbank_base, section_rel_dir
from skimindex.stamp import is_stamped, needs_run, stamp, unstamp
from skimindex.unix.compress import pigz, unzip
from skimindex.unix.ncbi import datasets, datasets_summary_genome


def list_assemblies(
    taxon: str,
    assembly_level: Optional[str] = None,
    reference: bool = False,
    assembly_source: Optional[str] = None,
    assembly_version: Optional[str] = None,
) -> List[Dict[str, Any]]:
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
    assembly_level: Optional[str],
    reference: bool,
    assembly_source: Optional[str],
    assembly_version: Optional[str],
) -> tuple:
    """Cached wrapper around list_assemblies() to avoid repeated NCBI API calls.

    Returns tuple instead of list for hashability (lru_cache requirement).
    """
    assemblies = list_assemblies(taxon, assembly_level, reference, assembly_source, assembly_version)
    return tuple(assemblies)  # Convert to tuple for hashability


def list_taxids(
    taxon: str,
    assembly_level: Optional[str] = None,
    reference: bool = False,
    assembly_source: Optional[str] = None,
    assembly_version: Optional[str] = None,
) -> List[int]:
    """List NCBI taxonomic IDs for assemblies matching the criteria.

    Returns list of tax_id values in order, including duplicates.
    """
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


def _get_genome_size(assembly: Dict[str, Any]) -> int:
    """Extract total sequence length from assembly stats."""
    stats = assembly.get("assembly_stats", {})
    total_length = stats.get("total_sequence_length", "0")
    try:
        return int(total_length)
    except (ValueError, TypeError):
        return 0


def filter_assemblies_by_species(assemblies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter assemblies to keep only one per species.

    Selection criteria (in order):
    1. Prefer RefSeq (GCF_) over GenBank (GCA_)
    2. Prefer larger genomes
    """
    species_groups = {}

    for assembly in assemblies:
        biosample = assembly.get("assembly_info", {}).get("biosample", {})
        description = biosample.get("description", {})
        organism = description.get("organism", {})
        organism_name = organism.get("organism_name", "")

        if organism_name:
            if organism_name not in species_groups:
                species_groups[organism_name] = []
            species_groups[organism_name].append(assembly)

    # Select best assembly per species
    selected = []
    for species, assemblies_list in species_groups.items():
        # Sort by: accession type (GCF first), then by genome size (descending)
        best = sorted(
            assemblies_list,
            key=lambda a: (
                _get_accession_type(a.get("accession", "")),
                -_get_genome_size(a),
            ),
        )[0]
        selected.append(best)

    return selected


def filter_assemblies_by_genus(assemblies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter assemblies to keep only one per genus.

    Selection criteria (in order):
    1. Prefer RefSeq (GCF_) over GenBank (GCA_)
    2. Prefer larger genomes
    """
    genus_groups = {}

    for assembly in assemblies:
        biosample = assembly.get("assembly_info", {}).get("biosample", {})
        description = biosample.get("description", {})
        organism = description.get("organism", {})
        organism_name = organism.get("organism_name", "")

        if organism_name:
            genus = organism_name.split()[0]
            if genus not in genus_groups:
                genus_groups[genus] = []
            genus_groups[genus].append(assembly)

    # Select best assembly per genus
    selected = []
    for genus, assemblies_list in genus_groups.items():
        # Sort by: accession type (GCF first), then by genome size (descending)
        best = sorted(
            assemblies_list,
            key=lambda a: (
                _get_accession_type(a.get("accession", "")),
                -_get_genome_size(a),
            ),
        )[0]
        selected.append(best)

    return selected


def list_sections() -> str:
    """List available reference genome sections as CSV from config."""
    cfg = config()
    sections = cfg.ref_genomes
    return ",".join(sections) if sections else ""


def _load_section_config(section: str) -> Dict[str, Any]:
    """Load parameters for a reference genome section from config."""
    try:
        cfg = config()
        section_data = cfg.data.get(section, {})

        # Get taxon (required)
        taxon = section_data.get("taxon")
        if not taxon:
            logerror(f"Section [{section}]: 'taxon' is not defined in config.")
            return {}

        # Get output directory
        rel_dir = section_rel_dir(section)
        output_dir = genbank_base() / rel_dir

        # Get optional filters
        reference = str(section_data.get("reference", "false")).lower() == "true"
        one_per = section_data.get("one_per", "").lower()  # "species", "genus", or empty

        return {
            "taxon": taxon,
            "output_dir": output_dir,
            "reference": reference,
            "assembly_source": section_data.get("assembly_source"),
            "assembly_level": section_data.get("assembly_level"),
            "assembly_version": section_data.get("assembly_version"),
            "one_per": one_per,
        }
    except Exception as e:
        logerror(f"Error loading section [{section}]: {e}")
        return {}


def _format_dataset_flags(
    reference: bool,
    assembly_source: Optional[str],
    assembly_level: Optional[str],
    assembly_version: Optional[str],
) -> str:
    """Format datasets CLI flags for logging."""
    flags = []
    if reference:
        flags.append("--reference")
    if assembly_source:
        flags.append(f"--assembly-source {assembly_source}")
    if assembly_level:
        flags.append(f"--assembly-level {assembly_level}")
    if assembly_version:
        flags.append(f"--assembly-version {assembly_version}")
    return " ".join(flags) if flags else "<none>"


def _get_organism_name_from_report(assembly: Dict[str, Any]) -> str:
    """Extract organism name from a datasets summary report dict."""
    biosample = assembly.get("assembly_info", {}).get("biosample", {})
    description = biosample.get("description", {})
    organism = description.get("organism", {})
    name = organism.get("organism_name", "")
    return name or assembly.get("accession", "unknown")


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
    """Extract a single accession ZIP. Skip if stamp exists.

    On failure, removes ZIP and dl_stamp to force re-download on retry.
    """
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
        # Suppress ZIP after extraction
        zip_file.unlink(missing_ok=True)
        loginfo(f"    [{accession}] Extraction complete")
        return True
    except Exception as e:
        logerror(f"    [{accession}] Extract failed: {e}")
        # Clean up corrupted ZIP and dl_stamp to force re-download on retry
        zip_file.unlink(missing_ok=True)
        unstamp(dl_stamp_key)
        return False


def _compress_accession(
    accession: str,
    organism_name: str,
    work_dir: Path,
    output_path: Path,
    stamp_key: Path,
) -> bool:
    """Compress GBFF files for one accession. Skip if stamp exists."""
    if is_stamped(stamp_key):
        loginfo(f"    [{accession}] Already compressed")
        return True

    safe_name_str = _safe_name(organism_name)
    out_file = output_path / f"{safe_name_str}-{accession}.gbff.gz"

    if out_file.exists():
        loginfo(f"    [{accession}] Output already exists: {out_file.name}")
        stamp(stamp_key)
        return True

    # Find GBFF files in work_dir/ncbi_dataset/data/{accession}/
    dataset_dir = work_dir / "ncbi_dataset" / "data" / accession
    if not dataset_dir.exists():
        logerror(f"    [{accession}] Dataset dir not found: {dataset_dir}")
        return False

    loginfo(f"    [{accession}] Compressing...")
    ok = _consolidate_accession(dataset_dir, organism_name, out_file)
    if ok:
        stamp(stamp_key)
        # Cleanup work directory
        shutil.rmtree(work_dir, ignore_errors=True)
        loginfo(f"    [{accession}] Compression complete")
    return ok


def _safe_name(organism: str) -> str:
    """Convert organism name to safe filename."""
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", organism)
    safe = re.sub(r"_+", "_", safe)
    safe = safe.strip("_")
    return safe


def _consolidate_accession(accession_dir: Path, organism: str, out_file: Path) -> bool:
    """Consolidate and compress GBFF files for an accession."""
    try:
        # Find all .gbff files
        gbff_files = list(accession_dir.glob("**/*.gbff"))

        if not gbff_files:
            logerror(f"No .gbff files found in {accession_dir}")
            return False

        # If only one file, compress it directly
        if len(gbff_files) == 1:
            gbff_file = gbff_files[0]
            pigz("-f", "-k", str(gbff_file))()
            Path(str(gbff_file) + ".gz").rename(out_file)
            return True

        # Multiple files: concatenate then compress
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


def process_refgenome_section(
    section: str,
    one_per: Optional[str] = None,
    dry_run: bool = False,
) -> bool:
    """Download and process a single reference genome section, accession by accession.

    Returns True on success, False if any step failed.
    """
    loginfo(f"===== Processing reference genome section: {section} =====")

    # Load section config
    config_vals = _load_section_config(section)
    if not config_vals:
        logerror(f"Section [{section}] configuration not found")
        return False

    taxon = config_vals["taxon"]
    output_dir = config_vals["output_dir"]
    reference = config_vals["reference"]
    assembly_source = config_vals.get("assembly_source")
    assembly_level = config_vals.get("assembly_level")
    assembly_version = config_vals.get("assembly_version")
    # CLI arguments override TOML config
    one_per = one_per if one_per is not None else config_vals.get("one_per", "")

    work_base = output_dir / ".work"
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    # Log configuration
    loginfo(f"[{section}] Taxon: {taxon}")
    loginfo(f"[{section}] Output: {output_dir}")
    dataset_flags = _format_dataset_flags(reference, assembly_source, assembly_level, assembly_version)
    if dataset_flags != "<none>":
        loginfo(f"[{section}] Datasets flags: {dataset_flags}")

    # Fetch assemblies (cached in memory to avoid repeated NCBI calls)
    assemblies = list(_cached_list_assemblies(taxon, assembly_level, reference, assembly_source, assembly_version))

    if not assemblies:
        logwarning(f"[{section}] No assemblies found for taxon '{taxon}'")
        return True

    # Apply optional filtering
    if one_per == "species":
        assemblies = filter_assemblies_by_species(assemblies)
        loginfo(f"[{section}] Filtered to {len(assemblies)} assemblies (one per species)")
    elif one_per == "genus":
        assemblies = filter_assemblies_by_genus(assemblies)
        loginfo(f"[{section}] Filtered to {len(assemblies)} assemblies (one per genus)")
    else:
        loginfo(f"[{section}] Processing {len(assemblies)} assemblies")

    # Build accession → organism_name map
    accession_map = {}
    for asm in assemblies:
        accession = asm.get("accession")
        if accession:
            accession_map[accession] = _get_organism_name_from_report(asm)

    total = len(accession_map)
    max_retries = 3

    # Process each accession with automatic retry on failures
    for attempt in range(1, max_retries + 1):
        errors = 0
        failed_accessions = []

        for i, (accession, organism_name) in enumerate(accession_map.items(), 1):
            work_dir = work_base / accession
            zip_file = work_dir / "download.zip"

            dl_stamp = work_base / accession / "download"
            ext_stamp = work_base / accession / "extract"
            cmp_stamp = work_base / accession / "compress"

            if not needs_run(cmp_stamp, dry_run=dry_run,
                             label=accession, action=f"download {accession}"):
                continue

            loginfo(f"[{section}] [{i}/{total}] {accession} — {organism_name}")

            # Download → Extract → Compress pipeline
            if not _download_accession(accession, zip_file, dl_stamp):
                errors += 1
                failed_accessions.append(accession)
                continue

            if not _extract_accession(accession, zip_file, work_dir, ext_stamp, dl_stamp):
                errors += 1
                failed_accessions.append(accession)
                continue

            if not _compress_accession(accession, organism_name, work_dir, output_dir, cmp_stamp):
                errors += 1
                failed_accessions.append(accession)

        # If no errors, we're done
        if errors == 0:
            break

        # Log retry attempt
        if attempt < max_retries:
            logwarning(f"[{section}] Attempt {attempt}/{max_retries}: {errors} accession(s) failed, retrying...")
        else:
            logerror(f"[{section}] Attempt {attempt}/{max_retries}: {errors} accession(s) still failing after {max_retries} attempts")

    # Cleanup empty work directory
    shutil.rmtree(work_base, ignore_errors=True)

    if errors:
        logerror(f"[{section}] {errors}/{total} accession(s) failed — {', '.join(failed_accessions[:5])}" +
                 ("..." if len(failed_accessions) > 5 else ""))
        return False

    loginfo(f"[{section}] ✓ All {total} accessions processed successfully")
    return True


def process_refgenome(sections: List[str] = None, dry_run: bool = False) -> int:
    """Main entry point: process reference genome sections.

    Args:
        sections: List of section names to process.
                 If None, uses all configured sections from config.

    Returns:
        0 on success, 1 if any section failed.
    """
    # Use provided sections or get from config
    if sections is None:
        cfg = config()
        sections = cfg.ref_genomes

    if not sections:
        logwarning("No reference genome sections configured")
        return 0

    loginfo(f"Processing {len(sections)} reference genome section(s)")

    # Process each section
    errors = 0
    for section in sections:
        if not process_refgenome_section(section, dry_run=dry_run):
            errors += 1

    if errors > 0:
        logerror(f"===== {errors} section(s) failed =====")
        return 1

    loginfo("===== All reference genomes processed successfully =====")
    return 0
