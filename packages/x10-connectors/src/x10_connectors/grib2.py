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

import functools
from types import ModuleType
from typing import TYPE_CHECKING

from .observability import connector_logger

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path

    import xarray as xr

_log = connector_logger(__name__)

#: Clés GRIB à faire remonter dans les attributs. `cfgrib` n'expose par défaut
#: ni la discipline ni les numéros de catégorie et de paramètre, or c'est le
#: **triplet** qui identifie un champ sans ambiguïté — un nom court peut être
#: absent, et `cfName` vaut souvent `unknown`.
READ_KEYS = (
    "discipline",
    "parameterCategory",
    "parameterNumber",
    "name",
    # **L'édition du format, et de quoi identifier un champ dans chacune.**
    # Mesuré le 20/10/2026 : l'édition 1 ne porte ni `discipline` ni
    # `parameterCategory` ni `parameterNumber`, et l'édition 2 ne porte ni
    # `table2Version` ni `indicatorOfParameter`. Demander les quatre ne
    # coûte rien — une clé absente est simplement absente de l'attribut, et
    # la bissection des dix-huit clés n'en a trouvé aucune qui fasse échouer
    # l'ouverture d'un granule de l'une ou l'autre édition.
    "editionNumber",
    "table2Version",
    "indicatorOfParameter",
    # Le seul identifiant que **les deux éditions partagent**, et qu'ecCodes
    # résout depuis l'une comme depuis l'autre : 167 est la température à 2 m
    # dans ERA5 en édition 1 comme dans AROME en édition 2. C'est l'axe du
    # nommage, là où l'identité d'un champ reste propre à son édition.
    "paramId",
    # Unité de la fenêtre d'agrégation, table 4.4 du format. Elle reste un
    # **attribut** et non une coordonnée : contrairement à la longueur, elle
    # ne varie pas d'une échéance à l'autre.
    "indicatorOfUnitForTimeRange",
    # Ce que le format déclare du **processus de production**, et que CF
    # attend dans son attribut `source`. Trois clés, trois degrés de
    # lisibilité : deux se résolvent par des tables normalisées, la
    # troisième est un code **local au centre** qu'aucune table publique ne
    # traduit.
    "typeOfGeneratingProcess",
    "productionStatusOfProcessedData",
    "generatingProcessIdentifier",
    # Version des tables maîtresses de l'OMM **déclarée par le message**, et
    # version la plus récente que notre ecCodes sache résoudre. Les comparer
    # est le seul moyen de voir venir une évolution du référentiel ; voir
    # `check_tables_version`.
    "tablesVersion",
    "tablesVersionLatest",
    # Version des tables **locales**, octet 11 de la section 1. Zéro y
    # signifie que les tables locales ne sont pas employées, donc que seules
    # les entrées des tables maîtresses hors plage réservée à l'usage local
    # sont valides. Confrontée aux numéros de paramètre par
    # `check_local_tables`.
    "localTablesVersion",
    # Gabarit de définition de produit, section 4. **Le triplet ne suffit
    # pas** : mesuré le 19/10/2026 sur le flux de vagues d'ECMWF, `swh` et
    # les six hauteurs par bande de période partagent `(10, 0, 3)` et ne se
    # distinguent que par leur gabarit — 4.0 contre 4.104.
    "productDefinitionTemplateNumber",
    # Taille de l'ensemble **déclarée par le message**. C'est le seul
    # discriminant fiable d'un axe de membres : mesuré sur trois gabarits, le
    # 4.104 remplit les octets d'ensemble de zéros, de sorte que `number` et
    # `perturbationNumber` y valent 0 sur une prévision déterministe. Voir
    # `contract.ENSEMBLE_SIZE`.
    "numberOfForecastsInEnsemble",
)

#: Attributs portant les versions de tables, une fois décodés.
ATTR_TABLES_VERSION = "GRIB_tablesVersion"
ATTR_TABLES_LATEST = "GRIB_tablesVersionLatest"
ATTR_LOCAL_TABLES = "GRIB_localTablesVersion"

#: Première valeur de la **plage réservée à l'usage local**. Le format la
#: réserve dans les trois composantes du triplet — discipline, catégorie,
#: numéro — et jusqu'à 254, 255 valant « manquant ». Un code de cette plage
#: n'a de sens que rapporté à une table locale.
LOCAL_USE_RANGE_START = 192

#: Clés décrivant le **référentiel géodésique**. Le GRIB le déclare et notre
#: sortie le perdait : un consommateur devait alors supposer, et les modèles
#: travaillent sur une sphère qui n'est pas WGS84.
#:
#: Inutile de recoder la table 3.2 du format : ecCodes la résout et expose le
#: résultat. `earthIsOblate` tranche entre sphère et ellipsoïde, puis `radius`
#: ou le couple d'axes porte la valeur.
#: Attributs que `cfgrib` pose à partir des clés ci-dessus. Les nommer évite
#: de répandre des chaînes littérales dans les fonctions qui les lisent.
ATTR_EDITION = "GRIB_editionNumber"
ATTR_PARAM_ID = "GRIB_paramId"
ATTR_TABLE2_VERSION = "GRIB_table2Version"
ATTR_INDICATOR = "GRIB_indicatorOfParameter"

