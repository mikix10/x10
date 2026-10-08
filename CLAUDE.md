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

**Deux connecteurs réels existent**, et la donnée est décodée : `EcmwfIfsOpenDataConnector` télécharge des messages GRIB2 depuis ECMWF open data ; `MeteoFrancePntConnector` récupère les paquets AROME et ARPEGE republiés en open data, et le module `decoding` les ouvre en tableaux `xarray` avec les noms standards CF. Restent des ébauches : l'API n'expose aucun point d'entrée, le catalogue n'est pas peuplé, rien n'est stocké.

Deux notes publiques établissent par la mesure ce que Météo-France expose réellement : [docs/arome-paquets-et-api-ciblee.md](docs/arome-paquets-et-api-ciblee.md) et [docs/arpege-paquets-et-api-ciblee.md](docs/arpege-paquets-et-api-ciblee.md).

## Structure

Monorepo `uv` workspace (`[tool.uv.workspace]` dans [pyproject.toml](pyproject.toml), membres `packages/*` et `services/*`).

| Chemin | Rôle | Contenu actuel |
|---|---|---|
| [packages/x10-models/](packages/x10-models/) | **vocabulaire** de domaine partagé | `Agent`, `Dataset`, `Distribution`, `Retrieval`, `GeoPoint`, `Observation`, `Provenance` |
| [packages/x10-catalog/](packages/x10-catalog/) | **registre** et politique de résolution | `CatalogEntry`, ordre de repli entre origines |
| [packages/x10-connectors/](packages/x10-connectors/) | chaîne ETL : téléchargement, décodage, normalisation, écriture | `BaseConnector`, `ConnectorResult`, `EcmwfIfsOpenDataConnector`, `MeteoFrancePntConnector`, décodage GRIB2, écriture NetCDF-CF, journalisation ECS |
| [packages/x10-storage/](packages/x10-storage/) | abstractions de persistance | `StorageAdapter`, `StorageRecord` |
| [services/x10-api/](services/x10-api/) | démonstrateur API (FastAPI) | fonction `hello()` |

Chaque membre suit le même moule, à reproduire pour tout nouveau package : layout `src/`, build `hatchling`, `version = "0.1.0"`, `requires-python = ">=3.12,<3.14"`, `license = "BSD-3-Clause"` avec une copie de `LICENSE` dans le dossier du package, classifiers et `project.urls` renseignés, marqueur `py.typed`, dossier `tests/`, et toute l'API publique exportée depuis le `__init__.py` avec un `__all__` explicite.

Règle de dépendance : `x10-api` → packages ; `x10-connectors` / `x10-storage` / `x10-catalog` → `x10-models`. Ne pas créer de dépendance descendante depuis `x10-models`, qui ne dépend de rien. `x10-connectors` et `x10-catalog` y sont câblés en `[tool.uv.sources]` (`{ workspace = true }`).

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
- **Accès ECMWF : le client officiel `ecmwf-opendata`**, en extra optionnel `ecmwf` de `x10-connectors`. Il implémente déjà l'index et les plages d'octets que nos décisions visaient, et expose quatre origines — ECMWF, AWS, Azure, Google — ce qui sert la redondance. Ne pas réimplémenter.
  **Deux pièges vérifiés le 29/09/2026.** Le client n'expose **aucun délai maximal** de requête ; ses valeurs de reprise par défaut, 500 tentatives espacées de 120 s, autorisent une attente de plusieurs heures. Le connecteur les abaisse à 3 et 10 s, et un test le garantit.
