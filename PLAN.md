# Plan de travail X10

Vue **macroscopique** : les phases et leur état. Le *pourquoi* des choix est
dans la section « Décisions arrêtées » de [CLAUDE.md](CLAUDE.md) ; le *comment
contribuer* dans [CONTRIBUTING.md](CONTRIBUTING.md).

**État au 16 octobre 2026**, après une analyse d'architecture complète dont
les constats sont repris phase par phase.

## Objectif

Construire un monorepo Python pour X10, avec plusieurs packages publiables,
intégration continue, publication PyPI, documentation ReadTheDocs, et base
technique préparée pour un futur déploiement Docker/Kubernetes.

## Où en est l'architecture

Six membres, et un déséquilibre qui oriente la suite.

| Membre | Source | Rôle tenu aujourd'hui |
|---|---:|---|
| `x10-connectors` | 2 945 l. | acquisition, décodage, normalisation, écriture, contrat |
| `x10-client` | 1 049 l. | assemblage de la chaîne et compte rendu |
| `x10-models` | 232 l. | vocabulaire de domaine |
| `x10-catalog` | ~330 l. | registre, interrogation à facettes, catalogue peuplé |
| `x10-storage` | 25 l. | **une interface sans implémentation ni appelant** |
| `x10-api` | 8 l. | une fonction `hello()` |

`x10-connectors` porte **73 % du code source**. Ce n'est pas un défaut en soi
— c'est là que vit le métier — mais cela dit où se trouve le risque de
concentration, et que trois membres sont encore des déclarations d'intention.

**Ce qui est vérifié et tient.** Le noyau s'importe avec la seule `pydantic`,
sans charger `cfgrib` ni `xarray` : la promesse d'un socle léger est réelle,
et mesurée. Le graphe de dépendances internes est acyclique et en couches.
Aucun paquet n'importe un membre de `services/`, et un test l'exige.

**Ce qui ne tient pas encore**, et devient donc du travail :

- **Le catalogue n'a pas de registre.** `CatalogEntry` décrit une entrée ;
  rien ne les enregistre, ne les cherche ni ne les résout depuis un besoin.
  C'est l'écart entre l'intention écrite — « un registre est un comportement »
  — et le code.
- **`x10-storage` n'est dans le chemin de personne.** La seule écriture du
  dépôt passe par `netcdf_cf.write_netcdf` et `base.atomic_write`. L'abstraction
  de persistance est contournée, pas utilisée.
- **Trois dépendances directes ne sont pas déclarées**, et ne fonctionnent que
  par transitivité : `pydantic` et `numpy` dans `x10-connectors`, `pydantic`
  dans `x10-client`. À l'inverse, `x10-api` déclare `fastapi` et `uvicorn`
  qu'il n'importe pas.

## Phase 1 — Initialisation du dépôt — **faite**

- [x] Structure du monorepo et configuration racine
- [x] Python 3.12 en cible, 3.13 en canari non bloquant
- [x] Licence BSD-3-Clause, à la racine et dans chaque paquet publiable
- [x] `uv` en espace de travail, `uv.lock` commité
- [x] Portes de qualité : `ruff` (lint et format), `mypy --strict`, `pytest`
- [x] Métadonnées PyPI complètes, build vérifié sur tous les membres
- [x] Conventions : GitHub Flow, Conventional Commits, commits signés en SSH
- [x] Dépôt distant, protection de `main` par un ruleset versionné

## Phase 2 — Socle technique — **faite pour la structure, pas pour le contenu**

Six membres autonomes, versionnés, typés et publiables :

- [x] `x10-models` — le vocabulaire de domaine
- [x] `x10-connectors` — acquisition, décodage, normalisation
- [x] `x10-client` — l'appelant de la chaîne, et son compte rendu
- [~] `x10-catalog` — **le type d'entrée existe, le registre reste à écrire**
- [~] `x10-storage` — abstraction posée, **sans implémentation ni appelant**
- [ ] `x10-api` — enveloppe seule

- [x] Le noyau s'installe et s'importe **sans la pile scientifique**, vérifié
- [x] Le vocabulaire public est figé dans une référence relue en revue
- [ ] Déclarer les trois dépendances directes aujourd'hui transitives

## Phase 3 — Packages métier et données — **en cours**

- [x] Vocabulaire aligné sur DCAT, PROV-O et INSPIRE, avec sa pierre de
      Rosette dans [docs/vocabulaire.md](docs/vocabulaire.md)
