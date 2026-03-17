"""
Integration tests: pipeline stderr stress × openlogfile() configuration.

Each test combines:
  - A real subprocess pipeline that writes large amounts to stderr
    (above the 64 KB kernel pipe buffer that caused the original deadlock)
  - An active log file opened via openlogfile() with varying mirror/everything flags

Implementation note on everything=True
---------------------------------------
Subprocess stderr goes through:
  pipe → drain thread → loginfo() → open(_logfile, 'a')
NOT through fd 2 of the parent process.  So everything=True does not
change how subprocess stderr reaches the log file; it only affects direct
writes to fd 2 / sys.stderr in the Python parent process.
Tests for everything=True therefore validate:
  1. pipelines still complete without deadlock
  2. direct fd-2 writes in the parent are captured
"""

import os
import threading
from pathlib import Path

import pytest
from plumbum import local as _plumbum_local

from skimindex.log import openlogfile, closelogfile
from skimindex.unix.base import LoggedBoundCommand

# ── constants ────────────────────────────────────────────────────────────────

_FLOOD = 150_000   # bytes written to stderr per stage — 3× the 64 KB pipe buffer
_TIMEOUT = 15      # seconds; exceed this → report as deadlock


# ── shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_log_state():
    """Always restore global log state after each test, even on failure."""
    yield
    closelogfile()


def _run(lbc, timeout=_TIMEOUT):
    """Run lbc() in a daemon thread; fail the test if it hangs."""
    result = [None]
    exc = [None]

    def _go():
        try:
            result[0] = lbc()
        except Exception as e:
            exc[0] = e

    t = threading.Thread(target=_go, daemon=True)
    t.start()
    t.join(timeout=timeout)
    assert not t.is_alive(), f"Pipeline deadlocked: still running after {timeout}s"
    return result[0], exc[0]


def _flood_and_pass(flood_bytes=_FLOOD):
    """plumbum command: write flood_bytes to stderr, pass stdin→stdout unchanged."""
    return _plumbum_local['python3'][
        '-c',
        f'import sys; sys.stderr.buffer.write(b"x" * {flood_bytes}); '
        f'sys.stdout.buffer.write(sys.stdin.buffer.read())',
    ]


def _emit_marker(marker):
    """plumbum command: write a known marker line to stderr, pass stdin through."""
    return _plumbum_local['python3'][
        '-c',
        f'import sys; print("{marker}", file=sys.stderr); '
        f'sys.stdout.buffer.write(sys.stdin.buffer.read())',
    ]


# ── mirror=False tests ────────────────────────────────────────────────────────

class TestMirrorFalse:
    """mirror=False: log output goes to file only, not to Python sys.stderr."""

    def test_large_stderr_reaches_log_file(self, tmp_path):
        logfile = tmp_path / "out.log"
        openlogfile(str(logfile), mirror=False, everything=False)

        stage = _flood_and_pass()
        _, exc = _run(LoggedBoundCommand(stage | _plumbum_local['cat']))

        assert exc is None
        assert logfile.stat().st_size > 0

    def test_marker_in_log_file_not_in_stderr(self, tmp_path, capsys):
        logfile = tmp_path / "out.log"
        openlogfile(str(logfile), mirror=False, everything=False)

        stage = _emit_marker("MARKER_MIRROR_FALSE")
        _, exc = _run(LoggedBoundCommand(stage | _plumbum_local['cat']))

        assert exc is None
        captured = capsys.readouterr()
        assert "MARKER_MIRROR_FALSE" in logfile.read_text()
        assert "MARKER_MIRROR_FALSE" not in captured.err

    def test_all_stages_stderr_in_log_file(self, tmp_path):
        logfile = tmp_path / "out.log"
        openlogfile(str(logfile), mirror=False, everything=False)

        cat = _plumbum_local['cat']
        pipe = _emit_marker("STAGE1") | _emit_marker("STAGE2") | cat
        _, exc = _run(LoggedBoundCommand(pipe))

        assert exc is None
        content = logfile.read_text()
        assert "STAGE1" in content
        assert "STAGE2" in content

    def test_stress_three_stages_no_deadlock(self, tmp_path):
        logfile = tmp_path / "out.log"
        openlogfile(str(logfile), mirror=False, everything=False)

        stage = _flood_and_pass()
        _, exc = _run(LoggedBoundCommand(stage | stage | stage))

        assert exc is None
        assert logfile.stat().st_size > 0


# ── mirror=True tests ─────────────────────────────────────────────────────────

