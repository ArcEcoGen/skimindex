# API Reference

Python API for the `skimindex` package. All public modules are documented below.

| Module | Description |
|--------|-------------|
| [`config`](config.md) | TOML configuration loading, path resolution, singleton access |
| [`config.validate`](config_validate.md) | Config validation — structural checks and cross-section dependencies |
| [`datasets`](datasets.md) | Dataset abstraction — resolves config datasets to `Data` objects |
| [`sources`](sources.md) | Source and artifact path helpers, `resolve_artifact()` |
| [`processing`](processing.md) | Processing type registry, pipeline builder, `Data` abstraction |
| [`stamp`](stamp.md) | Stamp file management — tracks completed pipeline steps |
| [`sequences`](sequences.md) | Sequence file discovery utilities |
| [`naming`](naming.md) | Canonical species/taxon name helpers, genome path parsing |
| [`log`](log.md) | Logging — levels, colors, file output |
| [`unix`](unix.md) | Unix CLI tool wrappers (plumbum-based): pigz, ntCard, datasets, OBITools4, SRA Toolkit |
