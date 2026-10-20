# Écarts observés — ce que X10 doit redresser

Note technique à l'usage de qui intègre X10, contribue au dépôt, ou maintient
l'une des sources que nous exploitons.

> **État au 20/10/2026** — 14 entrées, dont 11 confirmées et 3 sous
> instruction. 3 sont rejouables automatiquement. Registre :
> [divergences.tsv](divergences.tsv). Catalogue : [`probes/`](../probes).
> Mécanisme : `x10_client.probes`.

## Objet

Ce registre énumère, datées et reproductibles, les situations où une source
de données ou son outillage s'écarte de ce qu'une norme dit, de ce qu'elle
déclare elle-même, ou simplement de ce qu'elle devrait faire.

**C'est d'abord un document d'exploitation**, et seulement ensuite une base
de signalement. Même si aucune entrée n'est jamais corrigée en amont, la
liste garde sa valeur : elle dit à quoi se heurte une acquisition, et ce que
X10 fait en attendant.

**C'est aussi la justification de la couche de normalisation.** Un lecteur
qui se demande pourquoi X10 ne se contente pas de relayer des fichiers
trouvera ici la réponse en quatorze cas concrets : entre ce qu'un producteur
sert et ce qu'un consommateur peut exploiter sans se tromper, il y a un
travail, et il est mesurable.

**« Redresser » est le mot juste**, et il a été choisi contre deux autres.
« Absorber » ne dirait que l'entrée ; « corriger » accuserait la source, ce
qui est faux d'une divergence qui ne viole rien. Redresser dit ce que fait la
chaîne : l'entrée est de travers, la sortie est droite, sans préjuger de qui
a tort.

**Et le redressement n'est pas l'affaire de la seule normalisation** — c'est
pourquoi le titre dit « ce que X10 doit redresser » et non « ce que la
normalisation doit redresser », le dépôt employant ce mot au sens strict de
la fonction `normalise()`. Réparties sur les cinq temps de la chaîne —
**acquérir, vérifier, normaliser, décrire, exposer** —, les quatorze entrées
se logent ainsi :

| Étape | Entrées |
|---|---|
| acquérir | 4, plus une partagée |
| vérifier | 1 |
| normaliser | 6, plus une partagée |
| décrire | 2 |
| **exposer** | **0** |

Le zéro est le chiffre qui compte : **`exposer` est la seule étape où plus
rien ne doit être de travers.** Tout ce qui précède redresse ; ce qui sort
n'a plus à l'être. Cette répartition est un jugement sur ce qu'absorbe
chaque étape, non une mesure — elle se lit entrée par entrée dans la colonne
`workaround`.

## Nous pouvons nous tromper, et nous demandons qu'on nous le dise

Chaque entrée est un constat daté, pas un jugement. Plusieurs ont déjà été
nuancées ou retirées après vérification : une entrée peut reposer sur une
mauvaise lecture de notre part, sur un incident passager, ou sur une
subtilité que nous ignorons.

Si vous maintenez l'une des sources nommées ici et qu'une entrée vous paraît
inexacte, **ouvrez une issue sur ce dépôt** : elle sera corrigée ou retirée,
avec son motif, et son identifiant restera pour que la correction soit
traçable. Nous nous excusons par avance des erreurs que ce registre
contiendra, et nous préférons qu'elles soient visibles plutôt que diffuses.

## Les trois natures, qu'il ne faut pas confondre

On ne s'adresse pas de la même façon à un producteur selon le cas, et les
mélanger abîmerait un signalement.

| `nature` | Ce que cela veut dire |
|---|---|
| `non_conformity` | **Une clause écrite est violée**, et la colonne `clause` la cite — standard, version, section. Sans référence opposable, l'entrée n'a pas le droit d'exister : le modèle la refuse. |
| `divergence` | Surprenant, mais rien ne l'interdit. Le plus souvent un usage établi qui contredit l'esprit d'une norme sans en violer la lettre. |
| `data_quality` | Ni l'un ni l'autre : une coquille, un doublon, une empreinte fausse. Le plus facile à faire corriger. |

## Les autres colonnes

| Colonne | Vocabulaire | Pourquoi elle existe |
|---|---|---|
| `status` | `confirmed`, `under_investigation`, `withdrawn` | Le dépôt s'est trompé trois fois en une journée sur ce corpus. Une entrée ne monte en grade que sur preuve, et un retrait garde son motif. |
| `side` | `source`, `x10` | Certains manques sont les nôtres. Transmis à un producteur, ils seraient du bruit : la colonne permet de filtrer avant d'envoyer. |
| `handling` | `worked_around`, `documented`, `endured`, `not_applicable` | Une date seule ne dirait pas, dans un an, si l'écart a été neutralisé par du code, seulement écrit, ou subi faute de parade. |
| `handled_in` | une version | Depuis quelle version la parade existe. |
| `mode` | `automatic`, `manual`, `untested` | Vocabulaire d'EARL. `untested` n'est pas un aveu gênant : un écart qu'on sait non outillé vaut mieux qu'un écart qu'on ignore. |
| `replay` | `open`, `restricted` | **Libre par défaut** : les identifiants que nos sources demandent s'obtiennent en s'inscrivant. Aucune entrée n'est restreinte à ce jour. |
| `fixed_on` | une date | Remplie **sur un rejeu**, jamais à la main. |

