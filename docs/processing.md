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

Whether a step's output is saved to disk depends on how it is referenced:

| Context | `directory` present? | Output |
|---------|----------------------|--------|
| Top-level `[processing.X]` referenced by `run` | must be present | saved to `directory` |
| Named reference inside `steps` | yes | saved to its `directory` |
| Named reference inside `steps` | no | temporary |
| Inline table `{type=...}` inside `steps` | n/a | always temporary |

Temporary outputs are piped directly between steps where possible. When
intermediate files are unavoidable (e.g. between processes that cannot be
piped), they are written to a `tmp/` directory and deleted once the downstream
step completes.

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

## Validation rules

1. A `[processing.X]` section must have exactly one of `type` or `steps`.
2. A section with `steps` is composite; all elements must be strings or inline tables with `type`.
3. Inline tables inside `steps` must not have `steps` (inline steps are always atomic).
4. Any processing section referenced by a `run` key must have `directory`.
5. `type` values must match a registered `@processing` function in `skimindex.processing`.
