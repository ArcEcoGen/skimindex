"""
Split reference genomes into fragments for decontamination index building.
"""

from skimindex.cli import SkimCommand
from skimindex.split import list_sections, process_split

cmd = SkimCommand(
    name="split",
    description="Split reference genomes into fragments for decontamination indices",
    list_fn=list_sections,
    examples=[
        "%(prog)s",
        "%(prog)s --list",
        "%(prog)s --section human",
        "%(prog)s --frg-size 300 --overlap 28 --batches 32",
        "%(prog)s --section plant --frg-size 300 --overlap 28",
        "%(prog)s --dry-run",
    ],
)

cmd.add_argument(
    "--frg-size",
    type=int,
    metavar="SIZE",
    help="Fragment size in bp (default: from config decontamination.frg_size)",
)
cmd.add_argument(
    "--overlap",
    type=int,
    metavar="N",
    help="Overlap between fragments (default: from config decontamination.kmer_size - 1)",
)
cmd.add_argument(
    "--batches",
    type=int,
    metavar="N",
    help="Number of output batches (default: from config decontamination.batches)",
)


@cmd.handler
def _(sections, args, dry_run):
    return process_split(
        sections=sections,
        frg_size=args.frg_size,
        overlap=args.overlap,
        batches=args.batches,
        dry_run=dry_run,
    )


main = cmd.main

if __name__ == "__main__":
    import sys
    sys.exit(main())
