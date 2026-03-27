#!/usr/bin/env bash
# Installe CrazyClaude dans le projet courant.
# À lancer depuis la racine du projet après git subtree add.
#
# Usage : bash .claude/install.sh

set -euo pipefail

CLAUDE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$CLAUDE_DIR")"

require() {
    command -v "$1" &>/dev/null || { echo "ERREUR : '$1' introuvable dans le PATH" >&2; exit 1; }
}

require python3
require argc
require jq
require aichat
require claude

echo "=== Virtualenv Python ==="
python3 -m venv "$CLAUDE_DIR/venv"
"$CLAUDE_DIR/venv/bin/pip" install -q -r "$CLAUDE_DIR/mcp/qwen3-mcp/requirements.txt"
echo "OK"

echo ""
echo "=== Construction des outils llm-functions ==="
if [[ -f "$CLAUDE_DIR/llm-functions/Argcfile.sh" ]]; then
    argc build --arcgfile "$CLAUDE_DIR/llm-functions/Argcfile.sh"
    echo "OK"
else
    echo "WARN : llm-functions non trouvé — lance d'abord :"
    echo "  git subtree add --prefix .claude/llm-functions https://github.com/sigoden/llm-functions.git main --squash"
fi

echo ""
echo "=== Hooks exécutables ==="
chmod +x "$CLAUDE_DIR/hooks/"*.sh
echo "OK"

echo ""
echo "=== Enregistrement du serveur MCP ==="
PYTHON="$CLAUDE_DIR/venv/bin/python3"
SERVER="$CLAUDE_DIR/mcp/qwen3-mcp/server.py"

if claude mcp list 2>/dev/null | grep -q "^qwen3:"; then
    echo "MCP qwen3 déjà enregistré — mise à jour"
    claude mcp remove qwen3 2>/dev/null || true
fi

claude mcp add --transport stdio qwen3 -- "$PYTHON" "$SERVER"
echo "OK"

echo ""
echo "=== Vérification ==="
claude mcp list | grep qwen3

echo ""
echo "Installation terminée. Éditez .claude/CLAUDE.md pour adapter au projet."
