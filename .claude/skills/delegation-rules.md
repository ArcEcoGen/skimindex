---
name: delegation-rules
description: Règles pour décider quand et comment déléguer à qwen3-worker via le MCP qwen3_task
---

# Règles de Délégation à Qwen3

Qwen3-Coder opère via le MCP tool `qwen3_task`. Il dispose d'outils filesystem, shell
et web (llm-functions) — il peut lire/écrire des fichiers, exécuter des commandes,
faire des recherches web et exécuter du code de façon autonome.

## Critères de délégation (TOUS requis)

- Tâche bien définie, objectif clair
- Pas de modification de signature publique (trait, interface exportée)
- Pas de refactoring cross-module nécessitant une vision globale de l'architecture

## Tâches éligibles

- Génération de tests unitaires pour une fonction donnée
- Ajout de documentation (doc comments Rust, godoc Go)
- Scaffolding de stubs à partir d'une interface
- Conversion de types internes simples
- Reformatage / réorganisation d'imports
- Recherche d'information sur le web ou dans une URL
- Exécution et vérification d'un script Python
- Création ou modification de fichiers de configuration

## Procédure

1. Évalue les critères ci-dessus.
2. Si éligible → utilise le subagent `qwen3-worker` avec une description précise de la tâche.
   Ne pas pré-charger les fichiers : Qwen3 les lit lui-même si nécessaire.
3. Attends le résumé (STATUS / FILES_MODIFIED / SUMMARY).
4. Si `STATUS: failure` → prends en charge toi-même.
5. Si `STATUS: partial` → corrige les points restants directement.

## Ne jamais déléguer

- Refactoring impliquant une vision cross-module
- Changement d'architecture ou de design pattern
- Debugging avec stacktrace à analyser sur plusieurs fichiers
- Tâches nécessitant le contexte de la conversation en cours
