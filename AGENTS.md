# AGENTS.md

Guide de travail des agents sur le dépôt X10.

> **Source unique.** `CLAUDE.md` n'en porte qu'un import, et cet import
> n'est pas facultatif : Claude Code lit `AGENTS.md` directement depuis la
> v2.1.277, **mais seulement en l'absence de `CLAUDE.md` et de
> `CLAUDE.local.md`** — or les deux existent ici. `/memory` dit ce qui est
> chargé, et **`CLAUDE.local.md` ne se renomme pas** : `AGENTS.local.md`
> n'est lu par personne.

## Contexte

**GeoMetOc Open Data Server.** X10 exploite des données
**géo-hydro-océano-météo open data** et les expose à des systèmes clients,
depuis un socle de packages Python indépendants, publiables et réutilisables.
**Domaine pilote : météo, ECMWF IFS open data** — téléchargement sélectif par
paramètre et par échéance, requêtes HTTP Byte-Range sur les GRIB2,
normalisation vers NetCDF-CF.

Avant toute décision d'architecture : [README.md](README.md) pour
l'architecture cible, [PLAN.md](PLAN.md) pour l'état des phases.

## Où vit quoi

**Six emplacements pilotent le comportement, et le critère qui les sépare est
toujours le même : qui le lit, quand, et est-ce appliqué ou consultatif.**

| Destination | Ce qui y va | Chargé |
|---|---|---|
| **`AGENTS.md`** | ce qui vaut pour **tout contributeur** et doit être su en permanence — impératif, sans justification | à chaque session |
| **`docs/*.md`** | le **pourquoi** mesuré et daté d'une décision | à la lecture |
| **`.claude/skills/`** | une **procédure pas-à-pas**, et son déclencheur | à l'invocation |
| **`CLAUDE.local.md`** | ce qui ne vaut que pour **un poste**, et ce qui porte sur nos propres défenses | à chaque session, non versionné |
| **mémoire de l'assistant** | les corrections de comportement reçues — **et rien qui doive valoir ailleurs** : elle est locale à la machine | au démarrage |
| **hooks, `permissions.deny`** | ce qui doit être **appliqué**, non lu | — |

**Deux conséquences.** Ce qu'un skill décrit, ce guide ne le redit pas : il
**nomme** le skill et son déclencheur. Et une règle qui doit valoir pour un
contributeur n'a jamais sa place dans la seule mémoire. Les trois niveaux —
public, privé, hors dépôt — sont dans [CONTRIBUTING.md](CONTRIBUTING.md),
tenus par `workspace-tests/test_niveaux.py`.

## État réel du dépôt

**Deux connecteurs réels, et la donnée est décodée.** ECMWF open data et les
paquets AROME/ARPEGE republiés ; le module `grib2` les ouvre en tableaux
`xarray` aux noms standards CF. Le catalogue est peuplé depuis le 19/10/2026.
Restent des ébauches : l'API n'expose aucun point d'entrée, rien n'est stocké.

**Un relevé par source**, établi par la mesure et non par le descriptif du
producteur : voir [docs/README.md](docs/README.md).

## Structure

Monorepo `uv` workspace ([pyproject.toml](pyproject.toml), membres
`packages/*` et `services/*`).

| Chemin | Rôle | Contenu actuel |
|---|---|---|
| [x10-models](packages/x10-models/) | **vocabulaire** de domaine partagé | 14 modèles — `Dataset`, `Distribution`, `Retrieval`, `Rights`, `Variable`, `SourceTerms`, `InventorySource`… |
| [x10-catalog](packages/x10-catalog/) | **registre** et politique de résolution | `Registry`, `CatalogEntry`, `Query`, facettes, inventaire dérivé des fichiers |
| [x10-connectors](packages/x10-connectors/) | chaîne ETL : télécharger, décoder, normaliser, écrire | `BaseConnector`, les deux connecteurs, `grib2`, `netcdf_cf`, journalisation ECS |
| [x10-storage](packages/x10-storage/) | abstractions de persistance | `StorageAdapter`, `StorageRecord` — ébauche, aucun appelant |
| [x10-api](services/x10-api/) | démonstrateur API (FastAPI) | fonction `hello()` |
| [x10-client](services/x10-client/) | **appelant** de la chaîne, et compte rendu | `Session`, `PipelineReport`, `observe`, sondes |

**Chaque membre suit le même moule**, à reproduire pour tout nouveau
paquet : layout `src/`, build `hatchling`, `requires-python = ">=3.12,<3.15"`,
`license = "BSD-3-Clause"` et sa copie de `LICENSE`, marqueur `py.typed`,
dossier `tests/`, et toute l'API publique dans un `__all__` explicite.

