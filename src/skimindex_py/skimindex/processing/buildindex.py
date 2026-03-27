"""
skimindex.processing.buildindex — atomic 'buildindex' processing type.

Builds a kmindex sub-index from FASTA fragments using ``kmindex build``.
Output kind: DIRECTORY (is_indexer=True).

For each dataset, generates a kmtricks FOF file — one sample per subdirectory
of the parts directory; if parts/ is flat (no subdirectories), one sample named
after the dataset — then calls ``kmindex build`` to register a sub-index in the
global meta-index.

Bloom filter sizing uses a single-hash model:

    fpr = (n / (n + m)) ^ z  →  m = ceil(n * (fpr^(-1/z) - 1))

where:

- ``n``   = number of distinct k-mers from the ``F1`` line of ntcard histogram files
- ``m``   = Bloom filter size in cells (``bloom_size`` parameter to kmindex)
- ``z``   = number of k-mers required for a positive query result (``zvalue``)
- ``fpr`` = target false positive rate
"""

import math
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from skimindex.processing import OutputKind, processing_type
from skimindex.processing.data import Data, DataKind, directory_data
from skimindex.unix.kmindex import kmindex_build


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_f1(hist_dir: Path) -> int:
    """Sum F1 (total k-mer count) across all ntcard histogram files in *hist_dir*.

    ntcard histogram format::

        1    <count_of_1-mers>
        2    <count_of_2-mers>
        ...
        F0   <estimated_distinct_kmers>
        F1   <estimated_total_kmers>

    Args:
        hist_dir: Directory containing ``*.hist`` files produced by ntcard.

    Returns:
        Sum of F1 values across all histogram files.

    Raises:
        FileNotFoundError: If no ``F1`` line is found in any histogram file.
    """
    total = 0
    for hist_file in sorted(hist_dir.glob("*.hist")):
        with open(hist_file) as fh:
            for line in fh:
                if line.startswith("F1"):
                    parts = line.split()
                    if len(parts) >= 2:
                        total += int(parts[1])
                    break
    if total == 0:
        raise FileNotFoundError(
            f"No F1 value found in histogram files under {hist_dir}"
        )
    return total


def _compute_bloom_size(n: int, z: int, fpr: float) -> int:
    """Compute the Bloom filter cell count from model parameters.

    Formula: ``m = ceil(n * (fpr^(-1/z) - 1))``

    Args:
        n:   Number of k-mers to index (F1 from ntcard).
        z:   Number of k-mers required for a positive answer.
        fpr: Target false positive rate.

    Returns:
        Bloom filter size in number of cells.
    """
    return math.ceil(n * (fpr ** (-1.0 / z) - 1))


def _build_fof(parts_dir: Path, register_as: str, fof_path: Path) -> None:
    """Generate a kmtricks FOF file from a parts directory.

    One sample per subdirectory of *parts_dir*; if *parts_dir* is flat,
    one sample named *register_as* containing all files.

    FOF format::

        sample_name : /path/file1.fa.gz ; /path/file2.fa.gz

    Args:
        parts_dir:   Directory of FASTA fragment files (output of ``distribute``).
        register_as: Sample name to use when parts_dir is flat.
        fof_path:    Destination path for the generated FOF file.

    Raises:
        FileNotFoundError: If no sequence files are found.
    """
    from skimindex.sequences import list_sequence_files

    subdirs = sorted(d for d in parts_dir.iterdir() if d.is_dir())
    lines: list[str] = []

    if subdirs:
        for subdir in subdirs:
            files = sorted(
                list_sequence_files(subdir, mode="absolute", recursive=False)
            )
            if files:
                files_str = " ; ".join(str(f) for f in files)
                lines.append(f"{subdir.name} : {files_str}")
    else:
        files = sorted(
            list_sequence_files(parts_dir, mode="absolute", recursive=False)
        )
        if files:
            files_str = " ; ".join(str(f) for f in files)
            lines.append(f"{register_as} : {files_str}")

    if not lines:
        raise FileNotFoundError(
            f"No sequence files found in parts directory {parts_dir}"
        )

    fof_path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Processing type
# ---------------------------------------------------------------------------

@processing_type(output_kind=OutputKind.DIRECTORY, is_indexer=True)
def buildindex(params: dict) -> Callable[[Data, Path, bool], Data]:
    """Build a kmindex sub-index from FASTA fragments.

    Reads FASTA parts produced by ``distribute``, optionally computes a
    Bloom filter size from ntcard histograms, and calls ``kmindex build``
    to register a sub-index in the global meta-index.

    Expected ``output`` artifact reference: ``"kmindex@idx:<role>"``
    (e.g. ``"kmindex@idx:decontamination"``).

    The global meta-index path is derived as ``output_dir.parent.parent``.
    The sub-index ``register_as`` name defaults to ``data.subdir.name``
    (e.g. the dataset directory name such as ``"Human"`` or ``"Fungi"``).
    """
    sequence_ref  = params.get("sequence")
    histogram_ref = params.get("histogram")
    kmer_size     = int(params.get("kmer_size", 29))
    zvalue        = int(params.get("zvalue", 3))
    fpr           = float(params.get("fpr", 1e-3))
    bloom_size    = params.get("bloom_size")
    if bloom_size is not None:
        bloom_size = int(bloom_size)
    threads = int(params.get("threads", 1))

    def run(input_data: Data, output_dir: Path, dry_run: bool = False) -> Data:
        from skimindex.sources import resolve_artifact

        # Resolve FASTA parts directory
        if sequence_ref is not None:
            seq_path = resolve_artifact(sequence_ref, input_data.subdir)
        elif input_data.kind == DataKind.DIRECTORY:
            seq_path = input_data.path
        else:
            raise ValueError(
                "buildindex: provide a 'sequence' artifact reference or a DIRECTORY input"
            )

        # Compute Bloom filter size
        effective_bloom_size = bloom_size
        if effective_bloom_size is None:
            if histogram_ref is None:
                raise ValueError(
                    "buildindex: provide either 'bloom_size' or 'histogram' parameter"
                )
            hist_path = resolve_artifact(histogram_ref, input_data.subdir)
            n = _read_f1(hist_path)
            effective_bloom_size = _compute_bloom_size(n, zvalue, fpr)

        # Global meta-index = grandparent of per-dataset output_dir
        # output_dir = indexes/{role}/{dataset_subdir}/kmindex/
        # global_index = indexes/{role}/
        global_index = output_dir.parent.parent
        register_as  = (
            input_data.subdir.name if input_data.subdir else output_dir.parent.name
        )

        global_index.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        if not dry_run:
            tmpdir = Path(tempfile.mkdtemp())
            try:
                fof_file = tmpdir / "samples.fof"
                _build_fof(seq_path, register_as, fof_file)
                kmindex_build(
                    index=global_index,
                    fof=fof_file,
                    run_dir="@inplace",
                    register_as=register_as,
                    kmer_size=kmer_size,
                    bloom_size=effective_bloom_size,
                    threads=threads,
                )()
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)

        return directory_data(output_dir, subdir=input_data.subdir)

    return run
