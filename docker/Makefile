# =============================================================================
# Image identity
# =============================================================================

# IMAGE_NAME : Base name of the container image (used in tags, SIF filename,
#              OCI archive name, and buildx builder name).
IMAGE_NAME  := skimindex

# IMAGE_TAG  : Tag applied to the image. Use a version string (e.g. v1.2.3)
#              or "latest" for the rolling release.
IMAGE_TAG   := latest

# =============================================================================
# Registry
# =============================================================================

# REGISTRY   : Target OCI registry. Images are pushed via skopeo (not docker
#              push) because the registry is Zot-based and expects OCI layout.
#              Format: <host>/<namespace>
REGISTRY    := registry.metabarcoding.org/arcecogen

# =============================================================================
# Build platforms
# =============================================================================

# PLATFORMS  : Comma-separated list of target platforms for multi-platform
#              builds (docker buildx). Both amd64 (x86_64 servers) and arm64
#              (Apple Silicon, ARM HPC nodes) are produced by default.
PLATFORMS   := linux/amd64,linux/arm64

# =============================================================================
# Base image versions
# =============================================================================
# These values are substituted directly into the Dockerfile FROM lines by the
# $(DOCKERFILE_GEN) rule (sed replacement of @@…@@ placeholders).
# They are NOT passed as --build-arg because multi-stage FROM lines cannot
# reference global ARGs in all BuildKit versions.

# GO_VERSION        : Version tag for the Go base image (golang:<tag>).
#                     Use "latest" or a specific version such as "1.22".
GO_VERSION        := latest

# MINICONDA_VERSION : Version tag for the Miniconda base image.
#                     Use "latest" or a specific tag from the continuumio repo.
MINICONDA_VERSION := latest

# =============================================================================
# Tool versions installed inside the image
# =============================================================================
# Tracked here for auditability and future version pinning.
# Passed to docker build as --build-arg so they appear in the image metadata.

# OBITOOLS_BRANCH : Git branch (or tag) of OBITools to build from source.
OBITOOLS_BRANCH   := master

# KMINDEX_VERSION : Conda package specifier for kmindex (channel::package).
KMINDEX_VERSION   := bioconda::kmindex

# NTCARD_VERSION  : Conda package specifier for ntCard (channel::package).
NTCARD_VERSION    := bioconda::ntcard

# =============================================================================
# Derived image identifiers
# =============================================================================

# FULL_IMAGE  : Fully-qualified image reference used for push/pull and as the
#               docker/podman IMAGE_REF.  Format: <registry>/<name>:<tag>
FULL_IMAGE  := $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)

# OCI_ARCHIVE : Local OCI tar archive produced by `make build-multiplatform`.
#               Consumed by `make push` (skopeo oci-archive: source).
OCI_ARCHIVE := $(IMAGE_NAME)-$(IMAGE_TAG).oci.tar

# =============================================================================
# Docker buildx builder
# =============================================================================

# BUILDER    : Name of the buildx builder instance. The docker-container
#              driver is required for multi-platform builds and OCI export.
#              Created automatically by the .builder-ready target.
BUILDER := skimindex-builder

# =============================================================================
# OCI image annotations (injected via --build-arg)
# =============================================================================

# OCI_VERSION  : Human-readable version label embedded in the image.
OCI_VERSION  := $(IMAGE_TAG)

# OCI_CREATED  : ISO-8601 build timestamp (UTC), embedded as org.opencontainers
#                .image.created annotation.
OCI_CREATED  := $(shell date -u +%Y-%m-%dT%H:%M:%SZ)

# OCI_REVISION : Short Git SHA of the source commit, embedded as
#                org.opencontainers.image.revision annotation.
#                Falls back to "unknown" outside a git repository.
OCI_REVISION := $(shell git -C .. rev-parse --short HEAD 2>/dev/null || echo unknown)

# =============================================================================
# Build context and Dockerfile
# =============================================================================

# BUILD_CONTEXT  : Docker build context directory. Set to the project root
#                  (parent of docker/) so that `COPY ../genbank/` instructions
#                  in the Dockerfile can reach files outside docker/.
BUILD_CONTEXT := ..

# DOCKERFILE_TPL : Source Dockerfile template containing @@…@@ placeholders
#                  for base image versions.
DOCKERFILE_TPL := Dockerfile

# DOCKERFILE_GEN : Generated Dockerfile with placeholders replaced by actual
#                  version strings. Created by the $(DOCKERFILE_GEN) rule.
#                  Prefixed with a dot so it is hidden / gitignored by default.
DOCKERFILE_GEN := .Dockerfile.generated

