# ============================================================
# download_functions.sh
# Shared helper functions for NCBI genome download scripts.
# Source this file — do NOT execute it directly.
#
# Requires: datasets, jq, pigz, unzip
# ============================================================

# Guard against direct execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "ERROR: download_functions.sh is a library — source it, do not run it." >&2
    exit 1
fi

# ---------- safe_name ------------------------------------------
# Convert an organism name to a filesystem-safe string.
# "Homo sapiens" → "Homo_sapiens"
safe_name() {
    echo "$1" | tr ' ' '_' | tr -cd '[:alnum:]_.-'
}

# ---------- organism_from_report -------------------------------
# Look up the organism name for an accession in the
# assembly_data_report.jsonl bundled inside ncbi_dataset/.
# Usage: organism_from_report <report_file> <accession>
organism_from_report() {
    local report="$1"
    local accession="$2"
    if [[ -f "$report" ]]; then
        jq -r --arg acc "$accession" \
            'select(.accession == $acc) | .organism.organismName // empty' \
            "$report" | head -1
    fi
}

# ---------- organism_from_api ----------------------------------
# Query the NCBI datasets API for the organism name of an accession.
# Usage: organism_from_api <accession>
organism_from_api() {
    local accession="$1"
    datasets summary genome accession "$accession" --as-json-lines \
    | jq -r '.organism.organism_name // empty' \
    | head -1
}

# ---------- gbff_compress --------------------------------------
# Concatenate all .gbff files in <src_dir> (recursively, sorted)
# and compress them into <out_file> using pigz.
# Usage: gbff_compress <src_dir> <out_file>
gbff_compress() {
    local src_dir="$1"
    local out_file="$2"
    find "$src_dir" -name "*.gbff" | sort \
    | xargs cat \
    | pigz -9 -c > "$out_file"
}

# ---------- extract_zip ----------------------------------------
# Extract a ZIP archive into a destination directory.
# Usage: extract_zip <zip_file> <dest_dir>
extract_zip() {
    local zip_file="$1"
    local dest_dir="$2"
    echo "[extract] $zip_file → $dest_dir"
    unzip -q "$zip_file" -d "$dest_dir"
}

# ---------- consolidate_accession ------------------------------
# Compress all .gbff files for one accession into a single .gbff.gz.
# Skips silently if the output file already exists.
# Usage: consolidate_accession <acc_dir> <organism> <out_file>
# Returns: 0 on success or skip, non-zero on error
consolidate_accession() {
    local acc_dir="$1"
    local organism="$2"
    local out_file="$3"
    local size

    if [[ -f "$out_file" ]]; then
        size=$(du -sh "$out_file" | cut -f1)
        echo "  [SKIP] $(basename "$out_file")  [$size]"
        return 0
    fi

    echo "  [compress] $organism → $(basename "$out_file")"
    gbff_compress "$acc_dir" "$out_file"

    size=$(du -sh "$out_file" | cut -f1)
    echo "  [OK] $(basename "$out_file")  [$size]"
}
