"""La configuration lue de l'environnement, et ce qu'elle refuse de deviner.

Rien ici ne touche au GRIB ni au NetCDF : ces tests n'ont besoin d'aucun
extra et tournent partout.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from x10_client import ConfigurationManquante, Session, Settings
from x10_client.config import ETAT_PAR_DEFAUT


def test_une_destination_absente_leve_au_lieu_de_choisir():
    """Retenir un défaut enverrait des fichiers quelque part d'inattendu,
    et le client n'a aucune raison de savoir mieux que son utilisateur."""
    with pytest.raises(ConfigurationManquante, match="X10_DESTINATION"):
        Settings.from_env({})


def test_une_destination_vide_vaut_une_absence():
    with pytest.raises(ConfigurationManquante):
        Settings.from_env({"X10_DESTINATION": "   "})


def test_l_etat_se_pose_sous_la_destination_par_defaut(tmp_path):
    reglages = Settings.from_env({"X10_DESTINATION": str(tmp_path)})
    assert reglages.etat == tmp_path.resolve() / ETAT_PAR_DEFAUT
    assert reglages.max_bytes is None


def test_l_etat_peut_vivre_ailleurs_que_sous_la_destination(tmp_path):
    """Un carnet écrit ses sorties dans un dossier qu'il vide, et n'a aucune
    envie d'y perdre l'historique dont se déduit la disponibilité."""
    reglages = Settings.from_env(
        {"X10_DESTINATION": str(tmp_path / "sortie"), "X10_ETAT": str(tmp_path / "trace")}
    )
    assert reglages.etat == (tmp_path / "trace").resolve()


def test_les_chemins_sont_resolus_et_le_tilde_etendu(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    reglages = Settings.from_env({"X10_DESTINATION": "~/ici"})
    assert reglages.destination.is_absolute()
    assert reglages.destination.name == "ici"


def test_un_plafond_nul_leve_plutot_que_de_tout_interdire():
    """Zéro n'autoriserait aucun téléchargement : c'est une erreur de saisie,
    pas une intention. Le dire vaut mieux que ne rien rapporter."""
    with pytest.raises(ConfigurationManquante, match="n'autoriserait"):
        Settings.from_env({"X10_DESTINATION": "/tmp/x", "X10_MAX_BYTES": "0"})


def test_un_plafond_absent_laisse_celui_du_connecteur():
    """Le connecteur en a un. En imposer un second ici en ferait deux, dont
    le plus bas déciderait sans qu'on sache lequel."""
    assert Settings.from_env({"X10_DESTINATION": "/tmp/x"}).max_bytes is None


def test_un_plafond_explicite_est_repris_tel_quel():
    reglages = Settings.from_env({"X10_DESTINATION": "/tmp/x", "X10_MAX_BYTES": "268435456"})
    assert reglages.max_bytes == 268_435_456


def test_les_reglages_ne_se_modifient_pas_apres_coup(tmp_path):
    """Une session dont la destination change en cours de route écrirait la
    moitié de ses fichiers ailleurs."""
    reglages = Settings.from_env({"X10_DESTINATION": str(tmp_path)})
    with pytest.raises(FrozenInstanceError):
        reglages.destination = tmp_path / "autre"  # type: ignore[misc]


def test_une_session_se_construit_depuis_l_environnement_reel(tmp_path, monkeypatch):
    monkeypatch.setenv("X10_DESTINATION", str(tmp_path))
    assert Session.from_env().settings.destination == tmp_path.resolve()
