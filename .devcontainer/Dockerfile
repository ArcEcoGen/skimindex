ARG BASE_IMAGE=registry.metabarcoding.org/arcecogen/skimindex:latest
FROM ${BASE_IMAGE}

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        openssh-client \
        procps \
    && rm -rf /var/lib/apt/lists/*

USER skimindex
