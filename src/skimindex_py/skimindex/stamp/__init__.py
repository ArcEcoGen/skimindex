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

needs_run(path, *sources, dry_run, label, action) -> bool
    Single call that covers the three-way branch at every pipeline step:
      - already stamped (and all sources still fresh) → log "OK" and return False
      - dry_run and not stamped → log "WOULD <action>" and return False
      - otherwise → return True (caller should run the step and call stamp())
    Sources are checked with unstamp_if_newer before the stamp test.
"""

import os
import shutil
from pathlib import Path

from skimindex.bashwrapper import bash_export

type PathLike = str | Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STAMP_ROOT = Path(os.environ.get("SKIMINDEX_STAMP_DIR", "/stamp"))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _stamp_path(path: PathLike) -> Path:
    """Return the stamp file path for *path* under STAMP_ROOT.

    Hidden path components (starting with '.') are made visible by replacing
    the leading '.' with '_', so stamp files are never buried in hidden dirs.
    Example: /genbank/Plants/.work/GCA_xxx → /stamp/genbank/Plants/_work/GCA_xxx.stamp
    """
    resolved = Path(path).resolve()
    parts = [
        "_" + part[1:] if part.startswith(".") else part
        for part in resolved.parts
    ]
    visible = str(Path(*parts)).lstrip("/")
    return STAMP_ROOT / (visible + ".stamp")


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

@bash_export
def stamp(path: PathLike) -> bool:
    """Mark *path* as successfully processed.

    Creates (or updates) the stamp file that corresponds to *path*.
    Parent directories are created automatically.

    Args:
        path: The output path (file or directory) that has been produced.

    Returns:
        True on success, False if the stamp file could not be created.
    """
    try:
        sp = _stamp_path(path)
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.touch()
        return True
    except Exception:
        return False


@bash_export
def is_stamped(path: PathLike) -> bool:
    """Return True if *path* has a stamp file (has been successfully processed).

    Args:
        path: The output path whose stamp to check.

    Returns:
        True if the stamp file exists, False otherwise.
    """
    return _stamp_path(path).exists()


@bash_export
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


@bash_export
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


@bash_export
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


@bash_export
def unstamp(path: PathLike) -> bool:
    """Remove the stamp for *path*, forcing re-processing on the next run.

    Args:
        path: The output path whose stamp to remove.

    Returns:
        True if the stamp was removed, False if it did not exist.
    """
    sp = _stamp_path(path)
    try:
        sp.unlink()
        return True
    except FileNotFoundError:
        return False


@bash_export
def stamp_gz(path: PathLike) -> bool:
    """Verify gzip integrity of *path* with pigz -t, then stamp it.

    Args:
        path: A .gz file that has been produced and should be stamped.

    Returns:
        True if the file passed integrity check and was stamped.
        False if pigz -t failed (file is corrupt or incomplete).
    """
    from skimindex.unix.compress import pigz_test  # local import — unix layer above stamp
    try:
        pigz_test(str(path))()
        return stamp(path)
    except Exception:
        return False


@bash_export
def needs_run(
    path: PathLike,
    *sources: PathLike,
    target: PathLike | None = None,
    dry_run: bool = False,
    label: str = "",
    action: str = "process",
) -> bool:
    """Return True only when the pipeline step must actually run.

    Encapsulates the three-way branch repeated at every stamped pipeline step:

      1. Already up-to-date (stamp exists, target exists, all sources fresh):
         logs "[label] OK  (up-to-date)" and returns False.
      2. dry_run and work is needed:
         logs "[label] WOULD <action>" and returns False.
      3. Work is needed and dry_run is False:
         returns True — the caller should execute the step then call stamp().

    *sources* are checked with unstamp_if_newer before the stamp test,
    so the stamp is invalidated automatically when a dependency changes.

    The optional *target* parameter names the real output file or directory
    to check for existence.  Use it when the stamp key is a virtual path
    (e.g. a work-directory sub-path) that does not match the actual output.
    When *target* is None, *path* itself is used as the existence check.
    If the stamp exists but the target does not, the stamp is removed and
    the step is re-run, preventing silent data loss.

    Args:
        path:    The stamp key (used for stamp file lookup).
        *sources: Optional upstream files/directories to check for freshness.
        target:  The real output whose existence is verified alongside the stamp.
                 Defaults to *path* when None.
        dry_run: If True, do not run the step even when work is needed.
        label:   Short identifier shown in log messages (e.g. section name).
        action:  Description of the work, used in the "WOULD" log line.

    Returns:
        True if the caller should run the step, False otherwise.
    """
    from skimindex.log import loginfo, logwarning  # local import to avoid circular dependency

    if sources:
        unstamp_if_newer(path, *sources)

    if is_stamped(path):
        check = Path(target) if target is not None else Path(path)
        if not check.exists():
            logwarning(f"  [{label}] stamp exists but target missing ({check}), re-running")
            unstamp(path)
        else:
            prefix = f"  [{label}]" if label else " "
            loginfo(f"{prefix} OK  (up-to-date)")
            return False

    if dry_run:
        prefix = f"  [{label}]" if label else " "
        loginfo(f"{prefix} WOULD {action}")
        return False

    return True
