"""Unit tests for skimindex.log module."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import skimindex.log as log_mod


@pytest.fixture(autouse=True)
def reset_log_state():
    """Reset global log state before each test."""
    original_level = log_mod.LOG_LEVEL
    original_logfile = log_mod._logfile
    original_mirror = log_mod._mirror_to_stderr
    yield
    log_mod.LOG_LEVEL = original_level
    log_mod._logfile = original_logfile
    log_mod._mirror_to_stderr = original_mirror


class TestLogLevelFiltering:
    def test_setloglevel_debug(self):
        log_mod.setloglevel("DEBUG")
        assert log_mod.LOG_LEVEL == log_mod.LOG_DEBUG_LEVEL

    def test_setloglevel_info(self):
        log_mod.setloglevel("INFO")
        assert log_mod.LOG_LEVEL == log_mod.LOG_INFO_LEVEL

    def test_setloglevel_warning(self):
        log_mod.setloglevel("WARNING")
        assert log_mod.LOG_LEVEL == log_mod.LOG_WARNING_LEVEL

    def test_setloglevel_error(self):
        log_mod.setloglevel("ERROR")
        assert log_mod.LOG_LEVEL == log_mod.LOG_ERROR_LEVEL

    def test_setloglevel_case_insensitive(self):
        log_mod.setloglevel("debug")
        assert log_mod.LOG_LEVEL == log_mod.LOG_DEBUG_LEVEL

    def test_setloglevel_unknown_keeps_level(self):
        log_mod.setloglevel("INFO")
        log_mod.setloglevel("UNKNOWN")
        assert log_mod.LOG_LEVEL == log_mod.LOG_INFO_LEVEL

    def test_debug_suppressed_at_info_level(self, capsys):
        log_mod.LOG_LEVEL = log_mod.LOG_INFO_LEVEL
        log_mod._logfile = None
        with patch.object(log_mod, '_should_use_color', return_value=False):
            log_mod.logdebug("this should not appear")
        captured = capsys.readouterr()
        assert "this should not appear" not in captured.err

    def test_info_shown_at_info_level(self, capsys):
        log_mod.LOG_LEVEL = log_mod.LOG_INFO_LEVEL
        log_mod._logfile = None
        with patch.object(log_mod, '_should_use_color', return_value=False):
            log_mod.loginfo("hello info")
        captured = capsys.readouterr()
        assert "hello info" in captured.err

    def test_warning_shown_at_info_level(self, capsys):
        log_mod.LOG_LEVEL = log_mod.LOG_INFO_LEVEL
        log_mod._logfile = None
        with patch.object(log_mod, '_should_use_color', return_value=False):
            log_mod.logwarning("hello warning")
        captured = capsys.readouterr()
        assert "hello warning" in captured.err

    def test_error_shown_at_info_level(self, capsys):
        log_mod.LOG_LEVEL = log_mod.LOG_INFO_LEVEL
        log_mod._logfile = None
        with patch.object(log_mod, '_should_use_color', return_value=False):
            log_mod.logerror("hello error")
        captured = capsys.readouterr()
        assert "hello error" in captured.err

    def test_info_suppressed_at_warning_level(self, capsys):
        log_mod.LOG_LEVEL = log_mod.LOG_WARNING_LEVEL
        log_mod._logfile = None
        with patch.object(log_mod, '_should_use_color', return_value=False):
            log_mod.loginfo("this should not appear")
        captured = capsys.readouterr()
        assert "this should not appear" not in captured.err


class TestLogFormat:
    def test_log_format_contains_timestamp_and_message(self, capsys):
        log_mod._logfile = None
        with patch.object(log_mod, '_should_use_color', return_value=False):
            log_mod.loginfo("test message")
        captured = capsys.readouterr()
        assert "test message" in captured.err
        assert "--" in captured.err

    def test_log_label_info(self, capsys):
        log_mod._logfile = None
        with patch.object(log_mod, '_should_use_color', return_value=False):
            log_mod.loginfo("msg")
        captured = capsys.readouterr()
        assert "[INFO" in captured.err

    def test_log_label_warning(self, capsys):
        log_mod._logfile = None
        with patch.object(log_mod, '_should_use_color', return_value=False):
            log_mod.logwarning("msg")
        captured = capsys.readouterr()
        assert "[WARNING]" in captured.err

    def test_log_label_error(self, capsys):
        log_mod._logfile = None
        with patch.object(log_mod, '_should_use_color', return_value=False):
            log_mod.logerror("msg")
        captured = capsys.readouterr()
        assert "[ERROR" in captured.err


class TestLogFile:
    def test_openlogfile_writes_to_file(self, tmp_path):
        logfile = str(tmp_path / "test.log")
        log_mod.openlogfile(logfile)
        with patch.object(log_mod, '_should_use_color', return_value=False):
            log_mod.loginfo("written to file")
        log_mod.closelogfile()
        content = Path(logfile).read_text()
        assert "written to file" in content

    def test_openlogfile_strips_ansi_colors(self, tmp_path):
        logfile = str(tmp_path / "test.log")
        log_mod.openlogfile(logfile)
        with patch.object(log_mod, '_should_use_color', return_value=True):
            log_mod.loginfo("colored message")
        log_mod.closelogfile()
        content = Path(logfile).read_text()
        assert "\033[" not in content
        assert "colored message" in content

    def test_openlogfile_appends(self, tmp_path):
        logfile = str(tmp_path / "test.log")
        log_mod.openlogfile(logfile)
        with patch.object(log_mod, '_should_use_color', return_value=False):
            log_mod.loginfo("first line")
        log_mod.closelogfile()
        log_mod.openlogfile(logfile)
        with patch.object(log_mod, '_should_use_color', return_value=False):
            log_mod.loginfo("second line")
        log_mod.closelogfile()
        content = Path(logfile).read_text()
        assert "first line" in content
        assert "second line" in content

    def test_closelogfile_restores_stderr_output(self, capsys, tmp_path):
        logfile = str(tmp_path / "test.log")
        log_mod.openlogfile(logfile)
        log_mod.closelogfile()
        log_mod._logfile = None  # ensure clean state
        with patch.object(log_mod, '_should_use_color', return_value=False):
            log_mod.loginfo("back to stderr")
        captured = capsys.readouterr()
        assert "back to stderr" in captured.err

    def test_mirror_to_stderr(self, capsys, tmp_path):
        logfile = str(tmp_path / "test.log")
        log_mod.openlogfile(logfile, mirror=True)
        with patch.object(log_mod, '_should_use_color', return_value=False):
            log_mod.loginfo("mirrored message")
        log_mod.closelogfile()
        captured = capsys.readouterr()
        assert "mirrored message" in captured.err
