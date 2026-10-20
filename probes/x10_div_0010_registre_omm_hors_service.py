"""X10-DIV-0010 — le registre *linked data* de l'OMM ne répond plus.

**Le constat du 20/10/2026** : `https://codes.wmo.int/grib2/codeflag/4.2`
rend `404` à toute négociation de contenu — `text/turtle`,
`application/ld+json`, `application/rdf+xml` —, et `?_format=json` rend un
corps **vide** sous un code `200`.

**À confronter à un relevé antérieur**, du 19/10/2026, qui décrivait ce même
registre comme répondant mais figé : `owl:versionInfo 6`, `dct:modified`
2014-09-03, 590 entrées en table 4.2, contre 1 582 dans la source machine
vivante `wmo-im/GRIB2`.

Les deux relevés ne se contredisent pas nécessairement — une indisponibilité
passagère expliquerait le second —, mais **je ne peux pas les réconcilier**,
et c'est pourquoi l'entrée est `under_investigation`.

Ce qu'elle garde d'utile en l'état : le point d'entrée officiel ne peut pas
être tenu pour une source fiable d'identifiants, et c'est `wmo-im/GRIB2`,
sous licence MIT, qui porte la table vivante.
"""

from __future__ import annotations

from datetime import date

from x10_client.probes import Handling, Mode, Nature, Probe, Side, Status

PROBE = Probe(
    identifier="X10-DIV-0010",
    title="The WMO linked-data register answers 404 to content negotiation",
    nature=Nature.DIVERGENCE,
    status=Status.UNDER_INVESTIGATION,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 20),
    producer="Organisation météorologique mondiale",
    artefact="codes.wmo.int, table 4.2",
    workaround="Les tables lisibles par machine sont prises dans `wmo-im/GRIB2`.",
    handling=Handling.WORKED_AROUND,
    mode=Mode.UNTESTED,
    replay_note="Demander `https://codes.wmo.int/grib2/codeflag/4.2` avec plusieurs "
    "en-têtes `Accept`, à plusieurs jours d'intervalle, avant de "
    "conclure à autre chose qu'une indisponibilité.",
)
