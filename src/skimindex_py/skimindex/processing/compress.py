"""
skimindex.processing.compress — atomic 'compress' processing type.

Compresses a FASTA stream to gzip using pigz (parallel gzip).
Output kind: STREAM (chainable).

Typical use: last step in a composite pipeline to persist a compressed
FASTA file when a STREAM step declares a ``directory``.
"""

from collections.abc import Callable

from skimindex.processing import OutputKind, processing_type
from skimindex.processing.data import Data, DataKind, stream_data
from skimindex.unix.compress import pigz


@processing_type(output_kind=OutputKind.STREAM, output_filename="compressed.fasta.gz")
def compress(params: dict) -> Callable[[Data], Data]:
    """Compress a FASTA stream to gzip using pigz.

    Parameters (from TOML config):
        level:   Compression level, 1 (fast) to 9 (best), default 6.
        threads: Number of parallel compression threads, default 1.

    Args:
        params: Processing parameters dict from the TOML config block.

    Returns:
        A callable ``run(input_data) -> Data`` that pipes the input
        stream through ``pigz -c`` and returns a new STREAM Data.
    """
    level   = int(params.get("level", 6))
    threads = int(params.get("threads", 1))

    def run(input_data: Data) -> Data:
        if input_data.kind != DataKind.STREAM:
            raise ValueError(
                f"compress expects STREAM input, got {input_data.kind.name}"
            )
        return stream_data(
            input_data.command | pigz(f"-{level}", "-p", str(threads), "-c"),
            format="fasta.gz",
            subdir=input_data.subdir,
        )

    return run
