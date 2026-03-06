#!/usr/bin/env bash
# ============================================================
# download_genbank.sh
# Download GenBank flat-file divisions and convert them to
# gzip-compressed FASTA, retaining NCBI taxonomy information.
#
# Usage:
#   download_genbank.sh [-h|--help] [--divisions "bct pln ..."] [genbank_dir]
#
# Arguments:
#   genbank_dir   Root directory for GenBank data.
#                 Default: $SKIMINDEX__DIRECTORIES__GENBANK or /genbank.
#
# Options:
#   --divisions "bct pln ..."
#                 Space-separated list of two-letter division codes to
#                 download.  Overrides skimindex.toml [genbank] divisions.
#
# Configuration (skimindex.toml):
#   [directories]
#   genbank = "/genbank"      # root directory (overridden by genbank_dir argument)
#
#   [genbank]
#   divisions = "bct pln"     # space-separated list of two-letter division codes
#                             # Full list: bct inv mam phg pln pri rod vrl vrt
#                             # Default: bct pln (bacteria + land plants/fungi)
#
# Output structure:
#   <genbank_dir>/
#   └── Release_<N>/
#       ├── fasta/
#       │   ├── bct/          # one sub-directory per division
#       │   │   └── gb*.fasta.gz
#       │   └── pln/
#       │       └── gb*.fasta.gz
#       └── taxonomy/
#           └── ncbi_taxonomy.tgz
#
# Description:
#   Drives the GenBank download process defined in /genbank/Makefile.
#   Each division consists of hundreds of large flat files; a single
#   `make` run may fail partway through due to network issues.
#   Rather than abort, this script re-runs make in a loop as long as
#   progress is being made (stamp file count increases between runs).
#
#   Progress detection:
#     - count increased    → at least one new file downloaded; retry.
#     - count unchanged    → no progress; stop to avoid an infinite loop.
#     - make returned 0    → all targets satisfied; stop normally.
#
#   At the end of a successful run the Release_<N>/tmp/ directory must
#   be empty: any leftover file there means a conversion step (obiconvert)
#   failed after its download succeeded.  Re-run this script to retry.
#
# ============================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DIVISIONS=""
GENBANK_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            sed -n '2,/^# =\+$/{ s/^# \{0,1\}//; /^=\+$/d; p }' "$0"
            exit 0
            ;;
        --divisions) DIVISIONS="$2"; shift 2 ;;
        -*)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
        *) GENBANK_DIR="$1"; shift ;;
    esac
done

# shellcheck source=__skimindex_config.sh
source "${SCRIPT_DIR}/__skimindex_config.sh"

GENBANK_DIR="${GENBANK_DIR:-${SKIMINDEX__DIRECTORIES__GENBANK:-/genbank}}"

# Build make arguments: pass GBDIV only when --divisions was given explicitly.
# The Makefile already reads SKIMINDEX__GENBANK__DIVISIONS from the environment.
MAKE_ARGS=()
[[ -n "$DIVISIONS" ]] && MAKE_ARGS+=(GBDIV="$DIVISIONS")

pushd "$GENBANK_DIR" > /dev/null

loginfo "Starting GenBank download loop in $GENBANK_DIR ..."

while true; do
    before=$(find . -name "*.stamp" 2>/dev/null | wc -l)

    make "${MAKE_ARGS[@]}"
    make_status=$?

    after=$(find . -name "*.stamp" 2>/dev/null | wc -l)

    if [ "$make_status" -eq 0 ]; then
        loginfo "All GenBank targets completed successfully."
        break
    fi

    if [ "$after" -le "$before" ]; then
        logerror "No progress in last iteration ($after stamp files). Stopping."
        exit 1
    fi

    loginfo "Progress: $((after - before)) new file(s) downloaded, retrying..."
done

# ---------- post-run sanity check: tmp must be empty ----------
leftover=$(find . -path "*/tmp/*" -type f 2>/dev/null | wc -l)
if [ "$leftover" -gt 0 ]; then
    logwarning "$leftover file(s) left in tmp/ — some conversions failed."
    logwarning "Re-run this script to retry the failed conversions."
    popd > /dev/null
    exit 1
fi

popd > /dev/null
