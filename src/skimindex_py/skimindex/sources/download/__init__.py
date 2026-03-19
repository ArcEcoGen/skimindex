"""
skimindex.sources.download — download from external sources.

Public API
----------
GenBank (driven by [source.genbank].divisions):
    list_divisions()       → CSV of configured GenBank divisions
    process_genbank(...)   → download GenBank divisions (returns 0/1)

NCBI reference genomes (driven by [data.X] with source="ncbi"):
    list_datasets()              → CSV of configured NCBI dataset names
    query_assemblies(...)        → list+filter+print assemblies (no download, returns 0)
    process_ncbi(...)            → download all configured NCBI datasets (returns 0/1)
    process_ncbi_dataset(...)    → download a single NCBI dataset (returns bool)
    list_assemblies(...)         → raw NCBI assembly list for a taxon
    filter_assemblies_by_species → keep one assembly per species
    filter_assemblies_by_genus   → keep one assembly per genus
    filter_assemblies_no_hybrids → remove hybrid organisms
"""

from skimindex.sources.download.status import (
    download_status,
    genbank_status,
    ncbi_status,
    ncbi_dataset_status,
    print_status,
    DownloadStatus,
    GenBankStatus,
    DatasetStatus,
    DivisionStatus,
)
from skimindex.sources.download.genbank import (
    list_divisions,
    process_genbank,
    get_release_number,
    get_ftp_listing,
    download_taxonomy,
    download_and_process_genbank,
)
from skimindex.sources.download.ncbi import (
    list_datasets,
    query_assemblies,
    process_ncbi,
    process_ncbi_dataset,
    list_assemblies,
    list_taxids,
    filter_assemblies_by_species,
    filter_assemblies_by_genus,
    filter_assemblies_no_hybrids,
)

__all__ = [
    # Status
    "download_status",
    "genbank_status",
    "ncbi_status",
    "ncbi_dataset_status",
    "print_status",
    "DownloadStatus",
    "GenBankStatus",
    "DatasetStatus",
    "DivisionStatus",
    # GenBank
    "list_divisions",
    "process_genbank",
    "get_release_number",
    "get_ftp_listing",
    "download_taxonomy",
    "download_and_process_genbank",
    # NCBI
    "list_datasets",
    "query_assemblies",
    "process_ncbi",
    "process_ncbi_dataset",
    "list_assemblies",
    "list_taxids",
    "filter_assemblies_by_species",
    "filter_assemblies_by_genus",
    "filter_assemblies_no_hybrids",
]
