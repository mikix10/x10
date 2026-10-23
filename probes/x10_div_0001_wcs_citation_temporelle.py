"""X10-DIV-0001 — le WCS de Météo-France refuse la citation exigée par OGC.

**Le constat.** `GetCoverage` rejette un sous-ensemble temporel écrit
`time("2026-10-20T04:00:00Z")` — la forme que la norme impose — et n'accepte
que la forme nue `time(2026-10-20T04:00:00Z)`.

**Ce qui rend le piège coûteux**, et pourquoi l'entrée mérite un numéro : le
message d'erreur liste la valeur refusée **parmi les valeurs valides**. Un
intégrateur qui écrit son client depuis la spécification obtient donc un 404
accompagné d'un message qui lui montre sa propre valeur comme admise, et
rien ne le met sur la piste de la citation.

La sonde se place sur MFWAM France, dont le document de capacités fait
180 Kio quand celui d'AROME en fait 2,6 Mio : même démonstration, quinze
fois moins de sollicitation.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

from _access import MF_GATEWAY, fetch, instant_of, meteofrance_headers, redact, subsetting
from x10_client.credentials import Credentials
from x10_client.probes import Assertion, Handling, Mode, Nature, Outcome, Probe, Side, Status

SERVICE = "MF-NWP-HIGHRES-MFWAM-0025-FRANCE-WCS"
RACINE = f"{MF_GATEWAY}/public/wavesmodels/1.0/wcs/{SERVICE}"
GRANDEUR = "SIGNIFICANT_HEIGHT_OF_COMBINED_WIND_WAVES_AND_SWELL__WATER_SURFACE"

PROBE = Probe(
    identifier="X10-DIV-0001",
    title="WCS GetCoverage rejects the quoted temporal subset required by OGC WCS 2.0",
    nature=Nature.NON_CONFORMITY,
    status=Status.CONFIRMED,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 20),
    producer="Météo-France",
    artefact="API ciblée, service WCS (portail-api.meteofrance.fr)",
    clause=(
        "OGC 09-110r4, WCS 2.0.1 Core, KVP subset syntax: a temporal subset "
        "value is a quoted time position."
    ),
    workaround=(
        "La forme nue, avec la raison écrite à l'appel. Aucun connecteur "
        "n'atteint encore cette API : la parade ne vit que dans la sonde, "
        "d'où `documented` et non `worked_around`."
    ),
    handling=Handling.DOCUMENTED,
    mode=Mode.AUTOMATIC,
)


def _derniere_couverture(entetes: dict[str, str]) -> str:
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
    return identifiants[-1]


def check() -> Assertion:
    """Trois requêtes : le catalogue, puis la forme citée et la forme nue."""
    credentials = Credentials.from_env()
    entetes = meteofrance_headers(credentials)
    couverture = _derniere_couverture(entetes)
    subset = subsetting(RACINE, entetes, couverture)
    quand = instant_of(subset)
    sans_temps = [e for e in subset if not e.startswith("time(")]

    def demander(expression: str) -> int:
        code, _ = fetch(
            f"{RACINE}/GetCoverage",
            entetes=entetes,
            params={
                "service": "WCS",
                "version": "2.0.1",
                "coverageid": couverture,
                "format": "application/wmo-grib",
                "subset": [*sans_temps, expression],
            },
        )
        return code

    cite = demander(f'time("{quand}")')
    nu = demander(f"time({quand})")

    if cite == 200:
        resultat = Outcome.PASSED
        detail = "The quoted form is now accepted; the register must be updated."
    elif cite != 200 and nu == 200:
        resultat = Outcome.FAILED
        detail = f"Quoted form answered HTTP {cite}, bare form answered HTTP {nu}."
    else:
        resultat = Outcome.CANT_TELL
        detail = f"Neither form succeeded: quoted {cite}, bare {nu}."

    return Assertion(
        identifier=PROBE.identifier,
        outcome=resultat,
        detail=redact(credentials, detail),
        observed_at=datetime.now(UTC),
    )
