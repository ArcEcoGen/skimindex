#!/usr/bin/env bash
# ============================================================
# download_plants.sh
# Downloads Spermatophyta genome assemblies from NCBI.
# Wrapper around download_refgenome.sh --section plants.
#
# Usage:
#   download_plants.sh [-h|--help] [OPTIONS]
#
# All options are forwarded to download_refgenome.sh --section plants.
# Run download_refgenome.sh --help for the full option list.
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    sed -En '2,/^# =+$/{ s/^# ?//; /^=+$/d; p; }' "$0"
    exit 0
fi

# shellcheck source=__skimindex_config.sh
source "${SCRIPT_DIR}/__skimindex_config.sh"

exec "${SCRIPT_DIR}/download_refgenome.sh" --section plants "$@"
