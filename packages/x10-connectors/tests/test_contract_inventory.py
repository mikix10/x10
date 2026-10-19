"""Dérivation GRIB2 → inventaire de catalogue, et la frontière des deux vues.

Le contrat de sortie porte déjà le nom standard CF, l'unité canonique, la
méthode de cellule et l'identité GRIB. Dériver un inventaire n'est donc pas
une lecture de plus : c'est une **traduction**.

Ce que ces tests tiennent avant tout : **aucun terme de producteur ni
d'ecCodes dans la vue normalisée**. C'est elle que X10 expose et dont il
répond ; `SourceTerms` porte le reste, et ne promet rien.
"""

from __future__ import annotations

import pytest
from fixtures_grib2 import Field, granule

from x10_connectors.contract import (
    CF_VERTICAL,
    ENSEMBLE_COORD,
    ENSEMBLE_SIZE,
    WITHOUT_VERTICAL_REFERENCE,
    AxisSummary,
    Contract,
    GeometryContract,
    VariableContract,
    inventory,
    max_step_hours,
    output_contract,
    source_terms,
)
from x10_connectors.grib2 import normalise, open_granule

pytest.importorskip("cfgrib")


def _contrat(chemin):
    jeux = open_granule(chemin)
    return output_contract(tuple(normalise(j) for j in jeux))


@pytest.fixture
def surface(tmp_path):
    """Un granule à niveau de hauteur : le cas le plus courant."""
    chemin = granule(tmp_path / "surface.grib2", [Field(category=0, number=0, level=2)])
    return _contrat(chemin)


# --- La frontière des deux vues -----------------------------------------------


def test_la_vue_normalisee_ne_porte_aucun_terme_d_eccodes(surface):
    """Le test qui tient la règle.

    Un consommateur qui s'accroche à `heightAboveGround` ou à `2t` hérite de
    notre couplage au producteur. La vue normalisée existe pour qu'il n'ait
    pas à le faire.
    """
    interdits = set(WITHOUT_VERTICAL_REFERENCE) | set(CF_VERTICAL)
    for variable in inventory(surface):
        rendu = variable.model_dump_json()
        for terme in interdits:
            assert terme not in rendu, f"{terme} ne doit pas figurer dans la vue normalisée"


def test_la_vue_source_porte_le_nom_court_du_producteur(surface):
    termes = source_terms(surface)
    assert termes
    assert all(t.short_name for t in termes)


def test_les_deux_vues_sont_dans_le_meme_ordre(surface):
    """L'indice d'une grandeur désigne la même dans les deux vues ; sans
    cela, rapprocher l'une de l'autre serait faux."""
    assert len(inventory(surface)) == len(source_terms(surface))


def test_la_reference_verticale_est_un_nom_standard_cf(surface):
    """`heightAboveGround` d'ecCodes devient `height` de CF."""
    references = {v.level_reference for v in inventory(surface) if v.level_reference}
    assert references <= {nom for nom, _ in CF_VERTICAL.values()}


def test_le_type_de_niveau_d_eccodes_reste_du_cote_source(surface):
    types = {t.level_type for t in source_terms(surface) if t.level_type}
    assert types <= set(CF_VERTICAL) | WITHOUT_VERTICAL_REFERENCE


# --- Ce que la dérivation refuse de deviner -----------------------------------


def test_un_champ_de_surface_ne_porte_aucun_niveau(tmp_path):
    """La chaîne de décodage pose une coordonnée `surface = 0.0`. La rendre
    produirait un niveau sans référence ni unité, qu'une facette ferait
    correspondre à tout champ de surface du catalogue."""
    # `level_type=1` est la surface, table 4.5 du format.
    chemin = granule(tmp_path / "sol.grib2", [Field(category=0, number=0, level_type=1, level=0)])
    for variable in inventory(_contrat(chemin)):
        if variable.level_reference is None:
            assert variable.levels == ()
            assert variable.level_units is None


def test_un_type_de_niveau_inconnu_ne_produit_pas_de_reference(surface, monkeypatch):
    """On ne devine pas : la grandeur reste exposable, sans référence, et
    l'absence se voit."""
    import x10_connectors.contract as module

    monkeypatch.setattr(module, "CF_VERTICAL", {})
    monkeypatch.setattr(module, "WITHOUT_VERTICAL_REFERENCE", frozenset())
    for variable in inventory(surface):
        assert variable.level_reference is None
        assert variable.levels == ()


def test_une_grandeur_sans_nom_standard_reste_exposee(tmp_path):
    """La soupape : sans elle, un seul code exotique rendrait un granule
    entier inexposable."""
    chemin = granule(tmp_path / "local.grib2", [Field(category=16, number=192)])
    variables = inventory(_contrat(chemin))
    assert variables
    assert variables[0].standard_name is None


# --- L'échéance est une capacité, pas une disponibilité -----------------------


def test_l_echeance_maximale_se_lit_en_heures(tmp_path):
    chemin = granule(
        tmp_path / "echeances.grib2",
        [Field(category=0, number=0, step=0), Field(category=0, number=0, step=6)],
    )
    assert max_step_hours(_contrat(chemin)) == 6


