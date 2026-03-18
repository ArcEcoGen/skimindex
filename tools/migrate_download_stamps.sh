#!/usr/bin/env bash
# migrate_download_stamps.sh — Convert old local download stamp files to the new centralised layout.
#
# Covers two sub-systems written by the previous Python _download.py:
#
#   GenBank stamps
#     Old: {GENBANK}/Release_{N}/stamp/{gb_file}.stamp
#     New: {STAMP_ROOT}/{GENBANK}/Release_{N}/fasta/{div}/{gb_file→.fasta.gz}.stamp
#     (div = characters 3-5 of the gb_file, e.g. "gbpln001.seq.gz" → div="pln")
#
#   Reference-genome stamps
#     Old: {GENBANK}/{section_dir}/.stamps/{accession}.{step}.stamp
#     New: {STAMP_ROOT}/{GENBANK}/{section_dir}/_work/{accession}/{step}.stamp
#     (step ∈ download, extract, compress)
#
# The mtime of each old stamp is preserved so that freshness checks remain valid.
#
# Usage:
#   migrate_download_stamps.sh [--genbank DIR] [--stamp-root DIR] [--dry-run]
#
# Defaults:
#   --genbank      /genbank   (or $SKIMINDEX__DIRECTORIES__GENBANK)
#   --stamp-root   /stamp     (or $SKIMINDEX_STAMP_DIR)

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
GENBANK="${SKIMINDEX__DIRECTORIES__GENBANK:-/genbank}"
STAMP_ROOT="${SKIMINDEX_STAMP_DIR:-/stamp}"
DRY_RUN=0

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --genbank)     GENBANK="$2";    shift 2 ;;
        --stamp-root)  STAMP_ROOT="$2"; shift 2 ;;
        --dry-run)     DRY_RUN=1;       shift   ;;
        -h|--help)
            sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() { echo "[migrate_download_stamps] $*"; }
dry() { echo "[DRY-RUN]                 $*"; }

install_stamp() {
    # install_stamp OLD NEW
    local old="$1" new="$2"
    if [[ -e "$new" ]]; then
        log "SKIP  already exists: $new"
        return
    fi
    log "MIGRATE  $old"
    log "      →  $new"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        dry "mkdir -p $(dirname "$new")"
        dry "touch -r $old $new"
        return
    fi
    mkdir -p "$(dirname "$new")"
    touch "$new"
    touch -r "$old" "$new"
}

# ---------------------------------------------------------------------------
# GenBank stamps
#   Old: {GENBANK}/Release_{N}/stamp/{gb_file}.stamp
#   New: {STAMP_ROOT}/{GENBANK}/Release_{N}/fasta/{div}/{gb_file→.fasta.gz}.stamp
# ---------------------------------------------------------------------------
migrate_genbank() {
    local old_stamp="$1"
    # Extract Release directory and gb_file from path.
    # old_stamp = .../Release_{N}/stamp/{gb_file}.stamp
    local rel="${old_stamp#${GENBANK}/}"          # Release_{N}/stamp/{gb_file}.stamp
    local release_dir="${rel%%/stamp/*}"           # Release_{N}
    local gb_stamp="${rel##*/stamp/}"              # {gb_file}.stamp
    local gb_file="${gb_stamp%.stamp}"             # {gb_file}  e.g. gbpln001.seq.gz

    # Derive division: gb_file starts with "gb" then 3-char div code.
    local div="${gb_file:2:3}"                     # e.g. "pln"

    # Convert filename: replace .seq.gz with .fasta.gz
    local fasta_file="${gb_file/.seq.gz/.fasta.gz}"

    # Strip leading '/' from GENBANK for the mirror path.
    local gb_rel="${GENBANK#/}"
    local new_stamp="${STAMP_ROOT}/${gb_rel}/${release_dir}/fasta/${div}/${fasta_file}.stamp"

    install_stamp "$old_stamp" "$new_stamp"
}

# ---------------------------------------------------------------------------
# Reference-genome stamps
#   Old: {GENBANK}/{section_dir}/.stamps/{accession}.{step}.stamp
#   New: {STAMP_ROOT}/{GENBANK}/{section_dir}/_work/{accession}/{step}.stamp
# ---------------------------------------------------------------------------
migrate_refgenome() {
    local old_stamp="$1"
    # old_stamp = {GENBANK}/{section_dir}/.stamps/{accession}.{step}.stamp
    local rel="${old_stamp#${GENBANK}/}"           # {section_dir}/.stamps/{accession}.{step}.stamp
    local section_dir="${rel%%/.stamps/*}"         # {section_dir}
    local acc_step="${rel##*/.stamps/}"            # {accession}.{step}.stamp
    local acc_step_bare="${acc_step%.stamp}"       # {accession}.{step}

    # Split on last '.' to separate accession from step.
    local step="${acc_step_bare##*.}"              # download | extract | compress
    local accession="${acc_step_bare%.*}"          # e.g. GCF_000001405.40

    # Strip leading '/' from GENBANK for the mirror path.
    local gb_rel="${GENBANK#/}"
    local new_stamp="${STAMP_ROOT}/${gb_rel}/${section_dir}/_work/${accession}/${step}.stamp"

    install_stamp "$old_stamp" "$new_stamp"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
log "genbank    : $GENBANK"
log "stamp_root : $STAMP_ROOT"
[[ "$DRY_RUN" -eq 1 ]] && log "Mode       : DRY-RUN (no files written)"

count_gb=0
count_rg=0

# GenBank stamps: Release_*/stamp/*.stamp
while IFS= read -r -d '' old; do
    migrate_genbank "$old"
    (( count_gb++ )) || true
done < <(find "$GENBANK" -path "*/Release_*/stamp/*.stamp" -print0 2>/dev/null)

# Reference-genome stamps: {section_dir}/.stamps/*.stamp
while IFS= read -r -d '' old; do
    migrate_refgenome "$old"
    (( count_rg++ )) || true
done < <(find "$GENBANK" -path "*/.stamps/*.stamp" -print0 2>/dev/null)

log "Done — ${count_gb} GenBank stamp(s), ${count_rg} refgenome stamp(s) processed."
