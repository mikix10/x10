"""X10-DIV-0004 — un paramètre océanique qu'aucune table ne résout.

**Le constat.** La direction moyenne des vagues de MFWAM sort d'ecCodes
avec `shortName = unknown` et `units = unknown` ; GDAL la nomme
`var200 of table 2 of center 85`, commentaire `undefined [-]`. C'est un
paramètre **local** dans une table locale du centre 85 que notre ecCodes ne
possède pas.

**Pourquoi cette entrée-là compte plus que son voisinage.** C'est une
grandeur **circulaire** : la moyenne arithmétique de 350° et 10° vaut 180°,
soit l'exact opposé de la réponse juste. Un champ sans nom, sans unité et
sans avertissement est précisément celui qu'un consommateur moyennera.

Dans le même fichier, la hauteur significative se résout normalement —
`swh`, « Significant height of combined wind waves and swell », en mètres.
Le granule mêle donc le connu et l'inconnaissable sans que rien ne les
distingue.

C'est le problème que `grib2.check_local_tables` traite déjà en édition 2,
transposé à l'édition 1 où notre contrôle ne va pas.
"""

from __future__ import annotations

from datetime import date

from x10_client.probes import Handling, Mode, Nature, Probe, Side, Status

PROBE = Probe(
    identifier="X10-DIV-0004",
    title="Ocean wave direction resolves to no name and no unit (local table, centre 85)",
    nature=Nature.DIVERGENCE,
    status=Status.CONFIRMED,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 20),
    producer="Météo-France",
    artefact="API ciblée, MFWAM, GRIB1 paramètre 200 table 2 centre 85",
    workaround="Aucune. Le champ serait exposé sans nom standard, et l'écart se verrait.",
    handling=Handling.ENDURED,
    mode=Mode.MANUAL,
    replay_note="Extraire un granule MFWAM en `application/wmo-grib`, puis "
    "`eccodes.codes_get(gid, 'shortName')` — attendu `unknown`. "
    "Demande ecCodes, hors du périmètre de la sonde.",
)
