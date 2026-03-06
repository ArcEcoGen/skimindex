# builder runs for each target platform so OBITools4 binaries match the target architecture
# Uses the official golang image — no Go download needed inside the container
# Base image versions are substituted by the Makefile (GO_VERSION / ANACONDA_VERSION)
FROM golang:@@GO_VERSION@@ AS builder

ARG OBITOOLS_VERSION=latest
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update
RUN apt-get -y install \
    build-essential \
    ca-certificates \
    curl \
    make \
    unzip \
    zlib1g-dev

COPY docker/install_obitools.sh /tmp/install_obitools.sh
RUN if [ "$OBITOOLS_VERSION" = "latest" ]; then \
        bash /tmp/install_obitools.sh --install-dir /usr/local; \
    else \
        bash /tmp/install_obitools.sh --install-dir /usr/local --version "$OBITOOLS_VERSION"; \
    fi \
    && rm /tmp/install_obitools.sh

# Build C tools from src/
COPY src/ /tmp/src/
RUN for dir in /tmp/src/*/; do \
        [ -f "$dir/Makefile" ] && make -C "$dir"; \
    done

FROM continuumio/miniconda3:@@ANACONDA_VERSION@@ AS skimindex

ARG KMINDEX_VERSION=bioconda::kmindex
ARG NTCARD_VERSION=bioconda::ntcard

# OCI image annotations (https://github.com/opencontainers/image-spec/blob/main/annotations.md)
ARG OCI_VERSION=latest
ARG OCI_CREATED
ARG OCI_REVISION

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl make unzip less jq pigz \
    && rm -rf /var/lib/apt/lists/*

RUN conda install --yes ${KMINDEX_VERSION} ${NTCARD_VERSION} \
    && conda clean --all --yes

RUN mkdir -p /usr/local/bin \
             /genbank \
             /indexes \
             /processed_data/decontamination \
             /processed_data/skims \
             /skims \
             /app/scripts /app/bin /app/obiluascripts \
             /config \
             /log

COPY --from=builder /usr/local/bin/obi* /usr/local/bin
COPY genbank/Makefile /genbank/Makefile
COPY obiluascripts/ /app/obiluascripts/
COPY scripts/ /app/scripts/
COPY config/ /config/

# Install NCBI datasets CLI tools (architecture-aware) and C tools from src/
ARG TARGETARCH
RUN curl -fsSL "https://ftp.ncbi.nlm.nih.gov/pub/datasets/command-line/v2/linux-${TARGETARCH}/datasets" \
         -o /usr/local/bin/datasets \
    && curl -fsSL "https://ftp.ncbi.nlm.nih.gov/pub/datasets/command-line/v2/linux-${TARGETARCH}/dataformat" \
         -o /usr/local/bin/dataformat \
    && chmod 755 /usr/local/bin/obi* /usr/local/bin/datasets /usr/local/bin/dataformat

COPY --from=builder /tmp/src/ /tmp/src-built/
RUN find /tmp/src-built -maxdepth 2 -type f -executable -exec cp {} /app/bin/ \; \
    && rm -rf /tmp/src-built

# Create an unprivileged user
RUN groupadd -r skimindex \
    && useradd -r -g skimindex \
               -s /bin/bash \
               skimindex

LABEL org.opencontainers.image.title="skimindex" \
      org.opencontainers.image.description="Genome skim kmer indexing." \
      org.opencontainers.image.url="https://registry.metabarcoding.org" \
      org.opencontainers.image.source="https://github.com/metabarcoding/obitools4" \
      org.opencontainers.image.vendor="Metabarcoding.org" \
      org.opencontainers.image.licenses="CECILL-2.1" \
      org.opencontainers.image.version="${OCI_VERSION}" \
      org.opencontainers.image.created="${OCI_CREATED}" \
      org.opencontainers.image.revision="${OCI_REVISION}"

ENV PATH="/app/bin:/app/scripts:${PATH}"

WORKDIR /app

USER skimindex
