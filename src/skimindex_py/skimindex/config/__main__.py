"""
python -m skimindex.config

Validates the configuration file and prints shell export statements for all
SKIMINDEX__ environment variables derived from it.  Variables already set in
the environment are skipped (environment takes priority over the config file).

Usage in bash::

    eval "$(python3 -m skimindex.config)"

Validation errors are printed to stderr and the script exits with status 1,
which causes the bash ``eval`` to fail visibly instead of silently loading a
broken configuration.

The config file is read from SKIMINDEX_CONFIG (default /config/skimindex.toml).
If the file does not exist the script exits silently with no output.
"""

import sys
from skimindex.config import Config, DEFAULT_CONFIG
from skimindex.config.validate import validate


def main() -> int:
    cfg = Config(DEFAULT_CONFIG, apply_logging=False, export_env=False)

    if not cfg.path.exists():
        return 0

    errors = validate(cfg)
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        print(f"{len(errors)} configuration error(s) — aborting.", file=sys.stderr)
        return 1

    output = cfg.dump_env()
    if output:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
