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

Output:
  <processed_data>/<section_dir>/fragments/frg_{batch}.fasta.gz
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from skimindex.config import config
from skimindex.log import loginfo, logwarning, logerror
from skimindex.unix.obitools import obiconvert, obigrep, obiscript, obidistribute


# Path to the Lua script for sequence splitting
SPLITSEQS_LUA = "/app/obiluascripts/splitseqs.lua"


def list_sections() -> str:
    """List available genome sections (all taxa) as CSV from config."""
    cfg = config()
    sections = cfg.ref_taxa
    return ",".join(sections) if sections else ""


def _load_split_params(
    frg_size_opt: Optional[int] = None,
    overlap_opt: Optional[int] = None,
    batches_opt: Optional[int] = None,
) -> Dict[str, int]:
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


def _load_section_dirs(section: str) -> Optional[Dict[str, Any]]:
    """Load input/output directories for a section from config.

    Returns:
        Dict with: rel_dir, input_dir (genbank), fragments_dir (processed_data)
        None if section not found
    """
    cfg = config()
    section_data = cfg.data.get(section, {})

    if not section_data:
        logerror(f"Section [{section}] not found in config")
        return None

    genbank_root = cfg.get("directories", "genbank", "/genbank")
    processed_root = cfg.get("directories", "processed_data", "/processed_data")

    rel_dir = section_data.get("directory", section.lower())

    input_dir = Path(genbank_root) / rel_dir
    fragments_dir = Path(processed_root) / rel_dir / "fragments"

    return {
        "rel_dir": rel_dir,
        "input_dir": input_dir,
        "fragments_dir": fragments_dir,
        "section_data": section_data,
    }


def _find_latest_release(genbank_root: Path) -> Optional[Path]:
    """Find the most recent Release_* directory under genbank_root.

    Returns:
        Path to Release_* directory, or None if not found
    """
    try:
        releases = sorted(
            genbank_root.glob("Release_*"),
            key=lambda p: int(p.name.split("_")[1]) if "_" in p.name else 0,
        )
        return releases[-1] if releases else None
    except Exception as e:
        logerror(f"Error finding release directory: {e}")
        return None


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
        filter_cmd = obigrep("-v", "-s", "^[Nn]+$")
        dist_cmd_args = [
            "-Z",  # gzip output
            "-n", str(batches),
            "-p", str(fragments_dir / "frg_%s.fasta.gz"),
        ]

        # Save and set env vars for the Lua script
        old_env = {
            "FRAGMENT_SIZE": os.environ.get("FRAGMENT_SIZE"),
            "OVERLAP": os.environ.get("OVERLAP"),
        }
        try:
            os.environ["FRAGMENT_SIZE"] = str(frg_size)
            os.environ["OVERLAP"] = str(overlap)

            # Execute pipeline
            dist_cmd = obidistribute(*dist_cmd_args)
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


def split_taxon_section(section: str, params: Dict[str, int]) -> bool:
    """Split a taxon section (pre-downloaded FASTA/GBFF files).

    Reads .fasta.gz and .gbff.gz files from the section directory.
    """
    dirs = _load_section_dirs(section)
    if not dirs:
        return False

    input_dir = dirs["input_dir"]
    fragments_dir = dirs["fragments_dir"]

    loginfo(f"Section       : {section} (taxon-based)")
    loginfo(f"Input dir     : {input_dir}")
    loginfo(f"Output dir    : {fragments_dir}")

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

    loginfo(f"Splitting {len(input_files)} file(s) into {params['batches']} batches...")

    # Create source command: obiconvert on all input files
    source_cmd = obiconvert(*[str(f) for f in input_files])

    return _run_split_pipeline(
        source_cmd,
        fragments_dir,
        params["frg_size"],
        params["overlap"],
        params["batches"],
    )


def split_division_section(section: str, params: Dict[str, int]) -> bool:
    """Split a GenBank division section (filter by taxid from flat files).

    Reads divisions and taxid from config, locates taxonomy, filters sequences.
    """
    dirs = _load_section_dirs(section)
    if not dirs:
        return False

    section_data = dirs["section_data"]
    fragments_dir = dirs["fragments_dir"]

    # Get taxid and divisions from config
    taxid = section_data.get("taxid")
    divisions = section_data.get("divisions", "")

    if not taxid or not divisions:
        logerror(
            f"Section [{section}]: missing 'taxid' or 'divisions' in config"
        )
        return False

    loginfo(f"Section       : {section} (division-based)")
    loginfo(f"TaxID         : {taxid}")
    loginfo(f"Divisions     : {divisions}")
    loginfo(f"Output dir    : {fragments_dir}")

    # Find latest GenBank release
    genbank_root = Path(config().get("directories", "genbank", "/genbank"))
    release_dir = _find_latest_release(genbank_root)

    if not release_dir:
        logerror(f"No GenBank release directory found under {genbank_root}")
        return False

    taxonomy = release_dir / "taxonomy" / "ncbi_taxonomy.tgz"
    if not taxonomy.exists():
        logerror(f"Taxonomy file not found: {taxonomy}")
        return False

    loginfo(f"Taxonomy      : {taxonomy}")

    # Find division directories
    div_list = divisions.split()
    div_dirs = []
    for div in div_list:
        div_dir = release_dir / "fasta" / div
        if div_dir.exists():
            div_dirs.append(str(div_dir))
        else:
            logwarning(f"Division directory not found: {div_dir}")

    if not div_dirs:
        logwarning(f"No division directories found for {divisions}")
        return True

    loginfo(f"Splitting into {params['batches']} batches...")

    # Create source command: obigrep to filter by taxid
    source_cmd = obigrep("-t", str(taxonomy), "-r", str(taxid), *div_dirs)

    return _run_split_pipeline(
        source_cmd,
        fragments_dir,
        params["frg_size"],
        params["overlap"],
        params["batches"],
    )


def split_section(section: str, params: Dict[str, int]) -> bool:
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
        # Taxon section (from NCBI download)
        return split_taxon_section(section, params)
    else:
        # Division section (GenBank division)
        return split_division_section(section, params)


def process_split(
    sections: List[str] = None,
    frg_size: Optional[int] = None,
    overlap: Optional[int] = None,
    batches: Optional[int] = None,
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

    loginfo(f"===== Fragment splitting pipeline =====")
    loginfo(f"Fragment size : {params['frg_size']}")
    loginfo(f"Overlap       : {params['overlap']}")
    loginfo(f"Batches       : {params['batches']}")
    loginfo(f"Processing {len(sections)} section(s)")

    # Process each section
    errors = 0
    for section in sections:
        loginfo(f">>> Splitting: {section}")
        if split_section(section, params):
            loginfo(f"<<< {section} OK")
        else:
            logerror(f"<<< {section} FAILED")
            errors += 1

    if errors > 0:
        logerror(f"===== {errors} section(s) failed =====")
        return 1

    loginfo("===== All sections split successfully =====")
    return 0
