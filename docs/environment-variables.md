# Environment Variables

skimindex exports all configuration values as shell environment variables,
making them available to bash scripts, Makefile rules, and container
entrypoints without re-parsing the TOML file.

Variables are populated automatically when `__skimindex_config.sh` is sourced.
Inside the container the Python package reads them via `os.environ` with the
same precedence rules.

---

## Naming Convention

Every variable follows the pattern:

```
SKIMINDEX__{SECTION}__{KEY}
```

where dots in section names are replaced by double underscores:

| TOML section | Key | Variable |
|---|---|---|
| `[logging]` | `level` | `SKIMINDEX__LOGGING__LEVEL` |
| `[source.ncbi]` | `directory` | `SKIMINDEX__SOURCE__NCBI__DIRECTORY` |
| `[role.decontamination]` | `run` | `SKIMINDEX__ROLE__DECONTAMINATION__RUN` |
| `[processing.count_kmers_decontam]` | `kmer_size` | `SKIMINDEX__PROCESSING__COUNT_KMERS_DECONTAM__KMER_SIZE` |
| `[data.human]` | `taxon` | `SKIMINDEX__DATA__HUMAN__TAXON` |

**Precedence**: environment > config file > built-in defaults.
A variable already set in the environment is never overwritten.

**Value serialisation**:

- TOML arrays → space-separated string (`["bct", "pln"]` → `"bct pln"`)
- TOML booleans → lowercase string (`true` → `"true"`, `false` → `"false"`)
- Numeric and string values → `str(value)`
- Complex values (inline-table arrays such as `steps`) are not exported.

---

## Special Variables

These variables are not direct reflections of a single TOML key.

| Variable | Description |
|---|---|
| `SKIMINDEX_ROOT` | Container/runtime root path. Read from the environment; defaults to `/`. All path helpers prepend this value. |
| `SKIMINDEX__REF_TAXA` | Space-separated names of all datasets whose `source` is `ncbi` or `genbank`. |
| `SKIMINDEX__REF_GENOMES` | Space-separated names of all datasets whose `source` is `ncbi` (downloadable via NCBI Datasets CLI). |

---

## Variable Reference by Section

### `[local_directories]`

Each key `<k>` produces one variable whose value is the container-side mount
path `/<k>` (the host-side path from the TOML is discarded inside the
container).

| Variable | Default value |
|---|---|
| `SKIMINDEX__LOCAL_DIRECTORIES__GENBANK` | `/genbank` |
| `SKIMINDEX__LOCAL_DIRECTORIES__INDEXES` | `/indexes` |
| `SKIMINDEX__LOCAL_DIRECTORIES__RAW_DATA` | `/raw_data` |
| `SKIMINDEX__LOCAL_DIRECTORIES__PROCESSED_DATA` | `/processed_data` |
| `SKIMINDEX__LOCAL_DIRECTORIES__CONFIG` | `/config` |
| `SKIMINDEX__LOCAL_DIRECTORIES__LOG` | `/log` |
| `SKIMINDEX__LOCAL_DIRECTORIES__STAMP` | `/stamp` |
| `SKIMINDEX__LOCAL_DIRECTORIES__USERCMD` | `/usercmd` |

### `[logging]`

| Variable | Example value |
|---|---|
| `SKIMINDEX__LOGGING__DIRECTORY` | `log` |
| `SKIMINDEX__LOGGING__FILE` | `skimindex.log` |
| `SKIMINDEX__LOGGING__LEVEL` | `INFO` |
| `SKIMINDEX__LOGGING__MIRROR` | `true` |
| `SKIMINDEX__LOGGING__EVERYTHING` | `true` |

### `[processed_data]`, `[indexes]`, `[stamp]`

| Variable | Example value |
|---|---|
| `SKIMINDEX__PROCESSED_DATA__DIRECTORY` | `processed_data` |
| `SKIMINDEX__INDEXES__DIRECTORY` | `indexes` |
| `SKIMINDEX__STAMP__DIRECTORY` | `stamp` |

