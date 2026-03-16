"""Unit tests for skimindex.unix.base module."""

from unittest.mock import MagicMock, patch, call
from pathlib import Path
import tempfile

import pytest

from skimindex.unix.base import LoggedBoundCommand, LoggedLocalMachine


def make_cmd(stdout="output", side_effect=None):
    """Create a mock plumbum command that has with_stderr."""
    cmd = MagicMock()
    cmd.with_stderr.return_value = cmd
    if side_effect:
        cmd.side_effect = side_effect
    else:
        cmd.return_value = stdout
    cmd.__or__ = MagicMock(return_value=MagicMock())
    return cmd


def make_pipeline():
    """Create a mock pipeline (no with_stderr attribute)."""
    pipeline = MagicMock(spec=[])  # spec=[] means no attributes defined
    pipeline.return_value = "pipeline output"
    return pipeline


class TestLoggedBoundCommandGetitem:
    def test_getitem_single_arg(self):
        cmd = make_cmd()
        lbc = LoggedBoundCommand(cmd)
        result = lbc["--help"]
        cmd.__getitem__.assert_called_with("--help")
        assert isinstance(result, LoggedBoundCommand)

    def test_getitem_tuple_args(self):
        cmd = make_cmd()
        lbc = LoggedBoundCommand(cmd)
        result = lbc["-t", "value"]
        cmd.__getitem__.assert_called_with(("-t", "value"))
        assert isinstance(result, LoggedBoundCommand)

    def test_chained_getitem(self):
        cmd = make_cmd()
        child_cmd = make_cmd()
        cmd.__getitem__ = MagicMock(return_value=child_cmd)
        lbc = LoggedBoundCommand(cmd)
        result = lbc["arg1"]["arg2"]
        assert isinstance(result, LoggedBoundCommand)


class TestLoggedBoundCommandPipe:
    def test_or_with_logged_bound_command(self):
        cmd1 = make_cmd()
        cmd2 = make_cmd()
        lbc1 = LoggedBoundCommand(cmd1)
        lbc2 = LoggedBoundCommand(cmd2)
        result = lbc1 | lbc2
        assert isinstance(result, LoggedBoundCommand)
        cmd1.__or__.assert_called_with(cmd2)

    def test_or_with_raw_command(self):
        cmd1 = make_cmd()
        raw_cmd = MagicMock()
        lbc = LoggedBoundCommand(cmd1)
        result = lbc | raw_cmd
        assert isinstance(result, LoggedBoundCommand)

    def test_ror_with_logged_bound_command(self):
        cmd1 = make_cmd()
        cmd2 = make_cmd()
        lbc1 = LoggedBoundCommand(cmd1)
        lbc2 = LoggedBoundCommand(cmd2)
        result = lbc2.__ror__(lbc1)
        assert isinstance(result, LoggedBoundCommand)

    def test_ror_with_raw_command(self):
        cmd = make_cmd()
        raw_cmd = MagicMock()
        lbc = LoggedBoundCommand(cmd)
        result = lbc.__ror__(raw_cmd)
        assert isinstance(result, LoggedBoundCommand)


class TestLoggedBoundCommandRedirection:
    def test_gt_returns_logged_bound_command(self):
        cmd = make_cmd()
        cmd.__gt__ = MagicMock(return_value=MagicMock())
        lbc = LoggedBoundCommand(cmd)
        result = lbc > "/tmp/out.txt"
        assert isinstance(result, LoggedBoundCommand)

    def test_rshift_returns_logged_bound_command(self):
        cmd = make_cmd()
        cmd.__rshift__ = MagicMock(return_value=MagicMock())
        lbc = LoggedBoundCommand(cmd)
        result = lbc >> "/tmp/out.txt"
        assert isinstance(result, LoggedBoundCommand)


