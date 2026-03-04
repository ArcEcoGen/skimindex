FROM debian:trixie-slim as builder

RUN apt-get update
RUN apt-get -y install \
    build-essential \
    curl

RUN curl -L https://raw.githubusercontent.com/metabarcoding/obitools4/master/install_obitools.sh | bash

FROM continuumio/anaconda3:main as skimindex

RUN conda install bioconda::kmindex bioconda::ntcard
RUN mkdir -p /usr/local/bin
COPY --from=builder /usr/local/bin/obi* /usr/local/bin
