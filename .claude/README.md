# CrazyClaude

Configuration Claude Code pour orchestrer des tâches de développement Rust/Go en déléguant les tâches atomiques à **Qwen3-Coder** via LM Studio.

Ce dépôt est conçu pour être intégré comme sous-répertoire `.claude/` dans n'importe quel projet. Il fournit agents, hooks, skills et un serveur MCP prêts à l'emploi.

Pour le détail de l'architecture, voir [`rapport-orchestration-claude-code.md`](./rapport-orchestration-claude-code.md).

---

## Prérequis

- [Claude Code](https://claude.ai/code) installé (`claude` disponible dans le PATH)
- [LM Studio](https://lmstudio.ai/) avec le modèle `qwen/qwen3-coder-next` chargé, écoutant sur `http://localhost:1248`
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

Puis déplacez ou liez le contenu :

```sh
# Copier le répertoire .claude dans votre projet
cp -r .claude-crazy/.claude ./.claude

# Ou, si vous préférez garder une référence au dépôt source :
# utilisez jj workspace add pour ajouter un workspace dédié
```

> Si vous utilisez git en sous-jacent avec jj (`jj git init --colocate`),
> vous pouvez aussi ajouter ce dépôt comme subtree :
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

### 3. Enregistrer le serveur MCP

```sh
claude mcp add --transport stdio qwen3 -- .claude/venv/bin/python3 .claude/mcp/qwen3-mcp/server.py
```

Vérifier que la connexion est établie :

```sh
claude mcp list
# qwen3: ... - ✓ Connected
```

### 4. Adapter CLAUDE.md à votre projet

Éditez `.claude/CLAUDE.md` : mettez à jour la section `## Stack` et les heuristiques de délégation selon vos besoins.

### 5. Rendre les hooks exécutables

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
│   ├── qwen3-worker.md          # délégation vers LM Studio (Qwen3)
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
│       ├── server.py            # serveur MCP stdio (interface LM Studio)
│       ├── agent_lm.py          # agent loop CLI autonome
│       └── requirements.txt
├── logs/                        # produits par les hooks (ignorés par jj/git)
└── venv/                        # virtualenv Python (ignoré par jj/git)
```

---

## Configuration LM Studio

Le serveur MCP se connecte sur `http://localhost:1248` avec le modèle `qwen/qwen3-coder-next`.

Pour modifier ces valeurs, éditez `.claude/mcp/qwen3-mcp/server.py` :

```python
LMSTUDIO_URL = "http://localhost:1248/v1/chat/completions"
QWEN3_MODEL  = "qwen/qwen3-coder-next"
```

---

## Fichiers à ignorer (jj / git)

Ajoutez ces entrées dans votre fichier d'ignore :

```
.claude/venv/
.claude/logs/
```

Avec Jujutsu :

```sh
echo ".claude/venv/" >> .gitignore
echo ".claude/logs/" >> .gitignore
```

---

## Mise à jour

Avec Jujutsu (workflow colocalisé git) :

```sh
git subtree pull --prefix .claude https://gargoton.petite-maison-orange.fr/eric/CrazyClaude.git main --squash
```

Ou si vous avez cloné séparément, tirez les changements puis recopiez :

```sh
cd .claude-crazy && jj git fetch && jj new main
cp -r .claude/* ../.claude/
```


## Outils necessaire

### aichat

### jq

### argc
