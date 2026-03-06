# =============================================================================
# Image identity
# =============================================================================

IMAGE_NAME  := skimindex
IMAGE_TAG   := latest

# =============================================================================
# Registry
# =============================================================================

REGISTRY    := registry.metabarcoding.org/arcecogen

# =============================================================================
# Build platforms
# =============================================================================

PLATFORMS   := linux/amd64,linux/arm64

# =============================================================================
# Base image versions
# =============================================================================
# Substituted directly into the Dockerfile FROM lines (@@…@@ placeholders).
# NOT passed as --build-arg (multi-stage FROM lines cannot use global ARGs).

GO_VERSION        := latest
MINICONDA_VERSION := latest

# =============================================================================
# Tool versions installed inside the image
# =============================================================================

OBITOOLS_VERSION  := latest
KMINDEX_VERSION   := bioconda::kmindex
NTCARD_VERSION    := bioconda::ntcard

# =============================================================================
# Derived image identifiers
# =============================================================================

FULL_IMAGE  := $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)
OCI_ARCHIVE := $(IMAGE_NAME)-$(IMAGE_TAG).oci.tar

# =============================================================================
# Docker buildx builder
# =============================================================================

BUILDER := skimindex-builder

# =============================================================================
# OCI image annotations (injected via --build-arg)
# =============================================================================

OCI_VERSION  := $(IMAGE_TAG)
OCI_CREATED  := $(shell date -u +%Y-%m-%dT%H:%M:%SZ)
OCI_REVISION := $(shell git -C .. rev-parse --short HEAD 2>/dev/null || echo unknown)

# =============================================================================
# Build context and Dockerfile
# =============================================================================

BUILD_CONTEXT  := ..
DOCKERFILE_TPL := Dockerfile
DOCKERFILE_GEN := .Dockerfile.generated

BUILD_ARGS := \
	--build-arg OBITOOLS_VERSION=$(OBITOOLS_VERSION) \
	--build-arg KMINDEX_VERSION=$(KMINDEX_VERSION) \
	--build-arg NTCARD_VERSION=$(NTCARD_VERSION) \
	--build-arg OCI_VERSION=$(OCI_VERSION) \
	--build-arg OCI_CREATED=$(OCI_CREATED) \
	--build-arg OCI_REVISION=$(OCI_REVISION)

# =============================================================================
# Host filesystem layout
# =============================================================================

PROJECT_ROOT := $(abspath $(BUILD_CONTEXT))
CONFIG_FILE  := $(PROJECT_ROOT)/config/skimindex.toml

# =============================================================================
# GitHub repository
# =============================================================================

GITHUB_RAW_URL ?= https://raw.githubusercontent.com/metabarcoding/skimindex/main

# =============================================================================
# User entry-point script
# =============================================================================

SKIMINDEX_SH      := $(PROJECT_ROOT)/skimindex.sh
SKIMINDEX_SH_IN   := $(PROJECT_ROOT)/docker/skimindex.sh.in
BUILD_USER_SCRIPT := $(PROJECT_ROOT)/docker/build_user_script.sh


# =============================================================================
# Targets
# =============================================================================

.PHONY: all build build-multiplatform push run run-dev \
        skimindex-script clean clean-builder help

## all                : Build multi-platform image, push to registry, generate skimindex.sh
all: build-multiplatform push skimindex-script

## skimindex-script   : Generate the standalone user entry-point skimindex.sh
skimindex-script: $(SKIMINDEX_SH)

$(SKIMINDEX_SH): $(SKIMINDEX_SH_IN) $(BUILD_USER_SCRIPT) \
                 $(PROJECT_ROOT)/scripts/__utils_functions.sh \
                 $(wildcard $(PROJECT_ROOT)/scripts/*.sh)
	bash $(BUILD_USER_SCRIPT) \
		--root    $(PROJECT_ROOT) \
		--set     IMAGE_REGISTRY=$(REGISTRY) \
		--set     IMAGE_NAME=$(IMAGE_NAME) \
		--set     IMAGE_TAG=$(IMAGE_TAG) \
		--set     GITHUB_RAW_URL=$(GITHUB_RAW_URL) \
		$(SKIMINDEX_SH_IN) > $@
	chmod +x $@
	@echo "Generated: $@"

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

## run                : Start an interactive shell inside the container
run: $(SKIMINDEX_SH)
	$(SKIMINDEX_SH) --project-dir $(PROJECT_ROOT) shell

## run-dev            : Start a dev shell with source tree mounted (scripts/bin/obiluascripts)
run-dev: $(SKIMINDEX_SH)
	$(SKIMINDEX_SH) --project-dir $(PROJECT_ROOT) shell \
		--mount $(PROJECT_ROOT)/obiluascripts:/app/obiluascripts \
		--mount $(PROJECT_ROOT)/scripts:/app/scripts \
		--mount $(PROJECT_ROOT)/bin:/app/bin \
		--mount $(PROJECT_ROOT):/workspace

## push               : Push the OCI archive to the Zot registry using skopeo
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
