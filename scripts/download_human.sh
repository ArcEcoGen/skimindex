#!/usr/bin/env bash
# ============================================================
# download_human.sh
# Downloads the human reference genome (GBFF) from NCBI.
# Wrapper around download_refgenome.sh --section human.
#
# Usage:
#   download_human.sh [-h|--help] [OPTIONS]
#
# All options are forwarded to download_refgenome.sh --section human.
# Run download_refgenome.sh --help for the full option list.
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    sed -n '2,/^# =\+$/{ s/^# \{0,1\}//; /^=\+$/d; p }' "$0"
    exit 0
fi

# shellcheck source=__skimindex_config.sh
source "${SCRIPT_DIR}/__skimindex_config.sh"

exec "${SCRIPT_DIR}/download_refgenome.sh" --section human "$@"
