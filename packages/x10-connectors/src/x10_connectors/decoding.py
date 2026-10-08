"""Décodage GRIB2 vers des tableaux maillés, et normalisation.

Ce module ne **décode** pas lui-même : il encadre `cfgrib`, qui s'appuie sur
ecCodes. Sa valeur propre est ailleurs — écarter les champs redondants, poser
les noms standards CF que la chaîne ne fournit pas, et éviter les effets de
bord sur le disque.

**Règle de volumétrie** : aucun modèle Pydantic par point de grille. Les champs
restent dans des tableaux `xarray` ; les modèles servent aux métadonnées, à la
provenance et aux payloads d'API.

Dépendance optionnelle : installer l'extra `grib`.
"""

from __future__ import annotations

from types import ModuleType
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path

    import xarray as xr

#: Clés GRIB à faire remonter dans les attributs. `cfgrib` n'expose par défaut
#: ni la discipline ni les numéros de catégorie et de paramètre, or c'est le
#: **triplet** qui identifie un champ sans ambiguïté — un nom court peut être
#: absent, et `cfName` vaut souvent `unknown`.
READ_KEYS = ("discipline", "parameterCategory", "parameterNumber", "name")

#: Clés décrivant le **référentiel géodésique**. Le GRIB le déclare et notre
#: sortie le perdait : un consommateur devait alors supposer, et les modèles
#: travaillent sur une sphère qui n'est pas WGS84.
#:
#: Inutile de recoder la table 3.2 du format : ecCodes la résout et expose le
#: résultat. `earthIsOblate` tranche entre sphère et ellipsoïde, puis `radius`
#: ou le couple d'axes porte la valeur.
GEO_KEYS = (
    "shapeOfTheEarth",
    "earthIsOblate",
    "radius",
    "earthMajorAxis",
    "earthMinorAxis",
)

#: Options d'ouverture **fixées explicitement**, relevées le 08/10/2026.
#:
#: `cfgrib.open_datasets` expose dix-huit paramètres, et ses défauts décident
#: de la **forme du résultat**. S'en remettre à eux revient à laisser une
#: version mineure de la bibliothèque changer nos sorties sans que rien ne le
#: signale. Chaque valeur ci-dessous est donc écrite, avec sa raison.
OPTIONS_CFGRIB: dict[str, object] = {
    #: Défaut : `'{path}.{short_hash}.idx'`, qui **écrit à côté de la donnée**.
    #: Effet de bord indésirable sur un fichier en lecture seule ou déposé
    #: dans un stockage partagé.
    "indexpath": "",
    #: Défaut : `True`, qui **écrase les dimensions de longueur 1**. Mesuré :
    #: un paquet à une échéance rend `(latitude, longitude)` quand un paquet à
    #: deux rend `(step, latitude, longitude)`. La même donnée et le même code
    #: produisent alors deux structures différentes selon le contenu du
    #: fichier — un consommateur qui marche casse sans avoir rien changé, et
    #: aucune référence de structure n'est tenable. On garde les axes.
    "squeeze": False,
    #: Défaut : `('parameter', 'time', 'geography', 'vertical')`. Repris tel
    #: quel, mais écrit : ces quatre couches posent les noms CF, les axes
    #: temporels, les coordonnées et les niveaux.
    "encode_cf": ("parameter", "time", "geography", "vertical"),
    #: Défaut : `('time', 'step')`. Repris tel quel, et écrit pour la même
    #: raison — il décide de ce qui devient dimension plutôt que coordonnée.
    "time_dims": ("time", "step"),
}

#: Précision de restitution des valeurs. Défaut de `cfgrib`, repris
#: délibérément : les producteurs quantifient sur 12 bits, et la mantisse d'un
#: `float32` en porte 24. Passer en `float64` doublerait l'empreinte mémoire
#: sans ajouter la moindre information.
VALUES_DTYPE = "float32"


class GribIndisponible(RuntimeError):
    """La pile de décodage GRIB n'est pas installée."""


def _cfgrib() -> ModuleType:
    try:
        import cfgrib
    except ImportError as exc:  # pragma: no cover - depend de l'extra
        raise GribIndisponible(
            "La pile de décodage GRIB est absente. Installer l'extra : "
            "uv sync --all-packages --extra grib"
        ) from exc
    # `cfgrib` n'embarque pas de marqueur de typage : son import vaut `Any`.
    # Le passer par une variable typée garde la frontière explicite plutôt que
    # de laisser `Any` remonter dans la signature.
    module: ModuleType = cfgrib
    return module


