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

from skimindex.unix.base import LoggedBoundCommand, local


# Core data processing tools
def obiconvert(*args) -> LoggedBoundCommand:
    """Convert between different sequence file formats."""
    return local["obiconvert"][*args]


def obiscript(script_path: str, *args) -> LoggedBoundCommand:
    """Execute an OBITools Lua script on sequence data."""
    return local["obiscript"]["-S", script_path, *args]


def obigrep(*args) -> LoggedBoundCommand:
    """Filter sequences based on various criteria."""
    return local["obigrep"][*args]


def obidistribute(*args) -> LoggedBoundCommand:
    """Distribute sequences to multiple output files."""
    return local["obidistribute"][*args]


def obisplit(*args) -> LoggedBoundCommand:
    """Split sequences into overlapping fragments."""
    return local["obisplit"][*args]


# Sequence analysis tools
def obicount(*args) -> LoggedBoundCommand:
    """Count occurrences of sequences."""
    return local["obicount"][*args]


def obiuniq(*args) -> LoggedBoundCommand:
    """Remove duplicate sequences."""
    return local["obiuniq"][*args]


def obisummary(*args) -> LoggedBoundCommand:
    """Generate summary statistics for sequences."""
    return local["obisummary"][*args]


def obijoin(*args) -> LoggedBoundCommand:
    """Join sequence files."""
    return local["obijoin"][*args]


# Sequence cleaning and manipulation
def obiclean(*args) -> LoggedBoundCommand:
    """Clean sequences (remove ambiguous bases, etc.)."""
    return local["obiclean"][*args]


def obicomplement(*args) -> LoggedBoundCommand:
    """Get complement/reverse complement of sequences."""
    return local["obicomplement"][*args]


def obidemerge(*args) -> LoggedBoundCommand:
    """Merge de-multiplexed sequences."""
    return local["obidemerge"][*args]


def obimultiplex(*args) -> LoggedBoundCommand:
    """Demultiplex sequences by barcode."""
    return local["obimultiplex"][*args]


def obiconsensus(*args) -> LoggedBoundCommand:
    """Build consensus sequences."""
    return local["obiconsensus"][*args]


# K-mer and matching tools
def obik(*args) -> LoggedBoundCommand:
    """Execute an obik command (count, filter, etc)."""
    return local["obik"][*args]


def obik_count(*args) -> LoggedBoundCommand:
    """Count k-mers (obik count)."""
    return obik("count", *args)


def obik_filter(*args) -> LoggedBoundCommand:
    """Filter by k-mers (obik filter)."""
    return obik("filter", *args)


def obikindex(*args) -> LoggedBoundCommand:
    """Build k-mer index."""
    return local["obikindex"][*args]


def obikmerindex(*args) -> LoggedBoundCommand:
    """Build k-mer sequence index."""
    return local["obikmerindex"][*args]


def obikmermatch(*args) -> LoggedBoundCommand:
    """Match sequences against k-mer index."""
    return local["obikmermatch"][*args]


def obikmersimcount(*args) -> LoggedBoundCommand:
    """Count k-mer similarity."""
    return local["obikmersimcount"][*args]


# PCR and taxonomic tools
def obipcr(*args) -> LoggedBoundCommand:
    """Simulate PCR with primers."""
    return local["obipcr"][*args]


def obitagpcr(*args) -> LoggedBoundCommand:
    """Tag sequences by PCR."""
    return local["obitagpcr"][*args]


def obimicrosat(*args) -> LoggedBoundCommand:
    """Analyze microsatellites."""
    return local["obimicrosat"][*args]


def obitaxonomy(*args) -> LoggedBoundCommand:
    """Assign taxonomic information."""
    return local["obitaxonomy"][*args]


def obitag(*args) -> LoggedBoundCommand:
    """Tag sequences with metadata."""
    return local["obitag"][*args]


# Utility and database tools
def obilandmark(*args) -> LoggedBoundCommand:
    """Find sequence landmarks."""
    return local["obilandmark"][*args]


def obilowmask(*args) -> LoggedBoundCommand:
    """Mask low-complexity regions."""
    return local["obilowmask"][*args]


def obimatrix(*args) -> LoggedBoundCommand:
    """Generate sequence matrices."""
    return local["obimatrix"][*args]


def obicsv(*args) -> LoggedBoundCommand:
    """Export to CSV format."""
    return local["obicsv"][*args]


def obipairing(*args) -> LoggedBoundCommand:
    """Handle paired-end reads."""
    return local["obipairing"][*args]


def obiannotate(*args) -> LoggedBoundCommand:
    """Annotate sequences."""
    return local["obiannotate"][*args]


def obicleandb(*args) -> LoggedBoundCommand:
    """Clean sequence database."""
    return local["obicleandb"][*args]


def obisuperkmer(*args) -> LoggedBoundCommand:
    """Work with super k-mers."""
    return local["obisuperkmer"][*args]


def obilowermark(*args) -> LoggedBoundCommand:
    """Mark lower case regions."""
    return local["obilowermark"][*args]


def obirefidx(*args) -> LoggedBoundCommand:
    """Build reference index."""
    return local["obirefidx"][*args]


def obireffamidx(*args) -> LoggedBoundCommand:
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
