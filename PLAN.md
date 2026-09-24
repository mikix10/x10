# Plan de travail X10

## Objectif

Construire un monorepo Python pour X10, avec plusieurs packages publiables, intégration CI/CD GitHub, publication PyPI, documentation ReadTheDocs, et base technique préparée pour un futur déploiement Docker/Kubernetes.

## Phase 1 — Initialisation du dépôt — **faite**

- [x] Créer la structure du monorepo
- [x] Ajouter le fichier de configuration racine
- [x] Python 3.12 en cible de développement, 3.13 en canari CI non bloquant
- [x] Définir la licence BSD-3-Clause (`LICENSE` à la racine et dans chaque package publiable)
- [x] Mettre en place `uv` (workspace + `uv.lock` commité)
- [x] Quality gates : `ruff` (lint + format), `mypy --strict`, `pytest`
- [x] Métadonnées PyPI complètes et build vérifié sur les 5 membres
- [x] Conventions de contribution : GitHub Flow, Conventional Commits, commits signés en SSH
- [x] Commit initial sur `main`
- [ ] Créer le dépôt distant et configurer le remote

## Phase 2 — Socle technique

- `x10-models`
- `x10-catalog`
- `x10-connectors`
- `x10-storage`

Chacun doit être un package Python autonome, versionné, documenté et publiable.

## Phase 3 — Packages métier et données

- Modèles de données géo-hydro-océano-météo
- Sources open data et provenance
- Vérification et normalisation des données
- Gestion des métadonnées

## Phase 4 — API et démonstrateur

- Créer un service API de démonstration
- Préparer une couche FastAPI si nécessaire
- Exposer un accès cohérent aux données

## Phase 5 — CI/CD et publication — **partiellement faite**

- [x] GitHub Actions (jobs `quality`, `test`, `build`)
- [x] tests automatisés
- [x] lint / qualité
- [x] build des packages
- [ ] publication sur PyPI (Trusted Publishing plutôt qu'un token)
- [ ] release management (tags sur `main`, versions par package)

## Phase 6 — Documentation

- ReadTheDocs
- guides d’architecture
- références API
- exemples d’usage

## Phase 7 — Infrastructure future

- Dockerfiles
- configuration Kubernetes
- préparation pour déploiement industriel

## Critères de réussite

- architecture claire et modulaire
- packages réutilisables
- quality gates automatisés
- documentation exploitable
- base solide pour les services clients

## Prochaine action

Implémenter un connecteur ECMWF IFS open data concret dans `x10-connectors`, pour valider les abstractions (`BaseConnector`, `DataSource`, `Provenance`) par un cas d'usage réel. Voir `CLAUDE.md` pour les décisions d'architecture arrêtées.
