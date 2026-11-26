# Plan de travail X10

Vue **macroscopique** : les phases et leur état. Le *pourquoi* des choix est
dans la section « Décisions arrêtées » de [AGENTS.md](AGENTS.md) ; le *comment
contribuer* dans [CONTRIBUTING.md](CONTRIBUTING.md).

**État au 19 novembre 2026.** Les constats repris phase par phase viennent
de l'analyse d'architecture du 16/10/2026 ; les volumes et l'état des
chantiers sont remesurés à la date du document.

## Objectif

Construire un monorepo Python pour X10, avec plusieurs packages publiables,
intégration continue, publication PyPI, documentation ReadTheDocs, et base
technique préparée pour un futur déploiement Docker/Kubernetes.

## Où en est l'architecture

Six membres, et un déséquilibre qui oriente la suite.

| Membre | Source | Rôle tenu aujourd'hui |
|---|---:|---|
| `x10-connectors` | 4 618 l. | acquisition, décodage, normalisation, écriture, contrat |
| `x10-client` | 1 884 l. | assemblage de la chaîne et compte rendu |
| `x10-models` | 418 l. | vocabulaire de domaine |
| `x10-catalog` | 300 l. | registre, interrogation à facettes, catalogue peuplé |
| `x10-storage` | 25 l. | **une interface sans implémentation ni appelant** |
| `x10-api` | 8 l. | une fonction `hello()` |

`x10-connectors` porte **63 % des 7 253 lignes de source** au 26/11/2026 —
les valeurs à jour sont engendrées dans
[chiffres.txt](workspace-tests/chiffres.txt). Ce n'est pas un défaut en soi
— c'est là que vit le métier — mais cela dit où se trouve le risque de
concentration, et que trois membres sont encore des déclarations d'intention.

**Ce qui est vérifié et tient.** Le noyau s'importe avec la seule `pydantic`,
sans charger `cfgrib` ni `xarray` : la promesse d'un socle léger est réelle,
et mesurée. Le graphe de dépendances internes est acyclique et en couches.
Aucun paquet n'importe un membre de `services/`, et un test l'exige.

**Ce qui ne tient pas encore**, et devient donc du travail :

- **`x10-storage` n'est dans le chemin de personne.** La seule écriture du
  dépôt passe par `netcdf_cf.write_netcdf` et `base.atomic_write`. L'abstraction
  de persistance est contournée, pas utilisée.
- **Trois dépendances directes ne sont pas déclarées**, et ne fonctionnent que
  par transitivité : `pydantic` et `numpy` dans `x10-connectors`, `pydantic`
  dans `x10-client`. À l'inverse, `x10-api` déclare `fastapi` et `uvicorn`
  qu'il n'importe pas.

## Phase 1 — Initialisation du dépôt — **faite**

- [x] Structure du monorepo et configuration racine
- [x] Python 3.12 en cible, 3.13 et 3.14 en canaris non bloquants
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
- [x] `x10-catalog` — registre, recherche à facettes, catalogue peuplé
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
   résolution. **Fait depuis le 19/10/2026** : `Registry`, `Query`, facettes.
2. **Un inventaire de variables dérivé des fichiers**, et non des descriptifs
   des producteurs, qui se sont déjà révélés incomplets ou faux.
3. **Une requête exprimée en besoin**, que le catalogue traduit en sélection
   de producteur. C'est elle qui rendra `x10-api` possible sans que le client
   final connaisse AROME.

Le compte rendu du client y prépare déjà : il répond aux questions d'un
consommateur sans exiger qu'il connaisse le découpage en granules.

## Prochaine action

Le registre est écrit et le catalogue peuplé depuis le 19/10/2026 : cette
action est close.

**La suivante n'est pas arrêtée, et c'est délibéré.** Trois des points
restants de la phase 3 — ce que `x10-storage` doit porter, où vivent les
modèles que l'API expose, le sort de Zarr — dépendent de la manière dont le
système sera exploité, et cette cible vit hors du dépôt. Les trancher par
défaut produirait une architecture à défaire ; voir « Préciser la cible
d'exploitation avant de trancher » dans [AGENTS.md](AGENTS.md).

**Ce qui avance sans cette réponse** : l'inventaire de l'IFS, qui manque au
catalogue faute de granule au corpus, et les modèles de domaine encore
absents — emprises géographiques, séries temporelles, qualité.

## Le travail en vol

**Relevé le 26/11/2026.** Une branche porte du travail commité et jamais
proposé : `feat/image-de-verification`, du 24/11 — 413 lignes, un
`Dockerfile` à base épinglée par empreinte, un manifeste de Job, un
vérificateur et son workflow de construction.

> **Pourquoi cette ligne existe.** Le 26/11, une analyse de l'état du dépôt a
> conclu qu'aucun `Dockerfile` n'existait. C'était vrai de `main` et faux du
> dépôt, et personne n'avait de raison de le savoir. **Un travail commité et
> non proposé est invisible à tout le monde, y compris à son auteur.**
>
> Cette ligne se périme par construction : elle est datée, et le relevé qui
> la tient à jour est une commande, pas un paragraphe — `git branch -r` et
> `gh pr list` disent l'état réel en deux secondes.

## Ce qui contraint une décision de conception

Déplacé depuis le guide d'agent le 26/11/2026 : c'est de la feuille de route,
et un guide dit ce qui est, pas ce qui viendra. Ne figurent ici que les
points qu'il faut **avoir en tête au moment de trancher**, pas au moment
d'ouvrir un chantier.

- **Codecov, à réexaminer une fois, à la publication de la 1.0.0.** La
  barrière de couverture est locale et sans service tiers ; les courbes de
  tendance et le commentaire de couverture différentielle prennent leur sens
  quand le projet a une histoire et des contributeurs. Raisonnement complet
  dans [tests-et-couverture](docs/tests-et-couverture.md).
- **Métriques de supervision.** Les journaux permettent à une chaîne ELK de
  dériver taux de succès, latence et volume, mais la détection d'incident
  dépend alors du délai d'indexation. Un point d'entrée de métriques, ou un
  contrôle de santé par source, se prévoit si un besoin de supervision temps
  réel apparaît.
- **Montée de majeure des actions GitHub** — proposée par Dependabot, **une
  demande par majeure** et non groupée : c'est un changement fonctionnel, à
  éprouver isolément. Sans jamais abandonner l'épinglage par empreinte, que
  Dependabot comprend et met à jour de concert avec le commentaire de
  version. Si un nom de job change au passage, suivre la règle d'ordre du
  skill `github-protection` : un contexte requis sans job correspondant
  bloque toute fusion définitivement.
- **Documentation publiée : une version anglaise `/en/`.** La documentation
  et les commentaires sont en français par décision ; une publication Read
  the Docs porterait donc `/fr/` et `/en/`. Conséquence à garder en tête
  **dès maintenant** : ce sont les **docstrings** qui alimenteraient une
  référence d'API automatique, donc le coût de traduction croît à chaque
  module ajouté. Même échéance que la publication PyPI.
- **Sous-paquet `formats/` au troisième format.** À sept modules la structure
  plate reste plus lisible, et un `formats/` appellerait un `sources/` par
  symétrie. Le point de bascule est l'arrivée d'un troisième format.
- **Publication PyPI** — par Trusted Publishing plutôt qu'un jeton. Le jour
  venu, la matrice trois systèmes est la garantie que le paquet s'installe
  ailleurs que sur la machine du mainteneur.
