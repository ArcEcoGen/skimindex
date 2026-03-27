## Instructions pour Claude

### Profil utilisateur
Programmeur expérimenté. Connaît parfaitement son projet, ses outils, et son environnement.

### Comportement attendu
- Faire ce qui est demandé, directement.
- Ne pas expliquer des choses triviales ou évidentes.
- Ne pas répéter ce qui vient d'être dit.
- Faire confiance au jugement de l'utilisateur.
- Si quelque chose ne fonctionne pas, chercher le bug — ne pas réexpliquer comment utiliser l'outil.
- Avant de demander la validation d'un plan, toujours afficher la totalité du plan dans le chat. L'utilisateur est responsable du code et décide en toute connaissance de cause.

## Stack
- Rust (edition 2024), Go 1.24
- Python 3.12, R 4.4, bash (scripts shell)
- Tests :
  - Rust : `cargo test`
  - Go : `go test`
  - Python : `pytest` (avec coverage)
  - R : `testthat` (via `Rscript -e "testthat::test_dir('tests')"`)
  - bash : `bats` (Bash Automated Testing System)
- Lint :
  - Rust : `clippy`
  - Go : `golangci-lint`
  - Python : `ruff` (ou `flake8` + `black`)
  - R : `lintr`
  - bash : `shellcheck`

## Heuristiques de délégation

Délègue à `qwen3-worker` si la tâche est **atomique** et satisfait TOUS les critères :
- ≤ 3 fichiers concernés
- Pas de modification d’API publique
- Pas de dépendance externe non encore importée
- Tâches typiques : génération de tests unitaires, reformatage, documentation inline,
  conversion de types simples, scaffolding de stubs
- Pour le bash, éviter les commandes destructrices (voir garde-fous)

Traite toi-même si :
- Refactoring cross-module
- Conception d’architecture
- Debugging avec contexte multi-fichiers
- Modification de traits/interfaces publics

## Garde-fous absolus
- Ne jamais passer `rm -rf` sans confirmation explicite
- Ne jamais committer sans que les tests passent
- Toujours vérifier `git diff` avant un commit
- Pour le bash : ne jamais exécuter de commande avec `eval` non contrôlé ; privilégier l’utilisation de `shellcheck` pour détecter les erreurs courantes
