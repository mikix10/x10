# AGENTS.md

Guide de travail des agents sur le dépôt X10.

> **Source unique.** `CLAUDE.md` n'en porte qu'un import : Claude Code ne lit
> `AGENTS.md` qu'en repli, et ce repli dépend d'un drapeau de fonctionnalité.
> `/memory` dit ce qui est chargé. **`CLAUDE.local.md` ne se renomme pas** —
> il est propre à Claude Code, et `AGENTS.local.md` n'est lu par personne.

## Contexte

**GeoMetOc Open Data Server** — c'est l'accroche du dépôt, et la description publique sur GitHub.

X10 est la composante d'exploitation de données **géo-hydro-océano-météo open data**. L'objectif est d'exposer ces données via une API à des systèmes clients, à partir d'un socle de packages Python indépendants, publiables et réutilisables.

**Domaine pilote : météo, ECMWF IFS open data.** Techniques visées : téléchargement sélectif par paramètre et par échéance, requêtes HTTP Byte-Range sur les GRIB2 pour éviter le transfert intégral, normalisation vers NetCDF-CF.

> Le dépôt est public et ne nomme aucun projet utilisateur ni aucune source sans accord : voir « Confidentialité des tiers ».

Documents de cadrage à lire avant toute décision d'architecture :
- [README.md](README.md) — contexte, architecture cible, rôle de chaque package
- [PLAN.md](PLAN.md) — plan en 7 phases et critères de réussite

## État réel du dépôt

**Deux connecteurs réels existent**, et la donnée est décodée : `EcmwfIfsOpenDataConnector` télécharge des messages GRIB2 depuis ECMWF open data ; `MeteoFrancePntConnector` récupère les paquets AROME et ARPEGE republiés en open data, et le module `grib2` les ouvre en tableaux `xarray` avec les noms standards CF. Le catalogue est peuplé depuis le 19/10/2026, d'un inventaire dérivé des fichiers. Restent des ébauches : l'API n'expose aucun point d'entrée, et rien n'est stocké.

**Une note par source, établie par la mesure et non par le descriptif du producteur.** Météo-France : [docs/arome-paquets-et-api-ciblee.md](docs/arome-paquets-et-api-ciblee.md) et [docs/arpege-paquets-et-api-ciblee.md](docs/arpege-paquets-et-api-ciblee.md) pour la voie des paquets, [docs/meteofrance-portail-api.md](docs/meteofrance-portail-api.md) pour le portail d'API — 22 services, dont une suite océanique. Copernicus : [docs/copernicus-data-stores.md](docs/copernicus-data-stores.md) pour les trois magasins CDS, ADS et EWDS. Chacune renvoie au registre des écarts pour ce qui s'y écarte d'une norme.

## Structure

Monorepo `uv` workspace (`[tool.uv.workspace]` dans [pyproject.toml](pyproject.toml), membres `packages/*` et `services/*`).

| Chemin | Rôle | Contenu actuel |
|---|---|---|
| [packages/x10-models/](packages/x10-models/) | **vocabulaire** de domaine partagé | `Agent`, `Dataset`, `Distribution`, `Retrieval`, `GeoPoint`, `Observation`, `Provenance` |
| [packages/x10-catalog/](packages/x10-catalog/) | **registre** et politique de résolution | `Registry`, `CatalogEntry`, `Query`, recherche à facettes, inventaire dérivé des fichiers |
| [packages/x10-connectors/](packages/x10-connectors/) | chaîne ETL : téléchargement, décodage, normalisation, écriture | `BaseConnector`, `ConnectorResult`, `EcmwfIfsOpenDataConnector`, `MeteoFrancePntConnector`, décodage GRIB2, écriture NetCDF-CF, journalisation ECS |
| [packages/x10-storage/](packages/x10-storage/) | abstractions de persistance | `StorageAdapter`, `StorageRecord` |
| [services/x10-api/](services/x10-api/) | démonstrateur API (FastAPI) | fonction `hello()` |
| [services/x10-client/](services/x10-client/) | **appelant** de la chaîne, et compte rendu de ce qu'elle a fait | `Session`, `PipelineReport`, `observe` |

