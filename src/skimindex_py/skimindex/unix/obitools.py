"""
OBITools wrapper module using plumbum.

Provides Pythonic interfaces to OBITools commands installed in the image.
All tools can be used with piping via plumbum's | operator.

Example:
    from skimindex.obitools import obiconvert, obigrep, obidistribute
    from plumbum import FG

    (obiconvert["input.fasta", "-t", "fasta"] |
     obigrep["-s", "^count>10"] |
     obidistribute["-o", "output_{s}.fasta"]) & FG
"""

from plumbum import local
from typing import Optional


# Core data processing tools
def obiconvert(*args, **kwargs):
    """Convert between different sequence file formats."""
    return local["obiconvert"][*args]


def obiscript(script_path: str, *args, **kwargs):
    """Execute an OBITools Lua script on sequence data."""
    return local["obiscript"]["-S", script_path, *args]


def obigrep(*args, **kwargs):
    """Filter sequences based on various criteria."""
    return local["obigrep"][*args]


def obidistribute(*args, **kwargs):
    """Distribute sequences to multiple output files."""
    return local["obidistribute"][*args]


def obisplit(*args, **kwargs):
    """Split sequences into overlapping fragments."""
    return local["obisplit"][*args]


# Sequence analysis tools
def obicount(*args, **kwargs):
    """Count occurrences of sequences."""
    return local["obicount"][*args]


def obiuniq(*args, **kwargs):
    """Remove duplicate sequences."""
    return local["obiuniq"][*args]


def obisummary(*args, **kwargs):
    """Generate summary statistics for sequences."""
    return local["obisummary"][*args]


def obijoin(*args, **kwargs):
    """Join sequence files."""
    return local["obijoin"][*args]


# Sequence cleaning and manipulation
def obiclean(*args, **kwargs):
    """Clean sequences (remove ambiguous bases, etc.)."""
    return local["obiclean"][*args]


def obicomplement(*args, **kwargs):
    """Get complement/reverse complement of sequences."""
    return local["obicomplement"][*args]


def obidemerge(*args, **kwargs):
    """Merge de-multiplexed sequences."""
    return local["obidemerge"][*args]


def obimultiplex(*args, **kwargs):
    """Demultiplex sequences by barcode."""
    return local["obimultiplex"][*args]


def obiconsensus(*args, **kwargs):
    """Build consensus sequences."""
    return local["obiconsensus"][*args]


# K-mer and matching tools
def obik(*args, **kwargs):
    """Execute an obik command (count, filter, etc)."""
    return local["obik"][*args]


def obik_count(*args, **kwargs):
    """Count k-mers (obik count)."""
    return obik("count", *args)


def obik_filter(*args, **kwargs):
    """Filter by k-mers (obik filter)."""
    return obik("filter", *args)


def obikindex(*args, **kwargs):
    """Build k-mer index."""
    return local["obikindex"][*args]


def obikmerindex(*args, **kwargs):
    """Build k-mer sequence index."""
    return local["obikmerindex"][*args]


def obikmermatch(*args, **kwargs):
    """Match sequences against k-mer index."""
    return local["obikmermatch"][*args]


def obikmersimcount(*args, **kwargs):
    """Count k-mer similarity."""
    return local["obikmersimcount"][*args]


# PCR and taxonomic tools
def obipcr(*args, **kwargs):
    """Simulate PCR with primers."""
    return local["obipcr"][*args]


def obitagpcr(*args, **kwargs):
    """Tag sequences by PCR."""
    return local["obitagpcr"][*args]


def obimicrosat(*args, **kwargs):
    """Analyze microsatellites."""
    return local["obimicrosat"][*args]


def obitaxonomy(*args, **kwargs):
    """Assign taxonomic information."""
    return local["obitaxonomy"][*args]


def obitag(*args, **kwargs):
    """Tag sequences with metadata."""
    return local["obitag"][*args]


# Utility and database tools
def obilandmark(*args, **kwargs):
    """Find sequence landmarks."""
    return local["obilandmark"][*args]


def obilowmask(*args, **kwargs):
    """Mask low-complexity regions."""
    return local["obilowmask"][*args]


def obimatrix(*args, **kwargs):
    """Generate sequence matrices."""
    return local["obimatrix"][*args]


def obicsv(*args, **kwargs):
    """Export to CSV format."""
    return local["obicsv"][*args]


def obipairing(*args, **kwargs):
    """Handle paired-end reads."""
    return local["obipairing"][*args]


def obiannotate(*args, **kwargs):
    """Annotate sequences."""
    return local["obiannotate"][*args]


def obicleandb(*args, **kwargs):
    """Clean sequence database."""
    return local["obicleandb"][*args]


def obisuperkmer(*args, **kwargs):
    """Work with super k-mers."""
    return local["obisuperkmer"][*args]


def obilowermark(*args, **kwargs):
    """Mark lower case regions."""
    return local["obilowermark"][*args]


def obirefidx(*args, **kwargs):
    """Build reference index."""
    return local["obirefidx"][*args]


def obireffamidx(*args, **kwargs):
    """Build reference family index."""
    return local["obireffamidx"][*args]


# Helper function to get help for any tool
def help(tool_name: str) -> str:
    """Get help text for a tool.

    Args:
        tool_name: Name of the tool (e.g. "obiconvert", "obik")

    Returns:
        Help text from the tool's --help output
    """
    try:
        cmd = local[tool_name]
        return cmd["--help"]()
    except Exception as e:
        return f"Error getting help for {tool_name}: {e}"
