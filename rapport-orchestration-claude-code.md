# Rapport Technique : Orchestration Robuste avec Claude Code et Délégation à un LLM Local

**Auteur** : Eric Coissac  
**Date** : 26 mars 2026  
**Contexte** : Ce document décrit une architecture robuste exploitant les mécanismes natifs de **Claude Code** (subagents, hooks, skills, MCP) pour déléguer des tâches à faible complexité à **Qwen3-Coder** (via LM Studio), tout en maintenant Claude Code comme orchestrateur central.

---

## 1. Pourquoi cette architecture — et ce qu'elle n'est *pas*

Le document original décrivait un système où Claude Code appelait un script Python externe (`delegate_to_qwen.py`) pour piloter Qwen3. C'est un anti-pattern : cela court-circuite les mécanismes natifs de Claude Code et réintroduit de la complexité là où l'écosystème propose déjà des solutions mieux intégrées.

En mars 2026, Claude Code dispose de cinq systèmes fondamentaux :

| Système | Rôle |
|---------|------|
| **CLAUDE.md** | Contexte permanent du projet (règles, conventions, heuristiques) |
| **Skills** | Instructions chargées à la demande selon la pertinence |
| **Subagents** | Agents spécialisés avec fenêtre de contexte isolée, outils restreints, modèle configurable |
| **Hooks** | Scripts shell ou prompts LLM déclenchés sur des événements du cycle de vie |
| **MCP servers** | Extensions vers des outils et services externes via protocole standardisé |

La délégation à Qwen3 s'intègre naturellement via un **subagent pointant vers LM Studio** ou via un **MCP server stdio minimal**. Le script Python devient optionnel — il reste utile comme wrapper si LM Studio n'expose pas d'interface MCP, mais il ne doit pas être l'orchestrateur.

---

## 2. Architecture cible

```
Utilisateur
    │
    ▼
Claude Code (orchestrateur)
    │  lit CLAUDE.md au démarrage
    │  charge les skills pertinents à la demande
    │
    ├─── Subagent : qwen3-worker  ──────► LM Studio (localhost:1234)
    │         contexte isolé               modèle Qwen3-Coder
    │         outils : Read, Write, Bash
    │
    ├─── Subagent : code-reviewer ──────► Claude Haiku (coût réduit)
    │         validation syntaxe/style
    │
    ├─── Hooks ──────────────────────────► scripts shell
    │         PostToolUse : lint auto
    │         SubagentStop : log décision
    │         PreToolUse : garde-fous
    │
    └─── MCP servers (optionnel)
              qwen3-mcp (stdio) : wrapper LM Studio
```

**Principe clé** : Claude Code ne lit pas les fichiers sources pour les passer à Qwen3. C'est Qwen3 (via son subagent ou son agent loop) qui lit les fichiers dont il a besoin — le contenu ne transite pas par le contexte de Claude Code.

---

## 3. Structure du projet

```
.claude/
├── CLAUDE.md                    # contexte projet + heuristiques de délégation
├── settings.json                # hooks et permissions
├── agents/
│   ├── qwen3-worker.md          # subagent → LM Studio
│   ├── code-reviewer.md         # subagent → Haiku (validation)
│   └── task-planner.md          # subagent → Opus (planification complexe)
├── skills/
│   ├── delegation-rules.md      # quand déléguer à Qwen3
│   └── rust-go-conventions.md   # conventions spécifiques au projet
└── hooks/
    ├── post-write-lint.sh        # lint automatique après écriture
    ├── subagent-stop-log.sh      # observabilité
    └── pre-bash-guard.sh         # sécurité
mcp/
└── qwen3-mcp/
    ├── server.py                 # MCP server stdio (optionnel)
    └── agent_lm.py               # agent loop local (~120 lignes)
```

---

## 4. CLAUDE.md — contexte et heuristiques

