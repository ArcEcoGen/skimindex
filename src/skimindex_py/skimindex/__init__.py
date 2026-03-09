"""
skimindex — Python package for managing skimindex pipelines.

Modules:
  - config: Read and parse TOML configuration with automatic env var export
  - log: Logging module (colors, file output, levels)
  - unix: Unix tools wrappers (compress, ncbi, obitools)
  - download: Dataset download orchestration (refgenome)
  - split: Fragment splitting for decontamination indices
"""

from . import config, download, log, split, unix

__all__ = ["config", "download", "log", "split", "unix"]
