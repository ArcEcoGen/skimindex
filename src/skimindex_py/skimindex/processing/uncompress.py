"""
skimindex.processing.uncompress — atomic 'uncompress' processing type.

Decompresses a gzipped FASTA stream using pigz (parallel gzip).
Output kind: STREAM (chainable).
"""

from collections.abc import Callable

from skimindex.processing import OutputKind, processing_type
from skimindex.processing.data import Data, DataKind, stream_data
from skimindex.unix.compress import pigz


@processing_type(output_kind=OutputKind.STREAM, output_filename="uncompressed.fasta")
def uncompress(params: dict) -> Callable[[Data], Data]:
    """Decompress a gzipped FASTA stream using pigz.

    Parameters (from TOML config):
        threads: Number of parallel decompression threads, default 1.

    Args:
        params: Processing parameters dict from the TOML config block.

    Returns:
        A callable ``run(input_data) -> Data`` that pipes the input
        stream through ``pigz -d -c`` and returns a new STREAM Data.
    """
    threads = int(params.get("threads", 1))

    def run(input_data: Data) -> Data:
        if input_data.kind != DataKind.STREAM:
            raise ValueError(
                f"uncompress expects STREAM input, got {input_data.kind.name}"
            )
        return stream_data(
            input_data.command | pigz("-d", "-p", str(threads), "-c"),
            format="fasta",
            subdir=input_data.subdir,
        )

    return run
