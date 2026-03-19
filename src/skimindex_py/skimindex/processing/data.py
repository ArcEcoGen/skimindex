"""
skimindex.processing.data — Data abstraction for pipeline steps.

`Data` represents what flows between processing steps: sequences, files,
directories. It is the uniform currency of the processing model, hiding
the underlying execution layer (plumbum) from pipeline orchestration.

Three kinds of data, aligned with OutputKind:
  STREAM    — a deferred pipeline not yet executed (carries a plumbum command)
  FILES     — one or more files on disk (carries list[Path])
  DIRECTORY — a directory of files (carries a single Path)

Convenience constructors
------------------------
  stream_data(command, format=None)          → STREAM Data
  files_data(paths, format=None)             → FILES  Data  (Path or list[Path])
  directory_data(path)                       → DIRECTORY Data

Adapter
-------
  to_stream_command(data)
      Converts any Data into a plumbum source command.
      This is the only place where the plumbum layer is visible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any


class DataKind(Enum):
    STREAM    = auto()  # deferred plumbum pipeline, not yet executed
    FILES     = auto()  # one or more files on disk (list[Path])
    DIRECTORY = auto()  # a directory of files (single Path)


@dataclass
class Data:
    """Data flowing between processing steps.

    Attributes:
        kind:    Nature of the data (STREAM, FILES, DIRECTORY).
        paths:   File paths for FILES (1..N) or DIRECTORY (exactly 1).
        command: Plumbum command/pipe for STREAM (not yet executed).
        format:  Optional hint about the data format, e.g. "fasta.gz",
                 "gbff.gz", "fasta".  Used by adaptors and for documentation.
        subdir:  Relative output path contributed by this data item, e.g.
                 Path("human/Homo_sapiens-GCF_xxx") or Path("bacteria/bct").
                 Combined with the processing directory and the root
                 (processed_data or indexes) to form the full output path:
                 {root} / {subdir} / {processing.directory}
    """

    kind: DataKind
    paths: list[Path] | None = field(default=None)
    command: Any | None = field(default=None)
    format: str | None = field(default=None)
    subdir: Path | None = field(default=None)

    @property
    def path(self) -> Path | None:
        """Convenience: first (or only) path.

        Useful for DIRECTORY data (always one path) and single-file FILES.
        Returns None if paths is empty or not set.
        """
        return self.paths[0] if self.paths else None

    def __repr__(self) -> str:
        if self.kind == DataKind.STREAM:
            return f"Data(STREAM, format={self.format!r})"
        if self.kind == DataKind.FILES:
            n = len(self.paths) if self.paths else 0
            return f"Data(FILES, n={n}, format={self.format!r})"
        return f"Data(DIRECTORY, path={self.path})"


# ---------------------------------------------------------------------------
# Convenience constructors
# ---------------------------------------------------------------------------

def stream_data(command: Any, format: str | None = None, subdir: Path | None = None) -> Data:
    """Create STREAM Data from a plumbum command or pipe."""
    return Data(kind=DataKind.STREAM, command=command, format=format, subdir=subdir)


def files_data(paths: list[Path] | Path, format: str | None = None, subdir: Path | None = None) -> Data:
    """Create FILES Data from one or more paths.

    Accepts a single Path or a list. A single file is stored as a
    one-element list; callers do not need to special-case the two forms.
    """
    if isinstance(paths, Path):
        paths = [paths]
    return Data(kind=DataKind.FILES, paths=list(paths), format=format, subdir=subdir)


def directory_data(path: Path, subdir: Path | None = None) -> Data:
    """Create DIRECTORY Data from a single directory path."""
    return Data(kind=DataKind.DIRECTORY, paths=[path], subdir=subdir)


# ---------------------------------------------------------------------------
# Plumbum adaptor — the only place where Data touches plumbum
# ---------------------------------------------------------------------------

def to_stream_command(data: Data) -> Any:
    """Convert any Data into a plumbum source command.

    - STREAM    : returns data.command unchanged (already a plumbum pipe)
    - FILES     : wraps all paths in obiconvert(*paths)
    - DIRECTORY : wraps the directory path in obiconvert(path)

    Raises:
        ValueError: if data.kind is not recognised.
    """
    from skimindex.unix.obitools import obiconvert  # local import — unix layer

    if data.kind == DataKind.STREAM:
        return data.command

    if data.kind == DataKind.FILES:
        if not data.paths:
            raise ValueError("FILES Data has no paths")
        return obiconvert(*[str(p) for p in data.paths])

    if data.kind == DataKind.DIRECTORY:
        if not data.path:
            raise ValueError("DIRECTORY Data has no path")
        return obiconvert(str(data.path))

    raise ValueError(f"Cannot convert {data.kind!r} to a stream command")
