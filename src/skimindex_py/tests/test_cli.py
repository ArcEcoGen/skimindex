"""Unit tests for skimindex.cli — SkimCommand and run_sections."""

import pytest

from skimindex.cli import SkimCommand, run_sections


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cmd(list_items="a,b,c"):
    """Build a minimal SkimCommand with a captured-call handler."""
    calls = []

    cmd = SkimCommand(
        name="test",
        description="Test command",
        list_fn=lambda: list_items,
        examples=["%(prog)s --section foo"],
    )
    cmd.add_argument("--extra", type=int, default=0, help="Extra param")

    @cmd.handler
    def _(sections, args, dry_run):
        calls.append({"sections": sections, "args": args, "dry_run": dry_run})
        return 0

    return cmd, calls


# ---------------------------------------------------------------------------
# SkimCommand — --list
# ---------------------------------------------------------------------------

class TestSkimCommandList:
    def test_list_prints_csv(self, capsys):
        cmd, _ = _make_cmd("x,y,z")
        rc = cmd.main(["--list"])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "x,y,z"

    def test_list_empty_prints_blank(self, capsys):
        cmd, _ = _make_cmd("")
        rc = cmd.main(["--list"])
        assert rc == 0
        assert capsys.readouterr().out.strip() == ""

    def test_list_does_not_call_handler(self):
        cmd, calls = _make_cmd()
        cmd.main(["--list"])
        assert calls == []


# ---------------------------------------------------------------------------
# SkimCommand — --section
# ---------------------------------------------------------------------------

class TestSkimCommandSection:
    def test_section_passed_as_list(self):
        cmd, calls = _make_cmd()
        cmd.main(["--section", "human"])
        assert calls[0]["sections"] == ["human"]

    def test_no_section_passes_none(self):
        cmd, calls = _make_cmd()
        cmd.main([])
        assert calls[0]["sections"] is None


# ---------------------------------------------------------------------------
# SkimCommand — --dry-run
# ---------------------------------------------------------------------------

class TestSkimCommandDryRun:
    def test_dry_run_false_by_default(self):
        cmd, calls = _make_cmd()
        cmd.main([])
        assert calls[0]["dry_run"] is False

    def test_dry_run_true_when_flag(self):
        cmd, calls = _make_cmd()
        cmd.main(["--dry-run"])
        assert calls[0]["dry_run"] is True


# ---------------------------------------------------------------------------
# SkimCommand — extra argument forwarding
# ---------------------------------------------------------------------------

class TestSkimCommandExtraArgs:
    def test_extra_arg_forwarded(self):
        cmd, calls = _make_cmd()
        cmd.main(["--extra", "42"])
        assert calls[0]["args"].extra == 42

    def test_extra_arg_default(self):
        cmd, calls = _make_cmd()
        cmd.main([])
        assert calls[0]["args"].extra == 0


# ---------------------------------------------------------------------------
# SkimCommand — missing handler raises
# ---------------------------------------------------------------------------

class TestSkimCommandNoHandler:
    def test_raises_without_handler(self):
        cmd = SkimCommand(name="bare", description="...", list_fn=lambda: "")
        with pytest.raises(RuntimeError, match="No handler registered"):
            cmd.main([])


# ---------------------------------------------------------------------------
# SkimCommand — handler return code propagated
# ---------------------------------------------------------------------------

class TestSkimCommandReturnCode:
    def test_handler_rc_propagated(self):
        cmd = SkimCommand(name="t", description="...", list_fn=lambda: "")

        @cmd.handler
        def _(sections, args, dry_run):
            return 42

        assert cmd.main([]) == 42


# ---------------------------------------------------------------------------
# run_sections
# ---------------------------------------------------------------------------

class TestRunSections:
    def test_returns_0_when_all_succeed(self):
        assert run_sections("x", ["a", "b"], lambda s: True) == 0

    def test_returns_1_when_any_fails(self):
        assert run_sections("x", ["a", "b"], lambda s: s != "b") == 1

    def test_counts_all_failures(self):
        failed = []
        def fn(s):
            if s in ("b", "c"):
                failed.append(s)
                return False
            return True
        rc = run_sections("x", ["a", "b", "c"], fn)
        assert rc == 1
        assert len(failed) == 2

    def test_dry_run_in_banner(self, capsys):
        import skimindex.log as log_mod
        from unittest.mock import patch
        with patch.object(log_mod, "_logfile", None), \
             patch.object(log_mod, "_should_use_color", return_value=False):
            run_sections("mypipe", ["a"], lambda s: True, dry_run=True)
        out = capsys.readouterr().err
        assert "DRY-RUN" in out

    def test_no_dry_run_label_by_default(self, capsys):
        import skimindex.log as log_mod
        from unittest.mock import patch
        with patch.object(log_mod, "_logfile", None), \
             patch.object(log_mod, "_should_use_color", return_value=False):
            run_sections("mypipe", ["a"], lambda s: True, dry_run=False)
        out = capsys.readouterr().err
        assert "DRY-RUN" not in out

    def test_empty_sections_returns_0(self):
        assert run_sections("x", [], lambda s: True) == 0


# ---------------------------------------------------------------------------
# Integration — _split.main uses SkimCommand correctly
# ---------------------------------------------------------------------------

class TestSplitIntegration:
    def test_list_returns_0(self, capsys):
        from unittest.mock import patch
        from skimindex import _split
        # list_fn is stored by reference in cmd; patch via the object directly.
        with patch.object(_split.cmd, "_list_fn", return_value="human,fungi"):
            rc = _split.main(["--list"])
        assert rc == 0
        assert "human" in capsys.readouterr().out

    def test_dry_run_forwarded(self):
        from unittest.mock import patch
        from skimindex import _split
        # The handler looks up process_split in the _split module's globals.
        with patch("skimindex._split.process_split", return_value=0) as mock_ps:
            _split.main(["--dry-run"])
        mock_ps.assert_called_once()
        assert mock_ps.call_args.kwargs.get("dry_run") is True

    def test_section_forwarded(self):
        from unittest.mock import patch
        from skimindex import _split
        with patch("skimindex._split.process_split", return_value=0) as mock_ps:
            _split.main(["--section", "human"])
        assert mock_ps.call_args.kwargs.get("sections") == ["human"]
