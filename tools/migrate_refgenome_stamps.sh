#!/usr/bin/env bash
# migrate_refgenome_stamps.sh — Move refgenome compress stamps to new layout.
#
# After migrate_download_stamps.sh, compress stamps sit at:
#   {STAMP_ROOT}/{GENBANK}/{section_dir}/.work/{accession}/compress.stamp
#
# The new code stamps the actual output file, so stamps must be at:
#   {STAMP_ROOT}/{GENBANK}/{section_dir}/{safe_name}-{accession}.gbff.gz.stamp
#
# Strategy: for each compress.stamp found under .work/, find the matching
# *-{accession}.gbff.gz in the section directory, then mv the stamp.
#
# Usage:
#   migrate_refgenome_stamps.sh [--genbank DIR] [--stamp-root DIR] [--dry-run]
#
# Defaults:
#   --genbank      /genbank   (or $SKIMINDEX__DIRECTORIES__GENBANK)
#   --stamp-root   /stamp     (or $SKIMINDEX_STAMP_DIR)

set -euo pipefail

GENBANK="${SKIMINDEX__DIRECTORIES__GENBANK:-/genbank}"
STAMP_ROOT="${SKIMINDEX_STAMP_DIR:-/stamp}"
DRY_RUN=0

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

log() { echo "[migrate_refgenome_stamps] $*"; }
dry() { echo "[DRY-RUN]                  $*"; }

log "genbank    : $GENBANK"
log "stamp_root : $STAMP_ROOT"
[[ "$DRY_RUN" -eq 1 ]] && log "Mode       : DRY-RUN (no files written)"

GB_REL="${GENBANK#/}"
count_ok=0
count_skip=0
count_missing=0

# Find all compress stamps under .work/ in STAMP_ROOT
while IFS= read -r -d '' old_stamp; do
    # old_stamp = {STAMP_ROOT}/{GB_REL}/{section_dir}/.work/{accession}/compress.stamp
    rel="${old_stamp#${STAMP_ROOT}/${GB_REL}/}"   # {section_dir}/_work/{accession}/compress.stamp
    section_dir="${rel%%/_work/*}"                 # {section_dir}
    accession="${rel##*/_work/}"
    accession="${accession%/compress.stamp}"       # {accession}

    # Find matching .gbff.gz in the real genbank directory
    gz_file=$(find "${GENBANK}/${section_dir}" -maxdepth 1 -name "*-${accession}.gbff.gz" 2>/dev/null | head -1)

    if [[ -z "$gz_file" ]]; then
        log "SKIP  no .gbff.gz found for ${accession} in ${GENBANK}/${section_dir}"
        (( count_missing++ )) || true
        continue
    fi

    gz_rel="${gz_file#/}"
    new_stamp="${STAMP_ROOT}/${gz_rel}.stamp"

    if [[ -e "$new_stamp" ]]; then
        log "SKIP  already exists: ${new_stamp}"
        (( count_skip++ )) || true
        continue
    fi

    log "MOVE  ${old_stamp}"
    log "   →  ${new_stamp}"

    if [[ "$DRY_RUN" -eq 1 ]]; then
        dry "mv $old_stamp $new_stamp"
        (( count_ok++ )) || true
        continue
    fi

    mv "$old_stamp" "$new_stamp"
    (( count_ok++ )) || true

done < <(find "${STAMP_ROOT}/${GB_REL}" -path "*/_work/*/compress.stamp" -print0 2>/dev/null)

log "Done — ${count_ok} stamp(s) moved, ${count_skip} already present, ${count_missing} accession(s) without .gbff.gz"
