#!/usr/bin/env bash
# ============================================================
# download_references.sh
# Master script that runs the full reference data pipeline:
#   1. GenBank divisions  (via /genbank/Makefile loop)
#   2. Human reference genome
#   3. Spermatophyta complete assemblies
#
# Each step is independent: a failure stops the pipeline but
# already-completed steps are skipped on re-run (resume logic
# is handled by each individual script).
#
# Usage:
#   download_references.sh [genbank_dir] [human_dir] [plants_dir]
#
# Defaults:
#   genbank_dir → /genbank
#   human_dir   → /genbank/Human
#   plants_dir  → /genbank/Plants
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GENBANK_DIR="${1:-/genbank}"
HUMAN_DIR="${2:-/genbank/Human}"
PLANTS_DIR="${3:-/genbank/Plants}"

run_step() {
    local step="$1"
    local label="$2"
    shift 2

    echo ""
    echo "╔══════════════════════════════════════════════════════╗"
    printf  "║  Step %s: %-44s║\n" "$step" "$label"
    echo "╚══════════════════════════════════════════════════════╝"

    if "$@"; then
        echo "[ Step $step OK ]"
    else
        echo "[ERROR] Step $step ($label) failed — aborting." >&2
        exit 1
    fi
}

run_step 1 "GenBank divisions" \
    "${SCRIPT_DIR}/download_genbank.sh" "$GENBANK_DIR"

run_step 2 "Human reference genome" \
    "${SCRIPT_DIR}/download_human.sh" "$HUMAN_DIR"

run_step 3 "Spermatophyta complete assemblies" \
    "${SCRIPT_DIR}/download_plants.sh" "$PLANTS_DIR"

echo ""
echo "All reference data downloaded successfully."
