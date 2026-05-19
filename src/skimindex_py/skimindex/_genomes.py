"""
Manage genome datasets.

Usage:
  genomes                    Process all genome datasets (clean + prepare)
  genomes clean [options]    Decontaminate genome / skim datasets
  genomes prepare [options]  Prepare genome fragments (ACGT-clean, low-complexity filter, distribute)

Run 'genomes <subcommand> --help' for subcommand options.
"""

import sys

from skimindex.cli import SkimCommand


def _list_sections() -> str:
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


def _iter_datasets(sections: list[str] | None):
    from skimindex.datasets import Dataset, all_datasets, get_dataset
    if sections:
        return [get_dataset(name) for name in sections]
    return [
        Dataset(name, cfg)
        for name, cfg in all_datasets().items()
        if cfg.get("role") in ("genomes", "genome_skims")
    ]


# ---------------------------------------------------------------------------
# clean subcommand
# ---------------------------------------------------------------------------

def _run_clean(sections, dry_run, species=None, individual=None) -> int:
    from skimindex.log import logerror, loginfo, logwarning
    from skimindex.processing import build

    datasets = _iter_datasets(sections)
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
        pipeline_name = "clean_genomes" if ds.role == "genomes" else "clean_genome_skims"
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
    name="genomes clean",
    description="Decontaminate genome and skim datasets against the contamination index",
    list_fn=_list_sections,
    examples=[
        "%(prog)s",
        "%(prog)s --list",
        "%(prog)s --dataset species_15x",
        "%(prog)s --dataset species_15x --species Betula_nana",
        "%(prog)s --dataset species_15x --species Betula_nana --individual IGA-24-34",
        "%(prog)s --dry-run",
    ],
    section_arg="dataset",
    section_metavar="NAME",
    section_help="Process a single genomes/genome_skims dataset",
)
_clean_cmd.add_argument("--species",    metavar="NAME", help="Restrict to a single species")
_clean_cmd.add_argument("--individual", metavar="NAME", help="Restrict to a single individual (requires --species)")


@_clean_cmd.handler
def _(sections, args, dry_run):
    return _run_clean(sections, dry_run, species=args.species, individual=args.individual)


# ---------------------------------------------------------------------------
# prepare subcommand
# ---------------------------------------------------------------------------

def _run_prepare(sections, dry_run, species=None, individual=None) -> int:
    from skimindex.datasets import Dataset
    from skimindex.log import logerror, loginfo, logwarning
    from skimindex.processing import build
    from skimindex.processing.data import directory_data
    from skimindex.sources import resolve_artifact

    datasets = _iter_datasets(sections)
    if not datasets:
        logwarning("No genomes/genome_skims datasets configured")
        return 0

    loginfo("===== prepare =====" + (" [DRY-RUN]" if dry_run else ""))
    if species:
        loginfo(f"Filter species={species}" + (f" individual={individual}" if individual else ""))
    loginfo(f"Processing {len(datasets)} dataset(s)")

    pipeline = build("prepare_genomes")

    errors = 0
    for ds in datasets:
        loginfo(f">>> {ds.name} (role={ds.role})")
        count = 0
        try:
            for data in ds.to_data():
                parts = data.subdir.parts if data.subdir else ()
                if species and (len(parts) < 2 or parts[-2] != species):
                    continue
                if individual and (len(parts) < 1 or parts[-1] != individual):
                    continue

                cleaned_dir = resolve_artifact("cleaned@genomes", data.subdir)
                if not cleaned_dir.exists():
                    logwarning(f"  Skipping {data.subdir}: cleaned output not found ({cleaned_dir})")
                    continue

                count += 1
                cleaned_data = directory_data(
                    cleaned_dir, subdir=data.subdir, per_species=data.per_species
                )
                try:
                    result = pipeline(cleaned_data, dry_run=dry_run)
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
            logwarning(f"  No cleaned data found for {ds.name}")
        loginfo(f"<<< {ds.name} done")

    if errors:
        logerror(f"===== {errors} failure(s) =====")
        return 1

    loginfo("===== prepare done =====")
    return 0


_prepare_cmd = SkimCommand(
    name="genomes prepare",
    description="Prepare genome fragments: ACGT-clean → low-complexity filter → distribute",
    list_fn=_list_sections,
    examples=[
        "%(prog)s",
        "%(prog)s --list",
        "%(prog)s --dataset species_15x",
        "%(prog)s --dataset species_15x --species Betula_nana",
        "%(prog)s --dry-run",
    ],
    section_arg="dataset",
    section_metavar="NAME",
    section_help="Process a single genomes/genome_skims dataset",
)
_prepare_cmd.add_argument("--species",    metavar="NAME", help="Restrict to a single species")
_prepare_cmd.add_argument("--individual", metavar="NAME", help="Restrict to a single individual (requires --species)")


@_prepare_cmd.handler
def _(sections, args, dry_run):
    return _run_prepare(sections, dry_run, species=args.species, individual=args.individual)


# ---------------------------------------------------------------------------
# genomes — top-level command
# ---------------------------------------------------------------------------

_genomes_cmd = SkimCommand(
    name="genomes",
    description=(
        "Manage genome datasets.\n\n"
        "Subcommands:\n"
        "  clean    Decontaminate genome / skim datasets against the index\n"
        "  prepare  ACGT-clean → low-complexity filter → distribute into parts\n\n"
        "Run 'genomes <subcommand> --help' for subcommand options."
    ),
    list_fn=_list_sections,
    examples=[
        "%(prog)s clean --dataset species_15x --species Betula_nana",
        "%(prog)s prepare --dataset species_15x --species Betula_nana",
        "%(prog)s clean --dry-run",
        "%(prog)s prepare --dry-run",
    ],
    section_arg="dataset",
    section_metavar="NAME",
    section_help="Process a single genomes/genome_skims dataset",
)

_genomes_cmd.subcommand("clean",   _clean_cmd)
_genomes_cmd.subcommand("prepare", _prepare_cmd)


@_genomes_cmd.handler
def _(sections, args, dry_run):
    return 0


main = _genomes_cmd.main

if __name__ == "__main__":
    sys.exit(main())
