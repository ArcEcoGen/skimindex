# skimindex Data Model — Sources, Datasets, and Roles

## Overview

Three concepts organise all data in skimindex:

| Concept | Config prefix | What it represents |
|---------|---------------|--------------------|
| **Source** | `[source.X]` | Where raw sequences come from (download origin) |
| **Dataset** | `[data.X]`   | A named collection of sequences with a specific purpose |
| **Role**   | `[role.X]`   | A category of use — groups datasets and drives processing |

Every dataset binds exactly one source and one role:

```
[source.ncbi] ──────────────────┐
                                 ▼
                          [data.human]  ──▶  [role.decontamination]
                                 ▲
[source.genbank] ───────────────┘  (e.g. [data.fungi])
```

The TOML syntax for all three is specified in
[Configuration File Format](config-format.md).

---

## Sources

A source represents an **origin** for raw sequence data. There are three:

### `ncbi`

Data downloaded via the NCBI Datasets CLI (`datasets download genome`).
Files are organised per genome assembly:

```
{source.ncbi.directory}/
  {data.directory}/
    {Species}--{accession}.gbff.gz     ← level-0 layout
    {Species}/
      {accession}.gbff.gz              ← level-1 layout
      {accession}/
        *.gbff.gz                      ← level-2 layout (multi-file assemblies)
```

The canonical filename convention uses `--` as the separator between species
and accession (see [Directory Structure](directory-structure.md)).

### `genbank`

Data downloaded as GenBank flat-file releases from the NCBI FTP site.
Files are **not** split per dataset — the entire release is shared:

```
{source.genbank.directory}/
  Release_{N}.0/
    fasta/
      bct/    ← bacterial sequences
      pln/    ← plant/fungi sequences
      …
    taxonomy/
      ncbi_taxonomy.tgz
```

A dataset with `source = "genbank"` filters sequences out of these flat-files
at pipeline time using `obigrep` with:
- a **division filter** (`divisions` key) — selects flat-files by GenBank division
- an optional **taxid filter** (`taxid` key) — keeps only sequences in a given taxon

### `internal`

In-house sequencing data. No download step — files must be placed manually
in the source directory. No additional convention is imposed.

---

## Datasets

A dataset (`[data.X]`) is a named collection of sequences that:
- comes from one **source** (where to find the raw files)
- serves one **role** (what the pipeline will do with them)

### Runtime representation — `Dataset`

At runtime, a dataset is represented by a `Dataset` object
(`skimindex.datasets.Dataset`). Its primary method is:

```python
ds.to_data() -> Iterator[Data]
```

`to_data()` yields one or more `Data` objects ready to enter a processing
pipeline. The exact number and kind depends on the source:

| Source    | Yields | One `Data` per |
|-----------|--------|----------------|
| `ncbi`    | `FILES` | genome assembly file (recursive scan of download dir) |
| `genbank` | `FILES` or `STREAM` | division (after optional taxid filtering) |
| `internal`| *not yet implemented* | — |

Each `Data` object carries a `subdir` — the relative path from the processed
data root up to (but not including) the processing output directory. This
encodes the full dataset/species/accession context so that the pipeline can
compute output paths without additional parameters.

Each `Data` object also carries a `per_species: bool` flag (default `True`).
When `False`, processing steps switch to **per-part** mode: k-mer counting and
index building operate on individual fragment files rather than the whole
`parts/` directory at once. This flag is set automatically by the dataset source:

| Source | `per_species` | Indexing mode |
|--------|--------------|---------------|
| `ncbi` | `True` | one sample per assembly (`parts/` dir) |
| `genbank` (`by_species = false`) | `False` | one sample per part file (`frg_N`) |

### Listing and filtering datasets

```python
from skimindex.datasets import datasets_for_role, get_dataset, all_datasets

# All datasets with a given role
for ds in datasets_for_role("decontamination"):
    print(ds.name, ds.source)

# A single named dataset
ds = get_dataset("human")
```

---

## Roles

A role (`[role.X]`) defines **how** a group of datasets is processed. It:
- provides an output `directory` name (the role subdirectory in processed data)
- declares the default processing pipeline to run (`run` key)

### Linking datasets to roles

Every dataset declares its role via the `role` key:

```toml
[data.human]
source = "ncbi"
role   = "decontamination"   # ← belongs to this role

[data.fungi]
source = "genbank"
role   = "decontamination"   # ← also belongs to this role
```

The role groups all datasets that share the same processing purpose.

### Linking roles to processing

A role declares which processing pipeline to run by default:

```toml
[role.decontamination]
directory = "decontamination"
run       = "prepare_decontam"   # default pipeline for all datasets in this role
```

Individual datasets can override this with their own `run` key (see
[Configuration File Format](config-format.md#data-sections)).

### Linking processing to roles

A processing section can also declare which role it operates on via its own
`role` key. This makes the section self-describing — the runner can discover
which datasets to process without any hardcoding:

```toml
[processing.prepare_decontam]
role      = "decontamination"   # operates on all datasets with this role
directory = "parts"
steps     = [...]
```

See [Processing Model](processing.md#named-input-parameters) for
details on how named input parameters and artifact references work in processing sections.

---

## Data flow summary

```
[source.X]          [data.Y]           [role.Z]         [processing.W]
   │                   │                   │                   │
   │ raw files         │ source + role     │ directory         │ role + input
   │                   │ → Dataset         │ run = "W"         │ directory
   ▼                   ▼                   ▼                   ▼
download/          Dataset.to_data()  processed_data/    pipeline execution
{data}/              → Data(FILES)     {role}/             → output in
{species}/           → Data(STREAM)     {data}/              {role}/{data}/
{accession}/                             {species}/            {species}/
                                          {accession}/          {accession}/
                                           {processing}/
```

The `subdir` carried by each `Data` object encodes the path segments between
the processed data root and the processing output directory, so that output
paths are always computed from the data itself, never passed as external
parameters.
