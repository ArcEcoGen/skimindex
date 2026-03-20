"""
Sequence file discovery utilities.

Provides list_sequence_files() to enumerate sequence files (.fasta, .gbff, …)
in a directory.  Both compressed (.gz) and uncompressed variants are discovered.
Three path modes are available:

  relative  — path relative to the given directory
              e.g.  Homo_sapiens-GCF_000001405.40.gbff.gz
  absolute  — full absolute path
              e.g.  /genbank/Plants/Homo_sapiens-GCF_000001405.40.gbff.gz
  prefixed  — directory name prepended to the relative path
              e.g.  Plants/Homo_sapiens-GCF_000001405.40.gbff.gz

species_list() discovers species under the ``species/`` subdirectory of a
genome data directory (raw or processed).  The layout is expected to be::

    {directory}/species/{Species_name}/{individual}/...

Example:
    from skimindex.sequences import list_sequence_files, species_list

    files = list_sequence_files("/genbank/Plants", mode="prefixed")
    for f in files:
        print(f)   # Plants/Homo_sapiens-GCF_000001405.40.gbff.gz

    species = species_list("/raw_data/genomes_15x", mode="absolute")
    for name, path in species.items():
        print(name, path)  # Betula_nana  /raw_data/genomes_15x/species/Betula_nana
"""

from pathlib import Path
from collections.abc import Callable, Iterator
from typing import Literal

DataType = Literal["raw", "processed"]

PathLike = str | Path

# Base extensions (without .gz) — both compressed and uncompressed variants are found.
SEQUENCE_EXTENSIONS: tuple = (".fasta", ".gbff", ".fa", ".fastq")

PathMode = Literal["relative", "absolute", "prefixed"]


def _resolve_directory(directory: PathLike) -> Path:
    """Resolve *directory* to an absolute Path, raising FileNotFoundError if absent."""
    d = Path(directory).resolve()
    if not d.exists():
        raise FileNotFoundError(f"Directory not found: {d}")
    if not d.is_dir():
        raise NotADirectoryError(f"Not a directory: {d}")
    return d


def _mode_fn(d: Path, mode: PathMode) -> Callable[[Path], Path]:
    """Return a function that converts an absolute path to the requested *mode*."""
    if mode not in ("relative", "absolute", "prefixed"):
        raise ValueError(f"mode must be 'relative', 'absolute' or 'prefixed', got {mode!r}")
    if mode == "absolute":
        return lambda p: p
    if mode == "relative":
        return lambda p: p.relative_to(d)
    return lambda p: Path(d.name) / p.relative_to(d)


def list_sequence_files(
    directory: PathLike,
    mode: PathMode = "relative",
    extensions: tuple = SEQUENCE_EXTENSIONS,
    recursive: bool = False,
    compressed: bool = True,
    uncompressed: bool = True,
) -> list[Path]:
    """Return a sorted list of sequence files found in *directory*.

    For each extension (e.g. ".fasta"), both the compressed (".fasta.gz") and
    uncompressed (".fasta") variants are searched, controlled by the
    *compressed* and *uncompressed* flags.

    Args:
        directory:    Directory to search.
        mode:         How to express the returned paths:
                        "relative" — relative to *directory*
                        "absolute" — full absolute path
                        "prefixed" — directory name prepended (e.g. Plants/file.gbff.gz)
        extensions:   Tuple of base suffixes without .gz (default: SEQUENCE_EXTENSIONS).
        recursive:    If True, search subdirectories recursively.
        compressed:   Include compressed variants (e.g. .fasta.gz).
        uncompressed: Include uncompressed variants (e.g. .fasta).

    Returns:
        Sorted list of Path objects.

    Raises:
        FileNotFoundError: if *directory* does not exist.
        ValueError: if *mode* is not one of the three allowed values.
    """
    d = _resolve_directory(directory)
    apply = _mode_fn(d, mode)
    glob = d.rglob if recursive else d.glob

    patterns = []
    for ext in extensions:
        if uncompressed:
            patterns.append(f"*{ext}")
        if compressed:
            patterns.append(f"*{ext}.gz")

    files: Iterator[Path] = (
        f for pattern in patterns
        for f in glob(pattern)
        if f.is_file()
    )

    return sorted(apply(f) for f in files)


def species_list(
    directory: PathLike,
    mode: PathMode = "relative",
) -> dict[str, Path]:
    """Return a mapping of species name → species directory for a genome dataset.

    Expects the layout::

        {directory}/species/{Species_name}/{individual}/...

    Args:
        directory: Root of the genome dataset (e.g. ``raw_data/genomes_15x``).
        mode:      How to express the returned paths:
                     ``"relative"`` — relative to *directory*
                     ``"absolute"`` — full absolute path
                     ``"prefixed"`` — directory name prepended
                                      (e.g. ``genomes_15x/species/Betula_nana``)

    Returns:
        Sorted dict ``{species_name: path}`` where *species_name* is the
        directory name (e.g. ``"Betula_nana"``) and *path* follows *mode*.

    Raises:
        FileNotFoundError: if *directory* does not exist.
        ValueError: if *mode* is not one of the three allowed values.
    """
    d = _resolve_directory(directory)
    apply = _mode_fn(d, mode)

    species_root = d / "species"
    if not species_root.exists():
        return {}

    return {
        entry.name.replace("_", " "): apply(entry)
        for entry in sorted(species_root.iterdir())
        if entry.is_dir()
    }


def genome_species_list(
    mode: PathMode = "relative",
    data_type: DataType = "raw",
) -> dict[str, Path]:
    """Return the species list for the genome dataset, using paths from config.

    Reads ``[genomes] directory`` and the appropriate base directory
    (``raw_data`` or ``processed_data`` from ``[local_directories]``) to build
    the path, then delegates to :func:`species_list`.

    Args:
        mode:      Path mode — ``"relative"``, ``"absolute"`` or ``"prefixed"``.
        data_type: Which data tree to inspect:
                     ``"raw"``       — raw sequencing reads (``/raw_data/…``)
                     ``"processed"`` — pipeline outputs    (``/processed_data/…``)

    Returns:
        Sorted dict ``{species_name: path}`` (species names use spaces, not underscores).

    Raises:
        FileNotFoundError: if the resolved genome directory does not exist.
        ValueError: if *mode* is invalid.
    """
    from skimindex.config import config, processed_data_dir, raw_data_dir  # local — avoids circular dep

    genome_subdir = config().get("genomes", "directory", "genomes_15x")
    base = raw_data_dir() if data_type == "raw" else processed_data_dir()
    return species_list(base / genome_subdir, mode=mode)
