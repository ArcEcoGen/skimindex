#!/usr/bin/env bash
# ============================================================
# download_refgenome.sh
# Downloads genome assemblies from NCBI for a given taxon and
# produces one compressed GBFF file per accession:
#   {scientific_name}-{accession}.gbff.gz
#
# All filter options are passed through to:
#   datasets download genome taxon <TAXON> [OPTIONS] --include gbff
#
# Usage:
#   download_refgenome.sh --section NAME   [OVERRIDES]
#   download_refgenome.sh --taxon NAME --output DIR [OPTIONS]
#
# --section NAME
#   Load all parameters from the SKIMINDEX__{NAME^^}__* environment
#   variables exported by __skimindex_config.sh.  The section must
#   define at least SKIMINDEX__{NAME^^}__TAXON; the output directory
#   is SKIMINDEX__DIRECTORIES__GENBANK / SKIMINDEX__{NAME^^}__DIRECTORY
#   (falls back to SKIMINDEX__DIRECTORIES__GENBANK/<name>).
#   Explicit options listed below override the section values.
#
# Options (override section defaults when --section is used):
#   --taxon NAME              NCBI taxon name
#   --output DIR              Output directory
#   --reference               Pass --reference filter to datasets
#   --assembly-source SRC     refseq | genbank
#   --assembly-level LEVEL    complete | chromosome | scaffold | contig
#   --assembly-version VER    latest | all
#
# Resume logic (checked in order):
#   1. ncbi_dataset/ present  → compress only (skip existing .gbff.gz)
#   2. Otherwise              → download_zip + extract + compress per accession
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=__download_functions.sh
source "${SCRIPT_DIR}/__download_functions.sh"
# shellcheck source=__skimindex_config.sh
source "${SCRIPT_DIR}/__skimindex_config.sh"

# ---------- defaults ----------
SECTION=""
TAXON=""
OUTPUT_DIR=""
OPT_REFERENCE=""          # unset = not specified; "true"/"false" = explicit
OPT_ASSEMBLY_SOURCE=""
OPT_ASSEMBLY_LEVEL=""
OPT_ASSEMBLY_VERSION=""

# ---------- argument parsing ----------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            sed -n '2,/^# =\+$/{ s/^# \{0,1\}//; /^=\+$/d; p }' "$0"
            exit 0
            ;;
        --section)          SECTION="$2";              shift 2 ;;
        --taxon)            TAXON="$2";                shift 2 ;;
        --output)           OUTPUT_DIR="$2";            shift 2 ;;
        --reference)        OPT_REFERENCE="true";       shift   ;;
        --assembly-source)  OPT_ASSEMBLY_SOURCE="$2";   shift 2 ;;
        --assembly-level)   OPT_ASSEMBLY_LEVEL="$2";    shift 2 ;;
        --assembly-version) OPT_ASSEMBLY_VERSION="$2";  shift 2 ;;
        -*)
            logerror "Unknown option: $1"
            exit 1
            ;;
        *)
            OUTPUT_DIR="$1"
            shift
            ;;
    esac
done

# ---------- load section defaults ----------
if [[ -n "$SECTION" ]]; then
    SECTION_UP="${SECTION^^}"

    taxon_var="SKIMINDEX__${SECTION_UP}__TAXON"
    if [[ -z "${!taxon_var:-}" ]]; then
        logerror "Section [$SECTION]: SKIMINDEX__${SECTION_UP}__TAXON is not defined."
        exit 1
    fi

    # Section values as defaults (explicit options above take precedence)
    [[ -z "$TAXON"               ]] && TAXON="$( eval echo "\${${taxon_var}}" )"

    if [[ -z "$OUTPUT_DIR" ]]; then
        rel_var="SKIMINDEX__${SECTION_UP}__DIRECTORY"
        genbank_var="SKIMINDEX__DIRECTORIES__GENBANK"
        _genbank_root="${!genbank_var:-/genbank}"
        _rel_dir="${!rel_var:-${SECTION,,}}"
        OUTPUT_DIR="${_genbank_root}/${_rel_dir}"
        unset _genbank_root _rel_dir
    fi

    ref_var="SKIMINDEX__${SECTION_UP}__REFERENCE"
    [[ -z "$OPT_REFERENCE"        && -n "${!ref_var:-}"         ]] && OPT_REFERENCE="${!ref_var}"

    src_var="SKIMINDEX__${SECTION_UP}__ASSEMBLY_SOURCE"
    [[ -z "$OPT_ASSEMBLY_SOURCE"  && -n "${!src_var:-}"         ]] && OPT_ASSEMBLY_SOURCE="${!src_var}"

    lvl_var="SKIMINDEX__${SECTION_UP}__ASSEMBLY_LEVEL"
    [[ -z "$OPT_ASSEMBLY_LEVEL"   && -n "${!lvl_var:-}"         ]] && OPT_ASSEMBLY_LEVEL="${!lvl_var}"

    ver_var="SKIMINDEX__${SECTION_UP}__ASSEMBLY_VERSION"
    [[ -z "$OPT_ASSEMBLY_VERSION" && -n "${!ver_var:-}"         ]] && OPT_ASSEMBLY_VERSION="${!ver_var}"
