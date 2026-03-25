"""
skimindex.processing.kmercount — atomic 'kmercount' processing type.

Counts k-mers in a directory of FASTA fragments using ntcard.
Output kind: DIRECTORY.

ntcard is run as:
    ntcard -t <threads> -k <kmer_size> -p <output_dir>/<prefix> <input_dir>/*.fasta.gz

The output prefix is derived from the last component of data.subdir
(typically the accession or division name), falling back to "kmers".
ntcard writes one file per k value: <prefix>_k<K>.hist
"""

from pathlib import Path
from collections.abc import Callable

from skimindex.processing import OutputKind, processing_type
from skimindex.processing.data import Data, DataKind, directory_data
from skimindex.unix.ntcard import ntcard_count


@processing_type(output_kind=OutputKind.DIRECTORY, is_indexer=False)
def kmercount(params: dict) -> Callable[[Data, Path, bool], Data]:
    """Count k-mers in FASTA fragments using ntcard."""
    kmer_size    = int(params.get("kmer_size", 29))
    threads      = int(params.get("threads", 1))
    sequence_ref = params.get("sequence")

    def run(input_data: Data, output_dir: Path, dry_run: bool = False) -> Data:
        if sequence_ref is not None:
            from skimindex.sources import resolve_artifact
            seq_path    = resolve_artifact(sequence_ref, input_data.subdir)
            input_data  = directory_data(seq_path, subdir=input_data.subdir)

        if input_data.kind == DataKind.FILES:
            input_files = input_data.paths
        elif input_data.kind == DataKind.DIRECTORY:
            from skimindex.sequences import list_sequence_files
            input_files = list_sequence_files(input_data.path, mode="absolute", recursive=True)
        else:
            raise ValueError(f"kmercount expects FILES or DIRECTORY input, got {input_data.kind}")

        if not input_files:
            raise FileNotFoundError(f"No sequence files found in kmercount input")

        # Prefix = last meaningful path component (accession, division, ...)
        prefix = input_data.subdir.name if input_data.subdir else "kmers"

        output_dir.mkdir(parents=True, exist_ok=True)

        if not dry_run:
            ntcard_count(
                kmer=kmer_size,
                threads=threads,
                prefix=output_dir / prefix,
                files=input_files,
            )()

        return directory_data(output_dir, subdir=input_data.subdir)

    return run
