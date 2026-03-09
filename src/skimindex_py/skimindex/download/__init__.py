"""
Download module for managing dataset downloads.

Provides orchestration for GenBank and reference genome downloads.

Submodules:
  - genbank: Download and process GenBank data
  - refgenome: Download and process reference genomes from NCBI

Utilities:
    # List available GenBank divisions:
    from skimindex.download.genbank import list_divisions

    # List available reference genome sections:
    from skimindex.download.refgenome import list_sections

    # Process GenBank data:
    from skimindex.download.genbank import process_genbank
    process_genbank()  # Uses config defaults

    # Process reference genomes:
    from skimindex.download.refgenome import process_refgenome
    process_refgenome()  # Uses config defaults
"""

from . import genbank, refgenome

__all__ = ["genbank", "refgenome"]
