"""Unit tests for skimindex.stamp module."""

import os
import time
from pathlib import Path

import pytest

import skimindex.stamp as stamp_mod
from skimindex.stamp import (
    _stamp_path,
    is_stamped,
    newer_than_stamp,
    remove_if_not_stamped,
    stamp,
    unstamp,
    unstamp_if_newer,
)


@pytest.fixture(autouse=True)
def isolated_stamp_root(tmp_path, monkeypatch):
    """Redirect STAMP_ROOT to a temp directory for every test."""
    stamp_root = tmp_path / "stamp"
    stamp_root.mkdir()
    monkeypatch.setattr(stamp_mod, "STAMP_ROOT", stamp_root)
    return stamp_root


@pytest.fixture()
def missing_stamp_root(tmp_path, monkeypatch):
    """STAMP_ROOT points to a non-existent directory."""
    stamp_root = tmp_path / "stamp_does_not_exist"
    monkeypatch.setattr(stamp_mod, "STAMP_ROOT", stamp_root)
    return stamp_root


# ---------------------------------------------------------------------------
# Missing STAMP_ROOT
# ---------------------------------------------------------------------------

class TestMissingStampRoot:
    def test_is_stamped_returns_false(self, missing_stamp_root, tmp_path):
        assert not is_stamped(tmp_path / "output")

    def test_newer_than_stamp_returns_false(self, missing_stamp_root, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("data")
        assert not newer_than_stamp(src, tmp_path / "output")

    def test_unstamp_is_noop(self, missing_stamp_root, tmp_path):
        unstamp(tmp_path / "output")  # must not raise

    def test_unstamp_if_newer_is_noop(self, missing_stamp_root, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("data")
        assert not unstamp_if_newer(tmp_path / "output", src)

    def test_stamp_creates_root(self, missing_stamp_root, tmp_path):
        target = tmp_path / "output"
        stamp(target)
        assert is_stamped(target)
        assert missing_stamp_root.exists()


# ---------------------------------------------------------------------------
# _stamp_path
# ---------------------------------------------------------------------------

class TestStampPath:
    def test_mirrors_absolute_path(self, tmp_path):
        target = tmp_path / "some" / "output"
        sp = _stamp_path(target)
        assert sp == stamp_mod.STAMP_ROOT / (str(target).lstrip("/") + ".stamp")

    def test_ends_with_stamp_suffix(self, tmp_path):
        sp = _stamp_path(tmp_path / "foo")
        assert sp.suffix == ".stamp"

    def test_two_different_paths_give_different_stamps(self, tmp_path):
        assert _stamp_path(tmp_path / "a") != _stamp_path(tmp_path / "b")


# ---------------------------------------------------------------------------
# stamp / is_stamped / unstamp
# ---------------------------------------------------------------------------

class TestStampIsStampedUnstamp:
    def test_not_stamped_initially(self, tmp_path):
        assert not is_stamped(tmp_path / "output")

    def test_stamped_after_stamp(self, tmp_path):
        target = tmp_path / "output"
        stamp(target)
        assert is_stamped(target)

    def test_stamp_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "deep" / "nested" / "output"
        stamp(target)
        assert _stamp_path(target).exists()

    def test_unstamp_removes_stamp(self, tmp_path):
        target = tmp_path / "output"
        stamp(target)
        unstamp(target)
        assert not is_stamped(target)

    def test_unstamp_nonexistent_is_noop(self, tmp_path):
        unstamp(tmp_path / "never_stamped")  # must not raise

    def test_stamp_updates_mtime(self, tmp_path):
        target = tmp_path / "output"
        stamp(target)
        mtime1 = _stamp_path(target).stat().st_mtime
        time.sleep(0.05)
        stamp(target)
        mtime2 = _stamp_path(target).stat().st_mtime
        assert mtime2 >= mtime1


# ---------------------------------------------------------------------------
# newer_than_stamp
# ---------------------------------------------------------------------------

class TestNewerThanStamp:
    def test_returns_false_when_no_stamp(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("data")
        assert not newer_than_stamp(src, tmp_path / "output")

    def test_older_source_returns_false(self, tmp_path):
        output = tmp_path / "output"
        src = tmp_path / "src.txt"
        src.write_text("data")
        time.sleep(0.05)
        stamp(output)
        assert not newer_than_stamp(src, output)

    def test_newer_source_returns_true(self, tmp_path):
        output = tmp_path / "output"
        stamp(output)
        time.sleep(0.05)
        src = tmp_path / "src.txt"
        src.write_text("data")
        assert newer_than_stamp(src, output)

    def test_missing_source_returns_false(self, tmp_path):
        output = tmp_path / "output"
        stamp(output)
        assert not newer_than_stamp(tmp_path / "missing.txt", output)

    def test_directory_with_newer_file_returns_true(self, tmp_path):
        output = tmp_path / "output"
        stamp(output)
        time.sleep(0.05)
        src_dir = tmp_path / "src_dir"
        src_dir.mkdir()
        (src_dir / "file.txt").write_text("data")
        assert newer_than_stamp(src_dir, output)

    def test_directory_with_older_files_returns_false(self, tmp_path):
        src_dir = tmp_path / "src_dir"
        src_dir.mkdir()
        (src_dir / "file.txt").write_text("data")
        time.sleep(0.05)
        output = tmp_path / "output"
        stamp(output)
        assert not newer_than_stamp(src_dir, output)

    def test_directory_checked_recursively(self, tmp_path):
        output = tmp_path / "output"
        stamp(output)
        time.sleep(0.05)
        src_dir = tmp_path / "src_dir" / "sub"
        src_dir.mkdir(parents=True)
        (src_dir / "deep.txt").write_text("data")
        assert newer_than_stamp(tmp_path / "src_dir", output)

    def test_empty_directory_returns_false(self, tmp_path):
        output = tmp_path / "output"
        stamp(output)
        src_dir = tmp_path / "empty_dir"
        src_dir.mkdir()
        assert not newer_than_stamp(src_dir, output)


# ---------------------------------------------------------------------------
# unstamp_if_newer
# ---------------------------------------------------------------------------

class TestUnstampIfNewer:
    def test_no_stamp_does_nothing(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("data")
        assert not unstamp_if_newer(tmp_path / "output", src)

    def test_older_sources_do_not_unstamp(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("data")
        time.sleep(0.05)
        output = tmp_path / "output"
        stamp(output)
        assert not unstamp_if_newer(output, src)
        assert is_stamped(output)

    def test_newer_source_unstamps(self, tmp_path):
        output = tmp_path / "output"
        stamp(output)
        time.sleep(0.05)
        src = tmp_path / "src.txt"
        src.write_text("data")
        assert unstamp_if_newer(output, src)
        assert not is_stamped(output)

    def test_any_newer_source_triggers_unstamp(self, tmp_path):
        old_src = tmp_path / "old.txt"
        old_src.write_text("old")
        output = tmp_path / "output"
        time.sleep(0.05)
        stamp(output)
        time.sleep(0.05)
        new_src = tmp_path / "new.txt"
        new_src.write_text("new")
        assert unstamp_if_newer(output, old_src, new_src)
        assert not is_stamped(output)

    def test_directory_source_checked_recursively(self, tmp_path):
        output = tmp_path / "output"
        stamp(output)
        time.sleep(0.05)
        src_dir = tmp_path / "src" / "sub"
        src_dir.mkdir(parents=True)
        (src_dir / "file.txt").write_text("data")
        assert unstamp_if_newer(output, tmp_path / "src")
        assert not is_stamped(output)


# ---------------------------------------------------------------------------
# remove_if_not_stamped
# ---------------------------------------------------------------------------

class TestRemoveIfNotStamped:
    def test_removes_unstamped_file(self, tmp_path):
        f = tmp_path / "partial.txt"
        f.write_text("partial")
        assert remove_if_not_stamped(f)
        assert not f.exists()

    def test_removes_unstamped_directory(self, tmp_path):
        d = tmp_path / "partial_dir"
        d.mkdir()
        (d / "file.txt").write_text("data")
        assert remove_if_not_stamped(d)
        assert not d.exists()

    def test_does_not_remove_stamped_path(self, tmp_path):
        f = tmp_path / "output.txt"
        f.write_text("done")
        stamp(f)
        assert not remove_if_not_stamped(f)
        assert f.exists()

    def test_returns_false_when_path_missing(self, tmp_path):
        assert not remove_if_not_stamped(tmp_path / "nonexistent")

    def test_removes_nested_directory_tree(self, tmp_path):
        d = tmp_path / "deep"
        (d / "sub").mkdir(parents=True)
        (d / "sub" / "file.txt").write_text("data")
        assert remove_if_not_stamped(d)
        assert not d.exists()
