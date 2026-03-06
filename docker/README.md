# skimindex container image

This directory contains the `Dockerfile` and `Makefile` to build and run the `skimindex` image.
The Makefile supports **Apptainer**, **Docker**, and **Podman** transparently — the runtime is
auto-detected at invocation time (Apptainer takes priority on HPC clusters).

## What's inside

The image is built in two stages:

1. **builder** (`golang`) — compiles and installs the
   [OBITools4](https://github.com/metabarcoding/obitools4) binaries, and builds the C tools
   located in `src/` (one sub-directory per tool, each with its own `Makefile`).

2. **skimindex** (`continuumio/miniconda3`) — final image containing:
   - [kmindex](https://github.com/tlemane/kmindex) and [ntCard](https://github.com/bcgsc/ntCard)
     installed via conda (bioconda channel)
   - [NCBI datasets CLI](https://www.ncbi.nlm.nih.gov/datasets/docs/v2/command-line-tools/)
     (`datasets` + `dataformat`), downloaded for the target architecture
   - OBITools4 binaries copied from the builder stage (`/usr/local/bin/obi*`)
   - C tools from `src/` copied to `/app/bin/`
   - Pipeline scripts copied to `/app/scripts/` and `/app/obiluascripts/`
   - System packages: `curl`, `make`, `unzip`, `less`, `jq`, `pigz`

The container runs as an unprivileged user (`skimindex`).
`/app/bin` and `/app/scripts` are prepended to `PATH`.

### Mount points

| Path              | Purpose                                              |
|-------------------|------------------------------------------------------|
| `/genbank`        | Raw GenBank / reference sequence files               |
| `/indexes`        | kmindex index files                                  |
| `/skims`          | Input/output skim files                              |
| `/processed_data` | Post-processed and final result files                |
| `/config`         | The configuration directory for the pipeline         |

## Requirements

### Docker / Podman workflow (build & push)

- Docker 20.10+ with the **buildx** plugin (included in Docker Desktop;
  on Linux: `docker buildx install`)
- [skopeo](https://github.com/containers/skopeo) — required to push to the Zot OCI registry
- GNU Make

> **Note:** multi-platform builds require the `docker-container` buildx driver.
> `make build-multiplatform` automatically creates a dedicated builder (`skimindex-builder`)
> on first run. Use `make clean-builder` to remove it.

### Apptainer workflow (HPC)

- [Apptainer](https://apptainer.org/) 1.0+
- A local SIF file produced by `make pull-sif` (requires network access to the registry)
- GNU Make

## Registry

The image is published to `registry.metabarcoding.org/arcecogen`.
Because this Zot registry uses OCI layout with strict multi-platform support, `docker push` is
not supported — `make push` uses **skopeo** to copy a local OCI archive to the registry,
preserving the multi-platform manifest index.

Authenticate before pushing:

```bash
skopeo login registry.metabarcoding.org
```

## Image management

### Building the image

Build for the native platform only and load the result directly into the local Docker daemon.
Suitable for local testing; does not produce a multi-platform archive.

```bash
make build
```

Build for `linux/amd64` and `linux/arm64` simultaneously and export the result as a local OCI
archive (`skimindex-latest.oci.tar`). Requires the `docker-container` buildx driver (created
automatically on first run). Use this before pushing to the registry.

```bash
make build-multiplatform
make build-multiplatform PLATFORMS=linux/amd64,linux/arm64,linux/arm/v7
make build-multiplatform IMAGE_TAG=1.0.0
make build-multiplatform KMINDEX_VERSION=bioconda::kmindex=0.5.3
```

Remove the local image, OCI archive, generated Dockerfile, and buildx builder:

```bash
make clean
make help    # list all available targets
```

#### Build variables

All variables can be overridden on the `make` command line.

| Variable           | Default                                    | Description                                         |
|--------------------|--------------------------------------------|-----------------------------------------------------|
| `IMAGE_NAME`       | `skimindex`                                | Image name                                          |
| `IMAGE_TAG`        | `latest`                                   | Image tag                                           |
| `REGISTRY`         | `registry.metabarcoding.org/arcecogen`     | Target OCI registry (Zot)                           |
| `PLATFORMS`        | `linux/amd64,linux/arm64`                  | Target platforms for `build-multiplatform`          |
| `OCI_ARCHIVE`      | `skimindex-latest.oci.tar`                 | Local OCI archive produced by `build-multiplatform` |
| `BUILDER`          | `skimindex-builder`                        | buildx builder name (docker-container driver)       |
| `GO_VERSION`       | `latest`                                   | `golang` base image tag (builder stage)             |
| `MINICONDA_VERSION`| `latest`                                   | `continuumio/miniconda3` tag (final stage)          |
| `OBITOOLS_VERSION` | `latest`                                   | OBITools4 version (`latest` or e.g. `4.4.8`)        |
| `KMINDEX_VERSION`  | `bioconda::kmindex`                        | conda package spec for kmindex                      |
| `NTCARD_VERSION`   | `bioconda::ntcard`                         | conda package spec for ntCard                       |

### Pushing the image to the registry

`make push` uses **skopeo** to copy the local OCI archive to the registry, preserving the
multi-platform manifest. Authenticate first:

```bash
skopeo login registry.metabarcoding.org
```

Push (triggers `build-multiplatform` automatically if the archive is missing):

```bash
make push
make push IMAGE_TAG=1.0.0
```

### Obtaining the image on an HPC cluster (Apptainer)

On HPC systems Docker is typically unavailable. Pull the image from the registry and convert it
to a local SIF file stored in `images/`. This step requires network access and is done once per
release.

```bash
make pull-sif
make pull-sif IMAGE_TAG=1.0.0
```

#### Apptainer variables

| Variable             | Default                                  | Description                                            |
|----------------------|------------------------------------------|--------------------------------------------------------|
| `IMAGES_DIR`         | `<project_root>/images`                  | Directory holding the SIF file                         |
| `APPTAINER_CACHEDIR` | `<project_root>/images/.apptainer/cache` | Apptainer layer cache (overrides `~/.apptainer/cache`) |
| `APPTAINER_TMPDIR`   | `<project_root>/images/.apptainer/tmp`   | Apptainer build temp directory                         |

## Using the pipeline

The Makefile auto-detects the available container runtime in priority order:
**Apptainer** > **Docker** > **Podman**. The runtime can be forced if needed:

```bash
make run RUNTIME=podman
```

### Interactive shell

Start an interactive shell inside the container with the four data directories bind-mounted.
This is the entry point for manual exploration or ad-hoc commands.

```bash
make run
make run GENBANK_DIR=/data/genbank
```

Development mode additionally mounts the project source tree at `/workspace` and enables a
writable tmpfs overlay, allowing live editing of scripts without rebuilding the image.

```bash
make run-dev
```

### Downloading reference data

Reference downloads run non-interactively inside the container. Host directories are created
automatically if absent. Each script is resume-friendly: an interrupted download can be
restarted by re-running the same target.

Download all references in one shot (GenBank divisions + human genome + plant assemblies):

```bash
make download_references
```

Download each dataset individually:

```bash
make download_genbank    # GenBank divisions defined in genbank/Makefile (GBDIV)
make download_human      # Human reference genome (GRCh38 / GCF_000001405.*)
make download_plants     # All complete Spermatophyta assemblies from RefSeq + GenBank
```

#### Runtime variables

| Variable        | Default                         | Description                                              |
|-----------------|---------------------------------|----------------------------------------------------------|
| `RUNTIME`       | auto-detected                   | Container runtime: `apptainer`, `docker`, or `podman`    |
| `GENBANK_DIR`   | `<project_root>/genbank`        | Host directory mounted as `/genbank`                     |
| `INDEXES_DIR`   | `<project_root>/indexes`        | Host directory mounted as `/indexes`                     |
| `SKIMS_DIR`     | `<project_root>/skims`          | Host directory mounted as `/skims`                       |
| `PROCESSED_DIR` | `<project_root>/processed_data` | Host directory mounted as `/processed_data`              |
