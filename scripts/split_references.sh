#!/usr/bin/env bash
# ============================================================
# split_references.sh
# Split reference genome sequences into overlapping fragments
# for decontamination index building.
#
# Usage:
#   split_references.sh [OPTIONS]
#
# Options:
#   --list           Print available genome sections as CSV and exit.
#   --section NAME   Split a single genome section.
#   --all-sections   Split all genome sections defined in config.
#   --frg-size N     Fragment size (default: from config decontamination.frg_size).
#   --overlap N      Overlap between fragments (default: decontamination.kmer_size - 1).
#   --batches N      Number of output batches (default: from config decontamination.batches).
#
# Default (no options): --all-sections
#
# The output fragments are written to:
#   <genbank_dir>/<section_directory>/fragments/frg_<batch>.fasta.gz
# ============================================================

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=__skimindex_config.sh

source "${SCRIPT_DIR}/__skimindex_config.sh"

# ---------- argument parsing ----------
DO_ALL_SECTIONS=false
DO_SECTION=""
LIST_MODE=false
OPT_FRG_SIZE=""
OPT_OVERLAP=""
OPT_BATCHES=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            sed -En '2,/^# =+$/{ s/^# ?//; /^=+$/d; p; }' "$0"
            exit 0
            ;;
        --list)         LIST_MODE=true;        shift   ;;
        --all-sections) DO_ALL_SECTIONS=true;  shift   ;;
        --section)      DO_SECTION="$2";       shift 2 ;;
        --frg-size)     OPT_FRG_SIZE="$2";     shift 2 ;;
        --overlap)      OPT_OVERLAP="$2";      shift 2 ;;
        --batches)      OPT_BATCHES="$2";      shift 2 ;;
        -*)
            logerror "Unknown option: $1"
            exit 1
            ;;
        *)
            logerror "Unexpected argument: $1"
            exit 1
            ;;
    esac
done

# Default: no explicit action → do everything
if ! $DO_ALL_SECTIONS && [[ -z "$DO_SECTION" ]] && ! $LIST_MODE; then
    DO_ALL_SECTIONS=true
fi

# ---------- info-only modes ----------

if $LIST_MODE; then
    echo "${SKIMINDEX__GENOME_SECTIONS// /,}"
    exit 0
fi

# ---------- decontamination parameters ----------

FRG_SIZE="${OPT_FRG_SIZE:-${SKIMINDEX__DECONTAMINATION__FRG_SIZE}}"
OVERLAP="${OPT_OVERLAP:-$(( SKIMINDEX__DECONTAMINATION__KMER_SIZE - 1 ))}"
BATCHES="${OPT_BATCHES:-${SKIMINDEX__DECONTAMINATION__BATCHES}}"
GENBANK_ROOT="${SKIMINDEX__DIRECTORIES__GENBANK}"
PROCESSED_ROOT="${SKIMINDEX__DIRECTORIES__PROCESSED_DATA}"

loginfo "Fragment size : $FRG_SIZE"
loginfo "Overlap       : $OVERLAP"
loginfo "Batches       : $BATCHES"

# ---------- helpers ----------

# Find the most recent GenBank release directory under GENBANK_ROOT.
_genbank_release_dir() {
    find "$GENBANK_ROOT" -maxdepth 1 -type d -name 'Release_*' \
    | sort -t_ -k2 -V | tail -1
}

# Common pipeline: obiscript → filter Ns → distribute into batches.
# Reads sequences from stdin; $1 is the output fragments directory.
_do_split() {
    local fragments_dir="$1"
    FRAGMENT_SIZE="$FRG_SIZE" OVERLAP="$OVERLAP" \
    obiscript -S /app/obiluascripts/splitseqs.lua \
    | obigrep -v -s '^[Nn]+$' \
    | obidistribute -Z -n "$BATCHES" \
                    -p "${fragments_dir}/frg_%s.fasta.gz"
}

# ---------- split one section ----------