fi

# ---------- validation ----------
if [[ -z "$TAXON" ]]; then
    logerror "--taxon is required (or use --section with a configured section)."
    exit 1
fi

if [[ -z "$OUTPUT_DIR" ]]; then
    logerror "--output is required (or use --section with a configured output dir)."
    exit 1
fi

ZIP_FILE="${OUTPUT_DIR}/download.zip"
DATASET_DIR="${OUTPUT_DIR}/ncbi_dataset"
REPORT="${DATASET_DIR}/data/assembly_data_report.jsonl"

mkdir -p "$OUTPUT_DIR"

# ---------- build datasets filter flags ----------
DATASETS_OPTS=()
[[ "$OPT_REFERENCE"       == "true" ]] && DATASETS_OPTS+=(--reference)
[[ -n "$OPT_ASSEMBLY_SOURCE"        ]] && DATASETS_OPTS+=(--assembly-source  "$OPT_ASSEMBLY_SOURCE")
[[ -n "$OPT_ASSEMBLY_LEVEL"         ]] && DATASETS_OPTS+=(--assembly-level   "$OPT_ASSEMBLY_LEVEL")
[[ -n "$OPT_ASSEMBLY_VERSION"       ]] && DATASETS_OPTS+=(--assembly-version "$OPT_ASSEMBLY_VERSION")

loginfo "Taxon          : $TAXON"
loginfo "Output         : $OUTPUT_DIR"
loginfo "Datasets flags : ${DATASETS_OPTS[*]:-<none>}"

# ---------- stage 1: download + extract if needed ----------

if [[ ! -d "$DATASET_DIR" ]]; then
    loginfo "Downloading assemblies for '$TAXON'..."
    loginfo "Destination: $ZIP_FILE"
    loginfo "This may take a long time — be patient..."
    download_zip "$ZIP_FILE" taxon "$TAXON" \
        "${DATASETS_OPTS[@]}" \
        --include gbff

    extract_zip "$ZIP_FILE" "$OUTPUT_DIR"
    rm -f "$ZIP_FILE"
    loginfo "Download and extraction complete."
else
    loginfo "ncbi_dataset/ found — skipping download and extraction."
    rm -f "$ZIP_FILE" 2>/dev/null || true
fi

# ---------- stage 2: compress per accession ----------

loginfo "Compressing per-accession GBFF files into $OUTPUT_DIR ..."

ACCESSIONS=()
while IFS= read -r -d '' acc_dir; do
    ACCESSIONS+=( "$(basename "$acc_dir")" )
done < <(find "${DATASET_DIR}/data" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)

TOTAL=${#ACCESSIONS[@]}
COUNT=0
ERRORS=0

for accession in "${ACCESSIONS[@]}"; do
    COUNT=$((COUNT + 1))
    loginfo "[$COUNT/$TOTAL] $accession"

    organism=$(organism_from_report "$REPORT" "$accession")
    [[ -z "$organism" ]] && organism="$accession"

    sname=$(safe_name "$organism")
    out_file="${OUTPUT_DIR}/${sname}-${accession}.gbff.gz"

    if ! consolidate_accession "${DATASET_DIR}/data/${accession}" "$organism" "$out_file"; then
        logerror "Failed to compress $accession"
        ERRORS=$((ERRORS + 1))
    fi
done

if [[ $ERRORS -eq 0 ]]; then
    loginfo "Removing $DATASET_DIR ..."
    rm -rf "$DATASET_DIR"
fi

loginfo "===== Summary ====="
loginfo "  Total    : $TOTAL"
loginfo "  Errors   : $ERRORS"
loginfo "  Output   : $OUTPUT_DIR"

if [[ $ERRORS -gt 0 ]]; then
    logwarning "$ERRORS accession(s) failed — re-run to retry."
    exit 1
fi
