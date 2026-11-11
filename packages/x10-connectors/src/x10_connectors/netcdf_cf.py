"""Écriture des champs décodés en NetCDF, suivant les conventions CF.

Lire et écrire sont deux métiers : le décodage vit dans `grib2`, l'écriture
ici, avec ses propres tables.

**Ce que font les producteurs, et que l'on suit.** Un relevé de quatre chaînes
réelles — NCEP via Unidata, deux jeux de la NOAA, et l'outil officiel
d'ECMWF — montre la même pratique : `Conventions` déclarant CF, puis une
poignée d'attributs globaux que **CF recommande lui-même** à sa section
2.6.2 — `title`, `institution`, `source`, `history`, `references`, `comment`.
Aucun n'emploie de convention de découverte, et aucun ne porte de licence.

**Les unités sont ramenées à la forme canonique d'UDUNITS**, celle que la
suite de tests d'UDUNITS et tous les producteurs emploient — `m s-1` plutôt
que le `m s**-1` d'ecCodes. Voir le détail près de la table.

**Ce que l'on ajoute, et pourquoi.** CF ne définit aucun attribut de licence,
or une donnée qui quitte le système sans la sienne n'est pas exploitable.
L'attribut `license` est donc émis — son nom vient d'ACDD et se comprend
partout. **`ACDD-1.3` n'est pas pour autant ajouté à `Conventions`** : nous
n'émettons pas l'ensemble qu'ACDD exige, et le déclarer serait prétendre à
une conformité que nous n'avons pas. Un attribut global supplémentaire ne
rend aucun fichier non conforme à CF.

Dépendance optionnelle : installer l'extra `grib`.
"""

from __future__ import annotations

import contextlib
import functools
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .base import AGENT, atomic_write, table_fingerprint
from .grib2 import (
    COORD_UNDEFINED,
    GribUnavailableError,
    _numpy,
    cf_tables_revision,
    decoder_versions,
)
from .observability import connector_logger

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path

    import xarray as xr

    from x10_models import Retrieval

_log = connector_logger(__name__)

#: Version des conventions CF que nos sorties respectent. La chaîne de
#: décodage la pose déjà ; elle est reprise ici pour que l'écriture ne dépende
#: pas d'un attribut hérité.
#:
#: **Montée de 1.7 à 1.11 le 22/10/2026**, et c'est la montée minimale :
#: vérifié au texte publié, `units_metadata` compte zéro occurrence en 1.10 et
#: quinze en 1.11. Sans elle, l'attribut serait émis hors convention. La seule
#: obligation que la montée ouvre est conditionnelle — § 5.6, `grid_mapping`
#: et `coordinates` dès que la grille n'est pas lon/lat — et nous l'émettons
#: déjà.
CONVENTIONS = "CF-1.11"

#: Ce que `units_metadata` dit d'une température, et pourquoi il le faut.
#:
#: `units` ne distingue pas une température **sur une échelle** d'un **écart**
#: de température : les deux s'écrivent `K`. En l'absence de l'attribut, CF
#: 1.11 § 3.1 prescrit de supposer `temperature: unknown`, et la conversion
#: vers une autre échelle n'est alors **pas garantie** — un écart converti par
#: addition de 273,15 au lieu d'une mise à l'échelle est le mode d'échec que
#: la convention nomme elle-même.
UNITS_METADATA_ON_SCALE = "temperature: on_scale"

#: Le `stepType` d'une **différence**, seul cas où une grandeur en kelvins
#: n'est pas sur une échelle. CF ne couvre pas ce traitement — il figure à
#: `WITHOUT_CELL_METHOD` — donc rien d'autre ne le signalerait.
STEP_TYPE_DIFFERENCE = "diff"


#: Niveau de compression `zlib` appliqué aux variables de données.
#:
#: Mesuré le 09/10/2026 sur un granule AROME réel : **42,97 Mio sans
#: compression, 12,80 Mio au niveau 4**, soit un facteur 3,4. Monter au
#: niveau 6 ne gagne que 2 % de plus, pour un temps d'écriture supérieur.
#:
#: **La compression impose le découpage** — HDF5 ne sait comprimer que des
#: blocs —, mais la forme de ces blocs ne décide pas de la taille : sur
#: données réelles, le découpage automatique fait aussi bien qu'un bloc par
#: échéance. Elle décide de la **quantité lue** par requête, ce qui relève de
#: l'usage et non de l'écriture. On laisse donc `netCDF4` la choisir.
#:
#: `0` désactive la compression. Détail dans `docs/formats-de-sortie.md`.
COMPRESSION = 4

#: Nom de la variable conteneur portant le référentiel. CF n'en impose aucun ;
#: `crs` est celui que pratiquent la plupart des producteurs.
CRS_VARIABLE = "crs"

#: Marqueur d'absence d'ecCodes sur une clé entière, `INT32_MAX`. Lu sans
#: précaution, il produirait un rayon terrestre de 2 147 483 647 mètres —
#: une valeur absurde qu'aucun contrôle de conformité ne rattraperait.
ECCODES_MISSING = 2147483647


class UnconvertibleUnitError(ValueError):
    """Une unité GRIB n'a pas de correspondance UDUNITS connue."""


# --- Unités : d'ecCodes vers UDUNITS ------------------------------------------
#
# CF impose des unités analysables par UDUNITS. ecCodes écrit les exposants
# avec `**` — `m s**-1`.
#
# **Nuance vérifiée dans la grammaire d'UDUNITS-2, le 08/10/2026.** Son lexeur
# porte la règle `("^"|"**")[+-]?{int} -> EXPONENT` : `m s**-1` **est** donc
# analysable, et un contrôleur CF ne le rejetterait pas. La conversion n'est
# pas une affaire de conformité.
#
# Elle reste justifiée pour deux raisons. La forme à tiret est la **forme
# canonique** : la suite de tests d'UDUNITS n'emploie que `s-1`, `m.s-1`,
# `m2.s-2`, jamais `**`, et c'est ce que tous les producteurs émettent. Et la
# forme `**` n'est lisible qu'au prix de la correspondance la plus longue —
# un `*` seul vaut multiplication dans cette même grammaire —, donc un
# consommateur qui n'embarque pas un analyseur UDUNITS complet peut lire
# `m s**-1` comme un produit.
#
# La table est **fermée** : une unité absente ne produit pas de conversion
# devinée. Le relevé des sources intégrées donne dix-neuf chaînes distinctes,
# dont quatre étaient déjà valides. La table a ensuite été confrontée aux
# paquets de surface réels des deux modèles — 1,3 Go balayés — qui ont
# révélé une unité de plus, `J m**-2`. Le test marqué `network` rejoue cette
# confrontation.

