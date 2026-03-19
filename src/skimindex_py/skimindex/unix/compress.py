"""
Compression tools wrapper module using plumbum.

Provides Pythonic interfaces to compression tools installed in the image:
  - pigz: Parallel gzip compression
  - unzip: Extract ZIP archives

Two API styles:
  1. Flexible: pigz("--help"), unzip("-l", "archive.zip")
  2. Convenient: pigz_compress("file.txt"), unzip_list("archive.zip")

Example:
    from skimindex.compress import pigz_compress, unzip_extract
    from plumbum import FG

    # Compress with parallel gzip
    pigz_compress("file.txt") & FG

    # Extract ZIP archive
    unzip_extract("-d", "/output", "archive.zip") & FG

    # Flexible API for custom pigz options
    pigz("-p", "4", "-9", "file.txt") & FG
"""

from skimindex.unix.base import LoggedBoundCommand, local


# pigz (parallel gzip) — flexible API
def pigz(*args) -> LoggedBoundCommand:
    """Execute a pigz command (parallel gzip compression).

    Common options:
      -d: Decompress instead of compress
      -p N: Number of processes to use
      -9: Maximum compression
      -1: Fast compression
      -k: Keep input file

    Examples:
        pigz("file.txt")                      # compress
        pigz("-d", "file.txt.gz")             # decompress
        pigz("-p", "4", "-9", "file.txt")    # compress with 4 threads, max compression

    Full documentation: pigz --help
    """
    return local["pigz"][*args]


def pigz_compress(*args) -> LoggedBoundCommand:
    """Compress file(s) with parallel gzip."""
    return pigz(*args)


def pigz_decompress(*args) -> LoggedBoundCommand:
    """Decompress file(s) with parallel gzip."""
    return pigz("-d", *args)


def pigz_test(*args) -> LoggedBoundCommand:
    """Test integrity of gzipped file(s)."""
    return pigz("-t", *args)


# unzip — flexible API
def unzip(*args) -> LoggedBoundCommand:
    """Execute an unzip command.

    Common subcommands/options:
      -l: List contents of archive
      -d DIR: Extract to directory
      -o: Overwrite without prompting
      -q: Quiet mode
      file: Extract specific file(s)

    Examples:
        unzip("-l", "archive.zip")                    # list contents
        unzip("-d", "/output", "archive.zip")        # extract to directory
        unzip("archive.zip", "file.txt")              # extract specific file
        unzip("-o", "archive.zip")                    # overwrite existing

    Full documentation: unzip --help
    """
    return local["unzip"][*args]


def unzip_list(*args) -> LoggedBoundCommand:
    """List contents of archive."""
    return unzip("-l", *args)


def unzip_extract(*args) -> LoggedBoundCommand:
    """Extract archive (unzip -d DIR archive.zip)."""
    return unzip("-d", *args)


# Helper function to get help for any tool
def help(tool_name: str) -> str:
    """Get help text for a compression tool."""
    try:
        cmd = local[tool_name]
        return cmd["--help"]()
    except Exception as e:
        return f"Error getting help for {tool_name}: {e}"
