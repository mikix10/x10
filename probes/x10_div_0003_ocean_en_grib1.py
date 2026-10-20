"""X10-DIV-0003 — les modèles océaniques sont servis en GRIB édition 1.

**Le constat.** Sur la même API ciblée et par le même appel, l'atmosphère
sort en GRIB2 et l'océan en GRIB1 :

| Modèle | Édition |
|---|---|
| AROME 0,025°, ARPEGE 0,1° | 2 |
| MFWAM, HYCOM2D | **1** |

**Ce qui en fait l'entrée la plus structurante du registre**, et non une
curiosité de format : l'édition 1 n'a ni `discipline`, ni
`parameterCategory`, ni `parameterNumber`. Toute correspondance indexée par
le triplet GRIB2 — la nôtre l'est entièrement — est donc **inapplicable**
à ces champs. Et le recoupement est ce qui emporte la décision : au même
moment, ERA5 et CAMS sortent eux aussi en édition 1 du côté de Copernicus.
Deux producteurs indépendants, deux domaines différents.

L'édition se lit à l'**octet 8 de la section 0**, sans aucune bibliothèque :
c'est ce que fait cette sonde, qui n'a donc besoin ni d'ecCodes ni de rien
d'autre.

Côté X10, le manque correspondant porte son propre numéro — X10-DIV-0013 —
parce qu'il ne s'adresse pas au même destinataire.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

from _access import MF_GATEWAY, fetch, meteofrance_headers, redact, subsetting
from x10_client.credentials import Credentials
from x10_client.probes import Assertion, Handling, Mode, Nature, Outcome, Probe, Side, Status

SERVICE = "MF-NWP-HIGHRES-MFWAM-0025-FRANCE-WCS"
RACINE = f"{MF_GATEWAY}/public/wavesmodels/1.0/wcs/{SERVICE}"
GRANDEUR = "SIGNIFICANT_HEIGHT_OF_COMBINED_WIND_WAVES_AND_SWELL__WATER_SURFACE"

PROBE = Probe(
    identifier="X10-DIV-0003",
    title="Ocean models are served as GRIB edition 1 while the atmosphere is edition 2",
    nature=Nature.DIVERGENCE,
    status=Status.CONFIRMED,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 20),
    producer="Météo-France",
    artefact="API ciblée, WavesModels (MFWAM, WW3, HYCOM2D)",
    workaround=(
        "Aucun à ce jour : la chaîne de décodage lève sur ces granules. "
        "Voir X10-DIV-0013 pour le manque qui nous revient."
    ),
    handling=Handling.ENDURED,
    mode=Mode.AUTOMATIC,
)


def check() -> Assertion:
    """Deux requêtes, puis huit octets. Aucune bibliothèque de décodage."""
    credentials = Credentials.from_env()
    entetes = meteofrance_headers(credentials)

    code, corps = fetch(
        f"{RACINE}/GetCapabilities",
        entetes=entetes,
        params={"service": "WCS", "version": "2.0.1"},
    )
    if code != 200:
        raise RuntimeError(f"GetCapabilities answered HTTP {code}.")
    identifiants = sorted(
        m.decode()
        for m in re.findall(rb"<wcs:CoverageId>([^<]+)</wcs:CoverageId>", corps)
        if m.decode().startswith(GRANDEUR + "___")
    )
    if not identifiants:
        raise RuntimeError(f"No coverage for {GRANDEUR}.")
    couverture = identifiants[-1]

    code, octets = fetch(
        f"{RACINE}/GetCoverage",
        entetes=entetes,
        params={
            "service": "WCS",
            "version": "2.0.1",
            "coverageid": couverture,
            "format": "application/wmo-grib",
            "subset": subsetting(RACINE, entetes, couverture),
        },
    )
    if code != 200 or octets[:4] != b"GRIB":
        raise RuntimeError(f"GetCoverage answered HTTP {code}, {octets[:4]!r}.")

    edition = octets[7]
    if edition == 1:
        resultat = Outcome.FAILED
        detail = f"{SERVICE} still serves GRIB edition {edition}."
    elif edition == 2:
        resultat = Outcome.PASSED
        detail = "The ocean models now serve GRIB edition 2."
    else:
        resultat = Outcome.CANT_TELL
        detail = f"Unexpected GRIB edition {edition}."

    return Assertion(
        identifier=PROBE.identifier,
        outcome=resultat,
        detail=redact(credentials, detail),
        observed_at=datetime.now(UTC),
    )
