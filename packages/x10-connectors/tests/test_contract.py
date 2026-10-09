"""Tests du contrat de sortie.

Le contrat fige la forme et les métadonnées d'un paquet décodé. Comparé à une
référence versionnée, il signale une dérive du producteur — ou une régression
de notre code, selon le côté d'où vient l'écart.

Les références sont du **texte trié**, relu en revue : c'est leur seule
qualité sur un fichier binaire, et elle décide de l'utilité de l'exercice.
Régénération par `X10_REGENERATE_REFERENCES=1`, le mainteneur relisant
ensuite le `git diff`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fixtures_grib import Champ, champs_vent, paquet

from x10_connectors.contract import (
    COORDS_EXCLUES,
    SEUIL_ENUMERATION,
    AxeCaracterise,
    Contract,
    compare_contracts,
    output_contract,
)
from x10_connectors.decoding import GribIndisponible, normalise, open_granule

REFERENCES = Path(__file__).parent / "references"


def _contrat(source: Path) -> Contract:
    return output_contract(tuple(normalise(j) for j in open_granule(source)))


def _reference(nom: str, contrat: Contract) -> Contract:
    """Relit une référence versionnée, ou la régénère sur demande explicite."""
    cible = REFERENCES / f"{nom}.json"
    if os.environ.get("X10_REGENERATE_REFERENCES"):
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(contrat.json_stable() + "\n", encoding="utf-8")
        pytest.skip(f"référence régénérée : {cible.name}")
    if not cible.exists():
        pytest.fail(
            f"Référence absente : {cible}. La produire avec "
            "X10_REGENERATE_REFERENCES=1, puis relire le diff."
        )
    return Contract.model_validate_json(cible.read_text(encoding="utf-8"))


def _paquet_type(tmp_path: Path) -> Path:
    """Un paquet mêlant vent, cumul et niveaux — proche d'un fichier réel."""
    champs = [
        *champs_vent(steps=(0, 1)),
        Champ(category=0, number=0, level_type=103, level=2, step=0),
        Champ(category=1, number=8, accumulation=1, step=1),
    ]
    return paquet(tmp_path / "type.grib2", champs)


# --- Construction ---------------------------------------------------------------


def test_le_contrat_est_deterministe(tmp_path):
    """Deux exécutions sur la même entrée donnent le même texte, octet pour
    octet. Sans cela un diff montrerait du bruit, et personne ne le relirait."""
    source = _paquet_type(tmp_path)
    assert _contrat(source).json_stable() == _contrat(source).json_stable()


def test_la_date_de_reseau_est_exclue(tmp_path):
    """Elle change à chaque exécution **légitimement**. La figer produirait
    une rupture à chaque nouveau réseau, donc un indicateur qu'on désactive."""
    contrat = _contrat(_paquet_type(tmp_path))
    for variable in contrat.variables.values():
        assert not (set(variable.coords) & COORDS_EXCLUES)


def test_les_echeances_restent_au_contrat(tmp_path):
    """À l'inverse : un décalage relatif est stable pour une tranche donnée,
    et son évolution — passage de l'horaire au tri-horaire — est une dérive."""
    contrat = _contrat(_paquet_type(tmp_path))
    assert all("step" in v.coords for v in contrat.variables.values())


def test_les_echeances_sont_lisibles_en_secondes(tmp_path):
    """`numpy` range `timedelta64` parmi les entiers signés : sans traitement
    explicite les échéances resteraient en nanosecondes, illisibles."""
    contrat = _contrat(_paquet_type(tmp_path))
    assert contrat.variables["u"].coords["step"] == (0.0, 3600.0)


def test_la_grande_coordonnee_est_caracterisee_et_la_petite_enumeree(tmp_path):
    """Figer un millier de latitudes ôterait au contrat sa seule qualité sur
    un fichier binaire : être relu."""
    grille = {"ni": SEUIL_ENUMERATION + 10, "nj": 3, "di": 0.1, "dj": 0.1}
    source = paquet(tmp_path / "large.grib2", [Champ(category=0, number=0)], grille)
    contrat = _contrat(source)
    assert isinstance(contrat.geometry.grille["longitude"], AxeCaracterise)
    assert contrat.geometry.grille["longitude"].taille == SEUIL_ENUMERATION + 10
    assert "latitude" not in contrat.geometry.grille  # 3 points : énumérée


def test_l_unite_est_celle_que_la_sortie_declare(tmp_path):
    """Le contrat décrit ce qu'un consommateur lit, pas ce que le GRIB
    portait : l'unité y figure canonicalisée."""
    contrat = _contrat(_paquet_type(tmp_path))
    assert contrat.variables["u"].units == "m s-1"


def test_l_identite_grib_accompagne_chaque_variable(tmp_path):
    """C'est ce qui rend la localisation du fautif gratuite : une divergence
    nomme la variable **et** désigne les messages responsables."""
    grib = _contrat(_paquet_type(tmp_path)).variables["u"].grib
    assert grib["parameterCategory"] == "2"
    assert grib["stepType"] == "instant"


def test_un_paquet_vide_est_refuse(tmp_path):
    with pytest.raises(GribIndisponible):
        output_contract(())


# --- Comparaison ----------------------------------------------------------------


