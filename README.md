# skimindex

**skimindex** is a containerized pipeline for building k-mer indexes from genome
data.

The pipeline runs inside an OCI container (Apptainer on HPC, Docker or Podman on
workstations).  All downloads and index files are stored on the host and
bind-mounted into the container at runtime — no data lives inside the image.

---

## Installation

### Prerequisites

| Tool | Purpose | Where needed |
|------|---------|-------------|
| [Apptainer](https://apptainer.org) | Container runtime (HPC, preferred) | cluster nodes |
| [Docker](https://docs.docker.com) or [Podman](https://podman.io) | Container runtime (workstation) | local machine |
| `make` | Build orchestration | host (developers) |
| `skopeo` | Push multi-arch image to registry | release only |

### Get the entry-point script

The `skimindex.sh` script is the single entry point for end users.
It auto-detects the available runtime (**Apptainer > Docker > Podman**) and
manages bind-mounts from the project configuration.

Download it from the repository or generate it with `make skimindex-script` in
`docker/`.

### Pull the container image

```bash
./skimindex.sh update
```

This pulls the latest image from the registry.  For Apptainer the SIF file is
saved to `images/skimindex-latest.sif`; for Docker/Podman the image is cached
locally.

### Build from source

```bash
cd docker/
make build                  # native platform only (Docker)
make build-multiplatform    # linux/amd64 + linux/arm64 (Docker buildx)
```

Key build variables (override on the command line or in `docker/Makefile`):

| Variable | Default | Description |
|----------|---------|-------------|
| `IMAGE_TAG` | `latest` | Image tag |
| `REGISTRY` | `registry.metabarcoding.org/arcecogen` | OCI registry |
| `GO_VERSION` | `latest` | Go base image tag |
| `MINICONDA_VERSION` | `latest` | Miniconda base image tag |
| `OBITOOLS_VERSION` | `latest` | OBITools4 version (`latest` or e.g. `4.4.8`) |
| `KMINDEX_VERSION` | `bioconda::kmindex` | kmindex conda specifier |
| `NTCARD_VERSION` | `bioconda::ntcard` | ntCard conda specifier |

---

## Directory structure

```
skimindex/
├── config/
│   └── skimindex.toml          # pipeline configuration (mounted as /config)
├── docker/
│   ├── Dockerfile              # multi-stage OCI image definition
│   ├── Makefile                # image build and push targets
│   └── skimindex.sh.in         # template for the user entry-point script
├── genbank/
│   └── Makefile                # GenBank flat-file download and FASTA conversion
├── images/                     # SIF files produced by `skimindex.sh update`
├── indexes/                    # kmindex index files (mounted as /indexes)
├── log/                        # pipeline log files (mounted as /log)
├── obiluascripts/              # Lua scripts for OBITools4
│   └── splitseqs_31.lua        # split sequences into overlapping fragments
├── genbank/                    # reference data (mounted as /genbank)
│   ├── Human/                  # human reference genome (.gbff.gz per accession)
│   ├── Plants/                 # plant reference genomes (.gbff.gz per accession)
│   └── Release_<N>/            # GenBank flat-file release
│       ├── fasta/
│       │   ├── bct/            # bacteria FASTA files
│       │   └── pln/            # land plants / fungi FASTA files
│       └── taxonomy/
│           └── ncbi_taxonomy.tgz
├── processed_data/             # post-processed results (mounted as /processed_data)
├── scripts/                    # pipeline shell scripts (inside container at /app/scripts)
│   ├── download_genbank.sh     # download GenBank flat-file divisions
│   ├── download_references.sh  # download all taxon genome sections defined in config
│   ├── split_references.sh     # split reference sequences into overlapping fragments
│   └── _download_refgenome.sh  # internal: download one genome section (called by download_references.sh)
├── skimindex.sh                # user entry-point (generated)
├── skims/                      # skim input/output files (mounted as /skims)
└── src/
    └── kmerasm/                # C tool — compute unitigs from a k-mer set
```

---

## Configuration

All pipeline parameters are stored in `config/skimindex.toml`.
This file is bind-mounted read-only at `/config` inside the container and parsed
by `scripts/__skimindex_config.sh`, which exports one environment variable per
key using the naming convention `SKIMINDEX__{SECTION}__{KEY}` (uppercase).

Pre-existing environment variables always take priority over config-file values.

### `[local_directories]` — host-side mount points

Each key `k` defines the **host path** that is bind-mounted to `/<k>` inside the
container.  Relative paths are resolved from the project root.

```toml
[local_directories]
genbank        = "genbank"         # host path → /genbank  in container
indexes        = "indexes"         # host path → /indexes
skims          = "skims"           # host path → /skims
processed_data = "processed_data"  # host path → /processed_data
config         = "config"          # host path → /config
log            = "log"             # host path → /log
```

To redirect a mount point to an external storage volume, set an absolute path:

```toml
genbank = "/data/nfs/genbank"
```

No script change is needed — the bind-mount flags are generated automatically
from this section.

### `[logging]` — log level and file

```toml
[logging]
level      = "INFO"               # DEBUG | INFO | WARNING | ERROR
file       = "/log/skimindex.log" # container path; maps to log/skimindex.log on host
mirror     = true                 # true → tee logs to screen AND file
everything = true                 # true → also redirect all stderr to the log
```

### `[genbank]` — GenBank flat-file divisions

```toml
[genbank]
divisions = "bct pln"   # space-separated two-letter division codes
                        # Full list: bct inv mam phg pln pri rod vrl vrt
```

### `[decontamination]` — fragment and index parameters

```toml
[decontamination]
kmer_size = 29    # k-mer size for decontamination indices
frg_size  = 200   # fragment length (bp) when splitting reference sequences
batches   = 20    # number of output batch files per reference section
```

The overlap between consecutive fragments is computed automatically as
`kmer_size - 1`, ensuring every k-mer spanning a fragment boundary appears in at
least one fragment.

### Genome sections — one TOML section per reference target

Two types of genome sections are supported:

**Taxon sections** — sequences downloaded via NCBI datasets (must have a `taxon` key):

```toml
[human]
taxon            = "human"
directory        = "Human"       # relative to /genbank → /genbank/Human
reference        = true          # pass --reference filter to NCBI datasets
assembly_source  = "refseq"      # refseq | genbank
assembly_level   = "chromosome"  # complete | chromosome | scaffold | contig
assembly_version = "latest"      # latest | all

[plants]
taxon            = "Spermatophyta"
directory        = "Plants"
reference        = false
assembly_level   = "complete"
assembly_version = "latest"
```

**Division sections** — sequences filtered from GenBank flat files
(must have both `taxid` and `divisions` keys):

```toml
[fungi]
taxid     = 4751    # NCBI taxon ID
divisions = "pln"   # GenBank division(s) to search
directory = "Fungi"

[bacteria]
taxid     = 1       # root (all bacteria via bct division)
divisions = "bct"
directory = "Bacteria"
```

Reserved section names (never treated as genome targets):
`logging`, `local_directories`, `genbank`.

---

## Usage

### Initialise a new project

```bash
./skimindex.sh init
```

Creates the directory structure and downloads the default `config/skimindex.toml`.

### Interactive shell

```bash
./skimindex.sh shell                        # production shell
./skimindex.sh shell --mount SRC:DST ...   # with extra bind-mounts
```

### Install genome data

Download everything configured in `skimindex.toml` in a single step:

```bash
./skimindex.sh download_references
```

Or run individual steps:

```bash
./skimindex.sh download_genbank      # GenBank flat-file divisions (bct, pln, …)
./skimindex.sh download_references   # all taxon sections defined in config
```

All subcommands support `--help` for detailed usage.

#### GenBank flat files

The `download_genbank.sh` script drives `genbank/Makefile` in a retry loop,
re-running `make` as long as new stamp files appear (network failures are
expected with hundreds of large files).

Downloads go to `genbank/Release_<N>/` with the following structure:

```
Release_<N>/
├── fasta/
│   ├── bct/         # one sub-directory per division
│   └── pln/
└── taxonomy/
    └── ncbi_taxonomy.tgz
```

#### Reference genomes (taxon sections)

`download_references` iterates over all taxon sections defined in `skimindex.toml`
and downloads one `{organism}-{accession}.gbff.gz` file per accession.

To add a new genome target, add a `taxon` section to `skimindex.toml` and run:

```bash
./skimindex.sh download_references   # picks up all sections automatically
```

### Split reference sequences

Fragment reference sequences into overlapping windows for k-mer index building:

```bash
./skimindex.sh split_references                   # all sections
./skimindex.sh split_references --section human   # single section
```

Output files are written to `<processed_data>/<section_directory>/fragments/frg_<N>.fasta.gz`.

The fragmentation is performed by `obiluascripts/splitseqs_31.lua`, controlled
by the `[decontamination]` configuration section.

---

## Container internals

The image is built in two stages:

1. **builder** (`golang`) — compiles OBITools4 from source and builds C tools
   in `src/` for the target architecture.
2. **skimindex** (`continuumio/miniconda3`) — installs conda packages
   (`kmindex`, `ntcard`), NCBI datasets CLI (`datasets`, `dataformat`),
   copies all scripts and binaries, and creates an unprivileged `skimindex` user.

Mount points created inside the image: `/genbank`, `/indexes`, `/skims`,
`/processed_data`, `/config`, `/log`.

Scripts are at `/app/scripts`; custom binaries at `/app/bin`.
Both are prepended to `$PATH`.
