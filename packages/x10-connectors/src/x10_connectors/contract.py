"""Contrat de sortie : ce que la chaîne est censée produire.

Un contrat fige **la forme et les métadonnées** d'un granule décodé, jamais ses
valeurs. Comparé à une référence versionnée, il devient un **indicateur de
dérive** : un champ retiré, une unité modifiée, une grille déplacée se voient
au lieu d'attendre la plainte d'un consommateur.

**Le niveau retenu est le granule** — l'unité téléchargeable — et un seul. Le message GRIB n'a
pas besoin d'être un niveau distinct : chaque entrée porte l'identité GRIB du
champ, donc une divergence nomme la variable *et* désigne les messages
responsables. La variable seule ne suffirait pas — comparer ce qu'on trouve ne
détecte pas ce qui a disparu. Et un assemblage de plusieurs granules n'est pas
contractable : il dépend de ce que l'appelant a demandé, pas de ce que le
producteur publie.

**L'indexation est par nom de variable**, ni par ordre de jeu — rien n'en
garantit la stabilité entre versions — ni par type de niveau : mesuré le
08/10/2026, deux jeux d'AROME SP1 partagent `heightAboveGround = 10` et ne se
distinguent que par leur axe temporel.

Dépendance optionnelle : installer l'extra `grib`.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from x10_models import SourceTerms, Variable

from .grib2 import GribUnavailableError, _numpy
from .netcdf_cf import cell_method, grid_mapping, udunits
from .observability import connector_logger

_log = connector_logger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    import xarray as xr

#: Nombre de décimales conservées avant de caractériser ou d'empreindre une
#: coordonnée. Six décimales de degré valent une dizaine de centimètres, très
#: en deçà de tout changement signifiant.
#:
#: **Sans cet arrondi le contrat serait inutilisable** : le pas relevé sur un
#: granule AROME réel sort à `-0.02499999999999858`, et une évolution de
#: `cfgrib` ou de `numpy` dans le calcul des coordonnées produirait une
#: rupture qui ne dirait rien du producteur.
PRECISION = 6

#: Au-delà de cette taille, une coordonnée est **caractérisée** plutôt
#: qu'énumérée. Figer les 717 latitudes et 1121 longitudes d'AROME rendrait la
#: référence illisible — ce qui lui ôterait sa seule qualité sur un fichier
#: binaire.
ENUMERATION_THRESHOLD = 64

#: Clés GRIB retenues pour identifier un champ chez le producteur. C'est ce
#: qui rend la localisation du fautif gratuite : une divergence sur une
#: variable désigne du même coup les messages concernés.
GRIB_IDENTITY = (
    "discipline",
    "parameterCategory",
    "parameterNumber",
    "typeOfLevel",
    "stepType",
    # **Le triplet ne suffit pas à identifier un champ**, et ce n'est pas une
    # précaution : mesuré le 19/10/2026 sur le flux de vagues d'ECMWF, sept
    # messages portent `(10, 0, 3)` et seul le gabarit les sépare.
    "productDefinitionTemplateNumber",
    # Taille de l'ensemble déclarée par le message. Elle est ici pour deux
    # raisons : elle discrimine un axe de membres réel, et son évolution --
    # cinquante membres devenus cent -- est une dérive du producteur que le
    # contrat doit montrer.
    "numberOfForecastsInEnsemble",
)

#: Attributs dont une évolution est une **rupture**. Les autres écarts sont
#: des nouveautés, signalées sans faire échouer : un indicateur qui crie à
#: chaque ajout est désactivé au bout de trois fois.
CRITICAL_ATTRIBUTES = ("dims", "dtype", "units", "standard_name", "cell_methods")

#: Attributs dont une évolution est **signalée sans échec**.
INFORMATIVE_ATTRIBUTES = ("long_name", "grib", "coords")

#: Coordonnées **exclues du contrat** parce qu'elles changent légitimement à
#: chaque exécution. `time` porte la date de réseau et `valid_time` en
#: dérive ; les figer produirait une rupture à chaque nouveau réseau, donc un
#: indicateur qu'on désactive au bout de deux jours.
#:
#: `step` reste au contrat : c'est un décalage relatif, stable pour une
#: tranche donnée, et son évolution — un passage de l'horaire au tri-horaire,
#: par exemple — est précisément une dérive à détecter.
EXCLUDED_COORDS = frozenset({"time", "valid_time"})


class AxisSummary(BaseModel):
    """Coordonnée trop longue pour être énumérée.

    Quatre nombres et une empreinte au lieu d'un millier de valeurs, sans
    angle mort : un changement de résolution, d'emprise ou de sens de parcours
    modifie l'un des quatre ; toute autre altération modifie l'empreinte.
    """

    model_config = ConfigDict(frozen=True)

    size: int = Field(ge=0)
    first: float
    last: float
    stride: float | None = None
    fingerprint: str


class VariableContract(BaseModel):
    """Ce qu'une variable déclare, hors valeurs."""

    model_config = ConfigDict(frozen=True)

    dims: tuple[str, ...]
    dtype: str
    units: str | None = None
    standard_name: str | None = None
    long_name: str | None = None
    cell_methods: str | None = None
    #: Identité du champ chez le producteur, voir `IDENTITE_GRIB`.
    grib: dict[str, str] = Field(default_factory=dict)
    #: Valeurs des coordonnées **propres à la variable** — échéances, niveaux,
    #: membres. Elles ne sont pas communes au granule : `heightAboveGround`
    #: vaut 10 dans un jeu d'AROME SP1 et 2 dans un autre.
    coords: dict[str, tuple[float, ...]] = Field(default_factory=dict)


