# skimindex Processing Model

## Overview

Processing sections (`[processing.X]`) describe how raw or downloaded data are
transformed into pipeline outputs. Each section is either **atomic** (a single
operation) or **composite** (an ordered sequence of steps).

The `type` and `steps` keys are **mutually exclusive** — a processing section
must have exactly one of them.

---

## Atomic processing

An atomic section wraps a single registered operation. The `type` value maps
to a Python function decorated with `@processing` in the `skimindex.processing`
module — the set of valid types is therefore determined by the implementation.

| Key         | Type    | Required | Description                                                  |
|-------------|---------|----------|--------------------------------------------------------------|
| `type`      | string  | yes      | Registered processing function name                          |
| `directory` | string  | no       | Output subdirectory. If absent, output is temporary (see [Persistence](#persistence)) |
| *(others)*  | any     | no       | Operation-specific parameters passed to the function         |

```toml
[processing.split_decontam]
type      = "split"
directory = "split"     # results saved to this subdirectory
size      = 200         # fragment size in bp
overlap   = 28          # overlap = kmer_size - 1

[processing.remove_n]
type = "remove_n_only"  # no directory → temporary

[processing.distribute_batches]
type    = "distribute"
batches = 20            # no directory → temporary
```

---

## Composite processing

A composite section chains multiple steps in order. Each step is either a
**named reference** (string) or an **inline atomic** (TOML inline table).

| Key         | Type            | Required | Description                                                          |
|-------------|-----------------|----------|----------------------------------------------------------------------|
| `steps`     | array           | yes      | Ordered list of steps (strings or inline tables)                     |
| `directory` | string          | yes*     | Output subdirectory. *Required when this section is referenced by `run` |

Each element of `steps` is one of:

| Form | Example | Parameters |
|------|---------|-----------|
| Named reference | `"split_decontam"` | Defined in its own `[processing.X]` section |
| Inline atomic   | `{type = "remove_n_only"}` | Always temporary, always atomic |

```toml
[processing.prepare_decontam]
directory = "prepared"                        # required: this section is run by a role
steps = [
  "split_decontam",                           # named reference — saved if it has directory
  {type = "remove_n_only"},                   # inline — always temporary
  {type = "distribute", batches = 20},        # inline — always temporary
]
```

---

## Persistence

Whether a step's output is saved to disk depends on whether it declares a
`directory` key. The **runner** (not the atomic bricks) enforces these rules.

### Who persists what

| Context | `directory` present? | Result |
|---------|----------------------|--------|
| Top-level `[processing.X]` referenced by `run` | must be present | saved |
| Named reference inside `steps` | yes | saved to its `directory` |
| Named reference inside `steps` | no | temporary (cleaned up after pipeline) |
| Inline table `{type=...}` inside `steps` | n/a | always temporary |

Only the **composite output directory** carries a stamp. Intermediate steps
saved to their own `directory` are persisted but not stamped — they will not
trigger a short-circuit on re-run.

### How the runner persists each OutputKind

#### STREAM output with `directory`, **non-terminal** step

The runner injects `tee` into the pipe so the byte stream is simultaneously
written to disk and forwarded to the next step:

```
input_cmd | tee(out_file) | next_step
```

The output file is `step_dir / output_filename` (declared by the type).

#### STREAM output with `directory`, **terminal** step (last in composite)

The runner redirects stdout to the output file and executes the pipeline:

```python
(input_cmd > str(out_file))()
```

Execution happens here; the next Data object is `files_data([out_file])`.

#### DIRECTORY or FILE output with `directory`

The runner passes `step_dir` as the output directory to the atomic brick:

```python
fn(data, step_dir, dry_run=dry_run)
```

The brick creates the directory, writes its files, and returns a `Data` object.

#### Without `directory` (temporary)

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

**Rule**: the processing section referenced by `run` must have a `directory` key.

---

## Full example

```toml
# Atomic steps
[processing.split_decontam]
type      = "split"
directory = "split"
size      = 200
overlap   = 28

[processing.count_kmers]
type      = "kmercount"
directory = "kmercount"
kmer_size = 29

# Composite pipeline — run by [role.decontamination]
[processing.prepare_decontam]
directory = "prepared"
steps = [
  "split_decontam",                     # saved to split/
  {type = "remove_n_only"},             # temporary
  "count_kmers",                        # saved to kmercount/
]

# Role referencing the pipeline
[role.decontamination]
directory = "decontamination"
run       = "prepare_decontam"
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

- **Atomic** with `directory`: its own `directory`.
- **Atomic** without `directory`: no persistent output (temporary / piped).
- **Composite** with `directory`: its own `directory` (ignores last step's directory).
- **Composite** without `directory`: the effective output directory of its **last step**
  (which itself must have one, otherwise the composite has no persistent output).

The output type (STREAM / DIRECTORY / FILE) of a composite is always the output type
of its **last step**, regardless of whether the composite has its own `directory`.

### Output filename for STREAM and FILE types

When a STREAM or FILE output must be persisted to disk (because a `directory` is
declared), the filename is determined by the processing **type implementation**, not
by the TOML config. Each registered processing type declares its `output_filename` in
code (e.g. `"filtered.fasta.gz"`), because the type knows its own output format.

A type with no declared `output_filename` cannot be persisted and must remain
temporary; declaring a `directory` for such a type is a validation error.

### Runnability

A processing section is **runnable as a top-level step** only if it has an effective
output directory. Sections without a persistent output can only appear as intermediate
steps inside a composite.

---

## Dataset binding and input chaining

### `role` — which datasets a processing operates on

A processing section can declare the role of datasets it operates on via the
optional `role` key. When a pipeline is executed without an explicit dataset
list, the runner uses `role` to discover the relevant datasets automatically.

```toml
[processing.prepare_decontam]
role      = "decontamination"  # operates on all datasets with role="decontamination"
directory = "parts"
steps = [...]
```

This makes the processing section self-describing: it knows its own dataset
scope without any hardcoding in the calling code.

### `input` — where input data comes from

A processing section can declare where its input data comes from via the
optional `input` key:

| `input` present? | Source of input data |
|------------------|----------------------|
| absent | raw dataset files (`dataset.to_data()`) |
| `input = "X"` | output directory of `[processing.X]` for the same dataset |

```toml
[processing.prepare_decontam]
role      = "decontamination"
directory = "parts"
steps = [
  {type = "split",         size = 200, overlap = 28},
  {type = "filter_n_only"},
  {type = "distribute",    batches = 20},
]
# no input → reads raw downloaded files

[processing.count_kmers_decontam]
type      = "kmercount"
input     = "prepare_decontam"   # reads from parts/ produced by prepare_decontam
directory = "kmercount"
kmer_size = 29
```

These two sections implicitly define a chain:

```
dataset.to_data()
    → prepare_decontam   (role="decontamination") → parts/
    → count_kmers_decontam                        → kmercount/
```

Each section can be run independently: `decontam prepare` starts from raw files,
`decontam count` starts from `parts/` without re-running `prepare_decontam`.

### Input resolution rules

The rule is recursive and uniform:

**Standalone execution** (referenced by `run` or called directly):
- no `input` → `dataset.to_data()` (raw source files)
- `input = "X"` → `directory_data(output_dir_of_X / for_this_dataset)`

**As a step inside a composite**:
- the step's own `input` key is **silently ignored**
- first step → receives the composite's resolved input (same rules as standalone)
- subsequent steps → receive the output of the previous step

The composite resolves its own `input` first, then propagates the result through
its steps in order. A step's `input` is only meaningful when that section is
executed as a top-level pipeline.

---

## Validation rules

1. A `[processing.X]` section must have exactly one of `type` or `steps`.
2. A section with `steps` is composite; all elements must be strings or inline tables with `type`.
3. Inline tables inside `steps` must not have `steps` (inline steps are always atomic).
4. Any processing section referenced by a `run` key must have a runnable effective output directory.
5. `type` values must match a registered `@processing_type` function in `skimindex.processing`.
6. A STREAM/FILE atomic with `directory` must have a declared `output_filename` in its type.
7. Composite sections (`steps`) are **not** registered in the `@processing_type` registry.
   They are structural constructs executed by the pipeline runner, not named operations.
8. If `input` is present, it must reference an existing `[processing.X]` section that has a `directory`.
9. If `role` is present, it must be a valid role name declared in a `[role.X]` section.
