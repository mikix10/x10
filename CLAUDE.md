# CLAUDE.md

Guide de travail pour Claude Code sur le dépôt X10.

## Contexte

**GeoMetOc Open Data Server** — c'est l'accroche du dépôt, et la description publique sur GitHub.

X10 est la composante d'exploitation de données **géo-hydro-océano-météo open data**. L'objectif est d'exposer ces données via une API à des systèmes clients, à partir d'un socle de packages Python indépendants, publiables et réutilisables.

> Le dépôt est public et ne nomme aucun projet utilisateur ni aucune source sans accord : voir « Confidentialité des tiers ».

Documents de cadrage à lire avant toute décision d'architecture :
- [README.md](README.md) — contexte, architecture cible, rôle de chaque package
- [PLAN.md](PLAN.md) — plan en 7 phases et critères de réussite

## État réel du dépôt

Le socle technique est en place (licence, métadonnées PyPI, quality gates, CI, lockfile), mais le **code métier reste un ensemble de stubs** : les modèles et interfaces sont définis, aucun connecteur réel n'existe, l'API n'expose aucun endpoint.

## Structure

Monorepo `uv` workspace (`[tool.uv.workspace]` dans [pyproject.toml](pyproject.toml), membres `packages/*` et `services/*`).

| Chemin | Rôle | Contenu actuel |
|---|---|---|
| [packages/x10-models/](packages/x10-models/) | modèles de domaine partagés | `GeoPoint`, `Provenance`, `Observation` (Pydantic, frozen) |
| [packages/x10-catalog/](packages/x10-catalog/) | registre des sources et métadonnées | `DataSource`, `CatalogEntry` (Pydantic, frozen) |
| [packages/x10-connectors/](packages/x10-connectors/) | découverte / téléchargement / validation / normalisation | `BaseConnector`, `ConnectorResult` |
| [packages/x10-storage/](packages/x10-storage/) | abstractions de persistance | `StorageAdapter`, `StorageRecord` |
| [services/x10-api/](services/x10-api/) | démonstrateur API (FastAPI) | fonction `hello()` |

Chaque membre suit le même moule, à reproduire pour tout nouveau package : layout `src/`, build `hatchling`, `version = "0.1.0"`, `requires-python = ">=3.12,<3.14"`, `license = "BSD-3-Clause"` avec une copie de `LICENSE` dans le dossier du package, classifiers et `project.urls` renseignés, marqueur `py.typed`, dossier `tests/`, et toute l'API publique exportée depuis le `__init__.py` avec un `__all__` explicite.

Règle de dépendance : `x10-api` → packages ; `x10-connectors` / `x10-storage` / `x10-catalog` → `x10-models`. Ne pas créer de dépendance descendante depuis `x10-models`. Aucune dépendance interne n'est encore câblée — les ajouter en `[tool.uv.sources]` (`{ workspace = true }`) quand elles deviennent nécessaires.

## Commandes

```bash
uv sync --all-packages --dev   # installer le workspace et l'outillage
uv run pytest                  # tests
uv run ruff check .            # lint
uv run ruff format .           # format (la CI vérifie avec --check)
uv run mypy                    # typage strict sur les src/
uv build --all-packages        # construire les distributions
uv lock                        # après tout changement de dépendance (la CI exige --locked)
```

Python **3.12** (pin dans [.python-version](.python-version)). Le `.venv/` local est provisionné par `uv`. `uv.lock` est commité et la CI le vérifie — toujours le régénérer après avoir touché aux dépendances.

## Conventions de code

- Python 3.12, `from __future__ import annotations` en tête de module, annotations de types systématiques.
- Syntaxe de types moderne : `str | None`, `list[str]`, `dict[str, Any]`.
- Modèles de domaine : Pydantic v2 avec `model_config = ConfigDict(frozen=True)`, contraintes exprimées via `Field` (`ge`/`le` sur les coordonnées, `min_length=1` sur les identifiants). Objets de résultat / transport internes : dataclasses mutables (`ConnectorResult`, `StorageRecord`).
- Sur un modèle `frozen`, préférer `tuple[str, ...]` à `list[str]` pour les collections : une `list` rend le modèle non hashable.
- Classes de base abstraites : lever `NotImplementedError("Subclasses must implement X().")`.
- Valeurs numériques mesurées : `Decimal`, pas `float` (voir `Observation.value`). Les coordonnées restent en `float`.
- Toute donnée exploitée porte sa **provenance** et sa **licence** — c'est une exigence produit, pas un détail.
- Documentation et commentaires en français, identifiants et code en anglais.

