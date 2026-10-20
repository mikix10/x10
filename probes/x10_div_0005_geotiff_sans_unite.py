"""X10-DIV-0005 — le GeoTIFF convertit l'unité et ne la déclare pas.

**Le constat**, sur la même couverture demandée dans les deux formats que
le portail déclare :

| | minimum | maximum | unité déclarée |
|---|---|---|---|
| GRIB | 277,9517 | 295,0835 | `K` |
| GeoTIFF | 4,8017 | 21,9335 | **aucune** |

Exactement 273,15 d'écart. La seule trace est une étiquette GDAL de bande,
`GRIB_UNIT: '[C]'`, qui n'est pas un emplacement normalisé.

**Ce qui rend l'écart difficile à traiter** : la conversion est
**sélective**. Précipitation, hauteur de vague et surcote sortent
identiques dans les deux formats. On ne peut donc pas la neutraliser par
une règle de format — il faut lire l'unité du fichier reçu, et refuser
quand elle manque.

Le GeoTIFF perd par ailleurs tout le reste : ni nom standard, ni
`cell_methods`, ni bornes temporelles. Il conserve en revanche la
géoréférence et masque correctement les valeurs manquantes. C'est une
sortie de **visualisation**, pas un format d'échange.
"""

from __future__ import annotations

from datetime import date

from x10_client.probes import Handling, Mode, Nature, Probe, Side, Status

PROBE = Probe(
    identifier="X10-DIV-0005",
    title="GeoTIFF output converts temperature to Celsius and declares no unit",
    nature=Nature.DIVERGENCE,
    status=Status.CONFIRMED,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 20),
    producer="Météo-France",
    artefact="API ciblée, GetCoverage format image/tiff",
    workaround="Ne jamais déduire l'unité du format ; lire celle du fichier reçu. "
    "Le GeoTIFF n'est pas retenu comme source de normalisation.",
    handling=Handling.DOCUMENTED,
    mode=Mode.MANUAL,
    replay_note="Demander la même couverture en `application/wmo-grib` puis "
    "`image/tiff`, et comparer les extrema. Une sonde automatique "
    "exigerait un lecteur raster, qu'une sonde ne justifie pas seule.",
)