Chaque membre suit le même moule, à reproduire pour tout nouveau package : layout `src/`, build `hatchling`, `version = "0.1.0"`, `requires-python = ">=3.12,<3.15"`, `license = "BSD-3-Clause"` avec une copie de `LICENSE` dans le dossier du package, classifiers et `project.urls` renseignés, marqueur `py.typed`, dossier `tests/`, et toute l'API publique exportée depuis le `__init__.py` avec un `__all__` explicite.

Règle de dépendance : `x10-api` → packages ; `x10-connectors` / `x10-storage` / `x10-catalog` → `x10-models`. Ne pas créer de dépendance descendante depuis `x10-models`, qui ne dépend de rien. `x10-connectors` et `x10-catalog` y sont câblés en `[tool.uv.sources]` (`{ workspace = true }`).

**`services/` consomme, il n'est jamais consommé.** Aucun fichier de `packages/` ne doit importer `x10_client` ni `x10_api` — un test le vérifie. La conséquence pratique est que les paquets restent **validables seuls** par qui les installe : un test déplacé vers un membre de `services/` ferait dépendre la couverture d'un paquet de ce membre, soit la règle à l'envers. **L'API sert, le client consomme** : l'un expose une surface HTTP à des systèmes extérieurs, l'autre appelle la chaîne pour notre propre compte.

**Un module se nomme par ce qu'il traite, et les trois couches sont distinctes.**

| Couche | Modules | Nommage |
|---|---|---|
| **Transverse** | `base`, `observability`, `contract` | nom fonctionnel, aucun format |
| **Par source** | `ecmwf_ifs`, `meteofrance_pnt` | `<producteur>_<produit>` |
| **Par format** | `grib2`, `netcdf_cf` | **le format**, pas le sens de lecture |

**Les tests suivent le module, et leur docstring nomme le format dès la première ligne** — `test_grib2_local_tables.py`, `test_base_atomic_write.py`, `test_netcdf_cf.py`. Le nom de fichier ne porte pas tout : qui ouvre le fichier doit savoir à quoi il se rattache sans remonter l'arborescence.

**`x10-connectors` ne dépend pas de `x10-catalog`, et ne doit pas en dépendre.** Un connecteur ignore l'existence d'un catalogue : c'est l'appelant qui résout une entrée et lui transmet l'ordre des origines à tenter, par `CatalogEntry.origins()`.

## Commandes

```bash
uv sync --all-packages --dev   # installer le workspace et l'outillage
uv run pytest                  # tests
uv run ruff check .            # lint
uv run ruff format .           # format (la CI vérifie avec --check)
uv run mypy                    # typage strict sur les src/
uv build --all-packages        # construire les distributions

# Couverture : taux reel affiche, puis seuil sur le code atteignable hors ligne.
uv run pytest --cov --cov-report=term-missing:skip-covered --cov-report=html
uv run coverage report --rcfile=.coveragerc-offline
uv lock                        # après tout changement de dépendance (la CI exige --locked)

# Tests atteignant un service reel : exclus par defaut.
uv run pytest -m network            # Meteo-France : aucun extra requis
UV_PROJECT_ENVIRONMENT=.venv-ecmwf uv sync --all-packages --dev --extra ecmwf
UV_PROJECT_ENVIRONMENT=.venv-ecmwf uv run pytest -m network   # ECMWF
```

Sous VSCode, ces commandes sont aussi exposées en tâches — **Portes de qualité** enchaîne lint, typage et tests. Les extensions recommandées sont proposées à l'ouverture du dossier ; elles sont configurées pour utiliser le `ruff` et le `mypy` **du projet** et non leurs binaires embarqués, faute de quoi l'éditeur et la CI divergeraient en silence.