_split_section() {
    local section="$1"
    local section_up="${section^^}"

    local rel_var="SKIMINDEX__${section_up}__DIRECTORY"
    local rel_dir="${!rel_var:-${section,,}}"
    local fragments_dir="${PROCESSED_ROOT}/${rel_dir}/fragments"

    loginfo "Section       : $section"
    loginfo "Output dir    : $fragments_dir"

    mkdir -p "$fragments_dir"

    # Determine whether this is a taxon section or a GenBank division section
    case " ${SKIMINDEX__TAXON_SECTIONS} " in
        *" ${section} "*)
            _split_taxon_section "$section" "$rel_dir" "$fragments_dir" ;;
        *)
            _split_division_section "$section" "$section_up" "$fragments_dir" ;;
    esac

    loginfo "Fragments written to $fragments_dir"
}

# --- taxon section: input files are pre-downloaded .fasta.gz / .gbff.gz ---

_split_taxon_section() {
    local section="$1"
    local rel_dir="$2"
    local fragments_dir="$3"
    local section_dir="${GENBANK_ROOT}/${rel_dir}"

    loginfo "Input dir     : $section_dir"

    if [[ ! -d "$section_dir" ]]; then
        logwarning "Section directory not found: $section_dir — skipping."
        return 0
    fi

    local -a inputs=()
    while IFS= read -r -d '' f; do
        inputs+=("$f")
    done < <(find "$section_dir" -maxdepth 1 \( -name '*.fasta.gz' -o -name '*.gbff.gz' \) -print0 | sort -z)

    if [[ ${#inputs[@]} -eq 0 ]]; then
        logwarning "No .fasta.gz or .gbff.gz files found in $section_dir — skipping."
        return 0
    fi

    loginfo "Splitting ${#inputs[@]} file(s) into $BATCHES batches..."

    obiconvert "${inputs[@]}" | _do_split "$fragments_dir"
}

# --- GenBank division section: filter by taxid from division flat files ---

_split_division_section() {
    local section="$1"
    local section_up="$2"
    local fragments_dir="$3"

    local taxid_var="SKIMINDEX__${section_up}__TAXID"
    local div_var="SKIMINDEX__${section_up}__DIVISION"
    local taxid="${!taxid_var}"
    local divisions="${!div_var}"

    if [[ -z "$taxid" || -z "$divisions" ]]; then
        logerror "Section $section: missing taxid or division in config."
        return 1
    fi

    # Locate current GenBank release
    local release_dir
    release_dir="$(_genbank_release_dir)"
    if [[ -z "$release_dir" ]]; then
        logerror "No GenBank release directory found under $GENBANK_ROOT."
        return 1
    fi

    local taxonomy="${release_dir}/taxonomy/ncbi_taxonomy.tgz"
    if [[ ! -f "$taxonomy" ]]; then
        logerror "Taxonomy file not found: $taxonomy"
        return 1
    fi

    # Build list of division directories (obitools handle directory traversal)
    local -a inputs=()
    for div in $divisions; do
        local div_dir="${release_dir}/fasta/${div}"
        if [[ ! -d "$div_dir" ]]; then
            logwarning "Division directory not found: $div_dir — skipping."
            continue
        fi
        inputs+=("$div_dir")
    done

    if [[ ${#inputs[@]} -eq 0 ]]; then
        logwarning "No division directories found for [$divisions] — skipping."
        return 0
    fi

    loginfo "Taxonomy      : $taxonomy"
    loginfo "TaxID         : $taxid"
    loginfo "Divisions     : $divisions"
    loginfo "Splitting into $BATCHES batches..."

    obigrep -t "$taxonomy" -r "$taxid" "${inputs[@]}" | _do_split "$fragments_dir"
}

# ---------- dispatch ----------

_step=0

run_step() {
    local label="$1"; shift
    _step=$(( _step + 1 ))
    loginfo ">>> Step ${_step}: $label"
    if "$@"; then
        loginfo "<<< Step ${_step} OK"
    else
        logerror "Step ${_step} ($label) failed — aborting."
        exit 1
    fi
}

if [[ -n "$DO_SECTION" ]]; then
    run_step "Split: $DO_SECTION" _split_section "$DO_SECTION"
fi

if $DO_ALL_SECTIONS; then
    read -r -a GENOME_SECTIONS <<< "${SKIMINDEX__GENOME_SECTIONS}"

    if [[ ${#GENOME_SECTIONS[@]} -eq 0 ]]; then
        logwarning "No genome sections found in config — nothing to split."
    else
        for section in "${GENOME_SECTIONS[@]}"; do
            run_step "Split: $section" _split_section "$section"
        done
    fi
fi

loginfo "All requested splits completed successfully."
