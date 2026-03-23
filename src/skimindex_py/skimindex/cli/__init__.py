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


def validate_config() -> int:
    """Validate the current config. Returns 0 if valid, 1 if errors."""
    from skimindex.config import config, validate
    errors = validate(config())
    if errors:
        for e in errors:
            logerror(f"ConfigError(section='{e.section}', key='{e.key}', message={e.message!r})")
        logerror(f"{len(errors)} configuration error(s) — aborting.")
        return 1
    return 0


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
        section_arg: str = "dataset",
        section_metavar: str = "NAME",
        section_help: str = "Process a single named entry (e.g. human, fungi)",
    ):
        self._list_fn = list_fn
        self._handler: Callable | None = None
        self._section_arg = section_arg.replace("-", "_")
        self._subcommands: dict[str, "SkimCommand"] = {}

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
            help="Print available entries as CSV and exit",
        )
        self._parser.add_argument(
            f"--{section_arg}",
            metavar=section_metavar,
            help=section_help,
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

    def subcommand(self, name: str, cmd: "SkimCommand") -> None:
        """Register a named subcommand. Must be called before main() is used."""
        self._subcommands[name] = cmd

    def main(self, argv: list[str] | None = None) -> int:
        """Parse *argv* and dispatch to the registered handler.

        If the first argument matches a registered subcommand, delegates to it
        (validation happens inside the subcommand's main()).
        Otherwise validates config, then calls the top-level handler.

        Compatible with pyproject.toml entry points:
            foo = "skimindex._foo:main"  # works because main = cmd.main
        """
        if argv is None:
            import sys
            argv = sys.argv[1:]

        if argv and argv[0] in self._subcommands:
            return self._subcommands[argv[0]].main(argv[1:])

        if self._handler is None:
            raise RuntimeError(
                f"No handler registered for command '{self._parser.prog}'. "
                "Use @cmd.handler to register one."
            )

        args = self._parser.parse_args(argv)

        if args.list:
            print(self._list_fn() or "")
            return 0

        rc = validate_config()
        if rc != 0:
            return rc

        section_val = getattr(args, self._section_arg, None)
        sections = [section_val] if section_val else None
        return self._handler(sections, args, args.dry_run)