class TestLoggedBoundCommandCall:
    def test_call_with_with_stderr_captures_stderr(self, tmp_path):
        """Command with with_stderr uses temp file for stderr capture."""
        cmd = MagicMock()
        cmd.with_stderr.return_value = cmd
        cmd.return_value = "hello"
        lbc = LoggedBoundCommand(cmd)
        result = lbc()
        assert result == "hello"
        cmd.with_stderr.assert_called_once()

    def test_call_without_with_stderr_executes_directly(self):
        """Pipeline-like commands without with_stderr execute directly."""
        pipeline = MagicMock(spec=["__call__"])
        pipeline.return_value = "pipeline output"
        lbc = LoggedBoundCommand(pipeline)
        result = lbc()
        assert result == "pipeline output"
        pipeline.assert_called_once()

    def test_call_logs_stderr_content(self, tmp_path):
        """Stderr content is passed to logwarning."""
        def fake_with_stderr(path):
            Path(path).write_text("stderr line\n")
            return cmd
        cmd = MagicMock()
        cmd.with_stderr.side_effect = fake_with_stderr
        cmd.return_value = "stdout"
        lbc = LoggedBoundCommand(cmd)
        with patch("skimindex.unix.base.logwarning") as mock_warn:
            lbc()
        mock_warn.assert_called_with("stderr line")

    def test_call_exception_still_logs_stderr(self):
        """On exception, stderr is still logged before re-raise."""
        def fake_with_stderr(path):
            Path(path).write_text("error output\n")
            return inner
        inner = MagicMock(side_effect=RuntimeError("boom"))
        cmd = MagicMock()
        cmd.with_stderr.side_effect = fake_with_stderr
        lbc = LoggedBoundCommand(cmd)
        with patch("skimindex.unix.base.logwarning") as mock_warn:
            with pytest.raises(RuntimeError, match="boom"):
                lbc()
        mock_warn.assert_called_with("error output")

    def test_call_cleans_up_stderr_tempfile(self):
        """Temp stderr file is deleted after execution."""
        created_paths = []
        original_ntf = tempfile.NamedTemporaryFile

        def tracking_ntf(*args, **kwargs):
            f = original_ntf(*args, **kwargs)
            created_paths.append(f.name)
            return f

        cmd = MagicMock()
        cmd.with_stderr.return_value = cmd
        cmd.return_value = "ok"
        lbc = LoggedBoundCommand(cmd)
        with patch("skimindex.unix.base.tempfile.NamedTemporaryFile", side_effect=tracking_ntf):
            lbc()

        for p in created_paths:
            assert not Path(p).exists(), f"Temp file not cleaned up: {p}"

    def test_empty_stderr_not_logged(self):
        """Empty stderr produces no log warnings."""
        cmd = MagicMock()
        cmd.with_stderr.return_value = cmd
        cmd.return_value = "output"
        lbc = LoggedBoundCommand(cmd)
        with patch("skimindex.unix.base.logwarning") as mock_warn:
            lbc()
        mock_warn.assert_not_called()


class TestLoggedBoundCommandGetattr:
    def test_getattr_delegates_to_underlying_cmd(self):
        cmd = MagicMock()
        cmd.some_method = MagicMock(return_value="result")
        lbc = LoggedBoundCommand(cmd)
        assert lbc.some_method == cmd.some_method


class TestLoggedLocalMachine:
    def test_getattr_returns_logged_bound_command(self):
        """llm.echo wraps the plumbum command in LoggedBoundCommand."""
        llm = LoggedLocalMachine()
        result = llm["echo"]
        assert isinstance(result, LoggedBoundCommand)

    def test_getitem_returns_logged_bound_command(self):
        """llm['echo'] wraps the plumbum command in LoggedBoundCommand."""
        llm = LoggedLocalMachine()
        result = llm["echo"]
        assert isinstance(result, LoggedBoundCommand)

    def test_getitem_and_getattr_return_same_type(self):
        """Both access styles return LoggedBoundCommand."""
        llm = LoggedLocalMachine()
        assert isinstance(llm["echo"], LoggedBoundCommand)