- **La sélection par plages d'octets ne porte jamais sur la géographie.** L'index adresse le message, et un message GRIB2 est un champ global dont la section de données est un bloc unique compressé en CCSDS — template 42, grille 1440 × 721. Un sous-domaine s'obtient après décodage, pas au téléchargement. Vrai pour tout client.
- **Journalisation : `logging` standard, champs Elastic Common Schema, et la bibliothèque n'impose rien.** Aucun `basicConfig`, aucun handler, aucun format — seulement un `NullHandler`. C'est l'application qui choisit la destination et le rendu ; imposer du JSON casserait toute application nous intégrant. Un `EcsJsonFormatter` est fourni **pour les applications**, rien ne l'installe.
  **Trois points du schéma à respecter.** `event.outcome` n'admet que `success`, `failure` ou `unknown` — le champ `outcome` de `ConnectorResult` reprend ce vocabulaire pour éviter une correspondance. `event.duration` se compte en **nanosecondes**. Et `event.category` a un vocabulaire fermé où aucune valeur ne désigne l'acquisition de données ; `network` et `file` sont retenues.
  **Deux pièges vérifiés.** `extra=` lève une `KeyError` sur les attributs réservés de `LogRecord` — `message`, `name`, `levelname`, `asctime`, `args` — donc la journalisation échouerait elle-même ; un test vérifie qu'aucun champ émis n'y figure. Et le rendu JSON est en **ASCII pur** : une console `cp1252` corromprait sinon les accents de nos messages.
- **Vocabulaire aligné sur DCAT, PROV-O et INSPIRE.** La correspondance complète est dans [docs/vocabulaire.md](docs/vocabulaire.md) — notre pierre de Rosette, qui joue le rôle que GeoDCAT-AP joue entre INSPIRE et DCAT. **La consulter avant d'ajouter ou de renommer un terme du vocabulaire** : la plupart des notions sont déjà normalisées.
  Deux points vérifiés le 02/10/2026. La codelist INSPIRE des rôles est gouvernée au niveau **« Legal (EU) »**, donc réglementaire. Et `dcterms:publisher` n'est **pas** une propriété de `dcat:Distribution` : elle appartient à la ressource, d'où `Dataset.publisher` et une extension X10 nommée `Distribution.provider`, DCAT ne modélisant aucun agent par distribution.
- **Licence et restriction d'accès sont deux notions.** `Distribution.license` porte les conditions d'usage, `Distribution.access_rights` les motifs juridiques de restriction, repris verbatim de la codelist INSPIRE des alinéas de l'article 13. Les confondre produit des métadonnées fausses.
- **Vocabulaire du catalogue aligné sur DCAT et PROV-O**, sans sérialisation RDF. Ces standards distinguent depuis longtemps ce que notre premier modèle confondait : `dcterms:creator` le producteur, `dcterms:publisher` le diffuseur, `dcat:Distribution` un accès concret, `dcat:CatalogRecord` une ré-exposition après moissonnage, et PROV-O le lignage. Les réinventer aurait été une faute ; un export DCAT ou STAC reste possible sans rien reprendre.
  **`DataSource` est supprimé** — question en suspens depuis le premier connecteur, désormais tranchée. Le vocabulaire (`Agent`, `Dataset`, `Distribution`, `Retrieval`) vit dans `x10-models` parce que ce sont des modèles de domaine ; le registre et la politique de résolution vivent dans `x10-catalog` parce qu'un registre est un comportement, pas un type.