Python **3.12** (pin dans [.python-version](.python-version)). Le `.venv/` local est provisionné par `uv`. `uv.lock` est commité et la CI le vérifie — toujours le régénérer après avoir touché aux dépendances.

## Conventions de code

- Python 3.12, `from __future__ import annotations` en tête de module, annotations de types systématiques.
- Syntaxe de types moderne : `str | None`, `list[str]`, `dict[str, Any]`.
- Modèles de domaine : Pydantic v2 avec `model_config = ConfigDict(frozen=True)`, contraintes exprimées via `Field` (`ge`/`le` sur les coordonnées, `min_length=1` sur les identifiants).
- **Le critère Pydantic ou dataclass est le franchissement de frontière, pas le rôle de l'objet.** Tout objet sérialisé — journaux, XCom d'un ordonnanceur, réponse d'API — est un modèle Pydantic : la conversion des chemins et des horodatages est alors gratuite et testée. `ConnectorResult` est dans ce cas. Un objet purement interne au processus reste une dataclass mutable, comme `StorageRecord`.
- Sur un modèle `frozen`, préférer `tuple[str, ...]` à `list[str]` pour les collections : une `list` rend le modèle non hashable.
- Classes de base abstraites : lever `NotImplementedError("Subclasses must implement X().")`.
- Valeurs numériques mesurées : `Decimal`, pas `float` (voir `Observation.value`). Les coordonnées restent en `float`.
- Toute donnée exploitée porte sa **provenance** et sa **licence** — c'est une exigence produit, pas un détail.
- Documentation et commentaires en français, identifiants et code en anglais — **ainsi que tout message qu'un programme lit**, voir « Langue » dans les décisions arrêtées.
  **La portée de cette règle est le code, pas la prose.** Elle couvre tout ce qu'un autre fichier peut importer ou lire — modules, classes, fonctions, constantes, **champs de modèles Pydantic**, vocabulaires sérialisés — ainsi que les variables locales de `src/`. Elle ne couvre **pas** les noms de fonctions `def test_*` : pytest les affiche comme description du comportement, ce sont donc de la prose, et la règle de documentation s'y applique.
  **Un renommage de masse se fait par jetons, jamais par texte.** Vérifié le 13/10/2026 : un `sed` sur `taille` ou `grille` réécrit la documentation française au passage — « la grid sont requis ». Le module `tokenize` ne rend un jeton `NAME` que pour un identifiant réel, et laisse intactes chaînes, docstrings, commentaires et texte littéral d'une f-string. **Trois catégories lui échappent pourtant à juste titre, et doivent être reprises à la main** : les entrées de `__all__`, les noms de paramètres d'un `@pytest.mark.parametrize`, et les vocabulaires émis sous forme de chaîne. Un contrôle de collision — le fichier porte-t-il déjà le nom cible ? — évite l'autre piège : `champ` renommé en `field` masquerait le `field` de `dataclasses`.

### Typage : `mypy --strict` ne se relâche jamais globalement

`strict = true` porte sur **notre** code, et c'est un choix durable. Une
dépendance sans types ne le remet pas en cause : elle reçoit une **dérogation
nommée et limitée à son module** dans le `pyproject.toml`, jamais un
abaissement global. On y lit alors exactement quelles bibliothèques ne sont
pas typées, au lieu d'un affaissement silencieux.

Le détail et la forme exacte : [docs/socle-et-paquetage.md](docs/socle-et-paquetage.md).

## Les principes qui gouvernent

Onze critères tranchent ce qu'aucune note de `docs/` ne couvre. **Leur ordre
compte** :

> **L'ordre est celui du coût d'ignorer.** Une valeur fausse qui ne se
> signale pas passe avant un refus de servir, qui passe avant une imprécision
> de prose.

