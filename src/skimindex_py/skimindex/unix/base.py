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
import threading
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

        Fix: traverse the Pipeline AST before execution to find every leaf
        command; create an os.pipe() per leaf; redirect that leaf's stderr to
        the write end via /dev/fd/N; start a drain thread on the read end.
        Threads log lines via loginfo() in real time.  After the pipeline
        exits the parent closes the write ends so drain threads see EOF.

        AST traversal handles both left- and right-associative compositions
        correctly, unlike walking the srcproc chain after popen().
        """
        write_fds = []
        drain_threads = []

        def _redirect(cmd):
            if hasattr(cmd, 'srccmd'):
                return _redirect(cmd.srccmd) | _redirect(cmd.dstcmd)
            r_fd, w_fd = os.pipe()
            write_fds.append(w_fd)
            t = threading.Thread(
                target=self._drain_stderr,
                args=(os.fdopen(r_fd, 'rb'),),
                daemon=True,
            )
            t.start()
            drain_threads.append(t)
            return cmd >= f'/dev/fd/{w_fd}'

        modified = _redirect(self._cmd)
        try:
            result = modified(*args, **kwargs)
        finally:
            # Close parent's write ends so drain threads see EOF.
            for w_fd in write_fds:
                try:
                    os.close(w_fd)
                except OSError:
                    pass
            for t in drain_threads:
                t.join()
        return result

    @staticmethod
    def _drain_stderr(pipe):
        """Read lines from a pipe and log them via loginfo in real time."""
        try:
            for raw_line in pipe:
                line = raw_line.decode(errors='replace').rstrip('\n')
                if line:
                    loginfo(line)
        except Exception as e:
            logwarning(f"[base] error draining stderr: {e}")
        finally:
            try:
                pipe.close()
            except Exception:
                pass

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
                loginfo(line)

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