#: Un `paramId` nul signifie « non résolu », pas « paramètre zéro ».
#: Mesuré le 20/10/2026 : deux champs de tables locales de Météo-France le
#: portent tous les deux. L'employer comme identité les confondrait.
PARAM_ID_UNRESOLVED = 0

GEO_KEYS = (
    "shapeOfTheEarth",
    "earthIsOblate",
    "radius",
    "earthMajorAxis",
    "earthMinorAxis",
)

#: Options d'ouverture **fixées explicitement**, relevées le 08/10/2026.
#:
#: Les défauts de `cfgrib` décident de la **forme du résultat**. S'en remettre
#: à eux revient à laisser une version mineure de la bibliothèque changer nos
#: sorties sans que rien ne le signale. Chaque valeur ci-dessous est donc
#: écrite, avec sa raison.
#:
#: **Correction du 19/10/2026 : le compte annoncé ici était faux.** Il était
#: écrit « dix-huit paramètres » ; `CfGribBackend.open_dataset` en expose
#: **vingt**, sur la même version de cfgrib. Ce n'était donc pas une dérive de
#: la bibliothèque, mais un comptage que personne n'avait vérifié — et la
#: règle « on écrit plutôt qu'on hérite » reposait dessus.
#:
#: **Nous en fixons huit** : les cinq ci-dessous, plus `read_keys`, `errors` et
#: `values_dtype`, posés à l'appel. **Douze restent héritées** : `mask_and_scale`,
#: `decode_times`, `decode_coords`, `decode_timedelta`, `use_cftime`,
#: `concat_characters`, `drop_variables`, `lock`, `filter_by_keys`,
#: `ignore_keys`, `coords_as_attributes`, `cache_geo_coords`. Les recenser est
#: le minimum ; les contrôler reste à faire, et la méthode est une
#: introspection de signature — voir [docs/standards-et-outillage.md].
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
    #: Défaut : `{}`. **Remonte la longueur de la fenêtre d'agrégation en
    #: coordonnée**, le long de l'axe des échéances.
    #:
    #: Indispensable, et l'attribut ne suffit pas : `cfgrib` le prend au
    #: **premier message**. Mesuré le 09/10/2026 sur des fenêtres variables
    #: — (0→1), (0→2), (0→3) — l'attribut rend `1`, un seul chiffre pour
    #: trois fenêtres. Des bornes bâties dessus seraient fausses partout sauf
    #: à la première échéance. En coordonnée, on obtient `[1, 2, 3]`.
    #:
    #: **Effet de bord bienvenu** : la coordonnée distingue les hypercubes,
    #: donc `cfgrib` sépare désormais cumuls et instantanés qu'il réunissait.
    #: Sur un granule AROME de surface, cinq jeux deviennent six, et **chacun
    #: est homogène en structure d'intervalle** — ce qu'il fallait pour que
    #: chaque fichier écrit ne porte qu'un seul axe temporel.
    #:
    #: Sur un champ sans intervalle, la valeur vaut la chaîne `'undef'` et non
    #: une absence : le lire sans précaution donnerait une fenêtre absurde.
    "extra_coords": {"lengthOfTimeRange": "step"},
}

#: Valeur que `cfgrib` pose sur une coordonnée issue d'une clé GRIB absente.
#: C'est une **chaîne**, pas un manquant : la confondre avec un nombre
#: produirait une fenêtre d'agrégation sur un champ qui n'en a pas.
COORD_UNDEFINED = "undef"

#: Précision de restitution des valeurs. Défaut de `cfgrib`, repris
#: délibérément : les producteurs quantifient sur 12 bits, et la mantisse d'un
#: `float32` en porte 24. Passer en `float64` doublerait l'empreinte mémoire
#: sans ajouter la moindre information.
VALUES_DTYPE = "float32"


class GribUnavailableError(RuntimeError):
    """La pile de décodage GRIB n'est pas installée."""


class DroppedFieldsError(RuntimeError):
    """Des paramètres présents dans le fichier n'apparaissent pas au décodage."""


def _cfgrib() -> ModuleType:
    try:
        import cfgrib
    except ImportError as exc:  # pragma: no cover - depend de l'extra
        raise GribUnavailableError(
            "The GRIB decoding stack is missing. Install the extra: "
            "uv sync --all-packages --extra grib"
        ) from exc
    # `cfgrib` n'embarque pas de marqueur de typage : son import vaut `Any`.
    # Le passer par une variable typée garde la frontière explicite plutôt que
    # de laisser `Any` remonter dans la signature.
    module: ModuleType = cfgrib
    return module


def _eccodes() -> ModuleType:
    try:
        import eccodes
    except ImportError as exc:  # pragma: no cover - depend de l'extra
        raise GribUnavailableError(
            "The GRIB decoding stack is missing. Install the extra: "
            "uv sync --all-packages --extra grib"
        ) from exc
    module: ModuleType = eccodes
    return module


