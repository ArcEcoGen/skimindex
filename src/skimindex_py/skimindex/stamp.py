"""
Centralised stamp-file management for skimindex pipelines.

Stamp files record that a given output (or processing step) has been
successfully completed.  They live in a single directory tree mounted
at /stamp inside the container (configurable via SKIMINDEX_STAMP_DIR).

The stamp for a path mirrors the path's structure under STAMP_ROOT:
    /processed_data/Fungi/pln/parts  →  /stamp/processed_data/Fungi/pln/parts.stamp

Key functions
-------------
stamp(path)
    Mark *path* as successfully processed.

is_stamped(path) -> bool
    Return True if the stamp for *path* exists.

unstamp(path)
    Remove the stamp for *path* (force re-processing on next run).

remove_if_not_stamped(path)
    Delete *path* (file or directory tree) if it is not stamped.
    Useful to clean up partial outputs before a re-run.

newer_than_stamp(path, path_stamped) -> bool
    Return True if *path* (or any file inside it if it is a directory,
    checked recursively) is newer than the stamp of *path_stamped*.

unstamp_if_newer(path, *sources) -> bool
    Remove the stamp for *path* if any of *sources* (or any file inside
    them, checked recursively) is newer than it.
    Invalidates a downstream stamp when an upstream dependency changes.
"""

import os
import shutil
from pathlib import Path
from typing import Union

PathLike = Union[str, Path]

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STAMP_ROOT = Path(os.environ.get("SKIMINDEX_STAMP_DIR", "/stamp"))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _stamp_path(path: PathLike) -> Path:
    """Return the stamp file path for *path* under STAMP_ROOT."""
    resolved = Path(path).resolve()
    # Strip leading '/' so Path() joining works, then append .stamp suffix.
    relative = str(resolved).lstrip("/")
    return STAMP_ROOT / (relative + ".stamp")


def _max_mtime(path: Path) -> float:
    """Return the most recent mtime among all files in *path*.

    If *path* is a regular file, its own mtime is returned.
    If *path* is a directory, the maximum mtime of all files found
    recursively is returned (0.0 if the directory is empty).
    Raises FileNotFoundError if *path* does not exist.
    """
    if path.is_dir():
        mtimes = (f.stat().st_mtime for f in path.rglob("*") if f.is_file())
        return max(mtimes, default=0.0)
    return path.stat().st_mtime


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def stamp(path: PathLike) -> None:
    """Mark *path* as successfully processed.

    Creates (or updates) the stamp file that corresponds to *path*.
    Parent directories are created automatically.

    Args:
        path: The output path (file or directory) that has been produced.
    """
    sp = _stamp_path(path)
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.touch()


def is_stamped(path: PathLike) -> bool:
    """Return True if *path* has a stamp file (has been successfully processed).

    Args:
        path: The output path whose stamp to check.

    Returns:
        True if the stamp file exists, False otherwise.
    """
    return _stamp_path(path).exists()


def remove_if_not_stamped(path: PathLike) -> bool:
    """Delete *path* if it has no valid stamp.

    Removes files or entire directory trees that were left behind by an
    interrupted run, ensuring the next run starts from a clean state.
    Does nothing if *path* does not exist or is already stamped.

    Args:
        path: The output path to conditionally remove.

    Returns:
        True if *path* was removed, False otherwise.
    """
    if is_stamped(path):
        return False
    p = Path(path)
    if not p.exists():
        return False
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()
    return True


def newer_than_stamp(path: PathLike, path_stamped: PathLike) -> bool:
    """Return True if *path* is newer than the stamp of *path_stamped*.

    Useful for checking a single dependency in isolation, e.g.:
        if newer_than_stamp(taxonomy, fragments_dir):
            loginfo("taxonomy changed, re-splitting")

    If *path* is a directory, every file it contains is checked recursively;
    the result is True if any one of them is newer than the stamp.

    Returns False if the stamp does not exist or *path* is missing.

    Args:
        path:         The file/directory to test for freshness.
        path_stamped: The output whose stamp mtime is used as reference.

    Returns:
        True if any file under *path* has mtime > stamp(*path_stamped*).mtime.
    """
    sp = _stamp_path(path_stamped)
    if not sp.exists():
        return False
    stamp_mtime = sp.stat().st_mtime
    p = Path(path)
    try:
        if p.is_dir():
            return any(
                f.stat().st_mtime > stamp_mtime
                for f in p.rglob("*")
                if f.is_file()
            )
        return p.stat().st_mtime > stamp_mtime
    except FileNotFoundError:
        return False


def unstamp_if_newer(path: PathLike, *sources: PathLike) -> bool:
    """Remove the stamp for *path* if any of *sources* is newer than it.

    Combines newer_than_stamp() and unstamp() into a single call.
    Useful for invalidating a downstream output when an upstream dependency
    has changed, without yet knowing whether a re-run will be triggered.

    Does nothing if the stamp does not exist or all sources are older.

    Args:
        path:     The output whose stamp may be invalidated.
        *sources: Files/directories to check against the stamp mtime.

    Returns:
        True if the stamp was removed, False otherwise.
    """
    if any(newer_than_stamp(src, path) for src in sources):
        unstamp(path)
        return True
    return False


def unstamp(path: PathLike) -> None:
    """Remove the stamp for *path*, forcing re-processing on the next run.

    Does nothing if no stamp exists.

    Args:
        path: The output path whose stamp to remove.
    """
    sp = _stamp_path(path)
    try:
        sp.unlink()
    except FileNotFoundError:
        pass