- **Une `Distribution` par origine**, et non une distribution à plusieurs URL. Chacune porte sa priorité et sa licence — un ré-exposant peut ajouter ses conditions —, ce sur quoi s'appuie la résolution. **STAC ne convient pas ici** : sa spécification pose qu'il ne doit y avoir qu'un seul `host`, ce qui exclut la redondance.
- **Bascule d'origine, mais pas sur n'importe quelle erreur.** Un échec d'accès entraîne un repli sur l'origine suivante ; une erreur de notre fait ou de la requête — plafond de volume, chemin invalide, paramètre absurde — n'en entraîne aucun, puisqu'une autre origine servirait la même donnée et échouerait pareillement. Voir `NON_REESSAYABLE`.
- **`Retrieval` porte l'origine effectivement retenue**, qui peut différer de celle demandée. `Provenance` subsiste avec un rôle distinct : attribution d'une **valeur**, là où `Retrieval` décrit l'acquisition d'un **artefact**.
- **Deuxième source : les paquets Météo-France, par la voie sans authentification**, donc **X10 ne porte aucun secret**. Le choix exclut le temps sensible, les niveaux isothermes et le sommet d'atmosphère, réservés à l'API ciblée ; il gagne une archive plus profonde et le géopotentiel aux niveaux hauteur. Les deux voies **ne se recouvrent pas** : ce ne sont donc pas deux `Distribution` d'un même `Dataset`, que le modèle suppose interchangeables, mais deux jeux distincts. Mesures et détail dans les deux notes de `docs/`.
- **Pas de téléchargement sélectif par plage d'octets chez Météo-France** : le producteur ne publie aucun index, et le reconstruire se fige au-delà d'environ 3 500 requêtes successives sur un même objet. Le levier de sélection est le **choix du paquet**, d'où un plafond de volume par défaut à 256 Mio — il laisse passer la surface et arrête les niveaux.
- **Les grandeurs vectorielles se stockent en composantes.** Direction et force du vent sont **écartées au décodage** et recalculées à la demande. La direction est une grandeur circulaire : la moyenne arithmétique de 350° et 10° vaut 180°, soit l'exact opposé de la réponse juste, et interpolation, ré-échantillonnage et écart-type sont faux de la même façon.
  **Vérifié le 06/10/2026 sur 4,66 millions de points réels** d'un paquet AROME SP1 : la reconstitution depuis les composantes donne un écart maximal de **0,015 m/s sur la force** et de **0,25° sur la direction dès 3 m/s**. La seule dégradation est sous 0,5 m/s — jusqu'à 44° — là où la direction n'a pas de sens physique. Deux champs sur quatre disparaissent sans perte.
  Corollaire : ce qui est intrinsèquement scalaire, une rafale maximale, reste scalaire. L'API ciblée du producteur et les données ouvertes de l'ECMWF n'exposent d'ailleurs aucune direction.
- **La correspondance GRIB vers CF nous incombe, mais le vocabulaire CF ne manque pas.** Le tableau CF, version 95, compte plus de cinq mille noms et contient `wind_speed`, `wind_from_direction`, `visibility_in_air` et le reste ; c'est **la table de correspondance livrée par ecCodes** qui est incomplète — 9 codes sur 51 pour AROME, 9 sur 64 pour ARPEGE. `decoding.CF_STANDARD_NAMES` comble le manque, **chaque nom vérifié présent au tableau officiel**. Un nom inventé produirait un fichier qui se dit conforme sans l'être, et `SANS_NOM_CF` recense ce que CF ne couvre réellement pas.
  Piège associé : la chaîne de décodage pose `standard_name = "unknown"`, valeur **pire qu'une absence**. Elle est retirée.
- **Pas de dépendance à `MeteoFetch`.** Le paquet couvre un périmètre voisin, mais son dépôt porte un `LICENSE` en **GPL-2.0** tandis que son `pyproject.toml` déclare **MIT**. Sous GPL-2.0, la dépendance contaminerait notre publication BSD-3-Clause. Ni dépendance ni reprise de structure tant que l'ambiguïté n'est pas levée.
- **Les constantes propres à une source ne sont pas réexportées par `x10_connectors`.** Deux sources ne peuvent pas partager `SOURCE_NAME` dans un espace plat ; elles se prennent au module. Seuls le commun et les points d'entrée sont réexportés.
- **Les tests ne téléchargent rien et ne stockent rien.** Un message GRIB2 valide se construit en mémoire par ecCodes : quelques centaines d'octets suffisent à exercer géométrie, valeurs manquantes, cumuls et vent. Voir `tests/fixtures_grib.py`. **Aucune donnée réelle n'est commise au dépôt**, et la suite par défaut tourne hors ligne. Les tests atteignant le service réel portent le marqueur `network`.
- **Couverture : deux vues depuis une seule mesure.** La vue **informative**, dans `pyproject.toml`, n'exclut rien et affiche le taux réel — 92 % en branches au 08/10/2026. La vue **barrière**, dans `.coveragerc-offline`, écarte le code que seuls les tests `network` exercent et porte le seuil de **90 %**, atteint à 96 %. Un seuil global serait mal posé dans les deux sens : trop haut il sanctionnerait une exclusion délibérée, trop bas il ne se déclencherait qu'après un effondrement.
  **Piège à ne pas reproduire** : le marqueur est `# couvert par les tests reseau` et **ne contient pas `pragma: no cover`**, que les exclusions par défaut reconnaîtraient — le code serait alors masqué dans les **deux** vues, y compris celle qui doit montrer l'écart. Les exclusions s'appliquent au rapport et non à la mesure, donc un même fichier de données se relit des deux façons.
