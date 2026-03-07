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
#   --local              Use the locally cached image without checking the
#                        registry for updates (docker/podman only; apptainer
#                        always uses the local SIF file).
#   -h, --help           Show this help and exit.
#
# Subcommands:
#   init                     Initialise a new project directory and download the default config.
#   update                   Pull the latest container image from the registry (or refresh the SIF for apptainer).
#   shell                    Start an interactive shell inside the container.
#   download_genbank         Download GenBank flat-file divisions and convert them to
#   download_references      Master script for the reference data pipeline.
#   split_references         Split reference genome sequences into overlapping fragments
#
# shell options:
#   --mount SRC:DST      Bind-mount SRC (host) to DST (container).
#                        May be repeated for multiple extra mounts.
#
# Configuration:
#   <project-dir>/config/skimindex.toml
#       Pipeline configuration.  The [local_directories] section maps each
#       key k to a host path that is bind-mounted to /k inside the container.
#
# Container runtime:
#   Auto-detected in priority order: apptainer > docker > podman.
#   Apptainer uses the local SIF image:
#       <project-dir>/images/skimindex-latest.sif
#   Docker / Podman pull the image from the registry on first use:
#       registry.metabarcoding.org/arcecogen/skimindex:latest
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

# ---------- VT100 color codes (always defined as constants) ----------
# Colors are always embedded in log messages; openlogfile strips them via sed
# when writing to a file, so the file stays clean while the screen keeps colors.

_LOG_RESET=$'\033[0m'
_LOG_CYAN=$'\033[0;36m'    # DEBUG
_LOG_GREEN=$'\033[0;32m'   # INFO
_LOG_YELLOW=$'\033[0;33m'  # WARNING
_LOG_RED=$'\033[1;31m'     # ERROR
_LOG_DIM=$'\033[2m'        # timestamp / host dimmed

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
    local logpath="$1"
    local mirror="${2:-false}"      # "true" → tee logs to screen + file
    local everything="${3:-false}"  # "true" → also redirect fd 2 (all stderr) through fd 3
    # Test write access before redirecting fd 3 (avoids set -e crash).
    # Use touch rather than >> to avoid bash printing a redirection error
    # to stderr even when the failure is handled.
    if ! touch "$logpath" 2>/dev/null; then
        logwarning "cannot open log file: $logpath — logging to stderr only."
        return 0
    fi
    if [[ "$mirror" == "true" ]]; then
        # fd 3 → tee:
        #   - to screen via fd 2 (colors intact)
        #   - to file via sed (VT100 codes stripped)
        exec 3> >(tee >(sed 's/\x1b\[[0-9;]*m//g' >> "$logpath") >&2)
    else
        # fd 3 → file only (VT100 codes stripped)
        exec 3> >(sed 's/\x1b\[[0-9;]*m//g' >> "$logpath")
    fi
    if [[ "$everything" == "true" ]]; then
        # fd 2 → fd 3: all stderr (bash errors, command output) also captured
        # NOTE: tee's >&2 is evaluated at fork time (before this exec),
        # so it keeps pointing to the original screen fd — no loop.
        exec 2>&3
        LOGEVERYTHING=1
    fi
    LOGFILE="$logpath"
}

function closelogfile() {
    if [[ -n "${LOGFILE:-}" ]]; then
        # Restore fd 2 only if it was redirected (everything=true)
        if [[ -n "${LOGEVERYTHING:-}" ]]; then
            exec 2>/dev/tty 2>/dev/null || exec 2>&1
            unset LOGEVERYTHING
        fi
        exec 3>&-   # close log fd
        exec 3>&2   # restore fd 3 to stderr
        LOGFILE=""
    fi
}

# =============================================================================
# Image identity  (substituted at build time by docker/build_user_script.sh)
# =============================================================================
_SKI_IMAGE_REGISTRY="registry.metabarcoding.org/arcecogen"
_SKI_IMAGE_NAME="skimindex"
_SKI_IMAGE_TAG="latest"

# URL of the raw skimindex.toml in the source repository (used by `init`).
_SKI_CONFIG_URL="https://raw.githubusercontent.com/metabarcoding/skimindex/main/config/skimindex.toml"

# =============================================================================
# Project root — defaults to current working directory
# =============================================================================
PROJECT_ROOT="$PWD"
_SKI_LOCAL=0   # set to 1 by --local; disables --pull always for docker/podman

