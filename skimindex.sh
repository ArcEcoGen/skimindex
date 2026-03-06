#!/usr/bin/env bash
# =============================================================================
# skimindex — pipeline entry point
#
# Usage:
#   skimindex [--project-dir DIR] <subcommand> [subcommand-options]
#
# Global options:
#   --project-dir DIR    Project root directory (default: current working
#                        directory).  All relative paths in the configuration
#                        are resolved from this directory.
#   -h, --help           Show this help and exit.
#
# Subcommands:
#   init                     Initialise a new project directory and download the default config.
#   shell                    Start an interactive shell inside the container.
#   download_genbank         Download GenBank flat-file divisions and convert them to
#   download_human           Downloads the human reference genome (GBFF) from NCBI.
#   download_plants          Downloads Spermatophyta genome assemblies from NCBI.
#   download_references      Master script for the reference data pipeline.
#   download_refgenome       Downloads genome assemblies from NCBI for a given taxon and
#   split_human              
#
# Configuration:
#   <project-dir>/config/skimindex.toml
#       Pipeline configuration.  The [local_directories] section maps each
#       key k to a host path that is bind-mounted to /k inside the container.
#
# Container runtime:
#   Auto-detected in priority order: apptainer > docker > podman.
#   Apptainer uses the local SIF image:
#       <project-dir>/images/@@IMAGE_NAME@@-@@IMAGE_TAG@@.sif
#   Docker / Podman pull the image from the registry on first use:
#       @@FULL_IMAGE@@
# =============================================================================
set -euo pipefail

# =============================================================================
# Inlined utility functions
# =============================================================================

# Logging facilities for bash
# ===========================
#
# Provides the following functions:
#
#  openlogfile <FILENAME> [STDERR]
#    Redirects all logging to the file specified by FILENAME.
#    If the file already exists, new logs are appended at the end.
#    Pass STDERR as second argument to also mirror output to stderr.
#
#  closelogfile
#    Closes the current logfile and redirects logging back to stderr.
#
#  logdebug <MESSAGE>
#    Writes message as a debug level log to the current log destination.
#
#  loginfo <MESSAGE>
#    Writes message as an info level log to the current log destination.
#
#  logwarning <MESSAGE>
#    Writes message as a warning level log to the current log destination.
#
#  logerror <MESSAGE>
#    Writes message as an error level log to the current log destination.
#
#  setloglevel <LEVEL>
#    Sets the current logging level (DEBUG, INFO, WARNING or ERROR).
#    Only messages at or above this level are recorded.
#
# All logging goes through file descriptor 3.
# By default fd 3 is redirected to stderr.
# Colors (VT100) are applied automatically when fd 3 is a terminal.
# Default logging level: INFO.

LOG_DEBUG_LEVEL=1
LOG_INFO_LEVEL=2
LOG_WARNING_LEVEL=3
LOG_ERROR_LEVEL=4

LOG_LEVEL=$LOG_INFO_LEVEL

exec 3>&2

# ---------- VT100 color codes (empty when fd 3 is not a terminal) ----------

_log_color() {
    [ -t 3 ] && printf '%s' "$1" || true
}

_LOG_RESET=$(   _log_color $'\033[0m'    )
_LOG_CYAN=$(    _log_color $'\033[0;36m' )   # DEBUG
_LOG_GREEN=$(   _log_color $'\033[0;32m' )   # INFO
_LOG_YELLOW=$(  _log_color $'\033[0;33m' )   # WARNING
_LOG_RED=$(     _log_color $'\033[1;31m' )   # ERROR
_LOG_DIM=$(     _log_color $'\033[2m'    )   # timestamp / host dimmed

unset -f _log_color

# ---------- internal formatter ----------

_logwrite() {
    local color="$1"
    local label="$2"
    shift 2
    printf '%s%s%s %s%-9s%s %s%s.%s%s -- %s\n' \
        "${_LOG_DIM}" "$(date +'%Y-%m-%d %H:%M:%S')" "${_LOG_RESET}" \
        "${color}" "${label}" "${_LOG_RESET}" \
        "${_LOG_DIM}" "$(hostname)" "$$" "${_LOG_RESET}" \
        "$*" 1>&3
}

# ---------- public log functions ----------

function logdebug() {
    (( LOG_LEVEL <= LOG_DEBUG_LEVEL )) && \
        _logwrite "${_LOG_CYAN}"   "[DEBUG  ]" "$@"
    return 0
}

function loginfo() {
    (( LOG_LEVEL <= LOG_INFO_LEVEL )) && \
        _logwrite "${_LOG_GREEN}"  "[INFO   ]" "$@"
    return 0
}

function logwarning() {
    (( LOG_LEVEL <= LOG_WARNING_LEVEL )) && \
        _logwrite "${_LOG_YELLOW}" "[WARNING]" "$@"
    return 0
}

