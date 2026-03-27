"""
kmindex wrapper module using plumbum.

Provides a Pythonic interface to ``kmindex`` v0.6.0 — a tool for indexing
and querying kmtricks Bloom filter / counting Bloom filter matrices.

Two API styles:

1. **Flexible** — pass any subcommand and flags directly::

       kmindex("build", "-i", "/indexes/main", "-f", "fof.txt", ...)

2. **Shortcuts** — one function per subcommand with typed keyword arguments::

       kmindex_build(index="/indexes/main", fof="fof.txt",
                     run_dir="@inplace", register_as="human",
                     kmer_size=31, threads=8)

All functions return a plumbum ``BoundCommand`` that can be run with
``& FG``, ``& BG``, or piped with ``|``.

Example:
    ```python
    from skimindex.unix.kmindex import kmindex_build, kmindex_query
    from plumbum import FG

    kmindex_build(
        index="/indexes/decontam",
        fof="samples.fof",
        run_dir="@inplace",
        register_as="bacteria",
        kmer_size=29,
        threads=16,
    ) & FG

    kmindex_query(
        index="/indexes/decontam",
        fastx="sample.fa.gz",
        output="results/",
        zvalue=3,
        threads=8,
    ) & FG
    ```
"""

from pathlib import Path

from skimindex.unix.base import LoggedBoundCommand, local


def kmindex(*args: str) -> LoggedBoundCommand:
    """Execute a kmindex command with arbitrary arguments.

    Args:
        *args: Subcommand and flags, e.g. ``"build"``, ``"-i"``, ``"/path"``.

    Returns:
        A plumbum ``BoundCommand`` ready to execute.
    """
    return local["kmindex"][args]


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def kmindex_build(
    *,
    index: str | Path,
    fof: str | Path,
    run_dir: str | Path = "@inplace",
    register_as: str,
    from_index: str | None = None,
    km_path: str | Path | None = None,
    kmer_size: int | None = None,
    minim_size: int | None = None,
    hard_min: int | None = None,
    nb_partitions: int | None = None,
    bloom_size: int | None = None,
    nb_cell: int | None = None,
    bitw: int | None = None,
    threads: int | None = None,
    cpr: bool = False,
    verbose: str | None = None,
) -> LoggedBoundCommand:
    """Build a kmindex sub-index from a kmtricks file-of-files.

    Args:
        index: Global index path (``-i``).
        fof: kmtricks input file — file-of-files (``-f``).
        run_dir: kmtricks runtime directory.  Use ``"@inplace"`` to build
            inside the global index directory (``-d``).
        register_as: Name under which the sub-index is registered (``-r``).
        from_index: Re-use parameters from a pre-registered sub-index
            (``--from``).
        km_path: Path to the ``kmtricks`` binary; searched in ``$PATH`` if
            omitted (``--km-path``).
        kmer_size: k-mer length in ``[8, 255]``, default 31 (``-k``).
        minim_size: Minimizer length in ``[4, 15]``, default 10 (``-m``).
        hard_min: Minimum abundance to keep a k-mer, default 2
            (``--hard-min``).
        nb_partitions: Number of partitions, 0 = auto (``--nb-partitions``).
        bloom_size: Bloom filter size for presence/absence indexing
            (``--bloom-size``).
        nb_cell: Number of cells per counting Bloom filter for abundance
            indexing (``--nb-cell``).
        bitw: Bits per cell for abundance indexing, default 2 (``--bitw``).
            Abundances are stored as log₂ classes: ``2^bitw`` classes.
        threads: Number of threads (``-t``).
        cpr: Compress intermediate files (``--cpr``).
        verbose: Verbosity level: ``debug``, ``info``, ``warning``, ``error``
            (``-v``).

    Returns:
        A plumbum ``BoundCommand`` ready to execute.
    """
    args: list[str] = ["build", "--index", str(index), "--fof", str(fof),
                        "--run-dir", str(run_dir), "--register-as", register_as]
    if from_index is not None:
        args += ["--from", from_index]
    if km_path is not None:
        args += ["--km-path", str(km_path)]
    if kmer_size is not None:
        args += ["--kmer-size", str(kmer_size)]
    if minim_size is not None:
        args += ["--minim-size", str(minim_size)]
    if hard_min is not None:
        args += ["--hard-min", str(hard_min)]
    if nb_partitions is not None:
        args += ["--nb-partitions", str(nb_partitions)]
    if bloom_size is not None:
        args += ["--bloom-size", str(bloom_size)]
    if nb_cell is not None:
        args += ["--nb-cell", str(nb_cell)]
    if bitw is not None:
        args += ["--bitw", str(bitw)]
    if threads is not None:
        args += ["--threads", str(threads)]
    if cpr:
        args += ["--cpr"]
    if verbose is not None:
        args += ["--verbose", verbose]
    return kmindex(*args)


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

