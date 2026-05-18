"""
skimindex.processing.lowmask — atomic 'lowmask' processing type.

Filters low-complexity sequences using obik lowmask, keeping only
high-complexity regions (--extract-high).
Output kind: STREAM (chainable via Data → Data interface).
"""

from collections.abc import Callable

from skimindex.processing import OutputKind, processing_type
from skimindex.processing.data import Data, stream_data, to_stream_command
from skimindex.unix.obitools import obik


@processing_type(output_kind=OutputKind.STREAM, output_filename="highcomplexity.fasta")
def lowmask(params: dict) -> Callable[[Data], Data]:
    """Filter low-complexity sequences, keeping only high-complexity regions.

    Parameters (from TOML config):
        kmer_size:    K-mer size for complexity estimation, default 15.
        entropy_size: Entropy window size, default 15.
        threshold:    Minimum entropy threshold (0–1), default 0.7.
    """
    kmer_size    = int(params.get("kmer_size", 15))
    entropy_size = int(params.get("entropy_size", 15))
    threshold    = float(params.get("threshold", 0.7))

    def run(input_data: Data) -> Data:
        cmd = to_stream_command(input_data)
        mask = obik(
            "lowmask",
            "--extract-high",
            "--kmer-size",    str(kmer_size),
            "--entropy-size", str(entropy_size),
            "--threshold",    str(threshold),
        )
        return stream_data(
            cmd | mask,
            format="fasta",
            subdir=input_data.subdir,
            per_species=input_data.per_species,
        )

    return run