function logerror() {
    (( LOG_LEVEL <= LOG_ERROR_LEVEL )) && \
        _logwrite "${_LOG_RED}"    "[ERROR  ]" "$@"
    return 0
}

function setloglevel() {
    local _varname="LOG_${1}_LEVEL"
    LOG_LEVEL="${!_varname}"
    loginfo "Logging level set to: ${1} (${LOG_LEVEL})"
}

# ---------- logfile management ----------

function openlogfile() {
    if [[ "${2:-}" == "STDERR" ]]; then
        exec 3> >(tee -a "$1" >&2)
    else
        exec 3>> "$1"
    fi
    LOGFILE="$1"
}

function logstderrtoo() {
    [[ -n "${LOGFILE:-}" ]] && openlogfile "${LOGFILE}" STDERR
}

function closelogfile() {
    if [[ -n "${LOGFILE:-}" ]]; then
        exec 3>&-
        exec 3>&2
        LOGFILE=""
    fi
}

# =============================================================================
# Image identity  (substituted at build time by docker/build_user_script.sh)
# =============================================================================
_SKI_IMAGE_REGISTRY=""
_SKI_IMAGE_NAME="@@IMAGE_NAME@@"
_SKI_IMAGE_TAG="@@IMAGE_TAG@@"

# URL of the raw skimindex.toml in the source repository (used by `init`).
_SKI_CONFIG_URL="https://raw.githubusercontent.com/ArcEcoGen/skimindex/refs/heads/main/config/skimindex.toml"

# =============================================================================
# Project root — defaults to current working directory
# =============================================================================
PROJECT_ROOT="$PWD"

# Parse --project-dir (and -h/--help) before the subcommand
_remaining_args=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --project-dir)
            PROJECT_ROOT="$(cd "$2" && pwd)"; shift 2 ;;
        --project-dir=*)
            PROJECT_ROOT="$(cd "${1#--project-dir=}" && pwd)"; shift ;;
        -h|--help)
            sed -n '2,/^# =\+$/{ s/^# \{0,1\}//; /^=\+$/d; p }' "$0"
            exit 0 ;;
        *)
            _remaining_args+=("$1"); shift ;;
    esac
done
set -- "${_remaining_args[@]+"${_remaining_args[@]}"}"

CONFIG_FILE="${PROJECT_ROOT}/config/skimindex.toml"
SIF_FILE="${PROJECT_ROOT}/images/${_SKI_IMAGE_NAME}-${_SKI_IMAGE_TAG}.sif"

# =============================================================================
# Runtime detection
# =============================================================================
_ski_detect_runtime() {
    if   command -v apptainer >/dev/null 2>&1; then echo apptainer
    elif command -v docker    >/dev/null 2>&1; then echo docker
    elif command -v podman    >/dev/null 2>&1; then echo podman
    else echo none
    fi
}

RUNTIME="$(_ski_detect_runtime)"

# =============================================================================
# Config-driven bind-mount and host-dir helpers
# =============================================================================

