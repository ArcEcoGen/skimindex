# Pipeline Commands

The following subcommands are built into the container image and available via
`skimindex <command>`. For global options, runtime detection, and bind-mount
configuration see [Entry Point](entrypoint.md).

All pipeline commands share a common set of flags inherited from the
`SkimCommand` base class:

| Flag | Description |
|------|-------------|
| `--list` | Print available sections (datasets or divisions) as CSV and exit. |
| `--dry-run` | Show what would be done without executing anything. |
| `--help` | Show command help and exit. |

---

## `download` — Download raw data

Download GenBank flat-file releases and NCBI reference genome assemblies.

```
skimindex download                        # download everything
skimindex download genbank [options]      # GenBank flat-files only
skimindex download ncbi    [options]      # NCBI genome assemblies only
```

### `download genbank`

Downloads GenBank flat-file divisions declared in `[source.genbank]`.

| Option | Description |
|--------|-------------|
| `--division DIV` | Process a single GenBank division (e.g. `pln`, `bct`). |
| `--status` | Show download status without downloading. |
| `--list` | Print available divisions and exit. |
| `--dry-run` | Show what would be downloaded without executing. |

### `download ncbi`

Downloads NCBI reference genome assemblies declared as `source = "ncbi"` data
sections.

| Option | Description |
|--------|-------------|
| `--dataset NAME` | Process a single NCBI dataset (e.g. `human`, `plants`). |
| `--taxon TAXON` | Query assemblies for a taxon and display results (no download). |
| `--one-per species\|genus` | Keep only one assembly per species or genus. |
| `--assembly-level LEVEL` | Filter by assembly level (e.g. `complete`, `chromosome`). |
| `--assembly-source SOURCE` | Filter by assembly source (`refseq`, `genbank`). |
| `--assembly-version VERSION` | Filter by assembly version (e.g. `latest`). |
| `--reference` | Filter to reference assemblies only. |
| `--status` | Show download status without downloading. |
| `--list` | Print available datasets and exit. |
| `--dry-run` | Show what would be downloaded without executing. |

---

## `decontam` — Build decontamination k-mer index

