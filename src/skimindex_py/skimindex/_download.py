#!/usr/bin/env python3
"""
Download orchestration script for GenBank and reference genome data.

Provides command-line interface for download operations via doit.

Usage:
    python download.py genbank [--divisions "bct pln ..."]
    python download.py refgenome [--list] [--genbank-div]
    python download.py refgenome

Examples:
    # Download GenBank flat-file divisions
    python download.py genbank

    # Download GenBank with specific divisions
    python download.py genbank --divisions "bct pln pri"

    # Download all (GenBank + all reference genome sections)
    python download.py refgenome

    # List available reference genome sections
    python download.py refgenome --list

    # List configured GenBank divisions
    python download.py refgenome --genbank-div

Also available as:
    python -m skimindex               (via __main__.py)
    python -m skimindex.download
"""

import argparse
import importlib
import os
import sys
from typing import Optional

from doit.cmd_base import TaskLoader2
from doit.doit_cmd import DoitMain

from skimindex.download.genbank import list_divisions
from skimindex.download.refgenome import list_sections


class PythonModuleTaskLoader(TaskLoader2):
    """Load tasks from a Python module that contains task functions."""

    def __init__(self, module_name: str):
        self.module_name = module_name
        self.module = None

    def setup(self, opt_values):
        """Setup method required by TaskLoader2."""
        pass

    def load_doit_config(self):
        """Load DOIT_CONFIG from the module."""
        if self.module is None:
            self.module = importlib.import_module(self.module_name)
        return getattr(self.module, 'DOIT_CONFIG', {})

    def load_tasks(self, cmd, pos_args):
        """Load task generators from the module."""
        if self.module is None:
            self.module = importlib.import_module(self.module_name)

        tasks = []
        for name in dir(self.module):
            if name.startswith('task_'):
                obj = getattr(self.module, name)
                if callable(obj):
                    tasks.append(obj)
        return tasks, pos_args


def _run_doit_tasks(module_name: str, task_list: list) -> int:
    """Execute doit tasks from a module via doit API.

    Args:
        module_name: Module containing tasks (e.g., 'skimindex.download')
        task_list: List of task names to run (e.g., ['genbank'])

    Returns:
        0 on success, non-zero on failure
    """
    loader = PythonModuleTaskLoader(module_name)
    doit_main = DoitMain(loader)
    return doit_main.run(task_list)


def genbank_command(args) -> int:
    """Handle 'genbank' subcommand: list divisions or run download task."""
    # Info-only mode: --list
    if args.list:
        divisions = list_divisions()
        print(divisions if divisions else "")
        return 0

    # Run download task
    if args.divisions:
        os.environ["SKIMINDEX__GENBANK__DIVISIONS"] = args.divisions

    return _run_doit_tasks("skimindex.download", ["genbank"])


def refgenome_command(args) -> int:
    """Handle 'refgenome' subcommand: list, download single section, or download all."""
    # Info-only mode: --list
    if args.list:
        sections = list_sections()
        print(sections if sections else "")
        return 0

    # Single section download (run the entire pipeline for that section)
    if args.section:
        return _run_doit_tasks("skimindex.download.refgenome", [f"compress:{args.section}"])

    # Run doit refgenomes task (all sections + genbank)
    return _run_doit_tasks("skimindex.download", ["refgenomes"])


def main(argv: Optional[list] = None) -> int:
    """Main entry point for the download CLI."""
    parser = argparse.ArgumentParser(
        description="Download GenBank and reference genome data using doit orchestration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available GenBank divisions
  %(prog)s genbank --list

  # Download GenBank flat-file divisions
  %(prog)s genbank

  # Download GenBank with specific divisions
  %(prog)s genbank --divisions "bct pln pri"

  # List available reference genome sections
  %(prog)s refgenome --list

  # Download a specific reference genome (e.g., human)
  %(prog)s refgenome --section human

  # Download all (GenBank + all reference genome sections)
  %(prog)s refgenome
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # ===== genbank subcommand =====
    genbank_parser = subparsers.add_parser(
        "genbank",
        help="Download GenBank flat-file divisions"
    )
    genbank_parser.add_argument(
        "--list",
        action="store_true",
        help="Print available GenBank divisions as CSV and exit"
    )
    genbank_parser.add_argument(
        "--divisions",
        help='Space-separated list of division codes (e.g., "bct pln pri")',
        metavar="DIVS"
    )
    genbank_parser.set_defaults(func=genbank_command)

    # ===== refgenome subcommand =====
    refgenome_parser = subparsers.add_parser(
        "refgenome",
        help="Download reference genomes"
    )
    refgenome_parser.add_argument(
        "--list",
        action="store_true",
        help="Print available reference genome sections as CSV and exit"
    )
    refgenome_parser.add_argument(
        "--section",
        help="Download a specific reference genome section (e.g., human)",
        metavar="NAME"
    )
    refgenome_parser.set_defaults(func=refgenome_command)

    # Parse arguments
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