UDUNITS: dict[str, str | None] = {
    # Déjà conformes
    "%": "%",
    "K": "K",
    "Pa": "Pa",
    "m": "m",
    "s": "s",
    # Exposants à réécrire
    "J kg**-1": "J kg-1",
    "J m**-2": "J m-2",
    "K m**2 kg**-1 s**-1": "K m2 kg-1 s-1",
    "N m**-2": "N m-2",
    "Pa s**-1": "Pa s-1",
    "W m**-2": "W m-2",
    "kg kg**-1": "kg kg-1",
    "kg m**-2": "kg m-2",
    "kg m**-2 s**-1": "kg m-2 s-1",
    "m s**-1": "m s-1",
    "m**2 s**-2": "m2 s-2",
    "s**-1": "s-1",
    # Unités que nos propres fonctions dérivées posent déjà en UDUNITS
    "degree": "degree",
    "m s-1": "m s-1",
    # Cas nommés
    #: Convention GRIB pour un azimut. `degree` est défini par UDUNITS comme
    #: alias d'`arc_degree`, soit (pi/180) rad — vérifié dans sa base.
    "Degree true": "degree",
    #: Fraction sans dimension. La grammaire admet un nombre nu comme unité
    #: (`basic_exp: number`), et « 1 » est la façon d'écrire l'absence de
    #: dimension.
    "(0 - 1)": "1",
    #: Pas une unité : un code de table, qui relève d'une variable de drapeau
    #: avec `flag_values` et `flag_meanings`. Aucune unité ne doit être émise.
    "(Code table 4.201)": None,
    #: Façon dont ecCodes écrit l'absence de dimension en discipline 10.
    #: UDUNITS ne sait pas la lire — vérifié —, alors qu'il lit « 1 », qui
    #: est sa forme pour la même chose. Même traitement que `(0 - 1)`.
    "dimensionless": "1",
    #: Le décodage n'a pas su nommer le champ ; inventer une unité serait pire.
    "unknown": None,
    #: Façon dont ecCodes écrit « pas d'unité ». Même traitement que
    #: `unknown` : rien à émettre, et surtout rien à inventer.
    "~": None,
    # --- Familles relevées le 22/10/2026, et pourquoi elles entrent -------
    #
    # **Mesuré** : 42 chaînes qu'ecCodes émet sur les disciplines 0 et 10
    # n'avaient aucune entrée ici, couvrant **127 triplets sur 451, soit
    # 28 %**. La table fermée qui lève reste le bon choix, mais l'exposition
    # n'avait jamais été chiffrée : une source nouvelle avait plus d'une
    # chance sur quatre de bloquer l'écriture sur une unité dont la
    # traduction est purement mécanique.
    #
    # **Chacune est validée par UDUNITS lui-même**, pas par relecture —
    # `cf_units.Unit(...)` les accepte toutes.
    #: Deux façons d'écrire l'absence de dimension, que `1` dit déjà.
    "Numeric": "1",
    "Proportion": "1",
    #: Angles. UDUNITS lit `rad` et `degree`, pas les pluriels d'ecCodes.
    "radians": "rad",
    "degrees": "degree",
    #: Exposants à réécrire, de la même façon que les entrées ci-dessus.
    "kg m**-3": "kg m-3",
    "K s**-1": "K s-1",
    "m**2 s**-1": "m2 s-1",
    "kg kg**-1 s**-1": "kg kg-1 s-1",
    "m**-1": "m-1",
    "Bq m**-3": "Bq m-3",
    "J kg**-1 K**-1": "J kg-1 K-1",
    # --- Deux exclusions délibérées, et leurs raisons ---------------------
    #
    # `dB` : **UDUNITS le refuse**, vérifié. Rien à proposer sans inventer.
    #
    # `gpm`, le mètre géopotentiel : `m` passerait la validation d'UDUNITS et
    # serait **faux**. C'est exactement la faute que le dépôt a corrigée sur
    # `(0, 3, 6)`, où `geopotential_height` était faux deux fois. Une unité
    # qui se convertit n'est pas une unité qui veut dire la même chose.
}


#: Constructions CF qui désignent un **relèvement**, donc une grandeur
#: circulaire. CF documente lui-même la construction dans la description de
#: chacun de ces noms : « the phrase "from_direction" is used in the
#: construction X_from_direction and indicates the direction from which the
#: velocity vector of X is coming ».
#:
#: Une **règle** plutôt qu'une liste, délibérément : CF porte des dizaines de
#: noms de direction et une liste rouillerait, alors que la construction est
#: stable et documentée. Le risque d'excès est nul — ce qui se nomme ainsi
#: est un relèvement.
DIRECTION_SUFFIXES = ("_from_direction", "_to_direction")

#: Ce qu'un fichier doit dire d'une direction, faute de pouvoir l'empêcher.
#:
#: **Le mot juste n'est pas « non interpolable »** : moyenne, écart-type,
#: rééchantillonnage et interpolation sont tous des combinaisons linéaires,
#: et aucune n'est définie sur un cercle. La moyenne arithmétique de 350° et
#: 10° vaut 180°, soit l'exact opposé de la réponse juste. Dire « aucune
#: combinaison linéaire » couvre les quatre d'un coup et en donne la raison.
#:
#: En anglais : l'attribut franchit la frontière de sérialisation et sera lu
#: par un tiers.
CIRCULAR_COMMENT = (
    "Circular quantity: a bearing in degrees, where 0 and 360 denote the same "
    "value. Mean, standard deviation, interpolation and resampling are all "
    "linear combinations, and none of them is defined on a circle: the "
    "arithmetic mean of 350 and 10 is 180, the exact opposite of the right "
    "answer. Convert to unit vectors, combine those, then convert back."
)

