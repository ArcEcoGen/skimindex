#!/usr/bin/env bash
# Lint automatique après écriture de fichier
FILE=$(echo "$CLAUDE_TOOL_INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('file_path',''))")

if [[ "$FILE" == *.rs ]]; then
    cargo clippy --quiet 2>&1 | tail -20
elif [[ "$FILE" == *.go ]]; then
    golangci-lint run "$FILE" 2>&1 | tail -20
fi
