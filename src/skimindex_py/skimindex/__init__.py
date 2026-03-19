"""
skimindex — Python package for managing skimindex pipelines.

Modules:
  - config: Read and parse TOML configuration with automatic env var export
  - log: Logging module (colors, file output, levels)
  - unix: Unix tools wrappers (compress, ncbi, obitools)
  - datasets: Enumerate and access [data.X] config blocks
  - sources: Source registry, directory helpers, and download orchestration
  - decontamination: Fragment splitting and k-mer counting for decontamination indices
"""

from . import config, datasets, decontamination, log, sources, unix

__all__ = ["config", "datasets", "decontamination", "log", "sources", "unix"]