- [x] Deux sources open data intégrées, avec provenance et licence : ECMWF
      IFS, et les paquets AROME et ARPEGE de Météo-France
- [x] Décodage GRIB2 et normalisation vers les noms standards CF
- [x] Écriture des sorties normalisées en NetCDF-CF, avec licence et provenance
- [x] Contrôles d'intégrité dans la chaîne : tables locales, champs perdus au
      nommage, version des tables de l'OMM
- [x] Contrat de sortie, et compte rendu de pipeline lisible sans connaître
      le découpage en granules
- [x] **Registre de catalogue** — `Registry`, recherche à facettes, et deux
      vues dont une seule engage
- [~] **Catalogue peuplé pour Météo-France**, inventaire **dérivé de six
      granules réels** et daté par son `InventorySource` ; reste l'IFS, faute
      de granule au corpus
- [~] Modèles de domaine : `Variable`, `SourceTerms` et `InventorySource`
      faits ; restent emprises géographiques, séries temporelles, qualité
- [ ] Décision sur Zarr, et sur ce que `x10-storage` doit réellement porter

## Phase 4 — API et démonstrateur — **non commencée**

**L'API sert, le client consomme** — la phrase qui sépare `x10-api` de
`x10-client` et décide de ce qui a sa place dans chacun.

- [ ] Service API de démonstration, et couche FastAPI
- [ ] Accès cohérent aux données exposées
- [ ] Décider **où vivent les modèles que l'API expose**. `ConnectorResult` et
      `Contract` vivent dans `x10-connectors` ; les servir obligerait l'API à
      en dépendre. Le coût est aujourd'hui **nominal et non physique** —
      vérifié, le noyau s'importe sans la pile scientifique — mais la question
      se tranche avant d'écrire l'API, pas après.

## Phase 5 — CI/CD et publication — **partiellement faite**

- [x] Intégration continue : lint, typage, tests, build
- [x] Matrice trois systèmes — Linux, Windows, macOS — avec canari non bloquant
- [x] Couverture de tests, barrière locale, sans service tiers
- [x] Contrôle des métadonnées de distribution avant publication
- [x] Actions épinglées par empreinte, jeton restreint en lecture
- [x] Signatures des commits vérifiées par un job, le ruleset n'y suffisant pas
- [x] Analyse de sécurité CodeQL, sur le code et sur les workflows
- [ ] Publication PyPI, par Trusted Publishing plutôt qu'un jeton
- [ ] Gestion des versions et des tags

## Phase 6 — Documentation — **en cours**

- [x] Documentation de référence dans `docs/` : vocabulaire, relevés de
      sources, organisation des tests, unités, intervalles, agrégation
- [x] Porte d'entrée contributeur
- [ ] **Glossaire des concepts**, distinct de la pierre de Rosette : ce que
      nous appelons normalisation, granule, contrat, compte rendu — rédigé
      pour qui n'est pas du domaine
- [ ] Configuration ReadTheDocs, avec `/fr/` et `/en/`
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

## La question qui commande la suite

**Un consommateur ne demande pas « le paquet SP1 », il demande « la
température à deux mètres sur telle emprise, pour telle échéance ».** Rien
dans X10 ne sait traduire le second en premier : la requête que prend un
connecteur est déjà exprimée dans les termes du producteur.

C'est le rôle du catalogue, et c'est pourquoi il est devenu la prochaine
action plutôt que l'étoffement des modèles. Trois choses en découlent, dans
cet ordre :

1. **Un registre** — enregistrer des entrées, les chercher, et rendre une
   résolution. Le comportement que `x10-catalog` annonce sans l'avoir.
2. **Un inventaire de variables dérivé des fichiers**, et non des descriptifs
   des producteurs, qui se sont déjà révélés incomplets ou faux.
3. **Une requête exprimée en besoin**, que le catalogue traduit en sélection
   de producteur. C'est elle qui rendra `x10-api` possible sans que le client
   final connaisse AROME.

Le compte rendu du client y prépare déjà : il répond aux questions d'un
consommateur sans exiger qu'il connaisse le découpage en granules.

## Prochaine action

**Écrire le registre de catalogue**, puis le peupler avec les deux sources
déjà intégrées, l'inventaire des variables étant dérivé des fichiers.

Plusieurs choix y dépendent de la manière dont le système sera exploité ;
voir la section « Préciser la cible d'exploitation avant de trancher » de
[CLAUDE.md](CLAUDE.md).
