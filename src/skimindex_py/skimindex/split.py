"""
Fragment splitting for decontamination index building.

Splits reference genome sequences into overlapping fragments for constructing
decontamination indices. Handles both taxon-based sections (pre-downloaded
FASTA/GBFF files) and GenBank division sections (filtered by taxid).

Fragment pipeline:
  obiscript(splitseqs.lua) → obigrep(filter Ns) → obidistribute(batches)

Uses configuration parameters:
  - decontamination.frg_size   : fragment size (default: 200)
  - decontamination.kmer_size  : for overlap calculation (default: 29)
  - decontamination.batches    : number of output batches (default: 20)
  - directories.genbank        : GenBank root directory
  - directories.processed_data : output directory for fragments

Output structure:
  - Taxon sections (per genome): <processed_data>/<section_dir>/{genome_name}/parts/frg_{batch}.fasta.gz
  - Division sections: <processed_data>/<section_dir>/parts/frg_{batch}.fasta.gz
"""

import os
from pathlib import Path
from typing import Any

from skimindex.config import config
from skimindex.log import logerror, loginfo, logwarning
from skimindex.sections import genbank_base, latest_release, section_dirs
from skimindex.stamp import needs_run, remove_if_not_stamped, stamp
from skimindex.unix.obitools import obiconvert, obidistribute, obigrep, obiscript

# Path to the Lua script for sequence splitting
SPLITSEQS_LUA = "/app/obiluascripts/splitseqs.lua"


def _extract_genome_info_from_filename(filename: str) -> tuple | None:
    """Extract genome name and accession from filename.

    Expected pattern: {name}-{ACCESSION}.{ext}
    Example: Homo_sapiens-GCF_000001405.40.gbff.gz
             → ("Homo_sapiens", "GCF_000001405.40")

    Returns:
        Tuple of (name, accession), or None if pattern not matched.
    """
    import re

    # Match pattern: {name}-{ACCESSION}.{ext} where ACCESSION starts with GCF_ or GCA_
    match = re.search(r"^(.+?)-((GCF|GCA)_[^.]+\.[0-9]+)", filename)
    if match:
        return (match.group(1), match.group(2))
    return None


def _extract_accession_from_filename(filename: str) -> str | None:
    """Extract accession (GCF_/GCA_) from genome filename.

    Expected pattern: {name}-{ACCESSION}.{ext}
    Example: Homo_sapiens-GCF_000001405.40.gbff.gz → GCF_000001405.40

    Returns:
        Accession string, or None if pattern not matched.
    """
    result = _extract_genome_info_from_filename(filename)
    return result[1] if result else None


def list_sections() -> str:
    """List available genome sections (all taxa) as CSV from config."""
    cfg = config()
    sections = cfg.ref_taxa
    return ",".join(sections) if sections else ""


def _load_split_params(
    frg_size_opt: int | None = None,
    overlap_opt: int | None = None,
    batches_opt: int | None = None,
) -> dict[str, int]:
    """Load decontamination parameters from config with CLI overrides.

    Args:
        frg_size_opt: Override fragment size (None → use config)
        overlap_opt: Override overlap (None → use config: kmer_size - 1)
        batches_opt: Override batch count (None → use config)

    Returns:
        Dict with keys: frg_size, overlap, batches
    """
    cfg = config()

    frg_size = frg_size_opt
    if frg_size is None:
        frg_size = int(cfg.get("decontamination", "frg_size", "200"))

    kmer_size = int(cfg.get("decontamination", "kmer_size", "29"))
    overlap = overlap_opt if overlap_opt is not None else (kmer_size - 1)

    batches = batches_opt
    if batches is None:
        batches = int(cfg.get("decontamination", "batches", "20"))

    return {
        "frg_size": frg_size,
        "overlap": overlap,
        "batches": batches,
    }




