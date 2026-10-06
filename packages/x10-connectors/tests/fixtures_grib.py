"""Fabrique de fichiers GRIB2 minuscules, pour tester sans rien télécharger.

Un message GRIB2 valide tient en quelques centaines d'octets dès lors que la
grille est petite : neuf points sur cinq suffisent à exercer le décodage, la
géométrie, les valeurs manquantes et les cumuls. Les tests construisent donc
leurs propres paquets, et **aucune donnée réelle n'est commise au dépôt**.

Les quatre pièges relevés sur les paquets réels se reproduisent ici :

* **valeurs manquantes** par masque binaire, dont la proportion varie d'un
  champ à l'autre — c'est le cas d'AROME et de son domaine trapézoïdal ;
* **gabarit statistique** `4.8`, qui porte une période de cumul, mêlé à des
  champs instantanés dans un même fichier ;
* **types de niveau mêlés** dans un même fichier ;
* **longitudes en 0 a 360**, que le format impose.

Dépend de la pile GRIB, déclarée en groupe de développement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import eccodes
import numpy as np

#: Grille d'essai par défaut : neuf points sur cinq autour du nord de la
#: France, bornée à cheval sur le méridien de Greenwich pour que la conversion
#: des longitudes soit réellement exercée.
GRILLE_PAR_DEFAUT = {
    "ni": 9,
    "nj": 5,
    "lat1": 52.0,
    "lon1": 356.0,
    "lat2": 48.0,
    "lon2": 4.0,
    "di": 1.0,
    "dj": 1.0,
}


@dataclass(frozen=True)
class Champ:
    """Un message à fabriquer.

    `accumulation` bascule le message sur le gabarit `4.8` et lui donne une
    période de cumul en heures. `manquants` fixe le nombre de points marqués
    absents, en tête de grille.
    """

    category: int
    number: int
    discipline: int = 0
    level_type: int = 103
    level: int = 10
    step: int = 0
    accumulation: int | None = None
    manquants: int = 0
    #: Précision de quantification. Les paquets réels encodent sur 12 bits ;
    #: la reproduire permet de mesurer la perte réelle plutôt qu'une perte
    #: idéalisée.
    bits: int = 12
    valeurs: np.ndarray | None = field(default=None, repr=False)


#: Valeur conventionnelle des points absents, celle qu'emploie le producteur.
VALEUR_MANQUANTE = 9999.0


def message(champ: Champ, grille: dict[str, float] | None = None) -> bytes:
    """Construit un message GRIB2 complet, en mémoire."""
    g = {**GRILLE_PAR_DEFAUT, **(grille or {})}
    ni, nj = int(g["ni"]), int(g["nj"])

    h = eccodes.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    try:
        eccodes.codes_set(h, "centre", 85)
        eccodes.codes_set(h, "Ni", ni)
        eccodes.codes_set(h, "Nj", nj)
        eccodes.codes_set(h, "latitudeOfFirstGridPointInDegrees", g["lat1"])
        eccodes.codes_set(h, "longitudeOfFirstGridPointInDegrees", g["lon1"])
        eccodes.codes_set(h, "latitudeOfLastGridPointInDegrees", g["lat2"])
        eccodes.codes_set(h, "longitudeOfLastGridPointInDegrees", g["lon2"])
        eccodes.codes_set(h, "iDirectionIncrementInDegrees", g["di"])
        eccodes.codes_set(h, "jDirectionIncrementInDegrees", g["dj"])

        eccodes.codes_set(h, "discipline", champ.discipline)
        eccodes.codes_set(h, "parameterCategory", champ.category)
        eccodes.codes_set(h, "parameterNumber", champ.number)
        eccodes.codes_set(h, "typeOfFirstFixedSurface", champ.level_type)
        eccodes.codes_set(h, "scaledValueOfFirstFixedSurface", champ.level)
        eccodes.codes_set(h, "step", champ.step)

        if champ.accumulation is not None:
            eccodes.codes_set(h, "productDefinitionTemplateNumber", 8)
            eccodes.codes_set(h, "typeOfStatisticalProcessing", 1)
            eccodes.codes_set(h, "indicatorOfUnitForTimeRange", 1)
            eccodes.codes_set(h, "lengthOfTimeRange", champ.accumulation)

        valeurs = champ.valeurs
        if valeurs is None:
            valeurs = np.linspace(0.0, 1.0, ni * nj)
        valeurs = np.asarray(valeurs, dtype=float).reshape(-1).copy()

        if champ.manquants:
            eccodes.codes_set(h, "bitmapPresent", 1)
            eccodes.codes_set(h, "missingValue", VALEUR_MANQUANTE)
            valeurs[: champ.manquants] = VALEUR_MANQUANTE

        eccodes.codes_set(h, "bitsPerValue", champ.bits)
        eccodes.codes_set_values(h, valeurs)
        return bytes(eccodes.codes_get_message(h))
    finally:
        eccodes.codes_release(h)


def paquet(cible: Path, champs: list[Champ], grille: dict[str, float] | None = None) -> Path:
    """Écrit un fichier GRIB2 multi-messages, comme un paquet réel."""
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(b"".join(message(c, grille) for c in champs))
    return cible


def champs_vent(steps: tuple[int, ...] = (0, 1), *, graine: int = 0) -> list[Champ]:
    """Les quatre champs de vent tels que les paquets les portent.

    Composantes **et** direction et force, cohérentes entre elles, afin que la
    reconstitution de la direction et de la force à partir des seules
    composantes puisse être vérifiée.
    """
    rng = np.random.default_rng(graine)
    n = int(GRILLE_PAR_DEFAUT["ni"] * GRILLE_PAR_DEFAUT["nj"])
    out: list[Champ] = []
    for step in steps:
        u = rng.normal(0.0, 8.0, n)
        v = rng.normal(0.0, 8.0, n)
        ff = np.hypot(u, v)
        dd = np.degrees(np.arctan2(-u, -v)) % 360.0
        out += [
            Champ(category=2, number=2, step=step, valeurs=u),
            Champ(category=2, number=3, step=step, valeurs=v),
            Champ(category=2, number=0, step=step, valeurs=dd),
            Champ(category=2, number=1, step=step, valeurs=ff),
        ]
    return out


__all__ = [
    "GRILLE_PAR_DEFAUT",
    "VALEUR_MANQUANTE",
    "Champ",
    "champs_vent",
    "message",
    "paquet",
]
