# skimindex Documentation

skimindex is a pipeline for building k-mer decontamination indices from public
and internal sequence databases. It runs inside a container and is configured
via a single TOML file.

## Contents

- [Directory Structure](directory-structure.md) — layout of runtime data directories
  (raw data, processed outputs, indexes, stamps) and development directories
  (source code, Docker build, scripts)

- [Configuration File Format](config-format.md) — specification of
  `config/skimindex.toml`: configuration sections, source sections, role
  sections, processing sections, and data sections

## Quick Start

1. Copy `config/skimindex.toml` and edit it for your datasets.
2. Adjust host paths in `[local_directories]` to match your storage layout.
3. Add one data section per dataset, with `source` and `role` keys.
4. Run `skimindex.sh` to launch the pipeline inside the container.

## Pipeline Flow

```
Raw data                 Processed data              Indexes
────────────────         ──────────────────          ──────────
[source]/                [processed_data]/           [indexes]/
  {data}/                  {role}/                     {role}/
    {species}/               {data}/                     …
      {accession}/             {species}/
        *.gbff.gz                {accession}/
                                   {processing}/
                                     *.fasta.gz
```

Sources: `ncbi`, `genbank`, `internal`
Roles: `decontamination`, `genomes`, `genome_skims`
Processing steps: `split`, `kmercount`
