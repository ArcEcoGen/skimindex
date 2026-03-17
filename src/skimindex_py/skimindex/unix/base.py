"""
Base module for Unix command handling with integrated logging.

Provides a modified local machine instance that captures stderr from executed
commands and sends it to the skimindex logging system, keeping stderr separate
from stdout (data).

Equivalent to bash script's approach:
  - stderr → captured and sent to log.py (loginfo/logwarning/logerror)
  - stdout → untouched (application data)
"""

import os
import subprocess
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
        if hasattr(self._cmd, 'srccmd'):
            return self._run_pipeline(*args, **kwargs)

        # Single command: capture stderr via PIPE and log it.
        stderr_data = None
        try:
            _retcode, stdout, stderr_data = self._cmd.run(
                *args, stderr=subprocess.PIPE, **kwargs
            )
            return stdout
        except Exception as e:
            stderr_data = getattr(e, 'stderr', stderr_data)
            raise
        finally:
            self._log_stderr(stderr_data)

    def _run_pipeline(self, *args, **kwargs):
        """
        Run a plumbum Pipeline without deadlocking on stderr.

        plumbum's Pipeline.popen() propagates stderr=PIPE to every stage.
        Intermediate 64 KB pipes fill up and block if nobody reads them.

        Fix: traverse the Pipeline AST before popen(), wrap each leaf command
        with `cmd >= tmpfile` (plumbum's stderr-to-file redirect), then run the
        modified pipeline normally.  File redirects are applied at the command
        level, so they override the stderr=PIPE that Pipeline.popen() propagates.
        After execution, read and log each temp file, then delete it.

        This approach works for both left- and right-associative pipeline
        compositions, unlike srcproc-chain traversal which only works correctly
        with left-associative chains.
        """
        tmp_paths = []

        def _redirect(cmd):
            """Recursively replace every leaf command's stderr with a temp file."""
            if hasattr(cmd, 'srccmd'):
                return _redirect(cmd.srccmd) | _redirect(cmd.dstcmd)
            fd, path = tempfile.mkstemp(suffix='.stderr')
            os.close(fd)
            tmp_paths.append(path)
            return cmd >= path

        modified = _redirect(self._cmd)
        try:
            result = modified(*args, **kwargs)
        finally:
            for path in tmp_paths:
                try:
                    content = Path(path).read_text(errors='replace')
                    self._log_stderr(content)
                except Exception:
                    pass
                finally:
                    try:
                        os.unlink(path)
                    except Exception:
                        pass
        return result

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

    @staticmethod
    def _log_stderr(text):
        if not text:
            return
        for line in text.strip().split('\n'):
            if line:
                logwarning(line)

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
