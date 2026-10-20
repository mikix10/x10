"""X10-DIV-0013 — X10 ne lit pas le GRIB édition 1.

**Le manque est le nôtre**, et c'est pourquoi il porte son propre numéro :
transmis à un producteur, il serait du bruit.

`open_granule` lève `KeyValueNotFoundError` sur tout granule en édition 1,
parce que `READ_KEYS` demande `discipline`, `parameterCategory`,
`parameterNumber` et `productDefinitionTemplateNumber`, qui n'existent pas
dans cette édition. Et `CF_STANDARD_NAMES` étant **entièrement** indexée par
le triplet GRIB2, elle ne pourrait de toute façon nommer aucun de ces
champs.

**L'ampleur, mesurée sur deux producteurs** : ERA5 et CAMS chez Copernicus,
MFWAM, WW3 et HYCOM2D chez Météo-France. L'océan tout entier, et la
réanalyse la plus utilisée au monde.

Trois issues, et la décision n'est pas prise :

1. un second axe d'identification, `(table2Version, indicatorOfParameter,
   centre)` ;
2. un refus **explicite et nommé**, qui dise ce qu'il refuse ;
3. une conversion en amont.

Le comportement actuel — une exception de bibliothèque sans message utile —
est le pire des trois.
"""

from __future__ import annotations

from datetime import date

from x10_client.probes import Handling, Mode, Nature, Probe, Side, Status

PROBE = Probe(
    identifier="X10-DIV-0013",
    title="X10 cannot read GRIB edition 1, which carries ERA5, CAMS and the whole ocean suite",
    nature=Nature.DIVERGENCE,
    status=Status.CONFIRMED,
    side=Side.X10,
    observed_on=date(2026, 10, 20),
    producer="X10",
    artefact="x10-connectors, grib2.READ_KEYS et CF_STANDARD_NAMES",
    workaround="Aucune. Décision de conception à prendre.",
    handling=Handling.ENDURED,
    mode=Mode.UNTESTED,
    replay_note="Appeler `grib2.open_granule` sur un granule d'édition 1 ; attendu "
    "`KeyValueNotFoundError`. Deviendra un test une fois la "
    "décision prise.",
)
