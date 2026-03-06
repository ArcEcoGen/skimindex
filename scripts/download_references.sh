#!/usr/bin/env bash
# ============================================================
# download_references.sh
# Master script for the reference data pipeline.
#
# Usage:
#   download_references.sh [OPTIONS] [genbank_dir]
#
# Options:
#   --list           Print available genome sections as CSV and exit.
#   --genbank-div    Print configured GenBank divisions as CSV and exit.
#   --section NAME   Download a single genome section.
#   --genbank        Download GenBank flat-file divisions.
#   --all-sections   Download all genome sections defined in config.
#
# Default (no options): --all-sections --genbank
#
# Options can be combined freely:
#   download_references.sh --genbank --section human
#
# Each download step is independent: a failure stops the pipeline
# but already-completed steps are skipped on re-run (resume logic
# is handled by each individual script).
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=__skimindex_config.sh
source "${SCRIPT_DIR}/__skimindex_config.sh"

# ---------- argument parsing ----------
DO_GENBANK=false
DO_ALL_SECTIONS=false
DO_SECTION=""
LIST_MODE=false
GENBANK_DIV_MODE=false
GENBANK_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            sed -En '2,/^# =+$/{ s/^# ?//; /^=+$/d; p; }' "$0"
            exit 0
            ;;
        --list)         LIST_MODE=true;        shift   ;;
        --genbank-div)  GENBANK_DIV_MODE=true; shift   ;;
        --genbank)      DO_GENBANK=true;       shift   ;;
        --all-sections) DO_ALL_SECTIONS=true;  shift   ;;
        --section)      DO_SECTION="$2";       shift 2 ;;
        -*)
            logerror "Unknown option: $1"
            exit 1
            ;;
        *)
            GENBANK_DIR="$1"
            shift
            ;;
    esac
done

# Default: no explicit action selected → do everything
if ! $DO_GENBANK && ! $DO_ALL_SECTIONS && [[ -z "$DO_SECTION" ]] \
        && ! $LIST_MODE && ! $GENBANK_DIV_MODE; then
    DO_GENBANK=true
    DO_ALL_SECTIONS=true
fi

GENBANK_DIR="${GENBANK_DIR:-${SKIMINDEX__DIRECTORIES__GENBANK}}"

# ---------- info-only modes (print and exit) ----------

if $LIST_MODE; then
    echo "${SKIMINDEX__TAXON_SECTIONS// /,}"
    exit 0
fi

if $GENBANK_DIV_MODE; then
    echo "${SKIMINDEX__GENBANK__DIVISIONS// /,}"
    exit 0
fi

# ---------- helpers ----------

_step=0

run_step() {
    local label="$1"
    shift
    _step=$(( _step + 1 ))
    loginfo ">>> Step ${_step}: $label"
    if "$@"; then
        loginfo "<<< Step ${_step} OK"
    else
        logerror "Step ${_step} ($label) failed — aborting."
        exit 1
    fi
}

# ---------- GenBank divisions ----------

if $DO_GENBANK; then
    run_step "GenBank divisions" \
        "${SCRIPT_DIR}/download_genbank.sh" "$GENBANK_DIR"
fi

# ---------- single section ----------

if [[ -n "$DO_SECTION" ]]; then
    run_step "Genome: $DO_SECTION" \
        "${SCRIPT_DIR}/_download_refgenome.sh" --section "$DO_SECTION"
fi

# ---------- all genome sections ----------

if $DO_ALL_SECTIONS; then
    read -r -a GENOME_SECTIONS <<< "${SKIMINDEX__TAXON_SECTIONS}"

    if [[ ${#GENOME_SECTIONS[@]} -eq 0 ]]; then
        logwarning "No genome sections found in config — nothing to download."
    else
        for section in "${GENOME_SECTIONS[@]}"; do
            run_step "Genome: $section" \
                "${SCRIPT_DIR}/_download_refgenome.sh" --section "$section"
        done
    fi
fi

loginfo "All requested downloads completed successfully."
