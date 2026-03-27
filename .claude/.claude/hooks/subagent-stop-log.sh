#!/usr/bin/env bash
# Observabilité : log chaque fin de subagent
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
PAYLOAD=$(cat)
AGENT=$(echo "$PAYLOAD" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('agent_name','unknown'))" 2>/dev/null)
echo "$TIMESTAMP agent=$AGENT" >> .claude/logs/subagent-decisions.log