#: Ce qu'un fichier doit dire d'une unité qu'il n'a pas su traduire.
#:
#: CF § 3.1 : « a variable with no units attribute is assumed to be
#: dimensionless ». Retirer l'unité **affirme** donc, et il faut dire que
#: l'affirmation ne tient pas. En anglais : l'attribut franchit la frontière
#: de sérialisation.
UNTRANSLATED_UNIT_COMMENT = (
    "The unit declared by the source, {unit!r}, has no UDUNITS equivalent in "
    "this chain, so no units attribute is emitted and no standard_name is "
    "claimed. Do not read the absence as dimensionless: the original string "
    "is preserved in the GRIB_units attribute."
)

#: Séparateur employé quand un commentaire est déjà posé sur la variable.
COMMENT_SEPARATOR = " "

#: Ce qu'ecCodes écrit quand la « valeur » d'un champ est un code et non une
#: mesure — « (Code table 4.201) », « (Code table 4.222) » et six autres.
#:
#: **Une règle plutôt qu'une liste**, comme pour les directions : la forme est
#: celle d'ecCodes, elle est stable, et une énumération rouillerait à chaque
#: table nouvelle. Un code n'a pas d'unité ; il n'y a rien à émettre, et
#: surtout rien à inventer.
CODE_TABLE_UNIT = re.compile(r"^\(Code table \d+\.\d+\)$")


def is_circular(standard_name: object) -> bool:
    """La grandeur est-elle un relèvement, donc circulaire ?"""
    return isinstance(standard_name, str) and standard_name.endswith(DIRECTION_SUFFIXES)


def units_metadata(attrs: Mapping[str, object]) -> str | None:
    """Ce qu'il faut dire d'une température, ou `None` s'il n'y a rien à dire.

    **L'absence de cet attribut n'est pas neutre** : CF 1.11 § 3.1 prescrit de
    supposer alors `temperature: unknown`, donc une conversion d'échelle non
    garantie. Une température absolue mérite donc de le déclarer.

    La règle est étroite à dessein : l'unité canonique doit être le kelvin, et
    le traitement statistique ne doit pas être une **différence** — seul cas
    où une grandeur en kelvins n'est pas sur une échelle, et que rien d'autre
    ne signalerait puisque CF ne couvre pas ce `stepType`.
    """
    if attrs.get("units") != "K":
        return None
    if str(attrs.get("GRIB_stepType", "")) == STEP_TYPE_DIFFERENCE:
        return None
    return UNITS_METADATA_ON_SCALE


def udunits(unit: str | None) -> str | None:
    """Traduit une unité GRIB en UDUNITS, ou renvoie `None` s'il n'y a rien à
    émettre.

    Lève `UnconvertibleUnitError` pour une unité inconnue de la table. C'est
    délibéré : deviner une conversion produirait un fichier faux, et un fichier
    faux qui se dit conforme est pire qu'une écriture qui refuse.
    """
    if unit is None or not unit.strip():
        return None
    if CODE_TABLE_UNIT.match(unit.strip()):
        return None
    if unit not in UDUNITS:
        raise UnconvertibleUnitError(
            f"GRIB unit with no known UDUNITS counterpart: {unit!r}. "
            "Add it to `UDUNITS` once the expected form has been checked, "
            "rather than letting the writer guess."
        )
    return UDUNITS[unit]


def convert_units(dataset: xr.Dataset, *, strict: bool = True) -> xr.Dataset:
    """Réécrit les unités de chaque variable en UDUNITS.

    Une unité sans correspondance fait échouer l'écriture quand `strict`, et
    sinon disparaît de la variable. Dans les deux cas **rien n'est inventé**,
    et `GRIB_units`, que la chaîne de décodage conserve, garde la valeur
    d'origine.

    **Mais une unité absente n'est pas muette, et c'est la correction du
    22/10/2026.** CF § 3.1 énonce qu'« a variable with no units attribute is
    assumed to be dimensionless » : la retirer **affirme** quelque chose de
    faux, exactement comme `standard_name = "unknown"` le faisait. Le nom
    standard est donc retiré avec elle — un nom dont CF impose que l'unité
    soit équivalente à sa canonique ne peut pas survivre sans unité — et un
    commentaire nomme l'unité d'origine, pour que l'écart se voie.
    """
    out = dataset.copy()
    for name, var in out.data_vars.items():
        origin = var.attrs.get("units")
        try:
            traduite = udunits(origin)
        except UnconvertibleUnitError:
            if strict:
                raise
            _log.warning(
                "Unit not convertible, attribute omitted",
                extra={"x10.variable": str(name), "x10.units": origin},
            )
            traduite = None
        if traduite is None:
            out[name].attrs.pop("units", None)
            if out[name].attrs.pop("standard_name", None) is not None or origin:
                precedent = str(out[name].attrs.get("comment", "")).strip()
                avis = UNTRANSLATED_UNIT_COMMENT.format(unit=origin)
                out[name].attrs["comment"] = (
                    f"{precedent}{COMMENT_SEPARATOR}{avis}" if precedent else avis
                )
        else:
            out[name].attrs["units"] = traduite
    return out


# --- Période d'agrégation : bornes de coordonnée -------------------------------
#
# `cell_methods` dit **la nature** du traitement, jamais sa **durée**. Un
# cumul sur six heures et un maximum sur une heure portent la même date de
# validité ; sans bornes, rien ne les sépare, et lire le cumul de l'échéance
# 6 h comme « la pluie de la sixième heure » se trompe d'un facteur six.
#
# CF exprime l'étendue d'une cellule par des **bornes**, et sa section 7.1
# n'admet deux sommets que sur une coordonnée **unidimensionnelle**. D'où la
# remise en forme préalable, voir `cf_shape`.
#
# Raisonnement complet et mesures dans `docs/intervalles-de-temps.md`.

#: Suffixe des variables de bornes. Celui qu'emploie netCDF-Java, donc celui
#: qu'un consommateur habitué aux fichiers d'Unidata reconnaîtra.
BOUNDS_SUFFIX = "_bnds"

