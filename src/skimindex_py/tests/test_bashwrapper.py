"""Unit tests for skimindex.bashwrapper."""

import sys
import types
import pytest

from skimindex.bashwrapper import (
    bash_export,
    dispatch,
    generate_bash,
    _exported_functions,
    _build_parser,
    _annotation_to_argparse_type,
)


# ---------------------------------------------------------------------------
# Minimal test module — standalone functions, no real imports needed
# ---------------------------------------------------------------------------

@bash_export
def _greet(name: str) -> str:
    """Say hello to someone."""
    return f"Hello, {name}!"


@bash_export
def _add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@bash_export
def _flag_test(*, verbose: bool = False, label: str = "") -> bool:
    """Return True when verbose is set."""
    return verbose


@bash_export
def _variadic(first: str, *rest: str) -> str:
    """Join all arguments."""
    return " ".join([first, *rest])


@bash_export
def _always_true() -> bool:
    """Always returns True."""
    return True


@bash_export
def _always_false() -> bool:
    """Always returns False."""
    return False


@bash_export
def _returns_none() -> None:
    """Returns nothing."""
    return None


def _not_exported() -> str:
    """Not tagged — must be invisible to bashwrapper."""
    return "secret"


# Build a fake module containing our test functions
_TEST_MODULE = types.ModuleType("test_fake_module")
_TEST_MODULE.__name__ = "test_fake_module"
for _name in [
    "_greet", "_add", "_flag_test", "_variadic",
    "_always_true", "_always_false", "_returns_none", "_not_exported",
]:
    setattr(_TEST_MODULE, _name, globals()[_name])


# ---------------------------------------------------------------------------
# bash_export decorator
# ---------------------------------------------------------------------------

class TestBashExport:
    def test_attribute_set(self):
        assert getattr(_greet, "_bash_export", False) is True

    def test_function_unchanged(self):
        assert _greet("world") == "Hello, world!"

    def test_untagged_has_no_attribute(self):
        assert not getattr(_not_exported, "_bash_export", False)


# ---------------------------------------------------------------------------
# _exported_functions
# ---------------------------------------------------------------------------

class TestExportedFunctions:
    def test_returns_only_tagged(self):
        names = {n for n, _ in _exported_functions(_TEST_MODULE)}
        assert "_not_exported" not in names

    def test_returns_all_tagged(self):
        names = {n for n, _ in _exported_functions(_TEST_MODULE)}
        assert {"_greet", "_add", "_flag_test", "_variadic",
                "_always_true", "_always_false", "_returns_none"} <= names

    def test_returns_callables(self):
        for _, fn in _exported_functions(_TEST_MODULE):
            assert callable(fn)


# ---------------------------------------------------------------------------
# _annotation_to_argparse_type
# ---------------------------------------------------------------------------

class TestAnnotationToArgparseType:
    def test_int(self):
        assert _annotation_to_argparse_type(int) is int

    def test_float(self):
        assert _annotation_to_argparse_type(float) is float

    def test_str(self):
        assert _annotation_to_argparse_type(str) is str

    def test_none_falls_back_to_str(self):
        assert _annotation_to_argparse_type(None) is str

    def test_unknown_falls_back_to_str(self):
        assert _annotation_to_argparse_type(list) is str


# ---------------------------------------------------------------------------
# _build_parser
# ---------------------------------------------------------------------------

class TestBuildParser:
    def test_positional_args(self):
        parser = _build_parser(_add)
        ns = parser.parse_args(["3", "4"])
        assert ns.a == 3
        assert ns.b == 4

    def test_bool_flag_default_false(self):
        parser = _build_parser(_flag_test)
        ns = parser.parse_args([])
        assert ns.verbose is False

    def test_bool_flag_set(self):
        parser = _build_parser(_flag_test)
        ns = parser.parse_args(["--verbose"])
        assert ns.verbose is True

    def test_string_keyword(self):
        parser = _build_parser(_flag_test)
        ns = parser.parse_args(["--label", "human"])
        assert ns.label == "human"

    def test_variadic(self):
        parser = _build_parser(_variadic)
        ns = parser.parse_args(["a", "b", "c"])
        assert ns.first == "a"
        assert ns.rest == ["b", "c"]

    def test_variadic_empty_rest(self):
        parser = _build_parser(_variadic)
        ns = parser.parse_args(["a"])
        assert ns.rest == []

    def test_bash_name_in_prog(self):
        parser = _build_parser(_greet, bash_name="ski_greet")
        assert "ski_greet" in parser.prog

    def test_no_bash_name_uses_python_call(self):
        parser = _build_parser(_greet)
        assert "python3 -m" in parser.prog

    def test_docstring_as_description(self):
        parser = _build_parser(_greet)
        assert "Say hello" in parser.description

    def test_union_none_unwrapped(self):
        """Path | None annotation should not cause a crash."""
        from pathlib import Path

        @bash_export
        def _optional_path(p: Path | None = None) -> bool:
            return p is not None

        # Should not raise
        parser = _build_parser(_optional_path)
        ns = parser.parse_args(["/tmp"])
        assert ns.p == "/tmp"


