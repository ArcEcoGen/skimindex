"""
skimindex.processing.filter_n_only — atomic 'filter_n_only' processing type.

Removes sequences composed entirely of N bases via obigrep.
Output kind: STREAM (chainable).
"""

from collections.abc import Callable

from skimindex.processing import OutputKind, processing_type
from skimindex.processing.data import Data, DataKind, stream_data
from skimindex.unix.obitools import obigrep


@processing_type(output_kind=OutputKind.STREAM, output_filename="filtered.fasta")
def filter_n_only(params: dict) -> Callable[[Data], Data]:
    """Remove sequences composed only of N bases."""
    def run(input_data: Data) -> Data:
        if input_data.kind != DataKind.STREAM:
            raise ValueError(f"filter_n_only expects STREAM input, got {input_data.kind.name}")
        return stream_data(
            input_data.command | obigrep("-v", "-s", "^[n]+$"),
            format="fasta",
            subdir=input_data.subdir,
        )
    return run