def _numpy() -> ModuleType:
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - depend de l'extra
        raise GribIndisponible(
            "La pile de décodage GRIB est absente. Installer l'extra : "
            "uv sync --all-packages --extra grib"
        ) from exc
    return numpy


# --- Correspondance vers les noms standards CF --------------------------------
#
# Le vocabulaire CF **contient** ces noms : la table vérifiée le 06/10/2026
# contre la version 95 du tableau officiel en compte plus de cinq mille. Ce
# qui manque, c'est la correspondance depuis les codes GRIB, qu'ecCodes ne
# fournit que pour une minorité de champs — neuf sur cinquante et un pour
# AROME, neuf sur soixante-quatre pour ARPEGE.
#
# Cette table comble le manque pour les champs rencontrés. Chaque nom a été
# vérifié présent au tableau CF ; en ajouter un sans cette vérification
# produirait un fichier qui se dit conforme et ne l'est pas.

CF_STANDARD_NAMES: dict[tuple[int, int, int], str] = {
    (0, 0, 6): "dew_point_temperature",
    (0, 0, 10): "surface_upward_latent_heat_flux",
    (0, 0, 11): "surface_upward_sensible_heat_flux",
    (0, 1, 52): "precipitation_flux",
    (0, 1, 60): "surface_snow_amount",
    (0, 1, 83): "mass_fraction_of_cloud_liquid_water_in_air",
    (0, 1, 84): "mass_fraction_of_cloud_ice_in_air",
    (0, 2, 0): "wind_from_direction",
    (0, 2, 1): "wind_speed",
    (0, 2, 22): "wind_speed_of_gust",
    (0, 3, 1): "air_pressure_at_mean_sea_level",
    (0, 3, 6): "geopotential_height",
    (0, 3, 18): "atmosphere_boundary_layer_thickness",
    (0, 4, 7): "surface_downwelling_shortwave_flux_in_air",
    (0, 5, 3): "surface_downwelling_longwave_flux_in_air",
    (0, 6, 1): "cloud_area_fraction",
    (0, 6, 3): "low_type_cloud_area_fraction",
    (0, 6, 4): "medium_type_cloud_area_fraction",
    (0, 6, 5): "high_type_cloud_area_fraction",
    (0, 6, 13): "cloud_base_altitude",
    (0, 7, 6): "atmosphere_convective_available_potential_energy",
    (0, 19, 0): "visibility_in_air",
}

#: Champs pour lesquels **CF n'a pas de nom**, vérifié et non supposé. Les
#: énumérer vaut mieux que de les laisser se confondre avec un oubli de notre
#: part : ce sont des candidats à proposer au tableau CF.
SANS_NOM_CF: frozenset[tuple[int, int, int]] = frozenset(
    {
        (0, 19, 11),  # energie cinetique turbulente
    }
)

#: Direction et force du vent. **Écartées au décodage** : elles se recalculent
#: exactement à partir des composantes, et la direction est une grandeur
#: circulaire dont toute moyenne, interpolation ou dispersion calculée comme un
#: scalaire est fausse. Les conserver invite l'erreur.
#:
#: L'API ciblée du producteur ne les expose d'ailleurs pas non plus, pas plus
#: que les données ouvertes de l'ECMWF.
VENT_DERIVE: frozenset[tuple[int, int, int]] = frozenset({(0, 2, 0), (0, 2, 1)})