- **La sortie NetCDF suit ce que les producteurs font, pas ce qu'une convention de découverte propose.** Relevé de quatre chaînes réelles — NCEP via Unidata, deux jeux de la NOAA, l'outil officiel d'ECMWF : toutes déclarent `Conventions` en CF et posent une poignée d'attributs que **CF recommande lui-même** à sa section 2.6.2 — `title`, `institution`, `source`, `history`, `references`, `comment`. Aucune n'emploie ACDD. `Conventions` liste ses valeurs **séparées par des blancs**, ECMWF écrivant par exemple `"CF-1.6 C3S-0.1"`.
  **La licence est le seul ajout.** CF n'en définit aucun attribut, or une donnée qui quitte le système sans la sienne n'est pas exploitable. L'attribut `license` est émis, son nom venant d'ACDD, mais **`ACDD-1.3` n'est pas déclaré** : nous n'émettons pas l'ensemble qu'ACDD exige, et le déclarer serait la faute même que l'on corrige sur les unités. Un attribut global supplémentaire ne rend aucun fichier non conforme à CF.
- **Les unités sont ramenées à la forme canonique d'UDUNITS, par une table fermée.** ecCodes écrit `m s**-1`, la forme canonique est `m s-1`. **Vérifié dans la grammaire d'UDUNITS-2 le 08/10/2026 : `**` y est un opérateur d'exposant valide**, donc la forme d'ecCodes n'est pas non conforme — j'avais d'abord soutenu le contraire. La conversion se justifie autrement : la suite de tests d'UDUNITS n'emploie que la forme à tiret, tous les producteurs aussi, et la forme `**` ne tient qu'à la correspondance la plus longue puisqu'un `*` seul vaut multiplication. Un consommateur sans analyseur UDUNITS complet peut donc la mal lire.
  `output.UDUNITS` traduit et **lève plutôt que de deviner** sur une unité inconnue ; l'unité d'origine reste dans `GRIB_units`.
  **Un validateur portable existe, contrairement à ce qui était écrit ici.** `cfchecker` exige bien la bibliothèque C UDUNITS-2, mais `cf-units` publie des roues avec UDUNITS-2 **embarqué** pour les trois systèmes, en ABI stable, sous BSD-3-Clause. Les vingt entrées de la table ont été soumises à UDUNITS le 08/10/2026 : les seize formes à exposant sont valides des deux côtés et **de définition réduite identique**, et les quatre que UDUNITS refuse sont exactement les quatre qui ne sont pas des unités. Reste à décider si `cf-units` entre au groupe de développement pour que le test valide au lieu d'affirmer.
  La garantie actuelle demeure l'ensemble fermé, plus un test marqué `network` confrontant la table aux paquets réels — c'est ainsi qu'`J m**-2` a été trouvée manquante, après 1,3 Go balayés.
  **Tout ce qui précède est établi et daté dans [docs/unites-et-interoperabilite.md](docs/unites-et-interoperabilite.md)**, avec la méthode pour le rejouer.

- **Les options de `cfgrib` qui décident de la forme du résultat sont écrites, pas héritées.** `open_datasets` expose dix-huit paramètres ; s'en remettre à leurs défauts laisse une version mineure changer nos sorties sans que rien ne le signale. Voir `decoding.OPTIONS_CFGRIB`, où chaque valeur porte sa raison.
  **Trois défauts à connaître, relevés le 08/10/2026.** `squeeze=True` **écrase les dimensions de longueur 1** : un paquet à une échéance rendait trois axes, un paquet à deux en rendait quatre — même donnée, même code, structure différente selon le contenu du fichier. Il passe à `False`, d'où **cinq axes constants** (`time`, `step`, niveau, `latitude`, `longitude`) et une référence de structure enfin tenable. `errors='warn'` journalise un message illisible puis **poursuit** : l'appelant reçoit un tuple amputé, sans exception ni avertissement, et le compte rendu dirait `success` sur une donnée incomplète — le défaut passe à `raise`, la tolérance restant accessible par paramètre. `values_dtype` reste `float32`, délibérément : les producteurs quantifient sur 12 bits, la mantisse en porte 24.
