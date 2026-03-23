"""
skimindex.sources.sra — path helpers for the SRA source.

All paths follow the hierarchy:
    /sra/{directory}/{organism}/{biosample}/{run}*.fastq.gz

where:
  - /sra        is [source.sra].directory resolved against SKIMINDEX_ROOT
  - {directory} is [data.X].directory
  - {organism}  is the sanitised organism name from SRA metadata
  - {biosample} is the biosample accession (e.g. SAMEA9098823)
  - {run}       is the SRA run accession (e.g. ERR7254752)

Stamp paths mirror the output hierarchy under /stamp/sra/.
"""

from pathlib import Path

from skimindex.config import config
from skimindex.datasets import dataset_config
from skimindex.naming import canonical_species


def sra_dir() -> Path:
    """Root directory for the SRA source (/sra or configured equivalent)."""
    return config().source_dir("sra")


def scratch_dir() -> Path:
    """Scratch directory for temporary SRA files (/scratch or configured equivalent)."""
    return config().scratch_dir()


def dataset_sra_dir(dataset_name: str) -> Path:
    """Download directory for a named SRA dataset.

    Resolves: sra_dir() / dataset.directory

    Example:
        dataset_sra_dir("betula_skims") → /sra/Betula
    """
    ds = dataset_config(dataset_name)
    directory = ds.get("directory", dataset_name)
    return sra_dir() / directory


def organism_dir(dataset_name: str, organism: str) -> Path:
    """Directory for a given organism within an SRA dataset.

    Example:
        organism_dir("betula_skims", "Betula pendula") → /sra/Betula/Betula_pendula
    """
    return dataset_sra_dir(dataset_name) / canonical_species(organism)


def biosample_dir(dataset_name: str, organism: str, biosample: str) -> Path:
    """Directory for a biosample within an organism directory.

    Example:
        biosample_dir("betula_skims", "Betula pendula", "SAMEA9098823")
            → /sra/Betula/Betula_pendula/SAMEA9098823
    """
    return organism_dir(dataset_name, organism) / biosample


def run_output_paths(
    dataset_name: str,
    organism: str,
    biosample: str,
    run: str,
    paired: bool,
) -> list[Path]:
    """Final .fastq.gz output paths for a run.

    Returns a list with:
      - 2 paths for paired-end: [{run}_1.fastq.gz, {run}_2.fastq.gz]
      - 1 path for single-end: [{run}.fastq.gz]
    """
    base = biosample_dir(dataset_name, organism, biosample)
    if paired:
        return [base / f"{run}_1.fastq.gz", base / f"{run}_2.fastq.gz"]
    return [base / f"{run}.fastq.gz"]


def scratch_run_dir(run: str) -> Path:
    """Scratch directory for a single run's temporary files.

    Example:
        scratch_run_dir("ERR7254752") → /scratch/sra/ERR7254752
    """
    return scratch_dir() / "sra" / run


