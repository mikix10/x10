"""Messages GRIB **édition 1** construits en mémoire, pour les tests hors ligne.

Le pendant de `fixtures_grib2` pour l'édition 1. Même principe, et pour la
même raison : **aucune donnée réelle n'est commise au dépôt**, et quelques
centaines d'octets suffisent à exercer l'identité, le nommage et la
détection de perte.

L'édition 1 n'identifie pas ses paramètres comme la seconde : elle emploie
`table2Version` et `indicatorOfParameter` là où l'édition 2 emploie un
triplet. C'est précisément ce que ces fixtures permettent d'exercer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import eccodes
import numpy as np

#: La grille la plus petite qui reste une grille. Les tests portent sur les
#: métadonnées, pas sur les valeurs.
#:
#: **Les pas sont écrits, et il le faut.** L'échantillon d'ecCodes porte les
#: siens ; ne poser que les coins laisse une géométrie contradictoire, et
#: `xarray` refuse alors d'assembler — « conflicting sizes for dimension
#: latitude ». Le message reste écrit, et l'échec survient trois étapes plus
#: loin, au décodage.
GRILLE = {
    "ni": 4,
    "nj": 3,
    "lat1": 50.0,
    "lon1": 0.0,
    "lat2": 48.0,
    "lon2": 3.0,
    "di": 1.0,
    "dj": 1.0,
}


@dataclass(frozen=True)
class Champ:
    """Ce qu'il faut pour écrire un message d'édition 1 identifiable."""

    #: Version de la table 2 — 128 et au-delà désignent une table locale du
    #: centre, ce qu'ECMWF emploie pour l'essentiel de son catalogue.
    table2_version: int = 128
    #: Numéro du paramètre dans cette table. Avec elle, il forme l'identité
    #: du champ en édition 1.
    indicator: int = 167
    #: Niveau, et son type au sens de la table 3 du format.
    level_type: int = 1
    level: int = 0
    values: np.ndarray | None = field(default=None, repr=False)


def message(champ: Champ) -> bytes:
    """Construit un message d'édition 1 complet, en mémoire."""
    handle = eccodes.codes_grib_new_from_samples("regular_ll_sfc_grib1")
    try:
        eccodes.codes_set(handle, "Ni", int(GRILLE["ni"]))
        eccodes.codes_set(handle, "Nj", int(GRILLE["nj"]))
        for cle, valeur in (
            ("latitudeOfFirstGridPointInDegrees", GRILLE["lat1"]),
            ("longitudeOfFirstGridPointInDegrees", GRILLE["lon1"]),
            ("latitudeOfLastGridPointInDegrees", GRILLE["lat2"]),
            ("longitudeOfLastGridPointInDegrees", GRILLE["lon2"]),
            ("iDirectionIncrementInDegrees", GRILLE["di"]),
            ("jDirectionIncrementInDegrees", GRILLE["dj"]),
        ):
            eccodes.codes_set(handle, cle, valeur)
        eccodes.codes_set(handle, "table2Version", champ.table2_version)
        eccodes.codes_set(handle, "indicatorOfParameter", champ.indicator)
        eccodes.codes_set(handle, "indicatorOfTypeOfLevel", champ.level_type)
        eccodes.codes_set(handle, "level", champ.level)

        n = int(GRILLE["ni"] * GRILLE["nj"])
        valeurs = champ.values if champ.values is not None else np.full(n, 280.0)
        eccodes.codes_set_values(handle, np.asarray(valeurs, dtype=float))
        return bytes(eccodes.codes_get_message(handle))
    finally:
        eccodes.codes_release(handle)


def granule(cible: Path, champs: list[Champ]) -> Path:
    """Écrit un granule d'édition 1 à plusieurs messages."""
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(b"".join(message(c) for c in champs))
    return cible