Builds a [kmindex](https://tlemane.github.io/kmindex/) presence/absence index
from a set of reference sequences representing biological contaminants (e.g.
human, fungi, bacteria). The resulting index is used at query time to identify
and remove reads whose k-mer content overlaps with the reference.

The pipeline runs per dataset declared with `role = "decontamination"` in
`skimindex.toml` and proceeds in three sequential steps:

```
skimindex decontam                        # run full pipeline (prepare + count + index)
skimindex decontam prepare [options]      # step 1 — fragment reference sequences
skimindex decontam count   [options]      # step 2 — count k-mers (ntcard)
skimindex decontam index   [options]      # step 3 — build kmindex sub-indexes
```

Each step is stamped independently. Re-running `decontam` skips any dataset
whose output is already stamped.

### `decontam prepare`

Transforms each reference sequence file into a set of fixed-length overlapping
fragments, filters out degenerate sequences (N-only), and distributes the result
into a fixed number of FASTA batch files.

**Processing chain** (configured in `[processing.prepare_decontam]`):

1. **split** — slides a window of `size` bp with `overlap` bp between consecutive
   fragments over each input sequence (default: size = 200, overlap = 28).
   The overlap value should be set to $k - 1$ where $k$ is the k-mer size used
   for indexing, so that every k-mer spanning a fragment boundary is represented.
2. **filter_n_only** — discards fragments composed entirely of N bases.
3. **distribute** — partitions fragments into `batches` FASTA files
   (default: 20) to allow parallel processing downstream.

Output: `processed_data/decontamination/{dataset}/parts/`

| Option | Description |
|--------|-------------|
| `--dataset NAME` | Process a single decontamination dataset (e.g. `human`, `fungi`). |
| `--list` | Print available datasets and exit. |
| `--dry-run` | Show what would be processed without executing. |

### `decontam count`

Estimates the k-mer frequency spectrum of the prepared fragments using
[ntCard](https://github.com/bcgsc/ntCard).

ntCard produces a histogram file `{prefix}_k{K}.hist` per dataset with the
frequency distribution of all k-mers of length $k$ (`kmer_size`, default 29).
The histogram includes two aggregate statistics used by the next step:

- **F0** — estimated *total* k-mer count (including duplicates across fragments).
- **F1** — estimated number of *distinct* k-mers.

Output: `processed_data/decontamination/{dataset}/kmercount/`

| Option | Description |
|--------|-------------|
| `--dataset NAME` | Process a single decontamination dataset. |
| `--list` | Print available datasets and exit. |
| `--dry-run` | Show what would be processed without executing. |

### `decontam index`

Builds a kmindex Bloom filter sub-index for each decontamination dataset and
registers it in the global meta-index at `indexes/decontamination/`. Called
**once per dataset** (not once per assembly).

**FOF generation**

Before calling `kmindex build`, a kmtricks file-of-files (FOF) is generated
automatically:

- The `parts/` directory of the dataset is scanned recursively for assembly subdirectories.
- One sample is created per assembly subdirectory of `parts/`.
- Sample names are derived from the relative path of the subdirectory: `re.sub(r"[^A-Za-z0-9_-]", "_", "--".join(rel.parts))`.
- `register_as` = first component of the dataset's subdir path (e.g. `"Human"`, `"Plants"`).
- The FOF file is named `{register_as}.fof` and stored in `processed_data/decontamination/{dataset}/kmindex/`.

FOF example for Plants (62 assemblies, one sample per assembly):

```
Spermatophyta--GCF_000001735_4 : /path/parts/Spermatophyta/GCF_000001735.4/file1.fa.gz ; /path/parts/Spermatophyta/GCF_000001735.4/file2.fa.gz
Spermatophyta--GCF_000002775_5 : /path/parts/Spermatophyta/GCF_000002775.5/file1.fa.gz
...
```

**Bloom filter sizing**

kmindex uses a single-hash presence/absence Bloom filter (`--bloom-size` flag).
For a query requiring $z$ consecutive k-mer hits to call a positive match, the
false positive probability is:

$$P_{fpr} = \left(\frac{n}{n + m}\right)^z$$

where $n$ is the number of k-mers inserted into the filter (taken from the
**maximum F1** across all samples in the ntcard histograms — not the sum) and
$m$ is the number of cells in the filter (`bloom_size`). Inverting for $m$:

$$m = \left\lceil n \cdot \left(p^{-1/z} - 1\right) \right\rceil$$

The `bloom_size` value is computed automatically from the ntcard histograms
produced by `decontam count`, using the `fpr` and `zvalue` parameters declared
in `[processing.build_index_decontam]` (defaults: $p = 10^{-3}$, $z = 3$).
`hard_min = 1` is used because reference sequences are not sequencing data —
every k-mer occurrence counts.

**Index structure**

Each dataset produces a sub-index registered by name in the global meta-index:

```
indexes/decontamination/
├── Human/       ← sub-index run dir (created by kmindex)
├── Fungi/
├── Bacteria/
└── Plants/
```

The root `indexes/decontamination/` is the meta-index consumed by
`kmindex query` or `kmindex query2` at decontamination time. The stamp for each
dataset is written to `processed_data/decontamination/{dataset}/kmindex/`.

| Option | Description |
|--------|-------------|
| `--dataset NAME` | Process a single decontamination dataset. |
| `--list` | Print available datasets and exit. |
| `--dry-run` | Show what would be processed without executing. |

---

## `validate` — Validate configuration

Loads `config/skimindex.toml`, runs all validation rules, and reports errors.

```
skimindex validate [--config PATH]
```

| Option | Description |
|--------|-------------|
| `--config PATH` | Path to the config file (default: `/config/skimindex.toml`). |

Exits with code `0` if valid, `1` if errors are found.

---

## User subcommands

Scripts placed in the project's `usercmd/` directory are automatically
available as subcommands without rebuilding the image.

```
skimindex <name> [options]
```

Each script runs **inside the container** with:

- `usercmd/` bind-mounted to `/usercmd/`
- `SKIMINDEX_SCRIPTS_DIR=/app/scripts` set, so scripts can source the
  skimindex libraries:

```bash
source "${SKIMINDEX_SCRIPTS_DIR}/__skimindex.sh"   # log + config + stamping
```

The first non-empty comment line of the script (after the shebang and any
separator) is used as its description in `skimindex --help`.
