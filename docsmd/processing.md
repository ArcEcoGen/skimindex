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

# Atomic: build kmindex meta-index from k-mer counts
[processing.build_decontam_index]
type      = "build_index"
output    = "@idx:decontamination"        # → indexes/decontamination/
sequence  = "parts@decontamination"
counts    = "kmercount@decontamination"
kmer_size = 29

# Role referencing the preparation pipeline
[role.decontamination]
directory = "decontamination"
run       = "prepare_decontam"
```

The resulting chain:

```
dataset.to_data()
    → prepare_decontam          → processed_data/decontamination/…/parts/
    → count_kmers_decontam      → processed_data/decontamination/…/kmercount/
    → build_decontam_index      → indexes/decontamination/
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
