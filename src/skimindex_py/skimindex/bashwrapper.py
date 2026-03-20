"""
skimindex.bashwrapper — generate bash wrappers for Python functions.

Decorators
----------
bash_export
    Tag a function for bash wrapper generation.  The function must have
    a signature made of only positional, VAR_POSITIONAL (*args), and
    keyword-only parameters.  Return type should be bool, int, str, or None.

Module-level API
----------------
generate_bash(module, prefix)
    Return a bash script (string) that defines one shell function per
    @bash_export-tagged function in *module*.  Each shell function calls
    ``python3 -m <module_name> <fn_name> "$@"`` and propagates the exit
    code.  Intended to be eval'd by the sourcing bash script.

dispatch(module, fn_name, argv)
    Look up a @bash_export function in *module* by name, parse *argv*
    (list[str]) using an argparse.ArgumentParser derived from its
    signature, call the function, and return a POSIX exit code:
      - bool True  → 0
      - bool False → 1
      - int        → value (clamped 0-127)
      - str        → printed to stdout, exit 0
      - None       → exit 0

Type mapping (argv string → Python)
------------------------------------
Parameter annotation  | argparse action / type
--------------------- | ----------------------
bool (keyword-only)   | store_true flag (--name / --no-name)
int                   | type=int
float                 | type=float
str / PathLike / None | type=str (Path accepts str)
*args (VAR_POSITIONAL)| nargs='*'
"""

import argparse
import inspect
import sys
import types
from collections.abc import Callable
from typing import Any, get_type_hints


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------

def bash_export(fn: Callable) -> Callable:
    """Mark a function as exportable to bash.

    The decorated function is unchanged; the attribute ``_bash_export = True``
    is added so that :func:`generate_bash` and :func:`dispatch` can find it.
    """
    fn._bash_export = True
    return fn


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _exported_functions(module) -> list[tuple[str, Callable]]:
    """Return (name, fn) pairs for all @bash_export functions in *module*."""
    return [
        (name, fn)
        for name, fn in inspect.getmembers(module, inspect.isfunction)
        if getattr(fn, "_bash_export", False)
    ]


def _safe_hints(fn: Callable) -> dict[str, Any]:
    """Return type hints, falling back to {} if evaluation fails."""
    try:
        return get_type_hints(fn)
    except Exception:
        return {}


def _annotation_to_argparse_type(annotation: Any):
    """Convert a type annotation to an argparse *type* callable (or None)."""
    if annotation in (int,):
        return int
    if annotation in (float,):
        return float
    # str, Path, PathLike (type alias), None, inspect.Parameter.empty → str
    return str


def _build_parser(fn: Callable, bash_name: str | None = None) -> argparse.ArgumentParser:
    """Build an ArgumentParser from the signature of *fn*."""
    sig = inspect.signature(fn)
    hints = _safe_hints(fn)
    prog = bash_name or f"python3 -m {fn.__module__} {fn.__name__}"
    parser = argparse.ArgumentParser(
        prog=prog,
        description=inspect.cleandoc(fn.__doc__ or ""),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    for param in sig.parameters.values():
        ann = hints.get(param.name, str)
        # Unwrap simple unions like `X | None` → X
        origin = getattr(ann, "__origin__", None)
        if origin is types.UnionType:
            non_none = [a for a in ann.__args__ if a is not type(None)]
            ann = non_none[0] if non_none else str

        if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
            parser.add_argument(param.name, type=_annotation_to_argparse_type(ann))

        elif param.kind == param.VAR_POSITIONAL:
            parser.add_argument(param.name, nargs="*", type=str)

        elif param.kind == param.KEYWORD_ONLY:
            default = param.default if param.default is not param.empty else None
            dest = param.name
            flag = "--" + param.name.replace("_", "-")

            if ann is bool or isinstance(default, bool):
                parser.add_argument(flag, dest=dest, action="store_true", default=bool(default))
            else:
                parser.add_argument(
                    flag,
                    dest=dest,
                    type=_annotation_to_argparse_type(ann),
                    default=default,
                )

    return parser


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_bash(module, prefix: str = "ski") -> str:
    """Return a bash script defining wrapper functions for *module*.

    Each @bash_export function in *module* becomes a bash function named
    ``{prefix}_{fn_name}`` that calls::

        python3 -m {module.__name__} {fn_name} "$@"

    Boolean return values are already mapped to exit codes by the dispatcher,
    so the bash wrappers can be used directly in ``if`` statements.

    Args:
        module: A Python module containing @bash_export-tagged functions.
        prefix: Prefix for generated bash function names (default ``"ski"``).

    Returns:
        A string containing bash function definitions, ready for ``eval``.
    """
    mod_name = module.__name__
    lines = [
        f"# Bash wrappers for {mod_name}",
        f"# Generated by skimindex.bashwrapper — do not edit.",
        "",
    ]

    for name, fn in _exported_functions(module):
        bash_name = f"{prefix}_{name}"
        doc_first_line = (fn.__doc__ or "").strip().split("\n")[0]
        sig = inspect.signature(fn)
        params_doc = " ".join(
            ("*" + p.name if p.kind == p.VAR_POSITIONAL else p.name)
            for p in sig.parameters.values()
        )
        lines += [
            f"# {doc_first_line}",
            f"# Usage: {bash_name} {params_doc}",
            f"{bash_name}() {{",
            f'    python3 -m {mod_name} {name} "$@"',
            f"}}",
            "",
        ]

    return "\n".join(lines)


def dispatch(module, fn_name: str, argv: list[str], prefix: str = "ski") -> int:
    """Parse *argv* and call the named @bash_export function in *module*.

    Args:
        module:  Module containing the function.
        fn_name: Name of the @bash_export function to call.
        argv:    Command-line arguments (list of strings, excluding fn_name).

    Returns:
        POSIX exit code: 0 on success/True, 1 on failure/False,
        2 on usage error.
    """
    fn = getattr(module, fn_name, None)
    if fn is None or not getattr(fn, "_bash_export", False):
        print(f"ERROR: unknown command {fn_name!r}", file=sys.stderr)
        exported = [n for n, _ in _exported_functions(module)]
        print(f"Available: {', '.join(exported)}", file=sys.stderr)
        return 2

    parser = _build_parser(fn, bash_name=f"{prefix}_{fn_name}")
    try:
        ns = parser.parse_args(argv)
    except SystemExit:
        # Let --help (exit 0) and usage errors (exit 2) propagate naturally.
        raise

    sig = inspect.signature(fn)
    pos_args: list[Any] = []
    kw_args: dict[str, Any] = {}

    for param in sig.parameters.values():
        val = getattr(ns, param.name, None)
        if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
            pos_args.append(val)
        elif param.kind == param.VAR_POSITIONAL:
            pos_args.extend(val or [])
        elif param.kind == param.KEYWORD_ONLY:
            kw_args[param.name] = val

    try:
        result = fn(*pos_args, **kw_args)
    except Exception as exc:
        print(f"ERROR: {fn_name}: {exc}", file=sys.stderr)
        return 1

    if isinstance(result, bool):
        return 0 if result else 1
    if isinstance(result, int):
        return max(0, min(127, result))
    if result is not None:
        print(result)
    return 0
