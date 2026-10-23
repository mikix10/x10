"""X10-DIV-0007 — un identifiant en double dans la pagination du catalogue.

**Le constat, et sa limite.** Le 19/10/2026, le parcours paginé de
`get_collections()` d'`ecmwf-datastores-client` a rendu **145 identifiants
dont 144 uniques**, `insitu-gridded-observations-europe` apparaissant deux
fois.

**Non reproduit.** Le 20/10/2026, le même catalogue parcouru directement par
`/api/catalogue/v1/collections` en suivant `rel=next` rend **145
identifiants, 145 uniques**. L'écart n'est donc pas établi comme une
propriété du service.

**Hypothèse, et elle n'est pas vérifiée** : une pagination par décalage sans
tri stable peut servir deux fois la même entrée si l'ordre change entre deux
pages. Cela expliquerait un doublon transitoire et son absence le lendemain.

L'entrée reste au registre parce qu'un doublon silencieux dans un
inventaire est exactement ce qu'un inventaire ne doit pas faire — mais en
`under_investigation`, et il faudrait plusieurs parcours répétés pour
trancher.
"""

from __future__ import annotations

from datetime import date

from x10_client.probes import Handling, Mode, Nature, Probe, Side, Status

PROBE = Probe(
    identifier="X10-DIV-0007",
    title="Paginated collection listing returned a duplicate identifier, not reproduced since",
    nature=Nature.DATA_QUALITY,
    status=Status.UNDER_INVESTIGATION,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 19),
    producer="ECMWF — Copernicus Climate Data Store",
    artefact="API catalogue, pagination",
    workaround="Déduplication à la lecture de l'inventaire.",
    handling=Handling.WORKED_AROUND,
    mode=Mode.UNTESTED,
    replay_note="Parcourir la pagination plusieurs fois de suite et compter les "
    "doublons. Une seule exécution ne tranche rien.",
)
