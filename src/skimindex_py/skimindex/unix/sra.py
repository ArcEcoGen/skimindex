"""
SRA Toolkit wrappers using plumbum.

Provides Pythonic interfaces to SRA Toolkit tools installed in the image:
  - prefetch:      Download SRA archives
  - fasterq-dump:  Convert SRA archives to FASTQ

Two API styles:
  1. Flexible: prefetch("ERR7254752", "-O", "/scratch/sra/")
  2. Convenient: prefetch_run("ERR7254752", output_dir="/scratch/sra/")

Example:
    from skimindex.unix.sra import prefetch_run, fasterq_dump_run
    from plumbum import FG

    prefetch_run("ERR7254752", output_dir="/scratch/sra/") & FG
    fasterq_dump_run("/scratch/sra/ERR7254752", output_dir="/scratch/sra/ERR7254752/") & FG
"""

from skimindex.unix.base import LoggedBoundCommand, local


def prefetch(*args) -> LoggedBoundCommand:
    """Flexible wrapper for prefetch.

    Example:
        prefetch("ERR7254752", "-O", "/scratch/sra/")()
    """
    return local["prefetch"][args]


def prefetch_run(accession: str, output_dir: str) -> LoggedBoundCommand:
    """Download an SRA run accession into output_dir.

    Example:
        prefetch_run("ERR7254752", output_dir="/scratch/sra/")()
    """
    return prefetch(accession, "-O", output_dir)


def fasterq_dump(*args) -> LoggedBoundCommand:
    """Flexible wrapper for fasterq-dump.

    Example:
        fasterq_dump("/scratch/sra/ERR7254752", "-O", "/scratch/sra/ERR7254752/")()
    """
    return local["fasterq-dump"][args]


def fasterq_dump_run(
    sra_path: str,
    output_dir: str,
    threads: int = 4,
    temp_dir: str | None = None,
) -> LoggedBoundCommand:
    """Convert an SRA archive to FASTQ files.

    temp_dir defaults to output_dir so all intermediate files stay in /scratch.

    Example:
        fasterq_dump_run("/scratch/sra/ERR7254752", "/scratch/sra/ERR7254752/", threads=8)()
    """
    if temp_dir is None:
        temp_dir = output_dir
    return fasterq_dump(sra_path, "-O", output_dir, "-t", temp_dir, "-e", str(threads))
