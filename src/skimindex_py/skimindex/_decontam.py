"""
Prepare decontamination filter data.

Usage:
  decontam                        Prepare all decontamination datasets
  decontam prepare [options]      Split reference genomes into fragments

Run 'decontam prepare --help' for subcommand options.
"""

import argparse
import sys

from skimindex.cli import SkimCommand


def _list_sections() -> str:
    from skimindex.datasets import datasets_for_role
    return ",".join(ds.name for ds in datasets_for_role("decontamination"))


def _process_prepare(sections: list[str] | None, dry_run: bool) -> int:
    from skimindex.datasets import datasets_for_role, get_dataset
    from skimindex.log import logerror, loginfo, logwarning
    from skimindex.processing import build

    if sections:
        datasets = [get_dataset(name) for name in sections]
    else:
        datasets = datasets_for_role("decontamination")

    if not datasets:
        logwarning("No decontamination datasets configured")
        return 0

    pipeline = build("prepare_decontam")

    loginfo(f"===== Prepare decontam =====" + (" [DRY-RUN]" if dry_run else ""))
    loginfo(f"Processing {len(datasets)} dataset(s)")

    errors = 0
    for ds in datasets:
        loginfo(f">>> {ds.name}")
        for data in ds.to_data():
            result = pipeline(data, dry_run=dry_run)
            if result is None:
                logerror(f"  Pipeline failed for {ds.name} ({data.subdir})")
                errors += 1
        loginfo(f"<<< {ds.name} done")

    if errors:
        logerror(f"===== {errors} failure(s) =====")
        return 1

    loginfo("===== All datasets prepared =====")
    return 0


# ---------------------------------------------------------------------------
# prepare subcommand
# ---------------------------------------------------------------------------

_prepare_cmd = SkimCommand(
    name="decontam prepare",
    description="Split reference genomes into overlapping fragments",
    list_fn=_list_sections,
    examples=[
        "%(prog)s",
        "%(prog)s --list",
        "%(prog)s --dataset human",
        "%(prog)s --dry-run",
    ],
    section_arg="dataset",
    section_metavar="NAME",
    section_help="Process a single decontamination dataset (e.g. human, fungi)",
)


@_prepare_cmd.handler
def _(sections, args, dry_run):
    return _process_prepare(sections=sections or None, dry_run=dry_run)


# ---------------------------------------------------------------------------
# decontam — top-level entry point
# ---------------------------------------------------------------------------

_SUBCOMMANDS = {
    "prepare": _prepare_cmd.main,
}


def main(argv: list | None = None) -> int:
    """Prepare decontamination data, or a specific step via subcommand."""
    if argv is None:
        argv = sys.argv[1:]

    if argv and argv[0] in _SUBCOMMANDS:
        return _SUBCOMMANDS[argv[0]](argv[1:])

    parser = argparse.ArgumentParser(
        prog="decontam",
        description="Prepare decontamination filter data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Subcommands:\n"
            "  decontam prepare   Split reference genomes into fragments\n\n"
            "Run 'decontam <subcommand> --help' for subcommand-specific options."
        ),
    )
    parser.add_argument("--dry-run", action="store_true",
        help="Show what would be done without executing anything")
    args = parser.parse_args(argv)

    return _process_prepare(sections=None, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
