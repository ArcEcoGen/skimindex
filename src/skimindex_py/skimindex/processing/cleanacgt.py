"""
skimindex.processing.cleanacgt — atomic 'cleanacgt' processing type.

Splits sequences into pure-ACGT segments by cutting on any non-ACGT
character (N, IUPAC ambiguity codes, gaps, …) using cleanacgt.lua.
Output kind: STREAM (chainable via Data → Data interface).
"""

from collections.abc import Callable

from skimindex.processing import OutputKind, processing_type
from skimindex.processing.data import Data, stream_data, to_stream_command
from skimindex.unix.obitools import obiscript

CLEANACGT_LUA = "/app/obiluascripts/cleanacgt.lua"


@processing_type(output_kind=OutputKind.STREAM, output_filename="cleanacgt.fasta")
def cleanacgt(params: dict) -> Callable[[Data], Data]:
    """Split sequences into contiguous [ACGTacgt]+ segments.

    Non-ACGT characters act as split points; each resulting pure-ACGT
    run is emitted as a separate sequence.  No parameters required.
    """
    def run(input_data: Data) -> Data:
        cmd = to_stream_command(input_data)
        return stream_data(
            cmd | obiscript(CLEANACGT_LUA),
            format="fasta",
            subdir=input_data.subdir,
            per_species=input_data.per_species,
        )

    return run
