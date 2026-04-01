"""
skimindex.processing.buildindex — atomic 'buildindex' processing type.

Builds a kmindex sub-index from FASTA fragments using ``kmindex build``.
Output kind: DIRECTORY (is_indexer=True).

Called once per dataset. Scans the dataset output directory recursively for
all ``parts/`` subdirectories (one sample per assembly or division) and all
``kmercount/`` subdirectories (to compute the max F1 across samples).

Bloom filter sizing uses a single-hash model:

    fpr = (n / (n + m)) ^ (z+1)  →  m = ceil(n * (fpr^(-1/(z+1)) - 1))

where:

- ``n``   = max number of distinct k-mers across all samples (max F1 from ntcard)
- ``m``   = Bloom filter size in cells (``nb_cell`` parameter to kmindex)
- ``z``   = kmindex ``--zvalue`` parameter (queries use z+1 k-mers for a positive hit)
- ``fpr`` = target false positive rate
"""

import math
import re
import shutil
from collections.abc import Callable
from pathlib import Path

from skimindex.processing import OutputKind, processing_type
from skimindex.processing.data import Data, directory_data
from skimindex.unix.kmindex import kmindex_build


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_max_f1(base_dir: Path) -> int:
    """Return the maximum F1 value across all ntcard histogram files under *base_dir*.

    Scans all ``kmercount/`` subdirectories recursively and reads every ``*.hist``
    file, returning the maximum F1 value found.

    ntcard histogram format::

        F0   <estimated_distinct_kmers>
        F1   <estimated_total_kmers>

    Args:
        base_dir: Dataset output directory to scan recursively.

    Returns:
        Maximum F1 value found across all histogram files.

    Raises:
        FileNotFoundError: If no ``F1`` line is found anywhere under *base_dir*.
    """
    max_f1 = 0
    for kmercount_dir in sorted(base_dir.rglob("kmercount")):
        if not kmercount_dir.is_dir():
            continue
        for hist_file in sorted(kmercount_dir.glob("*.hist")):
            with open(hist_file) as fh:
                for line in fh:
                    if line.startswith("F1"):
                        parts = line.split()
                        if len(parts) >= 2:
                            max_f1 = max(max_f1, int(parts[1]))
                        break
    if max_f1 == 0:
        raise FileNotFoundError(
            f"No F1 value found in histogram files under {base_dir}"
        )
    return max_f1


def _compute_bloom_size(n: int, z: int, fpr: float) -> int:
    """Compute the Bloom filter cell count from model parameters.

    Formula: ``m = ceil(n * (fpr^(-1/(z+1)) - 1))``

    The ``z`` argument is the kmindex ``--zvalue`` parameter; kmindex uses
    ``z+1`` k-mers to declare a positive hit (findere algorithm).

    Args:
        n:   Number of k-mers to index (max F1 from ntcard).
        z:   kmindex ``--zvalue`` (effective positivity threshold is z+1).
        fpr: Target false positive rate.

    Returns:
        Bloom filter size in number of cells.
    """
    return math.ceil(n * (fpr ** (-1.0 / (z + 1)) - 1))


def _build_fof(base_dir: Path, fof_path: Path, per_part: bool = False) -> None:
    """Generate a kmtricks FOF file by scanning *base_dir* for all ``parts/`` dirs.

    When *per_part* is False (default): one sample per ``parts/`` directory.
    When *per_part* is True: one sample per file inside each ``parts/`` directory;
    the sample name is the file stem without any suffixes (e.g. ``frg_0`` for
    ``frg_0.fasta.gz``).

    FOF format::

        Homo_sapiens--GCF_000001405.40 : /path/file1.fa.gz ; /path/file2.fa.gz
        frg_0 : /path/frg_0.fasta.gz
        frg_1 : /path/frg_1.fasta.gz

    Args:
        base_dir: Dataset output directory to scan recursively for ``parts/``.
        fof_path: Destination path for the generated FOF file.
        per_part: If True, emit one sample per file instead of one per directory.

    Raises:
        FileNotFoundError: If no sequence files are found under any ``parts/`` dir.
    """
    from skimindex.sequences import list_sequence_files

    lines: list[str] = []

    for parts_dir in sorted(base_dir.rglob("parts")):
        if not parts_dir.is_dir():
            continue
        files = sorted(list_sequence_files(parts_dir, mode="absolute", recursive=False))
        if not files:
            continue
        if per_part:
            for f in files:
                sample_name = f.name.split(".")[0]
                lines.append(f"{sample_name} : {f}")
        else:
            rel = parts_dir.parent.relative_to(base_dir)
            raw = "--".join(rel.parts) if rel.parts else base_dir.name
            sample_name = re.sub(r"[^A-Za-z0-9_-]", "_", raw)
            files_str = " ; ".join(str(f) for f in files)
            lines.append(f"{sample_name} : {files_str}")

    if not lines:
        raise FileNotFoundError(
            f"No sequence files found in any parts/ directory under {base_dir}"
        )

    fof_path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Processing type