```markdown
# Projet [nom]

## Stack
- Rust (edition 2024), Go 1.24
- Tests : cargo test, go test
- Lint : clippy (Rust), golangci-lint (Go)

## Heuristiques de délégation

Délègue à `qwen3-worker` si la tâche est **atomique** et satisfait TOUS les critères :
- ≤ 3 fichiers concernés
- Pas de modification d'API publique
- Pas de dépendance externe non encore importée
- Tâches typiques : génération de tests unitaires, reformatage, documentation inline,
  conversion de types simples, scaffolding de stubs

Traite toi-même si :
- Refactoring cross-module
- Conception d'architecture
- Debugging avec contexte multi-fichiers
- Modification de traits/interfaces publics

## Garde-fous absolus
- Ne jamais passer `rm -rf` sans confirmation explicite
- Ne jamais committer sans que les tests passent
- Toujours vérifier `git diff` avant un commit
```

---

## 5. Subagent `qwen3-worker`

Fichier : `.claude/agents/qwen3-worker.md`

```markdown
---
name: qwen3-worker
description: >
  Délègue à Qwen3-Coder via LM Studio les tâches atomiques sur 1-3 fichiers :
  génération de tests unitaires, documentation inline, scaffolding de stubs,
  reformatage de code. N'utilise PAS pour du refactoring cross-module ou de
  la conception d'architecture.
tools: [Read, Write, Bash]
model: inherit
---

Tu es un assistant de codage spécialisé exécutant des tâches courtes et précises.

## Comportement
1. Lis les fichiers nécessaires avec l'outil Read (ne reçois pas le contenu en entrée).
2. Effectue la transformation demandée.
3. Écris le résultat avec Write.
4. Exécute le linter approprié (clippy pour Rust, golangci-lint pour Go) et corrige
   les erreurs éventuelles (max 2 tentatives).
5. Retourne un résumé : fichiers modifiés, changements effectués, résultat du lint.

## Format de sortie
```
STATUS: success|partial|failure
FILES_MODIFIED: liste des fichiers
SUMMARY: description des changements
LINT: passed|failed (+ détail si failed)
```

Ne génère pas de fonctions non demandées. Ne modifie pas les signatures publiques.
```

> **Note importante** : le champ `model: inherit` signifie que ce subagent utilise le modèle courant de la session. Pour pointer vers LM Studio, il faut soit configurer `ANTHROPIC_BASE_URL` pour ce subagent, soit utiliser le MCP server décrit en section 7.

---

## 6. Hooks

### `settings.json`

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/post-write-lint.sh",
            "async": true
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/subagent-stop-log.sh"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/pre-bash-guard.sh"
          }
        ]
      }
    ]
  }
}
```

### `post-write-lint.sh`

```bash
#!/usr/bin/env bash
# Lint automatique après écriture de fichier
FILE=$(echo "$CLAUDE_TOOL_INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('file_path',''))")

if [[ "$FILE" == *.rs ]]; then
    cargo clippy --quiet 2>&1 | tail -20
elif [[ "$FILE" == *.go ]]; then
    golangci-lint run "$FILE" 2>&1 | tail -20
fi
```

### `subagent-stop-log.sh`

```bash
#!/usr/bin/env bash
# Observabilité : log chaque fin de subagent
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
PAYLOAD=$(cat)
AGENT=$(echo "$PAYLOAD" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('agent_name','unknown'))" 2>/dev/null)
echo "$TIMESTAMP agent=$AGENT" >> .claude/logs/subagent-decisions.log
```

### `pre-bash-guard.sh`

```bash
#!/usr/bin/env bash
# Bloque les commandes destructives sans confirmation
CMD=$(echo "$CLAUDE_TOOL_INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('command',''))")

if echo "$CMD" | grep -qE 'rm -rf|DROP TABLE|git push --force'; then
    echo "BLOQUÉ : commande dangereuse détectée. Confirmez explicitement."
    exit 2  # exit 2 = deny dans Claude Code
fi
```

---

## 7. MCP Server (optionnel — si LM Studio n'est pas accessible comme modèle)

Si l'objectif est de router un subagent vers LM Studio plutôt que vers l'API Anthropic, le moyen le plus simple est un MCP server stdio minimal.

### `mcp/qwen3-mcp/server.py`

```python
#!/usr/bin/env python3
"""
MCP server stdio minimaliste exposant un outil `qwen3_task`.
Appelé par Claude Code via : claude mcp add --transport stdio qwen3 -- python3 mcp/qwen3-mcp/server.py
"""
import sys
import json
import requests

