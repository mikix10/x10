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
            "La pile de décodage GRIB est absente. Installer l'extra : "
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
            "La pile de décodage GRIB est absente. Installer l'extra : "
            "uv sync --all-packages --extra grib"
        ) from exc
    module: ModuleType = eccodes
    return module


def _numpy() -> ModuleType:
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - depend de l'extra
        raise GribUnavailableError(
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
WITHOUT_CF_NAME: frozenset[tuple[int, int, int]] = frozenset(
    {
        (0, 19, 11),  # energie cinetique turbulente
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
AMBIGUOUS_TRIPLETS: frozenset[tuple[int, int, int]] = frozenset({(0, 3, 6)})

#: Direction et force du vent. **Écartées au décodage** : elles se recalculent
#: exactement à partir des composantes, et la direction est une grandeur
#: circulaire dont toute moyenne, interpolation ou dispersion calculée comme un
#: scalaire est fausse. Les conserver invite l'erreur.
#:
#: L'API ciblée du producteur ne les expose d'ailleurs pas non plus, pas plus
#: que les données ouvertes de l'ECMWF.
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
        detail = ", ".join(str(code) for code in sorted(dropped))
        message = (
            f"{len(dropped)} paramètre(s) du granule n'apparaissent pas au "
            f"décodage : {detail}. Deux paramètres portant le même nom court "
            "se recouvrent dans un jeu, et le second écrase le premier."
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
        f"Le producteur déclare la version de tables {declared}, au-delà de la "
        f"version {known} que connaît notre ecCodes. Les paramètres introduits "
        "depuis sortiront en 'unknown' ; ceux dont la définition a changé seront "
        "résolus contre l'ancienne, sans que rien ne le signale."
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
                seen.add(
                    (
                        int(eccodes.codes_get(h, "discipline")),
                        int(eccodes.codes_get(h, "parameterCategory")),
                        int(eccodes.codes_get(h, "parameterNumber")),
                    )
                )
            finally:
                eccodes.codes_release(h)
    return frozenset(seen)


def dropped_fields(
    source: Path, datasets: tuple[xr.Dataset, ...]
) -> frozenset[tuple[int, int, int]]:
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
        if (code := triplet(var)) is not None
    }
    return frozenset(file_triplets(source) - decodes)


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
        "Le granule déclare n'employer aucune table locale et porte pourtant "
        f"{len(offenders)} paramètre(s) de la plage réservée à l'usage local : "
        f"{detail}. Aucune table ne permet de les interpréter ; leur nom et "
        "leur unité resteront indéterminés."
    )


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


def apply_cf_names(dataset: xr.Dataset) -> xr.Dataset:
    """Pose `standard_name` sur les champs que notre table couvre.

    Trois cas, dans cet ordre : un nom déjà posé et utilisable est conservé ;
    sinon celui de la chaîne de décodage ; sinon le nôtre. Quand aucun des
    trois ne donne de nom, **l'attribut est retiré** plutôt que laissé à sa
    valeur de remplissage — un champ sans nom standard doit se voir comme tel.
    """
    out = dataset.copy()
    for name, var in out.data_vars.items():
        existing = _usable_cf_name(var.attrs.get("standard_name"))
        if existing:
            continue
        chosen = _usable_cf_name(var.attrs.get("GRIB_cfName")) or CF_STANDARD_NAMES.get(
            triplet(var) or (-1, -1, -1)
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
    "ATTR_LOCAL_TABLES",
    "ATTR_TABLES_LATEST",
    "ATTR_TABLES_VERSION",
    "CF_STANDARD_NAMES",
    "COORD_UNDEFINED",
    "DERIVED_WIND",
    "GEO_KEYS",
    "LOCAL_USE_RANGE_START",
    "OPTIONS_CFGRIB",
    "PLACEHOLDER_CF",
    "READ_KEYS",
    "VALUES_DTYPE",
    "WITHOUT_CF_NAME",
    "DroppedFieldsError",
    "GribUnavailableError",
    "apply_cf_names",
    "check_local_tables",
    "check_tables_version",
    "drop_derived_wind",
    "dropped_fields",
    "file_triplets",
    "normalise",
    "open_granule",
    "tables_version",
    "triplet",
    "wind_from_direction",
    "wind_speed",
]
