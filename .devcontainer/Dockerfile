FROM registry.metabarcoding.org/arcecogen/skimindex:latest

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        openssh-client \
        procps \
    && (curl -fsSL https://claude.ai/install.sh | bash) \
    && rm -rf /var/lib/apt/lists/*

USER skimindex