class TestMirrorTrue:
    """mirror=True: log output goes to file AND Python sys.stderr."""

    def test_marker_in_both_log_file_and_stderr(self, tmp_path, capsys):
        logfile = tmp_path / "out.log"
        openlogfile(str(logfile), mirror=True, everything=False)

        stage = _emit_marker("MARKER_MIRROR_TRUE")
        _, exc = _run(LoggedBoundCommand(stage | _plumbum_local['cat']))

        assert exc is None
        captured = capsys.readouterr()
        assert "MARKER_MIRROR_TRUE" in logfile.read_text()
        assert "MARKER_MIRROR_TRUE" in captured.err

    def test_stress_large_stderr_no_deadlock(self, tmp_path):
        logfile = tmp_path / "out.log"
        openlogfile(str(logfile), mirror=True, everything=False)

        stage = _flood_and_pass()
        _, exc = _run(LoggedBoundCommand(stage | stage | stage))

        assert exc is None
        assert logfile.stat().st_size > 0

    def test_stress_all_stages_flood_content_in_log(self, tmp_path):
        """Even under heavy load, no log line must be silently dropped."""
        logfile = tmp_path / "out.log"
        openlogfile(str(logfile), mirror=True, everything=False)

        cat = _plumbum_local['cat']
        # Build left-associatively so all leaf commands are at the same AST level.
        pipe = _flood_and_pass() | _emit_marker("FLOOD_STAGE_A") | _emit_marker("FLOOD_STAGE_B") | cat
        _, exc = _run(LoggedBoundCommand(pipe))

        assert exc is None
        content = logfile.read_text()
        assert "FLOOD_STAGE_A" in content
        assert "FLOOD_STAGE_B" in content


# ── everything=False tests ────────────────────────────────────────────────────

class TestEverythingFalse:
    """everything=False: fd 2 is not redirected; subprocess stderr via logwarning()."""

    def test_pipeline_stderr_in_log_file(self, tmp_path):
        logfile = tmp_path / "out.log"
        openlogfile(str(logfile), mirror=False, everything=False)

        stage = _emit_marker("EVERYTHING_FALSE_MARKER")
        _, exc = _run(LoggedBoundCommand(stage | _plumbum_local['cat']))

        assert exc is None
        assert "EVERYTHING_FALSE_MARKER" in logfile.read_text()

    def test_stress_no_deadlock(self, tmp_path):
        logfile = tmp_path / "out.log"
        openlogfile(str(logfile), mirror=False, everything=False)

        stage = _flood_and_pass()
        _, exc = _run(LoggedBoundCommand(stage | stage | stage))

        assert exc is None

    def test_direct_fd2_write_does_not_go_to_log_file(self, tmp_path):
        """With everything=False, direct os.write(2, ...) bypasses the log file."""
        logfile = tmp_path / "out.log"
        openlogfile(str(logfile), mirror=False, everything=False)

        os.write(2, b"SHOULD_NOT_BE_IN_LOG\n")

        closelogfile()
        content = logfile.read_text()
        assert "SHOULD_NOT_BE_IN_LOG" not in content


# ── everything=True tests ─────────────────────────────────────────────────────

class TestEverythingTrue:
    """everything=True: fd 2 is redirected to the log file."""

    def test_direct_fd2_write_goes_to_log_file(self, tmp_path):
        """os.write(2, ...) in the parent process must appear in the log file."""
        logfile = tmp_path / "out.log"
        openlogfile(str(logfile), mirror=False, everything=True)

        os.write(2, b"DIRECT_FD2_WRITE\n")
        os.fsync(2)  # flush the kernel buffer to the file

        closelogfile()
        assert "DIRECT_FD2_WRITE" in logfile.read_text()

    def test_pipeline_stderr_still_in_log_file(self, tmp_path):
        """Pipeline subprocess stderr still reaches the log file (via logwarning path)."""
        logfile = tmp_path / "out.log"
        openlogfile(str(logfile), mirror=False, everything=True)

        stage = _emit_marker("EVERYTHING_TRUE_MARKER")
        _, exc = _run(LoggedBoundCommand(stage | _plumbum_local['cat']))

        assert exc is None
        assert "EVERYTHING_TRUE_MARKER" in logfile.read_text()

    def test_stress_large_stderr_no_deadlock(self, tmp_path):
        logfile = tmp_path / "out.log"
        openlogfile(str(logfile), mirror=True, everything=True)

        stage = _flood_and_pass()
        _, exc = _run(LoggedBoundCommand(stage | stage | stage))

        assert exc is None
        assert logfile.stat().st_size > 0

    def test_fd2_restored_after_close(self, tmp_path):
        """After closelogfile(), fd 2 must be restored to original stderr."""
        logfile = tmp_path / "out.log"
        fd2_before = os.dup(2)  # save a copy of fd 2 before

        openlogfile(str(logfile), mirror=False, everything=True)
        closelogfile()

        # After close, fd 2 and our saved copy should refer to the same file.
        stat_fd2 = os.fstat(2)
        stat_saved = os.fstat(fd2_before)
        os.close(fd2_before)
        assert stat_fd2.st_ino == stat_saved.st_ino


# ── combined stress matrix ────────────────────────────────────────────────────

class TestCombinedStressMatrix:
    """Exhaustive (mirror × everything) × flood: every combination must complete."""

    @pytest.mark.parametrize("mirror,everything", [
        (False, False),
        (True,  False),
        (False, True),
        (True,  True),
    ])
    def test_flood_completes_for_all_combinations(self, tmp_path, mirror, everything):
        logfile = tmp_path / f"m{mirror}_e{everything}.log"
        openlogfile(str(logfile), mirror=mirror, everything=everything)

        stage = _flood_and_pass()
        _, exc = _run(LoggedBoundCommand(stage | stage | stage))

        assert exc is None, f"Exception with mirror={mirror} everything={everything}: {exc}"
        assert logfile.stat().st_size > 0
