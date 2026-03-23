# ============================================================
# __skimindex_log.sh
# Logging facilities for skimindex bash scripts.
#
# Provides:
#   logdebug / loginfo / logwarning / logerror <MESSAGE>
#   setloglevel <LEVEL>          (DEBUG | INFO | WARNING | ERROR)
#   openlogfile <PATH> [MIRROR] [EVERYTHING]
#   closelogfile
#
# All logging goes through file descriptor 3 (default: stderr).
# VT100 colours are applied on terminals; stripped when writing to files.
# Default level: INFO.
#
# Source this file — do NOT execute it directly.
# ============================================================

# Guard against direct execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "ERROR: __skimindex_log.sh is a library — source it, do not run it." >&2
    exit 1
fi

# @@STRIP_INLINE_BEGIN@@
# Guard against multiple inclusion
[[ -n "${_SKIMINDEX_LOG_LOADED:-}" ]] && return 0

# Require __skimindex.sh as entry point (_skimindex_sh_dir must be set)
if [[ -z "${_skimindex_sh_dir:-}" ]]; then
    echo "ERROR: source __skimindex.sh instead of __skimindex_log.sh directly." >&2
    return 1
fi
# @@STRIP_INLINE_END@@

_SKIMINDEX_LOG_LOADED=1

LOG_DEBUG_LEVEL=1
LOG_INFO_LEVEL=2
LOG_WARNING_LEVEL=3
LOG_ERROR_LEVEL=4

LOG_LEVEL=$LOG_INFO_LEVEL

exec 3>&2

# ---------- VT100 colour codes ----------
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
    local everything="${3:-false}"  # "true" → also redirect fd 2 through fd 3
    if ! touch "$logpath" 2>/dev/null; then
        logwarning "cannot open log file: $logpath — logging to stderr only."
        return 0
    fi
    if [[ "$mirror" == "true" ]]; then
        exec 3> >(tee >(sed 's/\x1b\[[0-9;]*m//g' >> "$logpath") >&2)
    else
        exec 3> >(sed 's/\x1b\[[0-9;]*m//g' >> "$logpath")
    fi
    if [[ "$everything" == "true" ]]; then
        exec 2>&3
        LOGEVERYTHING=1
    fi
    LOGFILE="$logpath"
}

function closelogfile() {
    if [[ -n "${LOGFILE:-}" ]]; then
        if [[ -n "${LOGEVERYTHING:-}" ]]; then
            exec 2>/dev/tty 2>/dev/null || exec 2>&1
            unset LOGEVERYTHING
        fi
        exec 3>&-
        exec 3>&2
        LOGFILE=""
    fi
}
