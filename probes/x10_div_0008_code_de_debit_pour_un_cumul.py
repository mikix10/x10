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

**Outillé le 22/10/2026, et l'ampleur était sous-estimée.** Le contrôle a
trouvé **treize** couples incompatibles commités, dont onze dans le catalogue
livré et non dans les contrats de référence — là où personne ne regardait.

**Ce que l'invariant ne voit pas, et il faut le dire.** La compatibilité
dimensionnelle ignore le **signe** et la **convention de référence**. CF ne
publie l'intégrale des flux de chaleur que sous la forme *downward* quand le
GRIB compte *upward* : y rattacher nos noms passerait au vert tout en
inversant le sens des valeurs. Ces champs restent donc **sans nom**, et c'est
le bon résultat. Un test vert dit « nos noms et nos unités sont
dimensionnellement compatibles », pas « nos noms sont justes ».
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
    workaround="Outillé le 22/10/2026. `grib2.denotes_a_rate` reconnaît un nom "
    "de débit par ses jetons, et `CF_ACCUMULATED` lui substitue le "
    "nom de l'intégrale sur un champ cumulé — ici "
    "`precipitation_amount`. Faute d'intégrale connue, le nom est "
    "retiré plutôt que posé faux. "
    "`workspace-tests/test_coherence_noms_cf.py` soumet désormais "
    "chaque couple commis à UDUNITS.",
    handling=Handling.WORKED_AROUND,
    mode=Mode.MANUAL,
    replay_note="Extraire un cumul de précipitation d'AROME ou de CERRA et lire "
    "`stepType` et `units` sur le message. Demande ecCodes.",
)
