"""Fabrique de fichiers GRIB2 minuscules, pour tester sans rien télécharger.

Un message GRIB2 valide tient en quelques centaines d'octets dès lors que la
grille est petite : neuf points sur cinq suffisent à exercer le décodage, la
géométrie, les valeurs manquantes et les cumuls. Les tests construisent donc
leurs propres paquets, et **aucune donnée réelle n'est commise au dépôt**.

Les cinq pièges relevés sur les paquets réels se reproduisent ici :

* **valeurs manquantes** par masque binaire, dont la proportion varie d'un
  champ à l'autre — c'est le cas d'AROME et de son domaine trapézoïdal ;
* **gabarit statistique** `4.8`, qui porte une période de cumul, mêlé à des
  champs instantanés dans un même fichier ;
* **types de niveau mêlés** dans un même fichier ;
* **longitudes en 0 a 360**, que le format impose ;
* **empaquetage CCSDS**, celui des fichiers réels, et non l'empaquetage
  simple que produirait un échantillon laissé tel quel ;
* **prévision d'ensemble**, gabarit `4.1`, qui ajoute un axe de membre.

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
#: Empaquetage de la section de données. **CCSDS, gabarit 5.42**, parce que
#: c'est celui des fichiers réels : mesuré le 08/10/2026 sur un paquet AROME
#: comme sur les données ouvertes de l'ECMWF. L'échantillon d'ecCodes
#: produirait sinon du `grid_simple`, que la production n'emploie pas, et le
#: décodage ne serait jamais exercé contre ce qu'il rencontre vraiment.
DEFAULT_PACKING = "grid_ccsds"


class PackingNotAppliedError(RuntimeError):
    """ecCodes a accepté l'empaquetage demandé sans l'appliquer."""


DEFAULT_GRID = {
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
class Field:
    """Un message à fabriquer.

    `accumulation` bascule le message sur le gabarit `4.8` et lui donne une
    période de cumul en heures. `manquants` fixe le nombre de points marqués
    absents, en tête de grille. `membre` bascule sur le gabarit `4.1`, celui
    d'une prévision d'ensemble.
    """

    category: int
    number: int
    discipline: int = 0
    level_type: int = 103
    level: int = 10
    step: int = 0
    #: Version des tables maîtresses de l'OMM déclarée par le message. Sert à
    #: simuler un producteur qui a pris de l'avance sur notre ecCodes — cas
    #: qu'aucune donnée réelle ne nous offre aujourd'hui, et qui ne lève
    #: pourtant rien.
    tables: int | None = None
    #: Version des tables **locales**, octet 11 de la section 1. L'échantillon
    #: d'ecCodes la laisse à zéro, ce qui est la valeur des fichiers réels du
    #: producteur ; la fixer permet de construire le cas conforme, où un code
    #: de la plage locale s'accompagne bien d'une table locale déclarée.
    local_tables: int | None = None
    accumulation: int | None = None
    #: Type de traitement statistique, table 4.10 du format GRIB2. N'a de sens
    #: qu'avec `accumulation`, qui ouvre le gabarit `4.8`. Défaut : 1, le
    #: cumul. ecCodes le traduit en `stepType` au décodage — 0 donne `avg`,
    #: 2 `max`, 4 `diff`, et ainsi de suite.
    statistic: int = 1
    #: Numéro de perturbation. Non nul, bascule le message sur le gabarit
    #: `4.1` — prévision d'ensemble — et fait apparaître un axe `number` au
    #: décodage. Non combinable avec `accumulation`, qui relèverait du
    #: gabarit `4.11`.
    member: int | None = None
    #: Taille de l'ensemble annoncée par le message.
    members: int = 0
    missing: int = 0
    #: Précision de quantification. Les paquets réels encodent sur 12 bits ;
    #: la reproduire permet de mesurer la perte réelle plutôt qu'une perte
    #: idéalisée.
    bits: int = 12
    #: Empaquetage de la section de données, voir `PACKING_PAR_DEFAUT`.
    packing: str = DEFAULT_PACKING
    values: np.ndarray | None = field(default=None, repr=False)


#: Valeur conventionnelle des points absents, celle qu'emploie le producteur.
MISSING_VALUE = 9999.0


def message(spec: Field, grid: dict[str, float] | None = None) -> bytes:
    """Construit un message GRIB2 complet, en mémoire."""
    g = {**DEFAULT_GRID, **(grid or {})}
    ni, nj = int(g["ni"]), int(g["nj"])

    h = eccodes.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    try:
        eccodes.codes_set(h, "centre", 85)
        # Avant les paramètres : c'est la version de tables qui décide de la
        # façon dont ecCodes les résout.
        if spec.tables is not None:
            eccodes.codes_set(h, "tablesVersion", spec.tables)
        if spec.local_tables is not None:
            eccodes.codes_set(h, "localTablesVersion", spec.local_tables)
        eccodes.codes_set(h, "Ni", ni)
        eccodes.codes_set(h, "Nj", nj)
        eccodes.codes_set(h, "latitudeOfFirstGridPointInDegrees", g["lat1"])
        eccodes.codes_set(h, "longitudeOfFirstGridPointInDegrees", g["lon1"])
        eccodes.codes_set(h, "latitudeOfLastGridPointInDegrees", g["lat2"])
        eccodes.codes_set(h, "longitudeOfLastGridPointInDegrees", g["lon2"])
        eccodes.codes_set(h, "iDirectionIncrementInDegrees", g["di"])
        eccodes.codes_set(h, "jDirectionIncrementInDegrees", g["dj"])

        eccodes.codes_set(h, "discipline", spec.discipline)
        eccodes.codes_set(h, "parameterCategory", spec.category)
        eccodes.codes_set(h, "parameterNumber", spec.number)
        eccodes.codes_set(h, "typeOfFirstFixedSurface", spec.level_type)
        eccodes.codes_set(h, "scaledValueOfFirstFixedSurface", spec.level)
        eccodes.codes_set(h, "step", spec.step)

        if spec.member is not None and spec.accumulation is not None:
            raise ValueError(
                "Cumul et ensemble relèveraient du gabarit 4.11, que cette "
                "fabrique ne construit pas encore."
            )

        if spec.member is not None:
            eccodes.codes_set(h, "productDefinitionTemplateNumber", 1)
            eccodes.codes_set(h, "typeOfEnsembleForecast", 3)
            eccodes.codes_set(h, "perturbationNumber", spec.member)
            eccodes.codes_set(h, "numberOfForecastsInEnsemble", spec.members or 1)

        if spec.accumulation is not None:
            eccodes.codes_set(h, "productDefinitionTemplateNumber", 8)
            eccodes.codes_set(h, "typeOfStatisticalProcessing", spec.statistic)
            eccodes.codes_set(h, "indicatorOfUnitForTimeRange", 1)
            eccodes.codes_set(h, "lengthOfTimeRange", spec.accumulation)

        values = spec.values
        if values is None:
            values = np.linspace(0.0, 1.0, ni * nj)
        values = np.asarray(values, dtype=float).reshape(-1).copy()

        if spec.missing:
            eccodes.codes_set(h, "bitmapPresent", 1)
            eccodes.codes_set(h, "missingValue", MISSING_VALUE)
            values[: spec.missing] = MISSING_VALUE

        eccodes.codes_set(h, "packingType", spec.packing)
        eccodes.codes_set(h, "bitsPerValue", spec.bits)
        eccodes.codes_set_values(h, values)
        raw = bytes(eccodes.codes_get_message(h))
    finally:
        eccodes.codes_release(h)

    _require_packing(raw, spec.packing)
    return raw


def _require_packing(raw: bytes, expected: str) -> None:
    """Relit le message et refuse un empaquetage qui n'a pas pris.

    **ecCodes accepte certains réglages sans les appliquer** : demander
    `grid_second_order` ne lève rien et produit un `grid_simple`. Une fixture
    qui ne relit pas se croirait alors en train d'exercer un empaquetage
    qu'elle n'a jamais écrit — un test vert sur une hypothèse fausse, ce qui
    est pire que pas de test.
    """
    h = eccodes.codes_new_from_message(raw)
    try:
        obtenu = eccodes.codes_get(h, "packingType")
    finally:
        eccodes.codes_release(h)
    if obtenu != expected:
        raise PackingNotAppliedError(
            f"Empaquetage demandé {expected!r}, mais le message porte {obtenu!r}. "
            "ecCodes l'a accepté sans l'appliquer ; cette installation ne le "
            "prend pas en charge."
        )


def granule(target: Path, specs: list[Field], grid: dict[str, float] | None = None) -> Path:
    """Écrit un fichier GRIB2 multi-messages, comme un paquet réel."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"".join(message(c, grid) for c in specs))
    return target


def wind_fields(steps: tuple[int, ...] = (0, 1), *, graine: int = 0) -> list[Field]:
    """Les quatre champs de vent tels que les paquets les portent.

    Composantes **et** direction et force, cohérentes entre elles, afin que la
    reconstitution de la direction et de la force à partir des seules
    composantes puisse être vérifiée.
    """
    rng = np.random.default_rng(graine)
    n = int(DEFAULT_GRID["ni"] * DEFAULT_GRID["nj"])
    out: list[Field] = []
    for step in steps:
        u = rng.normal(0.0, 8.0, n)
        v = rng.normal(0.0, 8.0, n)
        ff = np.hypot(u, v)
        dd = np.degrees(np.arctan2(-u, -v)) % 360.0
        out += [
            Field(category=2, number=2, step=step, values=u),
            Field(category=2, number=3, step=step, values=v),
            Field(category=2, number=0, step=step, values=dd),
            Field(category=2, number=1, step=step, values=ff),
        ]
    return out


__all__ = [
    "DEFAULT_GRID",
    "DEFAULT_PACKING",
    "MISSING_VALUE",
    "Field",
    "PackingNotAppliedError",
    "granule",
    "message",
    "wind_fields",
]
