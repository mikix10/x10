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
    WITHOUT_VERTICAL_REFERENCE,
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
