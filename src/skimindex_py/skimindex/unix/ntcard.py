"""
ntCard k-mer coverage histogram estimator wrapper.

Acceptable input formats: fastq, fasta, sam, bam (compressed: gz, bz, zip, xz).
A file containing a list of filenames (one per line) can be passed with @ prefix.

Example:
    from skimindex.unix.ntcard import ntcard, ntcard_count

    # Flexible API
    ntcard("--kmer=29", "--threads=8", "--pref=out/prefix", "parts/*.fasta.gz")()

    # Shortcut
    ntcard_count(kmer=29, threads=8, prefix=Path("out/prefix"), files=files)()
"""

from pathlib import Path

from skimindex.unix.base import LoggedBoundCommand, local


def ntcard(*args) -> LoggedBoundCommand:
    """Build an ntCard command to estimate the k-mer coverage histogram.

    Passes all arguments directly to the ``ntcard`` executable.
    Call the returned command to execute it.

    Common options:
      -t, --threads=N      parallel threads [1]
      -k, --kmer=N         k-mer length
      -g, --gap=N          gap seed length [0]
      -c, --cov=N          maximum coverage in output [1000]
      -p, --pref=STRING    prefix for output file name(s)
      -o, --output=STRING  single output file name

    Returns:
        A :class:`LoggedBoundCommand` ready to execute (call with ``()``
        or pipe with ``|``).
    """
    return local["ntcard"][args]


def ntcard_count(
    kmer: int,
    prefix: Path,
    files: list[Path],
    threads: int = 1,
    cov: int | None = None,
) -> LoggedBoundCommand:
    """Count k-mers in files and write histogram(s).

    ntcard uses *prefix* as a filename prefix — it appends _k<K>.hist to it.
    For example, prefix=Path("out/sample") produces "out/sample_k29.hist".
    The parent directory of prefix must exist before calling this function.

    Args:
        kmer:    k-mer length
        prefix:  filename prefix (including parent directory)
        files:   input sequence files
        threads: parallel threads (use >=2 when files >=2)
        cov:     maximum coverage in output (default: ntcard's 1000)
    """
    args = [
        f"--kmer={kmer}",
        f"--threads={threads}",
        f"--pref={prefix}",
    ]
    if cov is not None:
        args.append(f"--cov={cov}")
    args += [str(f) for f in files]
    return ntcard(*args)
