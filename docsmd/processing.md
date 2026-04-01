# skimindex Processing Model

## Overview

Processing sections (`[processing.X]`) describe how raw or downloaded data are
transformed into pipeline outputs. Each section is either **atomic** (a single
operation) or **composite** (an ordered sequence of steps).

The `type` and `steps` keys are **mutually exclusive** — a processing section
must have exactly one of them.

---

## Artifact references — `dir@[idx:]role`

Both input and output locations are expressed as **artifact references**. An
artifact reference encodes the subdirectory name and the role tree in a single
string using the notation:

```
{dir}@{role}         →  processed_data/{role_dir}/{dataset_subdir}/{dir}/
{dir}@idx:{role}     →  indexes/{role_dir}/{dataset_subdir}/{dir}/
@idx:{role}          →  indexes/{role_dir}/   (meta-index, no subdir)
```

where `{role_dir}` is the `directory` value of `[role.{role}]`.

A dict form is also accepted wherever a string reference is valid:

```toml
sequence = {role = "decontamination", dir = "parts"}
output   = {role = "idx:decontamination", dir = ""}
```

The `{dataset_subdir}` component is supplied automatically at runtime from the
dataset being processed (e.g. `Human/Homo_sapiens--GCF_…`). The artifact
reference only names the role and subdirectory within that subtree.

---

## Atomic processing

An atomic section wraps a single registered operation. The `type` value maps
to a Python function decorated with `@processing_type` in the
`skimindex.processing` module.

| Key        | Type   | Required | Description                                                    |
|------------|--------|----------|----------------------------------------------------------------|
| `type`     | string | yes      | Registered processing function name                            |
| `output`   | string | yes*     | Artifact reference for the output. *Required to be runnable    |
| *(others)* | any    | no       | Operation-specific parameters passed to the function           |

Named input parameters (e.g. `sequence`, `counts`) are operation-specific — see
each type's documentation. If absent, the input defaults to the raw dataset
files.

```toml
[processing.count_kmers_decontam]
type      = "kmercount"
output    = "kmercount@decontamination"   # → processed_data/decontamination/…/kmercount/
sequence  = "parts@decontamination"       # reads fragments from parts/
kmer_size = 29
threads   = 10
```

---

## Composite processing

A composite section chains multiple steps in order. Each step is either a
**named reference** (string) or an **inline atomic** (TOML inline table).

| Key      | Type   | Required | Description                                                              |
|----------|--------|----------|--------------------------------------------------------------------------|
| `steps`  | array  | yes      | Ordered list of steps (strings or inline tables)                         |
| `output` | string | yes*     | Artifact reference for the composite output. *Required to be runnable    |

Each element of `steps` is one of:

| Form | Example | Parameters |
|------|---------|-----------|
| Named reference | `"split_decontam"` | Defined in its own `[processing.X]` section |
| Inline atomic   | `{type = "filter_n_only"}` | Always temporary, always atomic |

```toml
[processing.prepare_decontam]
output = "parts@decontamination"   # → processed_data/decontamination/…/parts/
steps = [
  {type = "split",         size = 200, overlap = 28},
  {type = "filter_n_only"},
  {type = "distribute",    batches = 20},
]
```

---

## Persistence

Whether a step's output is saved to disk depends on whether it declares an
`output` key. The **runner** (not the atomic bricks) enforces these rules.

### Who persists what

| Context | `output` present? | Result |
|---------|-------------------|--------|
| Top-level `[processing.X]` referenced by `run` | must be present | saved |
| Named reference inside `steps` | yes | saved to its `output` |
| Named reference inside `steps` | no | temporary (cleaned up after pipeline) |
| Inline table `{type=...}` inside `steps` | n/a | always temporary |

Only the **composite output directory** carries a stamp. Intermediate steps
saved to their own `output` are persisted but not stamped — they will not
trigger a short-circuit on re-run.

### How the runner persists each OutputKind

#### STREAM output with `output`, **non-terminal** step

The runner injects `tee` into the pipe so the byte stream is simultaneously
written to disk and forwarded to the next step:

```
input_cmd | tee(out_file) | next_step
```

The output file is `step_dir / output_filename` (declared by the type).

#### STREAM output with `output`, **terminal** step (last in composite)

The runner redirects stdout to the output file and executes the pipeline:

