"""
skimindex.processing.split — atomic 'split' processing type.

Splits reference sequences into overlapping fragments using obiscript(splitseqs.lua).
Output kind: STREAM (chainable via Data → Data interface).
"""

import os
from collections.abc import Callable

from skimindex.processing import OutputKind, processing_type
from skimindex.processing.data import Data, stream_data, to_stream_command
from skimindex.unix.obitools import obiscript

# Path to the Lua script bundled in the container image
SPLITSEQS_LUA = "/app/obiluascripts/splitseqs.lua"


@processing_type(output_kind=OutputKind.STREAM, output_filename="fragmented.fasta")
def split(params: dict) -> Callable[[Data], Data]:
    """Split reference sequences into overlapping fragments."""
    frg_size = int(params.get("size", 200))
    overlap  = int(params.get("overlap", 28))

    def run(input_data: Data) -> Data:
        cmd = to_stream_command(input_data)
        old_frag = os.environ.get("FRAGMENT_SIZE")
        old_over = os.environ.get("OVERLAP")
        try:
            os.environ["FRAGMENT_SIZE"] = str(frg_size)
            os.environ["OVERLAP"]       = str(overlap)
            return stream_data(cmd | obiscript(SPLITSEQS_LUA), format="fasta")
        finally:
            for key, old in [("FRAGMENT_SIZE", old_frag), ("OVERLAP", old_over)]:
                if old is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old

    return run
