# ============================================================
# download_functions.sh
# Shared helper functions for NCBI genome download scripts.
# Source this file — do NOT execute it directly.
#
# Requires: datasets, jq, pigz, python3, unzip
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

# ---------- check_zip ------------------------------------------
# Quickly verify a ZIP archive by checking for the
# End-of-Central-Directory signature (seeks to end of file only —
# no full-file read, fast even for large archives).
# Returns 0 if the ZIP looks valid, 1 if truncated or corrupt.
# Usage: check_zip <zip_file>
check_zip() {
    local zip_file="$1"
    [[ -f "$zip_file" ]] || return 1
    python3 -c "
import sys, zipfile
sys.exit(0 if zipfile.is_zipfile(sys.argv[1]) else 1)
" "$zip_file"
}

# ---------- download_zip ---------------------------------------
# Ensure a ZIP archive is present and valid, downloading it via
# `datasets download genome` if necessary.
#
# If a ZIP already exists:
#   - valid   → skip the download (resume-friendly)
#   - corrupt → warn, delete, then re-download
# After every download the integrity is verified; on failure the
# partial file is deleted and the function returns 1.
#
# Usage: download_zip <zip_file> <datasets_genome_args...>
# The extra arguments are forwarded verbatim to:
#   datasets download genome <datasets_genome_args...> --filename <zip_file>
# Examples:
#   download_zip plants.zip taxon Spermatophyta --assembly-level complete --include gbff
#   download_zip human.zip  accession GCF_000001405.40 --include gbff
download_zip() {
    local zip_file="$1"
    shift   # remaining args forwarded to datasets

    if [[ -f "$zip_file" ]]; then
        echo "[check] Verifying existing ZIP integrity..."
        if check_zip "$zip_file"; then
            echo "[RESUME] ZIP valid — skipping download."
            return 0
        else
            echo "[WARN] ZIP is corrupt or truncated — discarding and re-downloading."
            rm -f "$zip_file"
        fi
    fi

    datasets download genome "$@" --filename "$zip_file"

    echo "[check] Verifying downloaded ZIP integrity..."
    if ! check_zip "$zip_file"; then
        echo "[ERROR] Downloaded ZIP failed integrity check — removing." >&2
        rm -f "$zip_file"
        return 1
    fi
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

# ---------- zip_gbff_compress ----------------------------------
# Stream all .gbff files contained in a ZIP archive through pigz,
# producing a single compressed .gbff.gz without writing any
# intermediate files to disk.  Files are concatenated in sorted
# order (consistent with gbff_compress).
# Usage: zip_gbff_compress <zip_file> <out_file>
zip_gbff_compress() {
    local zip_file="$1"
    local out_file="$2"
    echo "[stream] $zip_file → $out_file"
    python3 - "$zip_file" <<'PYEOF' | pigz -9 -c > "$out_file"
import sys, zipfile, shutil

CHUNK = 1 << 20  # 1 MiB — avoids loading whole chromosomes into RAM

with zipfile.ZipFile(sys.argv[1]) as zf:
    for name in sorted(n for n in zf.namelist() if n.endswith('.gbff')):
        with zf.open(name) as f:
            shutil.copyfileobj(f, sys.stdout.buffer, CHUNK)
PYEOF
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
