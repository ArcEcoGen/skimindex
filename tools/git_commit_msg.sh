#!/usr/bin/env bash
# git_commit_msg.sh — generate a commit message from staged files using aichat
#
# Usage: git_commit_msg.sh
#   Summarises each staged file's diff individually, then combines all
#   summaries into a single commit message via aichat.

set -euo pipefail

# Log to stderr so progress doesn't pollute the commit message on stdout
log()  { printf '\033[1;34m==>\033[0m %s\n' "$*" >&2; }
info() { printf '    \033[0;37m%s\033[0m\n' "$*" >&2; }
ok()   { printf '    \033[0;32m✓\033[0m %s\n' "$*" >&2; }

# Collect staged files
staged_files=$(git diff --staged --name-only)

if [[ -z "$staged_files" ]]; then
    echo "No staged files." >&2
    exit 1
fi

file_count=$(wc -l <<< "$staged_files" | tr -d ' ')
log "Found $file_count staged file(s)"

summaries=""
n=0

while IFS= read -r file; do
    diff=$(git diff --staged -- "$file")
    if [[ -z "$diff" ]]; then
        continue
    fi

    n=$((n + 1))
    log "[$n/$file_count] Summarising $file …"

    summary=$(printf '%s' "$diff" | aichat "In 2-3 lines, summarise what this diff changes in the file '$file'. Be concise and technical.")

    # Print the summary indented to stderr
    while IFS= read -r line; do
        info "$line"
    done <<< "$summary"

    summaries+="### $file
$summary

"
done <<< "$staged_files"

if [[ -z "$summaries" ]]; then
    echo "No non-empty diffs found." >&2
    exit 1
fi

log "Generating commit message from $n summary/summaries …"
result=$(printf '%s' "$summaries" | aichat "From these per-file summaries of a git diff, write a single conventional git commit message in English. First line: short imperative summary (max 72 chars). Then a blank line. Then a short paragraph with more detail if needed. Output only the commit message, nothing else.")

ok "Done"
printf '\n' >&2

# Commit message goes to stdout
printf '%s\n' "$result"