# ---------------------------------------------------------------------------
# generate_bash
# ---------------------------------------------------------------------------

class TestGenerateBash:
    def setup_method(self):
        self.script = generate_bash(_TEST_MODULE, prefix="ski")

    def test_contains_wrapper_for_each_exported(self):
        for name, _ in _exported_functions(_TEST_MODULE):
            assert f"ski_{name}()" in self.script

    def test_does_not_contain_unexported(self):
        assert "ski__not_exported" not in self.script

    def test_calls_python_module(self):
        assert "python3 -m test_fake_module" in self.script

    def test_passes_all_args(self):
        assert '"$@"' in self.script

    def test_includes_docstring_first_line(self):
        assert "Say hello to someone." in self.script

    def test_custom_prefix(self):
        script = generate_bash(_TEST_MODULE, prefix="myprefix")
        assert "myprefix__greet()" in script
        assert "ski__greet()" not in script


# ---------------------------------------------------------------------------
# dispatch — return value → exit code
# ---------------------------------------------------------------------------

class TestDispatchReturnCodes:
    def test_bool_true_returns_0(self):
        assert dispatch(_TEST_MODULE, "_always_true", []) == 0

    def test_bool_false_returns_1(self):
        assert dispatch(_TEST_MODULE, "_always_false", []) == 1

    def test_none_returns_0(self):
        assert dispatch(_TEST_MODULE, "_returns_none", []) == 0

    def test_int_return_clamped(self):
        @bash_export
        def _big() -> int:
            return 200

        mod = types.ModuleType("m")
        mod._big = _big
        assert dispatch(mod, "_big", []) == 127

    def test_int_return_negative_clamped_to_0(self):
        @bash_export
        def _neg() -> int:
            return -1

        mod = types.ModuleType("m")
        mod._neg = _neg
        assert dispatch(mod, "_neg", []) == 0

    def test_str_result_printed(self, capsys):
        dispatch(_TEST_MODULE, "_greet", ["world"])
        assert capsys.readouterr().out.strip() == "Hello, world!"


# ---------------------------------------------------------------------------
# dispatch — argument parsing
# ---------------------------------------------------------------------------

class TestDispatchArgParsing:
    def test_positional_int(self):
        assert dispatch(_TEST_MODULE, "_add", ["3", "4"]) == 7  # int return → clamped

    def test_bool_flag(self):
        assert dispatch(_TEST_MODULE, "_flag_test", ["--verbose"]) == 0

    def test_bool_flag_absent(self):
        assert dispatch(_TEST_MODULE, "_flag_test", []) == 1

    def test_variadic_joined(self, capsys):
        dispatch(_TEST_MODULE, "_variadic", ["hello", "world", "!"])
        assert capsys.readouterr().out.strip() == "hello world !"

    def test_unknown_function(self, capsys):
        code = dispatch(_TEST_MODULE, "nonexistent", [])
        assert code == 2
        assert "nonexistent" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# dispatch — error handling
# ---------------------------------------------------------------------------

class TestDispatchErrors:
    def test_function_exception_returns_1(self, capsys):
        @bash_export
        def _raises(x: str) -> bool:
            raise ValueError("boom")

        mod = types.ModuleType("m")
        mod._raises = _raises
        code = dispatch(mod, "_raises", ["x"])
        assert code == 1
        assert "boom" in capsys.readouterr().err

    def test_help_exits_0(self):
        with pytest.raises(SystemExit) as exc:
            dispatch(_TEST_MODULE, "_greet", ["--help"])
        assert exc.value.code == 0

    def test_bad_args_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            dispatch(_TEST_MODULE, "_add", ["not_an_int", "2"])
        assert exc.value.code == 2
