"""
Download GenBank and reference genome data.

Usage:
  download                       Download everything (GenBank + all NCBI datasets)
  download genbank [options]     Download GenBank flat-file divisions only
  download ncbi    [options]     Download NCBI reference genome assemblies only
  download sra     [options]     Download raw sequencing reads from NCBI SRA

Run 'download <subcommand> --help' for subcommand options.
"""

import sys

from skimindex.cli import SkimCommand
from skimindex.sources.download.genbank import list_divisions, process_genbank
from skimindex.sources.download.ncbi import (
    list_datasets,
    process_ncbi,
    process_ncbi_dataset,
    query_assemblies,
)
from skimindex.sources.download.sra import (
    list_datasets as list_sra_datasets,
    process_sra,
    process_sra_dataset,
)
from skimindex.sources.download.status import (
    download_status,
    print_status,
    print_genbank_status,
    print_ncbi_status,
)


# ---------------------------------------------------------------------------
# genbank subcommand
# ---------------------------------------------------------------------------

_genbank_cmd = SkimCommand(
    name="download genbank",
    description="Download GenBank flat-file divisions",
    list_fn=list_divisions,
    examples=[
        "%(prog)s",
        "%(prog)s --list",
        "%(prog)s --status",
        "%(prog)s --division pln",
        "%(prog)s --dry-run",
    ],
    section_arg="division",
    section_metavar="DIV",
    section_help="Process a single GenBank division (e.g. pln, bct)",
)
_genbank_cmd.add_argument("--status", action="store_true",
    help="Show download status for GenBank (no download)")


@_genbank_cmd.handler
def _(sections, args, dry_run):
    if args.status:
        print_genbank_status()
        return 0
    return process_genbank(sections, dry_run=dry_run)


# ---------------------------------------------------------------------------
# ncbi subcommand
# ---------------------------------------------------------------------------

_ncbi_cmd = SkimCommand(
    name="download ncbi",
    description="Download NCBI reference genome assemblies",
    list_fn=list_datasets,
    examples=[
        "%(prog)s",
        "%(prog)s --list",
        "%(prog)s --status",
        "%(prog)s --dataset human",
        "%(prog)s --taxon Spermatophyta --one-per species",
        "%(prog)s --dry-run",
    ],
    section_arg="dataset",
    section_metavar="NAME",
    section_help="Process a single NCBI dataset (e.g. human, plants)",
)

_ncbi_cmd.add_argument(
    "--taxon",
    metavar="TAXON",
    help="Query assemblies for a taxon and display results (no download)",
)
_ncbi_cmd.add_argument(
    "--one-per",
    choices=["species", "genus"],
    metavar="species|genus",
    help="Keep only one assembly per species or genus",
)
_ncbi_cmd.add_argument("--assembly-level", metavar="LEVEL",
    help="Filter by assembly level (e.g. 'complete')")
_ncbi_cmd.add_argument("--assembly-source", metavar="SOURCE",
    help="Filter by assembly source")
_ncbi_cmd.add_argument("--assembly-version", metavar="VERSION",
    help="Filter by assembly version")
_ncbi_cmd.add_argument("--reference", action="store_true",
    help="Filter to reference assemblies only")
_ncbi_cmd.add_argument("--status", action="store_true",
    help="Show download status for NCBI datasets (no download)")


@_ncbi_cmd.handler
def _(sections, args, dry_run):
    if args.status:
        print_ncbi_status()
        return 0
    one_per = getattr(args, "one_per", None)
    if args.taxon:
        return query_assemblies(
            args.taxon,
            assembly_level=args.assembly_level,
            reference=args.reference,
            assembly_source=args.assembly_source,
            assembly_version=args.assembly_version,
            one_per=one_per,
        )
    if sections:
        return 0 if process_ncbi_dataset(sections[0], one_per=one_per, dry_run=dry_run) else 1
    return process_ncbi(one_per=one_per, dry_run=dry_run)


# ---------------------------------------------------------------------------
# sra subcommand
# ---------------------------------------------------------------------------

_sra_cmd = SkimCommand(
    name="download sra",
    description="Download raw sequencing reads from NCBI SRA",
    list_fn=list_sra_datasets,
    examples=[
        "%(prog)s",
        "%(prog)s --list",
        "%(prog)s --dataset betula_skims",
        "%(prog)s --dry-run",
    ],
    section_arg="dataset",
    section_metavar="NAME",
    section_help="Process a single SRA dataset (e.g. betula_skims)",
)


@_sra_cmd.handler
def _(sections, args, dry_run):
    if sections:
        return 0 if process_sra_dataset(sections[0], dry_run=dry_run) else 1
    return process_sra(dry_run=dry_run)


# ---------------------------------------------------------------------------
# download — top-level command with subcommands
# ---------------------------------------------------------------------------

def _list_all() -> str:
    return ""


_download_cmd = SkimCommand(
    name="download",
    description="Download all configured data sources.",
    list_fn=_list_all,
    examples=[
        "%(prog)s",
        "%(prog)s --dry-run",
        "%(prog)s --status",
        "%(prog)s genbank --division pln",
        "%(prog)s ncbi --dataset human",
        "%(prog)s sra --dataset betula_skims",
    ],
)
_download_cmd.add_argument("--status", action="store_true",
    help="Show download status for all sources (no download)")
_download_cmd.subcommand("genbank", _genbank_cmd)
_download_cmd.subcommand("ncbi",    _ncbi_cmd)
_download_cmd.subcommand("sra",     _sra_cmd)


@_download_cmd.handler
def _(sections, args, dry_run):
    if args.status:
        print_status(download_status())
        return 0
    if process_genbank(dry_run=dry_run) != 0:
        return 1
    if process_ncbi(dry_run=dry_run) != 0:
        return 1
    return process_sra(dry_run=dry_run)


main = _download_cmd.main

if __name__ == "__main__":
    sys.exit(main())
