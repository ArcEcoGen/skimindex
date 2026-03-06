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
| `make` | Build and run orchestration | host |
| `skopeo` | Push multi-arch image to registry | release only |

The Makefile in `docker/` auto-detects the available runtime in priority order:
**Apptainer > Docker > Podman**.

### Pull the pre-built image

**Apptainer (SIF format — recommended on HPC):**

```bash
cd docker/
make pull-sif
```

The SIF file is saved to `images/skimindex-latest.sif`.

**Docker / Podman:**

The image is pulled automatically from the registry the first time a `make run`
or `make download_*` target is executed.

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
│   └── Makefile                # build, run and registry targets
├── genbank/
│   └── Makefile                # GenBank flat-file download and FASTA conversion
├── images/                     # SIF files produced by `make pull-sif`
├── indexes/                    # kmindex index files (mounted as /indexes)
├── log/                        # pipeline log files (mounted as /log)
├── obiluascripts/              # Lua scripts for OBITools4
│   └── splitseqs_31.lua        # fragment sequences at 31-mer overlap
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
│   ├── download_references.sh  # master download coordinator
│   ├── download_genbank.sh     # download GenBank flat-file divisions
│   ├── download_refgenome.sh   # download a genome section defined in config
│   ├── download_human.sh       # shortcut → download_refgenome.sh --section human
│   └── download_plants.sh      # shortcut → download_refgenome.sh --section plants
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

No Makefile change is needed — the bind-mount flags are generated automatically.

### `[logging]` — log level and file

```toml
[logging]
level = "INFO"               # DEBUG | INFO | WARNING | ERROR
file  = "/log/skimindex.log" # container path; maps to log/skimindex.log on host
```

### `[directories]` — container-side data roots

```toml
[directories]
genbank = "/genbank"   # root for all downloaded reference data inside the container
```

### `[genbank]` — GenBank flat-file divisions

```toml
[genbank]
divisions = "bct pln"   # space-separated two-letter division codes
                        # Full list: bct inv mam phg pln pri rod vrl vrt
```

### Genome sections — one TOML section per reference target

Any section that contains a `taxon` key is treated as a genome download target.
The section name is used as an identifier (passed to `--section`).

```toml
[human]
taxon            = "human"
directory        = "Human"       # relative to [directories].genbank → /genbank/Human
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

Reserved section names (never treated as genome targets):
`logging`, `local_directories`, `directories`, `genbank`.

---

## Usage

All commands are run from the `docker/` directory.
Scripts inside the container are available directly by name (no path prefix needed)
because `/app/scripts` is on `$PATH`.

```bash
cd docker/
```

### Interactive shell

```bash
make run        # production shell
make run-dev    # development shell (source tree mounted at /workspace)
```

### Install genome data

#### Download reference data

Download everything configured in `skimindex.toml` in a single step:

```bash
make download_references
```

Or run individual steps:

```bash
make download_genbank    # GenBank flat-file divisions (bct, pln, …)
make download_human      # human reference genome (RefSeq, chromosome level)
make download_plants     # Spermatophyta complete assemblies
```

All download scripts support `--help` for detailed usage.

##### GenBank flat files

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

To download additional divisions without editing the config:

```bash
# Inside the container:
download_genbank.sh --divisions "bct pln pri"

# Or via make:
make download_genbank
# (set divisions in config/skimindex.toml [genbank] section)
```

##### Reference genomes (human, plants, custom)

`download_refgenome.sh` downloads all assemblies matching the filters for a
given taxon and produces one `{organism}-{accession}.gbff.gz` file per accession:

```bash
# Inside the container:
download_refgenome.sh --section human
download_refgenome.sh --section plants
download_refgenome.sh --taxon "Fungi" --output /genbank/Fungi \
                      --assembly-level complete
```

To add a new genome target, add a section to `skimindex.toml` and run:

```bash
make download_references   # picks up all sections automatically
```

### Decontamination filter

> **Note:** the decontamination workflow is partially automated.
> The steps below may require manual intervention or HPC job submission.

#### Preparing references

> *Not yet automated — see DEV.md for current manual procedure.*

The reference FASTA files must be fragmented into overlapping 200 bp windows
before indexing, using `obiluascripts/splitseqs_31.lua` (31-mer overlap):

```bash
# Inside the container (example for human):
obiscript -S /app/obiluascripts/splitseqs_31.lua \
          /genbank/Human/*.gbff.gz \
| obigrep -v -s '^n+$' \
| obidistribute -Z -n 20 \
               -p /genbank/Human/fragments/human_genome_frg_%s.fasta.gz
```

K-mer counts are needed to size the Bloom filter:

```bash
ntcard -k 31 -o /genbank/Human/human_kmer_spectrum.txt \
       /genbank/Human/*.gbff.gz 2>&1 | head -2 \
       > /genbank/Human/human_kmer_stats.txt
```

#### Decontaminate genomes

> *Not yet automated.*

Once fragment files and k-mer counts are available, build a kmindex index
and run decontamination queries against the index.
Refer to `DEV.md` and the kmindex documentation for current procedure.

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
