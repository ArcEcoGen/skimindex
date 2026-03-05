#!/usr/bin/env bash
# ============================================================
# download_plants.sh
# Downloads all complete Spermatophyta genome assemblies from
# NCBI (RefSeq + GenBank, latest version only) as a single
# bulk download, then produces one compressed GBFF file per
# genome:
#   {scientific_name}-{accession}.gbff.gz
#
# The ncbi_dataset archive unpacks to:
#   ncbi_dataset/data/{accession}/*.gbff
#   ncbi_dataset/data/assembly_data_report.jsonl
#
# Resume logic (checked in order):
#   1. ncbi_dataset/ present               → compress only
#      (per-accession .gbff.gz already present → skip that accession)
#   2. Otherwise                           → download_zip (resumes or
#      re-downloads if corrupt) + extract_zip + compress per accession
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=download_functions.sh
source "${SCRIPT_DIR}/download_functions.sh"

# ---------- configuration ----------
TAXON="Spermatophyta"
OUTPUT_DIR="${1:-/genbank/Plants}"
ZIP_FILE="${OUTPUT_DIR}/plants_complete.zip"
DATASET_DIR="${OUTPUT_DIR}/ncbi_dataset"
REPORT="${DATASET_DIR}/data/assembly_data_report.jsonl"

mkdir -p "$OUTPUT_DIR"

# ---------- stage 1: download + extract if needed ----------

if [[ ! -d "$DATASET_DIR" ]]; then
    echo "[1/2] Downloading complete $TAXON assemblies (latest versions)..."
    echo "      Destination : $ZIP_FILE"
    echo "      (This may take a long time and use tens of GB — be patient...)"
    download_zip "$ZIP_FILE" taxon "$TAXON" \
        --assembly-level complete \
        --assembly-version latest \
        --include gbff

    extract_zip "$ZIP_FILE" "$OUTPUT_DIR"
    rm -f "$ZIP_FILE"
    echo "[1/2] Download and extraction complete."
else
    echo "[RESUME] ncbi_dataset/ found — skipping download and extraction."
    rm -f "$ZIP_FILE" 2>/dev/null || true
fi

# ---------- stage 2: compress per accession ----------

echo "[2/2] Compressing per-accession GBFF files into $OUTPUT_DIR ..."

ACCESSIONS=()
while IFS= read -r -d '' acc_dir; do
    ACCESSIONS+=( "$(basename "$acc_dir")" )
done < <(find "${DATASET_DIR}/data" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)

TOTAL=${#ACCESSIONS[@]}
COUNT=0
ERRORS=0

for accession in "${ACCESSIONS[@]}"; do
    COUNT=$((COUNT + 1))
    printf "[%d/%d] %s\n" "$COUNT" "$TOTAL" "$accession"

    organism=$(organism_from_report "$REPORT" "$accession")
    [[ -z "$organism" ]] && organism="$accession"

    sname=$(safe_name "$organism")
    out_file="${OUTPUT_DIR}/${sname}-${accession}.gbff.gz"

    if ! consolidate_accession "${DATASET_DIR}/data/${accession}" "$organism" "$out_file"; then
        echo "  [ERROR] Failed to compress $accession" >&2
        ERRORS=$((ERRORS + 1))
    fi
done

# Remove ncbi_dataset/ only when everything succeeded
if [[ $ERRORS -eq 0 ]]; then
    echo ""
    echo "[cleanup] Removing $DATASET_DIR ..."
    rm -rf "$DATASET_DIR"
fi

# ---------- summary ----------
echo ""
echo "===== Summary ====="
echo "  Total    : $TOTAL"
echo "  Errors   : $ERRORS"
echo "  Output   : $OUTPUT_DIR"

if [[ $ERRORS -gt 0 ]]; then
    echo "[WARN] $ERRORS accession(s) failed — re-run to retry." >&2
    exit 1
fi
