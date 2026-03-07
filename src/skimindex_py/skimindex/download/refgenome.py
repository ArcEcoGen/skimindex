"""
Reference genome download module — pure doit pipeline for NCBI genome downloads.

Implements functionality of download_references.sh + _download_refgenome.sh:
- Downloads genome assemblies from NCBI for a given taxon (task_download)
- Extracts GBFF files from the ZIP archive (task_extract)
- Compresses one GBFF per accession: {scientific_name}-{accession}.gbff.gz (task_compress)
- Orchestrates downloads for all configured sections via doit

Fully doit-based orchestration:
- doit -f skimindex.download.refgenome (all sections)
- doit -f skimindex.download.refgenome download:human (single section download)
- doit -f skimindex.download.refgenome extract:human (single section extract)
- doit -f skimindex.download.refgenome compress:human (single section compress)

The pipeline for each section:
  task_download(section)
    → task_extract(section)
      → task_compress(section)

All three tasks are generated for each configured section.
"""

import json
import os
import re
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List

from skimindex.config import config
from skimindex.log import loginfo, logwarning, logerror
from skimindex.unix.ncbi import datasets
from skimindex.unix.compress import pigz, unzip


# Get reference genome sections from singleton config
_SECTIONS = config().ref_genomes


def list_sections() -> str:
    """
    List available reference genome sections as CSV.

    Returns:
        Comma-separated string of section names
    """
    sections = _get_sections()
    return ",".join(sections) if sections else ""


