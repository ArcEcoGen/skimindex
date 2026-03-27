---
name: rust-go-conventions
description: Conventions de style et patterns idiomatiques Rust (edition 2024) et Go 1.24 pour ce projet
---

# Conventions Rust / Go

## Rust (edition 2024)
- Utilise `thiserror` pour les types d'erreur publics, `anyhow` dans les binaires.
- Préfère `?` à `unwrap()` sauf dans les tests.
- Les `pub` structs doivent avoir des doc comments (`///`).
- Nomme les types de retour complexes avec des type aliases.
- `clippy::pedantic` activé — corrige tous les lints avant commit.

## Go 1.24
- Gestion d'erreurs : toujours `if err != nil { return ..., err }`, jamais `_`.
- Interfaces en minuscule si non exportées.
- Docstring obligatoire pour toute fonction exportée (commence par le nom de la fonction).
- Utilise `errors.Is` / `errors.As` pour comparer les erreurs.
- `golangci-lint` avec preset `default` + `gocritic`.

## Tests
- Rust : tests unitaires dans le même fichier (`#[cfg(test)]`), intégration dans `tests/`.
- Go : fichiers `_test.go`, table-driven tests avec `t.Run`.
- Couverture cible : 80 % sur les chemins critiques.
