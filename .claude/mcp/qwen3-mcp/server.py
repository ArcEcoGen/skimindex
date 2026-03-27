#!/usr/bin/env -S .claude/venv/bin/python3
"""
MCP server stdio exposant un outil `qwen3_task`.
Appelé par Claude Code via : claude mcp add --transport stdio qwen3 -- .claude/venv/bin/python3 .claude/mcp/qwen3-mcp/server.py
"""

import json
import sys

import requests

SERVER = "http://localhost"
PORT = 8888  # 1248
LMSTUDIO_URL = f"{SERVER}:{PORT}/v1/chat/completions"
QWEN3_MODEL = "qwen/qwen3-coder-next"

TOOLS = [
    {
        "name": "qwen3_task",
        "description": "Délègue une tâche de codage atomique à Qwen3-Coder via LM Studio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Description précise de la tâche",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Chemins des fichiers concernés",
                },
            },
            "required": ["task"],
        },
    }
]


def send(obj: dict):
    print(json.dumps(obj), flush=True)


def call_qwen3(task: str, files: list[str]) -> str:
    context = ""
    for path in files:
        try:
            with open(path) as f:
                context += f"--- {path} ---\n{f.read()}\n\n"
        except OSError as e:
            context += f"--- {path} --- ERREUR: {e}\n\n"

    prompt = f"""Tu es un assistant de codage. Effectue la tâche suivante de manière précise.

TÂCHE: {task}

FICHIERS:
{context}

Retourne uniquement le code modifié ou généré, sans explication.
"""
    resp = requests.post(
        LMSTUDIO_URL,
        json={
            "model": QWEN3_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 4096,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def handle(req: dict):
    method = req.get("method", "")
    req_id = req.get("id")

    if method == "initialize":
        send(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "qwen3-mcp", "version": "1.0.0"},
                },
            }
        )
    elif method == "notifications/initialized":
        pass  # notification, pas de réponse
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}})
    elif method == "tools/call":
        params = req.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {})
        if name == "qwen3_task":
            try:
                text = call_qwen3(args["task"], args.get("files", []))
                send(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"content": [{"type": "text", "text": text}]},
                    }
                )
            except Exception as e:
                send(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": f"ERROR: {e}"}],
                            "isError": True,
                        },
                    }
                )
        else:
            send(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Outil inconnu : {name}"},
                }
            )
    elif req_id is not None:
        send(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Méthode inconnue : {method}"},
            }
        )


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        handle(json.loads(line))
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr, flush=True)
