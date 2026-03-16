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

from skimindex.unix.base import local


# Core data processing tools
def obiconvert(*args):
    """Convert between different sequence file formats."""
    return local["obiconvert"][*args]


def obiscript(script_path: str, *args):
    """Execute an OBITools Lua script on sequence data."""
    return local["obiscript"]["-S", script_path, *args]


def obigrep(*args):
    """Filter sequences based on various criteria."""
    return local["obigrep"][*args]


def obidistribute(*args):
    """Distribute sequences to multiple output files."""
    return local["obidistribute"][*args]


def obisplit(*args):
    """Split sequences into overlapping fragments."""
    return local["obisplit"][*args]


# Sequence analysis tools
def obicount(*args):
    """Count occurrences of sequences."""
    return local["obicount"][*args]


def obiuniq(*args):
    """Remove duplicate sequences."""
    return local["obiuniq"][*args]


def obisummary(*args):
    """Generate summary statistics for sequences."""
    return local["obisummary"][*args]


def obijoin(*args):
    """Join sequence files."""
    return local["obijoin"][*args]


# Sequence cleaning and manipulation
def obiclean(*args):
    """Clean sequences (remove ambiguous bases, etc.)."""
    return local["obiclean"][*args]


def obicomplement(*args):
    """Get complement/reverse complement of sequences."""
    return local["obicomplement"][*args]


def obidemerge(*args):
    """Merge de-multiplexed sequences."""
    return local["obidemerge"][*args]


def obimultiplex(*args):
    """Demultiplex sequences by barcode."""
    return local["obimultiplex"][*args]


def obiconsensus(*args):
    """Build consensus sequences."""
    return local["obiconsensus"][*args]


# K-mer and matching tools
def obik(*args):
    """Execute an obik command (count, filter, etc)."""
    return local["obik"][*args]


def obik_count(*args):
    """Count k-mers (obik count)."""
    return obik("count", *args)


def obik_filter(*args):
    """Filter by k-mers (obik filter)."""
    return obik("filter", *args)


def obikindex(*args):
    """Build k-mer index."""
    return local["obikindex"][*args]


def obikmerindex(*args):
    """Build k-mer sequence index."""
    return local["obikmerindex"][*args]


def obikmermatch(*args):
    """Match sequences against k-mer index."""
    return local["obikmermatch"][*args]


def obikmersimcount(*args):
    """Count k-mer similarity."""
    return local["obikmersimcount"][*args]


# PCR and taxonomic tools
def obipcr(*args):
    """Simulate PCR with primers."""
    return local["obipcr"][*args]


def obitagpcr(*args):
    """Tag sequences by PCR."""
    return local["obitagpcr"][*args]


def obimicrosat(*args):
    """Analyze microsatellites."""
    return local["obimicrosat"][*args]


def obitaxonomy(*args):
    """Assign taxonomic information."""
    return local["obitaxonomy"][*args]


def obitag(*args):
    """Tag sequences with metadata."""
    return local["obitag"][*args]


# Utility and database tools
def obilandmark(*args):
    """Find sequence landmarks."""
    return local["obilandmark"][*args]


def obilowmask(*args):
    """Mask low-complexity regions."""
    return local["obilowmask"][*args]


def obimatrix(*args):
    """Generate sequence matrices."""
    return local["obimatrix"][*args]


def obicsv(*args):
    """Export to CSV format."""
    return local["obicsv"][*args]


def obipairing(*args):
    """Handle paired-end reads."""
    return local["obipairing"][*args]


def obiannotate(*args):
    """Annotate sequences."""
    return local["obiannotate"][*args]


def obicleandb(*args):
    """Clean sequence database."""
    return local["obicleandb"][*args]


def obisuperkmer(*args):
    """Work with super k-mers."""
    return local["obisuperkmer"][*args]


def obilowermark(*args):
    """Mark lower case regions."""
    return local["obilowermark"][*args]


def obirefidx(*args):
    """Build reference index."""
    return local["obirefidx"][*args]


def obireffamidx(*args):
    """Build reference family index."""
    return local["obireffamidx"][*args]


# Helper function to get help for any tool
def help(tool_name: str) -> str:
    """Get help text for a tool."""
    try:
        cmd = local[tool_name]
        return cmd["--help"]()
    except Exception as e:
        return f"Error getting help for {tool_name}: {e}"