def test_deux_contrats_identiques_ne_divergent_pas(tmp_path):
    contrat = _contrat(_paquet_type(tmp_path))
    ecarts = compare_contracts(contrat, contrat)
    assert not ecarts
    assert ecarts.resume() == "aucun écart"


def test_une_variable_disparue_est_une_rupture(tmp_path):
    avant = _contrat(_paquet_type(tmp_path))
    apres = avant.model_copy(
        update={"variables": {k: v for k, v in avant.variables.items() if k != "u"}}
    )
    ecarts = compare_contracts(avant, apres)
    assert ecarts
    assert any(d.chemin == "variables.u" for d in ecarts.ruptures)


@pytest.mark.parametrize(
    ("champ", "valeur"),
    [
        ("units", "parsecs"),
        ("standard_name", "autre_chose"),
        ("cell_methods", "time: sum"),
        ("dims", ("latitude", "longitude")),
        ("dtype", "float64"),
    ],
)
def test_un_attribut_critique_modifie_est_une_rupture(tmp_path, champ, valeur):
    avant = _contrat(_paquet_type(tmp_path))
    modifiee = avant.variables["u"].model_copy(update={champ: valeur})
    apres = avant.model_copy(update={"variables": {**avant.variables, "u": modifiee}})
    ecarts = compare_contracts(avant, apres)
    assert ecarts, f"{champ} modifié devrait être une rupture"
    assert any(d.chemin == f"variables.u.{champ}" for d in ecarts.ruptures)


def test_une_grille_deplacee_a_taille_constante_est_une_rupture(tmp_path):
    """Le cas qu'une simple comparaison de tailles laisserait passer."""
    grille = {"ni": SEUIL_ENUMERATION + 10, "nj": 3, "di": 0.1, "dj": 0.1}
    avant = _contrat(paquet(tmp_path / "a.grib2", [Champ(category=0, number=0)], grille))
    apres = _contrat(
        paquet(tmp_path / "b.grib2", [Champ(category=0, number=0)], {**grille, "lon1": 300.0})
    )
    ecarts = compare_contracts(avant, apres)
    assert ecarts
    assert any(d.chemin == "geometry.grille" for d in ecarts.ruptures)


def test_une_variable_apparue_est_une_nouveaute_sans_echec(tmp_path):
    """Un indicateur qui s'allume à chaque ajout est désactivé au bout de
    trois fois."""
    avant = _contrat(_paquet_type(tmp_path))
    ajoutee = avant.variables["u"].model_copy()
    apres = avant.model_copy(update={"variables": {**avant.variables, "nouveau": ajoutee}})
    ecarts = compare_contracts(avant, apres)
    assert not ecarts, "une nouveauté ne doit pas faire échouer"
    assert any(d.chemin == "variables.nouveau" for d in ecarts.nouveautes)
    assert "nouveauté" in ecarts.resume()


def test_un_libelle_modifie_est_signale_sans_echec(tmp_path):
    avant = _contrat(_paquet_type(tmp_path))
    modifiee = avant.variables["u"].model_copy(update={"long_name": "autre libellé"})
    apres = avant.model_copy(update={"variables": {**avant.variables, "u": modifiee}})
    ecarts = compare_contracts(avant, apres)
    assert not ecarts
    assert any(d.chemin == "variables.u.long_name" for d in ecarts.nouveautes)


# --- Référence versionnée -------------------------------------------------------


def test_la_chaine_reproduit_sa_reference(tmp_path):
    """Garde-fou hors ligne : détecte une régression **de notre code**.

    La référence est construite sur des fixtures, donc sans réseau ni donnée
    réelle. Elle fige ce que la chaîne produit aujourd'hui ; toute évolution
    volontaire se relit dans le diff au lieu de passer inaperçue.
    """
    observe = _contrat(_paquet_type(tmp_path))
    ecarts = compare_contracts(_reference("fixtures-surface", observe), observe)
    assert not ecarts, ecarts.resume()


def test_la_reference_versionnee_est_relisible():
    """Elle doit rester du texte trié, de taille raisonnable."""
    brut = (REFERENCES / "fixtures-surface.json").read_text(encoding="utf-8")
    assert json.loads(brut)["variables"], "référence vide"
    assert len(brut.encode()) < 64 * 1024, "référence trop volumineuse pour une revue"


# --- Service reel ---------------------------------------------------------------


@pytest.mark.network
def test_le_paquet_reel_reproduit_sa_reference(tmp_path):
    """L'indicateur de derive proprement dit.

    Un ecart signale que le producteur a change quelque chose : un champ
    retire, une unite modifiee, une grille redefinie. Les fixtures ne peuvent
    pas le detecter, puisqu'elles ne produisent que ce qu'on leur demande.
    """
    from x10_connectors import MeteoFrancePntConnector, MeteoFrancePntRequest

    resultat = MeteoFrancePntConnector(
        tmp_path,
        MeteoFrancePntRequest(model="arome", grid="0025", paquets=("SP1",), tranches=("00H06H",)),
    ).fetch()
    assert resultat.retrieval is not None

    observe = _contrat(resultat.retrieval.artefacts[0])
    ecarts = compare_contracts(_reference("meteofrance-arome-0025-SP1", observe), observe)
    assert not ecarts, ecarts.resume()
