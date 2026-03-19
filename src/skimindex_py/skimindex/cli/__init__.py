"""
Lightweight CLI framework for skimindex commands.

Provides two building blocks that eliminate boilerplate from every command:

SkimCommand
    Wraps argparse and injects the three standard flags present on every
    command (--list, --section, --dry-run).  The caller only adds the
    arguments specific to their command and registers a handler function.

run_sections(name, sections, fn, dry_run)
    Runs a callable over a list of sections, logs progress, counts errors
    and returns the standard 0/1 exit code.  Replaces the identical outer
    loop found in every process_*() function.

Typical usage
-------------
Creating a new command `_foo.py`:

    from skimindex.cli import SkimCommand
    from skimindex.foo import list_sections, process_foo

    cmd = SkimCommand(
        name="foo",
        description="Do foo things on reference sections",
        list_fn=list_sections,
        examples=[
            "%(prog)s",
            "%(prog)s --list",
            "%(prog)s --section human",
            "%(prog)s --foo-size 42",
        ],
    )
    cmd.add_argument("--foo-size", type=int, metavar="N", help="Foo size")

    @cmd.handler
    def _(sections, args, dry_run):
        return process_foo(sections=sections, foo_size=args.foo_size, dry_run=dry_run)

    main = cmd.main

Adding the entry point in pyproject.toml:

    [project.scripts]
    foo = "skimindex._foo:main"

Using run_sections in the backing module `foo.py`:

    from skimindex.cli import run_sections

    def process_foo(sections=None, foo_size=None, dry_run=False) -> int:
        if sections is None:
            sections = config().ref_taxa
        params = {"foo_size": foo_size or int(config().get("foo", "size", "100"))}
        return run_sections(
            "foo pipeline",
            sections,
            lambda s: _process_section(s, params, dry_run),
            dry_run=dry_run,
        )
"""

import argparse
from collections.abc import Callable

from skimindex.log import logerror, loginfo


# ---------------------------------------------------------------------------
# run_sections — standardised outer loop
# ---------------------------------------------------------------------------

def run_sections(
    name: str,
    sections: list[str],
    fn: Callable[[str], bool],
    dry_run: bool = False,
) -> int:
    """Run *fn* over each section, log progress and return 0/1.

    Args:
        name:     Human-readable pipeline name used in log banners.
        sections: List of section names to process.
        fn:       Callable(section_name) -> bool.
                  Must return True on success, False on failure.
        dry_run:  If True, appends [DRY-RUN] to the opening banner.

    Returns:
        0 if every section succeeded, 1 if any section failed.
    """
    loginfo("===== " + name + (" [DRY-RUN]" if dry_run else "") + " =====")
    loginfo(f"Processing {len(sections)} section(s)")

    errors = 0
    for section in sections:
        loginfo(f">>> {section}")
        if fn(section):
            loginfo(f"<<< {section} OK")
        else:
            logerror(f"<<< {section} FAILED")
            errors += 1

    if errors:
        logerror(f"===== {errors} section(s) failed =====")
        return 1

    loginfo(f"===== {name} done =====")
    return 0


# ---------------------------------------------------------------------------
# SkimCommand — argparse wrapper
# ---------------------------------------------------------------------------

class SkimCommand:
    """Argparse wrapper that provides the standard skimindex CLI structure.

    Every skimindex command shares three flags:
      --list      Print available sections as CSV and exit.
      --section   Restrict processing to a single named section.
      --dry-run   Show what would be done without executing anything.

    SkimCommand injects these automatically.  The caller adds only the
    arguments specific to their command via add_argument(), then
    registers a handler with the @cmd.handler decorator.

    Args:
        name:        Command name (used as prog in help text).
        description: One-line description shown by --help.
        list_fn:     Callable() -> str that returns available sections as CSV.
        examples:    Optional list of example invocation strings for the epilog.
    """

    def __init__(
        self,
        name: str,
        description: str,
        list_fn: Callable[[], str],
        examples: list[str] | None = None,
    ):
        self._list_fn = list_fn
        self._handler: Callable | None = None

        epilog = ""
        if examples:
            epilog = "Examples:\n" + "\n".join(f"  {e}" for e in examples)

        self._parser = argparse.ArgumentParser(
            prog=name,
            description=description,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=epilog,
        )

        # Standard flags injected on every command.
        self._parser.add_argument(
            "--list",
            action="store_true",
            help="Print available sections as CSV and exit",
        )
        self._parser.add_argument(
            "--section",
            metavar="NAME",
            help="Process a single named section (e.g. human, fungi)",
        )
        self._parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be processed without running anything or modifying stamps",
        )

    def add_argument(self, *args, **kwargs) -> None:
        """Add a command-specific argument to the parser.

        Identical signature to argparse.ArgumentParser.add_argument().
        """
        self._parser.add_argument(*args, **kwargs)

    def handler(self, fn: Callable) -> Callable:
        """Decorator: register *fn* as the command handler.

        The decorated function receives (sections, args, dry_run):
          sections  -- List[str] or None (None means "all configured sections")
          args      -- argparse.Namespace with all parsed arguments
          dry_run   -- bool

        It must return an int exit code (0 = success, non-zero = failure).

        Example::

            @cmd.handler
            def _(sections, args, dry_run):
                return process_foo(sections=sections, dry_run=dry_run)
        """
        self._handler = fn
        return fn

    def main(self, argv: list[str] | None = None) -> int:
        """Parse *argv* and dispatch to the registered handler.

        Compatible with pyproject.toml entry points:
            foo = "skimindex._foo:main"  # works because main = cmd.main
        """
        if self._handler is None:
            raise RuntimeError(
                f"No handler registered for command '{self._parser.prog}'. "
                "Use @cmd.handler to register one."
            )

        args = self._parser.parse_args(argv)

        if args.list:
            print(self._list_fn() or "")
            return 0

        sections = [args.section] if args.section else None
        return self._handler(sections, args, args.dry_run)
