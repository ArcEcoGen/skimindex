#!/usr/bin/env bash
# Met à jour .claude depuis CrazyClaude et llm-functions depuis upstream,
# puis reconstruit les outils aichat.
#
# Usage : bash .claude/update_crazyclaude.sh [--dry-run]

set -euo pipefail

CRAZY_CLAUDE_URL="https://gargoton.petite-maison-orange.fr/eric/CrazyClaude.git"
LLM_FUNCTIONS_URL="https://github.com/sigoden/llm-functions.git"
CLAUDE_PREFIX=".claude"
LLM_PREFIX=".claude/llm-functions"

dry_run=0
[[ "${1:-}" == "--dry-run" ]] && dry_run=1

run() {
    if [[ "$dry_run" -eq 1 ]]; then
        echo "[dry-run] $*"
    else
        echo "» $*"
        "$@"
    fi
}

require() {
    command -v "$1" &>/dev/null || { echo "ERREUR : '$1' introuvable dans le PATH" >&2; exit 1; }
}

require git
require argc
require jq

echo "=== Mise à jour de .claude (CrazyClaude) ==="
run git subtree pull --prefix "$CLAUDE_PREFIX" "$CRAZY_CLAUDE_URL" main --squash

echo ""
echo "=== Mise à jour de .claude/llm-functions ==="
run git subtree pull --prefix "$LLM_PREFIX" "$LLM_FUNCTIONS_URL" main --squash

echo ""
echo "=== Reconstruction des outils llm-functions ==="
run argc build --arcgfile "$LLM_PREFIX/Argcfile.sh"

echo ""
echo "OK — outils reconstruits dans $LLM_PREFIX/bin/"
