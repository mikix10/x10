# Plan de travail X10

Vue **macroscopique** : les phases et leur état. Le *pourquoi* des choix est
dans la section « Décisions arrêtées » de [CLAUDE.md](CLAUDE.md) ; le *comment
contribuer* dans [CONTRIBUTING.md](CONTRIBUTING.md).

**État au 8 octobre 2026.**

## Objectif

Construire un monorepo Python pour X10, avec plusieurs packages publiables,
intégration continue, publication PyPI, documentation ReadTheDocs, et base
technique préparée pour un futur déploiement Docker/Kubernetes.

## Phase 1 — Initialisation du dépôt — **faite**

- [x] Structure du monorepo et configuration racine
- [x] Python 3.12 en cible, 3.13 en canari non bloquant
- [x] Licence BSD-3-Clause, à la racine et dans chaque paquet publiable
- [x] `uv` en espace de travail, `uv.lock` commité
- [x] Portes de qualité : `ruff` (lint et format), `mypy --strict`, `pytest`
- [x] Métadonnées PyPI complètes, build vérifié sur les cinq membres
- [x] Conventions : GitHub Flow, Conventional Commits, commits signés en SSH
- [x] Dépôt distant, protection de `main` par un ruleset versionné

## Phase 2 — Socle technique — **faite**

Quatre paquets autonomes, versionnés, typés et publiables :

- [x] `x10-models` — le vocabulaire de domaine
- [x] `x10-catalog` — le registre et la politique de résolution
- [x] `x10-connectors` — acquisition, décodage, normalisation
- [x] `x10-storage` — abstractions de persistance, encore sans implémentation

## Phase 3 — Packages métier et données — **en cours**

- [x] Vocabulaire aligné sur DCAT, PROV-O et INSPIRE, avec sa pierre de
      Rosette dans [docs/vocabulaire.md](docs/vocabulaire.md)
- [x] Deux sources open data intégrées, avec provenance et licence : ECMWF
      IFS, et les paquets AROME et ARPEGE de Météo-France
- [x] Décodage GRIB2 et normalisation vers les noms standards CF
- [ ] Modèles de domaine à étoffer : unités, emprises géographiques, séries
      temporelles, qualité
- [ ] Catalogue à peupler, l'inventaire des variables étant **dérivé des
      fichiers** et non des descriptifs des producteurs
- [x] Écriture des sorties normalisées en NetCDF-CF, avec licence et provenance
- [ ] Décision sur Zarr

## Phase 4 — API et démonstrateur — **non commencée**

- [ ] Service API de démonstration
- [ ] Couche FastAPI
- [ ] Accès cohérent aux données exposées

## Phase 5 — CI/CD et publication — **partiellement faite**

- [x] Intégration continue : lint, typage, tests, build
- [x] Matrice trois systèmes — Linux, Windows, macOS — avec canari non bloquant
- [x] Couverture de tests, barrière locale, sans service tiers
- [x] Contrôle des métadonnées de distribution avant publication
- [x] Actions épinglées par empreinte, jeton restreint en lecture
- [ ] Publication PyPI, par Trusted Publishing plutôt qu'un jeton
- [ ] Gestion des versions et des tags

## Phase 6 — Documentation — **en cours**

- [x] Documentation de référence dans `docs/` : vocabulaire, relevés de
      sources, organisation des tests
- [x] Porte d'entrée contributeur
- [ ] Configuration ReadTheDocs
- [ ] Références d'API et exemples d'usage

## Phase 7 — Infrastructure future — **non commencée**

- [ ] Dockerfiles
- [ ] Manifestes Kubernetes

## Critères de réussite

- architecture claire et modulaire
- paquets réutilisables et publiables
- portes de qualité automatisées
- documentation exploitable
- base solide pour les services clients

## Prochaine action

**Étoffer les modèles de domaine** — unités, emprises géographiques, séries
temporelles, qualité — puis peupler le catalogue avec les sources déjà
intégrées.

Plusieurs choix y dépendent de la manière dont le système sera exploité ;
voir la section « Préciser la cible d'exploitation avant de trancher » de
`CLAUDE.md`.