class GeometryContract(BaseModel):
    """Ce qui est commun à tout un granule : la géométrie et le référentiel."""

    model_config = ConfigDict(frozen=True)

    grid: dict[str, AxisSummary] = Field(default_factory=dict)
    crs: dict[str, str] | None = None
    #: Nombre de jeux rendus par la chaîne de décodage pour ce granule. Informatif : un
    #: changement signale une réorganisation sans dire laquelle.
    datasets: int = Field(default=0, ge=0)


class Contract(BaseModel):
    """Contrat de sortie d'un granule."""

    model_config = ConfigDict(frozen=True)

    variables: dict[str, VariableContract] = Field(default_factory=dict)
    geometry: GeometryContract = Field(default_factory=GeometryContract)

    def json_stable(self) -> str:
        """Rendu déterministe, destiné à être versionné et relu en revue.

        Clés triées et indentation fixe : deux exécutions sur la même entrée
        donnent le même texte, octet pour octet, et un `git diff` ne montre
        que ce qui a réellement changé.
        """
        return json.dumps(
            self.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False
        )


class Divergence(BaseModel):
    """Un écart entre une référence et une observation."""

    model_config = ConfigDict(frozen=True)

    category: Literal["breaking", "addition"]
    path: str
    reference: str | None = None
    observed: str | None = None

    def __str__(self) -> str:
        return f"{self.path} : {self.reference!r} -> {self.observed!r}"


class Divergences(BaseModel):
    """Résultat d'une comparaison, **classé** plutôt que binaire.

    `__bool__` ne vaut `True` qu'en présence d'une rupture : une nouveauté se
    signale sans faire échouer. C'est ce qui décide du succès de l'outil — un
    indicateur qui s'allume à chaque évolution bénigne finit désactivé.
    """

    model_config = ConfigDict(frozen=True)

    breaking_changes: tuple[Divergence, ...] = ()
    additions: tuple[Divergence, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.breaking_changes)

    def resume(self) -> str:
        if not self.breaking_changes and not self.additions:
            return "no divergence"
        return "\n".join(
            [f"BREAKING {d}" for d in self.breaking_changes]
            + [f"addition {d}" for d in self.additions]
        )


def _coordinate(values: object) -> AxisSummary | tuple[float, ...]:
    """Énumère une coordonnée courte, caractérise une longue."""
    np = _numpy()
    raw = np.atleast_1d(np.asarray(values))
    # **Piège** : `numpy` range `timedelta64` parmi les entiers signés, donc
    # `issubdtype(..., number)` le laisse passer et les échéances resteraient
    # en nanosecondes — 18000000000000 pour cinq heures, illisible en revue.
    # Le genre de dtype est le seul test fiable.
    if raw.dtype.kind in "mM":
        raw = raw.astype("datetime64[s]" if raw.dtype.kind == "M" else "timedelta64[s]")
        raw = raw.astype("int64")
    elif not np.issubdtype(raw.dtype, np.number):
        raw = raw.astype("int64")
    rounded = np.round(raw.astype("float64"), PRECISION)
    if rounded.size <= ENUMERATION_THRESHOLD:
        return tuple(float(x) for x in rounded)
    return AxisSummary(
        size=int(rounded.size),
        first=float(rounded[0]),
        last=float(rounded[-1]),
        stride=float(round(float(rounded[1] - rounded[0]), PRECISION))
        if rounded.size > 1
        else None,
        fingerprint=hashlib.sha256(rounded.tobytes()).hexdigest()[:16],
    )


