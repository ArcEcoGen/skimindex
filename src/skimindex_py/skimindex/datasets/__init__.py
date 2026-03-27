"""
skimindex.datasets — enumeration and access of [data.X] config blocks.

Each dataset binds a source (ncbi, genbank, internal) to a role
(decontamination, genomes, genome_skims) with download and processing parameters.

Usage
-----
    from skimindex.datasets import Dataset, datasets_for_role

    for ds in datasets_for_role("decontamination"):
        for data in ds.to_data():
            pipeline(data, ds.output_dir, dry_run=False)
"""


from pathlib import Path
from collections.abc import Iterator
from typing import Any

from skimindex.config import config


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class Dataset:
    """A configured ``[data.X]`` block with typed access and Data conversion.

    Attributes:
        name:   Dataset name (the ``X`` in ``[data.X]``).
        source: Data origin — ``"ncbi"``, ``"genbank"``, ``"sra"``, or ``"internal"``.
        role:   Pipeline role — ``"decontamination"``, ``"genomes"``, etc.
    """

    def __init__(self, name: str, cfg: dict[str, Any]) -> None:
        """
        Args:
            name: Dataset name as declared in the TOML file.
            cfg:  Raw ``[data.X]`` dict from the parsed config.
        """
        self.name   = name
        self._cfg   = cfg

    # ------------------------------------------------------------------
    # Typed accessors
    # ------------------------------------------------------------------

    @property
    def source(self) -> str:
        return self._cfg.get("source", "ncbi")

    @property
    def role(self) -> str:
        return self._cfg.get("role", "")

    @property
    def directory(self) -> str:
        return self._cfg.get("directory", self.name)

    @property
    def download_dir(self) -> Path:
        """Directory where source files were downloaded."""
        from skimindex.sources import dataset_download_dir
        return dataset_download_dir(self.name)

    @property
    def output_dir(self) -> Path:
        """Processing output directory for this dataset."""
        from skimindex.sources import dataset_output_dir
        return dataset_output_dir(self.name)

    def get(self, key: str, default: Any = None) -> Any:
        """Return a raw config value for this dataset, without type conversion.

        Args:
            key:     Config key to look up (e.g. ``"taxon"``, ``"divisions"``).
            default: Value to return if the key is absent (default: ``None``).
        """
        return self._cfg.get(key, default)

    # ------------------------------------------------------------------
    # Data conversion
    # ------------------------------------------------------------------

    def to_index_data(self) -> "Data":  # noqa: F821
        """Return a single ``Data`` object representing the full dataset output directory.

        Used by indexers that process all assemblies of a dataset at once.

        Returns:
            A DIRECTORY ``Data`` with ``subdir`` set to ``Path(self.directory)``
            and ``path`` pointing to the dataset output directory.
        """
        from pathlib import Path
        from skimindex.processing.data import directory_data
        return directory_data(self.output_dir, subdir=Path(self.directory))

    def to_data(self) -> Iterator["Data"]:  # noqa: F821
        """Yield ``Data`` objects representing this dataset's input files.

        Yields:
            One ``Data`` per genome file for ``ncbi`` sources (``FILES`` kind),
            or one ``Data`` per GenBank division for ``genbank`` sources
            (``STREAM`` kind, optionally filtered by taxid).

        Raises:
            ValueError: If ``source`` is not a supported value.
        """
        if self.source == "ncbi":
            yield from self._ncbi_data()
        elif self.source == "genbank":
            yield from self._genbank_data()
        else:
            raise ValueError(
                f"Dataset [{self.name}]: unsupported source {self.source!r}"
            )

    def _ncbi_data(self) -> Iterator["Data"]:  # noqa: F821
        from skimindex.naming import scan_species_dir
        from skimindex.processing.data import files_data
        from skimindex.sources import output_dir as role_output_dir

        base = self.output_dir.relative_to(role_output_dir("role", self.role))
        dl = self.download_dir
        for f, species_subdir in scan_species_dir(dl):
            suffix = "".join(f.suffixes).lstrip(".")
            yield files_data(f, format=suffix, subdir=base / species_subdir)

    def _genbank_data(self) -> Iterator["Data"]:  # noqa: F821
        from skimindex.config import config
        from skimindex.processing.data import files_data
        from skimindex.processing.filter_taxid import filter_taxid
        from skimindex.sources.genbank import division_dir, latest_release, release_dir

        from skimindex.sources import output_dir as role_output_dir
        base     = self.output_dir.relative_to(role_output_dir("role", self.role))
        taxid    = self._cfg.get("taxid")
        divisions = self._cfg.get("divisions", [])
        release  = self._cfg.get("release") or latest_release()

        # Inputs: one Data per division, or the full release directory
        if divisions:
            inputs = [
                (div, division_dir(release, div))
                for div in divisions
                if division_dir(release, div).exists()
            ]
        else:
            inputs = [("", release_dir(release))]

        # Build filter_taxid runner once if taxid is declared
        taxid_filter = filter_taxid({"taxid": taxid}) if taxid else None

        for label, path in inputs:
            subdir = base / label if label else base
            data = files_data([path], format="fasta", subdir=subdir)
            if taxid_filter is not None:
                data = taxid_filter(data)
            yield data

    def __repr__(self) -> str:
        return f"Dataset({self.name!r}, source={self.source!r}, role={self.role!r})"


# ---------------------------------------------------------------------------
# Registry accessors
# ---------------------------------------------------------------------------

def all_datasets() -> dict[str, dict[str, Any]]:
    """Return all [data.X] sections keyed by dataset name."""
    return config().datasets


def datasets_for_source(source: str) -> list[str]:
    """Return the names of all datasets whose source matches *source*.

    Args:
        source: Source type to filter on (``"ncbi"``, ``"genbank"``, ``"sra"``, …).

    Returns:
        List of dataset names.

    Example:
        ```python
        datasets_for_source("ncbi")    # ["human", "fungi"]
        datasets_for_source("genbank") # ["bacteria"]
        ```
    """
    return [
        name for name, ds in all_datasets().items()
        if ds.get("source") == source
    ]


def datasets_for_role(role: str) -> list[Dataset]:
    """Return ``Dataset`` objects for all datasets assigned to *role*.

    Args:
        role: Role name to filter on (``"decontamination"``, ``"genomes"``, …).

    Returns:
        List of ``Dataset`` instances.

    Example:
        ```python
        datasets_for_role("decontamination")
        # [Dataset('human', ...), Dataset('bacteria', ...)]
        ```
    """
    return [
        Dataset(name, ds)
        for name, ds in all_datasets().items()
        if ds.get("role") == role
    ]


def dataset_config(name: str) -> dict[str, Any]:
    """Return the config dict for a single dataset (empty dict if not found).

    Example:
        dataset_config("human") → {"source": "ncbi", "role": "decontamination",
                                    "taxon": "human", "example": True}
    """
    return all_datasets().get(name, {})


def get_dataset(name: str) -> Dataset:
    """Return a ``Dataset`` object for a named dataset.

    Args:
        name: Dataset name as declared in ``[data.X]``.

    Returns:
        The corresponding ``Dataset`` instance.

    Raises:
        KeyError: If *name* is not found in the config.
    """
    cfg = all_datasets()
    if name not in cfg:
        raise KeyError(f"Dataset {name!r} not found in config")
    return Dataset(name, cfg[name])
