"""
skimindex.sources.genbank — GenBank source API.

Provides structured access to the GenBank flat-file source directory:
releases, divisions, and taxonomy.

Public API
----------
available_releases() -> list[str]
    All Release_* directory names found under the GenBank source root,
    sorted in ascending numeric order.

latest_release() -> str
    Name of the most recent release (e.g. "Release_270").

release_dir(release) -> Path
    Absolute path to a named release directory.

taxonomy(release) -> Path
    Absolute path to the NCBI taxonomy archive for a release.

division_dir(release, div) -> Path
    Absolute path to the FASTA directory for a division within a release
    (e.g. release_dir / "fasta" / "bct").
"""


from pathlib import Path

from skimindex.sources import source_dir


def _genbank_root() -> Path:
    return source_dir("genbank")


def available_releases() -> list[str]:
    """Return all release names under the GenBank root, sorted in ascending numeric order.

    A release name is the numeric part after "Release_", e.g. "270.0".

    Example:
        available_releases() → ["268.0", "269.0", "270.0"]
    """
    root = _genbank_root()
    releases = []
    for p in root.iterdir():
        if p.is_dir() and p.name.startswith("Release_"):
            parts = p.name.split("_", 1)
            if len(parts) == 2:
                releases.append(parts[1])

    def _as_float(r: str) -> float:
        try:
            return float(r)
        except ValueError:
            return 0.0

    return sorted(releases, key=_as_float)


def latest_release() -> str:
    """Return the name of the most recent GenBank release.

    Raises:
        RuntimeError: if no Release_* directory is found.
    """
    releases = available_releases()
    if not releases:
        raise RuntimeError(
            f"No Release_* directory found under {_genbank_root()}"
        )
    return releases[-1]


def release_dir(release: str) -> Path:
    """Return the absolute path to a named release directory.

    Args:
        release: release name, e.g. "270.0"

    Example:
        release_dir("270.0") → Path("/genbank/Release_270.0")
    """
    return _genbank_root() / f"Release_{release}"


def taxonomy(release: str) -> Path:
    """Return the absolute path to the NCBI taxonomy archive for a release.

    Example:
        taxonomy("270.0") → Path("/genbank/Release_270.0/taxonomy/ncbi_taxonomy.tgz")
    """
    return release_dir(release) / "taxonomy" / "ncbi_taxonomy.tgz"


def division_dir(release: str, div: str) -> Path:
    """Return the absolute path to the FASTA directory for a division.

    Example:
        division_dir("270.0", "bct") → Path("/genbank/Release_270.0/fasta/bct")
    """
    return release_dir(release) / "fasta" / div