def triplet(variable: xr.DataArray) -> tuple[int, int, int] | None:
    """Identifiant GRIB d'un champ décodé, ou `None` s'il n'a pas été lu."""
    try:
        return (
            int(variable.attrs["GRIB_discipline"]),
            int(variable.attrs["GRIB_parameterCategory"]),
            int(variable.attrs["GRIB_parameterNumber"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def open_package(source: Path, *, errors: str = "raise") -> tuple[xr.Dataset, ...]:
    """Ouvre un paquet GRIB2 multi-messages.

    Renvoie **plusieurs** jeux : un fichier réel mêle des types de niveau et des
    gabarits de produit — instantané et cumul — que `xarray` ne peut pas réunir
    dans une seule structure. Les paquets de surface du producteur sont dans ce
    cas ; prétendre le contraire masquerait des champs.

    Toutes les options qui décident de la forme du résultat sont écrites dans
    `OPTIONS_CFGRIB`, et non héritées des défauts de la bibliothèque.

    **`errors` vaut `"raise"`, là où `cfgrib` retient `"warn"`.** Sur un
    message illisible, le défaut journalise puis **poursuit** : l'appelant
    reçoit un tuple d'apparence normale, amputé de champs, sans exception ni
    avertissement — un compte rendu `success` sur une donnée incomplète. Un
    échec visible se corrige ; une sortie fausse se propage. `"warn"` ou
    `"ignore"` restent accessibles à qui préfère la tolérance, et l'assument.
    """
    jeux: list[xr.Dataset] = _cfgrib().open_datasets(
        str(source),
        backend_kwargs={
            **OPTIONS_CFGRIB,
            "read_keys": [*READ_KEYS, *GEO_KEYS],
            "errors": errors,
            "values_dtype": _numpy().dtype(VALUES_DTYPE),
        },
    )
    return tuple(jeux)


def wind_speed(u: xr.DataArray, v: xr.DataArray) -> xr.DataArray:
    """Force du vent, norme du vecteur."""
    np = _numpy()
    out: xr.DataArray = np.hypot(u, v)
    out.attrs = {"standard_name": "wind_speed", "units": "m s-1"}
    out.name = "ws"
    return out


def wind_from_direction(u: xr.DataArray, v: xr.DataArray) -> xr.DataArray:
    """Direction **d'où vient** le vent, en degrés depuis le nord, sens horaire.

    Convention météorologique : un vent de nord vaut 0°, un vent d'est 90°.

    La direction n'a pas de sens quand le vent est faible — les composantes
    approchent de zéro et l'arc-tangente devient arbitraire. C'est précisément
    pourquoi ce champ est calculé à la demande plutôt que stocké.
    """
    np = _numpy()
    out: xr.DataArray = np.degrees(np.arctan2(-u, -v)) % 360.0
    out.attrs = {"standard_name": "wind_from_direction", "units": "degree"}
    out.name = "wdir"
    return out


def drop_derived_wind(jeu: xr.Dataset) -> xr.Dataset:
    """Retire direction et force du vent, qui se recalculent des composantes."""
    a_retirer = [str(nom) for nom, var in jeu.data_vars.items() if triplet(var) in VENT_DERIVE]
    return jeu.drop_vars(a_retirer) if a_retirer else jeu


#: Valeur de remplissage que la chaîne de décodage pose quand elle ne connaît
#: pas le nom standard. Elle est **pire qu'une absence** : un consommateur qui
#: lit `standard_name` y voit un nom, et un fichier la portant se dit conforme
#: aux conventions CF sans l'être.
PLACEHOLDER_CF = "unknown"


def _nom_cf_utilisable(valeur: object) -> str | None:
    return valeur if isinstance(valeur, str) and valeur and valeur != PLACEHOLDER_CF else None


def apply_cf_names(jeu: xr.Dataset) -> xr.Dataset:
    """Pose `standard_name` sur les champs que notre table couvre.

    Trois cas, dans cet ordre : un nom déjà posé et utilisable est conservé ;
    sinon celui de la chaîne de décodage ; sinon le nôtre. Quand aucun des
    trois ne donne de nom, **l'attribut est retiré** plutôt que laissé à sa
    valeur de remplissage — un champ sans nom standard doit se voir comme tel.
    """
    sortie = jeu.copy()
    for nom, var in sortie.data_vars.items():
        existant = _nom_cf_utilisable(var.attrs.get("standard_name"))
        if existant:
            continue
        retenu = _nom_cf_utilisable(var.attrs.get("GRIB_cfName")) or CF_STANDARD_NAMES.get(
            triplet(var) or (-1, -1, -1)
        )
        if retenu:
            sortie[nom].attrs["standard_name"] = retenu
        else:
            sortie[nom].attrs.pop("standard_name", None)
    return sortie


def normalise(jeu: xr.Dataset) -> xr.Dataset:
    """Écarte le vent dérivé, puis pose les noms standards CF."""
    return apply_cf_names(drop_derived_wind(jeu))


__all__ = [
    "CF_STANDARD_NAMES",
    "GEO_KEYS",
    "OPTIONS_CFGRIB",
    "PLACEHOLDER_CF",
    "READ_KEYS",
    "SANS_NOM_CF",
    "VALUES_DTYPE",
    "VENT_DERIVE",
    "GribIndisponible",
    "apply_cf_names",
    "drop_derived_wind",
    "normalise",
    "open_package",
    "triplet",
    "wind_from_direction",
    "wind_speed",
]
