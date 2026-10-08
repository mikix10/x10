# X10 — GeoMetOc Open Data Server

[![CI](https://github.com/mikix10/x10/actions/workflows/ci.yml/badge.svg)](https://github.com/mikix10/x10/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/downloads/release/python-3120/)
[![Licence BSD-3-Clause](https://img.shields.io/badge/licence-BSD--3--Clause-blue)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Vérifié par mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![pre-commit](https://img.shields.io/badge/pre--commit-actif-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)

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

Pour aller plus loin : [CONTRIBUTING.md](CONTRIBUTING.md) décrit la mise en
route complète, les portes de qualité et ce qui est attendu d'une
modification. L'organisation de la suite de tests et la politique de
couverture sont dans [docs/tests-et-couverture.md](docs/tests-et-couverture.md).
Les pièges d'interopérabilité entre GRIB, CF et UDUNITS, et ce que les outils
de la chaîne en font réellement, sont relevés dans
[docs/unites-et-interoperabilite.md](docs/unites-et-interoperabilite.md).

## Plan retenu

Sept phases, dont l'état détaillé est dans [PLAN.md](PLAN.md).

1. Initialiser le monorepo et le packaging Python — **faite**
2. Créer le socle commun des paquets techniques — **faite**
3. Définir les paquets métier et données — **en cours**
4. Préparer le démonstrateur API / FastAPI
5. Intégration continue, publication PyPI et gestion des versions — **partiellement faite**
6. Documentation ReadTheDocs — **en cours**
7. Déploiement Docker / Kubernetes

## Où en est le projet

**Deux sources open data sont intégrées de bout en bout** : les prévisions
IFS d'ECMWF, et les paquets AROME et ARPEGE de Météo-France. La donnée est
téléchargée avec sa provenance et sa licence, décodée en tableaux maillés, et
normalisée vers les noms standards des conventions CF.

Restent des ébauches : l'API n'expose aucun point d'entrée, le catalogue
n'est pas peuplé, rien n'est stocké durablement.

Deux relevés publiés établissent **par la mesure** ce que les sources
exposent réellement, là où les descriptifs des producteurs s'en écartent :
[AROME](docs/arome-paquets-et-api-ciblee.md) et
[ARPEGE](docs/arpege-paquets-et-api-ciblee.md).
