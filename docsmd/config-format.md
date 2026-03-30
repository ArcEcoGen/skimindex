# skimindex Configuration File Format

## Overview

The skimindex configuration file (`config/skimindex.toml`) uses TOML format.
Sections fall into five categories, identified by a **TOML table prefix**:

| Prefix | Category | Example |
|--------|----------|---------|
| *(none — root level)* | **Configuration** | `[local_directories]`, `[logging]` |
| `source.` | **Source** | `[source.ncbi]`, `[source.genbank]` |
| `role.` | **Role** | `[role.decontamination]`, `[role.genomes]` |
| `processing.` | **Processing** | `[processing.split]`, `[processing.kmercount]` |
| `data.` | **Data** | `[data.human]`, `[data.plants]` |

The prefix makes the section type self-describing and removes the need for
any hardcoded list of reserved names.

- **Configuration sections** — infrastructure settings (paths, logging, pipeline storage locations)
- **Source sections** — one per data origin, defines where raw data are stored
- **Role sections** — one per data usage, defines processing parameters
- **Processing sections** — one per pipeline step, defines step parameters and output subdirectory
- **Data sections** — describe a dataset, require both `source` and `role` keys

The pipeline flow is: raw data live under their **source** directory → processed
outputs go to **`[processed_data]`** → k-mer indexes go to **`[indexes]`**.

The resulting directory layout is described in
[Directory Structure](directory-structure.md).

---

## Configuration Sections

### `[local_directories]`