#: Table 4.4 du format GRIB2, restreinte aux unités **représentables par une
#: durée fixe**. Mois, année et décennie en sont absents à dessein : leur
#: durée dépend de la date, et `timedelta64` ne sait pas les porter.
INTERVAL_UNITS: dict[int, tuple[int, str]] = {
    0: (1, "m"),
    1: (1, "h"),
    2: (1, "D"),
    10: (3, "h"),
    11: (6, "h"),
    12: (12, "h"),
    13: (1, "s"),
}


class UnrepresentableIntervalError(ValueError):
    """Une unité de fenêtre d'agrégation que l'on ne sait pas convertir."""


def _duration(longueur: int, unit_code: int) -> object:
    """Convertit une longueur de fenêtre en durée."""
    np = _numpy()
    if unit_code not in INTERVAL_UNITS:
        raise UnrepresentableIntervalError(
            f"Unknown or variable-length GRIB interval unit: {unit_code}. "
            "See table 4.4 of the format and `INTERVAL_UNITS`; months and "
            "years have no fixed duration and cannot become "
            "bounds."
        )
    facteur, unit = INTERVAL_UNITS[unit_code]
    return np.timedelta64(longueur * facteur, unit)


def time_bounds(dataset: xr.Dataset) -> object | None:
    """Bornes de la fenêtre d'agrégation, ou `None` s'il n'y en a pas.

    Renvoie un tableau `(n, 2)` — début puis fin — aligné sur la coordonnée
    de validité. La **fin** est la date de validité ; le **début** s'en
    déduit par la longueur de fenêtre, que `cfgrib` remonte en coordonnée.

    **Pourquoi la coordonnée et non l'attribut.** `cfgrib` prend l'attribut
    au premier message : sur les cumuls d'AROME, dont la fenêtre croît de une
    à six heures, il rendrait `1` partout. Les bornes seraient fausses à
    cinq échéances sur six.
    """
    np = _numpy()
    if "lengthOfTimeRange" not in dataset.coords or "valid_time" not in dataset.coords:
        return None

    longueurs = np.atleast_1d(dataset["lengthOfTimeRange"].values)
    if any(str(x) == COORD_UNDEFINED for x in longueurs):
        # Champ sans agrégation : il n'a pas d'étendue, et `time: point` le
        # dit déjà. Poser des bornes y serait une affirmation de trop.
        return None

    units = {
        int(var.attrs["GRIB_indicatorOfUnitForTimeRange"])
        for var in dataset.data_vars.values()
        if "GRIB_indicatorOfUnitForTimeRange" in var.attrs
    }
    if len(units) != 1:
        raise UnrepresentableIntervalError(
            f"Mixed interval units within a single dataset: {sorted(units)}. "
            "A single bounds coordinate cannot describe them."
        )
    (code,) = units

    end = np.atleast_1d(dataset["valid_time"].values).reshape(-1)
    start = np.array([f - _duration(int(n), code) for f, n in zip(end, longueurs, strict=True)])
    # `numpy` entre par import paresseux, donc sans types : la variable
    # annotée rend la frontière explicite plutôt que de laisser `Any`
    # remonter dans la signature. Même motif que `_cfgrib` dans `grib2`.
    bounds: object = np.stack([start, end], axis=-1)
    return bounds


#: Libellés posés sur la coordonnée de longueur de fenêtre. `cfgrib` la
#: remonte en nombre nu : un consommateur qui ne lirait pas les bornes y
#: verrait un entier sans unité ni sens. Les bornes restent la forme
#: normalisée ; ceci est le filet pour qui ne les exploite pas.
#: Clés d'encodage reprises telles quelles d'une variable à l'écriture.
#: Restreintes à l'échelle de temps : le reste de l'encodage hérité du
#: décodage appartient à `cfgrib` et ferait échouer le moteur netCDF4.
TIME_ENCODING = ("units", "calendar", "dtype")

LENGTH_ATTRS = {
    "long_name": "length of the aggregation window",
    "comment": (
        "Derived from GRIB lengthOfTimeRange. The normative form of this "
        "information is the bounds attached to the time coordinate."
    ),
}


def _label_length(dataset: xr.Dataset) -> None:
    """Donne un libellé et une unité à la longueur de fenêtre, en place."""
    if "lengthOfTimeRange" not in dataset.coords:
        return
    units = {
        int(var.attrs["GRIB_indicatorOfUnitForTimeRange"])
        for var in dataset.data_vars.values()
        if "GRIB_indicatorOfUnitForTimeRange" in var.attrs
    }
    attrs: dict[str, str] = dict(LENGTH_ATTRS)
    if len(units) == 1:
        (code,) = units
        if code in INTERVAL_UNITS:
            facteur, unit = INTERVAL_UNITS[code]
            attrs["units"] = {"m": "minutes", "h": "hours", "D": "days", "s": "seconds"}[unit]
            if facteur != 1:
                attrs["units"] = f"{facteur} {attrs['units']}"
    dataset["lengthOfTimeRange"].attrs.update(attrs)


def cf_shape(dataset: xr.Dataset) -> xr.Dataset:
    """Ramène l'axe temporel à une seule dimension, la date de validité.

    La chaîne de décodage rend `(time, step, …)` : la date de réseau et
    l'échéance sont deux axes, et `valid_time` en dérive, donc
    **bidimensionnelle**. Or CF n'admet des bornes à deux sommets que sur une
    coordonnée unidimensionnelle.

    Pour un granule — qui appartient à **un** réseau —, l'axe de réseau est de
    longueur 1. Le réduire en **coordonnée scalaire** conserve la date sans
    coûter une dimension, et l'axe porte alors la validité. Mesuré : cinq
    dimensions deviennent quatre, et rien n'est perdu.

    Un jeu couvrant plusieurs réseaux est rendu **inchangé** : la réduction
    serait une perte, et c'est un cas que nos granules ne produisent pas.
    """
    if "time" not in dataset.dims or dataset.sizes.get("time", 0) != 1:
        return dataset
    if "step" not in dataset.dims or "valid_time" not in dataset.coords:
        return dataset
    return dataset.squeeze("time", drop=False).swap_dims({"step": "valid_time"})


