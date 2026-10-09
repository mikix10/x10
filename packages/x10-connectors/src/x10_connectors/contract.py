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

from .decoding import GribIndisponible, _numpy
from .output import cell_method, grid_mapping, udunits

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
SEUIL_ENUMERATION = 64

#: Clés GRIB retenues pour identifier un champ chez le producteur. C'est ce
#: qui rend la localisation du fautif gratuite : une divergence sur une
#: variable désigne du même coup les messages concernés.
IDENTITE_GRIB = (
    "discipline",
    "parameterCategory",
    "parameterNumber",
    "typeOfLevel",
    "stepType",
)

#: Attributs dont une évolution est une **rupture**. Les autres écarts sont
#: des nouveautés, signalées sans faire échouer : un indicateur qui crie à
#: chaque ajout est désactivé au bout de trois fois.
ATTRIBUTS_CRITIQUES = ("dims", "dtype", "units", "standard_name", "cell_methods")

#: Attributs dont une évolution est **signalée sans échec**.
ATTRIBUTS_INFORMATIFS = ("long_name", "grib", "coords")

#: Coordonnées **exclues du contrat** parce qu'elles changent légitimement à
#: chaque exécution. `time` porte la date de réseau et `valid_time` en
#: dérive ; les figer produirait une rupture à chaque nouveau réseau, donc un
#: indicateur qu'on désactive au bout de deux jours.
#:
#: `step` reste au contrat : c'est un décalage relatif, stable pour une
#: tranche donnée, et son évolution — un passage de l'horaire au tri-horaire,
#: par exemple — est précisément une dérive à détecter.
COORDS_EXCLUES = frozenset({"time", "valid_time"})


class AxeCaracterise(BaseModel):
    """Coordonnée trop longue pour être énumérée.

    Quatre nombres et une empreinte au lieu d'un millier de valeurs, sans
    angle mort : un changement de résolution, d'emprise ou de sens de parcours
    modifie l'un des quatre ; toute autre altération modifie l'empreinte.
    """

    model_config = ConfigDict(frozen=True)

    taille: int = Field(ge=0)
    premier: float
    dernier: float
    pas: float | None = None
    empreinte: str


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

    grille: dict[str, AxeCaracterise] = Field(default_factory=dict)
    referentiel: dict[str, str] | None = None
    #: Nombre de jeux rendus par la chaîne de décodage pour ce granule. Informatif : un
    #: changement signale une réorganisation sans dire laquelle.
    jeux: int = Field(default=0, ge=0)


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

    categorie: Literal["rupture", "nouveaute"]
    chemin: str
    reference: str | None = None
    observe: str | None = None

    def __str__(self) -> str:
        return f"{self.chemin} : {self.reference!r} -> {self.observe!r}"


class Divergences(BaseModel):
    """Résultat d'une comparaison, **classé** plutôt que binaire.

    `__bool__` ne vaut `True` qu'en présence d'une rupture : une nouveauté se
    signale sans faire échouer. C'est ce qui décide du succès de l'outil — un
    indicateur qui s'allume à chaque évolution bénigne finit désactivé.
    """

    model_config = ConfigDict(frozen=True)

    ruptures: tuple[Divergence, ...] = ()
    nouveautes: tuple[Divergence, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.ruptures)

    def resume(self) -> str:
        if not self.ruptures and not self.nouveautes:
            return "aucun écart"
        return "\n".join(
            [f"RUPTURE   {d}" for d in self.ruptures] + [f"nouveauté {d}" for d in self.nouveautes]
        )


def _coordonnee(valeurs: object) -> AxeCaracterise | tuple[float, ...]:
    """Énumère une coordonnée courte, caractérise une longue."""
    np = _numpy()
    brut = np.atleast_1d(np.asarray(valeurs))
    # **Piège** : `numpy` range `timedelta64` parmi les entiers signés, donc
    # `issubdtype(..., number)` le laisse passer et les échéances resteraient
    # en nanosecondes — 18000000000000 pour cinq heures, illisible en revue.
    # Le genre de dtype est le seul test fiable.
    if brut.dtype.kind in "mM":
        brut = brut.astype("datetime64[s]" if brut.dtype.kind == "M" else "timedelta64[s]")
        brut = brut.astype("int64")
    elif not np.issubdtype(brut.dtype, np.number):
        brut = brut.astype("int64")
    arrondi = np.round(brut.astype("float64"), PRECISION)
    if arrondi.size <= SEUIL_ENUMERATION:
        return tuple(float(x) for x in arrondi)
    return AxeCaracterise(
        taille=int(arrondi.size),
        premier=float(arrondi[0]),
        dernier=float(arrondi[-1]),
        pas=float(round(float(arrondi[1] - arrondi[0]), PRECISION)) if arrondi.size > 1 else None,
        empreinte=hashlib.sha256(arrondi.tobytes()).hexdigest()[:16],
    )