def _run_split_pipeline(
    source_cmd,
    fragments_dir: Path,
    frg_size: int,
    overlap: int,
    batches: int,
) -> bool:
    """Execute the common split pipeline.

    Pipeline:
        source → obiscript(splitseqs.lua) → obigrep(filter Ns) → obidistribute(batches)

    Sets FRAGMENT_SIZE and OVERLAP env vars for the Lua script.
    """
    try:
        fragments_dir.mkdir(parents=True, exist_ok=True)

        # Build the pipeline commands
        split_cmd = obiscript(SPLITSEQS_LUA)
        filter_cmd = obigrep("-v", "-s", "^[n]+$")
        dist_cmd = obidistribute(
            "-Z",
            "-n",
            str(batches),
            "-p",
            str(fragments_dir / "frg_%s.fasta.gz"),
        )

        # Save and set env vars for the Lua script
        old_env = {
            "FRAGMENT_SIZE": os.environ.get("FRAGMENT_SIZE"),
            "OVERLAP": os.environ.get("OVERLAP"),
        }
        try:
            os.environ["FRAGMENT_SIZE"] = str(frg_size)
            os.environ["OVERLAP"] = str(overlap)

            # Execute pipeline
            (source_cmd | split_cmd | filter_cmd | dist_cmd)()

        finally:
            # Restore env vars
            for k, v in old_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        return True
    except Exception as e:
        logerror(f"Pipeline failed: {e}")
        return False


def split_taxon_section(section: str, params: dict[str, int], dry_run: bool = False) -> bool:
    """Split a taxon section (pre-downloaded FASTA/GBFF files).

    Processes each genome separately with its own parts subdirectory.
    Directory name uses the source filename without extensions.
    Output: <processed_data>/<section_dir>/{genome_name}/parts/frg_{batch}.fasta.gz

    Example: Homo_sapiens-GCF_000001405.40.gbff.gz → Homo_sapiens-GCF_000001405.40/parts/

    Reads .fasta.gz and .gbff.gz files from the section directory.
    Uses stamp files to skip re-splitting if source has not changed.
    """
    dirs = section_dirs(section)
    if not dirs:
        return False

    input_dir = dirs["input_dir"]
    section_output_dir = dirs["fragments_dir"]

    loginfo(f"Section       : {section} (taxon-based, per-genome)")
    loginfo(f"Input dir     : {input_dir}")

    if not input_dir.exists():
        logwarning(f"Input directory not found: {input_dir}")
        return True  # Not an error, section is empty

    # Find all .fasta.gz and .gbff.gz files
    input_files = sorted(
        list(input_dir.glob("*.fasta.gz")) + list(input_dir.glob("*.gbff.gz"))
    )

    if not input_files:
        logwarning(f"No .fasta.gz or .gbff.gz files found in {input_dir}")
        return True

    loginfo(f"Processing {len(input_files)} genome(s)...")

    errors = 0
    for f in input_files:
        # Use filename without extensions as directory name
        # e.g., "Homo_sapiens-GCF_000001405.40.gbff.gz" → "Homo_sapiens-GCF_000001405.40"
        parts = f.name.split(".")
        # Remove .gz, then .gbff or .fasta (last 2 extensions)
        genome_key = ".".join(parts[:-2]) if len(parts) > 2 else f.stem

        genome_output_dir = section_output_dir / genome_key / "parts"

        if not needs_run(genome_output_dir, f,
                         dry_run=dry_run, label=genome_key, action=f"split {f.name}"):
            continue

        loginfo(f"  [{genome_key}] Splitting...")

        # Clean up any partial output from a previous interrupted run.
        remove_if_not_stamped(genome_output_dir)

        source_cmd = obiconvert(str(f))

        if not _run_split_pipeline(
            source_cmd,
            genome_output_dir,
            params["frg_size"],
            params["overlap"],
            params["batches"],
        ):
            errors += 1
            continue

        stamp(genome_output_dir)

    return errors == 0


