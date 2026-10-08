"""Écriture des champs décodés en NetCDF, suivant les conventions CF.

Lire et écrire sont deux métiers : le décodage vit dans `decoding`, l'écriture
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

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .base import AGENT
from .decoding import GribIndisponible
from .observability import connector_logger

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path

    import xarray as xr

    from x10_models import Retrieval

_log = connector_logger(__name__)

#: Version des conventions CF que nos sorties respectent. La chaîne de
#: décodage la pose déjà ; elle est reprise ici pour que l'écriture ne dépende
#: pas d'un attribut hérité.
CONVENTIONS = "CF-1.7"


#: Nom de la variable conteneur portant le référentiel. CF n'en impose aucun ;
#: `crs` est celui que pratiquent la plupart des producteurs.
CRS_VARIABLE = "crs"

#: Marqueur d'absence d'ecCodes sur une clé entière, `INT32_MAX`. Lu sans
#: précaution, il produirait un rayon terrestre de 2 147 483 647 mètres —
#: une valeur absurde qu'aucun contrôle de conformité ne rattraperait.
ECCODES_MANQUANT = 2147483647


class UniteNonConvertible(ValueError):
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
    #: Le décodage n'a pas su nommer le champ ; inventer une unité serait pire.
    "unknown": None,
}


def udunits(unite: str | None) -> str | None:
    """Traduit une unité GRIB en UDUNITS, ou renvoie `None` s'il n'y a rien à
    émettre.

    Lève `UniteNonConvertible` pour une unité inconnue de la table. C'est
    délibéré : deviner une conversion produirait un fichier faux, et un fichier
    faux qui se dit conforme est pire qu'une écriture qui refuse.
    """
    if unite is None or not unite.strip():
        return None
    if unite not in UDUNITS:
        raise UniteNonConvertible(
            f"Unité GRIB sans correspondance UDUNITS connue : {unite!r}. "
            "L'ajouter à `UDUNITS` après avoir vérifié la forme attendue, "
            "plutôt que de laisser l'écriture deviner."
        )
    return UDUNITS[unite]


def convert_units(jeu: xr.Dataset, *, strict: bool = True) -> xr.Dataset:
    """Réécrit les unités de chaque variable en UDUNITS.

    Une unité sans correspondance fait échouer l'écriture quand `strict`, et
    sinon disparaît de la variable. Dans les deux cas **rien n'est inventé**,
    et `GRIB_units`, que la chaîne de décodage conserve, garde la valeur
    d'origine.
    """
    sortie = jeu.copy()
    for nom, var in sortie.data_vars.items():
        origine = var.attrs.get("units")
        try:
            traduite = udunits(origine)
        except UniteNonConvertible:
            if strict:
                raise
            _log.warning(
                "Unité non convertible, attribut omis",
                extra={"x10.variable": str(nom), "x10.units": origine},
            )
            traduite = None
        if traduite is None:
            sortie[nom].attrs.pop("units", None)
        else:
            sortie[nom].attrs["units"] = traduite
    return sortie


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
AXES_DECLARABLES = ("time",)

CELL_METHODS: dict[str, str] = {
    "instant": "time: point",
    "avg": "time: mean",
    "accum": "time: sum",
    "sum": "time: sum",
    "max": "time: maximum",
    "min": "time: minimum",
    "rms": "time: root_mean_square",
    "sd": "time: standard_deviation",
}

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
SANS_CELL_METHOD = frozenset({"diff", "cov", "ratio", "stdanom"})


class TraitementStatistiqueInconnu(ValueError):
    """Un `stepType` absent de la table et non recensé comme sans équivalent."""


def cell_method(attrs: Mapping[str, object]) -> str | None:
    """Méthode de cellule d'une variable, ou `None` s'il n'y a rien à déclarer.

    **Lève sur un `stepType` inconnu.** Omettre serait tentant, mais un
    traitement non reconnu est précisément celui dont on ignore s'il est
    statistique : le passer sous silence produirait un cumul qui se présente
    comme un instantané. Les traitements que CF ne couvre réellement pas sont
    recensés dans `SANS_CELL_METHOD` et n'émettent rien, en connaissance de
    cause.
    """
    brut = attrs.get("GRIB_stepType")
    if brut is None:
        return None
    step_type = str(brut)
    if step_type in SANS_CELL_METHOD:
        _log.info(
            "Traitement statistique sans équivalent CF, aucune méthode émise",
            extra={"x10.step_type": step_type},
        )
        return None
    if step_type not in CELL_METHODS:
        raise TraitementStatistiqueInconnu(
            f"`stepType` GRIB inconnu : {step_type!r}. L'ajouter à "
            "`CELL_METHODS` après avoir vérifié la méthode au tableau E.1 de "
            "CF, ou à `SANS_CELL_METHOD` si CF ne la couvre pas."
        )
    return CELL_METHODS[step_type]


def cell_methods(jeu: xr.Dataset) -> dict[str, str]:
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
        str(nom): methode
        for nom, var in jeu.data_vars.items()
        if (methode := cell_method(var.attrs)) is not None
    }


# --- Référentiel géodésique ----------------------------------------------------


def _valeur(attrs: dict[str, object], cle: str) -> float | None:
    """Lit une clé GRIB numérique, en écartant le marqueur d'absence."""
    brut = attrs.get(f"GRIB_{cle}")
    if not isinstance(brut, (int, float)) or isinstance(brut, bool):
        return None
    valeur = float(brut)
    return None if valeur == ECCODES_MANQUANT else valeur


