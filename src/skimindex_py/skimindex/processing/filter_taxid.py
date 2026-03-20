"""
skimindex.processing.filter_taxid — atomic 'filter_taxid' processing type.

Filters sequences by taxonomic ID using the NCBI taxonomy archive.
Accepts FILES (directories or files) or STREAM input via obigrep.
Output kind: STREAM (chainable).
"""

from collections.abc import Callable

from skimindex.processing import OutputKind, processing_type
from skimindex.processing.data import Data, pipe_through, stream_data
from skimindex.unix.obitools import obigrep


@processing_type(output_kind=OutputKind.STREAM, output_filename="filtered.fasta")
def filter_taxid(params: dict) -> Callable[[Data], Data]:
    """Filter sequences by taxonomic ID using NCBI taxonomy.

    Parameters (from TOML config):
        taxid:    Taxonomic ID to keep (required).
        taxonomy: Path to NCBI taxonomy archive; auto-detected if absent.
        compress: Compress output with gzip (obigrep -Z), default false.

    Accepts STREAM, FILES, or DIRECTORY input — obigrep handles all
    three forms natively.
    """
    if "taxid" not in params:
        raise ValueError("filter_taxid requires a 'taxid' parameter")
    taxid = str(params["taxid"])
    compress = bool(params.get("compress", False))

    def _taxonomy() -> str:
        if "taxonomy" in params:
            return str(params["taxonomy"])
        from skimindex.sources.genbank import latest_release, taxonomy
        return str(taxonomy(latest_release()))

    def run(input_data: Data) -> Data:
        tax = _taxonomy()
        base_args = ["-t", tax, "-r", taxid, "--no-order", "--update-taxid"]
        if compress:
            base_args.append("-Z")
        cmd = pipe_through(input_data, obigrep(*base_args))
        fmt = "fasta.gz" if compress else "fasta"
        return stream_data(cmd, format=fmt, subdir=input_data.subdir)

    return run
