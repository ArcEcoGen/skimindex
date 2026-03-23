"""Make skimindex package executable via python -m skimindex.

Prints available commands and exits.
"""

import sys


def main() -> int:
    print(
        "Usage: skimindex <command> [options]\n"
        "\n"
        "Commands:\n"
        "  download   Download data from configured sources\n"
        "  decontam   Prepare decontamination filter data\n"
        "  validate   Validate the configuration file\n"
        "\n"
        "Run '<command> --help' for command-specific options."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
