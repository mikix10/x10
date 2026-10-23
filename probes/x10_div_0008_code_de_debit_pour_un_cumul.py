"""X10-DIV-0008 — le code d'un débit employé pour une accumulation.

**Le constat, et il vaut pour deux producteurs indépendants.** Le triplet
`(0, 1, 52)` est nommé par l'OMM **« Total precipitation rate »**, en
`kg m-2 s-1`. Deux producteurs l'emploient pour un **cumul** :

| Producteur | Produit | `stepType` | `units` |
|---|---|---|---|
| Météo-France | AROME 0,025° | `accum` | `kg m**-2` |
| SMHI | CERRA | `accum` | `kg m**-2` |

**Pourquoi ce n'est pas une singularité** : deux occurrences indépendantes,
sur deux chaînes de production sans rapport, font un usage établi plutôt
qu'une erreur isolée.

**Ce que cela nous fait écrire de faux.** Notre table est fidèle à la norme
et pose `precipitation_flux` — un flux par seconde, sur une variable dont
l'unité n'a pas de seconde. Le fichier produit se dirait conforme sans
l'être.

**L'invariant qui en découle** : le `standard_name` émis et l'unité émise
doivent être **dimensionnellement compatibles**. `cf-units` est déjà au
groupe de développement et sait réduire une unité ; le tableau CF publie
l'unité canonique de chaque nom. Rien à inventer.
"""

from __future__ import annotations

from datetime import date

from x10_client.probes import Handling, Mode, Nature, Probe, Side, Status

PROBE = Probe(
    identifier="X10-DIV-0008",
    title="Triplet (0,1,52), a precipitation rate, is used for an accumulation",
    nature=Nature.DIVERGENCE,
    status=Status.CONFIRMED,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 20),
    producer="Météo-France et SMHI",
    artefact="GRIB2, table 4.2-0-1 entrée 52",
    workaround="Aucune à ce jour. L'invariant de compatibilité dimensionnelle "
    "reste à outiller ; en attendant, le nom est posé tel que la "
    "norme le dit.",
    handling=Handling.ENDURED,
    mode=Mode.MANUAL,
    replay_note="Extraire un cumul de précipitation d'AROME ou de CERRA et lire "
    "`stepType` et `units` sur le message. Demande ecCodes.",
)
