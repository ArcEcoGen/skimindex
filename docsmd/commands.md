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

## `decontam` — Prepare decontamination filter

Prepare reference sequences for building the decontamination k-mer filter.

```
skimindex decontam                        # run full pipeline (prepare + count)
skimindex decontam prepare [options]      # split genomes into fragments
skimindex decontam count   [options]      # count k-mers in fragments
```

### `decontam prepare`

Splits reference genomes into overlapping fragments using the
`[processing.prepare_decontam]` pipeline.

| Option | Description |
|--------|-------------|
| `--dataset NAME` | Process a single decontamination dataset (e.g. `human`, `fungi`). |
| `--list` | Print available datasets and exit. |
| `--dry-run` | Show what would be processed without executing. |

### `decontam count`

Counts k-mers in prepared fragments using `[processing.count_kmers_decontam]`.

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
