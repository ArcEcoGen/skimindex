"""
Reference genome download processor — pure Python, file-based robustness.

Orchestrates NCBI reference genome downloads and processing:
- Downloads genome assemblies from NCBI by taxon
- Extracts GBFF files from ZIP archives
- Compresses per-accession: {scientific_name}-{accession}.gbff.gz

Uses stamp files for robustness: if interrupted, relaunching skips already-processed steps.
"""

import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from skimindex.config import config
from skimindex.log import logerror, loginfo, logwarning
from skimindex.unix.compress import pigz, unzip
from skimindex.unix.ncbi import datasets


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
        genbank_root = cfg.get("directories", "genbank", "/genbank")
        rel_dir = section_data.get("directory", section.lower())
        output_dir = Path(genbank_root) / rel_dir

        # Get optional filters
        reference = str(section_data.get("reference", "false")).lower() == "true"

        return {
            "taxon": taxon,
            "output_dir": output_dir,
            "reference": reference,
            "assembly_source": section_data.get("assembly_source"),
            "assembly_level": section_data.get("assembly_level"),
            "assembly_version": section_data.get("assembly_version"),
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


def _download_assemblies(
    taxon: str,
    zip_file: Path,
    reference: bool,
    assembly_source: Optional[str],
    assembly_level: Optional[str],
    assembly_version: Optional[str],
) -> bool:
    """Download genome assemblies from NCBI using datasets command."""
    try:
        loginfo(f"Downloading assemblies for '{taxon}'...")
        loginfo(f"Destination: {zip_file}")
        loginfo("This may take a long time — be patient...")

        # Build datasets command arguments
        cmd_args = ["download", "genome", "taxon", taxon]

        if reference:
            cmd_args.append("--reference")
        if assembly_source:
            cmd_args.extend(["--assembly-source", assembly_source])
        if assembly_level:
            cmd_args.extend(["--assembly-level", assembly_level])
        if assembly_version:
            cmd_args.extend(["--assembly-version", assembly_version])

        cmd_args.extend(["--include", "gbff"])
        cmd_args.extend(["--filename", str(zip_file)])

        # Execute datasets command
        datasets(*cmd_args)()
        return True

    except Exception as e:
        logerror(f"Failed to download assemblies: {e}")
        return False


def _extract_assemblies(zip_file: Path, output_path: Path) -> bool:
    """Extract ZIP archive."""
    try:
        loginfo(f"Extracting {zip_file}...")
        output_path.mkdir(parents=True, exist_ok=True)
        unzip("-d", str(output_path), str(zip_file))()
        return True
    except Exception as e:
        logerror(f"Failed to extract ZIP: {e}")
        return False


def _get_organism_name(report_file: Path, accession: str) -> Optional[str]:
    """Extract organism name from assembly_data_report.jsonl."""
    try:
        if not report_file.exists():
            return None

        with open(report_file, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                if data.get("accession") == accession:
                    return data.get("organism", {}).get("organism_name")
    except Exception:
        pass
    return None


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
            pigz("-k", str(gbff_file))()
            Path(str(gbff_file) + ".gz").rename(out_file)
            return True

        # Multiple files: concatenate then compress
        temp_gbff = accession_dir / "consolidated.gbff"
        try:
            with open(temp_gbff, "wb") as out_f:
                for gbff_file in sorted(gbff_files):
                    with open(gbff_file, "rb") as in_f:
                        out_f.write(in_f.read())

            pigz("-k", str(temp_gbff))()
            Path(str(temp_gbff) + ".gz").rename(out_file)
            return True
        finally:
            temp_gbff.unlink(missing_ok=True)

    except Exception as e:
        logerror(f"Error consolidating {accession_dir}: {e}")
        return False


def _compress_accessions(
    dataset_dir: Path, output_path: Path, report_file: Path
) -> int:
    """Compress GBFF files per accession. Returns number of errors."""
    loginfo(f"Compressing per-accession GBFF files into {output_path}...")

    # Find accession directories
    accessions: List[str] = []
    data_dir = dataset_dir / "data"

    if data_dir.exists():
        for item in sorted(data_dir.iterdir()):
            if item.is_dir():
                accessions.append(item.name)

    total = len(accessions)
    count = 0
    errors = 0

    for accession in accessions:
        count += 1
        loginfo(f"[{count}/{total}] {accession}")

        # Get organism name from report
        organism = _get_organism_name(report_file, accession)
        if not organism:
            organism = accession

        # Create safe filename
        safe_name_str = _safe_name(organism)
        out_file = output_path / f"{safe_name_str}-{accession}.gbff.gz"

        # Skip if already exists
        if out_file.exists():
            loginfo(f"  Skipping {out_file.name} (already exists)")
            continue

        # Compress accession
        if not _consolidate_accession(data_dir / accession, organism, out_file):
            logerror(f"Failed to compress {accession}")
            errors += 1

    loginfo(f"  Total: {total}")
    return errors


def process_refgenome_section(section: str) -> bool:
    """Download and process a single reference genome section.

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

    # Setup paths
    zip_file = output_dir / "download.zip"
    dataset_dir = output_dir / "ncbi_dataset"
    report_file = dataset_dir / "data" / "assembly_data_report.jsonl"

    # Stamp files for robustness
    download_stamp = output_dir / ".download.stamp"
    extract_stamp = output_dir / ".extract.stamp"
    compress_stamp = output_dir / ".compress.stamp"

    # Step 1: Download ZIP (skip if already done)
    if not download_stamp.exists():
        loginfo(f"[{section}] Downloading assemblies for taxon: {taxon}")
        dataset_flags = _format_dataset_flags(reference, assembly_source, assembly_level, assembly_version)
        if dataset_flags != "<none>":
            loginfo(f"[{section}] Datasets flags: {dataset_flags}")

        output_dir.mkdir(parents=True, exist_ok=True)
        if not _download_assemblies(taxon, zip_file, reference, assembly_source, assembly_level, assembly_version):
            logerror(f"[{section}] Failed to download")
            return False

        download_stamp.touch()
        loginfo(f"[{section}] Download complete")
    else:
        loginfo(f"[{section}] ZIP already downloaded (stamp exists)")

    # Step 2: Extract ZIP (skip if already done)
    if not extract_stamp.exists():
        loginfo(f"[{section}] Extracting {zip_file}...")
        if not _extract_assemblies(zip_file, output_dir):
            logerror(f"[{section}] Failed to extract")
            return False

        # Delete ZIP after extraction
        zip_file.unlink(missing_ok=True)
        extract_stamp.touch()
        loginfo(f"[{section}] Extraction complete")
    else:
        loginfo(f"[{section}] Already extracted (stamp exists)")

    # Step 3: Compress accessions (skip if already done)
    if not compress_stamp.exists():
        loginfo(f"[{section}] Compressing per-accession files...")
        errors = _compress_accessions(dataset_dir, output_dir, report_file)

        if errors == 0:
            # Cleanup extracted data
            loginfo(f"[{section}] Removing {dataset_dir}...")
            shutil.rmtree(dataset_dir, ignore_errors=True)
            compress_stamp.touch()
            loginfo(f"[{section}] ✓ Completed successfully")
        else:
            logerror(f"[{section}] {errors} accession(s) failed — re-run to retry")
            return False
    else:
        loginfo(f"[{section}] Already compressed (stamp exists)")

    return True


def process_refgenome(sections: List[str] = None) -> int:
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
        if not process_refgenome_section(section):
            errors += 1

    if errors > 0:
        logerror(f"===== {errors} section(s) failed =====")
        return 1

    loginfo("===== All reference genomes processed successfully =====")
    return 0