| | Critère | Un cas qui l'a produit |
|---|---|---|
| **C1** | **Entre deux défauts, le plus cher est celui qui ne se voit pas.** Il arbitre les dix autres | `standard_name = "unknown"`, retiré : pire qu'une absence |
| **C2** | **Mesurer plutôt qu'affirmer** — et une **inexistence** se mesure comme le reste | la moitié des corrections du dépôt portent sur un « aucun » ou un « jamais » |
| **C3** | **Ne pas deviner à la place du producteur** | `grid_mapping` rend `None` ; `(0, 3, 6)` retiré plutôt que renommé |
| **C4** | **Fermer la classe, pas le cas** | une analyse interdit tout nom CF en littéral, pas seulement les deux trouvés |
| **C5** | **Rendre l'écart lisible dans un `git diff`** plutôt que le trancher | cinq références engendrées, jamais tenues à la main |
| **C6** | **Le paquet fournit le mécanisme, l'application fournit les valeurs** | le client résout un secret, le connecteur le reçoit en paramètre |
| **C7** | **Deux notions voisines, deux noms** — et on écrit ce que produirait la confusion | licence, droits d'accès et authentification sont **trois** notions |
| **C8** | **Pas de mécanique générale sous trois cas** | le catalogue ne construit aucune requête : il n'y a que deux sources |
| **C9** | **Un contrôle qui s'exécute vaut mieux qu'une consigne qui se lit** | deux garanties que la documentation déclarait acquises ne l'étaient pas |
| **C10** | **Une autorité se vérifie avant d'être reprise** | les libellés d'ecCodes sont d'ecCodes, pas de la norme |
| **C11** | **Une révision reste écrite à côté de l'énoncé qu'elle corrige** | le dépôt s'est contredit une quinzaine de fois, et l'a écrit |

**Trois tensions, et elles sont tranchées.** Entre *deviner* et *exposer*, ce
qui cède est **l'affirmation, jamais le champ** : il sort sans nom, mais il
sort. On **signale** quand la sortie peut porter l'écart, on **lève** quand
elle ne le peut pas — un champ perdu n'est pas une métadonnée dégradée. Et
l'exploitabilité l'emporte sur la fidélité **à condition que la forme
d'origine reste lisible à côté**.

**Quand s'arrêter d'instruire.** Une question paie quand elle change une
table, un contrôle, un refus, ou une affirmation fausse. **Deux tours
d'argument sans mesure nouvelle la closent.**

Les cas, les tensions et la règle de coût en entier :
[docs/criteres-de-choix.md](docs/criteres-de-choix.md).

## Décisions arrêtées — où les lire

**Soixante-deux décisions, avec leurs mesures et leurs dates, vivent dans
`docs/`**, rangées par sujet.

**Les consulter avant de trancher dans leur domaine** : la plupart des
questions qui s'y posent ont déjà reçu une réponse mesurée et datée.