Host-side paths for container bind-mounts. Each key `<k>` defines the host
path mounted to `${SKIMINDEX_ROOT}/<k>` inside the container. See
[Usage Directories](directory-structure.md#usage-directories) for the full
runtime layout.

`SKIMINDEX_ROOT` defaults to `/` inside the container, so by default the mount
point is `/<k>`. Set `SKIMINDEX_ROOT` to a different value to relocate all
mount points at once (e.g. for testing outside a container).

```toml
[local_directories]
genbank        = "genbank"
indexes        = "indexes"
raw_data       = "raw_data"
processed_data = "processed_data"
config         = "config"
log            = "log"
stamp          = "stamp"
usercmd        = "usercmd"   # optional user-defined sub-commands (mounted at /usercmd)
```

### `[logging]`

Log level, output file, and mirroring behaviour.

| Key         | Type    | Description                                                                 |
|-------------|---------|-----------------------------------------------------------------------------|
| `directory` | string  | Key from `[local_directories]` whose mount point is used as the log directory. The log file is written as `${SKIMINDEX_ROOT}/<directory>/<file>`. |
| `file`      | string  | Log filename within `directory` (default: `skimindex.log`)                  |
| `level`     | string  | `DEBUG`, `INFO`, `WARNING`, or `ERROR`                                      |
| `mirror`    | boolean | `true` → tee logs to screen AND file                                        |
| `everything`| boolean | `true` → redirect all stderr (commands, bash errors) to log as well         |

```toml
[logging]
directory  = "log"                # references [local_directories] key → ${SKIMINDEX_ROOT}/log/
file       = "skimindex.log"      # filename within directory
level      = "INFO"               # DEBUG | INFO | WARNING | ERROR
mirror     = true                 # tee to screen AND file
everything = true                 # redirect stderr to log as well
```

### `[processed_data]`

Root location for all pipeline outputs (processed sequences, statistics, etc.).

| Key         | Type   | Description                                                        |
|-------------|--------|--------------------------------------------------------------------|
| `directory` | string | Key from `[local_directories]` where all processed data are stored |

```toml
[processed_data]
directory = "processed_data"      # references [local_directories] key → ${SKIMINDEX_ROOT}/processed_data/
```

### `[indexes]`

Root location for k-mer index storage (final step of the pipeline).

| Key         | Type   | Description                                                   |
|-------------|--------|---------------------------------------------------------------|
| `directory` | string | Key from `[local_directories]` where k-mer indexes are stored |

```toml
[indexes]
directory = "indexes"             # references [local_directories] key → ${SKIMINDEX_ROOT}/indexes/
```

### `[stamp]`

Root location for stamp files used to track completed pipeline steps.
Stamp files allow interrupted runs to resume without reprocessing already-completed steps.

| Key         | Type   | Description                                                    |
|-------------|--------|----------------------------------------------------------------|
| `directory` | string | Key from `[local_directories]` where stamp files are stored    |

```toml
[stamp]
directory = "stamp"               # references [local_directories] key → ${SKIMINDEX_ROOT}/stamp/
```

### `[scratch]`

Root location for temporary files used during SRA processing (`prefetch` archives
and uncompressed FASTQ files). Files are removed automatically after each run.

On HPC systems, point this to a fast local scratch filesystem (e.g. `$TMPDIR` or
a node-local NVMe) by setting the corresponding `[local_directories]` entry to an
absolute host path.

| Key         | Type   | Description                                                       |
|-------------|--------|-------------------------------------------------------------------|
| `directory` | string | Key from `[local_directories]` where temporary files are written  |

```toml
[scratch]
directory = "scratch"             # references [local_directories] key → ${SKIMINDEX_ROOT}/scratch/
```

---

## Source Sections

One section per data origin. Each source section has a `directory` key
referencing a `[local_directories]` entry, which gives the root mount point
where raw data for that source are stored.

For a conceptual explanation of how sources, datasets, and roles interact at
runtime, see [Data Model](data.md).

### `[source.ncbi]`

Data downloaded via the NCBI Datasets CLI.

| Key         | Type   | Description                                                    |
|-------------|--------|----------------------------------------------------------------|
| `directory` | string | Key from `[local_directories]` where NCBI downloads are stored |

```toml
[source.ncbi]
directory = "genbank"             # references [local_directories] key → ${SKIMINDEX_ROOT}/genbank/
```

### `[source.genbank]`

Data to download from GenBank (FTP/HTTPS site) as flat-files.

| Key         | Type             | Description                                                          |
|-------------|------------------|----------------------------------------------------------------------|
| `directory` | string           | Key from `[local_directories]` where GenBank flat-files are stored   |
| `divisions` | array of strings | GenBank division codes to download.<br>Valid codes: `bct inv mam phg pln pri rod vrl vrt` |

```toml
[source.genbank]
directory = "genbank"             # references [local_directories] key → ${SKIMINDEX_ROOT}/genbank/
divisions = ["bct", "pln"]
```

### `[source.internal]`

Internal sequencing data produced in-house.

| Key         | Type   | Description                                                       |
|-------------|--------|-------------------------------------------------------------------|
| `directory` | string | Key from `[local_directories]` where internal data are stored     |

```toml
[source.internal]
directory = "raw_data"            # references [local_directories] key → ${SKIMINDEX_ROOT}/raw_data/
```

### `[source.sra]`

Raw sequencing reads downloaded from NCBI SRA. EBI (ERR/ERS/SAMEA) and DDBJ
accessions are mirrored at NCBI and supported transparently.

| Key         | Type   | Description                                                       |
|-------------|--------|-------------------------------------------------------------------|
| `directory` | string | Key from `[local_directories]` where SRA reads are stored         |

```toml
[source.sra]
directory = "sra"                 # references [local_directories] key → ${SKIMINDEX_ROOT}/sra/
```

---

## Role Sections

One section per data usage. The role name appears as an intermediate path
component for processed and indexed data, giving the full layout:

For species-organised data (`by_species = true`, default):

| Stage      | Path                                                                                                           |
|------------|----------------------------------------------------------------------------------------------------------------|
| Raw        | `${SKIMINDEX_ROOT}/<[source.X].directory>/<data.directory>/`                                                   |
| Processed  | `${SKIMINDEX_ROOT}/<[processed_data].directory>/<[role.X].directory>/<data.directory>/<species>/<accession>/<artifact_dir>/` |
| Indexes    | `${SKIMINDEX_ROOT}/<[indexes].directory>/<[role.X].directory>/`                                               |

where `<artifact_dir>` is the `dir` component of the processing section's `output` artifact reference.

For non-species-organised data (`by_species = false`):

| Stage      | Path                                                                                                           |
|------------|----------------------------------------------------------------------------------------------------------------|
| Raw        | `${SKIMINDEX_ROOT}/<[source.X].directory>/<data.directory>/`                                                   |
| Processed  | `${SKIMINDEX_ROOT}/<[processed_data].directory>/<[role.X].directory>/<data.directory>/<artifact_dir>/` |
| Indexes    | `${SKIMINDEX_ROOT}/<[indexes].directory>/<[role.X].directory>/`                                               |

### `[role.decontamination]`

Parameters for the decontamination filter role.

| Key        | Type   | Description                                                          |
|------------|--------|----------------------------------------------------------------------|
| `directory`| string | Subdirectory name within processed data tree                         |
| `run`      | string | Name of a `[processing.X]` section to execute (must have `directory`)|

```toml
[role.decontamination]
directory = "decontamination"
run       = "prepare_decontam"
```

### `[role.genomes]`

Parameters for the complete reference genomes role.

| Key        | Type    | Description                                                          |
|------------|---------|----------------------------------------------------------------------|
| `directory`| string  | Subdirectory name within processed data tree                         |
| `kmer_size`| integer | K-mer size used when indexing genomes                                |
| `run`      | string  | Name of a `[processing.X]` section to execute (optional)            |

```toml
[role.genomes]
directory = "genomes_15x"
kmer_size = 31
```

### `[role.genome_skims]`

Parameters for the low-coverage skim-sequenced genomes role.

| Key        | Type   | Description                                                          |
|------------|--------|----------------------------------------------------------------------|
| `directory`| string | Subdirectory name within processed data tree                         |
| `run`      | string | Name of a `[processing.X]` section to execute (optional)            |

```toml
[role.genome_skims]
directory = "skims"
```

---

## Processing Sections

Processing sections (`[processing.X]`) describe how data are transformed.
Each section is either **atomic** (single operation) or **composite** (ordered
sequence of steps). See [Processing Model](processing.md) for the full
specification including persistence rules and worked examples.

### Artifact references

Both the output location and any named input parameters are expressed as
**artifact references** using the `dir@[idx:]role` notation:

| Form | Resolves to |
|------|-------------|
| `"parts@decontamination"` | `processed_data/decontamination/…/parts/` |
| `"kmercount@decontamination"` | `processed_data/decontamination/…/kmercount/` |
| `"kmindex@decontamination"` | `processed_data/decontamination/…/kmindex/` (stamp target + FOF) |
| `"@idx:decontamination"` | `indexes/decontamination/` (global meta-index, no dataset subpath) |

The `…` component is the dataset-specific subpath supplied automatically at runtime.

### Atomic form

Has `type` (required) — maps to a registered `@processing_type` Python function.

| Key        | Type   | Required | Description                                                    |
|------------|--------|----------|----------------------------------------------------------------|
| `type`     | string | yes      | Registered processing function name                            |
| `output`   | string | yes*     | Artifact reference for the output. *Required to be runnable    |
| *(others)* | any    | no       | Operation-specific parameters (including named input refs)     |

```toml
[processing.count_kmers_decontam]
type      = "kmercount"
output    = "kmercount@decontamination"
sequence  = "parts@decontamination"   # named input — artifact reference
kmer_size = 29
threads   = 10
```

### Composite form

Has `steps` (required) — ordered list of named references (strings) or inline
atomics (inline tables `{type=...}`).

| Key      | Type   | Required | Description                                                           |
|----------|--------|----------|-----------------------------------------------------------------------|
| `steps`  | array  | yes      | Ordered steps: strings (named refs) or inline tables `{type=...}`    |
| `output` | string | yes*     | Artifact reference for the output. *Required when referenced by `run` |

```toml
[processing.prepare_decontam]
output = "parts@decontamination"
steps = [
  {type = "split",         size = 200, overlap = 28},
  {type = "filter_n_only"},
  {type = "distribute",    batches = 20},
]
```

### `type = "buildindex"` — Build a kmindex sub-index

Builds a kmindex presence/absence Bloom filter sub-index for a dataset and
registers it in a global meta-index. Called **once per dataset** via
`ds.to_index_data()`.

The `output` artifact reference points to
`processed_data/…/kmindex/` (stamp target and FOF location). The `index`
parameter is a separate artifact reference for the global kmindex meta-index
managed by kmindex itself.

FOF generation scans `parts/` subdirectories recursively — one sample per
assembly subdirectory. Sample names are sanitized with
`re.sub(r"[^A-Za-z0-9_-]", "_", "--".join(rel.parts))`. The FOF file is named
`{register_as}.fof` where `register_as` is the first component of the
dataset's subdir path (e.g. `"Human"`, `"Plants"`).

| Parameter    | Type    | Required | Description |
|--------------|---------|----------|-------------|
| `output`     | string  | yes      | Artifact ref for stamp target + FOF location: `"kmindex@decontamination"` → `processed_data/decontamination/{dataset}/kmindex/` |
| `index`      | string  | yes      | Artifact ref for the global kmindex meta-index: `"@idx:decontamination"` → `indexes/decontamination/` |
| `kmer_size`  | integer | yes      | K-mer length (must match `count_kmers_decontam`) |
| `zvalue`     | integer | yes      | Number of consecutive k-mer hits required for a positive match |
| `fpr`        | float   | yes      | Target false positive rate (e.g. `1e-3`) |
| `bloom_size` | integer | no       | Bloom filter size in cells. Computed automatically from max F1 across samples if absent |
| `hard_min`   | integer | no       | Minimum k-mer count to include (default: `1` — every k-mer counts for reference sequences) |
| `threads`    | integer | no       | Number of threads (default: 1) |
| `verbose`    | string  | no       | Verbosity level passed to kmindex (e.g. `"debug"`) |

```toml
[processing.build_index_decontam]
type      = "buildindex"
output    = "kmindex@decontamination"     # → processed_data/decontamination/{dataset}/kmindex/
index     = "@idx:decontamination"        # → indexes/decontamination/  (kmindex meta-index)
kmer_size = 29
zvalue    = 3
fpr       = 1e-3
hard_min  = 1
threads   = 10
verbose   = "debug"
```

---

## Data Sections

Every data section **must** contain both `source` and `role`.
Data sections use the `[data.<name>]` prefix where `<name>` is a free
identifier chosen by the user.

### Classification Keys

| Key      | Allowed values      | Meaning                                                        |
|----------|---------------------|----------------------------------------------------------------|
| `source` | `"ncbi"`            | Downloaded via the NCBI Datasets CLI                           |
|          | `"genbank"`         | Filtered from GenBank flat-files (FTP)                         |
|          | `"internal"`        | Internal sequencing data produced in-house                     |
|          | `"sra"`             | Raw reads downloaded from NCBI SRA                             |
| `role`   | `"decontamination"` | Sequences used to build the decontamination filter             |
|          | `"genomes"`         | Complete reference genomes                                     |
|          | `"genome_skims"`    | Low-coverage skim-sequenced genomes                            |

### Common Keys

| Key         | Type    | Description                                                                  |
|-------------|---------|------------------------------------------------------------------------------|
| `directory` | string  | Subdirectory name for this dataset. Defaults to the section name if absent.  |
| `by_species`| boolean | Whether data is organised per species/accession (default: `true`). Set to `false` for bulk sources such as GenBank flat-files where sequences are not separated by species. Controls the layout of processed data paths (see [Role Sections](#role-sections) and [processed_data](directory-structure.md#processed_data-processed-data)). |
| `run`       | string  | Override the role's `run` with a different `[processing.X]` for this dataset (optional). |

### Source-specific Keys

#### `source = "ncbi"`

| Key                | Type    | Description                                              |
|--------------------|---------|----------------------------------------------------------|
| `taxon`            | string  | Taxon name passed to `datasets download genome`          |
| `reference`        | boolean | Pass `--reference` filter to datasets                    |
| `assembly_source`  | string  | `refseq` or `genbank`                                    |
| `assembly_level`   | string  | `complete`, `chromosome`, `scaffold`, or `contig`        |
| `assembly_version` | string  | `latest` or `all`                                        |
| `one_per`          | string  | Keep one assembly per `genus` or `species` (optional)    |

#### `source = "genbank"`

Data sections with `source = "genbank"` are **not** backed by per-species raw
files. They are derived from the monolithic GenBank flat-file release by
applying one or two successive filters:

1. **Division filter** (`divisions`, required) — selects flat-files belonging
   to one or more GenBank divisions from the latest downloaded release.
2. **Taxonomic filter** (`taxid`, optional) — if present, only sequences whose
   taxonomy falls under the given NCBI taxon ID are retained.

The raw GenBank flat-files live under the `[source.genbank]` source directory and are
never copied per data section. The filtered output is the **first processed
artefact** for these sections and lives directly under `processed_data/`.

| Key        | Type             | Required | Description                                              |
|------------|------------------|----------|----------------------------------------------------------|
| `divisions`| array of strings | yes      | GenBank division codes to select (`bct`, `pln`, …). Must be a subset of the divisions declared in `[source.genbank] divisions`. |
| `release`  | string           | no       | Pin a specific release (e.g. `"270.0"`). Defaults to the latest downloaded release. |
| `taxid`    | integer          | no       | NCBI taxonomy ID. If present, only sequences belonging to this taxon are retained after division filtering. |

#### `source = "internal"`

No additional keys beyond the common `directory`.

#### `source = "sra"`

| Key          | Type             | Required | Description                                                            |
|--------------|------------------|----------|------------------------------------------------------------------------|
| `accessions` | array of strings | no       | Run accessions (SRR/ERR/DRR) or experiment accessions (SRX/ERX/DRX). For runs, the biosample is looked up automatically. For experiments, all associated runs are discovered. |
| `biosamples` | array of strings | no       | Biosample IDs (SAMEA/ERS/SRS/SAMN). All associated run accessions are discovered automatically. |
| `threads`    | integer          | no       | Number of threads for `fasterq-dump` (default: 4)                     |

At least one of `accessions` or `biosamples` must be present. Both may coexist;
runs are deduplicated across all sources.

Metadata (organism name, biosample, library layout) is resolved via the NCBI
Entrez API at download time.

```toml
[data.betula_skims]
source     = "sra"
role       = "genome_skims"
directory  = "Betula"
accessions = ["ERR7254752"]           # SRR/ERR/DRR run accessions
biosamples = ["SAMEA9098823"]         # SAMEA/ERS/SRS → all associated runs fetched
threads    = 4
```

### Role-specific Keys

#### `role = "decontamination"`

| Key       | Type    | Description                                                                                          |
|-----------|---------|------------------------------------------------------------------------------------------------------|
| `example` | boolean | `true` = positive example; `false` = counter-example (sequences that must **not** be filtered out)  |

---

## Examples

### Current data sections

```toml
[data.human]
source           = "ncbi"
role             = "decontamination"
example          = true
taxon            = "human"
reference        = true
assembly_source  = "refseq"
assembly_level   = "chromosome"
assembly_version = "latest"

[data.fungi]
source     = "genbank"
role       = "decontamination"
example    = true
by_species = false
divisions  = ["pln"]
taxid      = 4751

[data.bacteria]
source     = "genbank"
role       = "decontamination"
example    = true
by_species = false
divisions  = ["bct"]
taxid      = 1

[data.plants]
source           = "ncbi"
role             = "decontamination"
example          = false            # counter-example: must NOT be filtered out
taxon            = "Spermatophyta"
reference        = false
assembly_level   = "complete"
assembly_version = "latest"
one_per          = "genus"
```

### Future data sections (not yet active)

```toml
# Complete reference genome downloaded from NCBI
# [data.arabidopsis]
# source           = "ncbi"
# role             = "genomes"
# taxon            = "Arabidopsis thaliana"
# assembly_level   = "chromosome"
# assembly_version = "latest"

# Internal skim-sequenced genome
# [data.betula_nana]
# source    = "internal"
# role      = "genome_skims"
# directory = "Betula_nana"
```

---

## Validation Rules

1. The section type is determined by its TOML prefix: `source.`, `role.`, `processing.`, `data.`, or no prefix (configuration).
2. Configuration sections (no prefix) must **not** contain `source` or `role` keys. The valid configuration sections are: `local_directories`, `logging`, `processed_data`, `indexes`, `stamp`, `scratch`.
3. Data sections (`data.*`) must contain both `source` and `role`.
4. `source` must be one of: `"ncbi"`, `"genbank"`, `"internal"`, `"sra"`.
5. `role` must be one of: `"decontamination"`, `"genomes"`, `"genome_skims"`.
6. For `role = "decontamination"`, the `example` key is required (`true` or `false`).
7. For `source = "ncbi"`, the `taxon` key is required.
8. For `source = "genbank"`, `divisions` is required and must be a subset of
   the codes listed in `[source.genbank] divisions`.
9. For `source = "genbank"`, `taxid` is optional; when absent all sequences of
   the selected divisions are used.
9b. For `source = "sra"`, at least one of `accessions` or `biosamples` must be present.
10. For `source = "genbank"`, `by_species = true` is reserved for a future
    pre-processing step that would distribute sequences into per-species files
    using `obidistribute` (not yet implemented).
11. A `[processing.X]` section must have exactly one of `type` or `steps` (mutually exclusive).
12. A processing section referenced by a `run` key must have `output`.
13. Inline steps inside `steps` (`{type=...}`) must not have `steps` themselves (always atomic).
14. Artifact references (`output`, named inputs) must follow `dir@[idx:]role` or be a dict with `role` and `dir`.
15. The `role` part of an artifact reference must match a `[role.X]` section in the config.
16. See [Processing Model](processing.md) for the full processing validation rules.
