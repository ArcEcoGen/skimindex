# ============================================================
# __skimindex_config.sh
# Reads a TOML config file and exports environment variables
# of the form:
#   SKIMINDEX__{SECTION}__{KEY}   (all uppercase)
#
# Also exports:
#   SKIMINDEX__GENOME_SECTIONS — all genome sections: taxon OR (taxid AND division),
#                                excluding 'logging', 'local_directories', 'genbank'.
#   SKIMINDEX__TAXON_SECTIONS  — subset of GENOME_SECTIONS with a 'taxon' key only
#                                (downloadable via NCBI datasets).
#
# Container-side directory paths are derived automatically from
# [local_directories]: each key k is mounted at /k inside the
# container, so SKIMINDEX__DIRECTORIES__{K^^} is set to "/<k>".
# The [directories] section in the TOML is therefore not needed
# and is ignored during parsing.
#
# Pre-existing environment variables take priority: a variable
# already set in the environment is never overwritten.
#
# Config file location: /config/skimindex.toml by default.
# Override with the SKIMINDEX_CONFIG environment variable.
#
# Source this file — do NOT execute it directly.
# ============================================================

# Guard against direct execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "ERROR: __skimindex_config.sh is a library — source it, do not run it." >&2
    exit 1
fi

# Resolve this file's own directory (works even when sourced)
_ski_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load shared utilities if not already loaded
if [[ "$(type -t loginfo)" != "function" ]]; then
    source "${_ski_dir}/__utils_functions.sh"
fi

_ski_cfg="${SKIMINDEX_CONFIG:-/config/skimindex.toml}"
_ski_section=""
_ski_genome_sections=""   # all genome sections: taxon OR (taxid AND division)
_ski_taxon_sections=""    # only sections downloadable via datasets (taxon key)
_ski_has_taxon=0          # flags for current section
_ski_has_taxid=0
_ski_has_division=0

# _ski_append <list_var> <section>
_ski_append() {
    case " ${!1} " in
        *" $2 "*) ;;
        *) printf -v "$1" '%s' "${!1:+${!1} }$2" ;;
    esac
}

# Evaluate completed section and append to the relevant lists:
#   GENOME_SECTIONS : taxon  OR  (taxid AND division)
#   TAXON_SECTIONS  : taxon only
_ski_maybe_add_genome_section() {
    [[ -z "$_ski_section" ]] && return
    [[ "$_ski_section" == "logging"  ]] && return
    [[ "$_ski_section" == "genbank"  ]] && return
    if (( _ski_has_taxon )); then
        _ski_append _ski_genome_sections "$_ski_section"
        _ski_append _ski_taxon_sections  "$_ski_section"
    elif (( _ski_has_taxid && _ski_has_division )); then
        _ski_append _ski_genome_sections "$_ski_section"
    fi
    _ski_has_taxon=0
    _ski_has_taxid=0
    _ski_has_division=0
}

