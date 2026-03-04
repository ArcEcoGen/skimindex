# Image configuration
IMAGE_NAME  := skimindex
IMAGE_TAG   := latest

# Registry (Zot OCI registry — push via skopeo, not docker)
REGISTRY    := registry.metabarcoding.org/arcecogen

# Target platforms for multi-platform builds
PLATFORMS   := linux/amd64,linux/arm64

# Base images versions (substituted directly into FROM lines — no global ARG needed)
GO_VERSION        := latest
MINICONDA_VERSION := latest

# Tools versions (for tracking / future pinning)
OBITOOLS_BRANCH   := master
KMINDEX_VERSION   := bioconda::kmindex
NTCARD_VERSION    := bioconda::ntcard

# Full image name (registry + name + tag)
FULL_IMAGE  := $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)

# Local OCI archive produced by the multiplatform build
OCI_ARCHIVE := $(IMAGE_NAME)-$(IMAGE_TAG).oci.tar

# buildx builder name (docker-container driver required for OCI export and multi-platform)
BUILDER := skimindex-builder

# OCI image annotations
OCI_VERSION  := $(IMAGE_TAG)
OCI_CREATED  := $(shell date -u +%Y-%m-%dT%H:%M:%SZ)
OCI_REVISION := $(shell git -C .. rev-parse --short HEAD 2>/dev/null || echo unknown)

# Build context is the project root (parent of docker/) to allow COPY of ../genbank/
BUILD_CONTEXT := ..

# Effective Dockerfile (base image tags substituted, no global ARGs)
DOCKERFILE_TPL := Dockerfile
DOCKERFILE_GEN := .Dockerfile.generated

# Docker build args (no DEBIAN_VERSION / ANACONDA_VERSION — baked into FROM)
BUILD_ARGS := \
	--build-arg OBITOOLS_BRANCH=$(OBITOOLS_BRANCH) \
	--build-arg KMINDEX_VERSION=$(KMINDEX_VERSION) \
	--build-arg NTCARD_VERSION=$(NTCARD_VERSION) \
	--build-arg OCI_VERSION=$(OCI_VERSION) \
	--build-arg OCI_CREATED=$(OCI_CREATED) \
	--build-arg OCI_REVISION=$(OCI_REVISION)

# Absolute path to the project root (BUILD_CONTEXT may be relative)
PROJECT_ROOT := $(abspath $(BUILD_CONTEXT))

# Host directories bound into the container (override on command line)
GENBANK_DIR       := $(PROJECT_ROOT)/genbank
INDEXES_DIR       := $(PROJECT_ROOT)/indexes
SKIMS_DIR         := $(PROJECT_ROOT)/skims
PROCESSED_DIR     := $(PROJECT_ROOT)/processed_data

# SIF image for apptainer (stored in images/ at the project root)
IMAGES_DIR := $(PROJECT_ROOT)/images
SIF_FILE   := $(IMAGES_DIR)/$(IMAGE_NAME)-$(IMAGE_TAG).sif

# Apptainer cache and tmp — kept inside images/ to avoid filling /tmp
APPTAINER_CACHEDIR ?= $(IMAGES_DIR)/.apptainer/cache
APPTAINER_TMPDIR   ?= $(IMAGES_DIR)/.apptainer/tmp

# Detect container runtime: apptainer > docker > podman
RUNTIME := $(shell \
	if command -v apptainer >/dev/null 2>&1; then echo apptainer; \
	elif command -v docker  >/dev/null 2>&1; then echo docker;    \
	elif command -v podman  >/dev/null 2>&1; then echo podman;    \
	else echo none; fi)

# Image reference per runtime:
#   apptainer → local SIF file (must exist; run `make pull-sif` first)
#   docker/podman → registry image name
ifeq ($(RUNTIME),apptainer)
  IMAGE_REF := $(SIF_FILE)
else
  IMAGE_REF := $(FULL_IMAGE)
endif

# Bind-mount flags per runtime (apptainer uses --bind, docker/podman use -v)
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
  # Apptainer ignores Dockerfile ENV — use APPTAINERENV_* to inject environment
  APPTAINER_ENV = APPTAINER_CACHEDIR=$(APPTAINER_CACHEDIR) \
                  APPTAINER_TMPDIR=$(APPTAINER_TMPDIR) \
                  APPTAINERENV_PREPEND_PATH=/app/bin:/app/scripts
  RUN_CMD     = $(APPTAINER_ENV) apptainer run   --pwd /app $(BIND) $(IMAGE_REF)
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
  RUN_CMD    = $(RUNTIME) run --rm -it $(BIND) $(IMAGE_REF)
  RUN_DEV_CMD = $(RUNTIME) run --rm -it $(BIND_DEV) $(IMAGE_REF) bash
endif

# One-shot download command per runtime (non-interactive, no TTY)
ifeq ($(RUNTIME),apptainer)
  DOWNLOAD_CMD = $(APPTAINER_ENV) apptainer exec --pwd /app $(BIND) $(IMAGE_REF)
else
  DOWNLOAD_CMD = $(RUNTIME) run --rm $(BIND) $(IMAGE_REF)
endif

# Host directories that must exist before any container is started
HOST_DIRS := $(GENBANK_DIR) $(INDEXES_DIR) $(SKIMS_DIR) $(PROCESSED_DIR)

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
	$(DOWNLOAD_CMD) download_references.sh

## download_genbank   : Download GenBank divisions inside the container
download_genbank: ensure-dirs
	@if [ "$(RUNTIME)" = "none" ]; then echo "Error: no container runtime found (apptainer/docker/podman)"; exit 1; fi
	$(DOWNLOAD_CMD) download_genbank.sh

## download_human     : Download the human reference genome inside the container
download_human: ensure-dirs
	@if [ "$(RUNTIME)" = "none" ]; then echo "Error: no container runtime found (apptainer/docker/podman)"; exit 1; fi
	$(DOWNLOAD_CMD) download_human.sh

## download_plants    : Download Spermatophyta complete assemblies inside the container
download_plants: ensure-dirs
	@if [ "$(RUNTIME)" = "none" ]; then echo "Error: no container runtime found (apptainer/docker/podman)"; exit 1; fi
	$(DOWNLOAD_CMD) download_plants.sh

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