**Règle de dépendance** : `x10-api` → packages ; `x10-connectors`,
`x10-storage` et `x10-catalog` → `x10-models`, qui ne dépend de rien.
**`x10-connectors` ne dépend pas de `x10-catalog`** et ne doit pas : un
connecteur ignore l'existence d'un catalogue, c'est l'appelant qui résout une
entrée et lui transmet l'ordre des origines par `CatalogEntry.origins()`.

**`services/` consomme, il n'est jamais consommé.** Aucun fichier de
`packages/` n'importe `x10_client` ni `x10_api` — un test le vérifie. Les
paquets restent ainsi **validables seuls** : un test déplacé vers `services/`
ferait dépendre la couverture d'un paquet de ce membre, soit la règle à
l'envers. **L'API sert, le client consomme.**

**Un module se nomme par ce qu'il traite** : transverse par sa fonction
(`base`), par source en `<producteur>_<produit>`, par format **par le
format** et non le sens de lecture. **Les tests suivent le module, et leur
docstring nomme le format dès la première ligne.**

## Commandes

```bash
uv sync --all-packages --dev   # installer le workspace et l'outillage
uv run pre-commit install      # les controles avant chaque commit
uv run pytest                  # tests
uv run ruff check .            # lint
uv run ruff format .           # format (la CI verifie avec --check)
uv run mypy                    # typage strict sur les src/
uv build --all-packages        # construire les distributions
uv lock                        # apres tout changement de dependance

# Couverture : taux reel affiche, puis seuil sur le code atteignable hors ligne.
uv run pytest --cov --cov-report=term-missing:skip-covered --cov-report=html
uv run coverage report --rcfile=.coveragerc-offline
```

Les tests qui atteignent un service réel sont **exclus par défaut** ; leur
invocation est dans [tests-et-couverture](docs/tests-et-couverture.md).

Sous VSCode, la tâche **Portes de qualité** enchaîne lint, typage et tests.
Python **3.12** (pin dans [.python-version](.python-version)). `uv.lock` est
commité, et la CI le vérifie avec `--locked`.

## Conventions de code

- Python 3.12, `from __future__ import annotations` en tête de module,
  annotations systématiques, syntaxe moderne — `str | None`, `list[str]`.
- **Pydantic ou dataclass se décide au franchissement de frontière, pas au
  rôle.** Tout objet sérialisé — journal, XCom d'un ordonnanceur, réponse
  d'API — est un modèle Pydantic `frozen`, contraintes par `Field`. Un objet
  purement interne au processus reste une dataclass mutable.
- Sur un modèle `frozen`, `tuple[str, ...]` plutôt que `list[str]`, qui rend
  le modèle non hashable. Classe de base abstraite : lever
  `NotImplementedError("Subclasses must implement X().")`. Valeur mesurée :
  `Decimal`, pas `float` — les coordonnées restent en `float`.
- Toute donnée exploitée porte sa **provenance** et sa **licence** —
  exigence produit, pas détail.
- **Documentation et commentaires en français, identifiants et code en
  anglais — ainsi que tout message qu'un programme lit.** La portée est le
  code, y compris les champs de modèles et les vocabulaires sérialisés ; elle
  ne couvre **pas** les noms `def test_*`, que pytest affiche comme
  description.
- **Un renommage de masse se fait par jetons, jamais par texte** : un `sed`
  réécrit la prose au passage. `tokenize` ne rend un `NAME` que pour un
  identifiant réel ; trois catégories lui échappent et se reprennent à la
  main — `__all__`, les paramètres d'un `parametrize`, et les vocabulaires
  émis en chaîne.

### Écrire court, et justifier par le public servi

**Un texte se dimensionne sur ce qu'il change chez son lecteur, pas sur ce
qu'il a coûté à établir.** Vaut pour un message de commit, une demande de
fusion, une note, une réponse.

- **Le diff est lisible** : il n'a pas besoin d'être raconté.
- **Nommer le public plutôt que plaider le principe.** « Un chemin suffit à
  qui manipule à la main, une empreinte sert un traitement automatique » dit
  en une ligne ce qu'un paragraphe sur la nature des chemins ne dit pas.
- **Pas de récit** : ni comment on a trouvé, ni ce qui avait échappé.
- La longueur suit l'ampleur du changement : un correctif d'une ligne se
  décrit en une phrase.

### Typage : `mypy --strict` ne se relâche jamais globalement

`strict = true` porte sur **notre** code. Une dépendance sans types reçoit
une **dérogation nommée et limitée à son module**, jamais un abaissement
global : on lit alors quelles bibliothèques ne sont pas typées, au lieu d'un
affaissement silencieux. Forme exacte :
[socle-et-paquetage](docs/socle-et-paquetage.md).

## Les principes qui gouvernent

Onze critères tranchent ce qu'aucune note de `docs/` ne couvre, et **leur
ordre est celui du coût d'ignorer** : une valeur fausse qui ne se signale pas
passe avant un refus de servir, qui passe avant une imprécision de prose.

