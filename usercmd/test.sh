#!/usr/bin/env bash
# ============================================================
# Say hello — one-line description shown in skimindex --help.
# ============================================================
set -euo pipefail

source "${SKIMINDEX_SCRIPTS_DIR}/__skimindex.sh"   # logging + config + stamping

loginfo "Hello, skimindex!"
