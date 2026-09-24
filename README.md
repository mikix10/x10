# X10 — GeoMetOc Open Data Server

## Contexte

X10 est la composante d'exploitation de données géo-hydro-océano-météo open data.

Objectif général : fournir une base technique robuste pour exposer ces données open data sous forme d'API à des systèmes clients, avec une architecture évolutive pour des usages futurs en conteneurisation Docker/Kubernetes.

## Cadre fonctionnel

- Plusieurs packages Python à gérer dans un monorepo
- CI/CD sur GitHub
- Publication sur PyPI
- Documentation ReadTheDocs
- Référence technique pour un futur déploiement Docker/Kubernetes
- Architecture pensée comme composant réutilisable par des systèmes clients

## Architecture cible

### Monorepo Python

- Utiliser `uv` et un workspace Python basé sur `pyproject.toml`
- Séparer les composants publiables dans un dossier `packages/`
- Séparer les démonstrateurs / services dans un dossier `services/`
- Python 3.12 comme cible de développement ; la CI exécute en plus un job 3.13 non bloquant, en canari de compatibilité ascendante
- Licence BSD-3-Clause

### Packages envisagés

- `x10-models`
  - modèles Pydantic v2, immuables (`frozen`)
  - unités, emprises géographiques, horodatage
  - qualité et provenance des données

- `x10-catalog`
  - registre des sources
  - producteurs, diffuseurs, formats, licences, modalités d'accès
  - sémantique des catalogues de données

- `x10-connectors`
  - interfaces de découverte, téléchargement, validation, normalisation
  - adaptateurs pour sources externes

- `x10-storage`
  - abstractions de persistance
  - adaptateurs de démonstration sans imposer de backend de stockage cible

## Positionnement technique

Les composants doivent rester indépendants, publiables et réutilisables par d'autres projets, tout en servant de socle technique pour la couche API et l'orchestration du système global.

## Démarrage

```bash
uv sync --all-packages --dev   # installer le workspace et l'outillage
uv run pytest                  # tests
uv run ruff check .            # lint
uv run ruff format .           # format
uv run mypy                    # typage strict
uv build --all-packages        # construire les distributions
```

## Plan retenu

1. Initialiser le monorepo et le packaging Python
2. Créer le socle commun des packages techniques
3. Définir les packages métier / domaine
4. Mettre en place les workflows GitHub Actions
5. Préparer la publication PyPI et la release management
6. Écrire la documentation ReadTheDocs
7. Préparer le démonstrateur API / FastAPI
8. Poser les bases pour le déploiement Docker/Kubernetes

## Prochaines étapes recommandées

- créer la structure du dépôt
- mettre en place les fichiers `pyproject.toml` / workspace
- initialiser les packages de base
- définir les conventions de nommage, versioning et quality gates
- rédiger le plan technique détaillé version par version

## État

Ce document correspond au contexte qui a été capturé lors de la discussion précédente avec l’assistant. Il sert de base de travail pour la suite du projet X10.