### Typage : `mypy --strict` ne se relâche jamais globalement

`strict = true` porte sur **notre** code : fonctions annotées, pas d'appel non typé, pas d'`Any` implicite. C'est un choix durable, pas une position provisoire.

Une dépendance sans types ne remet pas ce réglage en cause. Elle déclenche une erreur distincte, `import-untyped`, qui n'appartient d'ailleurs pas à `strict` : mypy refuse par défaut un import sans stubs ni marqueur `py.typed`. La réponse est une dérogation nommée et limitée au module fautif, jamais un abaissement du réglage global :

```toml
[[tool.mypy.overrides]]
module = ["cfgrib.*", "eccodes.*"]
ignore_missing_imports = true
```

Même principe si un appel dans une bibliothèque non typée bloque `disallow_untyped_calls` : on désactive le contrôle sur ce module précis. L'intérêt est la lisibilité — on lit dans le `pyproject.toml` exactement quelles bibliothèques ne sont pas typées, au lieu d'un affaissement silencieux de tout le projet.

Pydantic, FastAPI, xarray embarquent `py.typed` et numpy a ses stubs ; ce sont surtout les liaisons GRIB (`cfgrib`, `eccodes`) qui risquent d'exiger une dérogation.

## Décisions arrêtées

- **Cible de développement : Python 3.12 uniquement.** Le code peut utiliser librement les constructions 3.12.
- **La CI teste 3.12 (bloquant) et 3.13 (canari de compatibilité ascendante, `continue-on-error`).** Conséquence technique : `requires-python` vaut `>=3.12,<3.14` partout, sinon `uv sync` refuserait de résoudre sur 3.13 avant même de lancer les tests. Ne pas resserrer à `<3.13`.
- **Modèles en Pydantic v2**, pas de couche dataclasses parallèle. La validation à l'ingestion (unités, bornes géographiques, provenance obligatoire) est le cœur du travail de `x10-connectors` ; OpenAPI et JSON Schema en découlent gratuitement pour `x10-api`.
- **Règle de volumétrie** : ne jamais instancier un modèle Pydantic par point de grille. Les données maillées (GRIB/NetCDF) restent dans des tableaux `xarray`/`numpy` ; les modèles servent aux métadonnées, entrées de catalogue, provenance et payloads API. `Observation` vaut pour les séries ponctuelles (stations, bouées), pas pour un champ IFS 0.25°.
- **Backend de build : `hatchling`, déclaré membre par membre.** Les cinq paquets sont en Python pur ; la seule chose que `setuptools` ferait mieux, compiler des extensions C, ne nous sert pas puisque le travail natif est délégué à `cfgrib`/`eccodes`, que nous consommons sous forme de wheels sans jamais les construire. Le backend n'a par ailleurs aucun effet sur le déploiement : la vraie contrainte de conteneurisation sera la bibliothèque C ecCodes, identique quel que soit le backend.
  **Corollaire à ne pas perdre de vue** : chaque membre porte son propre `[build-system]`. Le jour où un paquet devra embarquer une extension compilée — hypothèse crédible en géosciences — il basculera seul vers `setuptools` ou `meson-python`. Ne jamais uniformiser le backend « par cohérence » : c'est cette granularité qui donne l'évolutivité.
- **Domaine pilote : météo, ECMWF IFS open data.** Techniques visées : téléchargement sélectif par paramètre et par échéance, requêtes HTTP Byte-Range sur les GRIB2 pour éviter le transfert intégral, normalisation vers NetCDF-CF.

## Ordre de travail retenu

