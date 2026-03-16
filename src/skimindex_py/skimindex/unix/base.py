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
from skimindex.log import logwarning


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
        # Pipeline objects don't support with_stderr — execute directly
        if not hasattr(self._cmd, 'with_stderr'):
            return self._cmd(*args, **kwargs)

        stderr_file = tempfile.NamedTemporaryFile(
            mode='w+', delete=False, suffix='.stderr'
        )
        stderr_path = stderr_file.name
        stderr_file.close()

        try:
            cmd_with_stderr = self._cmd.with_stderr(stderr_path)
            stdout = cmd_with_stderr(*args, **kwargs)
        finally:
            self._log_stderr_file(stderr_path)
            Path(stderr_path).unlink(missing_ok=True)

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

    def __gt__(self, target):
        """Support output redirection with >."""
        return LoggedBoundCommand(self._cmd > target)

    def __rshift__(self, target):
        """Support append redirection with >>."""
        return LoggedBoundCommand(self._cmd >> target)

    def _log_stderr_file(self, stderr_path: str) -> None:
        """Read stderr file and log its contents."""
        try:
            with open(stderr_path, 'r') as f:
                stderr_content = f.read().strip()
            if stderr_content:
                for line in stderr_content.split('\n'):
                    if line:
                        logwarning(line)
        except Exception:
            pass

    def with_stderr(self, stderr_target):
        """Support plumbum's with_stderr for compatibility."""
        return LoggedBoundCommand(self._cmd.with_stderr(stderr_target))

    def __getattr__(self, name):
        """Forward unknown attributes to the underlying plumbum command."""
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
