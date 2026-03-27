#!/usr/bin/env -S .claude/venv/bin/python3
"""
MCP server stdio exposant un outil `qwen3_task`.
Lance aichat en mode serveur au démarrage et gère la boucle tool_calls.
Les outils disponibles pour Qwen3 sont chargés depuis llm-functions/functions.json.
Appelé par Claude Code via : claude mcp add --transport stdio qwen3 -- .claude/venv/bin/python3 .claude/mcp/qwen3-mcp/server.py
"""

import atexit
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests

QWEN3_MODEL = "LMStudio:qwen/qwen3-coder-next"
MAX_TOOL_ITERATIONS = 10

# Répertoire llm-functions relatif à ce script
_HERE = Path(__file__).parent
_LLM_FUNCTIONS_DIR = _HERE.parent.parent / "llm-functions"
_FUNCTIONS_JSON = _LLM_FUNCTIONS_DIR / "functions.json"
_BIN_DIR = _LLM_FUNCTIONS_DIR / "bin"


def _load_qwen3_tools() -> list[dict]:
    """Charge les outils depuis llm-functions/functions.json et les wrappe au format OpenAI."""
    if not _FUNCTIONS_JSON.exists():
        print(f"WARN: {_FUNCTIONS_JSON} introuvable — aucun outil disponible",
              file=sys.stderr, flush=True)
        return []
    raw = json.loads(_FUNCTIONS_JSON.read_text())
    return [{"type": "function", "function": tool} for tool in raw]


# Outil MCP exposé à Claude Code
MCP_TOOLS = [
    {
        "name": "qwen3_task",
        "description": "Délègue une tâche de codage à Qwen3-Coder via aichat. Qwen3 dispose d'outils filesystem, shell et web (llm-functions).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Description précise de la tâche"},
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Fichiers à mettre en contexte initial (optionnel)",
                },
            },
            "required": ["task"],
        },
    }
]


# --- Gestion du processus aichat ---

_aichat_proc: subprocess.Popen | None = None
_aichat_url: str | None = None


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_aichat() -> str:
    global _aichat_proc, _aichat_url

    if not shutil.which("aichat"):
        raise RuntimeError("aichat introuvable dans le PATH")

    port = _find_free_port()
    address = f"127.0.0.1:{port}"

    env = os.environ.copy()
    if _LLM_FUNCTIONS_DIR.exists():
        env["AICHAT_FUNCTIONS_DIR"] = str(_LLM_FUNCTIONS_DIR)

    _aichat_proc = subprocess.Popen(
        ["aichat", "--serve", address],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    atexit.register(_stop_aichat)

    url = f"http://{address}"
    for _ in range(30):
        try:
            requests.get(f"{url}/v1/models", timeout=1)
            _aichat_url = url
            return url
        except requests.RequestException:
            time.sleep(0.3)

    _aichat_proc.kill()
    raise RuntimeError(f"aichat n'a pas démarré sur {address}")


def _stop_aichat():
    if _aichat_proc and _aichat_proc.poll() is None:
        _aichat_proc.terminate()
        try:
            _aichat_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _aichat_proc.kill()


# --- Exécution des outils via llm-functions/bin/ ---

def _execute_tool(name: str, args: dict) -> str:
    """Exécute un outil llm-functions via son binaire dans bin/.
    Les binaires attendent le JSON des arguments comme premier argument positionnel.
    """
    bin_path = _BIN_DIR / name
    if not bin_path.exists():
        return f"ERROR: outil '{name}' introuvable dans {_BIN_DIR}"
    try:
        result = subprocess.run(
            [str(bin_path), json.dumps(args)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = (result.stdout + result.stderr).strip()
        return output or f"(exit code {result.returncode})"
    except subprocess.TimeoutExpired:
        return f"ERROR: timeout lors de l'exécution de '{name}'"
    except Exception as e:
        return f"ERROR: {e}"


# --- Boucle tool_calls → Qwen3 ---

def call_qwen3(task: str, files: list[str]) -> str:
    if _aichat_url is None:
        raise RuntimeError("aichat non démarré")

    qwen3_tools = _load_qwen3_tools()

    context = ""
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                context += f"--- {path} ---\n{f.read()}\n\n"
        except OSError as e:
            context += f"--- {path} --- ERREUR: {e}\n\n"

    user_content = f"TÂCHE: {task}"
    if context:
        user_content += f"\n\nFICHIERS:\n{context}"

    messages = [{"role": "user", "content": user_content}]
    payload: dict = {
        "model": QWEN3_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 4096,
    }
    if qwen3_tools:
        payload["tools"] = qwen3_tools

    for _ in range(MAX_TOOL_ITERATIONS):
        resp = requests.post(
            f"{_aichat_url}/v1/chat/completions",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        message = choice["message"]
        payload["messages"].append(message)

        if choice["finish_reason"] != "tool_calls":
            return message.get("content") or ""

        for tc in message.get("tool_calls", []):
            fn = tc["function"]
            args = json.loads(fn["arguments"])
            result = _execute_tool(fn["name"], args)
            payload["messages"].append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

    return "ERROR: nombre maximum d'itérations tool_calls atteint"


# --- Protocole MCP stdio ---

def send(obj: dict):
    print(json.dumps(obj), flush=True)


def handle(req: dict):
    method = req.get("method", "")
    req_id = req.get("id")

    if method == "initialize":
        send({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "qwen3-mcp", "version": "3.0.0"},
            },
        })
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": req_id, "result": {"tools": MCP_TOOLS}})
    elif method == "tools/call":
        params = req.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {})
        if name == "qwen3_task":
            try:
                text = call_qwen3(args["task"], args.get("files", []))
                send({"jsonrpc": "2.0", "id": req_id, "result": {
                    "content": [{"type": "text", "text": text}]
                }})
            except Exception as e:
                send({"jsonrpc": "2.0", "id": req_id, "result": {
                    "content": [{"type": "text", "text": f"ERROR: {e}"}],
                    "isError": True,
                }})
        else:
            send({"jsonrpc": "2.0", "id": req_id,
                  "error": {"code": -32601, "message": f"Outil inconnu : {name}"}})
    elif req_id is not None:
        send({"jsonrpc": "2.0", "id": req_id,
              "error": {"code": -32601, "message": f"Méthode inconnue : {method}"}})


# --- Démarrage ---

try:
    _start_aichat()
except Exception as e:
    print(json.dumps({"error": f"Impossible de démarrer aichat : {e}"}),
          file=sys.stderr, flush=True)
    sys.exit(1)

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        handle(json.loads(line))
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr, flush=True)
