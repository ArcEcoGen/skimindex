# skimindex Docker image

This directory contains the `Dockerfile` and `Makefile` to build the `skimindex` Docker image.

## What's inside

The image is built in two stages:

1. **builder** (`golang`) — compiles and installs the [OBITools4](https://github.com/metabarcoding/obitools4) binaries.
2. **skimindex** (`continuumio/miniconda3`) — final image with [kmindex](https://github.com/tlemane/kmindex), [ntCard](https://github.com/bcgsc/ntCard), and [NCBI datasets CLI](https://www.ncbi.nlm.nih.gov/datasets/docs/v2/command-line-tools/) installed, plus the OBITools4 binaries copied from the builder stage.

The container runs as an unprivileged user (`skimindex`) and exposes three mount points:

| Path       | Purpose                        |
|------------|--------------------------------|
| `/genbank` | GenBank or reference databases |
| `/indexes` | kmindex index files            |
| `/skims`   | Input/output skim files        |

## Requirements

- Docker 20.10+ with **buildx** plugin (included in Docker Desktop; on Linux: `docker buildx install`)
- [skopeo](https://github.com/containers/skopeo) — required to push to the Zot OCI registry
- GNU Make

> **Note:** multi-platform builds require the `docker-container` buildx driver.
> `make build-multiplatform` automatically creates a dedicated builder (`skimindex-builder`)
> on first run. Use `make clean-builder` to remove it.

## Registry

The image is published to the [Metabarcoding Zot registry](https://registry.metabarcoding.org).
Because Zot is a strict OCI registry with public/private separation, `docker push` is not
supported. `make push` uses **skopeo** to copy a local OCI archive to the registry, preserving
the multi-platform manifest index.

Authenticate before pushing:

```bash
skopeo login registry.metabarcoding.org
```

## Usage

```bash
# Build for the native platform and load into the local Docker daemon (fast, for local testing)
make build

# Build for linux/amd64 and linux/arm64, export as a local OCI archive
make build-multiplatform

# Push the OCI archive to the registry (triggers build-multiplatform if archive is missing)
make push

# One-liner: build multiplatform and push
make build-multiplatform && make push

# Override platforms
make build-multiplatform PLATFORMS=linux/amd64,linux/arm64,linux/arm/v7

# Push under a specific tag
make build-multiplatform IMAGE_TAG=1.0.0
make push IMAGE_TAG=1.0.0

# Build with a pinned kmindex version
make build-multiplatform KMINDEX_VERSION=bioconda::kmindex=0.5.3

# Remove the local image and OCI archive
make clean

# Show available targets
make help
```

## Configurable variables

All variables can be overridden on the `make` command line.

| Variable           | Default                          | Description                                        |
|--------------------|----------------------------------|----------------------------------------------------|
| `IMAGE_NAME`       | `skimindex`                      | Image name                                         |
| `IMAGE_TAG`        | `latest`                         | Image tag                                          |
| `REGISTRY`         | `registry.metabarcoding.org`     | Target OCI registry (Zot)                          |
| `PLATFORMS`        | `linux/amd64,linux/arm64`        | Target platforms for `build-multiplatform`         |
| `OCI_ARCHIVE`      | `skimindex-latest.oci.tar`       | Local OCI archive produced by `build-multiplatform`|
| `BUILDER`          | `skimindex-builder`              | buildx builder name (docker-container driver)      |
| `GO_VERSION`       | `latest`                         | `golang` base image tag (builder stage)            |
| `MINICONDA_VERSION`| `latest`                         | `continuumio/miniconda3` tag (final stage)         |
| `OBITOOLS_BRANCH`  | `master`                         | OBITools4 branch or tag used for installation      |
| `KMINDEX_VERSION`  | `bioconda::kmindex`              | conda package spec for kmindex                     |
| `NTCARD_VERSION`   | `bioconda::ntcard`               | conda package spec for ntCard                      |