def _numpy() -> ModuleType:
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - depend de l'extra
        raise GribUnavailableError(
            "The GRIB decoding stack is missing. Install the extra: "
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
    # Discipline 10 — produits océanographiques. Relevé le 19/10/2026 sur le
    # flux `wave` d'ECMWF open data, treize paramètres. Chaque nom est
    # **vérifié présent au tableau CF version 95**.
    (10, 0, 3): "sea_surface_wave_significant_height",
    #: Direction moyenne des vagues. **Le nom qui semble évident est le
    #: mauvais** : `sea_surface_wave_mean_from_direction` désigne chez CF une
    #: grandeur *spectrale*, « the wave direction in each frequency band »,
    #: que sa description distingue explicitement du paramètre global. `mwd`
    #: est global. C'est donc le nom générique qui convient.
    #:
    #: Elle est **conservée telle quelle**, contrairement à la direction du
    #: vent qui est écartée au profit des composantes. La règle ne change
    #: pas, son application dépend de ce que CF offre : il existe des noms
    #: pour les composantes du vent, il n'en existe aucun pour celles d'une
    #: direction de vagues, et ECMWF n'en publie pas. En inventer deux serait
    #: la faute que la table entière évite. La contrepartie est portée dans
    #: le fichier produit, voir `netcdf_cf.CIRCULAR_COMMENT`.
    (10, 0, 14): "sea_surface_wave_from_direction",
    (10, 0, 15): "sea_surface_wave_mean_period",
    #: Période moyenne de passage par zéro. CF définit `T(m2)` comme la racine
    #: du rapport `M(0)/M(2)` des moments fréquentiels, ce qui **est** la
    #: période de passage par zéro ; la correspondance n'est donc pas une
    #: approximation.
    (10, 0, 28): (
        "sea_surface_wave_mean_period_from_variance_spectral_density_second_frequency_moment"
    ),
    #: Période de pic. CF l'écrit lui-même dans sa description : « sometimes
    #: called peak wave period ».
    (10, 0, 34): "sea_surface_wave_period_at_variance_spectral_density_maximum",
}

#: Triplets dont le nom CF **ne vaut que pour certains gabarits** de la
#: section 4. Le triplet seul désignerait alors plusieurs grandeurs, et poser
#: le nom sans vérifier le gabarit en nommerait une pour une autre.
#:
#: `(10, 0, 3)` est le cas mesuré, le 19/10/2026 sur le flux `wave`
#: d'ECMWF : sept messages le portent. Un seul, de gabarit `4.0`, est la
#: hauteur significative totale ; les six autres, de gabarit `4.104`, sont
#: des hauteurs significatives **par bande de période** — de 10 à 12
#: secondes, de 12 à 14, et ainsi de suite. Les nommer comme le total serait
#: faux et dangereux : les hauteurs par bande se composent en somme
#: quadratique, non en somme, de sorte qu'un consommateur les additionnant
#: sous un même nom obtiendrait une valeur sans signification.
#:
#: CF n'a aucun nom pour une hauteur significative restreinte à une bande de
#: période ; les six restent donc **sans nom standard**, et l'absence se voit.
TEMPLATE_RESTRICTED: dict[tuple[int, int, int], frozenset[int]] = {
    (10, 0, 3): frozenset({0}),
}

#: Champs pour lesquels **CF n'a pas de nom**, vérifié et non supposé. Les
#: énumérer vaut mieux que de les laisser se confondre avec un oubli de notre
#: part : ce sont des candidats à proposer au tableau CF.
WITHOUT_CF_NAME: frozenset[tuple[int, int, int]] = frozenset(
    {
        (0, 19, 11),  # energie cinetique turbulente
        #: « Coefficient of drag with waves ». CF a bien
        #: `surface_drag_coefficient_for_momentum_in_air`, mais il **ne dit
        #: rien des vagues** — or c'est la distinction que l'OMM et le
        #: producteur tracent en nommant le code ainsi. L'y ramener
        #: confondrait un coefficient calculé par un modèle de vagues avec un
        #: coefficient qui ne l'est pas, sous un seul nom.
        (10, 0, 16),
    }
)

