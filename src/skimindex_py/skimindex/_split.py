#!/usr/bin/env python3
"""
Split reference genomes into fragments for decontamination index building.

Provides command-line interface for fragment splitting operations.

Usage:
    split [OPTIONS]
    split --list
    split --section NAME [OPTIONS]

Examples:
    # Split all sections using config defaults
    split

    # List available sections
    split --list

    # Split a specific section
    split --section human

    # Override fragment parameters
    split --frg-size 300 --overlap 28 --batches 32
    split --section plant --frg-size 300 --overlap 28

"""

import argparse
import sys
from typing import Optional

from skimindex.split import list_sections, process_split


def main(argv: Optional[list] = None) -> int:
    """Main entry point for the split CLI."""
    parser = argparse.ArgumentParser(
        description="Split reference genomes into fragments for decontamination indices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Split all sections using config defaults
  %(prog)s

  # List available sections
  %(prog)s --list

  # Split a specific section
  %(prog)s --section human

  # Override fragment parameters
  %(prog)s --frg-size 300 --overlap 28 --batches 32

  # Override parameters for a specific section
  %(prog)s --section plant --frg-size 300 --overlap 28
        """,
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="Print available sections as CSV and exit",
    )
    parser.add_argument(
        "--section",
        help="Split a specific section (e.g., human, plant)",
        metavar="NAME",
    )
    parser.add_argument(
        "--frg-size",
        type=int,
        help="Fragment size in bp (default: from config decontamination.frg_size)",
        metavar="SIZE",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        help="Overlap between fragments (default: from config decontamination.kmer_size - 1)",
        metavar="N",
    )
    parser.add_argument(
        "--batches",
        type=int,
        help="Number of output batches (default: from config decontamination.batches)",
        metavar="N",
    )

    args = parser.parse_args(argv)

    # Info-only mode: --list
    if args.list:
        sections = list_sections()
        print(sections if sections else "")
        return 0

    # Determine sections to process
    sections = None
    if args.section:
        sections = [args.section]

    # Call split pipeline
    return process_split(
        sections=sections,
        frg_size=args.frg_size,
        overlap=args.overlap,
        batches=args.batches,
    )


if __name__ == "__main__":
    sys.exit(main())
