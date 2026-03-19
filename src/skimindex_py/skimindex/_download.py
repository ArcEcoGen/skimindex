"""
Download GenBank and reference genome data.

Usage:
  download                       Download everything (GenBank + all NCBI datasets)
  download genbank [options]     Download GenBank flat-file divisions only
  download ncbi    [options]     Download NCBI reference genome assemblies only

Run 'download genbank --help' or 'download ncbi --help' for subcommand options.
"""

import argparse
import sys

from skimindex.cli import SkimCommand
from skimindex.sources.download.genbank import list_divisions, process_genbank
from skimindex.sources.download.ncbi import (
    list_datasets,
    process_ncbi,
    process_ncbi_dataset,
    query_assemblies,
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
# download — top-level entry point
# ---------------------------------------------------------------------------

_SUBCOMMANDS = {
    "genbank": _genbank_cmd.main,
    "ncbi":    _ncbi_cmd.main,
}


def main(argv: list | None = None) -> int:
    """Download everything, or a specific source via subcommand."""
    if argv is None:
        argv = sys.argv[1:]

    # Route to subcommand if the first argument names one
    if argv and argv[0] in _SUBCOMMANDS:
        return _SUBCOMMANDS[argv[0]](argv[1:])

    # No subcommand: download everything (or show global status)
    parser = argparse.ArgumentParser(
        prog="download",
        description="Download all configured data sources.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Subcommands:\n"
            "  download genbank   Download GenBank flat-file divisions\n"
            "  download ncbi      Download NCBI reference genome assemblies\n\n"
            "Run 'download <subcommand> --help' for subcommand-specific options."
        ),
    )
    parser.add_argument("--dry-run", action="store_true",
        help="Show what would be downloaded without executing anything")
    parser.add_argument("--status", action="store_true",
        help="Show download status for all sources (no download)")
    args = parser.parse_args(argv)

    if args.status:
        print_status(download_status())
        return 0

    if process_genbank(dry_run=args.dry_run) != 0:
        return 1
    return process_ncbi(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