def output_contract(datasets: tuple[xr.Dataset, ...]) -> Contract:
    """Construit le contrat d'un granule décodé et normalisé.

    Prend le tuple rendu par `open_granule`, chaque jeu passé par `normalise`.
    Le contrat est bâti **avant écriture** : c'est là que se voit une dérive
    du producteur, l'écriture ayant ses propres tests.
    """
    if not datasets:
        raise GribUnavailableError("No dataset to build a contract from.")

    variables: dict[str, VariableContract] = {}
    grid: dict[str, AxisSummary] = {}
    crs: dict[str, str] | None = None

    for dataset in datasets:
        if crs is None and (gm := grid_mapping(dataset)) is not None:
            crs = {key: str(value) for key, value in sorted(gm.items())}
        for name, var in dataset.data_vars.items():
            coords: dict[str, tuple[float, ...]] = {}
            for axis in var.dims:
                if str(axis) not in dataset.coords or str(axis) in EXCLUDED_COORDS:
                    continue
                decrit = _coordinate(dataset.coords[axis].values)
                if isinstance(decrit, AxisSummary):
                    grid.setdefault(str(axis), decrit)
                else:
                    coords[str(axis)] = decrit
            variables[str(name)] = VariableContract(
                dims=tuple(str(d) for d in var.dims),
                dtype=str(var.dtype),
                # L'unité **telle que la sortie la déclare**, donc après
                # canonicalisation : le contrat décrit ce qu'un consommateur
                # lit, pas ce que le GRIB portait.
                units=udunits(var.attrs.get("units")),
                standard_name=var.attrs.get("standard_name"),
                long_name=var.attrs.get("long_name"),
                cell_methods=cell_method(var.attrs),
                grib={
                    key: str(var.attrs[f"GRIB_{key}"])
                    for key in GRIB_IDENTITY
                    if f"GRIB_{key}" in var.attrs
                },
                coords=coords,
            )

    return Contract(
        variables=dict(sorted(variables.items())),
        geometry=GeometryContract(
            grid=dict(sorted(grid.items())),
            crs=crs,
            datasets=len(datasets),
        ),
    )


def _divergence(
    category: Literal["breaking", "addition"], path: str, a: object, b: object
) -> Divergence:
    return Divergence(category=category, path=path, reference=str(a), observed=str(b))


def compare_contracts(reference: Contract, observed: Contract) -> Divergences:
    """Compare deux contrats, en **classant** les écarts.

    Une variable disparue, une unité, une dimension ou une grille modifiées
    sont des **ruptures**. Une variable, un libellé ou une échéance qui
    s'ajoutent sont des **nouveautés**, signalées sans faire échouer.
    """
    breaking_changes: list[Divergence] = []
    additions: list[Divergence] = []

    for name in sorted(set(reference.variables) - set(observed.variables)):
        breaking_changes.append(_divergence("breaking", f"variables.{name}", "present", "absent"))
    for name in sorted(set(observed.variables) - set(reference.variables)):
        additions.append(_divergence("addition", f"variables.{name}", "absent", "appeared"))

    for name in sorted(set(reference.variables) & set(observed.variables)):
        avant, apres = reference.variables[name], observed.variables[name]
        for attribute in CRITICAL_ATTRIBUTES:
            if (a := getattr(avant, attribute)) != (b := getattr(apres, attribute)):
                breaking_changes.append(
                    _divergence("breaking", f"variables.{name}.{attribute}", a, b)
                )
        for attribute in INFORMATIVE_ATTRIBUTES:
            if (a := getattr(avant, attribute)) != (b := getattr(apres, attribute)):
                additions.append(_divergence("addition", f"variables.{name}.{attribute}", a, b))

    if reference.geometry.grid != observed.geometry.grid:
        breaking_changes.append(
            _divergence(
                "breaking", "geometry.grid", reference.geometry.grid, observed.geometry.grid
            )
        )
    if reference.geometry.crs != observed.geometry.crs:
        breaking_changes.append(
            _divergence(
                "breaking",
                "geometry.crs",
                reference.geometry.crs,
                observed.geometry.crs,
            )
        )
    if reference.geometry.datasets != observed.geometry.datasets:
        additions.append(
            _divergence(
                "addition",
                "geometry.datasets",
                reference.geometry.datasets,
                observed.geometry.datasets,
            )
        )

    return Divergences(breaking_changes=tuple(breaking_changes), additions=tuple(additions))