1. ~~**Socle technique**~~ — fait : workspace `uv`, `uv.lock`, `LICENSE`, métadonnées PyPI, ruff, `mypy --strict`, pytest, hook `pre-commit`, CI 3.12 avec canari 3.13, commits signés.
2. **Protéger `main`** puis reprendre le travail en pull request — voir « Reste à faire ».
3. **Connecteur ECMWF IFS** concret, pour valider les abstractions par l'usage.
4. **Modèle de catalogue multi-origines** — une information logique peut avoir plusieurs sources, avec une politique de résolution. Le `CatalogEntry` actuel, qui porte une source unique, ne le permet pas.
5. **Étoffer les modèles de domaine** — unités, emprises géographiques, séries temporelles, qualité.

## Reste à faire

- `docs/` et configuration ReadTheDocs (phase 6).
- Workflow GitHub Actions de release / publication PyPI (phase 5), avec Trusted Publishing plutôt qu'un token.
- Dockerfiles et manifestes Kubernetes (phase 7).
- Activer le *secret scanning* et la *push protection* sur GitHub (gratuits sur dépôt public) — réglage d'interface.
- Dependabot et CodeQL : différés tant que le code métier se résume à des stubs, à activer dès que `x10-connectors` contient du code réel.
- Monter les actions GitHub de majeure (`checkout` v4 → v7, `setup-uv` v5 → v10, `upload-artifact` v4 → v7) : changement fonctionnel à tester à part.
- **Protéger `main`** sur GitHub : tant qu'aucune règle n'est active, on peut y pousser et y force-pusher librement, ce qui vide GitHub Flow de son sens. Le ruleset est prêt — voir le skill [github-protection](.claude/skills/github-protection/SKILL.md) —, il reste à authentifier `gh` puis à l'appliquer.

## Procédures outillées (skills)

Les procédures pas-à-pas ne sont pas dans ce fichier : elles vivent dans `.claude/skills/`, versionnées avec le dépôt. Ce fichier ne garde que ce qui doit être connu en permanence.

| Skill | Quand l'invoquer |
|---|---|
| [commit](.claude/skills/commit/SKILL.md) | **Avant tout commit, sans exception.** Contrôle des termes proscrits, quality gates, Conventional Commits, branche, identité et signature, relecture du message. |
| [github-protection](.claude/skills/github-protection/SKILL.md) | Poser, vérifier ou modifier la protection de `main`. Le ruleset est versionné en JSON à côté du skill. |
| [security](.claude/skills/security/SKILL.md) | Avant toute nouvelle source de données, moyen d'accès ou surface d'exposition, et en cas de suspicion de fuite de secret. |

Trois points sont trop structurants pour n'exister que dans un skill :

- **Aucun commit n'est lancé avant validation explicite du message par le mainteneur.**
- **Les commits et les tags sont signés.** Un commit non signé n'entre pas dans `main`, le ruleset l'exige.
- **Le dépôt est public** — voir ci-dessous.

## Confidentialité des tiers

X10 peut être intégré par des projets, ou consommer des sources, dont les responsables ne souhaitent pas être cités publiquement : soit qu'ils ne communiquent pas sur leur usage, soit qu'ils préfèrent exposer leurs propres interfaces plutôt que la mécanique sous-jacente.

Le dépôt ne nomme donc **ni projet utilisateur ni source sans accord explicite**. Cela couvre le code, les commentaires, la documentation et les messages de commit.

Un contrôle local vérifie chaque commit contre une liste de termes concernés. Cette liste n'est **pas** versionnée : l'y écrire reviendrait à publier précisément ce qu'elle protège. Sur un clone neuf, en demander le contenu au mainteneur plutôt que de sauter le contrôle.

Les sources effectivement intégrées et documentées dans `x10-catalog` ne relèvent pas de cette règle : leur nom, leur licence et leur provenance doivent au contraire être explicites, c'est une exigence produit.

## Portée

Ne pas introduire de dépendances lourdes du domaine (`xarray`, `cfgrib`, `eccodes`, `ecmwf-opendata`) hors de `x10-connectors`, et en extras optionnels par connecteur. Le noyau doit rester léger et installable sans stack scientifique.
