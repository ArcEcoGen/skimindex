"""
Logging module for skimindex — Pythonic equivalent of __utils_functions.sh

Provides logging functions matching bash implementation:
  - logdebug(message)
  - loginfo(message)
  - logwarning(message)
  - logerror(message)
  - setloglevel(level)
  - openlogfile(path, mirror=False)
  - closelogfile()

Log levels: DEBUG, INFO, WARNING, ERROR
Default level: INFO
Colors are applied to terminal output; stripped from file output.

Example:
    from skimindex.log import loginfo, logwarning, openlogfile

    loginfo("Starting process")
    openlogfile("/tmp/process.log", mirror=True)
    logwarning("This goes to file and screen")
    closelogfile()
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path


# Log level constants (matching bash levels)
LOG_DEBUG_LEVEL = 1
LOG_INFO_LEVEL = 2
LOG_WARNING_LEVEL = 3
LOG_ERROR_LEVEL = 4

LOG_LEVEL = LOG_INFO_LEVEL

# VT100 color codes
_LOG_RESET = '\033[0m'
_LOG_CYAN = '\033[0;36m'      # DEBUG
_LOG_GREEN = '\033[0;32m'     # INFO
_LOG_YELLOW = '\033[0;33m'    # WARNING
_LOG_RED = '\033[1;31m'       # ERROR
_LOG_DIM = '\033[2m'          # timestamp/host dimmed

# Global state
_logfile: str | None = None
_mirror_to_stderr = False
_logeverything = False
_original_stderr = None  # Save original stderr fd for restoration


def _should_use_color() -> bool:
    """Check if output is a terminal."""
    return sys.stderr.isatty()


def _logwrite(color: str, label: str, *message: str) -> None:
    """Internal formatter (matches bash _logwrite)."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    hostname = os.uname().nodename
    pid = os.getpid()
    msg_text = ' '.join(str(m) for m in message)

    # Build log line with colors
    if _should_use_color():
        log_line = (
            f"{_LOG_DIM}{timestamp}{_LOG_RESET} "
            f"{color}{label:<9}{_LOG_RESET} "
            f"{_LOG_DIM}{hostname}.{pid}{_LOG_RESET} "
            f"-- {msg_text}"
        )
    else:
        # No colors for non-terminal output
        log_line = f"{timestamp} {label:<9} {hostname}.{pid} -- {msg_text}"

    # Write to current output
    if _logfile:
        clean_line = re.sub(r'\x1b\[[0-9;]*m', '', log_line)
        if _logeverything:
            # fd 2 has been redirected to the log file at the OS level.
            # Use os.write(2, ...) to hit that fd directly — avoids the
            # duplicate entry that open() + mirror-to-sys.stderr would produce.
            os.write(2, (clean_line + '\n').encode())
            if _mirror_to_stderr and _original_stderr is not None:
                os.write(_original_stderr, (log_line + '\n').encode())
        else:
            with open(_logfile, 'a') as f:
                f.write(clean_line + '\n')
            if _mirror_to_stderr:
                print(log_line, file=sys.stderr)
    else:
        # Write to stderr
        print(log_line, file=sys.stderr)


def logdebug(*message: str) -> None:
    """Write debug level log message."""
    if LOG_LEVEL <= LOG_DEBUG_LEVEL:
        _logwrite(_LOG_CYAN, "[DEBUG  ]", *message)


def loginfo(*message: str) -> None:
    """Write info level log message."""
    if LOG_LEVEL <= LOG_INFO_LEVEL:
        _logwrite(_LOG_GREEN, "[INFO   ]", *message)


def logwarning(*message: str) -> None:
    """Write warning level log message."""
    if LOG_LEVEL <= LOG_WARNING_LEVEL:
        _logwrite(_LOG_YELLOW, "[WARNING]", *message)


def logerror(*message: str) -> None:
    """Write error level log message."""
    if LOG_LEVEL <= LOG_ERROR_LEVEL:
        _logwrite(_LOG_RED, "[ERROR  ]", *message)


def setloglevel(level: str) -> None:
    """Set logging level (DEBUG, INFO, WARNING, ERROR)."""
    global LOG_LEVEL
    level_upper = level.upper()
    level_map = {
        'DEBUG': LOG_DEBUG_LEVEL,
        'INFO': LOG_INFO_LEVEL,
        'WARNING': LOG_WARNING_LEVEL,
        'ERROR': LOG_ERROR_LEVEL,
    }
    if level_upper in level_map:
        LOG_LEVEL = level_map[level_upper]
        loginfo(f"Logging level set to: {level_upper} ({LOG_LEVEL})")
    else:
        logwarning(f"Unknown logging level: {level}")


def openlogfile(logpath: str, mirror: bool = False, everything: bool = False) -> None:
    """
    Open a log file for output.

    Args:
        logpath: Path to log file (appends if exists)
        mirror: If True, also output to stderr
        everything: If True, redirect process stderr (fd 2) to log file,
                   capturing all command output and stderr
    """
    global _logfile, _mirror_to_stderr, _logeverything, _original_stderr

    # Test write access
    try:
        Path(logpath).parent.mkdir(parents=True, exist_ok=True)
        Path(logpath).touch()
    except Exception as e:
        logwarning(f"cannot open log file: {logpath} — logging to stderr only.")
        return

    _logfile = logpath
    _mirror_to_stderr = mirror
    _logeverything = everything

    # If everything=True, redirect process stderr (fd 2) to the log file
    if everything:
        try:
            # Save original stderr fd
            _original_stderr = os.dup(2)
            # Redirect fd 2 to the log file (append mode)
            log_fd = os.open(logpath, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
            os.dup2(log_fd, 2)
            os.close(log_fd)
        except Exception as e:
            logwarning(f"Failed to redirect stderr to log file: {e}")
            _logeverything = False

    loginfo(f"Logging to file: {logpath}")


def closelogfile() -> None:
    """Close the current log file and restore stderr output."""
    global _logfile, _mirror_to_stderr, _logeverything, _original_stderr

    if _logfile:
        loginfo(f"Closing log file: {_logfile}")

        # Restore stderr if it was redirected (everything=True)
        if _logeverything and _original_stderr is not None:
            try:
                os.dup2(_original_stderr, 2)
                os.close(_original_stderr)
            except Exception as e:
                logwarning(f"Failed to restore stderr: {e}")
            finally:
                _original_stderr = None

        _logfile = None
        _mirror_to_stderr = False
        _logeverything = False