# Parse global options before the subcommand.
# Stop option processing at the first non-option argument (the subcommand)
# so that options belonging to the subcommand (e.g. --help) are not consumed.
_remaining_args=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --project-dir)
            PROJECT_ROOT="$(cd "$2" && pwd)"; shift 2 ;;
        --project-dir=*)
            PROJECT_ROOT="$(cd "${1#--project-dir=}" && pwd)"; shift ;;
        --local)
            _SKI_LOCAL=1; shift ;;
        -h|--help)
            sed -En '2,/^# =+$/{ s/^# ?//; /^=+$/d; p; }' "$0"
            exit 0 ;;
        --)
            shift; _remaining_args+=("$@"); break ;;
        -*)
            logerror "Unknown global option: $1"
            logerror "Run '$(basename "$0") --help' for usage."
            exit 1 ;;
        *)
            # First non-option arg is the subcommand — stop global parsing
            _remaining_args+=("$@"); break ;;
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

# _ski_ensure_current
#   For apptainer: auto-update the SIF when the digest is unknown (no .digest
#   file) or when the registry has a newer image.  Skipped with --local.
_ski_ensure_current() {
    [[ "$RUNTIME" == "apptainer" ]] || return 0
    (( _SKI_LOCAL )) && return 0
    _ski_apptainer_needs_update && _ski_update
    return 0
}

# _ski_run_interactive [extra_mount ...]
#   extra_mount: "src:dst" pairs added on top of the config-driven mounts.
_ski_run_interactive() {
    _ski_ensure_dirs
    _ski_ensure_current
    local _SKI_FULL_IMAGE="${_SKI_IMAGE_REGISTRY}/${_SKI_IMAGE_NAME}:${_SKI_IMAGE_TAG}"
    local BIND=()
    local pull_flag=()
    (( _SKI_LOCAL )) || pull_flag=(--pull always)
    if [[ "$RUNTIME" == "apptainer" ]]; then
        _ski_build_bind_array "--bind"
        for _m in "$@"; do BIND+=(--bind "$_m"); done
        APPTAINERENV_PREPEND_PATH=/app/bin:/app/scripts \
        apptainer run --pwd /app "${BIND[@]}" "$SIF_FILE"
    else
        _ski_build_bind_array "-v"
        for _m in "$@"; do BIND+=(-v "$_m"); done
        "$RUNTIME" run "${pull_flag[@]}" --rm -it "${BIND[@]}" "$_SKI_FULL_IMAGE"
    fi
}

_ski_run_exec() {
    _ski_ensure_dirs
    _ski_ensure_current
    local _SKI_FULL_IMAGE="${_SKI_IMAGE_REGISTRY}/${_SKI_IMAGE_NAME}:${_SKI_IMAGE_TAG}"
    local BIND=()
    local pull_flag=()
    (( _SKI_LOCAL )) || pull_flag=(--pull always)
    if [[ "$RUNTIME" == "apptainer" ]]; then
        _ski_build_bind_array "--bind"
        APPTAINERENV_PREPEND_PATH=/app/bin:/app/scripts \
        apptainer exec --pwd /app "${BIND[@]}" "$SIF_FILE" "$@"
    else
        _ski_build_bind_array "-v"
        "$RUNTIME" run "${pull_flag[@]}" --rm "${BIND[@]}" "$_SKI_FULL_IMAGE" "$@"
    fi
}

# =============================================================================
# update subcommand — pull the latest image
# =============================================================================

# _ski_registry_digest <registry> <name> <tag>
#   Query the OCI registry for the current digest of <name>:<tag>.
#   Tries both OCI and Docker v2 manifest media types.
#   Outputs the digest (sha256:…) on success, empty string on failure.
_ski_registry_digest() {
    local registry="$1" name="$2" tag="$3"
    # registry may contain an org path (e.g. registry.example.com/org).
    # The OCI distribution v2 API requires /v2/ immediately after the host,
    # so split registry into host and optional org prefix.
    local host="${registry%%/*}"
    local prefix="${registry#"$host"}"           # empty or /org[/...]
    local repo="${prefix:+${prefix#/}/}${name}"  # org/name  or just  name
    local url="https://${host}/v2/${repo}/manifests/${tag}"
    local digest=""
    if command -v curl >/dev/null 2>&1; then
        # Fetch the manifest index and extract the digest for the current
        # platform (linux/<arch>).  This avoids false positives when only
        # a different architecture's image is updated.
        local arch
        case "$(uname -m)" in
            x86_64)  arch="amd64" ;;
            aarch64) arch="arm64" ;;
            *)       arch="$(uname -m)" ;;
        esac
        local body
        body=$(curl -fsSL --connect-timeout 5 \
            -H "Accept: application/vnd.oci.image.index.v1+json" \
            -H "Accept: application/vnd.docker.distribution.manifest.list.v2+json" \
            "$url" 2>/dev/null)
        # Parse the platform-specific digest from the JSON index.
        # digest appears before architecture in each manifest entry, so we
        # record the last seen digest and print it when the arch matches.
        # Falls back to empty string if the response is not a manifest list.
        digest=$(printf '%s' "$body" \
            | awk -v arch="$arch" \
                '/"digest":/ { match($0, /sha256:[^"]+/); last = substr($0, RSTART, RLENGTH) }
                 /"architecture":/ && index($0, "\"" arch "\"") > 0 && length(last) > 0 { print last; last = "" }')
    fi
    printf '%s' "$digest"
}