1. **C1 — entre deux défauts, le plus cher est celui qui ne se voit pas.** Il arbitre les dix autres.
2. **C2 — mesurer plutôt qu'affirmer**, et une **inexistence** se mesure comme le reste.
3. **C3 — ne pas deviner à la place du producteur.**
4. **C4 — fermer la classe, pas le cas.**
5. **C5 — rendre l'écart lisible dans un `git diff`** plutôt que le trancher.
6. **C6 — le paquet fournit le mécanisme, l'application fournit les valeurs.**
7. **C7 — deux notions voisines, deux noms**, et on écrit ce que produirait la confusion.
8. **C8 — pas de mécanique générale sous trois cas.**
9. **C9 — un contrôle qui s'exécute vaut mieux qu'une consigne qui se lit.**
10. **C10 — une autorité se vérifie avant d'être reprise.**
11. **C11 — une révision reste écrite à côté de l'énoncé qu'elle corrige.**

**Trois tensions, tranchées.** Entre *deviner* et *exposer*, ce qui cède est
**l'affirmation, jamais le champ** : il sort sans nom, mais il sort. On
**signale** quand la sortie peut porter l'écart, on **lève** quand elle ne le
peut pas. Et l'exploitabilité l'emporte sur la fidélité **à condition que la
forme d'origine reste lisible à côté**.

**Quand s'arrêter d'instruire.** Une question paie quand elle change une
table, un contrôle, un refus, ou une affirmation fausse. **Deux tours
d'argument sans mesure nouvelle la closent.** Les cas qui ont produit chaque
critère : [criteres-de-choix](docs/criteres-de-choix.md).

## Décisions arrêtées — où les lire

**Elles vivent dans `docs/`, avec leurs mesures et leurs dates, et se
consultent avant de trancher dans leur domaine** : la plupart des questions
qui s'y posent ont déjà reçu une réponse mesurée. L'index par sujet est
dans [docs/README.md](docs/README.md).

## Procédures outillées (skills)

Dans `.claude/skills/`. **Quatre sont versionnées** — le compte est dans
`workspace-tests/chiffres.txt`. **Cinq ne le sont pas** : `positioning`,
`echanges` et `deploiement` nomment des tiers ou une cible que le dépôt
public ne nomme pas ; `debut-de-session` et `fin-de-session` ne servent aucun
lecteur d'un clone. Elles fonctionnent : Claude Code charge les skills depuis
le disque, pas depuis l'index.

| Skill | Quand l'invoquer |
|---|---|
| [commit](.claude/skills/commit/) | **avant tout commit, sans exception** |
| [github-protection](.claude/skills/github-protection/) | poser, vérifier ou modifier la protection de `main` |
| [security](.claude/skills/security/) | avant toute nouvelle source, moyen d'accès ou surface d'exposition, et en cas de suspicion de fuite |
| [historique](.claude/skills/historique/) | dès qu'une question porte sur **le fil des échanges** et non sur l'état du code |

Trois points sont trop structurants pour n'exister que dans un skill :

- **Aucun commit n'est lancé avant validation explicite du message par le
  mainteneur**, sauf autorisation écrite pour un chantier nommé.
- **Les commits et les tags sont signés**, et c'est la **CI** qui le vérifie,
  pas le ruleset : sous fusion par squash, `required_signatures` ne contrôle
  que le commit que GitHub vient de signer lui-même.
- **Le dépôt est public**, et [CONTRIBUTING.md](CONTRIBUTING.md) dit ce qui
  n'y entre jamais.

## Préciser la cible d'exploitation avant de trancher

Beaucoup de décisions qui paraissent techniques sont déterminées par la
manière dont le système sera exploité — et ce contexte vit souvent **hors du
dépôt**. Avant d'arrêter un choix, se demander si la réponse en dépend ; si
oui, **poser la question plutôt que retenir un défaut raisonnable**, car un
défaut choisi dans l'ignorance du contexte produit une architecture qu'il
faudra défaire. Déclencheurs typiques : démonstrateur ou élément de
production ; qui décide d'un emplacement, d'un format, d'une rétention ; une
fonction manquante revient-elle à X10.

**Formuler la question par ses conséquences** — ce que chaque réponse
changerait concrètement — et non en termes abstraits.

## Portée

Ne pas introduire de dépendances lourdes du domaine — `xarray`, `cfgrib`,
`eccodes`, `ecmwf-opendata` — hors de `x10-connectors`, et en extras
optionnels par connecteur : `ecmwf` pour le client ECMWF, `grib` pour le
décodage. **Le noyau doit rester léger et installable sans pile
scientifique.** La pile GRIB figure en revanche dans le groupe de
développement : le décodage est du code métier, et l'intégration continue
doit l'exercer.