def _load_from_section(section: str) -> Dict[str, Any]:
    """Load parameters from config section environment variables."""
    try:
        section_upper = section.upper()

        # Get taxon (required)
        taxon_var = f"SKIMINDEX__{section_upper}__TAXON"
        taxon = os.environ.get(taxon_var)
        if not taxon:
            logerror(f"Section [{section}]: {taxon_var} is not defined.")
            return {}

        # Get output directory
        rel_dir_var = f"SKIMINDEX__{section_upper}__DIRECTORY"
        genbank_var = "SKIMINDEX__DIRECTORIES__GENBANK"
        genbank_root = os.environ.get(genbank_var, "/genbank")
        rel_dir = os.environ.get(rel_dir_var, section.lower())
        output_dir = str(Path(genbank_root) / rel_dir)

        # Get optional filters
        reference_var = f"SKIMINDEX__{section_upper}__REFERENCE"
        assembly_source_var = f"SKIMINDEX__{section_upper}__ASSEMBLY_SOURCE"
        assembly_level_var = f"SKIMINDEX__{section_upper}__ASSEMBLY_LEVEL"
        assembly_version_var = f"SKIMINDEX__{section_upper}__ASSEMBLY_VERSION"

        reference = os.environ.get(reference_var, "").lower() == "true"

        return {
            "taxon": taxon,
            "output_dir": output_dir,
            "reference": reference,
            "assembly_source": os.environ.get(assembly_source_var),
            "assembly_level": os.environ.get(assembly_level_var),
            "assembly_version": os.environ.get(assembly_version_var),
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
    """Download genome assemblies from NCBI using datasets (plumbum)."""
    try:
        loginfo(f"Downloading assemblies for '{taxon}'...")
        loginfo(f"Destination: {zip_file}")
        loginfo("This may take a long time — be patient...")

        # Build datasets command arguments
        cmd_args = ["download", "genome", "--taxon", taxon]

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

        # Execute datasets command via plumbum
        datasets(*cmd_args)()
        return True

    except Exception as e:
        logerror(f"Failed to download assemblies: {e}")
        return False


def _extract_assemblies(zip_file: Path, output_path: Path) -> bool:
    """Extract ZIP archive using unzip (plumbum)."""
    try:
        loginfo(f"Extracting {zip_file}...")
        # Execute unzip via plumbum
        unzip("-d", str(output_path), str(zip_file))()
        return True
    except Exception as e:
        logerror(f"Failed to extract ZIP: {e}")
        return False


def _compress_accessions(
    dataset_dir: Path, output_path: Path, report_file: Path
) -> int:
    """Compress GBFF files per accession using pigz (plumbum)."""
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

    loginfo(f"  Total    : {total}")
    return errors


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
    # Replace spaces and special chars with underscores
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", organism)
    # Remove consecutive underscores
    safe = re.sub(r"_+", "_", safe)
    # Remove leading/trailing underscores
    safe = safe.strip("_")
    return safe


def _consolidate_accession(accession_dir: Path, organism: str, out_file: Path) -> bool:
    """Consolidate and compress GBFF files for an accession using pigz (plumbum)."""
    try:
        # Find all .gbff files in accession directory
        gbff_files = list(accession_dir.glob("**/*.gbff"))

        if not gbff_files:
            logerror(f"No .gbff files found in {accession_dir}")
            return False

        # If only one file, compress it directly
        if len(gbff_files) == 1:
            gbff_file = gbff_files[0]
            # Compress with pigz -k (keep original), output goes to .gz
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

            # Compress consolidated file with pigz -k
            pigz("-k", str(temp_gbff))()
            Path(str(temp_gbff) + ".gz").rename(out_file)
            return True
        finally:
            temp_gbff.unlink(missing_ok=True)

    except Exception as e:
        logerror(f"Error consolidating {accession_dir}: {e}")
        return False


# ===== doit pure pipeline orchestration =====


# doit configuration
DOIT_CONFIG = {
    "default_tasks": ["all"],
    "verbosity": 2,
}


def _get_sections() -> List[str]:
    """Return reference genome sections (loaded at module init)."""
    return _SECTIONS


def task_download():
    """Download genome assemblies for each section (task generator)."""
    sections = _get_sections()

    if not sections:
        yield {
            "name": "none",
            "actions": [
                lambda: logwarning("No reference genome sections found in config.")
            ],
            "verbosity": 2,
        }
        return

    for section in sections:
        # Get section configuration
        config_vals = _load_from_section(section)
        if not config_vals:
            yield {
                "name": section,
                "actions": [
                    lambda s=section: logerror(
                        f"Section [{s}] configuration not found"
                    )
                ],
                "verbosity": 2,
            }
            continue

        # Extract parameters
        final_taxon = config_vals.get("taxon")
        final_output_dir = config_vals.get("output_dir")
        final_reference = config_vals.get("reference", False)
        final_assembly_source = config_vals.get("assembly_source")
        final_assembly_level = config_vals.get("assembly_level")
        final_assembly_version = config_vals.get("assembly_version")

        output_path = Path(final_output_dir)
        zip_file = output_path / "download.zip"
        dataset_dir = output_path / "ncbi_dataset"

        def download_assemblies_action(
            s=section,
            t=final_taxon,
            z=zip_file,
            ref=final_reference,
            src=final_assembly_source,
            lvl=final_assembly_level,
            ver=final_assembly_version,
        ):
            loginfo(f"[{s}] Downloading assemblies for taxon: {t}")
            dataset_flags = _format_dataset_flags(ref, src, lvl, ver)
            if dataset_flags != "<none>":
                loginfo(f"[{s}] Datasets flags: {dataset_flags}")
            return _download_assemblies(t, z, ref, src, lvl, ver)

        yield {
            "name": section,
            "actions": [download_assemblies_action],
            "targets": [str(zip_file)],
            "verbosity": 2,
        }


def task_extract():
    """Extract downloaded ZIP archives (task generator)."""
    sections = _get_sections()

    if not sections:
        return

    for section in sections:
        config_vals = _load_from_section(section)
        if not config_vals:
            continue

        final_output_dir = config_vals.get("output_dir")
        output_path = Path(final_output_dir)
        zip_file = output_path / "download.zip"
        dataset_dir = output_path / "ncbi_dataset"

        def extract_action(s=section, z=zip_file, o=output_path):
            loginfo(f"[{s}] Extracting {z}...")
            success = _extract_assemblies(z, o)
            if success:
                z.unlink(missing_ok=True)
                loginfo(f"[{s}] Extraction complete")
            return success

        yield {
            "name": section,
            "actions": [extract_action],
            "file_dep": [str(zip_file)],
            "targets": [str(dataset_dir)],
            "task_dep": [f"download:{section}"],
            "verbosity": 2,
        }


def task_compress():
    """Compress GBFF files per accession (task generator)."""
    sections = _get_sections()

    if not sections:
        return

    for section in sections:
        config_vals = _load_from_section(section)
        if not config_vals:
            continue

        final_output_dir = config_vals.get("output_dir")
        output_path = Path(final_output_dir)
        dataset_dir = output_path / "ncbi_dataset"
        report_file = dataset_dir / "data" / "assembly_data_report.jsonl"

        def compress_action(s=section, d=dataset_dir, o=output_path, r=report_file):
            loginfo(f"[{s}] Compressing per-accession GBFF files...")
            errors = _compress_accessions(d, o, r)

            if errors == 0:
                loginfo(f"[{s}] Removing {d}...")
                shutil.rmtree(d, ignore_errors=True)
                loginfo(f"[{s}] ✓ Completed successfully")
                return True
            else:
                logerror(f"[{s}] {errors} accession(s) failed — re-run to retry")
                return False

        yield {
            "name": section,
            "actions": [compress_action],
            "task_dep": [f"extract:{section}"],
            "verbosity": 2,
        }


def task_all():
    """Aggregate task for all sections (orchestration)."""
    sections = _get_sections()

    if not sections:
        return {
            "actions": [
                lambda: logwarning("No reference genome sections configured.")
            ],
            "verbosity": 2,
        }

    # Depend on compress tasks for all sections (the final stage)
    task_deps = [f"compress:{section}" for section in sections]

    return {
        "actions": [
            lambda: loginfo(f"===== Completed {len(sections)} section(s) =====")
        ],
        "task_dep": task_deps,
        "verbosity": 2,
    }
