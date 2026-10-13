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

from .grib2 import GribUnavailableError, _numpy
from .netcdf_cf import cell_method, grid_mapping, udunits

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
            return "aucun écart"
        return "\n".join(
            [f"RUPTURE   {d}" for d in self.breaking_changes]
            + [f"nouveauté {d}" for d in self.additions]
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
        raise GribUnavailableError("Aucun jeu à contractualiser.")

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
        breaking_changes.append(_divergence("breaking", f"variables.{name}", "présente", "absente"))
    for name in sorted(set(observed.variables) - set(reference.variables)):
        additions.append(_divergence("addition", f"variables.{name}", "absente", "apparue"))

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


__all__ = [
    "CRITICAL_ATTRIBUTES",
    "ENUMERATION_THRESHOLD",
    "EXCLUDED_COORDS",
    "GRIB_IDENTITY",
    "INFORMATIVE_ATTRIBUTES",
    "PRECISION",
    "AxisSummary",
    "Contract",
    "Divergence",
    "Divergences",
    "GeometryContract",
    "VariableContract",
    "compare_contracts",
    "output_contract",
]
