"""X10-DIV-0008 — retirée : le producteur suivait la norme, c'est nous qui nommions mal.

**Le constat de fait tient, son imputation était inversée.** Le triplet
`(0, 1, 52)` est nommé par l'OMM « Total precipitation rate », et deux
producteurs indépendants l'emploient pour un **cumul** :

| Producteur | Produit | `stepType` | `units` |
|---|---|---|---|
| Météo-France | AROME 0,025° | `accum` | `kg m**-2` |
| SMHI | CERRA | `accum` | `kg m**-2` |

**Ce que la mesure du 22/10/2026 a renversé.** Ils ne s'écartent de rien : ils
appliquent une recommandation écrite. La note 3 de la table 4.2-0-1 du *Manual
on Codes*, attachée à l'entrée 8 — *Total precipitation* —, dit verbatim :

> « Statistical process 1 (Accumulation) does not change units. It is
> recommended to use another parameter with "rate" in its name and
> accumulation in PDT. »

Et l'entrée 8 est **`Deprecated`** au registre de l'OMM, comme quatorze des
175 entrées de cette table. ecCodes ne la résout d'ailleurs plus : `(0, 1, 8)`
rend `paramId = 0` et `unknown` partout, sous les huit combinaisons de gabarit
et de traitement essayées, aux six versions de tables et sous trois centres —
seul `kwbc` porte une concordance locale. Le producteur emploie donc ce que la
norme recommande **et** ce que l'outillage sait lire.

**Le seul maillon fautif était le nôtre** : `grib2.CF_STANDARD_NAMES` indexait
`(0, 1, 52)` par le triplet seul et posait `precipitation_flux` sur le cumul.
Corrigé le 22/10/2026 — `denotes_a_rate` et `CF_ACCUMULATED` substituent
`precipitation_amount` dès que le champ est cumulé.

**Pourquoi un retrait plutôt qu'une bascule de côté.** Le registre recense ce
qui sépare ce qu'un producteur sert de ce qu'un consommateur peut exploiter.
Ici le producteur ne sépare rien : l'écart était entre notre table et la
norme, et il est clos. Le garder sous `side = x10` ferait du registre un
journal de nos propres défauts, ce que le contrat de sortie et la suite de
tests font déjà. **Une entrée fausse dans un registre présenté comme
contradictoire coûte plus cher qu'une entrée manquante.**

Ce qui subsiste du dossier est ailleurs, et mesuré : voir `X10-DIV-0018`, où
c'est ecCodes qui porte un nom CF incompatible avec l'unité qu'il déclare.
"""

from __future__ import annotations

from datetime import date

from x10_client.probes import Handling, Mode, Nature, Probe, Side, Status

PROBE = Probe(
    identifier="X10-DIV-0008",
    title="Withdrawn: (0,1,52) used for an accumulation follows a WMO recommendation",
    nature=Nature.DIVERGENCE,
    status=Status.WITHDRAWN,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 20),
    producer="Météo-France et SMHI",
    artefact="GRIB2, table 4.2-0-1 note 3",
    status_note="Retirée le 22/10/2026 : le producteur ne s'écarte de rien. La "
    "note 3 de la table 4.2-0-1 recommande d'employer un paramètre "
    "« rate » avec accumulation dans le gabarit, et l'entrée 8 est "
    "dépréciée. Le seul maillon fautif était notre table, corrigée "
    "le même jour.",
    workaround="Sans objet : l'écart n'était pas chez le producteur. Le défaut "
    "de nommage qu'il révélait est corrigé dans `grib2.CF_ACCUMULATED`.",
    handling=Handling.NOT_APPLICABLE,
    mode=Mode.MANUAL,
    replay_note="Relire la note 3 de la table 4.2-0-1 au registre de l'OMM, et "
    "le statut de l'entrée 8. Aucun granule nécessaire.",
)
