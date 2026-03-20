# ============================================================
# __skimindex_config.sh
# Reads a TOML config file and exports environment variables
# of the form:
#   SKIMINDEX__{SECTION}__{KEY}   (all uppercase)
#
# Delegates all TOML parsing to the Python skimindex.config module
# (python3 -m skimindex.config), which handles the full TOML syntax
# including dotted sections, arrays, and inline tables.
#
# Also exports (computed by the Python module):
#   SKIMINDEX__REF_TAXA    — datasets with source 'ncbi' or 'genbank'
#   SKIMINDEX__REF_GENOMES — datasets with source 'ncbi' only
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

# Guard against multiple inclusion
[[ -n "${_SKIMINDEX_CONFIG_LOADED:-}" ]] && return 0

# Require __skimindex.sh as entry point (_skimindex_sh_dir must be set)
if [[ -z "${_skimindex_sh_dir:-}" ]]; then
    echo "ERROR: source __skimindex.sh instead of __skimindex_config.sh directly." >&2
    return 1
fi

_SKIMINDEX_CONFIG_LOADED=1

# Resolve config file path:
#   1. SKIMINDEX_CONFIG env var (explicit override)
#   2. /config/skimindex.toml (container default)
#   3. $project_root/config/skimindex.toml (dev, relative to scripts/)
if [[ -n "${SKIMINDEX_CONFIG:-}" ]]; then
    _ski_cfg="$SKIMINDEX_CONFIG"
elif [[ -f "/config/skimindex.toml" ]]; then
    _ski_cfg="/config/skimindex.toml"
else
    _ski_cfg="${_skimindex_sh_dir}/../config/skimindex.toml"
fi

if [[ -f "$_ski_cfg" ]]; then
    # Delegate all parsing to the Python module.
    # python3 -m skimindex.config prints "export VAR=value" lines,
    # skipping variables already set in the environment.
    # SKIMINDEX_CONFIG is passed explicitly so the Python module finds the
    # same file regardless of its own DEFAULT_CONFIG path.
    if ! _ski_env="$(SKIMINDEX_CONFIG="$_ski_cfg" python3 -m skimindex.config 2>&1)"; then
        logerror "__skimindex_config.sh: failed to parse config: $_ski_cfg"
        logerror "$_ski_env"
    else
        eval "$_ski_env"
    fi
    unset _ski_env
else
    if [[ -n "${SKIMINDEX_CONFIG:-}" ]]; then
        logwarning "__skimindex_config.sh: config file not found: $_ski_cfg (set by SKIMINDEX_CONFIG)"
    else
        logwarning "__skimindex_config.sh: config file not found: $_ski_cfg (default path)"
    fi
fi

# Apply logging configuration now that env vars are set
if [[ -n "${SKIMINDEX__LOGGING__LEVEL:-}" ]]; then
    setloglevel "${SKIMINDEX__LOGGING__LEVEL}"
fi

if [[ -n "${SKIMINDEX__LOGGING__FILE:-}" ]]; then
    openlogfile "${SKIMINDEX__LOGGING__FILE}" \
                "${SKIMINDEX__LOGGING__MIRROR:-false}" \
                "${SKIMINDEX__LOGGING__EVERYTHING:-false}"
fi

# =============================================================
# Built-in defaults — always applied for any variable not set
# by the config file or the environment.
# Priority: environment > config file > these defaults.
# =============================================================
_ski_default() {
    local var="$1" val="$2"
    [[ -z "${!var+x}" ]] && export "${var}=${val}" || true
}

_ski_default SKIMINDEX__REF_TAXA    ""
_ski_default SKIMINDEX__REF_GENOMES ""

unset -f _ski_default
unset _ski_cfg
