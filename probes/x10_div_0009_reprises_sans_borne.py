"""X10-DIV-0009 — les clients officiels retentent pendant seize heures.

**Le constat.** Les deux clients officiels d'ECMWF exposent les mêmes
valeurs de reprise par défaut :

| Client | tentatives | intervalle |
|---|---|---|
| `ecmwf-opendata` | 500 | 120 s |
| `ecmwf-datastores-client` | 500 | 120 s |

Soit, au pire, plus de seize heures d'attente sans que rien ne le signale.
Observé en conditions réelles : un `502` a bien déclenché « Retrying in 120
seconds ».

**Ce n'est pas une non-conformité** — aucune norme ne fixe ces valeurs —,
mais c'est un piège d'exploitation. Un ordonnanceur qui attend une réponse
en minutes verra un travail occuper son emplacement une nuit entière.

Le dépôt avait déjà consigné le défaut pour `ecmwf-opendata` le 29/09/2026
et abaissé à 3 tentatives de 10 s. Le constat du 20/10/2026 est que le
second client le reproduit à l'identique : **la parade doit valoir pour
tout client ECMWF**, et non pour celui qu'on a rencontré en premier.
"""

from __future__ import annotations

from datetime import date

from x10_client.probes import Handling, Mode, Nature, Probe, Side, Status

PROBE = Probe(
    identifier="X10-DIV-0009",
    title="Official ECMWF clients default to 500 retries at 120 s, i.e. sixteen hours",
    nature=Nature.DIVERGENCE,
    status=Status.CONFIRMED,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 20),
    producer="ECMWF",
    artefact="ecmwf-opendata, ecmwf-datastores-client",
    workaround="Reprises abaissées à 3 tentatives de 10 s, et un test le garantit.",
    handling=Handling.WORKED_AROUND,
    mode=Mode.MANUAL,
    replay_note="Lire la signature de `Client.__init__` des deux paquets : "
    "`maximum_tries` et `retry_after`. Aucune requête réseau.",
)
