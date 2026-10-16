# x10-client — assembler la chaîne, et dire ce qu'on a fait

**L'API sert, le client consomme.** C'est la phrase qui distingue ce membre
de [`x10-api`](../x10-api/README.md), et elle décide de ce qui a sa place
ici.

Ce paquet **appelle** le socle ; il n'en fait pas partie. Il n'implémente
aucune logique de domaine : il assemble une acquisition, un décodage, une
normalisation, une écriture et un contrat de sortie, puis rend un compte
rendu de ce qui s'est passé.

## À quoi il sert

**À exploiter X10 à la main**, depuis un carnet ou un script, avec son propre
espace de stockage et sa propre configuration.

> **Aucun extra « carnet » n'est déclaré, et c'est une mesure.** En ajouter
> un — JupyterLab et Matplotlib — coûtait **1 202 lignes à `uv.lock`**, que
> la CI vérifie à chaque demande de fusion et que Dependabot suivrait, pour
> des dépendances qu'aucun test n'exerce. Un carnet apporte son propre
> outillage ; le client n'a pas à le déclarer pour lui.

```python
from x10_client import Session
from x10_connectors import MeteoFrancePntRequest

session = Session.from_env()
report = session.run(
    MeteoFrancePntRequest(model="arome", grid="0025", packages=("SP1",), time_ranges=("00H06H",))
)
print(report.summary())
```

**Et à éprouver la chaîne de bout en bout**, de notre côté. Les tests des
paquets exercent chaque étape ; rien n'exerçait leur enchaînement.

```bash
python -m x10_client run --package SP1 --time-range 00H06H
python -m x10_client observe
```

### En deux temps, sans retélécharger

`run()` est la composition de trois étapes publiques. Un carnet qui a déjà
rapporté cent quarante mébioctets les garde et rejoue ce qu'il veut :

```python
acquisition = session.acquire(request)  # une seule fois
granules = session.normalise(acquisition)  # autant de fois qu'on veut
```

Et un granule déjà sur le disque se traite sans acquisition du tout :

```python
session.normalise_granule(Path("arome_SP1_00H06H.grib2"))
```

## Configuration

Lue de l'environnement, jamais codée en dur.

| Variable | Rôle | Défaut |
|---|---|---|
| `X10_DESTINATION` | où déposer les artefacts et les sorties | obligatoire |
| `X10_MAX_BYTES` | plafond de volume par acquisition | celui du connecteur |
| `X10_STATE` | où accumuler les comptes rendus | `<destination>/.x10` |

## Options de traitement

`NormaliseOptions` rend explicites cinq décisions que la chaîne prenait en
dur. Les défauts ne changent rien au comportement ; ils se lisent, désormais.

| Option | Défaut | Ce qu'elle décide |
|---|---|---|
| `errors` | `"raise"` | lever, ou rendre un compte rendu en `failed` |
| `dropped_fields` | `"tolerate"` | tolérer un recouvrement de noms courts en le **nommant**, ou s'arrêter |
| `write` | `True` | écrire les sorties, ou s'arrêter au décodage |
| `strict_units` | `True` | refuser une unité sans correspondance UDUNITS plutôt que deviner |
| `compress` | `4` | niveau `zlib` des sorties |

**`run()` force `errors="report"`**, parce que rendre compte est son métier :
un granule fautif n'emporte pas les autres, et l'exécution est tout de même
accumulée. Appelée directement, `normalise_granule` **lève** — c'est le
comportement d'une bibliothèque, et qui l'appelle veut la trace.

> Cinq champs, et la liste ne s'allongera pas sans raison. Le motif a un mode
> de ruine connu : l'objet d'options finit par absorber la notification, le
> cache, la reprise — des fonctions qu'on n'a pas. **Un champ n'entre ici que
> s'il correspond à une décision que la chaîne prend déjà.**

## Ce qu'un consommateur lit

