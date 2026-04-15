"""
Prepare decontamination filter data.

Usage:
  decontam                        Prepare all decontamination datasets
  decontam prepare [options]      Split reference genomes into fragments
  decontam count [options]        Count k-mers in prepared fragments
  decontam index [options]        Build kmindex sub-indexes
  decontam clean [options]        Decontaminate genome / skim datasets

Run 'decontam <subcommand> --help' for subcommand options.
"""

import sys

from skimindex.cli import SkimCommand


def _list_sections() -> str:
    from skimindex.datasets import datasets_for_role
    names = [ds.name for ds in datasets_for_role("decontamination")]
    return "\n".join(["dataset"] + names)


def _run_pipeline(processing_name: str, sections: list[str] | None, dry_run: bool, dataset_level: bool = False) -> int:
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
            for data in ([ds.to_index_data()] if dataset_level else ds.to_data()):
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
    return _run_pipeline("build_index_decontam", sections or None, dry_run, dataset_level=True)


# ---------------------------------------------------------------------------
# decontam — top-level command with subcommands
# ---------------------------------------------------------------------------

_decontam_cmd = SkimCommand(
    name="decontam",
    description=(
        "Build and apply the decontamination k-mer index.\n\n"
        "Subcommands:\n"
        "  prepare   Split reference genomes into overlapping fragments\n"
        "  count     Count k-mers in prepared fragments (ntcard)\n"
        "  index     Build kmindex Bloom filter sub-indexes\n"
        "  clean     Decontaminate genome / skim datasets against the index\n\n"
        "Run 'decontam <subcommand> --help' for subcommand options."
    ),
    list_fn=_list_sections,
    examples=[
        "%(prog)s",
        "%(prog)s --dry-run",
        "%(prog)s prepare --dataset human",
        "%(prog)s count --dataset human",
        "%(prog)s index --dataset human",
        "%(prog)s clean --list",
        "%(prog)s clean --dataset species_15x --species Betula_nana",
        "%(prog)s clean --dataset species_15x --species Betula_nana --individual IGA-24-34",
    ],
    section_arg="dataset",
    section_metavar="NAME",
    section_help="Process a single decontamination dataset",
)

# ---------------------------------------------------------------------------
# clean subcommand
# ---------------------------------------------------------------------------

def _list_skim_sections() -> str:
    import csv
    import io
    from skimindex.datasets import Dataset, all_datasets
    from skimindex.naming import scan_species_dir

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["dataset", "species", "individual"])

    for name, cfg in all_datasets().items():
        if cfg.get("role") not in ("genomes", "genome_skims"):
            continue
        ds = Dataset(name, cfg)
        dl = ds.download_dir
        if not dl.exists():
            continue
        seen: set[tuple[str, str]] = set()
        for _, subdir in scan_species_dir(dl):
            if len(subdir.parts) >= 2:
                key = (subdir.parts[0], subdir.parts[1])
                if key not in seen:
                    seen.add(key)
                    writer.writerow([name, key[0], key[1]])

    return buf.getvalue().rstrip()


def _run_clean_pipeline(
    sections: list[str] | None,
    dry_run: bool,
    species: str | None = None,
    individual: str | None = None,
) -> int:
    from skimindex.datasets import Dataset, all_datasets, get_dataset
    from skimindex.log import logerror, loginfo, logwarning
    from skimindex.processing import build

    if sections:
        datasets = [get_dataset(name) for name in sections]
    else:
        datasets = [
            Dataset(name, cfg)
            for name, cfg in all_datasets().items()
            if cfg.get("role") in ("genomes", "genome_skims")
        ]

    if not datasets:
        logwarning("No genomes/genome_skims datasets configured")
        return 0

    loginfo("===== clean =====" + (" [DRY-RUN]" if dry_run else ""))
    if species:
        loginfo(f"Filter species={species}" + (f" individual={individual}" if individual else ""))
    loginfo(f"Processing {len(datasets)} dataset(s)")

    errors = 0
    for ds in datasets:
        loginfo(f">>> {ds.name} (role={ds.role})")
        pipeline_name = (
            "clean_genomes" if ds.role == "genomes"
            else "clean_genome_skims"
        )
        try:
            pipeline = build(pipeline_name)
        except (ValueError, KeyError) as e:
            logerror(f"  Cannot build pipeline {pipeline_name!r}: {e}")
            errors += 1
            continue

        count = 0
        try:
            for data in ds.to_data():
                parts = data.subdir.parts if data.subdir else ()
                if species and (len(parts) < 2 or parts[-2] != species):
                    continue
                if individual and (len(parts) < 1 or parts[-1] != individual):
                    continue
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

    loginfo("===== clean done =====")
    return 0


_clean_cmd = SkimCommand(
    name="decontam clean",
    description="Decontaminate genome and skim datasets against the contamination index",
    list_fn=_list_skim_sections,
    examples=[
        "%(prog)s",
        "%(prog)s --list",
        "%(prog)s --dataset vaccinium_skims",
        "%(prog)s --dataset species_15x --species Betula_nana",
        "%(prog)s --dataset species_15x --species Betula_nana --individual IGA-24-34",
        "%(prog)s --dry-run",
    ],
    section_arg="dataset",
    section_metavar="NAME",
    section_help="Process a single genomes/genome_skims dataset",
)
_clean_cmd.add_argument(
    "--species",
    metavar="NAME",
    help="Restrict to a single species (as listed by --list)",
)
_clean_cmd.add_argument(
    "--individual",
    metavar="NAME",
    help="Restrict to a single individual (requires --species)",
)


@_clean_cmd.handler
def _(sections, args, dry_run):
    return _run_clean_pipeline(sections, dry_run,
                               species=args.species,
                               individual=args.individual)


_decontam_cmd.subcommand("prepare", _prepare_cmd)
_decontam_cmd.subcommand("count",   _count_cmd)
_decontam_cmd.subcommand("index",   _index_cmd)
_decontam_cmd.subcommand("clean",   _clean_cmd)


@_decontam_cmd.handler
def _(sections, args, dry_run):
    return _run_pipeline("prepare_decontam", sections or None, dry_run)


main = _decontam_cmd.main

if __name__ == "__main__":
    sys.exit(main())
