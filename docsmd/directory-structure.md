# skimindex Directory Structure

## Overview

skimindex uses two distinct directory trees:

- **Usage directories** — runtime data, managed by the pipeline (bind-mounted into the container)
- **Development directories** — source code, configuration, and build artefacts (project repository)

All usage directories are bind-mounted into the container at
`${SKIMINDEX_ROOT}/<name>` (default `SKIMINDEX_ROOT=/`). Host-side paths are
declared in
[`[local_directories]`](config-format.md#local_directories)
inside `config/skimindex.toml`.

---

## Usage Directories

### Supported sequence file formats

All sequence data — whether from public databases or internal sequencing — may
be stored in any format supported by OBITools4, both compressed and
uncompressed:

| Format | Extensions |
|--------|------------|
| FASTA  | `.fasta`, `.fa`, `.fasta.gz`, `.fa.gz` |
| FASTQ  | `.fastq`, `.fastq.gz` |
| EMBL   | `.embl`, `.embl.gz` |
| GenBank flat-file | `.gbff`, `.gbff.gz` |

OBITools4 detects the format automatically from the file content.

---

### Public database raw data (source: `ncbi` and `genbank`)

Stores all raw sequence data downloaded from public databases. Both the `ncbi`
and `genbank` sources point to a `[local_directories]` entry via their
`directory` key. By default both are configured to use the same mount point:

```toml
[ncbi]
directory = "genbank"     # → ${SKIMINDEX_ROOT}/genbank/

[genbank]
directory = "genbank"     # → ${SKIMINDEX_ROOT}/genbank/
```

The generic layout inside that mount point is:

**Species-organised data** ([`by_species = true`](config-format.md#common-keys), default) — one subdirectory
per data section, files named with the canonical `--` separator.
Each accession corresponds to one sequenced individual of the species.

```
{source-directory}/
└── {data.directory}/
    │
    │  # Level 0 — one file per species (single accession = single individual)
    ├── {Species_name}--{accession}.<ext>
    │
    │  # Level 1 — multiple individuals, one file each
    ├── {Species_name}/
    │   ├── {accession_1}.<ext>      # individual 1
    │   └── {accession_2}.<ext>      # individual 2
    │
    │  # Level 2 — multiple individuals, multiple files each
    └── {Species_name}/
        ├── {accession_1}/           # individual 1
        │   └── *.<ext>
        └── {accession_2}/           # individual 2
            └── *.<ext>
```

**Non-species-organised data** ([`by_species = false`](config-format.md#common-keys)) — applies to bulk
GenBank flat-file sources where sequences are not separated by species:

```
{source-directory}/
└── Release_{N}/                 # one subdirectory per GenBank flat-file release
    ├── fasta/
    │   └── {division}/          # e.g. bct/, pln/
    │       └── gb{div}{N}.fasta.gz
    └── taxonomy/
        └── ncbi_taxonomy.tgz
```

With the default configuration this resolves to `${SKIMINDEX_ROOT}/genbank/`.

#### File naming convention for NCBI genome files

NCBI genome files are named `{Taxon_name}-{accession}.gbff.gz` where
`{Taxon_name}` follows these rules:

| Case | Convention | Example |
|------|-----------|---------|
| Species | `Genus_species` | `Arabidopsis_thaliana--GCA_946409825.1.gbff.gz` |
| Subspecies | `Genus_species_subsp._subspecies` | `Brassica_rapa_subsp._chinensis--GCA_052186795.1.gbff.gz` |
| Variety | `Genus_species_var._variety` | `Oryza_sativa_var._japonica--GCA_….gbff.gz` |
| Hybrid (species × species) | `Genus_species_x_other` | `Mentha_aquatica_x_spicata--GCA_….gbff.gz` |
| Hybrid (genus level) | `Genus_x_name` | `Mentha_x_piperita--GCA_….gbff.gz` |

The general rules for producing a canonical filename are:

1. **Spaces → underscores**: every space is replaced by `_`.
2. **Ambiguous characters removed**: any character that is not alphanumeric,
   `_`, `-`, or `.` is deleted. This includes parentheses, quotes, slashes,
   brackets, and other shell-special characters.
3. **Rank markers preserved**: `subsp.`, `var.`, and `x` are kept as literal
   strings surrounded by underscores.

The canonical filename is:

```
{canonical_taxon_name}--{canonical_accession}.{ext}
```

`--` is the **reserved separator** between the taxon name and the accession.
The accession is always the part after the **last `--`** in the filename stem.
The sequence `--` is consequently forbidden inside both the taxon name and the
accession (treated as a degenerate case).

Examples:
- `Arabidopsis_thaliana--GCA_946409825.1.gbff.gz`
- `Brassica_rapa_subsp._chinensis--GCA_052186795.1.gbff.gz`
- `Mentha_x_piperita--GCA_….gbff.gz`

### Internal raw data (source: `internal`)

Stores internal sequencing data produced in-house. The `internal` source points
to a `[local_directories]` entry via its `directory` key. By default:

```toml
[internal]
directory = "raw_data"    # → ${SKIMINDEX_ROOT}/raw_data/
```

The generic layout inside that mount point is:

Internal data follows the same species-organised layout (`by_species = true`
by default). Each accession corresponds to one sequenced individual.

```
{source-directory}/
└── {data.directory}/
    │
    │  # Level 0 — one file per species (single individual)
    ├── {Species_name}--{accession}.<ext>
    │
    │  # Level 1 — multiple individuals, one file each
    ├── {Species_name}/
    │   ├── {accession_1}.<ext>      # individual 1
    │   └── {accession_2}.<ext>
    │
    │  # Level 2 — multiple accessions, multiple files each
    └── {Species_name}/
        ├── {accession_1}/
        │   └── *.<ext>
        └── {accession_2}/
            └── *.<ext>
```

### `processed_data/` — Processed data

Stores all pipeline outputs. Layout depends on whether the data section is
species-organised (`by_species`). The `{processing.directory}` level names
the processing step (e.g. `split`, `kmercount`).
Mounted read-write at `${SKIMINDEX_ROOT}/processed_data/`.

**Species-organised** (`by_species = true`):

```
{[processed_data].directory}/
└── {[role].directory}/          # e.g. decontamination/, genomes/
    └── {data.directory}/
        └── {Species_name}/
            └── {accession}/     # "default" if source was a level-0 flat file
                └── {[processing].directory}/
                    └── *.<ext>
```

**Non-species-organised** (`by_species = false`):

```
{[processed_data].directory}/
└── {[role].directory}/          # e.g. decontamination/
    └── {data.directory}/
        └── {[processing].directory}/
            └── *.<ext>
```

### `indexes/` — K-mer indexes

Stores k-mer indexes built from processed data.
Mounted read-write at `${SKIMINDEX_ROOT}/indexes/`.

The top-level organisation by role is fixed. The internal structure below that
level is not yet specified.

```
{indexes}/
└── {role}/                      # e.g. decontamination/
    └── ...                      # to be specified
```

### `config/` — Configuration

Mounted read-only at `${SKIMINDEX_ROOT}/config/`. See
[Configuration File Format](config-format.md) for the full specification.

```
config/
└── skimindex.toml               # main pipeline configuration
```

### `log/` — Logs

Mounted read-write at `${SKIMINDEX_ROOT}/log/`.

```
log/
└── skimindex.log                # main pipeline log (filename set in [logging])
```

### `stamp/` — Stamp files

Stamp files track completed pipeline steps, allowing interrupted runs to resume
without reprocessing. The `stamp/` tree mirrors the full `${SKIMINDEX_ROOT}`
tree (excluding `stamp/` itself): for any output path, the stamp file is at
`${SKIMINDEX_ROOT}/stamp/<relative-path>.stamp`.

Mounted read-write at `${SKIMINDEX_ROOT}/stamp/`.

```
stamp/
├── genbank/
│   └── Plants/
│       └── Arabidopsis_thaliana--GCA_946409825.1.gbff.gz.stamp
├── processed_data/
│   └── decontamination/
│       └── human/
│           └── Homo_sapiens--GCF_000001405.40/
│               └── default/
│                   └── split/
│                       └── frg_1.fasta.gz.stamp
└── ...
```

---

## Development Directories

### `src/` — Source code

```
src/
├── skimindex_py/                # Python package
│   ├── pyproject.toml
│   ├── skimindex/               # main package
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── cli.py               # command-line interface
│   │   ├── config.py            # TOML config loading and env var export
│   │   ├── log.py               # logging (colors, file output, levels)
│   │   ├── sequences.py         # sequence file discovery utilities
│   │   ├── stamp.py             # stamp file management
│   │   ├── decontamination/     # decontamination pipeline
│   │   │   ├── sections.py      # directory helpers for decontamination sections
│   │   │   ├── split.py         # reference genome splitting into fragments
│   │   │   └── kmercount.py     # k-mer counting for decontamination indices
│   │   ├── download/            # download orchestration
│   │   │   ├── genbank.py       # GenBank flat-file download and conversion
│   │   │   └── refgenome.py     # NCBI reference genome download
│   │   └── unix/                # Unix CLI tool wrappers (plumbum-based)
│   │       ├── base.py          # LoggedBoundCommand base class
│   │       ├── compress.py      # pigz, unzip
│   │       ├── download.py      # curl
│   │       ├── ncbi.py          # datasets, dataformat
│   │       ├── ntcard.py        # ntCard k-mer counter
│   │       └── obitools.py      # OBITools4 bioinformatics suite
│   └── tests/                   # unit tests
│       ├── test_cli.py
│       ├── test_config.py
│       ├── test_download_logic.py
│       ├── test_integration_logging.py
│       ├── test_log.py
│       ├── test_sequences.py
│       ├── test_stamp.py
│       ├── test_unix_base.py
│       └── test_unix_wrappers.py
└── kmerasm/                     # C source for k-mer assembler
    ├── Makefile
    └── kmerasm.c
```

### `docker/` — Container build

```
docker/
├── Dockerfile                   # final container image
├── Dockerfile.in                # Dockerfile template
├── Makefile                     # build targets
├── build_user_script.sh         # generates the skimindex user script
├── install_obitools.sh          # OBITools4 installation helper
└── skimindex.sh.in              # entry-point script template
```

### `docs/` — Documentation

```
docs/
├── config-format.md             # configuration file format specification
└── directory-structure.md       # this file
```

### `config/` — Pipeline configuration (host side)

```
config/
└── skimindex.toml               # pipeline configuration (bind-mounted read-only)
```

### `scripts/` — Internal shell scripts

```
scripts/
├── __skimindex_config.sh        # config parsing helpers (bash)
├── __utils_functions.sh         # shared utility functions
├── __download_functions.sh      # download helpers
└── _download_refgenome.sh       # reference genome download script
```

### `jobscripts/` — HPC job scripts

Slurm/PBS job scripts for running pipeline steps on a cluster.

```
jobscripts/
├── download_references.sh
├── split_references.sh
├── contaminent_build.sh
└── ...
```

### `bin/` — Compiled binaries (generated)

Built artefacts, not tracked by git.

### `skimindex.sh` — Main entry point

Wrapper script that sets up bind-mounts and launches the container.
