"""
Unix tools wrapper module using plumbum.

Provides Pythonic interfaces to Unix command-line tools and external programs
installed in the Docker image.

Submodules:
  - download: Download utilities (curl)
  - compress: Compression tools (pigz, unzip)
  - ncbi: NCBI CLI tools (datasets, dataformat)
  - obitools: OBITools bioinformatics tools (37 sequence processing commands)

All tools support piping via plumbum's | operator.

Example:
    from skimindex.unix import compress, ncbi, obitools
    from plumbum import FG

    # Compress with pigz
    compress.pigz_compress("file.txt") & FG

    # Download genome from NCBI
    ncbi.datasets_download_genome("--taxon", "human") & FG

    # Process sequences with OBITools
    (obitools.obiconvert["input.fasta"] |
     obitools.obigrep["-s", "^count>10"]) & FG
"""

from . import compress, download, ncbi, obitools

__all__ = ["compress", "download", "ncbi", "obitools"]
