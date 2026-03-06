# Guard against direct execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "ERROR: __utils_functions.sh is a library — source it, do not run it." >&2
    exit 1
fi

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