# --- Méthodes de cellule : la nature du traitement statistique -----------------
#
# **Le manque que cette table comble est dangereux, pas cosmétique.** Un champ
# cumulé et un champ instantané se ressemblent trait pour trait une fois
# décodés : mêmes dimensions, même unité, mêmes coordonnées. Sans
# `cell_methods`, rien ne les distingue, et un consommateur moyenne des
# cumuls — exactement la faute que l'on a déjà écartée sur les directions de
# vent, où la moyenne de 350° et 10° donne l'opposé de la réponse juste.
#
# ecCodes résout la table 4.10 du format GRIB2 et expose le résultat en
# `stepType` ; la correspondance vers CF nous incombe.
#
# **Chaque méthode est vérifiée présente au tableau E.1 du standard**, lu le
# 08/10/2026 dans les sources du dépôt des conventions. Une méthode inventée
# produirait un fichier qui se dit conforme sans l'être.
#
# Le nom `time` désigne ici le **nom standard**, ce que CF autorise
# explicitement à sa section 7.3 — et non la dimension `time`, qui porte chez
# `cfgrib` la date de réseau. La coordonnée qui porte `standard_name = "time"`
# est `valid_time`, et c'est bien d'elle qu'il s'agit.

#: Axes sur lesquels une méthode peut être **déclarée par simple traduction**
#: de ce que porte le GRIB. Un seul : le temps.
#:
#: **`area:` n'en fait pas partie, et c'est un choix motivé.** Une méthode
#: spatiale — « ce point est la moyenne sur la maille » — cesse d'être vraie
#: dès que le producteur rééchantillonne, ce que tous font : l'IFS diffuse en
#: latitude-longitude régulière un champ calculé sur une grille gaussienne
#: réduite octaédrique, AROME et ARPEGE de même depuis leurs grilles natives.
#: L'ECMWF qualifie lui-même le rééchantillonnage de **procédure destructrice**
#: (newsletter 169, « Advanced regridding in Metview »).
#:
#: La nuance porte sur « par défaut » : rien n'interdit de déclarer une
#: méthode spatiale qu'on aurait **soi-même calculée** en connaissance de
#: cause. Ce qui est proscrit, c'est de la **recopier** — hériter d'un
#: attribut dont on ne sait pas s'il survit au traitement subi.
DECLARABLE_AXES = ("time",)

CELL_METHODS: dict[str, str] = {
    "instant": "time: point",
    "avg": "time: mean",
    "accum": "time: sum",
    "sum": "time: sum",
    "max": "time: maximum",
    "min": "time: minimum",
    "rms": "time: root_mean_square",
    "sd": "time: standard_deviation",
    #: Mode, traitement 101 de la table 4.10. Vérifié présent au tableau E.1
    #: de CF, et **atteignable** : ecCodes rend bien `stepType = mode`.
    "mode": "time: mode",
}

#: **`median` n'entre pas, et ce n'est pas un oubli.** Le tableau E.1 de CF le
#: porte, la table 4.10 de l'OMM aussi — traitement 13 —, mais mesuré le
#: 22/10/2026 : poser `typeOfStatisticalProcessing = 13` fait lever
#: `KeyValueNotFoundError` à la lecture de `stepType`. ecCodes ne l'expose
#: pas, donc l'entrée serait du code mort. À rouvrir si une version
#: ultérieure le rend.
MEDIAN_NOT_EXPOSED = 13

#: Traitements de la table 4.10 que **CF ne couvre pas**, recensés plutôt que
#: rapprochés de force d'une méthode voisine :
#:
#: * `diff` — différence entre fin et début de période. `range` est la
#:   différence entre maximum et minimum, ce n'est pas la même grandeur.
#: * `cov` — la covariance ne figure pas au tableau E.1.
#: * `ratio` — le rapport non plus.
#: * `stdanom` — anomalie **normalisée**. Le tableau porte `anomaly_wrt`, qui
#:   décrit un écart à une norme et non un écart réduit par l'écart-type ;
#:   la méthode est d'ailleurs postérieure au CF-1.7 que nous déclarons.
WITHOUT_CELL_METHOD = frozenset({"diff", "cov", "ratio", "stdanom"})


class UnknownStatisticalProcessingError(ValueError):
    """Un `stepType` absent de la table et non recensé comme sans équivalent."""


def cell_method(attrs: Mapping[str, object]) -> str | None:
    """Méthode de cellule d'une variable, ou `None` s'il n'y a rien à déclarer.

    **Lève sur un `stepType` inconnu.** Omettre serait tentant, mais un
    traitement non reconnu est précisément celui dont on ignore s'il est
    statistique : le passer sous silence produirait un cumul qui se présente
    comme un instantané. Les traitements que CF ne couvre réellement pas sont
    recensés dans `WITHOUT_CELL_METHOD` et n'émettent rien, en connaissance de
    cause.
    """
    raw = attrs.get("GRIB_stepType")
    if raw is None:
        return None
    step_type = str(raw)
    if step_type in WITHOUT_CELL_METHOD:
        _log.info(
            "Statistical processing with no CF equivalent, no method emitted",
            extra={"x10.step_type": step_type},
        )
        return None
    if step_type not in CELL_METHODS:
        raise UnknownStatisticalProcessingError(
            f"Unknown GRIB `stepType`: {step_type!r}. Add it to "
            "`CELL_METHODS` once the method has been checked against table E.1 "
            "of CF, or to `WITHOUT_CELL_METHOD` if CF does not cover it."
        )
    return CELL_METHODS[step_type]


def cell_methods(dataset: xr.Dataset) -> dict[str, str]:
    """Méthodes de cellule du jeu, par variable.

    **La résolution est par variable, et non par jeu.** On pouvait croire
    `cfgrib` capable de séparer les traitements statistiques, puisqu'il
    éclate un paquet en plusieurs jeux. Il n'en est rien : il groupe par
    **forme d'hypercube**, pas par traitement. Vérifié le 08/10/2026 sur un
    paquet AROME de surface réel, où un même jeu réunit quatre champs cumulés
    — rayonnement, précipitations, neige, grésil — et un champ instantané.
    Une méthode unique par jeu y était tout simplement fausse.

    Les fixtures ne le montraient pas : elles ne produisaient que des jeux
    homogènes. Il a fallu un fichier du producteur pour le voir.
    """
    return {
        str(name): methode
        for name, var in dataset.data_vars.items()
        if (methode := cell_method(var.attrs)) is not None
    }


