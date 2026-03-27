# CrazyClaude

Configuration Claude Code pour orchestrer des tâches de développement en déléguant les tâches atomiques à **Qwen3-Coder** via [aichat](https://github.com/sigoden/aichat).

Ce dépôt est conçu pour être intégré comme sous-répertoire `.claude/` dans n'importe quel projet. Il fournit agents, hooks, skills, un serveur MCP et une collection d'outils prêts à l'emploi.

Pour le détail de l'architecture, voir [`rapport-orchestration-claude-code.md`](./rapport-orchestration-claude-code.md).

---

## Architecture

```
Claude Code (orchestrateur)
    │
    └── MCP qwen3  (stdio)
            │
            └── aichat --serve (port dynamique)
                        │
                        └── LM Studio → Qwen3-Coder-Next
                                    + outils llm-functions
                                      (fs, shell, web, ...)
```

Le serveur MCP lance aichat au démarrage sur un port libre. Qwen3 dispose d'outils filesystem, shell et web fournis par [llm-functions](https://github.com/sigoden/llm-functions) — sans aucune logique d'outil dans le serveur lui-même.

---

## Prérequis

- [Claude Code](https://claude.ai/code) (`claude` dans le PATH)
- [aichat](https://github.com/sigoden/aichat) (`aichat` dans le PATH)
- [LM Studio](https://lmstudio.ai/) avec le modèle `qwen/qwen3-coder-next` chargé et accessible depuis aichat
- [argc](https://github.com/sigoden/argc) — runner de scripts pour llm-functions
- [jq](https://jqlang.github.io/jq/) — requis par llm-functions
- Python 3.11+ (pour le serveur MCP)
- Outils selon votre stack : `cargo` + `clippy` (Rust), `golangci-lint` (Go)

---

## Installation dans un projet existant

### 1. Cloner ce dépôt

Avec **Jujutsu** :

```sh
# Depuis la racine de votre projet
jj git clone https://gargoton.petite-maison-orange.fr/eric/CrazyClaude.git .claude-crazy
```

Puis copiez le contenu :

```sh
cp -r .claude-crazy/.claude ./.claude
cp -r .claude-crazy/llm-functions ./.claude/llm-functions  # si présent dans le clone
```

> Avec jj colocalisé git, vous pouvez aussi utiliser subtree :
>
> ```sh
> git subtree add --prefix .claude https://gargoton.petite-maison-orange.fr/eric/CrazyClaude.git main --squash
> ```

### 2. Créer le virtualenv Python

```sh
cd .claude
python3 -m venv venv
venv/bin/pip install -r mcp/qwen3-mcp/requirements.txt
```

### 3. Installer et construire llm-functions

Si `llm-functions/` n'est pas déjà présent dans `.claude/` :

```sh
git clone https://github.com/sigoden/llm-functions .claude/llm-functions
```

Choisissez les outils à activer en éditant `.claude/llm-functions/tools.txt`, puis construisez :

```sh
cd .claude/llm-functions
argc build
```

Les outils activés par défaut :

```
fs_cat.sh
fs_ls.sh
fs_mkdir.sh
fs_write.sh
fs_patch.sh
execute_command.sh
fetch_url_via_curl.sh
web_search_aichat.sh
execute_py_code.py
```

### 4. Configurer aichat

Vérifiez que aichat peut accéder à LM Studio et que le modèle `qwen/qwen3-coder-next` est disponible :

```sh
aichat --list-models | grep qwen
```

### 5. Enregistrer le serveur MCP

```sh
claude mcp add --transport stdio qwen3 -- .claude/venv/bin/python3 .claude/mcp/qwen3-mcp/server.py
```

Vérifier :

```sh
claude mcp list
# qwen3: ... - ✓ Connected
```

### 6. Adapter CLAUDE.md à votre projet

Éditez `.claude/CLAUDE.md` : mettez à jour la section `## Stack` et les heuristiques de délégation.

### 7. Rendre les hooks exécutables

```sh
chmod +x .claude/hooks/*.sh
```

---

## Structure

```
.claude/
├── CLAUDE.md                    # contexte projet + heuristiques de délégation
├── settings.json                # hooks et permissions
├── agents/
│   ├── qwen3-worker.md          # délégation vers Qwen3 via MCP
│   ├── code-reviewer.md         # révision code (Claude Haiku)
│   └── task-planner.md          # planification complexe (Claude Opus)
├── skills/
│   ├── delegation-rules.md      # quand déléguer à Qwen3
│   └── rust-go-conventions.md   # conventions Rust/Go
├── hooks/
│   ├── post-write-lint.sh       # lint automatique après écriture
│   ├── subagent-stop-log.sh     # log des décisions de délégation
│   └── pre-bash-guard.sh        # blocage des commandes dangereuses
├── mcp/
│   └── qwen3-mcp/
│       ├── server.py            # serveur MCP stdio : lance aichat + gère tool_calls
│       ├── agent_lm.py          # agent loop CLI autonome (usage direct sans MCP)
│       └── requirements.txt
├── llm-functions/               # collection d'outils pour Qwen3 (sous-repo)
│   ├── tools.txt                # outils activés
│   ├── functions.json           # déclarations générées (lues par server.py)
│   ├── bin/                     # binaires générés par argc build
│   └── tools/                   # scripts sources (.sh, .py, .js)
├── logs/                        # produits par les hooks (ignorés par jj/git)
└── venv/                        # virtualenv Python (ignoré par jj/git)
```

---

## Outils disponibles pour Qwen3

Les outils sont définis dans `.claude/llm-functions/tools.txt` et buildés avec `argc build`.

| Outil | Description |
|-------|-------------|
| `fs_cat` | Lit un fichier |
| `fs_ls` | Liste un répertoire |
| `fs_mkdir` | Crée un répertoire |
| `fs_write` | Écrit/crée un fichier |
| `fs_patch` | Modifie un fichier par patch |
| `execute_command` | Exécute une commande shell |
| `fetch_url_via_curl` | Requête HTTP GET |
| `web_search_aichat` | Recherche web |
| `execute_py_code` | Exécute du code Python |

Pour ajouter un outil : éditez `tools.txt` et relancez `argc build`.

---

## Configuration du modèle

Le modèle Qwen3 est configuré dans `.claude/mcp/qwen3-mcp/server.py` :

```python
QWEN3_MODEL = "LMStudio:qwen/qwen3-coder-next"
```

Le format `Provider:model-id` suit la convention aichat. Adaptez selon votre installation LM Studio.

---

## Fichiers à ignorer (jj / git)

```
.claude/venv/
.claude/logs/
.claude/llm-functions/bin/
.claude/llm-functions/cache/
```

Avec Jujutsu :

```sh
printf ".claude/venv/\n.claude/logs/\n.claude/llm-functions/bin/\n.claude/llm-functions/cache/\n" >> .gitignore
```

---

## Mise à jour

Avec Jujutsu colocalisé (`jj git init --colocate`), la mise à jour est gérée côté git :

```sh
git subtree pull --prefix .claude https://gargoton.petite-maison-orange.fr/eric/CrazyClaude.git main --squash
```

jj voit le commit résultant comme un commit ordinaire dans son graphe.

Après mise à jour, reconstruire llm-functions si `tools.txt` a changé :

```sh
cd .claude/llm-functions && argc build
```
