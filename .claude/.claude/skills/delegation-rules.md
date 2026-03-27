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