def kmindex_register(
    *,
    global_index: str | Path,
    name: str | None = None,
    index_path: str | Path | None = None,
    from_file: str | Path | None = None,
    mode: str = "symlink",
    verbose: str | None = None,
) -> LoggedBoundCommand:
    """Register an existing kmtricks run as a sub-index.

    Either provide ``name`` + ``index_path`` for a single sub-index, or
    ``from_file`` for batch registration.

    Args:
        global_index: Global index path (``-i``).
        name: Sub-index name; ignored when ``from_file`` is set (``-n``).
        index_path: Path to a kmtricks run directory; ignored when
            ``from_file`` is set (``-p``).
        from_file: Tab-separated file with ``index_name<tab>index_path``
            per line (``-f``).
        mode: Registration mode: ``symlink``, ``copy``, or ``move``
            (``-m``), default ``symlink``.
        verbose: Verbosity level (``-v``).

    Returns:
        A plumbum ``BoundCommand`` ready to execute.
    """
    args: list[str] = ["register", "-i", str(global_index), "-m", mode]
    if name is not None:
        args += ["-n", name]
    if index_path is not None:
        args += ["-p", str(index_path)]
    if from_file is not None:
        args += ["-f", str(from_file)]
    if verbose is not None:
        args += ["-v", verbose]
    return kmindex(*args)


# ---------------------------------------------------------------------------
# query / query2
# ---------------------------------------------------------------------------

def kmindex_query(
    *,
    index: str | Path,
    fastx: str | Path,
    output: str | Path = "output",
    names: str | None = None,
    zvalue: int | None = None,
    threshold: float | None = None,
    single_query: str | None = None,
    format: str | None = None,
    batch_size: int | None = None,
    aggregate: bool = False,
    fast: bool = False,
    threads: int | None = None,
    verbose: str | None = None,
) -> LoggedBoundCommand:
    """Query a kmindex index with a FASTA/FASTQ file.

    Use :func:`kmindex_query2` instead when the index contains hundreds or
    thousands of sub-indexes.

    Args:
        index: Global index path (``-i``).
        fastx: Input FASTA/FASTQ file, supports gz/bzip2 (``-q``).
        output: Output directory, default ``"output"`` (``-o``).
        names: Comma-separated list of sub-indexes to query; all if omitted
            (``-n``).
        zvalue: Findere z value — index s-mers, query ``(s+z)``-mers.
            Enables approximate matching against an index built with size
            ``K`` by querying with size ``K+z`` (``-z``).
        threshold: Minimum shared k-mer fraction in ``[0.0, 1.0]`` to
            report a hit (``-r``).
        single_query: Query identifier — treat all sequences as a single
            query (``-s``).
        format: Output format: ``json``, ``matrix``, ``json_vec``,
            ``jsonl``, ``jsonl_vec`` (``-f``).
        batch_size: Size of query batches; 0 = auto (``-b``).
        aggregate: Aggregate batch results into one file (``-a``).
        fast: Keep more pages in cache for faster repeated queries
            (``--fast``).
        threads: Number of threads (``-t``).
        verbose: Verbosity level (``-v``).

    Returns:
        A plumbum ``BoundCommand`` ready to execute.
    """
    args: list[str] = ["query", "-i", str(index), "-q", str(fastx),
                        "-o", str(output)]
    if names is not None:
        args += ["-n", names]
    if zvalue is not None:
        args += ["-z", str(zvalue)]
    if threshold is not None:
        args += ["-r", str(threshold)]
    if single_query is not None:
        args += ["-s", single_query]
    if format is not None:
        args += ["-f", format]
    if batch_size is not None:
        args += ["-b", str(batch_size)]
    if aggregate:
        args += ["-a"]
    if fast:
        args += ["--fast"]
    if threads is not None:
        args += ["-t", str(threads)]
    if verbose is not None:
        args += ["-v", verbose]
    return kmindex(*args)