_ski_host_dirs() {
    [[ -f "$CONFIG_FILE" ]] || return 0
    awk -v root="$PROJECT_ROOT" '
        /^\[local_directories\]/ { s=1; next }
        /^\[/                    { s=0 }
        s && /^[a-zA-Z_][a-zA-Z0-9_]*[[:space:]]*=/ {
            v=$0; gsub(/^[^"]*"/, "", v); gsub(/".*$/, "", v)
            print (substr(v,1,1)=="/") ? v : root "/" v
        }
    ' "$CONFIG_FILE"
}

_ski_bind_flags() {
    local prefix="$1"
    [[ -f "$CONFIG_FILE" ]] || return 0
    awk -v root="$PROJECT_ROOT" -v pfx="$prefix" '
        /^\[local_directories\]/ { s=1; next }
        /^\[/                    { s=0 }
        s && /^[a-zA-Z_][a-zA-Z0-9_]*[[:space:]]*=/ {
            k=$1
            v=$0; gsub(/^[^"]*"/, "", v); gsub(/".*$/, "", v)
            path = (substr(v,1,1)=="/") ? v : root "/" v
            printf "%s\n%s:/%s\n", pfx, path, k
        }
    ' "$CONFIG_FILE"
}

_ski_build_bind_array() {
    local prefix="$1" flag
    while IFS= read -r flag; do
        BIND+=("$flag")
    done < <(_ski_bind_flags "$prefix")
}

# =============================================================================
# Directory management
# =============================================================================
_ski_ensure_dirs() {
    local dir
    while IFS= read -r dir; do
        mkdir -p "$dir"
    done < <(_ski_host_dirs)
}

# =============================================================================
# Run helpers
# =============================================================================
_ski_run_interactive() {
    _ski_ensure_dirs
    local _SKI_FULL_IMAGE="${_SKI_IMAGE_REGISTRY}/${_SKI_IMAGE_NAME}:${_SKI_IMAGE_TAG}"
    local BIND=()
    if [[ "$RUNTIME" == "apptainer" ]]; then
        _ski_build_bind_array "--bind"
        APPTAINERENV_PREPEND_PATH=/app/bin:/app/scripts \
        apptainer run --pwd /app "${BIND[@]}" "$SIF_FILE"
    else
        _ski_build_bind_array "-v"
        "$RUNTIME" run --rm -it "${BIND[@]}" "$_SKI_FULL_IMAGE"
    fi
}

_ski_run_exec() {
    _ski_ensure_dirs
    local _SKI_FULL_IMAGE="${_SKI_IMAGE_REGISTRY}/${_SKI_IMAGE_NAME}:${_SKI_IMAGE_TAG}"
    local BIND=()
    if [[ "$RUNTIME" == "apptainer" ]]; then
        _ski_build_bind_array "--bind"
        APPTAINERENV_PREPEND_PATH=/app/bin:/app/scripts \
        apptainer exec --pwd /app "${BIND[@]}" "$SIF_FILE" "$@"
    else
        _ski_build_bind_array "-v"
        "$RUNTIME" run --rm "${BIND[@]}" "$_SKI_FULL_IMAGE" "$@"
    fi
}

# =============================================================================
# init subcommand
# =============================================================================
_ski_init() {
    loginfo "Initialising project directory: $PROJECT_ROOT"

    mkdir -p "${PROJECT_ROOT}/config"
    loginfo "Directory ready: ${PROJECT_ROOT}/config"

    if [[ -f "$CONFIG_FILE" ]]; then
        loginfo "Config already present: $CONFIG_FILE — skipping download."
    else
        loginfo "Downloading config from: $_SKI_CONFIG_URL"
        if command -v curl >/dev/null 2>&1; then
            curl -fsSL "$_SKI_CONFIG_URL" -o "$CONFIG_FILE"
        elif command -v wget >/dev/null 2>&1; then
            wget -q "$_SKI_CONFIG_URL" -O "$CONFIG_FILE"
        else
            logerror "Neither curl nor wget found — cannot download config."
            exit 1
        fi
        loginfo "Config written: $CONFIG_FILE"
    fi

    local dir
    while IFS= read -r dir; do
        mkdir -p "$dir"
        loginfo "Directory ready: $dir"
    done < <(_ski_host_dirs)

    loginfo "Project initialised successfully."
    loginfo "Edit $CONFIG_FILE to customise paths and downloads."
}

# =============================================================================
# Subcommand dispatch
# =============================================================================
if [[ $# -eq 0 ]]; then
    sed -n '2,/^# =\+$/{ s/^# \{0,1\}//; /^=\+$/d; p }' "$0"
    exit 0
fi

SUBCMD="$1"; shift

case "$SUBCMD" in
    -h|--help)
        sed -n '2,/^# =\+$/{ s/^# \{0,1\}//; /^=\+$/d; p }' "$0"
        exit 0
        ;;
    init)
        _ski_init "$@"
        exit 0
        ;;
    shell)
        if [[ "$RUNTIME" == "none" ]]; then
            logerror "No container runtime found (apptainer, docker or podman required)."
            exit 1
        fi
        if [[ "$RUNTIME" == "apptainer" && ! -f "$SIF_FILE" ]]; then
            logerror "SIF image not found: $SIF_FILE"
            logerror "Run: cd <project>/docker && make pull-sif"
            exit 1
        fi
        _ski_run_interactive
        exit 0
        ;;
esac

# All remaining subcommands require a container runtime
if [[ "$RUNTIME" == "none" ]]; then
    logerror "No container runtime found (apptainer, docker or podman required)."
    exit 1
fi
if [[ "$RUNTIME" == "apptainer" && ! -f "$SIF_FILE" ]]; then
    logerror "SIF image not found: $SIF_FILE"
    logerror "Run: cd <project>/docker && make pull-sif"
    exit 1
fi

case "$SUBCMD" in
    download_genbank)
        _ski_run_exec download_genbank.sh "$@"
        ;;
    download_human)
        _ski_run_exec download_human.sh "$@"
        ;;
    download_plants)
        _ski_run_exec download_plants.sh "$@"
        ;;
    download_references)
        _ski_run_exec download_references.sh "$@"
        ;;
    download_refgenome)
        _ski_run_exec download_refgenome.sh "$@"
        ;;
    split_human)
        _ski_run_exec split_human.sh "$@"
        ;;
    *)
        logerror "Unknown subcommand '$SUBCMD'."
        logerror "Run '$(basename "$0") --help' for usage."
        exit 1
        ;;
esac
