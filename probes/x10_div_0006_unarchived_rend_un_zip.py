"""X10-DIV-0006 — `download_format: unarchived` rend une archive ZIP.

**Le constat.** Une requête ERA5 portant quatre variables de surface, avec
`data_format: "netcdf"` et `download_format: "unarchived"`, rend un fichier
dont les quatre premiers octets sont `PK\x03\x04`. Il contient deux membres :

```
data_stream-oper_stepType-instant.nc    59 421 o
data_stream-oper_stepType-accum.nc      26 947 o
```

Le service **découpe sa sortie NetCDF par `stepType`** quand une requête
mêle instantané et cumul, là où le GRIB livre un seul fichier. Même requête,
même donnée : un fichier d'un côté, deux de l'autre.

**La leçon est plus large que le défaut** : détecter le format par les
**octets**, jamais par l'extension ni par le paramètre demandé. Quatre
octets suffisent — `PK\x03\x04`, `CDF\x01`, `\x89HDF`, `GRIB`.
"""

from __future__ import annotations

from datetime import date

from x10_client.probes import Handling, Mode, Nature, Probe, Side, Status

PROBE = Probe(
    identifier="X10-DIV-0006",
    title="download_format 'unarchived' still returns a ZIP when the result is multi-file",
    nature=Nature.DIVERGENCE,
    status=Status.CONFIRMED,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 19),
    producer="ECMWF — Copernicus Climate Data Store",
    artefact="API de récupération, paramètre download_format",
    workaround="Détection du format par les quatre premiers octets.",
    handling=Handling.DOCUMENTED,
    mode=Mode.MANUAL,
    replay_note="Soumettre une requête ERA5 mêlant un instantané et un cumul, "
    "`download_format: unarchived`, et lire les quatre premiers octets. "
    "Non automatisée : la récupération met une à deux minutes et "
    "sollicite une file d'attente.",
)