# --- Référentiel géodésique ----------------------------------------------------


def _value(attrs: dict[str, object], key: str) -> float | None:
    """Lit une clé GRIB numérique, en écartant le marqueur d'absence."""
    raw = attrs.get(f"GRIB_{key}")
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return None
    value = float(raw)
    return None if value == ECCODES_MISSING else value


#: Les formes de la Terre dont la table 3.2 du format **nomme le datum**.
#:
#: Le code 8 est le seul cas où le producteur déclare autre chose qu'une
#: géométrie : son libellé dit que « the horizontal datum of the resulting
#: latitude/longitude field is the WGS-84 reference frame ». Le code 6, le
#: nôtre, ne dit rien — et c'est pourquoi rien n'est émis pour lui. Supposer
#: à la place du producteur serait la faute que `grid_mapping` corrige déjà
#: en rendant `None` plutôt qu'un défaut.
DECLARED_DATUM: dict[int, str] = {8: "WGS84"}


def _datum(attrs: Mapping[str, object]) -> dict[str, str]:
    """Le datum **déclaré** par le message, s'il en déclare un."""
    try:
        forme = int(str(attrs["GRIB_shapeOfTheEarth"]))
    except (KeyError, TypeError, ValueError):
        return {}
    nom = DECLARED_DATUM.get(forme)
    return {"horizontal_datum_name": nom} if nom else {}


def grid_mapping(dataset: xr.Dataset) -> dict[str, object] | None:
    """Décrit le référentiel géodésique, au sens de l'annexe F de CF.

    **Pourquoi ce n'est pas un détail.** Les modèles de prévision travaillent
    sur une sphère — 6 371 229 m pour AROME, ARPEGE et l'IFS — et non sur
    l'ellipsoïde WGS84. Le GRIB le déclare, et un NetCDF sans `grid_mapping`
    le perd : le consommateur doit alors supposer, sans rien pour l'avertir
    qu'il suppose.

    Renvoie `None` si le jeu ne porte pas l'information, plutôt que de poser
    un référentiel par défaut — supposer à la place du producteur serait la
    faute même que cette fonction corrige.
    """
    for var in dataset.data_vars.values():
        attrs = dict(var.attrs)
        if "GRIB_shapeOfTheEarth" not in attrs:
            continue
        mapping: dict[str, object] = {
            "grid_mapping_name": "latitude_longitude",
            "longitude_of_prime_meridian": 0.0,
            #: Trace de la correspondance, pour qui veut remonter au GRIB.
            "GRIB_shapeOfTheEarth": attrs["GRIB_shapeOfTheEarth"],
            **_datum(attrs),
        }
        if _value(attrs, "earthIsOblate"):
            demi_grand = _value(attrs, "earthMajorAxis")
            demi_petit = _value(attrs, "earthMinorAxis")
            if demi_grand is None or demi_petit is None:
                return None
            mapping["semi_major_axis"] = demi_grand
            mapping["semi_minor_axis"] = demi_petit
        else:
            rayon = _value(attrs, "radius")
            if rayon is None:
                return None
            mapping["earth_radius"] = rayon
        return mapping
    return None


# --- Attributs globaux --------------------------------------------------------


#: Table 4.3 du format GRIB2, type de processus générateur. Relevée dans les
#: définitions d'ecCodes le 09/10/2026 ; seules les valeurs rencontrées ou
#: plausibles sur nos sources y figurent, un code absent n'étant pas traduit
#: plutôt que deviné.
PROCESS_TYPE = {
    0: "analysis",
    1: "initialization",
    2: "forecast",
    3: "bias corrected forecast",
    4: "ensemble forecast",
    5: "probability forecast",
    9: "climatological",
    13: "post-processed forecast",
    14: "nowcast",
    15: "hindcast",
}

#: Table 1.3 du format GRIB2, statut de production. Même provenance.
PRODUCTION_STATUS = {
    0: "operational",
    1: "operational test",
    2: "research",
    3: "re-analysis",
}


def production_source(dataset: xr.Dataset) -> str | None:
    """Décrit le **processus de production**, au sens de l'attribut `source`.

    CF y attend « the method of production of the original data […] name the
    model and its version ». Nous y écrivions l'identifiant du jeu et
    l'origine du téléchargement : c'était l'acquisition, qui relève de
    `history`.

    **Ce que le GRIB permet de dire, et pas davantage.** Le statut de
    production et le type de processus se résolvent par les tables 1.3 et
    4.3. Le nom du modèle, lui, n'y est pas : `generatingProcessIdentifier`
    est un code **local au centre**, qu'aucune table publique ne traduit et
    qu'ecCodes ne sait pas rendre littéralement — vérifié. Nous le citons
    tel quel plutôt que d'en déduire « AROME », ce qui serait une
    interprétation et non une lecture.

    Renvoie `None` si rien n'est déclaré. Un appelant qui en sait plus — le
    catalogue, le jour où il sera peuplé — passe `source=` et l'emporte.
    """
    attrs: dict[str, object] = {}
    for var in dataset.data_vars.values():
        attrs.update(var.attrs)
    attrs.update(dataset.attrs)

    parts: list[str] = []
    code_statut = _integer(attrs, "productionStatusOfProcessedData")
    code_processus = _integer(attrs, "typeOfGeneratingProcess")
    statut = PRODUCTION_STATUS.get(code_statut) if code_statut is not None else None
    processus = PROCESS_TYPE.get(code_processus) if code_processus is not None else None
    if statut and processus:
        parts.append(f"{statut} {processus}")
    elif processus:
        parts.append(processus)

    centre = attrs.get("GRIB_centre")
    description = attrs.get("GRIB_centreDescription")
    if centre:
        parts.append(f"centre {centre}" + (f" ({description})" if description else ""))

    identifiant = _integer(attrs, "generatingProcessIdentifier")
    if identifiant is not None:
        # Code local au centre : on le cite, on ne le traduit pas.
        parts.append(f"generating process {identifiant}")

    return ", ".join(parts) or None