# --- Inventaire : du contrat au catalogue -------------------------------------
#
# Le contrat porte déjà, par variable, le nom standard CF, l'unité canonique,
# la méthode de cellule, l'identité GRIB et les coordonnées propres. Dériver
# un inventaire de catalogue n'est donc pas une lecture de plus des fichiers :
# c'est une **traduction** de ce qui a déjà été lu.
#
# La frontière est celle du vocabulaire. `inventory` ne rend que du normalisé
# — ce que X10 expose et dont il répond. `source_terms` rend les termes du
# producteur, qui ne promettent **rien, par construction, puisqu'ils suivent
# le producteur**. Les deux sortent de la même passe parce que décoder est
# l'étape coûteuse, jamais du même objet parce que l'un engage et l'autre non.

#: `typeOfLevel` d'ecCodes vers la référence verticale **normalisée** : nom
#: standard CF, et unité des valeurs telles que le producteur les donne.
#:
#: Table **close**, chaque nom vérifié présent au tableau CF. Un type absent
#: d'ici ne produit **pas** de référence verticale plutôt qu'une supposition —
#: même règle que `grib2.CF_STANDARD_NAMES`, et même raison : un nom inventé
#: produit une métadonnée qui se dit normalisée sans l'être.
CF_VERTICAL: dict[str, tuple[str, str]] = {
    "heightAboveGround": ("height", "m"),
    "heightAboveSea": ("altitude", "m"),
    "isobaricInhPa": ("air_pressure", "hPa"),
    "depthBelowLandLayer": ("depth", "m"),
}

#: Types de niveau que CF ne décrit par **aucune coordonnée verticale**, et
#: c'est correct : un champ de surface n'en porte pas, la convention étant
#: son absence. Les recenser évite de les confondre avec un trou de table.
WITHOUT_VERTICAL_REFERENCE = frozenset(
    {
        "surface",
        "meanSea",
        "entireAtmosphere",
        "cloudBase",
        "cloudTop",
        "isothermZero",
        "nominalTop",
    }
)

#: Nom de la coordonnée d'échéance posée par la chaîne de décodage, en
#: **secondes**.
STEP_COORD = "step"

#: Nom que `cfgrib` donne à l'axe des membres d'un ensemble. CF l'appelle
#: `realization` ; la traduction se fait ici, et `Variable` n'expose que le
#: vocabulaire normalisé.
ENSEMBLE_COORD = "number"

#: Clé GRIB qui dit si l'axe des membres en est vraiment un.
#:
#: **La présence de l'axe ne suffit pas**, et c'est une correction. Mesuré le
#: 19/10/2026 sur trois gabarits : un déterministe `4.0` ne porte aucune de
#: ces clés ; un ensemble `4.1` déclare dix prévisions et un numéro de
#: perturbation ; et le gabarit `4.104` des hauteurs de vagues par bande de
#: période **remplit les octets d'ensemble de zéros**, de sorte que `number`
#: et `perturbationNumber` y valent 0 sur une prévision pourtant
#: déterministe. `cfgrib` en tire un axe `number` de longueur 1, et le
#: compte de membres valait 1 là où il doit valoir « aucun ».
#:
#: Le discriminant retenu est donc la taille déclarée, strictement positive.
#: Il ne suppose aucune liste de gabarits — énumérer ceux qui portent un
#: ensemble reviendrait à redériver une table de l'OMM de mémoire.
ENSEMBLE_SIZE = "numberOfForecastsInEnsemble"

SECONDS_PER_HOUR = 3600


def _declared_ensemble(entry: VariableContract) -> bool:
    """Le message déclare-t-il un ensemble de taille non nulle ?"""
    try:
        return int(entry.grib.get(ENSEMBLE_SIZE, "0")) > 0
    except ValueError:
        return False


def _realizations(entry: VariableContract, geometry: GeometryContract) -> int | None:
    """Le nombre de membres d'une grandeur, ou `None` si elle est déterministe.

    **Deux endroits à consulter, et c'est la raison d'être de cette
    fonction.** Une coordonnée courte est énumérée dans `coords`, une longue
    est caractérisée dans `geometry.grid` — le seuil est à
    `ENUMERATION_THRESHOLD`, soit 64. Les 50 membres d'ECMWF passent donc par
    le premier chemin, mais un producteur plus fourni basculerait dans le
    second, et ne lire que `coords` rendrait `None` précisément sur
    l'ensemble le plus volumineux.
    """
    if ENSEMBLE_COORD not in entry.dims or not _declared_ensemble(entry):
        return None
    if (enumerated := entry.coords.get(ENSEMBLE_COORD)) is not None:
        return len(enumerated)
    if (summarised := geometry.grid.get(ENSEMBLE_COORD)) is not None:
        return summarised.size
    # L'axe est dans les dimensions sans coordonnée associée : le nombre de
    # membres n'est pas lisible, et le supposer serait pire que l'ignorer.
    return None


