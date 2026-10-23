"""X10-DIV-0015 — la base de paramètres d'ECMWF a une colonne CF, et elle est vide.

**La bonne nouvelle d'abord.** `codes.ecmwf.int/parameter-database/api/v1/`
est **lisible par machine et libre d'accès** : 8 230 paramètres, trois
encodages déclarés — `grib1`, `grib2`, et `netcdf` dont l'unique clé est
`cfName`. C'est la table à trois colonnes que l'on cherchait, et elle existe
bel et bien.

**La mauvaise.** Mesuré le 20/10/2026 :

| Combinaison déclarée | Paramètres | |
|---|---|---|
| `grib2` seul | 3 984 | 48,4 % |
| `grib1` + `grib2` | 3 603 | 43,8 % |
| `grib1` seul | 475 | 5,8 % |
| **portant un `cfName`** | **168** | **2,0 %** |

**Deux pour cent.** C'est moins que toutes les tentatives que
[standards-et-outillage.md] recense, dont le plafond observé était de 6 %.
La température à 2 m elle-même, paramètre 167, n'en a aucun — on ne peut
guère trouver plus courant.

**Ce qui est utile, et ce n'est pas la colonne CF.** Le **pont entre
éditions** couvre 45,2 % des paramètres : un `paramId` y porte à la fois son
encodage d'édition 1 et celui d'édition 2. C'est cela qui sert, et cela se
compose avec notre propre table GRIB2 → CF.

**Et le chemin principal n'a même pas besoin du service.** ecCodes traduit
`paramId` en nom CF **hors ligne, depuis la roue**, dans les deux éditions —
ce qui lui manque est une **table locale**, non une édition : voir
X10-DIV-0017. Sa couverture reste mince des deux côtés, 96,0 % des `paramId`
encodables n'ayant de nom CF dans aucune édition. La base reste précieuse en
recoupement, et pour les cas où le `paramId` est ambigu.

L'entrée est classée `divergence` et non `non_conformity` : aucune clause
n'oblige ECMWF à remplir cette colonne. Elle est au registre parce qu'un
intégrateur qui la découvre pourrait la croire exploitable.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime

from _access import fetch
from x10_client.probes import Assertion, Handling, Mode, Nature, Outcome, Probe, Side, Status

BASE = "https://codes.ecmwf.int/parameter-database/api/v1"

#: Au-delà de ce taux, la colonne cesserait d'être anecdotique et l'entrée
#: demanderait d'être relue. Le plafond observé ailleurs est de 6 %.
SEUIL = 10.0

PROBE = Probe(
    identifier="X10-DIV-0015",
    title="The ECMWF parameter database declares a CF name for 2 % of its parameters",
    nature=Nature.DIVERGENCE,
    status=Status.CONFIRMED,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 20),
    producer="ECMWF — base de paramètres",
    artefact="codes.ecmwf.int/parameter-database, encodage netcdf",
    workaround=(
        "La colonne CF n'est pas employée. Le pont entre éditions l'est, et "
        "le nom vient d'ecCodes puis de notre table."
    ),
    handling=Handling.DOCUMENTED,
    mode=Mode.AUTOMATIC,
)


def check() -> Assertion:
    """Une requête, et le taux se recalcule au lieu d'être recopié."""
    code, corps = fetch(
        f"{BASE}/param/",
        entetes={"Accept": "application/json", "User-Agent": "x10-probe"},
    )
    if code != 200:
        raise RuntimeError(f"The parameter database answered HTTP {code}.")
    parametres = json.loads(corps)

    compte: Counter[str] = Counter()
    for p in parametres:
        for encodage in p.get("encoding_ids") or []:
            compte[encodage] += 1
    total = len(parametres)
    taux = compte["netcdf"] / total * 100 if total else 0.0
    pont = sum(1 for p in parametres if {"grib1", "grib2"} <= set(p.get("encoding_ids") or []))

    detail = (
        f"{total} parameters; {compte['netcdf']} carry a cfName "
        f"({taux:.1f} %); {pont} bridge GRIB1 and GRIB2 ({pont / total * 100:.1f} %)."
    )
    resultat = Outcome.FAILED if taux < SEUIL else Outcome.PASSED
    return Assertion(
        identifier=PROBE.identifier,
        outcome=resultat,
        detail=detail,
        observed_at=datetime.now(UTC),
    )
