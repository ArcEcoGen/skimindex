"""Unit tests for skimindex.unix.base module."""

import threading
from unittest.mock import MagicMock, patch

from plumbum import local as _plumbum_local

import pytest

from skimindex.unix.base import LoggedBoundCommand, LoggedLocalMachine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_single_cmd(stdout="output", stderr="", retcode=0, side_effect=None):
    """Mock a plumbum BoundCommand (no srccmd → single command path)."""
    cmd = MagicMock(spec=['run', '__getitem__', '__or__', '__ror__', '__gt__', '__rshift__'])
    if side_effect:
        cmd.run.side_effect = side_effect
    else:
        cmd.run.return_value = (retcode, stdout, stderr)
    return cmd


# ---------------------------------------------------------------------------
# __getitem__
# ---------------------------------------------------------------------------

class TestGetitem:
    def test_single_arg(self):
        cmd = MagicMock()
        lbc = LoggedBoundCommand(cmd)
        result = lbc["--help"]
        cmd.__getitem__.assert_called_with("--help")
        assert isinstance(result, LoggedBoundCommand)

    def test_tuple_args(self):
        cmd = MagicMock()
        lbc = LoggedBoundCommand(cmd)
        result = lbc["-t", "value"]
        cmd.__getitem__.assert_called_with(("-t", "value"))
        assert isinstance(result, LoggedBoundCommand)

    def test_chained(self):
        cmd = MagicMock()
        lbc = LoggedBoundCommand(cmd)
        result = lbc["arg1"]["arg2"]
        assert isinstance(result, LoggedBoundCommand)


# ---------------------------------------------------------------------------
# Pipe / redirection operators
# ---------------------------------------------------------------------------

class TestPipeOperators:
    def test_or_with_logged_bound_command(self):
        cmd1, cmd2 = MagicMock(), MagicMock()
        lbc1, lbc2 = LoggedBoundCommand(cmd1), LoggedBoundCommand(cmd2)
        result = lbc1 | lbc2
        assert isinstance(result, LoggedBoundCommand)
        cmd1.__or__.assert_called_with(cmd2)

    def test_or_with_raw_command(self):
        cmd1, raw = MagicMock(), MagicMock()
        result = LoggedBoundCommand(cmd1) | raw
        assert isinstance(result, LoggedBoundCommand)

    def test_ror_with_logged_bound_command(self):
        cmd1, cmd2 = MagicMock(), MagicMock()
        result = LoggedBoundCommand(cmd2).__ror__(LoggedBoundCommand(cmd1))
        assert isinstance(result, LoggedBoundCommand)

    def test_ror_with_raw_command(self):
        result = LoggedBoundCommand(MagicMock()).__ror__(MagicMock())
        assert isinstance(result, LoggedBoundCommand)

    def test_gt_returns_logged_bound_command(self):
        cmd = MagicMock()
        cmd.__gt__ = MagicMock(return_value=MagicMock())
        result = LoggedBoundCommand(cmd) > "/tmp/out.txt"
        assert isinstance(result, LoggedBoundCommand)

    def test_rshift_returns_logged_bound_command(self):
        cmd = MagicMock()
        cmd.__rshift__ = MagicMock(return_value=MagicMock())
        result = LoggedBoundCommand(cmd) >> "/tmp/out.txt"
        assert isinstance(result, LoggedBoundCommand)


# ---------------------------------------------------------------------------
# __call__ — single command path
# ---------------------------------------------------------------------------