# _ski_apptainer_needs_update
#   Returns 0 (true) when the registry digest differs from the locally cached
#   digest, or when the SIF file is absent.  Returns 1 when up-to-date or
#   when the registry cannot be reached (offline mode).
_ski_apptainer_needs_update() {
    local digest_file="${SIF_FILE%.sif}.digest"
    [[ -f "$SIF_FILE" ]] || return 0   # no SIF → must pull

    local remote_digest
    remote_digest=$(_ski_registry_digest \
        "$_SKI_IMAGE_REGISTRY" "$_SKI_IMAGE_NAME" "$_SKI_IMAGE_TAG")
    [[ -z "$remote_digest" ]] && return 1   # offline / unreachable → skip

    local local_digest=""
    [[ -f "$digest_file" ]] && local_digest="$(cat "$digest_file")"

    [[ "$remote_digest" != "$local_digest" ]]
}

_ski_update() {
    local _SKI_FULL_IMAGE="${_SKI_IMAGE_REGISTRY}/${_SKI_IMAGE_NAME}:${_SKI_IMAGE_TAG}"
    if [[ "$RUNTIME" == "apptainer" ]]; then
        local sif_dir digest_file
        sif_dir="$(dirname "$SIF_FILE")"
        digest_file="${SIF_FILE%.sif}.digest"
        mkdir -p "$sif_dir"
        loginfo "Pulling latest SIF from docker://${_SKI_FULL_IMAGE}"
        loginfo "Destination: $SIF_FILE"
        apptainer pull --force "$SIF_FILE" "docker://${_SKI_FULL_IMAGE}"
        # Record the remote digest so future checks can skip unnecessary pulls
        local remote_digest
        remote_digest=$(_ski_registry_digest \
            "$_SKI_IMAGE_REGISTRY" "$_SKI_IMAGE_NAME" "$_SKI_IMAGE_TAG")
        [[ -n "$remote_digest" ]] && printf '%s' "$remote_digest" > "$digest_file"
        loginfo "SIF updated: $SIF_FILE"
    else
        loginfo "Pulling latest image: ${_SKI_FULL_IMAGE}"
        "$RUNTIME" pull "$_SKI_FULL_IMAGE"
        loginfo "Image updated."
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
    sed -En '2,/^# =+$/{ s/^# ?//; /^=+$/d; p; }' "$0"
    exit 0
fi

SUBCMD="$1"; shift

case "$SUBCMD" in
    -h|--help)
        sed -En '2,/^# =+$/{ s/^# ?//; /^=+$/d; p; }' "$0"
        exit 0
        ;;
    init)
        _ski_init "$@"
        exit 0
        ;;
    update)
        if [[ "$RUNTIME" == "none" ]]; then
            logerror "No container runtime found (apptainer, docker or podman required)."
            exit 1
        fi
        _ski_update
        exit 0
        ;;
    shell)
        if [[ "$RUNTIME" == "none" ]]; then

            logerror "No container runtime found (apptainer, docker or podman required)."
            exit 1
        fi
        _shell_mounts=()
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --mount)     _shell_mounts+=("$2"); shift 2 ;;
                --mount=*)   _shell_mounts+=("${1#--mount=}"); shift ;;
                --)          shift; break ;;
                -*)          logerror "Unknown shell option: $1"; exit 1 ;;
                *)           break ;;
            esac
        done
        _ski_run_interactive "${_shell_mounts[@]}"
        exit 0
        ;;
esac

# All remaining subcommands require a container runtime
if [[ "$RUNTIME" == "none" ]]; then
    logerror "No container runtime found (apptainer, docker or podman required)."
    exit 1
fi

case "$SUBCMD" in
    download_genbank)
        _ski_run_exec download_genbank.sh "$@"
        ;;
    download_references)
        _ski_run_exec download_references.sh "$@"
        ;;
    split_references)
        _ski_run_exec split_references.sh "$@"
        ;;
    *)
        logerror "Unknown subcommand '$SUBCMD'."
        logerror "Run '$(basename "$0") --help' for usage."
        exit 1
        ;;
esac