#: Codes dont le **triplet ne détermine pas la grandeur**. Rien ne manque au
#: vocabulaire CF ici : c'est le code GRIB qui désigne plusieurs champs, de
#: sorte qu'aucun nom ne peut être posé sans savoir d'où vient le fichier.
#: Les distinguer de `SANS_NOM_CF` importe — l'un se corrige en proposant un
#: nom à CF, l'autre pas.
#:
#: `(0, 3, 6)`, « Geometric height », est le cas établi. **L'OMM le dit
#: elle-même** : sa note 124 recommande les numéros 33 et 34 à la place du 6,
#: « because it does not indicate whether this is referring to height above
#: mean sea level or height above ground » — et laisse le 6 opérationnel.
#: Mesuré le 13/10/2026 sur la grille AROME 0,025° : le code porte le relief
#: du modèle dans les champs CONSTANT et un **autre** champ dans le paquet
#: SP2, masqué sur 17,2 % du domaine et s'écartant du relief de 44 m en
#: médiane au-dessus de 1 000 m. La table du producteur le nomme `ALTITUDE`,
#: sans préciser laquelle.
#:
#: Notre table posait `geopotential_height`, qui est **faux** à deux titres :
#: c'est l'entrée 5 de la table 4.2-0-3, et elle s'exprime en mètres
#: géopotentiels quand le champ est en mètres. Le retirer vaut mieux que de
#: lui substituer une autre supposition.
#: `(10, 4, 7)`, « Model bathymetry », est le second cas, et il prend l'autre
#: forme de l'ambiguïté : ce n'est pas le code qui désigne plusieurs champs,
#: c'est **CF qui exige une précision que le producteur ne déclare pas**. Le
#: tableau offre cinq profondeurs de fond selon le niveau de référence —
#: géoïde, niveau moyen de la mer, surface, ellipsoïde, datum géopotentiel —
#: et rien dans le message ne dit lequel le modèle emploie. Le classement
#: reste le bon : il n'y a rien à proposer à CF, seulement un choix que nous
#: ne pouvons pas faire.
#: Noms CF que nous posons **par `paramId`**, pour les champs qu'aucune autre
#: voie ne nomme.
#:
#: **Pourquoi une seconde table, et pas une seule.** L'identité d'un champ est
#: propre à son édition — triplet en 2, `(table2Version, indicatorOfParameter)`
#: en 1 — mais `paramId` vaut la même chose des deux côtés. Indexer le
#: nommage par lui évite d'écrire deux fois le même nom ; indexer l'identité
#: par lui serait faux, puisqu'il vaut zéro sur un paramètre non résolu.
#:
#: **Elle reste un complément, pas un remplacement.** Mesuré le 20/10/2026 sur
#: les huit granules d'édition 1 du corpus : trois champs sur quatorze sont
#: déjà nommés par ecCodes, six le sont par le second passage de
#: `cf_name_for_param_id`, et cette table ne vise que le reste.
#:
#: Chaque nom est **vérifié présent au tableau CF**, version 95, le
#: 20/10/2026 — et le test marqué `network` les y confronte avec les autres.
CF_BY_PARAM_ID: dict[int, str] = {
    # `tp` d'ERA5 et d'ERA5-Land, en **mètres** : une épaisseur d'eau
    # liquide équivalente, et non une masse surfacique. ecCodes ne le nomme
    # pas, et son encodage d'édition 2 est un code **local** `(0, 1, 193)`
    # qu'aucune table maîtresse ne couvre.
    228: "lwe_thickness_of_precipitation_amount",
    # `swh` de MFWAM. Le même champ porte `(10, 0, 3)` en édition 2, que
    # `CF_STANDARD_NAMES` couvre déjà ; ici l'identifiant est orphelin —
    # voir X10-DIV-0016 — et ecCodes ne le connaît pas du tout.
    3100: "sea_surface_wave_significant_height",
}

AMBIGUOUS_TRIPLETS: frozenset[tuple[int, int, int]] = frozenset({(0, 3, 6), (10, 4, 7)})

#: Direction et force du vent. **Écartées au décodage** : elles se recalculent
#: exactement à partir des composantes, et la direction est une grandeur
#: circulaire dont toute moyenne, interpolation ou dispersion calculée comme un
#: scalaire est fausse. Les conserver invite l'erreur.
#:
#: L'API ciblée du producteur ne les expose d'ailleurs pas non plus, pas plus
#: que les données ouvertes de l'ECMWF — **pour le vent**. Leur flux de
#: vagues publie bien une direction, `mwd`, pour laquelle aucune composante
#: n'est diffusée : la règle ne s'y applique donc pas, et le cas reste
#: ouvert.
DERIVED_WIND: frozenset[tuple[int, int, int]] = frozenset({(0, 2, 0), (0, 2, 1)})


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


def format_identity(code: tuple[object, ...]) -> str:
    """Rend un identifiant lisible par un humain, édition comprise.

    `identity` préfixe l'édition pour qu'un triplet et un couple ne se
    confondent pas, mais `(2, 0, 16, 193)` ne dit rien à qui lit un compte
    rendu : le premier chiffre n'y ressemble pas à une édition. On écrit
    donc `GRIB2 (0, 16, 193)`, et `GRIB1 (128, 167)`.
    """
    if not code:
        return "?"
    edition, *reste = code
    valeurs = ", ".join(str(v) for v in reste)
    return f"GRIB{edition} ({valeurs})"


def param_id(variable: xr.DataArray) -> int | None:
    """Le `paramId` d'un champ décodé, ou `None` s'il n'identifie rien.

    Zéro est écarté : ecCodes l'emploie pour dire « non résolu », et deux
    champs inconnus le partageraient.
    """
    try:
        valeur = int(variable.attrs[ATTR_PARAM_ID])
    except (KeyError, TypeError, ValueError):
        return None
    return None if valeur == PARAM_ID_UNRESOLVED else valeur


