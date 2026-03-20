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
    """Split reference sequences into overlapping fragments.

    Parameters (from TOML config):
        size:     Fragment size in bases, default 200.
        overlap:  Overlap between consecutive fragments, default 28.
        compress: Compress output with gzip (obiscript -Z), default false.
    """
    frg_size = int(params.get("size", 200))
    overlap  = int(params.get("overlap", 28))
    compress = bool(params.get("compress", False))

    script_args = [SPLITSEQS_LUA]
    if compress:
        script_args.append("-Z")

    def run(input_data: Data) -> Data:
        cmd = to_stream_command(input_data)
        old_frag = os.environ.get("FRAGMENT_SIZE")
        old_over = os.environ.get("OVERLAP")
        try:
            os.environ["FRAGMENT_SIZE"] = str(frg_size)
            os.environ["OVERLAP"]       = str(overlap)
            fmt = "fasta.gz" if compress else "fasta"
            return stream_data(cmd | obiscript(*script_args), format=fmt, subdir=input_data.subdir)
        finally:
            for key, old in [("FRAGMENT_SIZE", old_frag), ("OVERLAP", old_over)]:
                if old is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old

    return run