```python
(input_cmd > str(out_file))()
```

Execution happens here; the next Data object is `files_data([out_file])`.

#### DIRECTORY or FILE output with `output`

The runner passes the resolved `output` path as the output directory to the
atomic brick:

```python
fn(data, output_dir, dry_run=dry_run)
```

The brick creates the directory, writes its files, and returns a `Data` object.

#### Without `output` (temporary)

- **STREAM**: the step is chained without executing (no intermediate file).
- **DIRECTORY / FILE**: the runner creates a temporary directory via
  `tempfile.mkdtemp()`, passes it to the brick, and removes it in a
  `try/finally` block after the pipeline completes.

### Stamp management

```
needs_run(composite_output_dir, *sources)  →  skip if already stamped
remove_if_not_stamped(composite_output_dir)  →  clean partial results
… all steps execute …
stamp(composite_output_dir)  →  mark success
```

Stamp files live under the `[stamp]` directory configured in `skimindex.toml`.

---

## Linking processing to roles and data

A role or data section triggers a processing pipeline via the `run` key:

```toml
[role.decontamination]
directory = "decontamination"
run       = "prepare_decontam"   # references [processing.prepare_decontam]
```

A data section can override the role's `run`:

```toml
[data.fungi]
source = "genbank"
role   = "decontamination"
run    = "prepare_gb_decontam"   # overrides [role.decontamination].run
```

**Rule**: the processing section referenced by `run` must have an `output` key.

---

## Full example

```toml
# Composite pipeline: prepare decontamination reference sequences
[processing.prepare_decontam]
output = "parts@decontamination"   # → processed_data/decontamination/…/parts/
steps = [
  {type = "split",         size = 200, overlap = 28},
  {type = "filter_n_only"},
  {type = "distribute",    batches = 20},
]

# Atomic: count k-mers in prepared fragments
[processing.count_kmers_decontam]
type      = "kmercount"
output    = "kmercount@decontamination"
sequence  = "parts@decontamination"
kmer_size = 29
threads   = 10

# Atomic: build kmindex sub-index for one decontamination dataset
[processing.build_index_decontam]
type      = "buildindex"
output    = "kmindex@decontamination"  # → processed_data/decontamination/{dataset}/kmindex/  (FOF + stamp)
index     = "@idx:decontamination"     # → indexes/decontamination/  (kmindex meta-index, managed by kmindex)
kmer_size = 29
zvalue    = 3
fpr       = 1e-3
hard_min  = 1     # reference sequences are not sequencing data — every k-mer occurrence counts
threads   = 10

# Role referencing the preparation pipeline
[role.decontamination]
directory = "decontamination"
run       = "prepare_decontam"
```

The resulting chain (`build_index_decontam` is called once per dataset):

```
dataset.to_index_data()
    → prepare_decontam          → processed_data/decontamination/{dataset}/parts/
    → count_kmers_decontam      → processed_data/decontamination/{dataset}/kmercount/
    → build_index_decontam      → processed_data/decontamination/{dataset}/kmindex/  (FOF + stamp)
                                   indexes/decontamination/  (global meta-index, managed by kmindex)
```

---

## Decontamination index pipeline

The decontamination pipeline transforms downloaded reference sequences into a
kmindex meta-index used to filter contaminant k-mers from sequencing reads.
It runs **per dataset** — each `[data.X]` section with `role = "decontamination"`
produces one registered sub-index.

### Pipeline steps

```
dataset.to_index_data()
    → prepare_decontam          → processed_data/decontamination/{dataset}/parts/
    → count_kmers_decontam      → processed_data/decontamination/{dataset}/kmercount/
    → build_index_decontam      → processed_data/decontamination/{dataset}/kmindex/  (FOF + stamp)
                                   indexes/decontamination/  (global meta-index, managed by kmindex)
```

Each step is stamped independently. A dataset whose `parts/` directory is already
stamped will skip `prepare_decontam` on re-run.

### Bloom filter sizing