## Rejouer

Une sonde n'est pas un test `pytest`, et le mot est choisi pour éviter la
confusion : un test dit si *notre* code est juste, une sonde dit si un
constat daté sur un **tiers** tient toujours. Elle atteint un service réel,
demande des identifiants, et son résultat n'a aucune raison d'être vert.

```python
from pathlib import Path
from x10_client.probes import charger, executer

inscrites = charger(Path("probes"))
rapport = executer(inscrites, seulement=["X10-DIV-0001"])  # ou sans filtre
print(rapport.still_failing, rapport.newly_fixed)
```

Les identifiants se posent en variables d'environnement — voir le `README`
de [x10-client](../services/x10-client/README.md). Sans eux, les sondes
concernées rendent `cantTell`, jamais un succès.

**Le verdict se lit à l'envers de l'habitude.** Le sujet de l'assertion est
le producteur, et le critère est la clause :

| `outcome` | Sens |
|---|---|
| `failed` | L'écart est toujours là. C'est le cas nominal. |
| `passed` | **Bonne nouvelle** : la source a été corrigée, et le registre doit suivre. |
| `cantTell` | La sonde n'a pas conclu. Ce n'est pas un succès. |
| `untested` | Aucune sonde n'existe pour cette entrée. |

**Resonder par parties, pas tout d'un coup.** Le paramètre `seulement` existe
pour cela : une sonde unitaire coûte deux à quatre requêtes, et rien
n'oblige à solliciter toutes les sources le même jour. La cadence raisonnable
reste à établir — elle le sera quand nous aurons mesuré ce que coûte un
cycle complet.

## Ce que le registre ne garantit pas

**Sa fraîcheur.** Les sondes exigent des identifiants, donc l'intégration
continue ne les lance pas et personne ne les rejoue à notre place. Les dates
disent quand nous avons regardé, pas que l'état décrit vaut aujourd'hui.
Tenir la table nous revient ; la rejouer est ouvert à quiconque.

**L'exhaustivité.** Quatorze entrées sortent de deux journées de relevé sur
deux producteurs. Il y en a d'autres, et des pans entiers n'ont pas été
examinés — observations in-situ, projections climatiques, produits
satellitaires.

## Comment une entrée est faite

Un fichier par entrée dans [`probes/`](../probes), nommé d'après son
identifiant. Il expose un `SONDE` — les métadonnées, qui alimentent le
registre — et, s'il y en a une, une fonction `verifier()` qui rejoue le
constat. **La docstring du module porte le raisonnement**, mesures à
l'appui : c'est là qu'est le capital, et aucun tableau ne le remplace.

`docs/divergences.tsv` est **engendré** depuis ces modules et vérifié par
`workspace-tests/test_divergences.py`. Il ne se modifie pas à la main : une
colonne qu'un humain doit penser à mettre à jour ne l'est jamais, et c'est
exactement ainsi que sont mortes les tentatives de correspondance que
[standards-et-outillage.md](standards-et-outillage.md) recense.

```bash
X10_DIVERGENCES_UPDATE=1 uv run pytest workspace-tests/test_divergences.py
```

**Les identifiants sont stables à jamais.** `X10-DIV-0001` désigne la même
chose dans dix ans : la numérotation est monotone et jamais réutilisée, et
une entrée retirée garde son numéro en statut `withdrawn`, avec son motif.
C'est ce qui permet à un message de commit de citer un écart sans le
réécrire.

## Où sont les mesures

Les relevés qui ont produit ces entrées — documents de capacités, granules,
rapports de confrontation — pèsent une centaine de mégaoctets et **ne sont
pas versionnés**, conformément à la règle du dépôt : les tests ne
téléchargent rien et ne stockent rien. Ils vivent hors dépôt, datés et
empreints, et les sondes se suffisent à elles-mêmes pour rejouer.

## Références

- [standards-et-outillage.md](standards-et-outillage.md) — le modèle dont
  `Divergence` et `Verdict` viennent, et pourquoi une correspondance est un
  processus plutôt qu'un livrable.
- [triplet-et-tables-grib.md](triplet-et-tables-grib.md) — pourquoi le
  triplet GRIB2 n'identifie pas un paramètre.
- [vocabulaire.md](vocabulaire.md) — la correspondance avec DCAT, PROV-O,
  INSPIRE, SSSOM et EARL.