# BUILD_ARGS     : --build-arg flags forwarded to `docker build` / `docker
#                  buildx build`. Carries tool versions and OCI annotations.
#                  Base image versions are NOT included here (see above).
BUILD_ARGS := \
	--build-arg OBITOOLS_BRANCH=$(OBITOOLS_BRANCH) \
	--build-arg KMINDEX_VERSION=$(KMINDEX_VERSION) \
	--build-arg NTCARD_VERSION=$(NTCARD_VERSION) \
	--build-arg OCI_VERSION=$(OCI_VERSION) \
	--build-arg OCI_CREATED=$(OCI_CREATED) \
	--build-arg OCI_REVISION=$(OCI_REVISION)

# =============================================================================
# Host filesystem layout
# =============================================================================

# PROJECT_ROOT  : Absolute path to the project root, computed from
#                 BUILD_CONTEXT so it is stable regardless of the directory
#                 from which make is invoked.
PROJECT_ROOT := $(abspath $(BUILD_CONTEXT))

# The following four directories are bind-mounted into every container run.
# They can be overridden on the command line, e.g.:
#   make run GENBANK_DIR=/data/genbank
#
# GENBANK_DIR   : Holds raw GenBank sequence files downloaded by the
#                 download_* targets.  Mounted as /genbank inside the container.
GENBANK_DIR       := $(PROJECT_ROOT)/genbank

# INDEXES_DIR   : Holds kmindex index files built from the sequences.
#                 Mounted as /indexes inside the container.
INDEXES_DIR       := $(PROJECT_ROOT)/indexes

# SKIMS_DIR     : Holds skim output files produced by the pipeline.
#                 Mounted as /skims inside the container.
SKIMS_DIR         := $(PROJECT_ROOT)/skims

# PROCESSED_DIR : Holds post-processed / final result files.
#                 Mounted as /processed_data inside the container.
PROCESSED_DIR     := $(PROJECT_ROOT)/processed_data

# HOST_DIRS     : Aggregated list of all host directories that must exist
#                 before starting any container.  Created by `make ensure-dirs`.
HOST_DIRS := $(GENBANK_DIR) $(INDEXES_DIR) $(SKIMS_DIR) $(PROCESSED_DIR)

# =============================================================================
# Apptainer image and cache
# =============================================================================

# IMAGES_DIR         : Directory where the SIF file is stored.  Kept inside
#                      the project to avoid scattering large files across the
#                      filesystem.
IMAGES_DIR := $(PROJECT_ROOT)/images

# SIF_FILE           : Path of the Apptainer SIF image produced by `make
#                      pull-sif`.  Named after the image and tag for clarity.
SIF_FILE   := $(IMAGES_DIR)/$(IMAGE_NAME)-$(IMAGE_TAG).sif

# APPTAINER_CACHEDIR : Apptainer layer cache directory.  Kept inside images/
#                      (instead of the default ~/.apptainer/cache) to avoid
#                      filling the user home directory on HPC systems.
#                      Can be overridden: make pull-sif APPTAINER_CACHEDIR=/tmp/cache
APPTAINER_CACHEDIR ?= $(IMAGES_DIR)/.apptainer/cache

# APPTAINER_TMPDIR   : Apptainer temporary directory used during SIF
#                      construction.  Same rationale as APPTAINER_CACHEDIR.
APPTAINER_TMPDIR   ?= $(IMAGES_DIR)/.apptainer/tmp

# =============================================================================
# Runtime detection
# =============================================================================

# RUNTIME    : Auto-detected container runtime, in priority order:
#                apptainer  — preferred on HPC clusters (rootless, SIF-based)
#                docker     — standard workstation runtime
#                podman     — rootless Docker-compatible alternative
#                none       — no runtime found; targets that need one will fail
#              Override on the command line if auto-detection is wrong:
#                make run RUNTIME=podman
RUNTIME := $(shell \
	if command -v apptainer >/dev/null 2>&1; then echo apptainer; \
	elif command -v docker  >/dev/null 2>&1; then echo docker;    \
	elif command -v podman  >/dev/null 2>&1; then echo podman;    \
	else echo none; fi)

# =============================================================================
# Image reference (runtime-dependent)
# =============================================================================

# IMAGE_REF  : The image identifier passed to the runtime command.
#                apptainer  → path to the local SIF file ($(SIF_FILE))
#                             The SIF must exist; run `make pull-sif` first.
#                docker/podman → fully-qualified registry image name
#                             ($(FULL_IMAGE)); pulled automatically if absent.
ifeq ($(RUNTIME),apptainer)
  IMAGE_REF := $(SIF_FILE)