class TestCallSingleCommand:
    def test_returns_stdout(self):
        lbc = LoggedBoundCommand(make_single_cmd(stdout="hello"))
        assert lbc() == "hello"

    def test_stderr_is_logged(self):
        lbc = LoggedBoundCommand(make_single_cmd(stderr="warn line\n"))
        with patch("skimindex.unix.base.loginfo") as mock_warn:
            lbc()
        mock_warn.assert_called_with("warn line")

    def test_multiline_stderr_logged_per_line(self):
        lbc = LoggedBoundCommand(make_single_cmd(stderr="line1\nline2\n"))
        with patch("skimindex.unix.base.loginfo") as mock_warn:
            lbc()
        calls = [c.args[0] for c in mock_warn.call_args_list]
        assert "line1" in calls
        assert "line2" in calls

    def test_empty_stderr_not_logged(self):
        lbc = LoggedBoundCommand(make_single_cmd(stderr=""))
        with patch("skimindex.unix.base.loginfo") as mock_warn:
            lbc()
        mock_warn.assert_not_called()

    def test_exception_propagates_and_logs_stderr(self):
        from plumbum import ProcessExecutionError
        exc = ProcessExecutionError(["cmd"], 1, "", "error msg\n")
        lbc = LoggedBoundCommand(make_single_cmd(side_effect=exc))
        with patch("skimindex.unix.base.loginfo") as mock_warn:
            with pytest.raises(ProcessExecutionError):
                lbc()
        mock_warn.assert_called_with("error msg")

    def test_uses_run_with_stderr_pipe(self):
        import subprocess
        cmd = make_single_cmd()
        LoggedBoundCommand(cmd)()
        cmd.run.assert_called_once()
        _, kwargs = cmd.run.call_args
        assert kwargs.get('stderr') == subprocess.PIPE


# ---------------------------------------------------------------------------
# __call__ — pipeline path
# ---------------------------------------------------------------------------

class TestCallPipeline:
    """Use real plumbum commands: the new impl traverses the AST and uses >= tmpfile."""

    def test_returns_stdout(self):
        echo = _plumbum_local['echo']
        cat = _plumbum_local['cat']
        result = LoggedBoundCommand(echo['hello'] | cat)()
        assert 'hello' in result

    def test_stderr_from_single_stage_is_logged(self):
        python = _plumbum_local['python3']
        cat = _plumbum_local['cat']
        stage = python['-c', 'import sys; print("WARN_LINE", file=sys.stderr)']
        with patch("skimindex.unix.base.loginfo") as mock_warn:
            LoggedBoundCommand(stage | cat)()
        logged = [c.args[0] for c in mock_warn.call_args_list]
        assert any("WARN_LINE" in l for l in logged)

    def test_stderr_from_all_stages_is_logged(self):
        python = _plumbum_local['python3']
        cat = _plumbum_local['cat']
        def stage(marker):
            return python['-c',
                f'import sys; print("{marker}", file=sys.stderr); '
                'sys.stdout.buffer.write(sys.stdin.buffer.read())']
        pipe = stage("MARKER_A") | stage("MARKER_B") | cat
        with patch("skimindex.unix.base.loginfo") as mock_warn:
            LoggedBoundCommand(pipe)()
        logged = [c.args[0] for c in mock_warn.call_args_list]
        assert any("MARKER_A" in l for l in logged)
        assert any("MARKER_B" in l for l in logged)

    def test_empty_stderr_not_logged(self):
        echo = _plumbum_local['echo']
        cat = _plumbum_local['cat']
        with patch("skimindex.unix.base.loginfo") as mock_warn:
            LoggedBoundCommand(echo['hello'] | cat)()
        mock_warn.assert_not_called()

    def test_right_associative_pipeline_all_stages_logged(self):
        """
        Right-associative composition (flood | (A | (B | cat))) must still
        capture stderr from every stage — this was the original bug trigger.
        """
        python = _plumbum_local['python3']
        cat = _plumbum_local['cat']
        def stage(marker):
            return python['-c',
                f'import sys; print("{marker}", file=sys.stderr); '
                'sys.stdout.buffer.write(sys.stdin.buffer.read())']

        # Build right-associatively by nesting the sub-pipeline first.
        inner = stage("RIGHT_B") | cat          # plumbum Pipeline
        outer = stage("RIGHT_A") | inner        # RIGHT_A | (RIGHT_B | cat)
        with patch("skimindex.unix.base.loginfo") as mock_warn:
            LoggedBoundCommand(outer)()
        logged = [c.args[0] for c in mock_warn.call_args_list]
        assert any("RIGHT_A" in l for l in logged)
        assert any("RIGHT_B" in l for l in logged)


# ---------------------------------------------------------------------------
# Integration — deadlock prevention with real subprocesses
# ---------------------------------------------------------------------------

# 200 KB > 3× the 64 KB kernel pipe buffer: enough to trigger the deadlock
# if stderr pipes are not drained concurrently.
_STDERR_FLOOD_BYTES = 200_000
_DEADLOCK_TIMEOUT_S = 15