### `[source.X]`

One set of variables per source section.

| Variable | Example value |
|---|---|
| `SKIMINDEX__SOURCE__NCBI__DIRECTORY` | `genbank` |
| `SKIMINDEX__SOURCE__GENBANK__DIRECTORY` | `genbank` |
| `SKIMINDEX__SOURCE__GENBANK__DIVISIONS` | `bct pln` |
| `SKIMINDEX__SOURCE__INTERNAL__DIRECTORY` | `raw_data` |

### `[role.X]`

One set of variables per role section.

| Variable | Example value |
|---|---|
| `SKIMINDEX__ROLE__DECONTAMINATION__DIRECTORY` | `decontamination` |
| `SKIMINDEX__ROLE__DECONTAMINATION__RUN` | `prepare_decontam` |
| `SKIMINDEX__ROLE__GENOMES__DIRECTORY` | `genomes_15x` |
| `SKIMINDEX__ROLE__GENOMES__KMER_SIZE` | `31` |
| `SKIMINDEX__ROLE__GENOME_SKIMS__DIRECTORY` | `skims` |

### `[processing.X]`

One set of variables per processing section. Scalar keys only — the `steps`
array (list of inline tables) is not exported.

| Variable | Example value |
|---|---|
| `SKIMINDEX__PROCESSING__PREPARE_DECONTAM__ROLE` | `decontamination` |
| `SKIMINDEX__PROCESSING__PREPARE_DECONTAM__DIRECTORY` | `parts` |
| `SKIMINDEX__PROCESSING__COUNT_KMERS_DECONTAM__TYPE` | `kmercount` |
| `SKIMINDEX__PROCESSING__COUNT_KMERS_DECONTAM__ROLE` | `decontamination` |
| `SKIMINDEX__PROCESSING__COUNT_KMERS_DECONTAM__INPUT` | `prepare_decontam` |
| `SKIMINDEX__PROCESSING__COUNT_KMERS_DECONTAM__DIRECTORY` | `kmercount` |
| `SKIMINDEX__PROCESSING__COUNT_KMERS_DECONTAM__KMER_SIZE` | `29` |
| `SKIMINDEX__PROCESSING__COUNT_KMERS_DECONTAM__THREADS` | `10` |

### `[data.X]`

One set of variables per dataset. The exact keys depend on the dataset's
`source` and `role`; see [Configuration Format](config-format.md#data-sections)
for the full key reference.

```bash
# Example — data.human
SKIMINDEX__DATA__HUMAN__DIRECTORY=Human
SKIMINDEX__DATA__HUMAN__SOURCE=ncbi
SKIMINDEX__DATA__HUMAN__ROLE=decontamination
SKIMINDEX__DATA__HUMAN__TAXON=human
SKIMINDEX__DATA__HUMAN__REFERENCE=true
SKIMINDEX__DATA__HUMAN__ASSEMBLY_LEVEL=chromosome
SKIMINDEX__DATA__HUMAN__ASSEMBLY_VERSION=latest
```

---

## How Variables Are Loaded

### Inside the container

`__skimindex_config.sh` delegates all TOML parsing to the Python module:

```bash
eval "$(python3 -m skimindex.config)"
```

`python3 -m skimindex.config` also **validates** the configuration before
printing any variables — if validation fails, it exits with status 1 and
prints errors to stderr, which causes the `eval` to abort visibly.

### In development (outside the container)

The same script detects the project `.venv` and injects its `site-packages`
into `PYTHONPATH` automatically, so no manual activation is needed:

```bash
source scripts/__skimindex_config.sh
```

### In Python code

```python
from skimindex.config import config

cfg = config()
# Values are in os.environ after Config.__init__ calls _export_env().
# Use cfg.get() for typed access with the same precedence rules:
level = cfg.get("logging", "level")          # → "INFO"
taxa  = cfg.get("data.human", "taxon")       # → "human"
```