else
  IMAGE_REF := $(FULL_IMAGE)
endif

# =============================================================================
# Bind-mount flags (runtime-dependent)
# =============================================================================
# Apptainer uses --bind src:dst; docker/podman use -v src:dst.
# Two mount sets are defined:
#
# BIND      : Production mounts — only the four data directories.
#             Used by RUN_CMD and EXEC_CMD.
#
# BIND_DEV  : Development mounts — production mounts plus source tree
#             directories (scripts, bin, obiluascripts) and the full project
#             root at /workspace.  Used by RUN_DEV_CMD for live editing.

ifeq ($(RUNTIME),apptainer)
  BIND = --bind $(GENBANK_DIR):/genbank \
         --bind $(INDEXES_DIR):/indexes \
         --bind $(SKIMS_DIR):/skims \
         --bind $(PROCESSED_DIR):/processed_data
  BIND_DEV = $(BIND) \
             --bind $(PROJECT_ROOT)/obiluascript:/app/obiluascripts \
             --bind $(PROJECT_ROOT)/scripts:/app/scripts \
             --bind $(PROJECT_ROOT)/bin:/app/bin \
             --bind $(PROJECT_ROOT):/workspace \
             --writable-tmpfs

  # APPTAINER_ENV : Environment variables prepended to every apptainer
  #                 invocation.  Apptainer does not inherit Dockerfile ENV
  #                 declarations, so PATH is extended via APPTAINERENV_*.
  APPTAINER_ENV = APPTAINER_CACHEDIR=$(APPTAINER_CACHEDIR) \
                  APPTAINER_TMPDIR=$(APPTAINER_TMPDIR) \
                  APPTAINERENV_PREPEND_PATH=/app/bin:/app/scripts

  # RUN_CMD     : Interactive production shell via `apptainer run`.
  #               Executes the image's default runscript with a TTY.
  RUN_CMD     = $(APPTAINER_ENV) apptainer run   --pwd /app $(BIND) $(IMAGE_REF)

  # RUN_DEV_CMD : Interactive development shell via `apptainer shell`.
  #               Drops into a shell with the full source tree mounted.
  RUN_DEV_CMD = $(APPTAINER_ENV) apptainer shell --pwd /app $(BIND_DEV) $(IMAGE_REF)
else
  BIND = -v $(GENBANK_DIR):/genbank \
         -v $(INDEXES_DIR):/indexes \
         -v $(SKIMS_DIR):/skims \
         -v $(PROCESSED_DIR):/processed_data
  BIND_DEV = $(BIND) \
             -v $(PROJECT_ROOT)/obiluascripts:/app/obiluascripts \
             -v $(PROJECT_ROOT)/scripts:/app/scripts \
             -v $(PROJECT_ROOT)/bin:/app/bin \
             -v $(PROJECT_ROOT):/workspace

  # RUN_CMD     : Interactive production shell (-it flag).
  #               The container is removed after exit (--rm).
  RUN_CMD    = $(RUNTIME) run --rm -it $(BIND) $(IMAGE_REF)

  # RUN_DEV_CMD : Interactive development shell with source tree mounted.
  #               Starts bash explicitly (overrides the default entrypoint).
  RUN_DEV_CMD = $(RUNTIME) run --rm -it $(BIND_DEV) $(IMAGE_REF) bash
endif

# =============================================================================
# Non-interactive execution prefix (runtime-dependent)
# =============================================================================

# EXEC_CMD   : Prefix used to run a single command non-interactively inside
#              the container (no TTY, no interactive session).  Append the
#              command to execute, e.g.:
#                $(EXEC_CMD) my_script.sh
#              Used by all download_* targets; can also be used ad-hoc.
#                apptainer → `apptainer exec` (runs an explicit command,
#                            as opposed to `apptainer run` which calls the
#                            default runscript)
#                docker/podman → `run --rm` without -it
ifeq ($(RUNTIME),apptainer)
  EXEC_CMD = $(APPTAINER_ENV) apptainer exec --pwd /app $(BIND) $(IMAGE_REF)
else
  EXEC_CMD = $(RUNTIME) run --rm $(BIND) $(IMAGE_REF)
endif

# =============================================================================
# Targets
# =============================================================================

.PHONY: build build-multiplatform push pull-sif run run-dev ensure-dirs \
        download_references download_genbank download_human download_plants \
        clean clean-builder help

## ensure-dirs        : Create host mount directories if they do not exist
ensure-dirs:
	@mkdir -p $(HOST_DIRS)
	@echo "Host directories ready:"
	@for d in $(HOST_DIRS); do echo "  $$d"; done