def _integer(attrs: dict[str, object], key: str) -> int | None:
    raw = attrs.get(f"GRIB_{key}")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return int(raw)


def _maintenant() -> str:
    """L'instant de l'écriture, au format que CF emploie dans `history`."""
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


#: Constantes de module que `output_tables_revision` **n'a pas à couvrir**,
#: avec leur raison. Chaque entrée est une ligne de `git diff` qu'un relecteur
#: lit, sur le modèle du lexique public.
#:
#: `COMPRESSION` ne change que les **octets**, jamais le sens : deux fichiers
#: qui n'en diffèrent disent la même chose, et l'appelant la passe de toute
#: façon en paramètre. `MEDIAN_NOT_EXPOSED` ne décide rien — c'est le numéro
#: de table de l'OMM qui documente pourquoi la médiane est absente, et aucun
#: chemin d'exécution ne le consulte.
UNFINGERPRINTED: frozenset[str] = frozenset({"COMPRESSION", "MEDIAN_NOT_EXPOSED"})


@functools.lru_cache(maxsize=1)
def output_tables_revision() -> str:
    """Empreinte des tables de ce module, celles qui décident d'un attribut écrit.

    **Pendant de `grib2.cf_tables_revision`, et il manquait.** L'empreinte
    des noms CF ne dit rien de l'unité canonique, de la méthode de cellule,
    des bornes d'intervalle, du datum ni des commentaires — toutes choses que
    ce module écrit dans le fichier. Deux sorties pouvaient donc différer sur
    chacune d'elles en portant la même signature.

    Mise en cache pour la même raison, et avec la même réserve : un test qui
    modifie une table doit appeler `output_tables_revision.cache_clear()`.
    """
    return table_fingerprint(sys.modules[__name__], exempt=UNFINGERPRINTED)


def _outillage() -> str:
    """Les versions qui décident de ce que le fichier dira.

    L'empreinte de nos tables répond à la question que deux fichiers
    divergents posent : *laquelle a parlé ?* Elle est **dérivée du contenu**,
    donc elle ne peut pas être oubliée au moment d'un changement.
    """
    pieces = [
        f"x10 cf tables {cf_tables_revision()}",
        f"x10 output tables {output_tables_revision()}",
    ]
    # La pile GRIB est un extra : une sortie écrite sans elle reste traçable
    # par l'empreinte de nos tables, qui ne dépend d'aucune dépendance.
    with contextlib.suppress(Exception):  # pragma: no cover - extra absent
        pieces += [f"{nom} {version}" for nom, version in sorted(decoder_versions().items())]
    return ", ".join(pieces)


def _history_line(precedente: str | None, *lines: str) -> str:
    """Journal d'audit cumulatif, au format que CF recommande.

    CF demande « an audit trail for modifications to the original data », et
    que chaque ligne commence par la date et l'heure. Les filtres génériques
    **ajoutent** la leur ; les nouvelles lignes vont donc **à la fin**, dans
    l'ordre chronologique, et une trace antérieure est préservée.
    """
    horodatage = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    nouvelles = [*lines, f"{horodatage} : converted from GRIB2 by {AGENT}"]
    return "\n".join([precedente, *nouvelles] if precedente else nouvelles)


def global_attributes(
    dataset: xr.Dataset,
    *,
    retrieval: Retrieval | None = None,
    title: str | None = None,
    source: str | None = None,
    references: str | None = None,
) -> dict[str, str]:
    """Attributs globaux à poser, les six de CF plus la licence.

    Sans `retrieval`, ni `license` ni `source` ne sont produits : **l'absence
    de provenance doit se voir dans le fichier**, et non être comblée par une
    valeur plausible.
    """
    acquisitions: list[str] = []
    if retrieval is not None:
        # **L'acquisition relève de `history`, pas de `source`.** Elle
        # modifie la donnée — elle la déplace — et CF réserve `source` à la
        # méthode de production.
        horodatage = retrieval.retrieved_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        acquisitions.append(
            f"{horodatage} : retrieved {retrieval.dataset} "
            f"from {retrieval.origin} by {retrieval.agent}"
        )

    # **La trace de notre propre outillage**, sans laquelle une divergence
    # future est inattribuable. `GRIB_tablesVersion` dit la version des tables
    # du producteur ; rien ne disait la nôtre. Deux fichiers écrits depuis le
    # même granule à six mois d'écart peuvent porter deux `standard_name`
    # différents — c'est arrivé le 22/10/2026 — et le lecteur doit pouvoir
    # dire lequel de nous ou du producteur a bougé.
    acquisitions.append(f"{_maintenant()} : normalised by {AGENT} ({_outillage()})")

    attrs: dict[str, str] = {
        "Conventions": CONVENTIONS,
        "history": _history_line(dataset.attrs.get("history"), *acquisitions),
    }
    if institution := dataset.attrs.get("institution"):
        attrs["institution"] = str(institution)
    if (methode := source or production_source(dataset)) is not None:
        attrs["source"] = methode
    if retrieval is not None and retrieval.license:
        attrs["license"] = retrieval.license
    if title:
        attrs["title"] = title
    elif retrieval is not None:
        attrs["title"] = retrieval.dataset
    if references:
        attrs["references"] = references
    return attrs


