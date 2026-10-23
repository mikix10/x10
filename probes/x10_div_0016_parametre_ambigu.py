"""X10-DIV-0016 — un `paramId` n'identifie pas une grandeur de façon unique.

`paramId` est le meilleur axe dont nous disposions : il vaut la même chose
dans les deux éditions du format, là où le triplet n'existe qu'en édition 2.
Il ne faut pas pour autant le croire univoque.

**Mesuré le 20/10/2026 sur la base d'ECMWF**, la hauteur significative des
vagues porte **trois** identifiants :

| `paramId` | encodages déclarés |
|---|---|
| 3 100 | `grib1` seul |
| 140 229 | `grib1` + `grib2` |
| 500 071 | `grib1` + `grib2` |

Même nom court, même libellé. Et `tp` fait de même, sous 228 et 228228.

**Le piège est que MFWAM émet le 3 100**, celui qui n'a aucun encodage
d'édition 2 — et qu'ecCodes ne connaît pas du tout : lui demander ce
`paramId` lève une `ConceptNoMatchError` dont le message renvoie à la base.
Le pont entre éditions échoue donc **précisément sur le cas qui a motivé la
recherche**, pendant qu'il fonctionne sur les deux autres.

**La conséquence de conception.** Indexer notre correspondance sur
`paramId` ne suffira pas : il faudra ou bien recenser les identifiants
équivalents d'une même grandeur, ou bien accepter de ne pas nommer ce que
le producteur encode sous un identifiant orphelin. Les deux se défendent ;
ce qui ne se défend pas est de croire le problème réglé par le seul
changement d'axe.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from _access import fetch
from x10_client.probes import Assertion, Handling, Mode, Nature, Outcome, Probe, Side, Status

BASE = "https://codes.ecmwf.int/parameter-database/api/v1"

#: L'identifiant que MFWAM émet réellement pour la hauteur significative.
ORPHELIN = 3100
#: Celui qui, pour la même grandeur, porte les deux encodages.
PONTE = 140229

PROBE = Probe(
    identifier="X10-DIV-0016",
    title="paramId does not uniquely identify a quantity, and the orphan is the one emitted",
    nature=Nature.DIVERGENCE,
    status=Status.CONFIRMED,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 20),
    producer="ECMWF et Météo-France",
    artefact="paramId, base de paramètres et définitions ecCodes",
    workaround=(
        "Aucun à ce jour. L'indexation par `paramId` devra recenser les "
        "identifiants équivalents, ou assumer de ne pas nommer un orphelin."
    ),
    handling=Handling.ENDURED,
    mode=Mode.AUTOMATIC,
)


def _encodages(param_id: int, encodage: str) -> list[object]:
    """Les encodages déclarés, ou une liste vide quand il n'y en a pas.

    `fetch` rend le code plutôt que de lever : un `404` est ici une
    **donnée** — il dit que l'identifiant n'a pas cet encodage —, et c'est
    précisément le constat que la sonde cherche.
    """
    code, corps = fetch(
        f"{BASE}/param/{param_id}/{encodage}/",
        entetes={"Accept": "application/json", "User-Agent": "x10-probe"},
    )
    if code == 404:
        return []
    if code != 200:
        raise RuntimeError(f"The parameter database answered HTTP {code}.")
    return list(json.loads(corps))


def check() -> Assertion:
    """Deux requêtes minuscules : l'orphelin a-t-il toujours son trou ?"""
    orphelin = _encodages(ORPHELIN, "grib2")
    ponte = _encodages(PONTE, "grib2")

    if orphelin:
        resultat = Outcome.PASSED
        detail = f"paramId {ORPHELIN} now declares a GRIB2 encoding; the gap is closed."
    elif not ponte:
        resultat = Outcome.CANT_TELL
        detail = f"Neither {ORPHELIN} nor {PONTE} declares a GRIB2 encoding; check the service."
    else:
        resultat = Outcome.FAILED
        detail = (
            f"paramId {ORPHELIN}, the one MFWAM emits, still has no GRIB2 encoding, "
            f"while {PONTE} names the same quantity and has {len(ponte)}."
        )
    return Assertion(
        identifier=PROBE.identifier,
        outcome=resultat,
        detail=detail,
        observed_at=datetime.now(UTC),
    )