## pull-sif           : Pull the image from the registry and convert it to a local SIF file
pull-sif:
	@mkdir -p $(IMAGES_DIR) $(APPTAINER_CACHEDIR) $(APPTAINER_TMPDIR)
	APPTAINER_CACHEDIR=$(APPTAINER_CACHEDIR) \
	APPTAINER_TMPDIR=$(APPTAINER_TMPDIR) \
	apptainer pull --force $(SIF_FILE) docker://$(FULL_IMAGE)

# Generate the Dockerfile with base image tags substituted
$(DOCKERFILE_GEN): $(DOCKERFILE_TPL)
	sed \
		-e 's/@@GO_VERSION@@/$(GO_VERSION)/g' \
		-e 's/@@ANACONDA_VERSION@@/$(MINICONDA_VERSION)/g' \
		$< > $@

## build              : Build for the native platform and load into the local Docker daemon
build: $(DOCKERFILE_GEN)
	docker build $(BUILD_ARGS) \
		--tag $(FULL_IMAGE) \
		--file $(DOCKERFILE_GEN) \
		$(BUILD_CONTEXT)

## build-multiplatform: Build for $(PLATFORMS) and export as a local OCI archive ($(OCI_ARCHIVE))
build-multiplatform: $(DOCKERFILE_GEN) .builder-ready
	docker buildx build $(BUILD_ARGS) \
		--builder $(BUILDER) \
		--platform $(PLATFORMS) \
		--tag $(FULL_IMAGE) \
		--file $(DOCKERFILE_GEN) \
		--provenance=false \
		--output type=oci,dest=$(OCI_ARCHIVE) \
		$(BUILD_CONTEXT)

# Create the buildx builder with docker-container driver (once)
.builder-ready:
	docker buildx inspect $(BUILDER) > /dev/null 2>&1 \
		|| docker buildx create --name $(BUILDER) --driver docker-container --bootstrap
	touch .builder-ready

## run                : Run the image (apptainer > docker > podman), mounting genbank/indexes/skims
run: ensure-dirs
	@if [ "$(RUNTIME)" = "none" ]; then echo "Error: no container runtime found (apptainer/docker/podman)"; exit 1; fi
	$(RUN_CMD)

## run-dev            : Run the image in dev mode (root, project mounted at /workspace)
run-dev: ensure-dirs
	@if [ "$(RUNTIME)" = "none" ]; then echo "Error: no container runtime found (apptainer/docker/podman)"; exit 1; fi
	$(RUN_DEV_CMD)

## download_references: Download GenBank, Human and Plants references inside the container
download_references: ensure-dirs
	@if [ "$(RUNTIME)" = "none" ]; then echo "Error: no container runtime found (apptainer/docker/podman)"; exit 1; fi
	$(EXEC_CMD) download_references.sh

## download_genbank   : Download GenBank divisions inside the container
download_genbank: ensure-dirs
	@if [ "$(RUNTIME)" = "none" ]; then echo "Error: no container runtime found (apptainer/docker/podman)"; exit 1; fi
	$(EXEC_CMD) download_genbank.sh

## download_human     : Download the human reference genome inside the container
download_human: ensure-dirs
	@if [ "$(RUNTIME)" = "none" ]; then echo "Error: no container runtime found (apptainer/docker/podman)"; exit 1; fi
	$(EXEC_CMD) download_human.sh

## download_plants    : Download Spermatophyta complete assemblies inside the container
download_plants: ensure-dirs
	@if [ "$(RUNTIME)" = "none" ]; then echo "Error: no container runtime found (apptainer/docker/podman)"; exit 1; fi
	$(EXEC_CMD) download_plants.sh

## push               : Push the OCI archive to the Zot registry using skopeo (run build-multiplatform first)
push: $(OCI_ARCHIVE)
	skopeo copy \
		--dest-tls-verify=true \
		--multi-arch all \
		oci-archive:$(OCI_ARCHIVE) \
		docker://$(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)

## clean              : Remove the local Docker image, the OCI archive and generated files
clean: clean-builder
	docker rmi --force $(FULL_IMAGE) 2>/dev/null || true
	rm -f $(OCI_ARCHIVE) $(DOCKERFILE_GEN)

## clean-builder      : Remove the buildx builder ($(BUILDER))
clean-builder:
	docker buildx rm $(BUILDER) 2>/dev/null || true
	rm -f .builder-ready

## help               : Show this help
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## //'

# Ensure the OCI archive exists before pushing
$(OCI_ARCHIVE):
	$(MAKE) build-multiplatform
