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
rapport = session.run(
    MeteoFrancePntRequest(model="arome", grid="0025", packages=("SP1",), time_ranges=("00H06H",))
)
print(rapport.resume())
```

**Et à éprouver la chaîne de bout en bout**, de notre côté. Les tests des
paquets exercent chaque étape ; rien n'exerçait leur enchaînement.

```bash
python -m x10_client run --paquet SP1 --tranche 00H06H
python -m x10_client constater
```

## Configuration

Lue de l'environnement, jamais codée en dur.

| Variable | Rôle | Défaut |
|---|---|---|
| `X10_DESTINATION` | où déposer les artefacts et les sorties | obligatoire |
| `X10_MAX_BYTES` | plafond de volume par acquisition | celui du connecteur |
| `X10_ETAT` | où accumuler les comptes rendus | `<destination>/.x10` |

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