`buildindex` uses a **single-hash Bloom filter** model with the
[findere](https://github.com/lrobidou/findere) algorithm. kmindex indexes
s-mers and queries (s+z)-mers, so a positive hit requires **z+1** consecutive
k-mers to be present. The false positive probability is therefore:

```
fpr = (n / (n + m)) ^ (z+1)
```

| Symbol | Meaning |
|--------|---------|
| $n$    | Number of distinct k-mers inserted into the filter — line `F1` from ntcard histogram |
| $m$    | Number of cells in the Bloom filter (`bloom_size` passed to `kmindex build`) |
| $z$    | `--zvalue` parameter passed to kmindex (positive hit requires $z+1$ k-mers) |
| $p$    | Target false positive rate (`fpr` parameter) |

$$
P_{fpr} = \left(\frac{n}{n + m}\right)^{z+1}
$$

Inverting for $m$:

$$
m = \left\lceil n \cdot \left(p^{-1/(z+1)} - 1\right) \right\rceil
$$

When `bloom_size` is omitted from the config, it is computed automatically from
the ntcard histograms produced by `count_kmers_decontam`, using the **maximum F1**
across all samples (not the sum — since a presence/absence filter only needs to
represent the largest single sample).

**Example** — $n = 10^9$, $z = 3$, $p = 10^{-3}$:

$$
m = \left\lceil 10^9 \cdot \left(10^{-1/4} - 1\right) \right\rceil
  \approx \left\lceil 10^9 \cdot (5.62 - 1) \right\rceil
  \approx 4.62 \times 10^9 \text{ cells}
$$

### Global meta-index layout

All per-dataset sub-indexes are registered in the same global meta-index at
`indexes/decontamination/`. The `output` reference `"kmindex@decontamination"`
resolves to `processed_data/decontamination/{dataset}/kmindex/` (stamp target and
FOF location). The `index` parameter `"@idx:decontamination"` resolves to
`indexes/decontamination/`, the global meta-index managed by kmindex.

```
indexes/decontamination/
├── Human/       ← sub-index run dir (created by kmindex)
├── Fungi/
├── Bacteria/
└── Plants/
```

The root `indexes/decontamination/` is the global meta-index consumed by
`kmindex query` or `kmindex query2`.

### Per-part indexing for bulk sources

Datasets sourced from GenBank flat-files (`by_species = false`) are **bulk
sources**: all sequences of a division are processed together and distributed
into `N` batch files (`frg_0.fasta.gz`, …, `frg_{N-1}.fasta.gz`) by
`obidistribute`. For these datasets, indexing is done **per part**:

- `count_kmers_decontam` runs ntcard on **each part file individually**,
  producing one histogram per file (`frg_0_k29.hist`, …).
- `build_index_decontam` registers **one sample per part file** in the FOF.
- The Bloom filter is sized from the **maximum F1 across individual parts**
  (≈ total F1 / N), not the total F1 of the entire division.

This reduces the Bloom filter size by a factor of N compared to treating the
entire division as a single sample.

For NCBI datasets (`source = "ncbi"`), each genome assembly is already its own
`Data` item and its own `parts/` directory, so the standard per-directory
sampling applies unchanged.

The `per_species` property on `Dataset` (and on the `Data` objects it yields)
controls this behaviour automatically — no config parameter is needed.

To maximise kmindex memory efficiency, the number of samples in an index
should be a multiple of 8. Configure `batches` in `[processing.prepare_decontam]`
accordingly (e.g. `batches = 24`).

### FOF generation

Before calling `kmindex build`, `buildindex` generates a kmtricks
**file-of-files** (FOF). The strategy depends on the dataset source:

**Per-species sources** (`ncbi`): one sample per `parts/` directory, sample
name derived from the relative path joined by `--`.

**Bulk sources** (`genbank`, `by_species = false`): one sample per file inside
each `parts/` directory, sample name = file stem without suffixes.

- `register_as` = first component of the dataset's subdir path (e.g. `"Human"`, `"Plants"`).
- The FOF file is named `{register_as}.fof` and stored in `output_dir` (`processed_data/decontamination/{dataset}/kmindex/`).

FOF example for Plants (per-species, 62 assemblies):

```
Spermatophyta--GCF_000001735_4 : /path/parts/Spermatophyta/GCF_000001735.4/file1.fa.gz ; ...
Spermatophyta--GCF_000002775_5 : /path/parts/Spermatophyta/GCF_000002775.5/file1.fa.gz
...
```

FOF example for Bacteria (bulk, 20 parts):

```
frg_0 : /path/Bacteria/bct/parts/frg_0.fasta.gz
frg_1 : /path/Bacteria/bct/parts/frg_1.fasta.gz
...
frg_19 : /path/Bacteria/bct/parts/frg_19.fasta.gz
```

---

## Data model

Data flowing between processing steps is represented as a `Data` object.
The plumbum execution layer is an implementation detail — pipeline orchestration
only sees `Data`.

Three kinds, aligned with `OutputKind`:

| Kind | Description | Carries |
|------|-------------|---------|
| **STREAM** | A deferred pipeline not yet executed | a plumbum command/pipe |
| **FILES** | One or more files on disk | `list[Path]` |
| **DIRECTORY** | A directory of files | a single `Path` |

Every processing type has the uniform interface `Data → Data`.
The pipeline executor chains steps by passing the `Data` output of one step as
the `Data` input of the next.

Initial data (downloaded sources) is wrapped into `Data` before entering the
pipeline:

```python
files_data(Path("genome.gbff.gz"), format="gbff.gz")   # single genome file
files_data(list(dir.glob("*.fasta.gz")), format="fasta.gz")  # batch of files
directory_data(Path("/genbank/fasta/bct"))              # directory of FASTA files
stream_data(cmd, format="fasta")                        # pre-filtered stream
```

The `to_stream_command(data)` adapter is the **only** place where `Data` touches
plumbum — it converts any `Data` kind into a plumbum source command via
`obiconvert`. Atomic type implementations call it internally; pipeline
orchestration never sees plumbum objects.

---

## Output resolution

### Effective output directory

The effective output directory of a processing section is determined as follows:

- **Atomic** with `output`: resolved via `resolve_artifact(output, dataset_subdir)`.
- **Atomic** without `output`: no persistent output (temporary / piped).
- **Composite** with `output`: resolved via `resolve_artifact(output, dataset_subdir)`.
- **Composite** without `output`: the effective output directory of its **last step**
  (which itself must have one, otherwise the composite has no persistent output).

The output type (STREAM / DIRECTORY / FILE) of a composite is always the output type
of its **last step**, regardless of whether the composite has its own `output`.

### Output filename for STREAM and FILE types

When a STREAM or FILE output must be persisted to disk (because an `output` is
declared), the filename is determined by the processing **type implementation**, not
by the TOML config. Each registered processing type declares its `output_filename` in
code (e.g. `"filtered.fasta.gz"`), because the type knows its own output format.

A type with no declared `output_filename` cannot be persisted and must remain
temporary; declaring an `output` for such a type is a validation error.

### Runnability

A processing section is **runnable as a top-level step** only if it has an effective
output directory. Sections without a persistent output can only appear as intermediate
steps inside a composite.

---

## Named input parameters

Processing types that read from a previously produced artefact declare named
input parameters instead of a generic `input` key. Each type documents which
parameters it accepts.

The value of a named input parameter is always an **artifact reference**
(`dir@[idx:]role` or dict form). At runtime the runner resolves the reference
to an absolute path using the current `dataset_subdir`.

If a named input parameter is absent, the type falls back to the raw dataset
files supplied by the caller.

```toml
[processing.count_kmers_decontam]
type      = "kmercount"
output    = "kmercount@decontamination"
sequence  = "parts@decontamination"   # named input — reads from parts/
kmer_size = 29
```

Named inputs decouple processing sections from each other: `count_kmers_decontam`
does not reference `prepare_decontam` by name — it only declares which artefact
directory it needs. Renaming `prepare_decontam` has no effect as long as its
`output` remains `"parts@decontamination"`.

---

## Validation rules

1. A `[processing.X]` section must have exactly one of `type` or `steps`.
2. A section with `steps` is composite; all elements must be strings or inline tables with `type`.
3. Inline tables inside `steps` must not have `steps` (inline steps are always atomic).
4. Any processing section referenced by a `run` key must have a runnable effective output (`output`).
5. `type` values must match a registered `@processing_type` function in `skimindex.processing`.
6. A STREAM/FILE atomic with `output` must have a declared `output_filename` in its type.
7. Composite sections (`steps`) are **not** registered in the `@processing_type` registry.
   They are structural constructs executed by the pipeline runner, not named operations.
8. Artifact references must follow the `dir@[idx:]role` format or be a dict with `role` and `dir`.
9. The `role` part of an artifact reference must match a `[role.X]` section in the config.
