# Tools installed in the container image

This page documents all third-party tools bundled in the skimindex container image.
Versions are pinned in `docker/Makefile` and substituted at build time via `--build-arg`.

---

## OBITools4

Bioinformatics suite for the analysis of DNA metabarcoding data.
Provides sequence manipulation, demultiplexing, taxonomic assignment,
and quality filtering.

| | |
|---|---|
| **Version** | 4.4.29 (pinned; `OBITOOLS_VERSION` in `docker/Makefile`) |
| **Binary location** | `/usr/local/bin/obi*` |
| **Architecture** | Compiled from source for each target platform (builder stage) |
| **Language** | Go |
| **GitHub** | <https://github.com/metabarcoding/obitools4> |
| **Documentation** | <https://metabarcoding.org/obitools4> |
| **Institution** | LECA / Université Grenoble Alpes |

### Reference

> Boyer F., Mercier C., Bonin A., Le Bras Y., Taberlet P., Coissac E. (2016).
> **obitools: a unix-inspired software package for DNA metabarcoding.**
> *Molecular Ecology Resources*, 16(1), 176–182.
> <https://doi.org/10.1111/1755-0998.12428>

---

## kmindex

Fast and memory-efficient k-mer indexing and querying across large collections
of genomic datasets. Used by skimindex for decontamination k-mer index construction
and querying.

| | |
|---|---|
| **Version** | latest bioconda release (`bioconda::kmindex`) |
| **Binary location** | `/opt/conda/bin/kmindex` |
| **Architecture** | linux/amd64, linux/arm64 |
| **Language** | C++ |
| **GitHub** | <https://github.com/tlemane/kmindex> |
| **Documentation** | <https://tlemane.github.io/kmindex> |

### Reference

> Marchet C., Mehta N., Sinno R., Pibiri G.E., Limasset A. (2024).
> **Scalable sequence search and taxonomic classification using kmindex and FULGOR.**
> *iScience*, 27, 109308.
> <https://doi.org/10.1016/j.isci.2024.109308>

---

## ntCard

Streaming algorithm for estimating k-mer frequency histograms from sequencing data.
Used to estimate genome size and coverage prior to k-mer counting.

| | |
|---|---|
| **Version** | latest bioconda release (`bioconda::ntcard`) |
| **Binary location** | `/opt/conda/bin/ntcard` |
| **Architecture** | linux/amd64, linux/arm64 |
| **Language** | C++ |
| **GitHub** | <https://github.com/bcgsc/ntCard> |
| **Website** | <https://bcgsc.ca/resources/software/ntcard> |

### Reference

> Mohamadi H., Khan H., Birol I. (2017).
> **ntCard: a streaming algorithm for cardinality estimation in genomics data.**
> *Bioinformatics*, 33(9), 1324–1330.
> <https://doi.org/10.1093/bioinformatics/btw832>

---

## NCBI SRA Toolkit

Suite of tools for downloading, validating, and converting sequencing data
from the NCBI Sequence Read Archive (SRA). Provides `prefetch`, `fasterq-dump`,
`sam-dump`, and many others.

| | |
|---|---|
| **Version** | 3.2.0 (latest bioconda; `bioconda::sra-tools`) |
| **Binary location** | `/opt/conda/bin/prefetch`, `/opt/conda/bin/fasterq-dump`, … |
| **Architecture** | linux/amd64, linux/arm64 (via bioconda + `conda-forge::ossuuid`) |
| **Language** | C / C++ |
| **GitHub** | <https://github.com/ncbi/sra-tools> |
| **Documentation** | <https://github.com/ncbi/sra-tools/wiki> |
| **Website** | <https://www.ncbi.nlm.nih.gov/sra/docs/sradownload/> |
| **Institution** | NCBI / National Library of Medicine |

### Reference

> Leinonen R., Sugawara H., Shumway M., International Nucleotide Sequence Database Collaboration (2011).
> **The sequence read archive.**
> *Nucleic Acids Research*, 39(Database issue), D19–D21.
> <https://doi.org/10.1093/nar/gkq1019>

---

## NCBI Datasets CLI

Command-line interface for downloading genome assemblies, gene sequences, and
associated metadata directly from NCBI. Provides `datasets` and `dataformat`.

| | |
|---|---|
| **Version** | v18.21.0 (pinned; `NCBI_DATASETS_VERSION` in `docker/Makefile`) |
| **Binaries** | `/usr/local/bin/datasets`, `/usr/local/bin/dataformat` |
| **Architecture** | linux/amd64, linux/arm64 (official NCBI releases) |
| **Language** | Go |
| **GitHub** | <https://github.com/ncbi/datasets> |
| **Documentation** | <https://www.ncbi.nlm.nih.gov/datasets/docs/v2/download-and-install/> |
| **Institution** | NCBI / National Library of Medicine |

---

## IBM Aspera Transfer SDK (`ascp`)

High-speed file transfer client using the FASP protocol. Used by the SRA Toolkit
to accelerate downloads from NCBI when available, falling back transparently to
HTTPS otherwise.

| | |
|---|---|
| **Version** | 1.1.7 (pinned; `ASPERA_SDK_VERSION` in `docker/Makefile`) |
| **Binary** | `/usr/local/bin/ascp` |
| **Architecture** | linux/amd64 (`linux-amd64`), linux/arm64 (`linux-aarch64`) |
| **Distribution** | IBM CloudFront CDN (`d3pgwzphl5a0ty.cloudfront.net`) |
| **Documentation** | <https://www.ibm.com/docs/en/ahts/4.4.x> |
| **SDK** | <https://developer.ibm.com/apis/catalog/aspera--aspera-transfer-sdk/> |
| **Website** | <https://www.ibm.com/products/aspera> |
| **Institution** | IBM |
| **SRA integration** | Configured via `vdb-config --set /TOOLS/ascp-path=/usr/local/bin/ascp` |

> **Note:** ARM64 support was introduced in SDK 1.1.4 (transferd 1.1.4).

---

## kmerasm

Simple de Bruijn unitig assembler for 31-mers.
Reads canonical 31-mers (one per line) and outputs unitigs in FASTA format,
built from non-branching paths in the de Bruijn graph.

| | |
|---|---|
| **Version** | in-house (built from `src/kmerasm/`) |
| **Binary** | `/app/bin/kmerasm` |
| **Architecture** | Compiled for each target platform (builder stage) |
| **Language** | C |
| **Source** | `src/kmerasm/kmerasm.c` in this repository |

---

## Base environment

### Miniconda3 / conda

| | |
|---|---|
| **Base image** | `continuumio/miniconda3:latest` |
| **Python** | `/opt/conda/bin/python3` |
| **Website** | <https://docs.conda.io> |

Tools installed via conda are in `/opt/conda/bin/` and available on `PATH`.

### System utilities (apt)

Installed via `apt-get` in the container:

| Tool | Purpose |
|------|---------|
| `pigz` | Parallel gzip compression / decompression |
| `jq` | JSON processor |
| `curl` | HTTP/FTP client |
| `make` | Build automation |
| `less` | Pager |
| `sudo` | Privilege escalation (user `skimindex` has `NOPASSWD:ALL`) |

---

## Version management

All pinned versions are centralised in `docker/Makefile`:

```makefile
OBITOOLS_VERSION      := 4.4.29
NCBI_DATASETS_VERSION := v18.21.0
KMINDEX_VERSION       := bioconda::kmindex
NTCARD_VERSION        := bioconda::ntcard
SRATOOLS_VERSION      := bioconda::sra-tools
ASPERA_SDK_VERSION    := 1.1.7
```

To update a tool, change the corresponding variable and rebuild with `make all`.