| Sujet | Note | Ce qu'elle tranche |
|---|---|---|
| **Socle et paquetage** | [docs/socle-et-paquetage.md](docs/socle-et-paquetage.md) | Python, Pydantic, volumétrie, backend de build, langue, journalisation ECS, écriture atomique, lexique public |
| **Catalogue** | [docs/catalogue.md](docs/catalogue.md) | les deux vues, la gradation de ce qu'on expose, l'inventaire dérivé, les facettes, les origines et la bascule |
| **Sources et accès** | [docs/sources-et-acces.md](docs/sources-et-acces.md) | ECMWF, Météo-France, plages d'octets, place d'un secret, cadence d'un producteur |
| **Triplet et tables GRIB** | [docs/triplet-et-tables-grib.md](docs/triplet-et-tables-grib.md) | la correspondance GRIB vers CF, les versions de tables, les deux contrôles, et le troisième producteur traversé |
| **Formats de sortie** | [docs/formats-de-sortie.md](docs/formats-de-sortie.md) | NetCDF-CF, options de `cfgrib`, référentiel géodésique, compression, assemblage |
| **Tests et couverture** | [docs/tests-et-couverture.md](docs/tests-et-couverture.md) | corpus hors ligne, deux vues de couverture, contrat de sortie, signatures, CodeQL |
| **Vocabulaire** | [docs/vocabulaire.md](docs/vocabulaire.md) | DCAT, PROV-O, INSPIRE, licence contre droits d'accès, le mot `granule` |
| **Agrégation et rééchantillonnage** | [docs/agregation-et-reechantillonnage.md](docs/agregation-et-reechantillonnage.md) | composantes vectorielles, méthode par axe, ce qu'on refuse d'hériter |
| **Intervalles de temps** | [docs/intervalles-de-temps.md](docs/intervalles-de-temps.md) | `cell_methods`, périodes d'agrégation, hypercubes non homogènes |
| **Unités** | [docs/unites-et-interoperabilite.md](docs/unites-et-interoperabilite.md) | la forme canonique d'UDUNITS, et comment elle est validée |
| **Standards et outillage** | [docs/standards-et-outillage.md](docs/standards-et-outillage.md) | le modèle LinkML de la chaîne, et les quatre vocabulaires ajoutés |
| **Écarts des sources** | [docs/divergences-observees.md](docs/divergences-observees.md) | le registre engendré depuis les sondes, et ce qu'une sonde établit |

## Reste à faire

Ne figurent ici que les points qui **contraignent une décision de
conception** : il faut les avoir en tête au moment de trancher, pas au moment
d'ouvrir un chantier. Le cap est dans [PLAN.md](PLAN.md).

- **Réexaminer Codecov une fois, à la publication de la 1.0.0.** La barrière de couverture est locale et sans service tiers ; les courbes de tendance et le commentaire de couverture différentielle prennent leur sens quand le projet a une histoire et des contributeurs. Raisonnement complet dans [docs/tests-et-couverture.md](docs/tests-et-couverture.md).
- **Métriques de supervision** — les journaux permettent à une chaîne ELK de dériver taux de succès, latence et volume, mais la détection d'incident dépend alors du délai d'indexation. Un point d'entrée de métriques, ou un contrôle de santé par source, reste à prévoir si un besoin de supervision temps réel apparaît.
- **Montée de majeure des actions GitHub** — désormais proposée par Dependabot, **une demande par majeure** et non groupée : c'est un changement fonctionnel, à éprouver isolément. Sans jamais abandonner l'épinglage par empreinte, que Dependabot comprend et met à jour de concert avec le commentaire de version. Si un nom de job change au passage, suivre la règle d'ordre du skill `github-protection` : un contexte requis sans job correspondant bloque toute fusion définitivement.
- **Documentation publiée : prévoir une version anglaise `/en/`.** La documentation et les commentaires sont en français par décision ; une publication Read the Docs devra donc porter `/fr/` et `/en/`. Conséquence à garder en tête **dès maintenant** : ce sont les **docstrings** qui alimenteraient une référence d'API automatique, donc le coût de traduction croît à chaque module ajouté. À trancher au moment de la publication PyPI, dont cette note partage l'échéance.
- **Sous-paquet `formats/` au troisième format.** À sept modules la structure plate reste plus lisible, et un `formats/` appellerait un `sources/` par symétrie. Le point de bascule est l'arrivée d'un troisième format — une réorganisation à faire alors, pas avant.
- **Publication PyPI** — par Trusted Publishing plutôt qu'un jeton. Le jour venu, la matrice trois systèmes est la garantie que le paquet s'installe ailleurs que sur la machine du mainteneur.

## Procédures outillées (skills)

Les procédures pas-à-pas ne sont pas dans ce fichier : elles vivent dans `.claude/skills/`, versionnées avec le dépôt. Ce fichier ne garde que ce qui doit être connu en permanence.

