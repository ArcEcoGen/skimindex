"""
Prepare decontamination filter data.

Usage:
  decontam                        Prepare all decontamination datasets
  decontam prepare [options]      Split reference genomes into fragments
  decontam count [options]        Count k-mers in prepared fragments
  decontam index [options]        Build kmindex sub-indexes

Run 'decontam <subcommand> --help' for subcommand options.
"""

import sys

from skimindex.cli import SkimCommand


def _list_sections() -> str:
    from skimindex.datasets import datasets_for_role
    return ",".join(ds.name for ds in datasets_for_role("decontamination"))


def _run_pipeline(processing_name: str, sections: list[str] | None, dry_run: bool) -> int:
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

    pipeline = build(processing_name)

    loginfo(f"===== {processing_name} =====" + (" [DRY-RUN]" if dry_run else ""))
    loginfo(f"Processing {len(datasets)} dataset(s)")

    errors = 0
    for ds in datasets:
        loginfo(f">>> {ds.name}")
        count = 0
        try:
            for data in ds.to_data():
                count += 1
                try:
                    result = pipeline(data, dry_run=dry_run)
                    if result is None:
                        logerror(f"  Pipeline failed for {ds.name} ({data.subdir})")
                        errors += 1
                except Exception as e:
                    import traceback
                    logerror(f"  Pipeline exception for {ds.name} ({data.subdir}): {e}")
                    logerror(traceback.format_exc())
                    errors += 1
        except Exception as e:
            import traceback
            logerror(f"  to_data() exception for {ds.name}: {e}")
            logerror(traceback.format_exc())
            errors += 1
        if count == 0:
            logwarning(f"  No input data found for {ds.name} (download_dir={ds.download_dir})")
        loginfo(f"<<< {ds.name} done")

    if errors:
        logerror(f"===== {errors} failure(s) =====")
        return 1

    loginfo(f"===== {processing_name} done =====")
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
    return _run_pipeline("prepare_decontam", sections or None, dry_run)


# ---------------------------------------------------------------------------
# count subcommand
# ---------------------------------------------------------------------------

_count_cmd = SkimCommand(
    name="decontam count",
    description="Count k-mers in prepared decontamination fragments",
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


@_count_cmd.handler
def _(sections, args, dry_run):
    return _run_pipeline("count_kmers_decontam", sections or None, dry_run)


# ---------------------------------------------------------------------------
# index subcommand
# ---------------------------------------------------------------------------

_index_cmd = SkimCommand(
    name="decontam index",
    description="Build kmindex sub-indexes from k-mer count histograms",
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


@_index_cmd.handler
def _(sections, args, dry_run):
    return _run_pipeline("build_index_decontam", sections or None, dry_run)


# ---------------------------------------------------------------------------
# decontam — top-level command with subcommands
# ---------------------------------------------------------------------------

_decontam_cmd = SkimCommand(
    name="decontam",
    description="Prepare decontamination filter data.",
    list_fn=_list_sections,
    examples=[
        "%(prog)s",
        "%(prog)s --dry-run",
        "%(prog)s prepare --dataset human",
        "%(prog)s count --dataset human",
        "%(prog)s index --dataset human",
    ],
    section_arg="dataset",
    section_metavar="NAME",
    section_help="Process a single decontamination dataset",
)
_decontam_cmd.subcommand("prepare", _prepare_cmd)
_decontam_cmd.subcommand("count",   _count_cmd)
_decontam_cmd.subcommand("index",   _index_cmd)


@_decontam_cmd.handler
def _(sections, args, dry_run):
    return _run_pipeline("prepare_decontam", sections or None, dry_run)


main = _decontam_cmd.main

if __name__ == "__main__":
    sys.exit(main())