# ---------------------------------------------------------------------------

@processing_type(output_kind=OutputKind.DIRECTORY, is_indexer=True)
def buildindex(params: dict) -> Callable[[Data, Path, bool], Data]:
    """Build a kmindex sub-index for an entire dataset.

    Called once per dataset. Scans the dataset output directory for all
    ``parts/`` subdirectories (one sample per assembly/division), computes
    the Bloom filter size from the maximum F1 across all samples, and calls
    ``kmindex build`` to register one sub-index in the global meta-index.

    Parameters (TOML):
        output:     Artifact ref for the FOF directory and stamp target
                    (e.g. ``"kmindex@decontamination"``).
        index:      Artifact ref for the kmindex global meta-index
                    (e.g. ``"@idx:decontamination"``).
        kmer_size:  k-mer length (default 29).
        zvalue:     k-mers required for a positive query (default 3).
        fpr:        Target false positive rate (default 1e-3).
        bloom_size: Explicit Bloom filter size; computed from F1 if omitted.
        threads:    Number of threads (default 1).
    """
    output_ref = params.get("output", "")
    index_ref  = params.get("index")
    kmer_size  = int(params.get("kmer_size", 29))
    zvalue     = int(params.get("zvalue", 3))
    fpr        = float(params.get("fpr", 1e-3))
    bloom_size = params.get("bloom_size")
    if bloom_size is not None:
        bloom_size = int(bloom_size)
    hard_min = int(params.get("hard_min", 1))
    threads  = int(params.get("threads", 1))
    verbose  = params.get("verbose")

    def run(input_data: Data, output_dir: Path, dry_run: bool = False) -> Data:
        from skimindex.sources import resolve_artifact

        # Dataset root: parent of the kmindex/ output dir
        # e.g. processed_data/decontamination/Plants/
        dataset_dir = output_dir.parent

        # Compute Bloom filter size
        effective_bloom_size = bloom_size
        if effective_bloom_size is None:
            n = _read_max_f1(dataset_dir)
            effective_bloom_size = _compute_bloom_size(n, zvalue, fpr)

        # Global meta-index
        if index_ref is not None:
            global_index = resolve_artifact(index_ref)
        elif "@" in output_ref:
            _, role_spec = output_ref.split("@", 1)
            global_index = resolve_artifact(f"@{role_spec}")
        else:
            global_index = output_dir.parent.parent

        register_as = (
            input_data.subdir.parts[0] if input_data.subdir else output_dir.parent.name
        )

        output_dir.mkdir(parents=True, exist_ok=True)

        if not dry_run:
            sub_index_dir = global_index / register_as
            if sub_index_dir.exists():
                shutil.rmtree(sub_index_dir)
            fof_file = output_dir / f"{register_as}.fof"
            _build_fof(dataset_dir, fof_file, per_part=not input_data.per_species)
            kmindex_build(
                index=global_index,
                fof=fof_file,
                run_dir=sub_index_dir,
                register_as=register_as,
                kmer_size=kmer_size,
                bloom_size=effective_bloom_size,
                hard_min=hard_min,
                threads=threads,
                verbose=verbose,
            )()

        return directory_data(output_dir, subdir=input_data.subdir)

    return run