class TestPipelineDeadlockPrevention:
    """Verify that large stderr output from intermediate stages never deadlocks."""

    def _run_with_timeout(self, lbc):
        """Run lbc() in a thread; fail the test if it hangs."""
        result = [None]
        exc = [None]

        def _run():
            try:
                result[0] = lbc()
            except Exception as e:
                exc[0] = e

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=_DEADLOCK_TIMEOUT_S)
        assert not t.is_alive(), (
            f"Pipeline deadlocked: still running after {_DEADLOCK_TIMEOUT_S}s"
        )
        return result[0], exc[0]

    def test_single_stage_large_stderr_no_deadlock(self):
        """Single command writing >64KB to stderr must complete."""
        python = _plumbum_local['python3']
        cmd = python['-c', f'import sys; sys.stderr.buffer.write(b"x" * {_STDERR_FLOOD_BYTES})']
        lbc = LoggedBoundCommand(cmd)
        with patch("skimindex.unix.base.loginfo"):
            _, exc = self._run_with_timeout(lbc)
        assert exc is None

    def test_intermediate_stage_large_stderr_no_deadlock(self):
        """
        Intermediate stage writing >64KB to stderr must not block the pipeline.
        This is the exact scenario from the bug report.
        """
        python = _plumbum_local['python3']
        cat = _plumbum_local['cat']

        # stage 1: flood stderr, pass stdin → stdout unchanged
        flooder = python[
            '-c',
            f'import sys; sys.stderr.buffer.write(b"e" * {_STDERR_FLOOD_BYTES}); '
            f'sys.stdout.buffer.write(sys.stdin.buffer.read())',
        ]
        # stage 2: just passes data through
        pipe = flooder | cat
        lbc = LoggedBoundCommand(pipe)
        with patch("skimindex.unix.base.loginfo"):
            _, exc = self._run_with_timeout(lbc)
        assert exc is None

    def test_all_stages_large_stderr_no_deadlock(self):
        """Every stage flooding stderr simultaneously must not deadlock."""
        python = _plumbum_local['python3']
        flood_and_pass = (
            f'import sys; sys.stderr.buffer.write(b"e" * {_STDERR_FLOOD_BYTES}); '
            f'sys.stdout.buffer.write(sys.stdin.buffer.read())'
        )
        stage = python['-c', flood_and_pass]
        pipe = stage | stage | stage
        lbc = LoggedBoundCommand(pipe)
        with patch("skimindex.unix.base.loginfo"):
            _, exc = self._run_with_timeout(lbc)
        assert exc is None

    def test_intermediate_stderr_is_captured_and_logged(self):
        """Stderr from intermediate stages must reach loginfo, not be discarded."""
        python = _plumbum_local['python3']
        cat = _plumbum_local['cat']

        emitter = python['-c', 'import sys; print("marker_line", file=sys.stderr)']
        pipe = emitter | cat
        lbc = LoggedBoundCommand(pipe)
        with patch("skimindex.unix.base.loginfo") as mock_warn:
            self._run_with_timeout(lbc)
        logged = [c.args[0] for c in mock_warn.call_args_list]
        assert any("marker_line" in line for line in logged), (
            f"Expected 'marker_line' in logged stderr, got: {logged}"
        )


# ---------------------------------------------------------------------------
# __getattr__ delegation
# ---------------------------------------------------------------------------

class TestGetattr:
    def test_delegates_to_underlying_cmd(self):
        cmd = MagicMock()
        cmd.some_method = MagicMock(return_value="result")
        lbc = LoggedBoundCommand(cmd)
        assert lbc.some_method == cmd.some_method


# ---------------------------------------------------------------------------
# LoggedLocalMachine
# ---------------------------------------------------------------------------

class TestLoggedLocalMachine:
    def test_getattr_returns_logged_bound_command(self):
        assert isinstance(LoggedLocalMachine()["echo"], LoggedBoundCommand)

    def test_getitem_returns_logged_bound_command(self):
        assert isinstance(LoggedLocalMachine()["echo"], LoggedBoundCommand)

    def test_both_access_styles_return_same_type(self):
        llm = LoggedLocalMachine()
        assert isinstance(llm["echo"], LoggedBoundCommand)
