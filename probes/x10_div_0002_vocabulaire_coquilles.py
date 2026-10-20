"""X10-DIV-0002 — trois coquilles dans le vocabulaire source de Météo-France.

**Le constat**, relevé sur les 260 couples (grandeur, niveau) des 35 services
WCS :

| Forme | Occurrences |
|---|---|
| `GROUND_OR_WATER_SURFACE` | 95 |
| `GROUND_OR_WATER_SUFACE` | 1 — un `R` manquant |
| `LEVEL_OF_ADIABATIC_CONDENSATION` | 3 |
| `LEVEL_OF_ADIABATIC_CONDESATION` | 3 — un `N` manquant, **et les deux coexistent** |
| `LEVEL_OF_ADIABATIC_CONDESATION ` | 1 — avec un espace final |

**Pourquoi c'est plus qu'une curiosité.** Un intégrateur qui normalise sur
`GROUND_OR_WATER_SURFACE` perd silencieusement une couverture ; qui groupe
par niveau en obtient deux là où il y en a un. C'est la démonstration
concrète de ce que le dépôt affirme de la vue source : elle ne promet rien,
par construction, puisqu'elle suit le producteur.

C'est aussi l'entrée la plus facile à faire corriger — ni norme violée, ni
usage à défendre, seulement une faute de saisie.

La sonde interroge **deux** services, chacun porteur d'une des coquilles.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from _access import MF_GATEWAY, fetch, meteofrance_headers, redact
from x10_client.credentials import Credentials
from x10_client.probes import Assertion, Handling, Mode, Nature, Outcome, Probe, Side, Status

#: (contexte, service, forme fautive) — relevé le 20/10/2026.
COQUILLES = [
    ("/public/aromepi", "MF-NWP-HIGHRES-AROMEPI-0025-FRANCE-WCS", "GROUND_OR_WATER_SUFACE"),
    ("/public/arpege", "MF-NWP-GLOBAL-ARPEGE-01-ATOURX-WCS", "LEVEL_OF_ADIABATIC_CONDESATION"),
]

PROBE = Probe(
    identifier="X10-DIV-0002",
    title="Misspelt level names in the WCS coverage vocabulary",
    nature=Nature.DATA_QUALITY,
    status=Status.CONFIRMED,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 20),
    producer="Météo-France",
    artefact="API ciblée, identifiants de couverture WCS",
    workaround=(
        "Aucun. La vue source est exposée telle quelle, et c'est sa règle ; "
        "la vue normalisée n'en dépend pas."
    ),
    handling=Handling.ENDURED,
    mode=Mode.AUTOMATIC,
)


def check() -> Assertion:
    """Une requête par service, et on cherche la forme fautive telle quelle."""
    credentials = Credentials.from_env()
    entetes = meteofrance_headers(credentials)
    presentes, absentes, indecis = [], [], []
    for contexte, service, fautive in COQUILLES:
        code, corps = fetch(
            f"{MF_GATEWAY}{contexte}/1.0/wcs/{service}/GetCapabilities",
            entetes=entetes,
            params={"service": "WCS", "version": "2.0.1"},
        )
        if code != 200:
            indecis.append(f"{service}: HTTP {code}")
        elif fautive.encode() in corps:
            presentes.append(fautive)
        else:
            absentes.append(fautive)

    if indecis:
        resultat, detail = Outcome.CANT_TELL, "; ".join(indecis)
    elif presentes:
        resultat = Outcome.FAILED
        detail = f"Still misspelt: {', '.join(presentes)}."
    else:
        resultat = Outcome.PASSED
        detail = "All known misspellings are gone; the register must be updated."

    return Assertion(
        identifier=PROBE.identifier,
        outcome=resultat,
        detail=redact(credentials, detail),
        observed_at=datetime.now(UTC),
    )