- **Le référentiel géodésique est décrit, plus supposé.** Les modèles travaillent sur une **sphère de 6 371 229 m** — `shapeOfTheEarth = 6` — et non sur WGS84. Le GRIB le déclarait, notre NetCDF le perdait. `output.grid_mapping` émet désormais une variable `crs` conforme à l'annexe F de CF, et renvoie **`None` plutôt qu'un défaut** quand l'information manque : supposer à la place du producteur serait la faute que l'on corrige.
  Inutile de recoder la table 3.2 du format : ecCodes la résout, `earthIsOblate` tranchant entre sphère et ellipsoïde. **Piège vérifié le 08/10/2026** : ecCodes signale une clé entière absente par `INT32_MAX`, et lu sans précaution ce marqueur donnerait une Terre de 2 147 483 647 mètres qu'aucun contrôle de conformité ne rattraperait.
- **Manque CF restant : `cell_methods` sur les cumuls.** `GRIB_stepType = 'accum'` est connu et conservé, mais n'est pas traduit. Sans lui, rien ne distingue un cumul d'un instantané, et moyenner des cumuls est la même classe d'erreur que moyenner des directions de vent.
- **Domaine pilote : météo, ECMWF IFS open data.** Techniques visées : téléchargement sélectif par paramètre et par échéance, requêtes HTTP Byte-Range sur les GRIB2 pour éviter le transfert intégral, normalisation vers NetCDF-CF.

## Ordre de travail retenu

**Fait**, leçons consignées dans « Décisions arrêtées » : socle technique et outillage, protection de `main`, connecteur ECMWF IFS, catalogue multi-origines éprouvé par la bascule d'origine, puis deuxième source Météo-France avec décodage GRIB2 et normalisation.

1. **Étoffer les modèles de domaine** — unités, emprises géographiques, séries temporelles, qualité.
2. **Peupler le catalogue** — entrées réelles pour ECMWF, AROME et ARPEGE, dont l'inventaire des variables est **dérivé des fichiers**, jamais du descriptif technique du producteur.
3. **Sortie NetCDF-CF et stockage** — écrire ce qui est décodé, décider de Zarr, puis exposer par l'API.

## Reste à faire

Ne figurent ici que les points qui **contraignent une décision de
conception** : il faut les avoir en tête au moment de trancher, pas au moment
d'ouvrir un chantier. Le cap est dans [PLAN.md](PLAN.md).

- **Réexaminer Codecov une fois, à la publication de la 1.0.0.** La barrière de couverture est locale et sans service tiers ; les courbes de tendance et le commentaire de couverture différentielle prennent leur sens quand le projet a une histoire et des contributeurs. Raisonnement complet dans [docs/tests-et-couverture.md](docs/tests-et-couverture.md).
- **Métriques de supervision** — les journaux permettent à une chaîne ELK de dériver taux de succès, latence et volume, mais la détection d'incident dépend alors du délai d'indexation. Un point d'entrée de métriques, ou un contrôle de santé par source, reste à prévoir si un besoin de supervision temps réel apparaît.
- **Montée de majeure des actions GitHub** — changement fonctionnel, à tester isolément, et sans jamais abandonner l'épinglage par empreinte. Si un nom de job change au passage, suivre la règle d'ordre du skill `github-protection` : un contexte requis sans job correspondant bloque toute fusion définitivement.
- **Publication PyPI** — par Trusted Publishing plutôt qu'un jeton. Le jour venu, la matrice trois systèmes est la garantie que le paquet s'installe ailleurs que sur la machine du mainteneur.

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