def output_contract(jeux: tuple[xr.Dataset, ...]) -> Contract:
    """Construit le contrat d'un granule décodé et normalisé.

    Prend le tuple rendu par `open_granule`, chaque jeu passé par `normalise`.
    Le contrat est bâti **avant écriture** : c'est là que se voit une dérive
    du producteur, l'écriture ayant ses propres tests.
    """
    if not jeux:
        raise GribIndisponible("Aucun jeu à contractualiser.")

    variables: dict[str, VariableContract] = {}
    grille: dict[str, AxeCaracterise] = {}
    referentiel: dict[str, str] | None = None

    for jeu in jeux:
        if referentiel is None and (gm := grid_mapping(jeu)) is not None:
            referentiel = {cle: str(valeur) for cle, valeur in sorted(gm.items())}
        for nom, var in jeu.data_vars.items():
            coords: dict[str, tuple[float, ...]] = {}
            for axe in var.dims:
                if str(axe) not in jeu.coords or str(axe) in COORDS_EXCLUES:
                    continue
                decrit = _coordonnee(jeu.coords[axe].values)
                if isinstance(decrit, AxeCaracterise):
                    grille.setdefault(str(axe), decrit)
                else:
                    coords[str(axe)] = decrit
            variables[str(nom)] = VariableContract(
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
                    cle: str(var.attrs[f"GRIB_{cle}"])
                    for cle in IDENTITE_GRIB
                    if f"GRIB_{cle}" in var.attrs
                },
                coords=coords,
            )

    return Contract(
        variables=dict(sorted(variables.items())),
        geometry=GeometryContract(
            grille=dict(sorted(grille.items())),
            referentiel=referentiel,
            jeux=len(jeux),
        ),
    )


def _ecart(
    categorie: Literal["rupture", "nouveaute"], chemin: str, a: object, b: object
) -> Divergence:
    return Divergence(categorie=categorie, chemin=chemin, reference=str(a), observe=str(b))


def compare_contracts(reference: Contract, observe: Contract) -> Divergences:
    """Compare deux contrats, en **classant** les écarts.

    Une variable disparue, une unité, une dimension ou une grille modifiées
    sont des **ruptures**. Une variable, un libellé ou une échéance qui
    s'ajoutent sont des **nouveautés**, signalées sans faire échouer.
    """
    ruptures: list[Divergence] = []
    nouveautes: list[Divergence] = []

    for nom in sorted(set(reference.variables) - set(observe.variables)):
        ruptures.append(_ecart("rupture", f"variables.{nom}", "présente", "absente"))
    for nom in sorted(set(observe.variables) - set(reference.variables)):
        nouveautes.append(_ecart("nouveaute", f"variables.{nom}", "absente", "apparue"))

    for nom in sorted(set(reference.variables) & set(observe.variables)):
        avant, apres = reference.variables[nom], observe.variables[nom]
        for champ in ATTRIBUTS_CRITIQUES:
            if (a := getattr(avant, champ)) != (b := getattr(apres, champ)):
                ruptures.append(_ecart("rupture", f"variables.{nom}.{champ}", a, b))
        for champ in ATTRIBUTS_INFORMATIFS:
            if (a := getattr(avant, champ)) != (b := getattr(apres, champ)):
                nouveautes.append(_ecart("nouveaute", f"variables.{nom}.{champ}", a, b))

    if reference.geometry.grille != observe.geometry.grille:
        ruptures.append(
            _ecart("rupture", "geometry.grille", reference.geometry.grille, observe.geometry.grille)
        )
    if reference.geometry.referentiel != observe.geometry.referentiel:
        ruptures.append(
            _ecart(
                "rupture",
                "geometry.referentiel",
                reference.geometry.referentiel,
                observe.geometry.referentiel,
            )
        )
    if reference.geometry.jeux != observe.geometry.jeux:
        nouveautes.append(
            _ecart("nouveaute", "geometry.jeux", reference.geometry.jeux, observe.geometry.jeux)
        )

    return Divergences(ruptures=tuple(ruptures), nouveautes=tuple(nouveautes))


__all__ = [
    "ATTRIBUTS_CRITIQUES",
    "ATTRIBUTS_INFORMATIFS",
    "COORDS_EXCLUES",
    "IDENTITE_GRIB",
    "PRECISION",
    "SEUIL_ENUMERATION",
    "AxeCaracterise",
    "Contract",
    "Divergence",
    "Divergences",
    "GeometryContract",
    "VariableContract",
    "compare_contracts",
    "output_contract",
]
