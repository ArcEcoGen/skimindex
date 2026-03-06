# ============================================================
# __skimindex_config.sh
# Reads a TOML config file and exports environment variables
# of the form:
#   SKIMINDEX__{SECTION}__{KEY}   (all uppercase)
#
# Also exports SKIMINDEX__GENOME_SECTIONS (space-separated list
# of section names that contain a 'taxon' key, excluding the
# reserved sections 'logging', 'local_directories', 'directories', 'genbank').
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
    # shellcheck source=__utils_functions.sh
    source "${_ski_dir}/__utils_functions.sh"
fi

_ski_cfg="${SKIMINDEX_CONFIG:-/config/skimindex.toml}"

if [[ ! -f "$_ski_cfg" ]]; then
    logwarning "__skimindex_config.sh: config file not found: $_ski_cfg"
    unset _ski_cfg
    return 0
fi

_ski_section=""
_ski_genome_sections=""   # space-separated list built during parsing

while IFS= read -r _ski_line; do
    # Strip inline comments, then trim leading/trailing whitespace
    _ski_line="${_ski_line%%#*}"
    _ski_line="${_ski_line#"${_ski_line%%[![:space:]]*}"}"
    _ski_line="${_ski_line%"${_ski_line##*[![:space:]]}"}"
    [[ -z "$_ski_line" ]] && continue

    # Section header: [section_name]
    if [[ "$_ski_line" =~ ^\[([a-zA-Z0-9_]+)\]$ ]]; then
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

        # Build variable name (uppercase section and key)
        _ski_var="SKIMINDEX__${_ski_section^^}__${_ski_key^^}"

        # Export only if not already set in the environment
        if [[ -z "${!_ski_var+x}" ]]; then
            export "${_ski_var}=${_ski_val}"
        fi

        # Track genome sections: any section with a 'taxon' key,
        # excluding the reserved sections 'logging', 'directories', 'genbank'
        if [[ "$_ski_key" == "taxon" &&
              "$_ski_section" != "logging" &&
              "$_ski_section" != "local_directories" &&
              "$_ski_section" != "directories" &&
              "$_ski_section" != "genbank" ]]; then
            # Append only if not already listed
            case " $_ski_genome_sections " in
                *" $_ski_section "*) ;;
                *) _ski_genome_sections="${_ski_genome_sections:+$_ski_genome_sections }${_ski_section}" ;;
            esac
        fi
    fi
done < "$_ski_cfg"

# Export genome sections list (honour pre-existing env var)
if [[ -z "${SKIMINDEX__GENOME_SECTIONS+x}" ]]; then
    export SKIMINDEX__GENOME_SECTIONS="$_ski_genome_sections"
fi

# Apply logging configuration from config file
if [[ -n "${SKIMINDEX__LOGGING__LEVEL:-}" ]]; then
    setloglevel "${SKIMINDEX__LOGGING__LEVEL}"
fi
if [[ -n "${SKIMINDEX__LOGGING__FILE:-}" ]]; then
    openlogfile "${SKIMINDEX__LOGGING__FILE}"
fi

unset _ski_cfg _ski_dir _ski_section _ski_line _ski_key _ski_val _ski_var _ski_genome_sections