def identity(variable: xr.DataArray) -> tuple[object, ...] | None:
    """L'identifiant d'un champ **dans son édition**, ou `None`.

    **Chaque édition identifie ses paramètres à sa façon, et il ne faut pas
    l'uniformiser.** L'édition 2 emploie le triplet `(discipline, catégorie,
    numéro)` ; l'édition 1 emploie `(table2Version, indicatorOfParameter)`.
    Aucune des deux ne porte les clés de l'autre.

    **Pourquoi pas `paramId`, qui vaut pourtant des deux côtés.** Parce qu'il
    vaut **zéro** sur un paramètre qu'ecCodes ne résout pas — mesuré sur deux
    champs de tables locales de Météo-France. S'en servir comme identité les
    confondrait, et c'est précisément la confusion que `dropped_fields`
    existe pour détecter. Le `paramId` sert au **nommage**, pas à l'identité.

    L'édition est préfixée pour qu'un triplet et un couple ne puissent pas
    se ressembler par accident.
    """
    code = triplet(variable)
    if code is not None:
        return (2, *code)
    try:
        return (
            1,
            int(variable.attrs[ATTR_TABLE2_VERSION]),
            int(variable.attrs[ATTR_INDICATOR]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def open_granule(source: Path, *, errors: str = "raise") -> tuple[xr.Dataset, ...]:
    """Ouvre un granule GRIB2 multi-messages.

    Un **granule** est l'unité téléchargeable d'une collection — un fichier
    porteur de plusieurs messages. Le terme vient de STAC, d'OGC API et de
    WIS 2.0 ; il évite les deux collisions de « paquet », avec le paquet
    Python et avec le format GeoPackage. Voir [docs/vocabulaire.md].

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

    **Le même paramètre gouverne une seconde perte**, de même nature et
    d'origine différente : deux paramètres qu'ecCodes ne résout pas reçoivent
    tous deux le nom `unknown`, et l'un écrase l'autre dans le jeu. Voir
    `champs_perdus`. L'appelant n'a ainsi qu'un seul réglage de tolérance à
    connaître.
    """
    datasets: list[xr.Dataset] = _cfgrib().open_datasets(
        str(source),
        backend_kwargs={
            **OPTIONS_CFGRIB,
            "read_keys": [*READ_KEYS, *GEO_KEYS],
            "errors": errors,
            "values_dtype": _numpy().dtype(VALUES_DTYPE),
        },
    )
    granule = tuple(datasets)

    # Un champ qui disparaît n'est pas une métadonnée dégradée : c'est de la
    # donnée en moins. Même faute que le `errors="warn"` de `cfgrib`, et même
    # réponse — on la traite donc sous le **même paramètre**, pour que
    # l'appelant n'ait qu'un seul réglage de tolérance à connaître.
    if dropped := dropped_fields(source, granule):
        detail = ", ".join(format_identity(code) for code in sorted(dropped))
        message = (
            f"{len(dropped)} parameter(s) of the granule do not appear in the "
            f"decoded output: {detail}. Two parameters sharing a short name "
            "overlap within a dataset, and the second overwrites the first."
        )
        if errors == "raise":
            raise DroppedFieldsError(message)
        if errors != "ignore":
            _log.warning(message, extra={"x10.granule": str(source)})

    # Le référentiel de tables vit hors de notre code et change sans nous.
    # Une seule fois par granule : la version est une propriété du fichier,
    # pas de chacun de ses hypercubes.
    if (gap := check_tables_version(granule)) is not None:
        versions = tables_version(granule)
        _log.warning(
            gap,
            extra={
                "x10.granule": str(source),
                "x10.tables_version_declaree": versions[0] if versions else None,
                "x10.tables_version_connue": versions[1] if versions else None,
            },
        )

    # Même raison, même portée : la déclaration de tables locales est une
    # propriété du fichier. L'écart est un invariant du format, indépendant
    # du producteur.
    if (gap := check_local_tables(granule)) is not None:
        _log.warning(gap, extra={"x10.granule": str(source)})

    return granule


def tables_version(datasets: tuple[xr.Dataset, ...]) -> tuple[int, int] | None:
    """Version de tables **déclarée** par le producteur, et version **connue**.

    La seconde n'est pas un réglage : les définitions d'ecCodes sont
    **compilées dans la roue** — `codes_definition_path()` rend
    `/MEMFS/definitions` —, de sorte que la version des tables maîtresses est
    une propriété de la version du paquet installé.

    Renvoie `None` si le granule ne porte pas les deux clés. On retient la
    version déclarée **la plus haute** et la version connue **la plus basse**,
    ce qui est le choix prudent quand un granule n'est pas homogène.
    """
    declarees = {
        int(value)
        for dataset in datasets
        for var in dataset.data_vars.values()
        if isinstance(value := var.attrs.get(ATTR_TABLES_VERSION), (int, float))
    }
    connues = {
        int(value)
        for dataset in datasets
        for var in dataset.data_vars.values()
        if isinstance(value := var.attrs.get(ATTR_TABLES_LATEST), (int, float))
    }
    if not declarees or not connues:
        return None
    return max(declarees), min(connues)


def check_tables_version(datasets: tuple[xr.Dataset, ...]) -> str | None:
    """Signale que le producteur emploie des tables que nous ne connaissons pas.

    **Le second silence de la chaîne.** Mesuré le 09/10/2026 : demander à
    ecCodes une version de tables supérieure à celle qu'il connaît **ne lève
    rien**. La valeur est acceptée, relue telle quelle, et les paramètres non
    résolus sortent en `unknown` — sans avertissement.

    Ce qui nous protège aujourd'hui est accidentel : une unité `unknown`
    heurte la table UDUNITS fermée de `netcdf_cf`, qui lève. Le garde-fou est à
    trois étapes de là et n'a pas été conçu pour cela. **Et il ne couvre pas
    le cas dangereux** — un paramètre qui existe déjà dans la version connue
    mais dont une version ultérieure change la définition se résoudrait
    silencieusement, avec une unité valide et un sens faux. Le contrat de
    sortie ne le verrait pas davantage : la forme n'aurait pas bougé.

    Renvoie le message d'écart, ou `None` quand il n'y a rien à signaler.
    **Ne lève pas** : une table plus récente n'est pas une panne, la plupart
    des paramètres continuent de se résoudre. C'est un signal pour
    l'exploitant, pas un refus de servir.
    """
    versions = tables_version(datasets)
    if versions is None:
        return None
    declared, known = versions
    if declared <= known:
        return None
    return (
        f"The producer declares tables version {declared}, beyond version "
        f"{known} known to our ecCodes. Parameters introduced since will "
        "come out as 'unknown'; those whose definition changed will be "
        "resolved against the older one, with nothing to signal it."
    )


def file_triplets(source: Path) -> frozenset[tuple[int, int, int]]:
    """Les identifiants GRIB présents dans un granule, lus **sans le décoder**.

    Seuls les en-têtes sont parcourus : la section de données n'est jamais
    décompressée, de sorte que le coût reste négligeable même sur un granule
    de plusieurs centaines de mébioctets.

    **Un message illisible est passé, pas remonté.** Ce relevé sert à dire ce
    que le fichier contient ; d'un message qu'on ne sait pas lire, on ne peut
    rien affirmer, et prétendre le contraire accuserait le décodage d'une
    perte dont il n'est pas responsable. La lisibilité des messages relève du
    paramètre `errors` de `open_granule`, qui s'en charge en amont.
    """
    eccodes = _eccodes()
    seen: set[tuple[int, int, int]] = set()
    with source.open("rb") as flux:
        while True:
            position = flux.tell()
            try:
                h = eccodes.codes_grib_new_from_file(flux)
            except Exception:  # message illisible : voir la note du docstring
                # Sans progression dans le fichier, la boucle ne finirait pas.
                if flux.tell() == position:
                    break
                continue
            if h is None:
                break
            try:
                try:
                    seen.add(
                        (
                            int(eccodes.codes_get(h, "discipline")),
                            int(eccodes.codes_get(h, "parameterCategory")),
                            int(eccodes.codes_get(h, "parameterNumber")),
                        )
                    )
                except Exception:
                    # **Un message d'édition 1 n'a pas de triplet, et ce
                    # n'est pas une anomalie.** Sans cette garde, ecCodes
                    # lève `KeyValueNotFoundError` et l'exception remontait
                    # jusqu'à `open_granule` : c'était l'unique raison pour
                    # laquelle la chaîne ne lisait pas l'édition 1, alors que
                    # `cfgrib` l'ouvre sans difficulté. Mesuré le 20/10/2026.
                    #
                    # Rendre les triplets **réellement présents** est la
                    # bonne réponse : un fichier d'édition 1 n'en a aucun, et
                    # cette fonction dit ce que le fichier contient. La perte
                    # de champs, elle, se détecte par `file_identities`.
                    continue
            finally:
                eccodes.codes_release(h)
    return frozenset(seen)


def file_identities(source: Path) -> frozenset[tuple[object, ...]]:
    """Les identifiants d'un granule, **dans l'édition de chaque message**.

    Même parcours que `file_triplets`, et même prudence sur les messages
    illisibles — mais l'identité suit l'édition, de sorte qu'un granule
    d'édition 1 n'est pas vu comme vide.

    C'est ce relevé, et non celui des triplets, que `dropped_fields`
    confronte au décodage.
    """
    eccodes = _eccodes()
    seen: set[tuple[object, ...]] = set()
    with source.open("rb") as flux:
        while True:
            position = flux.tell()
            try:
                h = eccodes.codes_grib_new_from_file(flux)
            except Exception:
                if flux.tell() == position:
                    break
                continue
            if h is None:
                break
            try:
                for cles, prefixe in (
                    (("discipline", "parameterCategory", "parameterNumber"), 2),
                    (("table2Version", "indicatorOfParameter"), 1),
                ):
                    try:
                        seen.add((prefixe, *(int(eccodes.codes_get(h, c)) for c in cles)))
                    except Exception:
                        continue
                    break
            finally:
                eccodes.codes_release(h)
    return frozenset(seen)


def dropped_fields(source: Path, datasets: tuple[xr.Dataset, ...]) -> frozenset[tuple[object, ...]]:
    """Identifiants présents dans le fichier et absents du décodage.

    **Le troisième silence de la chaîne, mesuré le 13/10/2026.** `cfgrib`
    nomme ses variables d'après le nom court qu'ecCodes résout. Deux
    paramètres portant **le même nom court** se recouvrent donc dans un jeu,
    et le second écrase le premier : quatre messages entrent, un champ sort.
    Sans exception, sans avertissement, et le compte rendu dirait `success`.

    Deux familles de recouvrement, et la seconde surprend.

    Les codes qu'ecCodes **ne résout pas** reçoivent tous `unknown`. Ce n'est
    pas un cas d'école : `(0, 6, 11)` et `(0, 17, 4)`, du paquet SP3 d'ARPEGE
    0,25°, ne sont résolus ni par ecCodes ni par la table du producteur.

    Mais des codes **parfaitement résolus** se recouvrent aussi. Relevé sur
    365 codes des disciplines 0 et 10 : **cinq noms courts** désignent
    plusieurs triplets — dont `h` pour `(0, 3, 6)` et `(0, 3, 34)`, et `tmax`
    pour une température maximale `(0, 0, 4)` et une période de houle
    `(10, 0, 23)`. Le recouvrement n'est donc pas réservé aux codes exotiques.

    Ni `errors="raise"` ni `compat="equals"` n'y voient quoi que ce soit : le
    premier porte sur les messages illisibles, le second sur la fusion de
    jeux. La perte se produit **à l'intérieur** d'un jeu, au nommage.
    """
    decodes = {
        code
        for dataset in datasets
        for var in dataset.data_vars.values()
        if (code := identity(var)) is not None
    }
    return frozenset(file_identities(source) - decodes)


def check_local_tables(datasets: tuple[xr.Dataset, ...]) -> str | None:
    """Signale un paramètre de la plage locale sur un fichier qui n'en déclare aucune.

    **Un invariant du format, pas un cas connu.** La section 1 donne à son
    octet 11 la valeur zéro pour dire que les tables locales ne sont pas
    employées, et que seules les entrées des tables maîtresses *hors* plage
    réservée à l'usage local sont valides. Un code de cette plage dans un tel
    fichier est donc une contradiction interne au message : il n'existe aucune
    table où aller le lire.

    Le contrôle ne connaît aucun producteur et n'en nomme aucun. C'est ce qui
    lui permet de rendre la main sur une source que nous n'avons jamais vue.

    Mesuré le 12/10/2026 sur 863 messages d'AROME 0,025° : quarante-deux
    messages portent `(0, 16, 192)` alors que tous déclarent une version de
    tables locales nulle. ecCodes rend alors `shortName`, `name` **et**
    `units` à `unknown`. Le producteur publie bien la définition — `RFLCTVT` —
    mais hors du mécanisme que le format prévoit pour la désigner.

    Renvoie le message d'écart, ou `None`. **Ne lève pas** : le fichier reste
    exploitable pour tous ses autres champs, et c'est au contrat de sortie,
    non à ce contrôle, de refuser une donnée.
    """
    offenders: dict[tuple[int, int, int], str] = {}
    for dataset in datasets:
        for name, var in dataset.data_vars.items():
            local_tables = var.attrs.get(ATTR_LOCAL_TABLES)
            if not isinstance(local_tables, (int, float)) or int(local_tables) != 0:
                continue
            code = triplet(var)
            if code is None or max(code) < LOCAL_USE_RANGE_START:
                continue
            offenders.setdefault(code, str(name))
    if not offenders:
        return None
    detail = ", ".join(f"{code} ({name})" for code, name in sorted(offenders.items()))
    return (
        "The granule declares it uses no local table, yet carries "
        f"{len(offenders)} parameter(s) from the local-use range: "
        f"{detail}. No table allows interpreting them; their name and "
        "their unit will stay undetermined."
    )


#: Noms CF des grandeurs que nous **calculons** au lieu de les décoder, avec
#: l'unité que nous leur donnons. Ce sont des noms CF émis au même titre que
#: ceux de `CF_STANDARD_NAMES`, et ils étaient écrits en dur dans les deux
#: fonctions ci-dessous — donc invisibles du contrôle qui confronte nos noms
#: au tableau officiel. Les réunir ici les y rend visibles, et un test
#: interdit désormais qu'un nom CF réapparaisse en dur ailleurs.
CF_DERIVED: dict[str, str] = {
    "wind_speed": "m s-1",
    "wind_from_direction": "degree",
}


def wind_speed(u: xr.DataArray, v: xr.DataArray) -> xr.DataArray:
    """Force du vent, norme du vecteur."""
    np = _numpy()
    out: xr.DataArray = np.hypot(u, v)
    nom = "wind_speed"
    out.attrs = {"standard_name": nom, "units": CF_DERIVED[nom]}
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
    nom = "wind_from_direction"
    out.attrs = {"standard_name": nom, "units": CF_DERIVED[nom]}
    out.name = "wdir"
    return out


def drop_derived_wind(dataset: xr.Dataset) -> xr.Dataset:
    """Retire direction et force du vent, qui se recalculent des composantes."""
    a_retirer = [
        str(name) for name, var in dataset.data_vars.items() if triplet(var) in DERIVED_WIND
    ]
    return dataset.drop_vars(a_retirer) if a_retirer else dataset


#: Valeur de remplissage que la chaîne de décodage pose quand elle ne connaît
#: pas le nom standard. Elle est **pire qu'une absence** : un consommateur qui
#: lit `standard_name` y voit un nom, et un fichier la portant se dit conforme
#: aux conventions CF sans l'être.
PLACEHOLDER_CF = "unknown"


def _usable_cf_name(value: object) -> str | None:
    return value if isinstance(value, str) and value and value != PLACEHOLDER_CF else None


@functools.cache
def cf_name_for_param_id(identifiant: int) -> str | None:
    """Le nom CF qu'ecCodes associe à un `paramId`, **hors ligne**.

    **L'asymétrie que cette fonction contourne est mesurée**, et elle vaut
    d'être connue. Sur un message d'édition 1, ecCodes rend
    `cfName = unknown` ; le **même** `paramId` posé sur un échantillon
    d'édition 2 rend le nom. Vérifié le 20/10/2026 sur les échantillons que
    la roue embarque :

    ```
    GRIB1, paramId 167  →  cfName unknown
    GRIB2, paramId 167  →  cfName air_temperature
    ```

    L'information est donc déjà là ; elle n'est simplement pas exposée. Ce
    second passage explique à lui seul **six des quatorze** champs non nommés
    du diagnostic d'édition 1, et il ne coûte ni réseau ni service — voir
    `X10-DIV-0017` au registre des écarts.

    **Un `paramId` inconnu lève chez ecCodes** plutôt que de rendre une
    valeur : `ConceptNoMatchError`, dont le message renvoie à la base de
    paramètres d'ECMWF. On rend `None`, un champ sans nom devant se voir
    comme tel.

    Le résultat est mis en cache : la table de concepts ne change pas en
    cours d'exécution, et un granule répète les mêmes identifiants.
    """
    # **Un identifiant que nous avons déjà tranché n'est pas redemandé.**
    # Ce n'est pas une préséance de notre table sur ecCodes : c'est qu'un
    # `paramId` qu'il ne connaît pas le fait **écrire sur la sortie
    # d'erreur** — quatre lignes pour 3100 — avant de lever. Une
    # bibliothèque n'a pas à polluer la sortie de l'application qui
    # l'intègre, et nous ne pouvons pas l'en empêcher ; nous pouvons
    # seulement ne pas la provoquer pour rien.
    if identifiant in CF_BY_PARAM_ID:
        return None
    eccodes = _eccodes()
    handle = eccodes.codes_grib_new_from_samples("GRIB2")
    try:
        eccodes.codes_set(handle, "paramId", identifiant)
        nom = eccodes.codes_get(handle, "cfName")
    except Exception:
        return None
    finally:
        eccodes.codes_release(handle)
    return _usable_cf_name(nom)


def _our_cf_name(variable: xr.DataArray) -> str | None:
    """Le nom de **notre** table, si le gabarit ne l'interdit pas.

    Un triplet inscrit à `TEMPLATE_RESTRICTED` n'est nommé que sous les
    gabarits qui y figurent. Un gabarit absent de l'attribut — clé non lue,
    message d'une autre provenance — est traité comme non conforme : mieux
    vaut un champ sans nom qu'un champ mal nommé.
    """
    code = triplet(variable)
    if code is None or (nom := CF_STANDARD_NAMES.get(code)) is None:
        return None
    if (admis := TEMPLATE_RESTRICTED.get(code)) is None:
        return nom
    try:
        gabarit = int(variable.attrs["GRIB_productDefinitionTemplateNumber"])
    except (KeyError, TypeError, ValueError):
        return None
    return nom if gabarit in admis else None


def _our_cf_name_by_param_id(variable: xr.DataArray) -> str | None:
    """Le nom de notre table indexée par `paramId`, pour les derniers trous."""
    identifiant = param_id(variable)
    return None if identifiant is None else CF_BY_PARAM_ID.get(identifiant)


def apply_cf_names(dataset: xr.Dataset) -> xr.Dataset:
    """Pose `standard_name` sur les champs que notre table couvre.

    **Quatre voies, dans cet ordre, et l'ordre est le sujet.**

    1. Un nom déjà posé et utilisable est conservé.
    2. Sinon celui que la chaîne de décodage a résolu, `GRIB_cfName`.
    3. Sinon le **second passage par `paramId`** : ecCodes connaît le nom
       mais ne l'expose pas en édition 1, et ce détour le récupère sans
       réseau. Il vient avant nos tables parce qu'il vient d'ecCodes, dont
       nous ne faisons que combler les trous.
    4. Sinon les nôtres — par triplet d'abord, le plus précis puisqu'il
       distingue les gabarits, puis par `paramId` pour ce qu'aucune des
       autres voies n'atteint.

    Quand aucune ne donne de nom, **l'attribut est retiré** plutôt que laissé
    à sa valeur de remplissage — un champ sans nom standard doit se voir
    comme tel.
    """
    out = dataset.copy()
    for name, var in out.data_vars.items():
        existing = _usable_cf_name(var.attrs.get("standard_name"))
        if existing:
            continue
        identifiant = param_id(var)
        chosen = (
            _usable_cf_name(var.attrs.get("GRIB_cfName"))
            or (cf_name_for_param_id(identifiant) if identifiant is not None else None)
            or _our_cf_name(var)
            or _our_cf_name_by_param_id(var)
        )
        if chosen:
            out[name].attrs["standard_name"] = chosen
        else:
            out[name].attrs.pop("standard_name", None)
    return out


def normalise(dataset: xr.Dataset) -> xr.Dataset:
    """Écarte le vent dérivé, puis pose les noms standards CF."""
    return apply_cf_names(drop_derived_wind(dataset))


__all__ = [
    "AMBIGUOUS_TRIPLETS",
    "ATTR_EDITION",
    "ATTR_INDICATOR",
    "ATTR_LOCAL_TABLES",
    "ATTR_PARAM_ID",
    "ATTR_TABLE2_VERSION",
    "ATTR_TABLES_LATEST",
    "ATTR_TABLES_VERSION",
    "CF_BY_PARAM_ID",
    "CF_DERIVED",
    "CF_STANDARD_NAMES",
    "COORD_UNDEFINED",
    "DERIVED_WIND",
    "GEO_KEYS",
    "LOCAL_USE_RANGE_START",
    "OPTIONS_CFGRIB",
    "PARAM_ID_UNRESOLVED",
    "PLACEHOLDER_CF",
    "READ_KEYS",
    "TEMPLATE_RESTRICTED",
    "VALUES_DTYPE",
    "WITHOUT_CF_NAME",
    "DroppedFieldsError",
    "GribUnavailableError",
    "apply_cf_names",
    "cf_name_for_param_id",
    "check_local_tables",
    "check_tables_version",
    "drop_derived_wind",
    "dropped_fields",
    "file_identities",
    "file_triplets",
    "format_identity",
    "identity",
    "normalise",
    "open_granule",
    "param_id",
    "tables_version",
    "triplet",
    "wind_from_direction",
    "wind_speed",
]
