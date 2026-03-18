#!/usr/bin/env bash
# migrate_stamps.sh — Convert old local stamp files to the new centralised layout.
#
# Old layout (written by the previous _split.py):
#   {PROCESSED_DATA}/{section_dir}/stamp/{key}.stamp
#
# New layout (written by skimindex.stamp):
#   {STAMP_ROOT}/{PROCESSED_DATA}/{section_dir}/{key}/parts.stamp
#
# The mtime of each old stamp is preserved so that freshness checks remain valid.
#
# Usage:
#   migrate_stamps.sh [--processed-data DIR] [--stamp-root DIR] [--dry-run]
#
# Defaults:
#   --processed-data   /processed_data   (or $SKIMINDEX_PROCESSED_DATA)
#   --stamp-root       /stamp            (or $SKIMINDEX_STAMP_DIR)

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults (overridable via env or flags)
# ---------------------------------------------------------------------------
PROCESSED_DATA="${SKIMINDEX_PROCESSED_DATA:-/processed_data}"
STAMP_ROOT="${SKIMINDEX_STAMP_DIR:-/stamp}"
DRY_RUN=0

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --processed-data)  PROCESSED_DATA="$2"; shift 2 ;;
        --stamp-root)      STAMP_ROOT="$2";      shift 2 ;;
        --dry-run)         DRY_RUN=1;             shift   ;;
        -h|--help)
            sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { echo "[migrate_stamps] $*"; }
dry()  { echo "[DRY-RUN]        $*"; }

migrate_one() {
    local old_stamp="$1"
    # old_stamp = {PROCESSED_DATA}/{section_dir}/stamp/{key}.stamp
    # Strip PROCESSED_DATA prefix and /stamp/{key}.stamp suffix to get section_dir.
    local rel="${old_stamp#${PROCESSED_DATA}/}"   # {section_dir}/stamp/{key}.stamp
    local section_dir="${rel%%/stamp/*}"           # {section_dir}
    local key_stamp="${rel##*/stamp/}"             # {key}.stamp
    local key="${key_stamp%.stamp}"                # {key}

    # New stamp path: {STAMP_ROOT}/{PROCESSED_DATA}/{section_dir}/{key}/parts.stamp
    # Strip leading '/' from PROCESSED_DATA for the mirror path.
    local pd_rel="${PROCESSED_DATA#/}"
    local new_stamp="${STAMP_ROOT}/${pd_rel}/${section_dir}/${key}/parts.stamp"

    if [[ -e "$new_stamp" ]]; then
        log "SKIP  already exists: $new_stamp"
        return
    fi

    log "MIGRATE  $old_stamp"
    log "      →  $new_stamp"

    if [[ "$DRY_RUN" -eq 1 ]]; then
        dry "mkdir -p $(dirname "$new_stamp")"
        dry "touch -r $old_stamp $new_stamp"
        return
    fi

    mkdir -p "$(dirname "$new_stamp")"
    # Create new stamp, then copy mtime from old stamp.
    touch "$new_stamp"
    touch -r "$old_stamp" "$new_stamp"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
log "processed_data : $PROCESSED_DATA"
log "stamp_root     : $STAMP_ROOT"
[[ "$DRY_RUN" -eq 1 ]] && log "Mode           : DRY-RUN (no files written)"

count=0
while IFS= read -r -d '' old_stamp; do
    migrate_one "$old_stamp"
    (( count++ )) || true
done < <(find "$PROCESSED_DATA" -path "*/stamp/*.stamp" -print0 2>/dev/null)

if [[ "$count" -eq 0 ]]; then
    log "No old stamp files found under $PROCESSED_DATA"
else
    log "Done — $count stamp(s) processed."
fi