def kmindex_query2(
    *,
    index: str | Path,
    fastx: str | Path,
    output: str | Path = "output",
    names: str | None = None,
    zvalue: int | None = None,
    threshold: float | None = None,
    single_query: str | None = None,
    format: str | None = None,
    batch_size: int | None = None,
    aggregate: bool = False,
    fast: bool = False,
    threads: int | None = None,
    verbose: str | None = None,
) -> LoggedBoundCommand:
    """Query a kmindex index — optimised for large numbers of sub-indexes.

    Drop-in replacement for :func:`kmindex_query` when the global index
    contains hundreds or thousands of sub-indexes.

    Args:
        index: Global index path (``-i``).
        fastx: Input FASTA/FASTQ file, supports gz/bzip2 (``-q``).
        output: Output directory, default ``"output"`` (``-o``).
        names: Comma-separated list of sub-indexes to query (``-n``).
        zvalue: Findere z value (``-z``).
        threshold: Minimum shared k-mer fraction (``-r``).
        single_query: Treat all sequences as a single query (``-s``).
        format: Output format (``-f``).
        batch_size: Batch size; 0 = auto (``-b``).
        aggregate: Aggregate batch results (``-a``).
        fast: Keep more pages in cache (``--fast``).
        threads: Number of threads (``-t``).
        verbose: Verbosity level (``-v``).

    Returns:
        A plumbum ``BoundCommand`` ready to execute.
    """
    args: list[str] = ["query2", "-i", str(index), "-q", str(fastx),
                        "-o", str(output)]
    if names is not None:
        args += ["-n", names]
    if zvalue is not None:
        args += ["-z", str(zvalue)]
    if threshold is not None:
        args += ["-r", str(threshold)]
    if single_query is not None:
        args += ["-s", single_query]
    if format is not None:
        args += ["-f", format]
    if batch_size is not None:
        args += ["-b", str(batch_size)]
    if aggregate:
        args += ["-a"]
    if fast:
        args += ["--fast"]
    if threads is not None:
        args += ["-t", str(threads)]
    if verbose is not None:
        args += ["-v", verbose]
    return kmindex(*args)


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------

def kmindex_merge(
    *,
    index: str | Path,
    new_name: str,
    new_path: str | Path,
    to_merge: list[str],
    rename: str | None = None,
    delete_old: bool = False,
    threads: int | None = None,
    verbose: str | None = None,
) -> LoggedBoundCommand:
    """Merge sub-indexes into a new combined sub-index.

    Sub-indexes containing identical sample identifiers cannot be merged
    without renaming — use the ``rename`` parameter in that case.

    Args:
        index: Global index path (``-i``).
        new_name: Name for the merged sub-index (``-n``).
        new_path: Output path for the merged sub-index (``-p``).
        to_merge: Sub-index names to merge, passed as a comma-separated
            list (``-m``).
        rename: Rename strategy for sample identifiers (``-r``).
            Three forms:

            - ``"f:id1.txt,id2.txt,..."`` — one identifier file per
              sub-index (one id per line).
            - ``"s:prefix_{}"`` — format string (``{}`` replaced by an
              integer).
            - Manual editing of ``kmtricks.fof`` files (not recommended).
        delete_old: Delete old sub-index files after merging (``-d``).
        threads: Number of threads (``-t``).
        verbose: Verbosity level (``-v``).

    Returns:
        A plumbum ``BoundCommand`` ready to execute.
    """
    args: list[str] = ["merge", "-i", str(index),
                        "-n", new_name,
                        "-p", str(new_path),
                        "-m", ",".join(to_merge)]
    if rename is not None:
        args += ["-r", rename]
    if delete_old:
        args += ["-d"]
    if threads is not None:
        args += ["-t", str(threads)]
    if verbose is not None:
        args += ["-v", verbose]
    return kmindex(*args)


# ---------------------------------------------------------------------------
# index-infos
# ---------------------------------------------------------------------------

def kmindex_index_infos(
    *,
    index: str | Path,
    verbose: str | None = None,
) -> LoggedBoundCommand:
    """Print information about a kmindex global index.

    Args:
        index: Global index path (``-i``).
        verbose: Verbosity level (``-v``).

    Returns:
        A plumbum ``BoundCommand`` ready to execute.
    """
    args: list[str] = ["index-infos", "-i", str(index)]
    if verbose is not None:
        args += ["-v", verbose]
    return kmindex(*args)


# ---------------------------------------------------------------------------
# compress
# ---------------------------------------------------------------------------

def kmindex_compress(index: str | Path, *args: str) -> LoggedBoundCommand:
    """Compress a kmindex index.

    Args:
        index: Global index path (``-i``).
        *args: Additional flags passed directly to ``kmindex compress``.

    Returns:
        A plumbum ``BoundCommand`` ready to execute.
    """
    return kmindex("compress", "-i", str(index), *args)


# ---------------------------------------------------------------------------
# sum-index / sum-query  (experimental)
# ---------------------------------------------------------------------------

def kmindex_sum_index(*args: str) -> LoggedBoundCommand:
    """Build a lightweight summarised index (experimental).

    At query time reports only the number of samples containing each k-mer.

    Args:
        *args: Flags passed directly to ``kmindex sum-index``.

    Returns:
        A plumbum ``BoundCommand`` ready to execute.
    """
    return kmindex("sum-index", *args)


def kmindex_sum_query(*args: str) -> LoggedBoundCommand:
    """Query a summarised index (experimental).

    Args:
        *args: Flags passed directly to ``kmindex sum-query``.

    Returns:
        A plumbum ``BoundCommand`` ready to execute.
    """
    return kmindex("sum-query", *args)
