#!/usr/bin/env python3
"""
Download GenBank and reference genome data.

Provides command-line interface for download operations.

Usage:
    download all
    download genbank [--divisions "bct pln ..."]
    download refgenome [--list] [--section NAME]
    download refgenome [--taxon TAXON] [--one-per-species|--one-per-genus]
    download refgenome

Examples:
    # Download everything (GenBank + all reference genomes using config)
    download all

    # Download GenBank flat-file divisions
    download genbank

    # Download GenBank with specific divisions
    download genbank --divisions "bct pln pri"

    # List available reference genome sections
    download refgenome --list

    # Download a specific reference genome section
    download refgenome --section human

    # List assemblies for a taxon, filtering to one per species
    download refgenome --taxon Spermatophyta --one-per-species

    # List assemblies for a taxon, filtering to one per genus
    download refgenome --taxon Spermatophyta --one-per-genus

    # Download all reference genomes (all configured sections)
    download refgenome
"""

import argparse
import sys
from typing import Optional

from skimindex.download.genbank import list_divisions, process_genbank
from skimindex.download.refgenome import (
    filter_assemblies_by_genus,
    filter_assemblies_by_species,
    list_assemblies,
    list_sections,
    process_refgenome,
    process_refgenome_section,
)


def genbank_command(args) -> int:
    """Handle 'genbank' subcommand: list divisions or run download task."""
    # Info-only mode: --list
    if args.list:
        divisions = list_divisions()
        print(divisions if divisions else "")
        return 0

    # Determine divisions: CLI option > config default
    if args.divisions:
        divisions = args.divisions.split()
    else:
        divisions = None  # Let process_genbank use config default

    return process_genbank(divisions)


def refgenome_command(args) -> int:
    """Handle 'refgenome' subcommand: list, download single section, or download all."""
    # Info-only mode: --list
    if args.list:
        sections = list_sections()
        print(sections if sections else "")
        return 0

    # Filter mode: show filtered assemblies for a taxon
    if hasattr(args, "taxon") and args.taxon:
        assemblies = list_assemblies(
            args.taxon,
            assembly_level=getattr(args, "assembly_level", None),
            reference=getattr(args, "reference", False),
            assembly_source=getattr(args, "assembly_source", None),
            assembly_version=getattr(args, "assembly_version", None),
        )

        one_per = getattr(args, "one_per", None)
        if one_per == "species":
            assemblies = filter_assemblies_by_species(assemblies)
        elif one_per == "genus":
            assemblies = filter_assemblies_by_genus(assemblies)

        # Display filtered results
        print(f"Found {len(assemblies)} assemblies")
        for asm in assemblies:
            accession = asm.get("accession", "N/A")
            organism = (
                asm.get("assembly_info", {})
                .get("biosample", {})
                .get("description", {})
                .get("organism", {})
                .get("organism_name", "N/A")
            )
            size = asm.get("assembly_stats", {}).get("total_sequence_length", "0")
            print(f"  {accession} - {organism} ({size} bp)")
        return 0

    # Single section download with optional CLI overrides
    if args.section:
        one_per = getattr(args, "one_per", None)

        if not process_refgenome_section(args.section, one_per):
            return 1
        return 0

    # Download all sections (use config)
    return process_refgenome()


def all_command(args) -> int:
    """Handle 'all' subcommand: download GenBank + all reference genomes using config defaults."""
    # Download GenBank with config defaults
    if process_genbank() != 0:
        return 1

    # Download all reference genomes with config defaults
    if process_refgenome() != 0:
        return 1

    return 0


def main(argv: Optional[list] = None) -> int:
    """Main entry point for the download CLI."""
    parser = argparse.ArgumentParser(
        description="Download GenBank and reference genome data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download everything (GenBank + all reference genomes using config)
  %(prog)s all

  # List available GenBank divisions
  %(prog)s genbank --list

  # Download GenBank flat-file divisions
  %(prog)s genbank

  # Download GenBank with specific divisions
  %(prog)s genbank --divisions "bct pln pri"

  # List available reference genome sections
  %(prog)s refgenome --list

  # Download a specific reference genome (e.g., human)
  %(prog)s refgenome --section human

  # List assemblies for a taxon, filtered to one per species
  %(prog)s refgenome --taxon Spermatophyta --one-per species

  # List assemblies for a taxon, filtered to one per genus
  %(prog)s refgenome --taxon Spermatophyta --one-per genus

  # Download all reference genome sections (use config)
  %(prog)s refgenome
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # ===== all subcommand =====
    all_parser = subparsers.add_parser(
        "all",
        help="Download GenBank + all reference genomes (uses config defaults)",
    )
    all_parser.set_defaults(func=all_command)

    # ===== genbank subcommand =====
    genbank_parser = subparsers.add_parser(
        "genbank", help="Download GenBank flat-file divisions"
    )
    genbank_parser.add_argument(
        "--list",
        action="store_true",
        help="Print available GenBank divisions as CSV and exit",
    )
    genbank_parser.add_argument(
        "--divisions",
        help='Space-separated list of division codes (e.g., "bct pln pri")',
        metavar="DIVS",
    )
    genbank_parser.set_defaults(func=genbank_command)

    # ===== refgenome subcommand =====
    refgenome_parser = subparsers.add_parser(
        "refgenome", help="Download reference genomes"
    )
    refgenome_parser.add_argument(
        "--list",
        action="store_true",
        help="Print available reference genome sections as CSV and exit",
    )
    refgenome_parser.add_argument(
        "--section",
        help="Download a specific reference genome section (e.g., human)",
        metavar="NAME",
    )
    refgenome_parser.add_argument(
        "--taxon",
        help="Filter assemblies for a given taxon (e.g., Spermatophyta)",
        metavar="TAXON",
    )
    refgenome_parser.add_argument(
        "--one-per",
        choices=["species", "genus"],
        help="Keep only one assembly per species or genus (prefer RefSeq, then largest genome)",
        metavar="species|genus",
    )
    refgenome_parser.add_argument(
        "--assembly-level",
        help="Filter by assembly level (e.g., 'complete')",
        metavar="LEVEL",
    )
    refgenome_parser.add_argument(
        "--assembly-source", help="Filter by assembly source", metavar="SOURCE"
    )
    refgenome_parser.add_argument(
        "--assembly-version", help="Filter by assembly version", metavar="VERSION"
    )
    refgenome_parser.add_argument(
        "--reference", action="store_true", help="Filter to reference assemblies only"
    )
    refgenome_parser.set_defaults(func=refgenome_command)

    # Parse arguments
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
