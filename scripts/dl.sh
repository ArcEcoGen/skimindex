#!/usr/bin/env bash
# ============================================================
# dl.sh
# Wrapper for Python download module
#
# Usage:
#   dl.sh refgenome --section NAME     Download reference genomes for a section
#   dl.sh refgenome --list             List available sections
#   dl.sh refgenome                    Download all configured sections
#   dl.sh genbank                      Download all GenBank divisions
#   dl.sh genbank --divisions "bct"    Download specific GenBank divisions
#
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=__skimindex_config.sh
source "${SCRIPT_DIR}/__skimindex_config.sh"

# Pass all arguments to the download command
download "$@"
