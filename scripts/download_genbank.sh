#!/bin/bash
#
# download_genbank.sh — Download and convert GenBank flat files to FASTA
#
# This script drives the GenBank download process defined in /genbank/Makefile.
# Because each GenBank division consists of hundreds of large files downloaded
# over the network, a single `make` run may fail partway through (transient
# network errors, server timeouts, etc.). Rather than abort the whole process,
# this script re-runs `make fasta` in a loop as long as progress is being made.
#
# Progress detection strategy
# ----------------------------
# The /genbank/Makefile uses stamp files (*.stamp) to track which raw GenBank
# files have been successfully downloaded. After each `make` invocation, the
# script counts the stamp files present on disk:
#
#   - If the count increased  → at least one new file was fetched; retry.
#   - If the count is unchanged → no progress was made (all remaining targets
#     failed); stop to avoid an infinite loop.
#   - If make returned exit 0 → all targets are satisfied; stop normally.
#
# This strategy is robust to partial failures: already-completed downloads are
# never re-fetched (make skips their targets), and the loop terminates as soon
# as the pipeline stalls completely.
#
# Usage
# -----
#   Run inside the skimindex container (mounts /genbank to the host data dir):
#
#     docker run --rm -v /data/genbank:/genbank skimindex:latest \
#         download_genbank.sh
#
#   Or via the Makefile shortcut (from the docker/ directory):
#
#     make run           # interactive shell, then: download_genbank.sh
#

set -uo pipefail

pushd /genbank > /dev/null

echo "Starting GenBank download loop..."

while true; do
    before=$(find . -name "*.stamp" 2>/dev/null | wc -l)

    make
    make_status=$?

    after=$(find . -name "*.stamp" 2>/dev/null | wc -l)

    if [ "$make_status" -eq 0 ]; then
        echo "All GenBank targets completed successfully."
        break
    fi

    if [ "$after" -le "$before" ]; then
        echo "No progress in last iteration ($after stamp files). Stopping." >&2
        exit 1
    fi

    echo "Progress: $((after - before)) new file(s) downloaded, retrying..."
done

popd > /dev/null
