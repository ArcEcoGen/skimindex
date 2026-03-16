"""
NCBI tools wrapper module using plumbum.

Provides Pythonic interfaces to NCBI CLI tools installed in the image:
  - datasets: Download datasets from NCBI (genome sequences, etc.)
  - dataformat: Convert dataset formats (e.g., JSON to FASTA)

Two API styles:
  1. Flexible: datasets("download", "genome", ...)
  2. Convenient: datasets_download_genome(...)

Example:
    from skimindex.ncbi import datasets, dataformat, help
    from plumbum import FG

    # Flexible API
    datasets("download", "genome", "--taxon", "human",
             "--reference", "--assembly-level", "chromosome") & FG

    # Convenient API
    datasets_download_genome("--taxon", "human", "--reference") & FG

    # Convert JSON output to FASTA
    dataformat("convert", "json-to-fasta",
               "--input-file", "data.json") & FG
"""

from skimindex.unix.base import local


# Main NCBI tools — flexible API
def datasets(*args):
    """Execute a datasets command.

    Common subcommands:
      - download: Download datasets from NCBI
      - summary: Get summary information about datasets

    Examples:
        datasets("download", "genome", "--taxon", "human", "--reference")
        datasets("summary", "genome", "--taxon", "Spermatophyta")
        datasets("download", "protein", "--taxon", "human")

    Full documentation: datasets --help
    """
    return local["datasets"][*args]


def dataformat(*args):
    """Execute a dataformat command.

    Common subcommands:
      - convert: Convert between formats (json-to-fasta, json-to-gff3, etc.)
      - fasta: Extract/convert to FASTA format
      - tsv: Extract/convert to TSV format
      - gff3: Extract/convert to GFF3 format

    Examples:
        dataformat("convert", "json-to-fasta", "--input-file", "data.json")
        dataformat("convert", "json-to-gff3", "--input-file", "data.json")
        dataformat("fasta", "--input-file", "data.json", "--seq-type", "nucl")

    Full documentation: dataformat --help
    """
    return local["dataformat"][*args]


# datasets download shortcuts — convenient API
def datasets_download(*args):
    """Download datasets from NCBI."""
    return datasets("download", *args)


def datasets_download_genome(*args):
    """Download genome sequences (datasets download genome)."""
    return datasets_download("genome", *args)


def datasets_download_gene(*args):
    """Download gene sequences (datasets download gene)."""
    return datasets_download("gene", *args)


def datasets_download_protein(*args):
    """Download protein sequences (datasets download protein)."""
    return datasets_download("protein", *args)


# datasets summary shortcuts — convenient API
def datasets_summary(*args):
    """Get summary information about datasets without downloading."""
    return datasets("summary", *args)


def datasets_summary_genome(*args):
    """Get summary of genome datasets."""
    return datasets_summary("genome", *args)


def datasets_summary_gene(*args):
    """Get summary of gene datasets."""
    return datasets_summary("gene", *args)


def datasets_summary_protein(*args):
    """Get summary of protein datasets."""
    return datasets_summary("protein", *args)


# dataformat shortcuts — convenient API
def dataformat_convert(*args):
    """Convert between dataset formats."""
    return dataformat("convert", *args)


def dataformat_fasta(*args):
    """Extract or convert to FASTA format."""
    return dataformat("fasta", *args)


def dataformat_tsv(*args):
    """Extract or convert to TSV format."""
    return dataformat("tsv", *args)


def dataformat_gff3(*args):
    """Extract or convert to GFF3 format."""
    return dataformat("gff3", *args)


# Helper function to get help for any tool
def help(tool_name: str) -> str:
    """Get help text for an NCBI tool."""
    try:
        parts = tool_name.split()
        cmd = local[parts[0]]
        for part in parts[1:]:
            cmd = cmd[part]
        return cmd["--help"]()
    except Exception as e:
        return f"Error getting help for {tool_name}: {e}"