| Skill | Quand l'invoquer |
|---|---|
| [commit](.claude/skills/commit/SKILL.md) | **Avant tout commit, sans exception.** Contrôle des termes proscrits, quality gates, Conventional Commits, branche, identité et signature, relecture du message. |
| [github-protection](.claude/skills/github-protection/SKILL.md) | Poser, vérifier ou modifier la protection de `main`. Le ruleset est versionné en JSON à côté du skill. |
| [security](.claude/skills/security/SKILL.md) | Avant toute nouvelle source de données, moyen d'accès ou surface d'exposition, et en cas de suspicion de fuite de secret. |
| [historique](.claude/skills/historique/SKILL.md) | Dès qu'une question porte sur **le fil de nos échanges** — qui a proposé quoi, quand une décision a basculé — et non sur l'état du code. Le transcrit de session est la source ; la mémoire de conversation n'en est pas une. |

Trois points sont trop structurants pour n'exister que dans un skill :

- **Aucun commit n'est lancé avant validation explicite du message par le mainteneur.**
- **Les commits et les tags sont signés**, et c'est la **CI** qui le vérifie, pas le ruleset. Voir « Signatures des commits » dans les décisions arrêtées : sous fusion par squash, `required_signatures` ne contrôle que le commit que GitHub vient de signer lui-même.
- **Le dépôt est public** — voir ci-dessous.

## Préciser la cible d'exploitation avant de trancher

Beaucoup de décisions qui paraissent techniques sont en réalité déterminées par la manière dont le système sera exploité. Or ce contexte vit souvent **hors du dépôt**, dans des analyses amont que rien ici ne reflète.

Avant d'arrêter un choix de conception, se demander si la réponse en dépend. Si oui, **poser la question plutôt que retenir un défaut raisonnable** : un défaut choisi dans l'ignorance du contexte produit une architecture qu'il faudra défaire, et le coût de la question est sans commune mesure.

Déclencheurs typiques :

- un composant est-il un démonstrateur ou un élément de production ;
- qui décide d'un emplacement, d'un format, d'une rétention ;
- une exigence de disponibilité, de volumétrie ou de conformité s'applique-t-elle ;
- une fonction manquante revient-elle à X10 ou à un autre composant du système.

Formuler la question par ses **conséquences** — ce que chaque réponse changerait concrètement — et non en termes abstraits. Le mainteneur peut alors trancher sans avoir à reconstituer le raisonnement.

## Confidentialité des tiers

X10 peut être intégré par des projets, ou consommer des sources, dont les responsables ne souhaitent pas être cités publiquement : soit qu'ils ne communiquent pas sur leur usage, soit qu'ils préfèrent exposer leurs propres interfaces plutôt que la mécanique sous-jacente.

Le dépôt ne nomme donc **ni projet utilisateur ni source sans accord explicite**. Cela couvre le code, les commentaires, la documentation et les messages de commit.

Un contrôle local vérifie chaque commit contre une liste de termes concernés. Cette liste n'est **pas** versionnée : l'y écrire reviendrait à publier précisément ce qu'elle protège. Sur un clone neuf, en demander le contenu au mainteneur plutôt que de sauter le contrôle.

Les sources effectivement intégrées et documentées dans `x10-catalog` ne relèvent pas de cette règle : leur nom, leur licence et leur provenance doivent au contraire être explicites, c'est une exigence produit.

## Portée

Ne pas introduire de dépendances lourdes du domaine (`xarray`, `cfgrib`, `eccodes`, `ecmwf-opendata`) hors de `x10-connectors`, et en extras optionnels par connecteur — `ecmwf` pour le client ECMWF, `grib` pour le décodage. Le noyau doit rester léger et installable sans stack scientifique.

La pile GRIB figure en revanche dans le **groupe de développement** : le décodage est du code métier, et l'intégration continue doit l'exercer. Cela ne change rien aux paquets publiés.
