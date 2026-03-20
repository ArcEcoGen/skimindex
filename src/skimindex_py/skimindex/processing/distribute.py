"""
skimindex.processing.distribute — atomic 'distribute' processing type.

Distributes sequences into batches of gzipped FASTA files via obidistribute.
Output kind: DIRECTORY.
"""

from pathlib import Path
from collections.abc import Callable

from skimindex.processing import OutputKind, processing_type
from skimindex.processing.data import Data, directory_data, pipe_through
from skimindex.unix.obitools import obidistribute


@processing_type(output_kind=OutputKind.DIRECTORY)
def distribute(params: dict) -> Callable[[Data, Path, bool], Data]:
    """Distribute sequences into batches of FASTA files.

    Parameters (from TOML config):
        batches:  Number of output files, default 20.
        compress: Compress output with gzip (obidistribute -Z), default true.

    Accepts STREAM, FILES, or DIRECTORY input — obidistribute handles all
    three forms natively.
    """
    batches  = int(params.get("batches", 20))
    compress = bool(params.get("compress", True))

    def run(input_data: Data, output_dir: Path, dry_run: bool = False) -> Data:
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = "fasta.gz" if compress else "fasta"
        dist_args = ["-n", str(batches), "-p", str(output_dir / f"frg_%s.{suffix}")]
        if compress:
            dist_args.insert(0, "-Z")
        dist = obidistribute(*dist_args)
        pipe_through(input_data, dist)()
        return directory_data(output_dir)

    return run
