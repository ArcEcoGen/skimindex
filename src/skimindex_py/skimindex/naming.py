"""
skimindex.naming — canonical naming rules for genome files and directories.

The `--` sequence is the reserved separator between a taxon name and an accession
in level-0 filenames.  All business logic for converting between the
(species, accession, ext, compressed) tuple and filesystem paths lives here.

Species-organised layouts (by_species=true)
-------------------------------------------
Level 0 — flat file, single accession per species:
    {Species_name}--{accession}.{ext}[.gz]
    processed_data subdir: {Species_name}/{accession}

No-accession layout (accession unknown, any source):
    processed_data subdir: {Species_name}/default

Level 1 — species subdirectory, one file per accession:
    {Species_name}/{accession}.{ext}[.gz]
    processed_data subdir: {Species_name}/{accession}

Level 2 — species+accession subdirectories, multiple files per accession:
    {Species_name}/{accession}/*  .{ext}[.gz]
    processed_data subdir: {Species_name}/{accession}

Non-species-organised layout (by_species=false)
-----------------------------------------------
    Release_{N}/fasta/{division}/gb{div}{N}.{ext}[.gz]
    processed_data subdir: {division}

Public API
----------
parse_genome_path(path)
    → (species, accession, ext, compressed)
    Accepts level-0, level-1, and level-2 paths (relative to data.directory).
    For level-0, accession is the stem part after '--'; output subdir uses "default".

genome_subdir(species, accession) → Path
    Build the canonical processed_data relative path: Species_name/accession.
    For level-0 sources pass accession="default".

output_subdir_for(path) → Path
    Convenience: parse_genome_path + genome_subdir in one call.
    Returns the correct processed_data relative subdir for any level.

parse_division_path(path) → (division, filename, ext, compressed)
    Parse a non-species-organised GenBank path to extract the division name.

genome_filename(species, accession, ext, compressed) → str
    Build the canonical level-0 filename.

canonical_species(name) → str
    Normalise a raw species/taxon name to the canonical underscore form.

scan_species_dir(directory) → Iterator[tuple[Path, Path]]
    Scan a species-organised directory and yield (absolute_file, subdir) pairs.
    subdir is the species/accession relative path, derived from directory
    structure for level-1/2, and from the filename for level-0.
"""


import re
from collections.abc import Iterator
from pathlib import Path

from skimindex.sequences import SEQUENCE_EXTENSIONS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Base extensions without leading dot, e.g. {"fasta", "gbff", "fa", "fastq"}
_BASE_EXTS: frozenset[str] = frozenset(e.lstrip(".") for e in SEQUENCE_EXTENSIONS)


def _split_ext(name: str) -> tuple[str, str, bool]:
    """Return (stem, ext, compressed) for a filename.

    ext is the base extension without dot (e.g. "gbff").
    compressed is True when the file ends with ".gz".

    Raises:
        ValueError: if the extension is not a recognised sequence extension.
    """
    compressed = name.endswith(".gz")
    if compressed:
        name = name[:-3]  # strip ".gz"

    for base_ext in sorted(_BASE_EXTS, key=len, reverse=True):  # longest first
        if name.endswith("." + base_ext):
            stem = name[: -(len(base_ext) + 1)]
            return stem, base_ext, compressed

    raise ValueError(
        f"Unrecognised sequence extension in {name!r}. "
        f"Known extensions: {sorted(_BASE_EXTS)}"
    )


# ---------------------------------------------------------------------------
# Canonical species name
# ---------------------------------------------------------------------------

def canonical_species(name: str) -> str:
    """Normalise a raw taxon/species name to the canonical underscore form.

    Rules (applied in order):
    1. Spaces → underscores.
    2. Characters that are not alphanumeric, '_', '-', or '.' are removed.
       (This includes parentheses, quotes, slashes, brackets, etc.)
    3. Leading/trailing underscores or hyphens are stripped.

    Examples:
        canonical_species("Homo sapiens")                    → "Homo_sapiens"
        canonical_species("Brassica rapa subsp. chinensis")  → "Brassica_rapa_subsp._chinensis"
        canonical_species("Mentha × piperita")               → "Mentha_piperita"
    """
    name = name.replace(" ", "_")
    name = re.sub(r"[^\w.\-]", "", name)   # \w = [a-zA-Z0-9_]
    name = re.sub(r"_+", "_", name)        # collapse consecutive underscores
    name = name.strip("_-")
    return name


# ---------------------------------------------------------------------------
# Species-organised: parse
# ---------------------------------------------------------------------------

def parse_genome_path(path: Path | str) -> tuple[str, str, str, bool]:
    """Parse a species-organised genome path into (species, accession, ext, compressed).

    The path must be relative to {data.directory}.  Three levels are recognised:

    Level 0 — flat filename with '--' separator:
        Homo_sapiens--GCF_000001405.40.gbff.gz
        → ("Homo_sapiens", "GCF_000001405.40", "gbff", True)

    Level 1 — species subdirectory, one file per accession:
        Homo_sapiens/GCF_000001405.40.gbff.gz
        → ("Homo_sapiens", "GCF_000001405.40", "gbff", True)

    Level 2 — species+accession subdirectories, multiple files:
        Homo_sapiens/GCF_000001405.40/sequence.gbff.gz
        → ("Homo_sapiens", "GCF_000001405.40", "gbff", True)

    Raises:
        ValueError: if the path cannot be parsed or has an unrecognised extension.
    """
    path = Path(path)
    depth = len(path.parts) - 1  # number of directory components

    if depth == 0:
        # Level 0: flat filename, accession after last '--'
        stem, ext, compressed = _split_ext(path.name)
        if "--" not in stem:
            raise ValueError(
                f"Cannot parse level-0 genome filename {path.name!r}: "
                f"no '--' separator found in stem {stem!r}"
            )
        species, accession = stem.rsplit("--", 1)
        return species, accession, ext, compressed

    if depth == 1:
        # Level 1: Species_name/accession.ext[.gz]
        species = path.parts[0]
        stem, ext, compressed = _split_ext(path.name)
        accession = stem
        return species, accession, ext, compressed

    # depth >= 2: Level 2: Species_name/accession/file.ext[.gz]
    species = path.parts[0]
    accession = path.parts[1]
    _, ext, compressed = _split_ext(path.name)
    return species, accession, ext, compressed


