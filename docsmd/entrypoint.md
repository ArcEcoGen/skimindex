# skimindex Entry Point

`skimindex.sh` is the single user-facing entry point for the pipeline.
It handles container runtime detection, bind-mounting project directories,
image lifecycle, and subcommand dispatch.

---

## Usage

```
skimindex [--project-dir DIR] [--local] <subcommand> [subcommand-options]
skimindex --help
```

---

## Global Options

| Option | Description |
|--------|-------------|
| `--project-dir DIR` | Project root directory. Defaults to the current working directory. All relative paths in `config/skimindex.toml` are resolved from this directory. |
| `--local` | Use the locally cached image without checking the registry for updates. |
| `-h`, `--help` | Show help and exit. |

Global options must appear **before** the subcommand. Options after the
subcommand name are passed through to the subcommand unchanged.

---

## Built-in Subcommands

### `init`

Initialise a new project directory:

1. Creates `config/` and downloads a default `skimindex.toml` from the
   source repository if none is present.
2. Creates all host-side directories declared in `[local_directories]`
   (including `usercmd/`, `log/`, `stamp/`, etc.).

```bash
skimindex --project-dir /path/to/project init
```

The project directory is created if it does not exist. If `config/skimindex.toml`
already exists it is left untouched. The directory creation step is always
performed, so `init` is safe to re-run.

### `update`

Pull the latest container image from the registry (or rebuild the SIF for
Apptainer). An automatic update check is performed at every
run unless `--local` is set.

```bash
skimindex update
```

### `shell`

Start an interactive shell inside the container with all project directories
bind-mounted. Useful for debugging and manual inspection.

```bash
skimindex shell [--mount SRC:DST] …
```

| Option | Description |
|--------|-------------|
| `--mount SRC:DST` | Add an extra bind-mount on top of the config-driven ones. May be repeated. |

### Pipeline subcommands

All other subcommands are dispatched to scripts inside the container image
(in `/app/scripts/`). Run `skimindex --help` to see the full list available
in your installed version. See [Pipeline Commands](commands.md) for the full
reference.

### User subcommands (`usercmd/`)

Scripts placed in the project's `usercmd/` directory are available as
additional subcommands without rebuilding the image.
See [Writing Shell Commands](devshell.md) for details.

---

## Container Runtime

The runtime is auto-detected in priority order:

```
apptainer  →  docker  →  podman
```

| Runtime | Image location |
|---------|---------------|
| Apptainer | `<project-dir>/images/<name>-<tag>.sif` (local file) |
| Docker / Podman | Registry: pulled on first use, then cached locally |

For Docker and Podman, `--pull always` is the default — the registry is
checked for a newer image at every run. Use `--local` to skip this check.

For Apptainer, the SIF digest is compared against the registry at startup.
If the registry is unreachable (offline), the local SIF is used as-is.

---

## Bind-Mounts

All directories declared in `[local_directories]` in `config/skimindex.toml`
are automatically bind-mounted into the container.

Each key `<k>` maps its host path to `/<k>` inside the container:

```toml
[local_directories]
genbank        = "genbank"          # host: <project-dir>/genbank/  →  /genbank
processed_data = "processed_data"   # host: <project-dir>/processed_data/  →  /processed_data
usercmd        = "usercmd"          # host: <project-dir>/usercmd/  →  /usercmd
…
```

Extra mounts can be added when using the `shell` subcommand via `--mount SRC:DST` (not available for pipeline subcommands).

---

## Configuration

The pipeline configuration file is read from:

```
<project-dir>/config/skimindex.toml
```

See [Configuration File Format](config-format.md) for the full specification.