def _encoding(dataset: xr.Dataset, compress: int) -> dict[str, dict[str, object]]:
    """Encodage d'écriture : compression des données, et coordonnées sans
    valeur de remplissage.

    **`xarray` pose un `_FillValue` sur toute variable flottante**, y compris
    les coordonnées. CF l'y déconseille — une coordonnée n'admet pas de
    valeur manquante —, et un contrôleur de conformité le relève. On le
    retire explicitement plutôt que de le laisser passer.
    """
    # **Un dictionnaire d'encodage remplace celui que porte la variable, il
    # ne le complète pas.** Omettre la reprise a produit une coordonnée en
    # « hours since 13:00 » et ses bornes en « hours since 12:00 » : deux
    # époques, que seuls leurs attributs propres rendaient lisibles.
    #
    # La reprise est **sélective** : l'encodage hérité du décodage porte des
    # clés propres à `cfgrib` — `filter_by_keys`, `encode_cf` — que le
    # moteur netCDF4 refuse. On ne garde que l'échelle de temps.
    repris: dict[str, dict[str, object]] = {
        str(name): {
            key: value for key, value in dataset[name].encoding.items() if key in TIME_ENCODING
        }
        for name in (*dataset.coords, *dataset.data_vars)
    }

    encodage: dict[str, dict[str, object]] = {
        str(name): {**repris[str(name)], "_FillValue": None} for name in dataset.coords
    }
    # Les bornes ne sont pas une donnée : leur encodage est **conservé**, ce
    # qui les aligne sur leur coordonnée, et elles ne sont pas comprimées —
    # quelques dizaines d'octets n'y gagneraient rien.
    bounds = [name for name in dataset.data_vars if str(name).endswith(BOUNDS_SUFFIX)]
    encodage.update({str(name): {**repris[str(name)], "_FillValue": None} for name in bounds})
    if compress:
        encodage.update(
            {
                str(name): {"zlib": True, "complevel": compress}
                for name in dataset.data_vars
                if name not in bounds
            }
        )
    return encodage


def write_netcdf(
    dataset: xr.Dataset,
    target: Path,
    *,
    retrieval: Retrieval | None = None,
    title: str | None = None,
    source: str | None = None,
    references: str | None = None,
    strict_units: bool = True,
    compress: int = COMPRESSION,
) -> Path:
    """Écrit un jeu décodé en NetCDF, avec ses attributs CF et sa licence.

    Les unités sont converties avant écriture : un fichier qui déclare CF doit
    porter des unités qu'UDUNITS sait lire.
    """
    try:
        import netCDF4  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depend de l'extra
        raise GribUnavailableError(
            "Writing NetCDF requires `netCDF4`. Install the extra: "
            "uv sync --all-packages --extra grib"
        ) from exc

    prepare = convert_units(dataset, strict=strict_units)
    prepare.attrs = {
        **prepare.attrs,
        **global_attributes(
            prepare, retrieval=retrieval, title=title, source=source, references=references
        ),
    }
    methodes = cell_methods(prepare)
    for name in dataset.data_vars:
        if name in methodes:
            prepare[name].attrs["cell_methods"] = methodes[name]
        else:
            # Rien à déclarer : on **retire** un éventuel attribut hérité
            # plutôt que de le laisser passer. Un `cell_methods` recopié est
            # une affirmation dont personne n'a vérifié qu'elle tient encore
            # après le traitement subi — voir `AXES_DECLARABLES`.
            prepare[name].attrs.pop("cell_methods", None)
        # Une direction reste une direction : on ne peut pas l'écarter comme
        # on écarte celle du vent, faute de composantes chez le producteur et
        # de noms CF pour les exprimer. Ce que le fichier peut faire, c'est
        # le dire -- CF n'offrant rien de plus structuré qu'un commentaire.
        # Une température sans `units_metadata` se lit `temperature:
        # unknown`, donc sans garantie de conversion d'échelle. L'absence
        # affirme ; on dit donc ce qu'il en est.
        if (echelle := units_metadata(prepare[name].attrs)) is not None:
            prepare[name].attrs["units_metadata"] = echelle
        if is_circular(prepare[name].attrs.get("standard_name")):
            precedent = str(prepare[name].attrs.get("comment", "")).strip()
            prepare[name].attrs["comment"] = (
                f"{precedent}{COMMENT_SEPARATOR}{CIRCULAR_COMMENT}"
                if precedent
                else CIRCULAR_COMMENT
            )

    if (mapping := grid_mapping(prepare)) is not None:
        import xarray

        prepare[CRS_VARIABLE] = xarray.DataArray(0, attrs=mapping)
        for name in dataset.data_vars:
            prepare[name].attrs["grid_mapping"] = CRS_VARIABLE

    prepare = cf_shape(prepare)
    _label_length(prepare)
    if (bounds := time_bounds(prepare)) is not None:
        import xarray

        bounds_name = f"valid_time{BOUNDS_SUFFIX}"
        prepare[bounds_name] = xarray.DataArray(bounds, dims=("valid_time", "bnds"))
        # **Les bornes reprennent l'encodage de leur coordonnée** — même
        # époque, même calendrier. Sans cela `xarray` en choisit une autre,
        # et les deux ne se lisent plus sur la même échelle : mesuré une
        # fois à une heure d'écart.
        prepare[bounds_name].encoding = dict(prepare["valid_time"].encoding)
        # CF : la variable de bornes **n'hérite pas** d'attributs propres ;
        # c'est la coordonnée qui la désigne.
        prepare["valid_time"].attrs["bounds"] = bounds_name

    # L'écriture est atomique : un NetCDF tronqué s'ouvre parfois sans erreur
    # et rend des variables amputées, ce qui est exactement le genre de panne
    # silencieuse que la chaîne doit s'interdire.
    with atomic_write(target) as provisoire:
        prepare.to_netcdf(provisoire, engine="netcdf4", encoding=_encoding(prepare, compress))
    return target


__all__ = [
    "BOUNDS_SUFFIX",
    "CELL_METHODS",
    "CIRCULAR_COMMENT",
    "COMMENT_SEPARATOR",
    "COMPRESSION",
    "CONVENTIONS",
    "CRS_VARIABLE",
    "DECLARABLE_AXES",
    "DIRECTION_SUFFIXES",
    "ECCODES_MISSING",
    "INTERVAL_UNITS",
    "LENGTH_ATTRS",
    "PROCESS_TYPE",
    "PRODUCTION_STATUS",
    "STEP_TYPE_DIFFERENCE",
    "TIME_ENCODING",
    "UDUNITS",
    "UNITS_METADATA_ON_SCALE",
    "UNTRANSLATED_UNIT_COMMENT",
    "WITHOUT_CELL_METHOD",
    "UnconvertibleUnitError",
    "UnknownStatisticalProcessingError",
    "UnrepresentableIntervalError",
    "cell_method",
    "cell_methods",
    "cf_shape",
    "convert_units",
    "global_attributes",
    "grid_mapping",
    "is_circular",
    "output_tables_revision",
    "production_source",
    "time_bounds",
    "udunits",
    "units_metadata",
    "write_netcdf",
]