def grid_mapping(jeu: xr.Dataset) -> dict[str, object] | None:
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
    for var in jeu.data_vars.values():
        attrs = dict(var.attrs)
        if "GRIB_shapeOfTheEarth" not in attrs:
            continue
        mapping: dict[str, object] = {
            "grid_mapping_name": "latitude_longitude",
            "longitude_of_prime_meridian": 0.0,
            #: Trace de la correspondance, pour qui veut remonter au GRIB.
            "GRIB_shapeOfTheEarth": attrs["GRIB_shapeOfTheEarth"],
        }
        if _valeur(attrs, "earthIsOblate"):
            demi_grand = _valeur(attrs, "earthMajorAxis")
            demi_petit = _valeur(attrs, "earthMinorAxis")
            if demi_grand is None or demi_petit is None:
                return None
            mapping["semi_major_axis"] = demi_grand
            mapping["semi_minor_axis"] = demi_petit
        else:
            rayon = _valeur(attrs, "radius")
            if rayon is None:
                return None
            mapping["earth_radius"] = rayon
        return mapping
    return None


# --- Attributs globaux --------------------------------------------------------


def _ligne_history(precedente: str | None) -> str:
    """Trace d'audit, au format que pratiquent les producteurs.

    CF demande un journal des modifications. ECMWF écrit « date GMT by
    outil-version » ; la forme reprise ici en est proche, et **préserve** une
    éventuelle ligne antérieure plutôt que de l'écraser.
    """
    horodatage = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    ligne = f"{horodatage} : converted from GRIB2 by {AGENT}"
    return f"{ligne}\n{precedente}" if precedente else ligne


def global_attributes(
    jeu: xr.Dataset,
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
    attrs: dict[str, str] = {
        "Conventions": CONVENTIONS,
        "history": _ligne_history(jeu.attrs.get("history")),
    }
    if institution := jeu.attrs.get("institution"):
        attrs["institution"] = str(institution)
    if retrieval is not None:
        attrs["source"] = source or f"{retrieval.dataset}, origine {retrieval.origin}"
        if retrieval.license:
            attrs["license"] = retrieval.license
        attrs["comment"] = f"Acquis le {retrieval.retrieved_at.isoformat()} par {retrieval.agent}."
    elif source:
        attrs["source"] = source
    if title:
        attrs["title"] = title
    elif retrieval is not None:
        attrs["title"] = retrieval.dataset
    if references:
        attrs["references"] = references
    return attrs


def write_netcdf(
    jeu: xr.Dataset,
    cible: Path,
    *,
    retrieval: Retrieval | None = None,
    title: str | None = None,
    source: str | None = None,
    references: str | None = None,
    strict_units: bool = True,
) -> Path:
    """Écrit un jeu décodé en NetCDF, avec ses attributs CF et sa licence.

    Les unités sont converties avant écriture : un fichier qui déclare CF doit
    porter des unités qu'UDUNITS sait lire.
    """
    try:
        import netCDF4  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depend de l'extra
        raise GribIndisponible(
            "L'écriture NetCDF demande `netCDF4`. Installer l'extra : "
            "uv sync --all-packages --extra grib"
        ) from exc

    prepare = convert_units(jeu, strict=strict_units)
    prepare.attrs = {
        **prepare.attrs,
        **global_attributes(
            prepare, retrieval=retrieval, title=title, source=source, references=references
        ),
    }
    methodes = cell_methods(prepare)
    for nom in jeu.data_vars:
        if nom in methodes:
            prepare[nom].attrs["cell_methods"] = methodes[nom]
        else:
            # Rien à déclarer : on **retire** un éventuel attribut hérité
            # plutôt que de le laisser passer. Un `cell_methods` recopié est
            # une affirmation dont personne n'a vérifié qu'elle tient encore
            # après le traitement subi — voir `AXES_DECLARABLES`.
            prepare[nom].attrs.pop("cell_methods", None)

    if (mapping := grid_mapping(prepare)) is not None:
        import xarray

        prepare[CRS_VARIABLE] = xarray.DataArray(0, attrs=mapping)
        for nom in jeu.data_vars:
            prepare[nom].attrs["grid_mapping"] = CRS_VARIABLE

    cible.parent.mkdir(parents=True, exist_ok=True)
    prepare.to_netcdf(cible, engine="netcdf4")
    return cible


__all__ = [
    "AXES_DECLARABLES",
    "CELL_METHODS",
    "CONVENTIONS",
    "CRS_VARIABLE",
    "ECCODES_MANQUANT",
    "SANS_CELL_METHOD",
    "UDUNITS",
    "TraitementStatistiqueInconnu",
    "UniteNonConvertible",
    "cell_method",
    "cell_methods",
    "convert_units",
    "global_attributes",
    "grid_mapping",
    "udunits",
    "write_netcdf",
]
