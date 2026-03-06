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
