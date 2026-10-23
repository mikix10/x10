"""X10-DIV-0014 — le coût annoncé ne prédit pas le volume livré.

**Le constat.** `estimate_costs` rend un coût avant soumission, ce qui est
une courtoisie réelle. Mais il ne mesure pas le volume :

| Jeu | coût GRIB | coût NetCDF | octets GRIB | octets NetCDF |
|---|---|---|---|---|
| ERA5 surface | 4,0 | 24,0 | 20 440 | 86 697 |
| CARRA | **1,0** | **1,0** | 2 713 849 | **23 702 082** |

Sur ERA5 le coût suit le format d'un facteur six ; sur CARRA il annonce la
même valeur des deux côtés alors que le NetCDF pèse **8,7 fois** le GRIB.

**La lecture juste** : c'est un plafond de service, pas une prédiction de
taille. S'y fier pour dimensionner un stockage ou un transfert serait
faux — et l'erreur est silencieuse, puisque le nombre a l'air d'une
estimation.
"""

from __future__ import annotations

from datetime import date

from x10_client.probes import Handling, Mode, Nature, Probe, Side, Status

PROBE = Probe(
    identifier="X10-DIV-0014",
    title="The announced request cost does not predict the delivered volume",
    nature=Nature.DIVERGENCE,
    status=Status.CONFIRMED,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 19),
    producer="ECMWF — Copernicus Climate Data Store",
    artefact="API de récupération, estimate_costs",
    workaround="Le coût est lu comme un plafond de service ; la volumétrie se "
    "mesure sur le fichier reçu.",
    handling=Handling.DOCUMENTED,
    mode=Mode.MANUAL,
    replay_note="Appeler `estimate_costs` puis récupérer, sur ERA5 et sur CARRA, "
    "dans les deux formats, et comparer coût et octets.",
)
