"""
Validate the skimindex configuration file.

Loads the config, runs all validation rules, and reports any errors.
Exits with code 0 if valid, 1 if there are errors.
"""

import sys

from skimindex.config import DEFAULT_CONFIG, Config, validate
from skimindex.log import logerror, loginfo, logwarning


def main() -> int:
    """Validate the skimindex config file. Returns exit code."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="validate",
        description="Validate the skimindex configuration file",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=str(DEFAULT_CONFIG),
        help=f"Path to config file (default: {DEFAULT_CONFIG})",
    )
    args = parser.parse_args()

    from pathlib import Path
    path = Path(args.config)

    if not path.exists():
        logerror(f"Config file not found: {path}")
        return 1

    loginfo(f"Validating config: {path}")
    cfg = Config(path)
    errors = validate(cfg)

    if not errors:
        loginfo("Config is valid.")
        return 0

    logwarning(f"{len(errors)} validation error(s) found:")
    for e in errors:
        logerror(f"  [{e.section}]  {e.key}: {e.message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
