#!/usr/bin/env bash
# Bloque les commandes destructives sans confirmation
CMD=$(echo "$CLAUDE_TOOL_INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('command',''))")

if echo "$CMD" | grep -qE 'rm -rf|DROP TABLE|git push --force'; then
    echo "BLOQUÉ : commande dangereuse détectée. Confirmez explicitement."
    exit 2  # exit 2 = deny dans Claude Code
fi