# ---------------------------------------------------------------------------
# Species-organised: build
# ---------------------------------------------------------------------------

def genome_filename(
    species: str,
    accession: str,
    ext: str,
    compressed: bool = True,
) -> str:
    """Build the canonical level-0 filename.

    Example:
        genome_filename("Homo_sapiens", "GCF_000001405.40", "gbff")
        → "Homo_sapiens--GCF_000001405.40.gbff.gz"
    """
    name = f"{species}--{accession}.{ext}"
    if compressed:
        name += ".gz"
    return name


def genome_subdir(species: str, accession: str) -> Path:
    """Build the canonical processed_data relative path: Species_name/accession.

    When no accession is available, pass accession="default" as a conventional
    placeholder for a single individual of unknown or untracked accession.

    Examples:
        genome_subdir("Homo_sapiens", "GCF_000001405.40") → Path("Homo_sapiens/GCF_000001405.40")
        genome_subdir("Betula_nana", "default")            → Path("Betula_nana/default")
    """
    return Path(species) / accession


def output_subdir_for(path: Path | str) -> Path:
    """Return the processed_data relative subdir for a species-organised source path.

    Combines parse_genome_path and genome_subdir.  The accession is always
    extracted from the path, including for level-0 flat files.

    Examples:
        output_subdir_for(Path("Homo_sapiens--GCF_000001405.40.gbff.gz"))
            → Path("Homo_sapiens/GCF_000001405.40")
        output_subdir_for(Path("Homo_sapiens/GCF_000001405.40.gbff.gz"))
            → Path("Homo_sapiens/GCF_000001405.40")
        output_subdir_for(Path("Homo_sapiens/GCF_000001405.40/seq.gbff.gz"))
            → Path("Homo_sapiens/GCF_000001405.40")
    """
    species, accession, _, _ = parse_genome_path(Path(path))
    return genome_subdir(species, accession)


# ---------------------------------------------------------------------------
# Non-species-organised: parse
# ---------------------------------------------------------------------------

def parse_division_path(path: Path | str) -> tuple[str, str, str, bool]:
    """Parse a non-species-organised GenBank path into (division, filename, ext, compressed).

    Expected layout (path relative to source-directory):
        Release_{N}/fasta/{division}/gb{div}{N}.{ext}[.gz]

    Returns:
        division  — e.g. "bct", "pln"
        filename  — e.g. "gbpln1.fasta.gz"
        ext       — base extension without dot, e.g. "fasta"
        compressed — True if ".gz"

    Example:
        parse_division_path(Path("Release_270/fasta/bct/gbbct1.fasta.gz"))
        → ("bct", "gbbct1.fasta.gz", "fasta", True)

    Raises:
        ValueError: if the path structure is not recognised.
    """
    path = Path(path)
    parts = path.parts

    # Expect at least: Release_N / fasta / {division} / filename
    if len(parts) < 4 or not parts[0].startswith("Release_") or parts[1] != "fasta":
        raise ValueError(
            f"Cannot parse division path {str(path)!r}: "
            f"expected Release_{{N}}/fasta/{{division}}/filename"
        )

    division = parts[2]
    filename = parts[-1]
    _, ext, compressed = _split_ext(filename)
    return division, filename, ext, compressed


# ---------------------------------------------------------------------------
# Species-organised: scan a directory
# ---------------------------------------------------------------------------

def scan_species_dir(directory: Path | str) -> Iterator[tuple[Path, Path]]:
    """Scan a species-organised directory and yield (absolute_file, subdir) pairs.

    subdir is the species/accession path (e.g. Homo_sapiens/GCF_000001405.40),
    derived from directory structure for level-1 and level-2, and from the
    filename (using the '--' separator) for level-0.

    Three layouts are recognised (relative to *directory*):

    Level 0 — flat file:
        {Species}--{accession}.ext  →  subdir = Species/accession

    Level 1 — species subdirectory:
        {Species}/{accession}.ext   →  subdir = Species/accession

    Level 2 — species+accession subdirectories:
        {Species}/{accession}/*.ext →  subdir = Species/accession

    Files that cannot be parsed (unknown extension, missing separator at
    level-0) are silently skipped.

    Yields:
        (absolute_path, subdir) where subdir is a relative Path.
    """
    from skimindex.sequences import list_sequence_files

    directory = Path(directory)
    for f in list_sequence_files(directory, mode="absolute", recursive=True):
        rel = f.relative_to(directory)
        depth = len(rel.parts) - 1  # number of directory components
        try:
            if depth == 0:
                # Level 0: derive subdir from filename via parse_genome_path
                species, accession, _, _ = parse_genome_path(rel)
                subdir = genome_subdir(species, accession)
            elif depth == 1:
                # Level 1: Species/accession.ext
                species = rel.parts[0]
                stem, _, _ = _split_ext(rel.name)
                subdir = genome_subdir(species, stem)
            else:
                # Level 2+: Species/accession/...
                species = rel.parts[0]
                accession = rel.parts[1]
                subdir = genome_subdir(species, accession)
        except ValueError:
            continue
        yield f, subdir