# Parse config file if present
if [[ -f "$_ski_cfg" ]]; then

    while IFS= read -r _ski_line; do
        # Strip inline comments, then trim leading/trailing whitespace
        _ski_line="${_ski_line%%#*}"
        _ski_line="${_ski_line#"${_ski_line%%[![:space:]]*}"}"
        _ski_line="${_ski_line%"${_ski_line##*[![:space:]]}"}"
        [[ -z "$_ski_line" ]] && continue

        # Section header: [section_name]
        if [[ "$_ski_line" =~ ^\[([a-zA-Z0-9_]+)\]$ ]]; then
            _ski_maybe_add_genome_section   # evaluate completed section
            _ski_section="${BASH_REMATCH[1]}"
            continue
        fi

        # Key-value pair: key = "value"  or  key = value
        if [[ -n "$_ski_section" && "$_ski_line" =~ ^([a-zA-Z0-9_]+)[[:space:]]*=[[:space:]]*(.+)$ ]]; then
            _ski_key="${BASH_REMATCH[1]}"
            _ski_val="${BASH_REMATCH[2]}"

            # Strip surrounding double quotes if present
            _ski_val="${_ski_val#\"}"
            _ski_val="${_ski_val%\"}"

            # [local_directories]: derive container-side path SKIMINDEX__DIRECTORIES__{KEY}="/<key>"
            if [[ "$_ski_section" == "local_directories" ]]; then
                _ski_dir_var="SKIMINDEX__DIRECTORIES__${_ski_key^^}"
                [[ -z "${!_ski_dir_var+x}" ]] && export "${_ski_dir_var}=/${_ski_key}"
                continue
            fi

            # Skip the now-redundant [directories] section
            [[ "$_ski_section" == "directories" ]] && continue

            # Build variable name (uppercase section and key)
            _ski_var="SKIMINDEX__${_ski_section^^}__${_ski_key^^}"

            # Export only if not already set in the environment
            if [[ -z "${!_ski_var+x}" ]]; then
                export "${_ski_var}=${_ski_val}"
            fi

            # Track keys relevant to genome section detection
            case "$_ski_key" in
                taxon)    _ski_has_taxon=1    ;;
                taxid)    _ski_has_taxid=1    ;;
                divisions) _ski_has_division=1 ;;
            esac
        fi
    done < "$_ski_cfg"

    _ski_maybe_add_genome_section   # evaluate last section

else
    if [[ -n "${SKIMINDEX_CONFIG:-}" ]]; then
        logwarning "__skimindex_config.sh: config file not found: $_ski_cfg (set by SKIMINDEX_CONFIG)"
    else
        logwarning "__skimindex_config.sh: config file not found: $_ski_cfg (default path)"
    fi
fi

# Export section lists (honour pre-existing env vars)
if [[ -z "${SKIMINDEX__GENOME_SECTIONS+x}" ]]; then
    export SKIMINDEX__GENOME_SECTIONS="$_ski_genome_sections"
fi
if [[ -z "${SKIMINDEX__TAXON_SECTIONS+x}" ]]; then
    export SKIMINDEX__TAXON_SECTIONS="$_ski_taxon_sections"
fi

# Apply logging configuration from config file
if [[ -n "${SKIMINDEX__LOGGING__LEVEL:-}" ]]; then
    setloglevel "${SKIMINDEX__LOGGING__LEVEL}"
fi


if [[ -n "${SKIMINDEX__LOGGING__FILE:-}" ]]; then
    openlogfile "${SKIMINDEX__LOGGING__FILE}" \
                "${SKIMINDEX__LOGGING__MIRROR:-false}" \
                "${SKIMINDEX__LOGGING__EVERYTHING:-false}"
fi


unset _ski_cfg _ski_dir _ski_section _ski_line _ski_key _ski_val _ski_var \
      _ski_dir_var _ski_genome_sections _ski_taxon_sections \
      _ski_has_taxon _ski_has_taxid _ski_has_division
unset -f _ski_maybe_add_genome_section _ski_append

# =============================================================
# Built-in defaults — always applied, for any variable not set
# by the config file or the environment.
# Priority: environment > config file > these defaults.
# =============================================================
_ski_default() {
    local var="$1" val="$2"
    [[ -z "${!var+x}" ]] && export "${var}=${val}" ||true
}

_ski_default SKIMINDEX__GENOME_SECTIONS            ""
_ski_default SKIMINDEX__TAXON_SECTIONS             ""
_ski_default SKIMINDEX__DIRECTORIES__GENBANK       "/genbank"
_ski_default SKIMINDEX__DIRECTORIES__PROCESSED_DATA "/processed_data"
_ski_default SKIMINDEX__GENBANK__DIVISIONS         "bct pln"
_ski_default SKIMINDEX__DECONTAMINATION__KMER_SIZE "29"
_ski_default SKIMINDEX__DECONTAMINATION__FRG_SIZE  "200"
_ski_default SKIMINDEX__DECONTAMINATION__BATCHES   "20"

unset -f _ski_default
