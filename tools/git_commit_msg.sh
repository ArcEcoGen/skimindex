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

# _readable_diff <file>
#   Returns a human-readable diff for <file>.
#   For pathological single-line formats (JSON, minified JS/CSS…), pretty-prints
#   both the committed and working versions before diffing so the LLM sees
#   structured changes rather than one enormous ±line.
_readable_diff() {
    local file="$1"
    local raw_diff
    raw_diff=$(git diff --staged -- "$file")
    [[ -z "$raw_diff" ]] && return 0

    # Detect pathological diff: any +/- content line longer than 500 chars
    local max_len
    max_len=$(grep '^[+-]' <<< "$raw_diff" | awk '{ if (length > m) m = length } END { print m+0 }')

    if (( max_len <= 500 )); then
        printf '%s' "$raw_diff"
        return
    fi

    # Pretty-print strategy per extension
    local ext="${file##*.}"
    local pretty_old pretty_new
    case "$ext" in
        json)
            pretty_old=$(git show "HEAD:${file}" 2>/dev/null | python3 -m json.tool 2>/dev/null || true)
            pretty_new=$(git show ":${file}"     2>/dev/null | python3 -m json.tool 2>/dev/null || true)
            ;;
        js|mjs|cjs|css|ts)
            local node_fmt='
                const chunks = [];
                process.stdin.on("data", d => chunks.push(d));
                process.stdin.on("end", () => {
                    const src = chunks.join("");
                    // Insert newline before { } ( ) ; and after ,
                    const out = src
                        .replace(/([{(])/g,  "$1\n  ")
                        .replace(/([;}])/g,  "\n$1\n")
                        .replace(/,\s*/g,    ",\n  ");
                    process.stdout.write(out);
                });'
            pretty_old=$(git show "HEAD:${file}" 2>/dev/null | node -e "$node_fmt" 2>/dev/null || true)
            pretty_new=$(git show ":${file}"     2>/dev/null | node -e "$node_fmt" 2>/dev/null || true)
            ;;
        *)
            # Generic fallback: fold long lines at 120 chars
            pretty_old=$(git show "HEAD:${file}" 2>/dev/null | fold -s -w 120 || true)
            pretty_new=$(git show ":${file}"     2>/dev/null | fold -s -w 120 || true)
            ;;
    esac

    if [[ -n "$pretty_old" && -n "$pretty_new" ]]; then
        diff <(printf '%s\n' "$pretty_old") <(printf '%s\n' "$pretty_new") \
            --label "a/${file}" --label "b/${file}" -u || true
    else
        printf '%s' "$raw_diff"
    fi
}

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
    diff=$(_readable_diff "$file")
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