`PipelineReport` est l'interface ; `GranuleReport` est le détail de
diagnostic. **Le granule est l'unité que le producteur publie** — un
consommateur a demandé « AROME SP1, 00H06H », pas deux granules rendant
chacun N hypercubes. Il répond donc à ses cinq questions au premier niveau,
sans ouvrir `granules` :

| Clé | Question |
|---|---|
| `verdict` | puis-je m'en servir |
| `outputs` | où est ma donnée |
| `dropped` | qu'est-ce qui manque |
| `license` | sous quelles conditions |
| `selection` | ce que j'avais demandé |
| `granule_count`, `complete_count`, `partial_count`, `failed_count` | dans quelle mesure |

Les quatre verdicts, **tous produits quelque part** :

| Valeur | Sens |
|---|---|
| `complete` | tout ce qui est entré est ressorti |
| `partial` | la donnée est là, amputée, et ce qui manque est nommé |
| `failed` | ce granule n'a pas pu être traité ; `error_type` dit pourquoi |
| `not_assessed` | on ne s'est pas prononcé — l'acquisition a échoué |

## Deux règles qui ne sont pas négociables

### Constater la disponibilité, ne pas la tester

Chaque acquisition réelle dit déjà si la source a répondu, en combien de
temps et pour quel volume. **La disponibilité se déduit de ce trafic**, elle
ne se mesure pas par des requêtes synthétiques.

Une sonde n'est légitime que là où le trafic réel ne passe pas, et alors sous
la forme la moins coûteuse — requête conditionnelle ou en-tête seul, jamais
un téléchargement complet pour vérifier qu'une source répond.

> Notre crédit auprès d'un producteur est un bien commun et fini. Une sonde
> qui télécharge pour vérifier qu'on peut télécharger le dépense pour rien.

Conséquence assumée : l'observation a des trous là où l'usage est rare. Mieux
vaut un trou connu qu'une mesure payée par le producteur.

**Deux taux, et leur écart est le signal.** `success_rate` dit la part des
exécutions où **la source a répondu** ; `usable_rate` celle où la donnée est
sortie **complète**. Les confondre masquerait exactement la situation où un
producteur sert parfaitement une donnée que nous ne savons pas traiter.

> Et `run()` n'est jamais sans trace. Avant le 16/10/2026, un échec de
> décodage faisait remonter l'exception **avant** l'accumulation : un
> téléchargement réussi ne laissait rien, et comme les connecteurs lèvent au
> lieu de rendre un échec, `success_rate` valait structurellement `1.0`.
> L'accumulation est désormais dans un `finally`, et un connecteur qui lève
> produit un compte rendu composé par le client.

### Le compte rendu n'est pas une interface

`PipelineReport` est un **prototype interne**, et il le restera tant qu'un
intégrateur n'aura pas dit ce dont il a besoin. Il n'est pas versionné, il
n'est pas documenté comme contrat, et il peut changer sans préavis.

Ce qui est en revanche arrêté : **il référence le contrat de sortie, il ne le
contient pas.** Le contrat décrit la forme d'une source et ne bouge que si le
producteur bouge ; le compte rendu décrit une exécution et diffère à chaque
fois. Les fusionner détruirait l'invariance qui fait du contrat un indicateur
de dérive. Leur comparaison produit le verdict.

## Ce que ce paquet ne fera jamais

- **Porter de la logique de domaine.** Décoder, corriger ou interpréter
  appartient aux paquets. Un client qui s'en charge devient un paquet
  fantôme, et le socle se vide sans que personne le décide.
- **Être une dépendance.** `services/` consomme, il n'est jamais consommé.
  Aucun fichier de `packages/` ne doit l'importer.
- **Reprendre les tests des paquets.** Ceux-ci doivent rester validables
  seuls, par qui les installe sans ce client. Les tests d'ici portent sur
  **l'assemblage et la configuration**, pas sur le décodage ni sur
  l'écriture.
- **Ordonnancer.** Pas de planification, pas de file, pas de service
  résident : une entrée exécutable qu'un ordonnanceur extérieur appelle.
