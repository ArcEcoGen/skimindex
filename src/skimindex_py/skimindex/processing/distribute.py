"""
skimindex.processing.distribute — atomic 'distribute' processing type.

Distributes sequences into batches of gzipped FASTA files via obidistribute.
Output kind: DIRECTORY.
"""

from pathlib import Path
from collections.abc import Callable

from skimindex.processing import OutputKind, processing_type
from skimindex.processing.data import Data, DataKind, directory_data
from skimindex.unix.obitools import obidistribute


@processing_type(output_kind=OutputKind.DIRECTORY)
def distribute(params: dict) -> Callable[[Data, Path, bool], Data]:
    """Distribute sequences into batches of gzipped FASTA files."""
    batches = int(params.get("batches", 20))

    def run(input_data: Data, output_dir: Path, dry_run: bool = False) -> Data:
        if input_data.kind != DataKind.STREAM:
            raise ValueError(f"distribute expects STREAM input, got {input_data.kind.name}")
        output_dir.mkdir(parents=True, exist_ok=True)
        dist = obidistribute(
            "-Z", "-n", str(batches),
            "-p", str(output_dir / "frg_%s.fasta.gz"),
        )
        (input_data.command | dist)()
        return directory_data(output_dir)

    return run
