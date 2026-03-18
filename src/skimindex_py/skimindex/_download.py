"""
Download GenBank and reference genome data.

Three entry points:
  download-genbank   Download GenBank flat-file divisions.
  download-refgenome Download reference genome assemblies from NCBI.
  download           Download everything (GenBank + all reference genomes).
"""

import sys
from typing import Optional

from skimindex.cli import SkimCommand
from skimindex.download.genbank import list_divisions, process_genbank
from skimindex.download.refgenome import (
    filter_assemblies_by_genus,
    filter_assemblies_by_species,
    list_assemblies,
    list_sections,
    process_refgenome,
    process_refgenome_section,
)


# ---------------------------------------------------------------------------
# download-genbank
# ---------------------------------------------------------------------------

genbank_cmd = SkimCommand(
    name="download-genbank",
    description="Download GenBank flat-file divisions",
    list_fn=list_divisions,
    examples=[
        "%(prog)s",
        "%(prog)s --list",
        "%(prog)s --section pln",
    ],
)

# Note: --section from SkimCommand maps to a single division (e.g. "pln").
# Without --section, all configured divisions are downloaded.

@genbank_cmd.handler
def _(sections, args, dry_run):
    return process_genbank(sections, dry_run=dry_run)


main_genbank = genbank_cmd.main


# ---------------------------------------------------------------------------
# download-refgenome
# ---------------------------------------------------------------------------

refgenome_cmd = SkimCommand(
    name="download-refgenome",
    description="Download reference genome assemblies from NCBI",
    list_fn=list_sections,
    examples=[
        "%(prog)s",
        "%(prog)s --list",
        "%(prog)s --section human",
        "%(prog)s --taxon Spermatophyta --one-per species",
        "%(prog)s --taxon Spermatophyta --one-per genus",
    ],
)

refgenome_cmd.add_argument(
    "--taxon",
    metavar="TAXON",
    help="Query assemblies for a taxon and display results (no download)",
)
refgenome_cmd.add_argument(
    "--one-per",
    choices=["species", "genus"],
    metavar="species|genus",
    help="Keep only one assembly per species or genus (prefer RefSeq, then largest genome)",
)
refgenome_cmd.add_argument(
    "--assembly-level",
    metavar="LEVEL",
    help="Filter by assembly level (e.g. 'complete')",
)
refgenome_cmd.add_argument(
    "--assembly-source",
    metavar="SOURCE",
    help="Filter by assembly source",
)
refgenome_cmd.add_argument(
    "--assembly-version",
    metavar="VERSION",
    help="Filter by assembly version",
)
refgenome_cmd.add_argument(
    "--reference",
    action="store_true",
    help="Filter to reference assemblies only",
)


@refgenome_cmd.handler
def _(sections, args, dry_run):
    # Query mode: display filtered assembly list without downloading.
    if args.taxon:
        assemblies = list_assemblies(
            args.taxon,
            assembly_level=args.assembly_level,
            reference=args.reference,
            assembly_source=args.assembly_source,
            assembly_version=args.assembly_version,
        )
        one_per = getattr(args, "one_per", None)
        if one_per == "species":
            assemblies = filter_assemblies_by_species(assemblies)
        elif one_per == "genus":
            assemblies = filter_assemblies_by_genus(assemblies)
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

    # Download a single section.
    if sections:
        one_per = getattr(args, "one_per", None)
        return 0 if process_refgenome_section(sections[0], one_per, dry_run=dry_run) else 1

    # Download all configured sections.
    return process_refgenome(dry_run=dry_run)


main_refgenome = refgenome_cmd.main


# ---------------------------------------------------------------------------
# download — download everything (GenBank + all reference genomes)
# ---------------------------------------------------------------------------

def main(argv: Optional[list] = None) -> int:
    """Download everything: GenBank divisions then all reference genome sections."""
    if process_genbank() != 0:
        return 1
    return process_refgenome()


if __name__ == "__main__":
    sys.exit(main())
