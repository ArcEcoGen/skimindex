#!/usr/bin/env -S .claude/venv/bin/python3
"""
Agent loop local (~120 lignes) pour interagir avec LM Studio via l'API OpenAI-compatible.
Usage : python3 .claude/mcp/qwen3-mcp/agent_lm.py --task "..." --files file1.py file2.go
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests

SERVER = "http://localhost"
PORT = 8888  # 1248
LMSTUDIO_URL = f"{SERVER}:{PORT}/v1/chat/completions"
LMSTUDIO_MODELS_URL = f"{SERVER}:{PORT}/v1/models"
DEFAULT_MODEL = "qwen/qwen3-coder-next"

SYSTEM_PROMPT = """Tu es un assistant de codage spécialisé. Tu effectues des tâches atomiques sur des fichiers source.
Règles :
- Ne modifie que ce qui est demandé
- Ne change pas les signatures publiques (traits Rust, interfaces Go exportées)
- Retourne uniquement le code, sans explication ni markdown
- Si tu ne peux pas accomplir la tâche, réponds avec: ERROR: <raison>
"""


def list_models() -> list[str]:
    """Retourne la liste des modèles disponibles dans LM Studio."""
    try:
        resp = requests.get(LMSTUDIO_MODELS_URL, timeout=10)
        resp.raise_for_status()
        return [m["id"] for m in resp.json().get("data", [])]
    except requests.RequestException as e:
        print(f"Impossible de contacter LM Studio : {e}", file=sys.stderr)
        return []


def read_files(paths: list[str]) -> str:
    """Lit les fichiers et les formate pour le prompt."""
    context = ""
    for path in paths:
        try:
            content = Path(path).read_text(encoding="utf-8")
            context += f"=== {path} ===\n{content}\n\n"
        except OSError as e:
            context += f"=== {path} === ERREUR: {e}\n\n"
    return context


def call_lmstudio(task: str, file_context: str, model: str) -> str:
    """Envoie la tâche à LM Studio et retourne la réponse."""
    user_message = (
        f"TÂCHE: {task}\n\nFICHIERS:\n{file_context}"
        if file_context
        else f"TÂCHE: {task}"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
    }

    try:
        resp = requests.post(LMSTUDIO_URL, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except requests.Timeout:
        return "ERROR: LM Studio timeout (>120s)"
    except requests.RequestException as e:
        return f"ERROR: {e}"
    except (KeyError, IndexError) as e:
        return f"ERROR: réponse inattendue de LM Studio : {e}"


def write_file(path: str, content: str) -> bool:
    """Écrit le contenu dans un fichier, crée les répertoires si nécessaire."""
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content, encoding="utf-8")
        return True
    except OSError as e:
        print(f"Erreur écriture {path}: {e}", file=sys.stderr)
        return False


def run_lint(file_path: str) -> tuple[bool, str]:
    """Lance le linter approprié selon l'extension."""
    import subprocess

    if file_path.endswith(".rs"):
        result = subprocess.run(
            ["cargo", "clippy", "--quiet"], capture_output=True, text=True, timeout=60
        )
    elif file_path.endswith(".go"):
        result = subprocess.run(
            ["golangci-lint", "run", file_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
    else:
        return True, "no linter for this file type"

    passed = result.returncode == 0
    output = (result.stdout + result.stderr).strip()
    return passed, output


def agent_loop(
    task: str,
    input_files: list[str],
    output_file: str | None,
    model: str,
    max_retries: int = 2,
) -> dict:
    """Boucle principale : génère, écrit, lint, corrige (max_retries fois)."""
    file_context = read_files(input_files) if input_files else ""
    result = {
        "status": "failure",
        "files_modified": [],
        "summary": "",
        "lint": "skipped",
    }

    for attempt in range(max_retries + 1):
        response = call_lmstudio(task, file_context, model)

        if response.startswith("ERROR:"):
            result["summary"] = response
            break

        target = output_file or (input_files[0] if input_files else None)
        if not target:
            result["status"] = "success"
            result["summary"] = response
            result["lint"] = "skipped (no output file)"
            break

        if write_file(target, response):
            result["files_modified"] = [target]

            lint_ok, lint_output = run_lint(target)
            result["lint"] = "passed" if lint_ok else f"failed: {lint_output[:500]}"

            if lint_ok:
                result["status"] = "success"
                result["summary"] = (
                    f"Attempt {attempt + 1}: task completed successfully"
                )
                break
            elif attempt < max_retries:
                task = f"{task}\n\nCORRECTION REQUISE (tentative {attempt + 1}):\n{lint_output}"
                file_context = read_files([target])
            else:
                result["status"] = "partial"
                result["summary"] = f"Lint failed after {max_retries + 1} attempts"

    return result


def main():
    parser = argparse.ArgumentParser(description="Agent loop local pour LM Studio")
    parser.add_argument("--task", required=True, help="Description de la tâche")
    parser.add_argument("--files", nargs="*", default=[], help="Fichiers source à lire")
    parser.add_argument(
        "--output", help="Fichier de sortie (défaut: premier fichier input)"
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Modèle LM Studio")
    parser.add_argument(
        "--list-models", action="store_true", help="Liste les modèles disponibles"
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output", help="Sortie JSON"
    )
    args = parser.parse_args()

    if args.list_models:
        models = list_models()
        if models:
            print("Modèles disponibles :")
            for m in models:
                print(f"  - {m}")
        else:
            print("Aucun modèle trouvé ou LM Studio inaccessible.")
        return

    result = agent_loop(args.task, args.files, args.output, args.model)

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"STATUS: {result['status']}")
        print(f"FILES_MODIFIED: {', '.join(result['files_modified']) or 'none'}")
        print(f"SUMMARY: {result['summary']}")
        print(f"LINT: {result['lint']}")

    sys.exit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