def inventory(contract: Contract) -> tuple[Variable, ...]:
    """L'inventaire **normalisé** d'un granule, pour le catalogue.

    Ne rend que du vocabulaire que X10 engage : noms CF, unités UDUNITS,
    méthodes de cellule CF, référence verticale par son nom standard. Rien du
    producteur — c'est `source_terms` qui le porte.

    Une grandeur sans nom standard est **rendue quand même**, avec
    `standard_name=None`. CF ne couvre pas tout, et la règle arrêtée est
    retirer plutôt que renommer : sans cette soupape, un seul code exotique
    rendrait un granule entier inexposable.
    """
    variables = []
    for nom in sorted(contract.variables):
        fiche = contract.variables[nom]
        type_niveau = fiche.grib.get("typeOfLevel")
        reference, unite = _vertical(type_niveau)
        # Sans référence verticale, **pas de niveaux**. La chaîne de décodage
        # pose une coordonnée `surface = 0.0` sur les champs de surface ; la
        # rendre ici produirait un niveau sans référence ni unité, qu'une
        # facette ferait correspondre à tout champ de surface du catalogue.
        niveaux = fiche.coords.get(type_niveau or "", ()) if reference is not None else ()
        variables.append(
            Variable(
                standard_name=fiche.standard_name,
                units=fiche.units,
                cell_methods=fiche.cell_methods,
                level_reference=reference,
                levels=niveaux,
                level_units=unite if reference is not None else None,
                realizations=_realizations(fiche, contract.geometry),
            )
        )
    return tuple(variables)


def source_terms(contract: Contract) -> tuple[SourceTerms, ...]:
    """Les mêmes grandeurs **dans les termes du producteur**, même ordre.

    > Cette vue ne promet rien, par construction, puisqu'elle suit le
    > producteur. Si le nom court change chez lui, elle change ici.

    Rendue dans l'ordre d'`inventory`, de sorte que l'indice d'une grandeur
    désigne la même dans les deux vues.
    """
    termes = []
    for nom in sorted(contract.variables):
        fiche = contract.variables[nom]
        termes.append(
            SourceTerms(
                short_name=nom,
                level_type=fiche.grib.get("typeOfLevel"),
                grib=dict(fiche.grib),
            )
        )
    return tuple(termes)


def max_step_hours(contract: Contract) -> int | None:
    """Échéance maximale servie par le granule, en heures entières.

    C'est une **capacité** du jeu, pas une disponibilité : elle dit jusqu'où
    la source sait aller, jamais si un réseau donné est présent à l'instant
    où l'on demande. Cette seconde question se lit dans l'historique
    d'exécution.

    `None` quand aucune variable ne porte d'échéance — un champ constant, par
    exemple. Ne pas savoir n'est pas zéro.
    """
    echeances = [
        valeur
        for fiche in contract.variables.values()
        for valeur in fiche.coords.get(STEP_COORD, ())
    ]
    if not echeances:
        return None
    return int(max(echeances) // SECONDS_PER_HOUR)


def _vertical(type_niveau: str | None) -> tuple[str | None, str | None]:
    """Référence verticale normalisée, ou `None` quand il n'y en a pas."""
    if type_niveau is None or type_niveau in WITHOUT_VERTICAL_REFERENCE:
        return None, None
    if (connu := CF_VERTICAL.get(type_niveau)) is None:
        # Un type que nous n'avons pas rencontré. On ne devine pas : la
        # grandeur reste exposable, sans référence verticale, et l'absence
        # se voit.
        _log.warning(
            "Vertical level type without a known CF reference",
            extra={"x10.level_type": type_niveau},
        )
        return None, None
    return connu


__all__ = [
    "CF_VERTICAL",
    "CRITICAL_ATTRIBUTES",
    "ENSEMBLE_COORD",
    "ENSEMBLE_SIZE",
    "ENUMERATION_THRESHOLD",
    "EXCLUDED_COORDS",
    "GRIB_IDENTITY",
    "INFORMATIVE_ATTRIBUTES",
    "PRECISION",
    "SECONDS_PER_HOUR",
    "STEP_COORD",
    "WITHOUT_VERTICAL_REFERENCE",
    "AxisSummary",
    "Contract",
    "Divergence",
    "Divergences",
    "GeometryContract",
    "VariableContract",
    "compare_contracts",
    "inventory",
    "max_step_hours",
    "output_contract",
    "source_terms",
]
