"""
skimindex.processing.filter_n_only — atomic 'filter_n_only' processing type.

Removes sequences composed entirely of N bases via obigrep.
Output kind: STREAM (chainable).
"""

from collections.abc import Callable

from skimindex.processing import OutputKind, processing_type
from skimindex.processing.data import Data, pipe_through, stream_data
from skimindex.unix.obitools import obigrep


@processing_type(output_kind=OutputKind.STREAM, output_filename="filtered.fasta")
def filter_n_only(params: dict) -> Callable[[Data], Data]:
    """Remove sequences composed only of N bases.

    Parameters (from TOML config):
        compress: Compress output with gzip (obigrep -Z), default false.

    Accepts STREAM, FILES, or DIRECTORY input — obigrep handles all
    three forms natively.
    """
    args = ["-v", "-s", "^[n]+$"]
    if params.get("compress", False):
        args.append("-Z")

    def run(input_data: Data) -> Data:
        fmt = "fasta.gz" if params.get("compress", False) else "fasta"
        return stream_data(
            pipe_through(input_data, obigrep(*args)),
            format=fmt,
            subdir=input_data.subdir,
        )
    return run
