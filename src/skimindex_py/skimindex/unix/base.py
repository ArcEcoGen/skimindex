"""
Base module for Unix command handling with integrated logging.

Provides a modified local machine instance that captures stderr from executed
commands and sends it to the skimindex logging system, keeping stderr separate
from stdout (data).

Equivalent to bash script's approach:
  - stderr → captured and sent to log.py (loginfo/logwarning/logerror)
  - stdout → untouched (application data)
"""

import tempfile
from pathlib import Path
from plumbum import local as _plumbum_local
from skimindex.log import loginfo, logwarning


class LoggedBoundCommand:
    """
    Wraps a plumbum BoundCommand to capture and log stderr separately.

    When executed:
    - stderr is captured and sent to the logging system
    - stdout is returned unchanged
    - Data integrity is maintained
    """

    def __init__(self, bound_command):
        self._cmd = bound_command

    def __call__(self, *args, **kwargs):
        """Execute command with stderr captured and sent to logs."""
        # Redirect stderr to a temporary file
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.stderr') as stderr_file:
            stderr_path = stderr_file.name

        try:
            # Execute command: redirect stderr to temp file, keep stdout
            cmd_with_stderr = self._cmd.with_stderr(stderr_path)
            # Execute and capture stdout
            stdout = cmd_with_stderr()
        except Exception as e:
            # Even on error, capture and log stderr
            self._log_stderr_file(stderr_path)
            raise
        finally:
            # Clean up stderr file
            Path(stderr_path).unlink(missing_ok=True)

        # Log any captured stderr
        self._log_stderr_file(stderr_path)

        return stdout

    def __getitem__(self, args):
        """Support plumbum's bracket notation for arguments."""
        return LoggedBoundCommand(self._cmd[args])

    def __or__(self, other):
        """Support piping with |."""
        if isinstance(other, LoggedBoundCommand):
            return LoggedBoundCommand(self._cmd | other._cmd)
        return LoggedBoundCommand(self._cmd | other)

    def __ror__(self, other):
        """Support piping when on the right side."""
        if isinstance(other, LoggedBoundCommand):
            return LoggedBoundCommand(other._cmd | self._cmd)
        return LoggedBoundCommand(other | self._cmd)

    def _log_stderr_file(self, stderr_path: str) -> None:
        """Read stderr file and log its contents."""
        try:
            with open(stderr_path, 'r') as f:
                stderr_content = f.read().strip()
                if stderr_content:
                    # Send stderr to log (typically logwarning for stderr output)
                    for line in stderr_content.split('\n'):
                        if line:
                            logwarning(line)
        except Exception:
            # Silently ignore if we can't read the file
            pass

    def with_stderr(self, stderr_target):
        """Support plumbum's with_stderr for compatibility."""
        return LoggedBoundCommand(self._cmd.with_stderr(stderr_target))

    # Forward other method calls to the underlying command
    def __getattr__(self, name):
        return getattr(self._cmd, name)


class LoggedLocalMachine:
    """
    Wrapper around plumbum's local machine that captures stderr from commands
    and sends it to the logging system, maintaining stderr/stdout separation.

    - Logs go to skimindex.log (via loginfo/logwarning/logerror)
    - Data (stdout) remains untouched
    """

    def __init__(self):
        self._local = _plumbum_local

    def __getattr__(self, name: str):
        """Get a command from the local machine with logging support."""
        cmd = getattr(self._local, name)
        return LoggedBoundCommand(cmd)

    def __getitem__(self, name: str):
        """Support bracket notation: local['command']."""
        cmd = self._local[name]
        return LoggedBoundCommand(cmd)


# Global instance to use instead of plumbum.local
local = LoggedLocalMachine()
