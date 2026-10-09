"""Le producteur peut employer des tables que notre outillage ignore.

Le second silence de la chaîne, et le plus discret. Mesuré le 09/10/2026 :
demander à ecCodes une version de tables supérieure à celle qu'il connaît
**ne lève rien**. La valeur est acceptée, relue telle quelle, et les
paramètres non résolus sortent en `unknown`.

Ce qui nous protège aujourd'hui est accidentel — une unité `unknown` heurte
la table UDUNITS fermée, trois étapes plus loin — et **ne couvre pas le cas
dangereux** : un paramètre dont une table ultérieure change la définition se
résoudrait avec une unité valide et un sens faux. Le contrat de sortie ne le
verrait pas : la forme n'aurait pas bougé.
"""

from __future__ import annotations

import logging

import pytest
from fixtures_grib import Champ, paquet

decoding = pytest.importorskip("x10_connectors.decoding")

#: Ce que notre roue ecCodes sait résoudre. Relevé, non supposé : la valeur
#: dépend de la version installée, pas d'un réglage.
CONNUE_ATTENDUE = 37


# --- Le constat qui justifie tout le reste -----------------------------------


def test_eccodes_accepte_sans_broncher_une_version_qu_il_ignore(tmp_path):
    """Le cœur du sujet. Si ecCodes levait, ce module n'aurait pas lieu d'être."""
    eccodes = pytest.importorskip("eccodes")
    h = eccodes.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    try:
        connue = eccodes.codes_get(h, "tablesVersionLatest")
        eccodes.codes_set(h, "tablesVersion", connue + 10)
        assert eccodes.codes_get(h, "tablesVersion") == connue + 10, (
            "la version est acceptée et relue telle quelle — aucun refus"
        )
    finally:
        eccodes.codes_release(h)


def test_la_version_connue_est_celle_de_la_roue_installee(tmp_path):
    """Elle n'est pas configurable : les définitions sont compilées dans la roue."""
    chemin = paquet(tmp_path / "granule.grib2", [Champ(category=0, number=0)])
    versions = decoding.tables_version(decoding.open_granule(chemin))
    assert versions is not None
    _, connue = versions
    assert connue == CONNUE_ATTENDUE, (
        "une montée d'ecCodes a changé la version connue — mettre à jour la "
        "constante, et vérifier ce que les producteurs déclarent"
    )


# --- Le signalement ----------------------------------------------------------


def test_un_producteur_a_jour_ne_declenche_rien(tmp_path):
    chemin = paquet(tmp_path / "granule.grib2", [Champ(category=0, number=0, tables=30)])
    assert decoding.check_tables_version(decoding.open_granule(chemin)) is None


def test_une_version_egale_a_la_notre_ne_declenche_rien(tmp_path):
    """La borne est inclusive : connaître la version 37 suffit à la lire."""
    chemin = paquet(
        tmp_path / "granule.grib2", [Champ(category=0, number=0, tables=CONNUE_ATTENDUE)]
    )
    assert decoding.check_tables_version(decoding.open_granule(chemin)) is None


def test_une_version_en_avance_est_signalee(tmp_path):
    chemin = paquet(
        tmp_path / "granule.grib2", [Champ(category=0, number=0, tables=CONNUE_ATTENDUE + 3)]
    )
    ecart = decoding.check_tables_version(decoding.open_granule(chemin))
    assert ecart is not None
    assert str(CONNUE_ATTENDUE + 3) in ecart
    assert str(CONNUE_ATTENDUE) in ecart


def test_le_message_nomme_le_cas_dangereux(tmp_path):
    """Un paramètre absent se voit ; un paramètre **redéfini**, non. Le message
    doit dire les deux, sans quoi on croira n'avoir affaire qu'au premier."""
    chemin = paquet(
        tmp_path / "granule.grib2", [Champ(category=0, number=0, tables=CONNUE_ATTENDUE + 1)]
    )
    ecart = decoding.check_tables_version(decoding.open_granule(chemin))
    assert ecart is not None
    assert "unknown" in ecart
    assert "définition a changé" in ecart


def test_les_deux_versions_sont_rendues(tmp_path):
    chemin = paquet(
        tmp_path / "granule.grib2", [Champ(category=0, number=0, tables=CONNUE_ATTENDUE + 2)]
    )
    assert decoding.tables_version(decoding.open_granule(chemin)) == (
        CONNUE_ATTENDUE + 2,
        CONNUE_ATTENDUE,
    )


