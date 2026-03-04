#!/usr/bin/env bash
# ============================================================
# download_human.sh
# Downloads the human reference genome (GBFF) from NCBI and
# consolidates all chromosomes into a single compressed file:
#   {scientific_name}-{accession}.gbff.gz
#
# Resume logic (checked in order):
#   1. Final .gbff.gz exists           → done, nothing to do
#   2. ncbi_dataset/ present           → consolidate + cleanup
#   3. ZIP present                     → extract + consolidate + cleanup
#   4. Nothing                         → full download pipeline
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=download_functions.sh
source "${SCRIPT_DIR}/download_functions.sh"

# ---------- configuration ----------
TAXON="human"
OUTPUT_DIR="${1:-/genbank/Human}"
ZIP_FILE="${OUTPUT_DIR}/human_reference.zip"
DATASET_DIR="${OUTPUT_DIR}/ncbi_dataset"

mkdir -p "$OUTPUT_DIR"

# ---------- resolve accession ----------
echo "[INFO] Looking up reference genome accession for '$TAXON'..."
ACCESSION=$(
    datasets summary genome taxon "$TAXON" \
        --reference \
        --assembly-source refseq \
        --as-json-lines \
    | jq -r '
        select(
            .assembly_info.assembly_status == "current" and
            .assembly_info.refseq_category  == "reference genome"
        )
        | .accession
    ' \
    | head -1
)

if [[ -z "$ACCESSION" ]]; then
    echo "[ERROR] No accession found for '$TAXON'." >&2
    exit 1
fi

ORGANISM=$(organism_from_api "$ACCESSION")
SNAME=$(safe_name "$ORGANISM")
FINAL_FILE="${OUTPUT_DIR}/${SNAME}-${ACCESSION}.gbff.gz"

echo "[INFO] Accession : $ACCESSION"
echo "[INFO] Organism  : $ORGANISM"
echo "[INFO] Target    : $FINAL_FILE"

# ---------- stage 1: already done ----------
if [[ -f "$FINAL_FILE" ]]; then
    SIZE=$(du -sh "$FINAL_FILE" | cut -f1)
    echo "[SKIP] $FINAL_FILE already exists [$SIZE] — nothing to do."
    exit 0
fi

# ---------- stage 2: ncbi_dataset/ present ----------
if [[ -d "$DATASET_DIR" ]]; then
    echo "[RESUME] ncbi_dataset/ found — consolidating without re-downloading."
    consolidate_accession "${DATASET_DIR}/data/${ACCESSION}" "$ORGANISM" "$FINAL_FILE"
    rm -rf "$DATASET_DIR"
    exit 0
fi

# ---------- stage 3: zip present ----------
if [[ -f "$ZIP_FILE" ]]; then
    echo "[RESUME] ZIP found — extracting..."
    extract_zip "$ZIP_FILE" "$OUTPUT_DIR"
    rm -f "$ZIP_FILE"
    consolidate_accession "${DATASET_DIR}/data/${ACCESSION}" "$ORGANISM" "$FINAL_FILE"
    rm -rf "$DATASET_DIR"
    exit 0
fi

# ---------- stage 4: full download ----------
echo "[1/3] Fetching metadata for $ACCESSION..."
datasets summary genome accession "$ACCESSION" --as-json-lines \
| jq -r '"    Name      : " + .assembly_info.assembly_name,
          "    Organism  : " + .organism.organism_name,
          "    Status    : " + .assembly_info.assembly_status,
          "    Released  : " + .assembly_info.release_date'

echo "[2/3] Downloading GBFF for $ACCESSION..."
echo "      Destination : $ZIP_FILE"
echo "      (This file is large ~1.5 GB, please be patient...)"
datasets download genome accession "$ACCESSION" \
    --include gbff \
    --filename "$ZIP_FILE"

echo "[3/3] Extracting and consolidating..."
extract_zip "$ZIP_FILE" "$OUTPUT_DIR"
rm -f "$ZIP_FILE"
consolidate_accession "${DATASET_DIR}/data/${ACCESSION}" "$ORGANISM" "$FINAL_FILE"
rm -rf "$DATASET_DIR"
