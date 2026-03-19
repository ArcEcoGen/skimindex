"""
skimindex.processing.filter_taxid — atomic 'filter_taxid' processing type.

Filters sequences by taxonomic ID using the NCBI taxonomy archive.
Accepts FILES (directories or files) or STREAM input via obigrep.
Output kind: STREAM (chainable).
"""

from typing import Callable

from skimindex.processing import OutputKind, processing_type
from skimindex.processing.data import Data, DataKind, stream_data
from skimindex.unix.obitools import obigrep


@processing_type(output_kind=OutputKind.STREAM, output_filename="filtered.fasta")
def filter_taxid(params: dict) -> Callable[[Data], Data]:
    """Filter sequences by taxonomic ID using NCBI taxonomy."""
    taxid = str(params["taxid"])

    def _taxonomy() -> str:
        if "taxonomy" in params:
            return str(params["taxonomy"])
        from skimindex.sources.genbank import latest_release, taxonomy
        return str(taxonomy(latest_release()))

    def run(input_data: Data) -> Data:
        tax = _taxonomy()
        base_args = ("-t", tax, "-r", taxid, "--no-order", "--update-taxid")

        if input_data.kind == DataKind.STREAM:
            cmd = input_data.command | obigrep(*base_args)
        else:
            paths = [str(p) for p in input_data.paths]
            cmd = obigrep(*base_args, *paths)

        return stream_data(cmd, format="fasta", subdir=input_data.subdir)

    return run