LMSTUDIO_URL = "http://localhost:1234/v1/chat/completions"
QWEN3_MODEL = "qwen3-coder"  # nom du modèle dans LM Studio


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


def handle_tool_call(tool_name: str, args: dict) -> str:
    if tool_name == "qwen3_task":
        return call_qwen3(args["task"], args.get("files", []))
    return f"Outil inconnu : {tool_name}"


# Boucle MCP stdio (protocole JSON-RPC simplifié)
for line in sys.stdin:
    try:
        req = json.loads(line)
        if req.get("method") == "tools/call":
            result = handle_tool_call(
                req["params"]["name"], req["params"].get("arguments", {})
            )
            print(json.dumps({"id": req["id"], "result": {"content": [{"type": "text", "text": result}]}}))
        elif req.get("method") == "tools/list":
            print(json.dumps({
                "id": req["id"],
                "result": {"tools": [{
                    "name": "qwen3_task",
                    "description": "Délègue une tâche de codage atomique à Qwen3-Coder via LM Studio.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "task": {"type": "string", "description": "Description précise de la tâche"},
                            "files": {"type": "array", "items": {"type": "string"}, "description": "Chemins des fichiers concernés"}
                        },
                        "required": ["task"]
                    }
                }]}
            }))
        elif req.get("method") == "initialize":
            print(json.dumps({"id": req["id"], "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}}}))
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
    sys.stdout.flush()
```

**Installation** :
```bash
claude mcp add --transport stdio qwen3 -- python3 mcp/qwen3-mcp/server.py
```

---

## 8. Skill de délégation

Fichier : `.claude/skills/delegation-rules.md`

```markdown
---
name: delegation-rules
description: Règles pour décider quand et comment déléguer à qwen3-worker ou qwen3 MCP
---

# Règles de Délégation à Qwen3

## Critères de délégation (TOUS requis)
- ≤ 3 fichiers source concernés
- Tâche atomique, sans dépendance à résoudre
- Pas de modification de signature publique (trait, interface exportée)
- Contexte de fichier estimé < 8 000 tokens

## Tâches typiques éligibles
- Génération de tests unitaires pour une fonction donnée
- Ajout de documentation (doc comments Rust, godoc Go)
- Scaffolding de stubs à partir d'une interface
- Conversion de types internes simples
- Reformatage / réorganisation d'imports

## Procédure
1. Évalue les critères ci-dessus.
2. Si éligible → utilise le subagent `qwen3-worker` en précisant la tâche et les fichiers.
3. Attends le résumé de sortie (STATUS / FILES_MODIFIED / LINT).
4. Si STATUS=failure → prends en charge toi-même.
5. Si STATUS=partial → corrige les points restants directement.

## Ne jamais déléguer
- Refactoring impliquant > 3 fichiers
- Changement d'architecture ou de design pattern
- Debugging avec stacktrace à analyser
- Tâches nécessitant une recherche web ou du contexte externe
```

---

## 9. Pipeline de validation native

Claude Code valide via les hooks et les subagents dédiés — pas via du code de validation embarqué dans le script de délégation.

| Étape | Mécanisme | Déclencheur |
|-------|-----------|-------------|
| Lint syntaxique | `post-write-lint.sh` (hook) | PostToolUse/Write automatique |
| Validation de style | subagent `code-reviewer` | explicitement demandé |
| Tests | `Bash: cargo test / go test` | dans le subagent ou directement |
| Contrôle des diffs | `Bash: git diff --stat` | avant tout commit |

### Subagent `code-reviewer`

```markdown
---
name: code-reviewer
description: >
  Révise du code Rust ou Go pour détecter bugs, régressions, problèmes de style.
  Utilise après génération par qwen3-worker ou avant un commit.
tools: [Read, Grep, Glob, Bash]
model: claude-haiku-4-5-20251001
---

Tu es un reviewer expérimenté en Rust et Go.

Pour chaque fichier fourni :
1. Vérifie la cohérence des types et la gestion d'erreurs.
2. Identifie les patterns non idiomatiques.
3. Signale les tests manquants pour les chemins critiques.

Format de sortie :
```
VERDICT: approved|changes_requested
ISSUES: liste numérotée (vide si approved)
```
```

---

## 10. Boucle de correction contrôlée

La boucle de correction n'est pas un script externe — elle est gérée nativement par Claude Code via le prompt du subagent et les hooks.

Séquence type :
1. Claude Code délègue à `qwen3-worker`.
2. Le subagent retourne `STATUS: failure` avec détail.
3. Claude Code lit le résumé, corrige lui-même ou re-délègue avec le feedback intégré dans le prompt.
4. Maximum 2 re-délégations ; au-delà, Claude Code traite directement.

---

## 11. Sécurité

Les garde-fous sont dans les **hooks** (non contournables par le contexte) plutôt que dans des fonctions Python.

```json
{
  "permissions": {
    "allow": [
      "Bash(cargo:*)",
      "Bash(go:*)",
      "Bash(git diff*)",
      "Bash(git add*)",
      "Bash(git commit*)",
      "Read(**/*.rs)",
      "Read(**/*.go)",
      "Write(**/*.rs)",
      "Write(**/*.go)"
    ],
    "deny": [
      "Bash(rm -rf*)",
      "Bash(curl * | bash*)",
      "Bash(git push --force*)"
    ]
  }
}
```

---

## 12. Observabilité

Les logs sont produits par les hooks, pas par du code applicatif.

```
.claude/logs/
├── subagent-decisions.log    # timestamp + agent name à chaque SubagentStop
└── delegation-outcomes.log   # STATUS de chaque délégation (si ajouté au hook)
```

Pour des métriques plus élaborées (taux de délégation, taux d'échec), un hook `SubagentStop` peut écrire dans un fichier JSON et un script externe peut agréger.

---

## 13. Workflow complet — exemple

**Requête** : "Génère les tests unitaires pour les fonctions `parse_header` et `validate_checksum` dans `src/parser.rs`."

1. Claude Code lit `CLAUDE.md` → identifie les heuristiques de délégation.
2. Charge le skill `delegation-rules.md` → tâche éligible (1 fichier, atomique, pas d'API publique).
3. Délègue au subagent `qwen3-worker` : *"Génère des tests unitaires pour `parse_header` et `validate_checksum` dans `src/parser.rs`"*.
4. `qwen3-worker` lit `src/parser.rs` via l'outil Read (le contenu ne passe pas par le contexte principal).
5. Écrit les tests dans `src/parser.rs` (ou `tests/parser_tests.rs`).
6. Hook `post-write-lint.sh` déclenché → `cargo clippy` → résultat injecté dans le contexte du subagent.
7. Subagent retourne : `STATUS: success | FILES_MODIFIED: src/parser.rs | LINT: passed`.
8. Claude Code confirme à l'utilisateur.

---

## 14. Ce qui a changé par rapport au document initial

| Document initial | Cette version |
|-----------------|---------------|
| Script Python `delegate_to_qwen.py` comme orchestrateur | Claude Code natif comme orchestrateur |
| Validation syntaxique dans le script | Hook `post-write-lint.sh` (déterministe, non contournable) |
| Boucle de correction en Python | Gérée par le prompt du subagent + logique d'orchestration Claude |
| Sécurité dans `is_safe_file()` | Permissions natives (`settings.json`) + hook `pre-bash-guard.sh` |
| Logs en Python | Hooks shell sur les événements du cycle de vie |
| Tools MCP = scripts ad hoc | MCP server stdio standard + subagents natifs |

---

## 15. Prochaines étapes recommandées

1. **Bootstrapper la structure** : créer `.claude/agents/`, `settings.json`, `CLAUDE.md` avec les templates ci-dessus.
2. **Tester LM Studio** : vérifier que `curl http://localhost:1234/v1/models` répond avant d'activer le MCP server.
3. **Calibrer les heuristiques** : après 20-30 délégations, affiner les critères dans `delegation-rules.md` selon les résultats observés dans les logs.
4. **Envisager `model:` explicite** : si Claude Haiku est suffisant pour `qwen3-worker` (coût réduit, latence moindre), configurer `model: claude-haiku-4-5-20251001` à la place du LLM local.
5. **MCP Tool Search** : activer `ENABLE_TOOL_SEARCH=auto` pour réduire la consommation de contexte quand les MCP servers sont nombreux.