def test_sans_echeance_la_capacite_est_inconnue_et_non_nulle(surface, monkeypatch):
    """Ne pas savoir n'est pas zéro — un champ constant n'a pas d'échéance."""
    nu = surface.model_copy(
        update={
            "variables": {
                nom: fiche.model_copy(update={"coords": {}})
                for nom, fiche in surface.variables.items()
            }
        }
    )
    assert max_step_hours(nu) is None


# --- Reproductibilité ---------------------------------------------------------


def test_la_derivation_est_reproductible(surface):
    """Rejouée sur le même contrat, elle rend exactement la même chose —
    c'est ce qui permet de commiter le résultat et d'en lire le `git diff`."""
    assert inventory(surface) == inventory(surface)
    assert source_terms(surface) == source_terms(surface)


# --- L'axe des membres --------------------------------------------------------


def test_un_ensemble_porte_son_nombre_de_membres(tmp_path):
    """CF appelle `realization` cet axe ; le compte suffit au catalogue."""
    chemin = granule(
        tmp_path / "ensemble.grib2",
        [Field(category=0, number=0, level=2, member=m, members=3) for m in (1, 2, 3)],
    )

    variables = inventory(_contrat(chemin))

    assert {v.realizations for v in variables} == {3}


def test_un_champ_deterministe_n_a_pas_d_axe_de_membres(surface):
    """`None` et non zéro : un déterministe n'a pas un membre, il n'en a pas."""
    assert all(v.realizations is None for v in inventory(surface))


def test_un_ensemble_plus_grand_que_le_seuil_se_lit_dans_la_geometrie():
    """Au-delà de 64 valeurs, l'axe est caractérisé et non plus énuméré.

    ECMWF en sert cinquante, donc aucune donnée réelle n'atteint ce chemin ;
    un producteur plus fourni y tomberait, et ne lire que les coordonnées
    rendrait `None` précisément sur l'ensemble le plus volumineux.
    """
    contrat = Contract(
        variables={
            "t2m": VariableContract(
                dims=(ENSEMBLE_COORD, "latitude", "longitude"),
                dtype="float32",
                units="K",
                standard_name="air_temperature",
                grib={"typeOfLevel": "heightAboveGround", ENSEMBLE_SIZE: "100"},
                coords={},
            )
        },
        geometry=GeometryContract(
            grid={
                ENSEMBLE_COORD: AxisSummary(
                    size=100, first=1.0, last=100.0, stride=1.0, fingerprint="x"
                )
            },
            crs=None,
            datasets=1,
        ),
    )

    assert inventory(contrat)[0].realizations == 100


def test_un_axe_de_membres_sans_coordonnee_ne_se_devine_pas():
    """Le supposer serait pire que l'ignorer : le compte serait faux."""
    contrat = Contract(
        variables={
            "t2m": VariableContract(
                dims=(ENSEMBLE_COORD,),
                dtype="float32",
                grib={"typeOfLevel": "heightAboveGround", ENSEMBLE_SIZE: "8"},
                coords={},
            )
        },
        geometry=GeometryContract(grid={}, crs=None, datasets=1),
    )

    assert inventory(contrat)[0].realizations is None


def _un_axe_de_membres(taille_declaree: str | None) -> Contract:
    """Un contrat portant l'axe `number`, avec ou sans ensemble déclaré."""
    grib = {"typeOfLevel": "surface"}
    if taille_declaree is not None:
        grib[ENSEMBLE_SIZE] = taille_declaree
    return Contract(
        variables={
            "x": VariableContract(
                dims=(ENSEMBLE_COORD, "latitude"),
                dtype="float32",
                grib=grib,
                coords={ENSEMBLE_COORD: (0.0,)},
            )
        },
        geometry=GeometryContract(grid={}, crs=None, datasets=1),
    )


def test_un_axe_de_membres_sans_ensemble_declare_n_en_est_pas_un():
    """Mesuré le 19/10/2026 sur le gabarit 4.104 des hauteurs de vagues.

    Ce gabarit remplit les octets d'ensemble de zéros, de sorte que `number`
    et `perturbationNumber` y valent 0 sur une prévision pourtant
    déterministe. `cfgrib` en tire un axe `number` de longueur 1, et le
    compte de membres valait 1 là où il doit valoir « aucun ». La présence de
    l'axe ne suffit donc pas : c'est la taille déclarée qui tranche.
    """
    assert inventory(_un_axe_de_membres("0"))[0].realizations is None
    assert inventory(_un_axe_de_membres(None))[0].realizations is None
    assert inventory(_un_axe_de_membres("10"))[0].realizations == 1


def test_une_taille_d_ensemble_illisible_ne_compte_pour_aucun_membre():
    """Une valeur qu'on ne sait pas lire ne se devine pas dans un sens."""
    assert inventory(_un_axe_de_membres("beaucoup"))[0].realizations is None