def split_division_section(section: str, params: dict[str, int], dry_run: bool = False) -> bool:
    """Split a GenBank division section (filter by taxid from flat files).

    Processes each division separately with its own fragments subdirectory.
    Output: <processed_data>/<section_dir>/{division}/parts/frg_{batch}.fasta.gz

    Reads divisions and taxid from config, locates taxonomy, filters sequences.
    Uses stamp file to skip re-splitting if sources have not changed.
    """
    dirs = section_dirs(section)
    if not dirs:
        return False

    section_data = dirs["section_data"]
    section_output_dir = dirs["fragments_dir"]

    # Get taxid and divisions from config
    taxid = section_data.get("taxid")
    divisions = section_data.get("divisions", "")

    if not taxid or not divisions:
        logerror(f"Section [{section}]: missing 'taxid' or 'divisions' in config")
        return False

    loginfo(f"Section       : {section} (division-based, per-division)")
    loginfo(f"TaxID         : {taxid}")
    loginfo(f"Divisions     : {divisions}")

    # Find latest GenBank release
    release_dir = latest_release(genbank_base())

    if not release_dir:
        logerror(f"No GenBank release directory found under {genbank_root}")
        return False

    taxonomy = release_dir / "taxonomy" / "ncbi_taxonomy.tgz"
    if not taxonomy.exists():
        logerror(f"Taxonomy file not found: {taxonomy}")
        return False

    loginfo(f"Taxonomy      : {taxonomy}")

    # Process each division separately
    div_list = divisions.split()
    errors = 0

    for div in div_list:
        div_dir = release_dir / "fasta" / div
        if not div_dir.exists():
            logwarning(f"Division directory not found: {div_dir}")
            continue

        div_fragments_dir = section_output_dir / div / "parts"

        if not needs_run(div_fragments_dir, taxonomy, div_dir,
                         dry_run=dry_run, label=div, action=f"split {div_dir}"):
            continue

        loginfo(f"  [{div}] Splitting...")

        # Clean up any partial output from a previous interrupted run.
        remove_if_not_stamped(div_fragments_dir)

        source_cmd = obigrep(
            "-t",
            str(taxonomy),
            "-r",
            str(taxid),
            "--no-order",
            "--update-taxid",
            str(div_dir),
        )

        if not _run_split_pipeline(
            source_cmd,
            div_fragments_dir,
            params["frg_size"],
            params["overlap"],
            params["batches"],
        ):
            errors += 1
            continue

        stamp(div_fragments_dir)

    return errors == 0


def split_section(section: str, params: dict[str, int], dry_run: bool = False) -> bool:
    """Split a section (dispatch to taxon or division handler).

    Args:
        section: Section name
        params: Dict with frg_size, overlap, batches

    Returns:
        True on success, False on failure
    """
    cfg = config()

    # Determine section type: taxon-based or division-based
    if section in cfg.ref_genomes:
        return split_taxon_section(section, params, dry_run=dry_run)
    else:
        return split_division_section(section, params, dry_run=dry_run)


def process_split(
    sections: list[str] | None = None,
    frg_size: int | None = None,
    overlap: int | None = None,
    batches: int | None = None,
    dry_run: bool = False,
) -> int:
    """Main entry point: split genome sections into fragments.

    Args:
        sections: List of section names to split.
                 If None, uses all configured sections.
        frg_size: Override fragment size
        overlap: Override overlap
        batches: Override batch count

    Returns:
        0 on success, 1 if any section failed.
    """
    cfg = config()

    # Use provided sections or get from config
    if sections is None:
        sections = cfg.ref_taxa

    if not sections:
        logwarning("No genome sections configured")
        return 0

    # Load parameters
    params = _load_split_params(frg_size, overlap, batches)

    loginfo(f"===== Fragment splitting pipeline =====" + (" [DRY-RUN]" if dry_run else ""))
    loginfo(f"Fragment size : {params['frg_size']}")
    loginfo(f"Overlap       : {params['overlap']}")
    loginfo(f"Batches       : {params['batches']}")
    loginfo(f"Processing {len(sections)} section(s)")

    # Process each section
    errors = 0
    for section in sections:
        loginfo(f">>> Splitting: {section}")
        if split_section(section, params, dry_run=dry_run):
            loginfo(f"<<< {section} OK")
        else:
            logerror(f"<<< {section} FAILED")
            errors += 1

    if errors > 0:
        logerror(f"===== {errors} section(s) failed =====")
        return 1

    loginfo("===== All sections split successfully =====")
    return 0