def test_un_granule_sans_les_cles_ne_prononce_rien(tmp_path):
    """Pas d'information n'est pas une alerte. On se tait plutôt que de supposer."""
    import xarray as xr

    jeu = xr.Dataset({"t": ("x", [1.0])}, coords={"x": [0]})
    assert decoding.tables_version((jeu,)) is None
    assert decoding.check_tables_version((jeu,)) is None


def test_la_version_la_plus_haute_du_granule_est_retenue(tmp_path):
    """Un granule hétérogène existe ; le choix prudent est la plus avancée."""
    chemin = paquet(
        tmp_path / "granule.grib2",
        [
            Champ(category=0, number=0, tables=CONNUE_ATTENDUE),
            Champ(category=1, number=1, tables=CONNUE_ATTENDUE + 5),
        ],
    )
    versions = decoding.tables_version(decoding.open_granule(chemin))
    assert versions is not None
    assert versions[0] == CONNUE_ATTENDUE + 5


# --- Le signal sort du processus ---------------------------------------------


def test_l_ouverture_journalise_l_ecart(tmp_path, caplog):
    """Un indicateur qui ne sort pas du processus ne sert à personne."""
    chemin = paquet(
        tmp_path / "granule.grib2", [Champ(category=0, number=0, tables=CONNUE_ATTENDUE + 4)]
    )
    with caplog.at_level(logging.WARNING, logger="x10_connectors.decoding"):
        decoding.open_granule(chemin)

    assert len(caplog.records) == 1, "une seule alerte par granule, non par hypercube"
    enregistre = caplog.records[0]
    assert enregistre.levelno == logging.WARNING
    assert getattr(enregistre, "x10.tables_version_declaree") == CONNUE_ATTENDUE + 4
    assert getattr(enregistre, "x10.tables_version_connue") == CONNUE_ATTENDUE


def test_l_ouverture_reste_muette_quand_il_n_y_a_rien_a_dire(tmp_path, caplog):
    chemin = paquet(tmp_path / "granule.grib2", [Champ(category=0, number=0)])
    with caplog.at_level(logging.WARNING, logger="x10_connectors.decoding"):
        decoding.open_granule(chemin)
    assert caplog.records == []


def test_l_ecart_ne_leve_pas(tmp_path):
    """Une table plus récente n'est pas une panne : la plupart des paramètres
    continuent de se résoudre. C'est un signal pour l'exploitant, pas un refus
    de servir — et le décodage doit rendre ses jeux."""
    chemin = paquet(
        tmp_path / "granule.grib2", [Champ(category=0, number=0, tables=CONNUE_ATTENDUE + 9)]
    )
    assert len(decoding.open_granule(chemin)) >= 1


# --- Service reel ------------------------------------------------------------


@pytest.mark.network
def test_le_producteur_reel_est_dans_ce_que_nous_savons_lire(tmp_path):
    """La mesure, et pas seulement le garde-fou.

    Nous ne savions pas quelle version de tables les producteurs emploient
    réellement. Ce test l'établit, et échouera le jour où l'un d'eux prendra
    de l'avance sur notre roue — ce qui est précisément l'événement que
    `VEILLE-2` doit voir venir.

    Il consigne la valeur relevée dans son message d'échec, de sorte qu'une
    rupture renseigne au lieu de simplement interdire.
    """
    from x10_connectors import MeteoFrancePntConnector, MeteoFrancePntRequest

    resultat = MeteoFrancePntConnector(
        tmp_path,
        MeteoFrancePntRequest(model="arome", grid="0025", paquets=("SP1",), tranches=("00H06H",)),
    ).fetch()
    assert resultat.retrieval is not None

    granule = decoding.open_granule(resultat.retrieval.artefacts[0])
    versions = decoding.tables_version(granule)
    assert versions is not None, "le producteur ne déclare pas sa version de tables"

    declaree, connue = versions
    assert declaree <= connue, (
        f"Le producteur est passé à la version de tables {declaree}, au-delà de "
        f"la {connue} que connaît notre ecCodes. Monter la dépendance, puis "
        "vérifier que les noms CF et les unités n'ont pas bougé."
    )
