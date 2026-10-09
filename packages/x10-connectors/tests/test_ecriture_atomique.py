"""Rien n'apparaît sous son nom définitif avant d'être complet.

Le défaut que ces tests ferment est silencieux : un processus interrompu en
cours de transfert laissait un fichier partiel que *rien ne distinguait* d'un
fichier entier. La reprise le trouvait, le croyait bon, et l'erreur ressortait
trois étapes plus loin — ou jamais, sur une donnée tronquée qui se décode.

On vérifie donc trois choses à chaque étage de la chaîne : la cible n'existe
pas tant que l'écriture n'est pas finie, un échec ne laisse **aucun** résidu,
et un échec **ne détruit pas** la version précédente.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from x10_connectors import (
    AucunFichierProduit,
    EcmwfIfsError,
    EcmwfIfsOpenDataConnector,
    EcmwfIfsRequest,
    MeteoFrancePntError,
    ecriture_atomique,
)
from x10_connectors.base import SUFFIXE_PARTIEL


class _PanneSimulee(RuntimeError):
    """Interruption en cours d'écriture — délai dépassé, conteneur évincé."""


def _residus(dossier: Path) -> list[Path]:
    """Tout ce qui traîne, fichiers masqués compris."""
    return sorted(p for p in dossier.iterdir() if p.is_file())


# --- Le mécanisme ------------------------------------------------------------


def test_la_cible_n_apparait_qu_une_fois_l_ecriture_finie(tmp_path):
    cible = tmp_path / "granule.grib2"
    with ecriture_atomique(cible) as provisoire:
        provisoire.write_bytes(b"GRIB7777")
        assert not cible.exists(), "la cible ne doit pas exister avant la fin du bloc"
    assert cible.read_bytes() == b"GRIB7777"
    assert _residus(tmp_path) == [cible]


def test_un_echec_ne_laisse_ni_cible_ni_residu(tmp_path):
    cible = tmp_path / "granule.grib2"
    with pytest.raises(_PanneSimulee), ecriture_atomique(cible) as provisoire:
        provisoire.write_bytes(b"GRI")  # transfert interrompu
        raise _PanneSimulee
    assert not cible.exists()
    assert _residus(tmp_path) == []


def test_un_echec_preserve_la_version_precedente(tmp_path):
    """Une acquisition ratée ne doit pas détruire la précédente, qui était bonne."""
    cible = tmp_path / "granule.grib2"
    cible.write_bytes(b"ancien mais valide")
    with pytest.raises(_PanneSimulee), ecriture_atomique(cible) as provisoire:
        provisoire.write_bytes(b"nouveau, incomplet")
        raise _PanneSimulee
    assert cible.read_bytes() == b"ancien mais valide"
    assert _residus(tmp_path) == [cible]


def test_une_ecriture_reussie_remplace_la_version_precedente(tmp_path):
    cible = tmp_path / "granule.grib2"
    cible.write_bytes(b"ancien")
    with ecriture_atomique(cible) as provisoire:
        provisoire.write_bytes(b"nouveau")
    assert cible.read_bytes() == b"nouveau"


def test_le_provisoire_est_voisin_de_la_cible(tmp_path):
    """Condition de l'atomicité : un renommage entre systèmes de fichiers copie."""
    cible = tmp_path / "sous" / "dossier" / "granule.grib2"
    with ecriture_atomique(cible) as provisoire:
        assert provisoire.parent == cible.parent
        assert provisoire.name.endswith(SUFFIXE_PARTIEL)
        provisoire.write_bytes(b"x")


def test_le_provisoire_est_unique_a_chaque_appel(tmp_path):
    """Deux instances écrivant la même cible ne doivent pas se marcher dessus."""
    cible = tmp_path / "granule.grib2"
    vus: set[Path] = set()
    for _ in range(5):
        with ecriture_atomique(cible) as provisoire:
            vus.add(provisoire)
            provisoire.write_bytes(b"x")
    assert len(vus) == 5


def test_l_arborescence_manquante_est_creee(tmp_path):
    cible = tmp_path / "a" / "b" / "granule.grib2"
    with ecriture_atomique(cible) as provisoire:
        provisoire.write_bytes(b"x")
    assert cible.exists()


def test_un_bloc_qui_n_ecrit_rien_leve(tmp_path):
    """Publier une absence en silence serait la même faute, à l'envers."""
    cible = tmp_path / "granule.grib2"
    with pytest.raises(AucunFichierProduit, match=r"granule\.grib2"), ecriture_atomique(cible):
        pass
    assert not cible.exists()


def test_une_interruption_du_processus_est_aussi_nettoyee(tmp_path):
    """`KeyboardInterrupt` n'hérite pas d'`Exception` : le nettoyage doit
    quand même avoir lieu, sans quoi un arrêt manuel laisserait un résidu."""
    cible = tmp_path / "granule.grib2"
    with pytest.raises(KeyboardInterrupt), ecriture_atomique(cible) as provisoire:
        provisoire.write_bytes(b"partiel")
        raise KeyboardInterrupt
    assert _residus(tmp_path) == []


# --- Au bout de la chaîne : l'écriture NetCDF --------------------------------


def test_write_netcdf_ne_laisse_aucun_residu_si_l_ecriture_echoue(tmp_path, monkeypatch):
    """Un NetCDF tronqué s'ouvre parfois sans erreur et rend des variables
    amputées — la panne la plus discrète de toute la chaîne."""
    xr = pytest.importorskip("xarray")
    from x10_connectors import output

    jeu = xr.Dataset({"t": ("x", [1.0, 2.0])}, coords={"x": [0, 1]})
    jeu["t"].attrs["units"] = "K"

    def _echoue(*args: Any, **kwargs: Any) -> None:
        raise _PanneSimulee

    monkeypatch.setattr(xr.Dataset, "to_netcdf", _echoue)
    cible = tmp_path / "sortie.nc"
    with pytest.raises(_PanneSimulee):
        output.write_netcdf(jeu, cible)
    assert not cible.exists()
    assert _residus(tmp_path) == []


# --- À l'entrée de la chaîne : les deux connecteurs --------------------------


RESEAU = "2026-10-09T00:00:00Z"


def _cle(paquet: str, tranche: str) -> str:
    return f"pnt/{RESEAU}/arome/0025/{paquet}/arome__0025__{paquet}__{tranche}__{RESEAU}.grib2"


class _TransportQuiLache:
    """Écrit quelques octets, puis tombe — le cas réel d'un transfert coupé.

    L'inventaire répond normalement : c'est bien le **transfert** qu'on veut
    voir échouer, pas la découverte.
    """

    def __init__(self, *, ecrit: int = 32) -> None:
        self.ecrit = ecrit

    def lire(self, url: str) -> bytes:
        if "delimiter=/" in url:
            corps = f"<CommonPrefixes><Prefix>pnt/{RESEAU}/</Prefix></CommonPrefixes>"
        else:
            corps = "".join(
                f"<Contents><Key>{_cle('SP1', t)}</Key><Size>1000</Size></Contents>"
                for t in ("00H06H", "07H12H")
            )
        return f"<?xml version='1.0'?><ListBucketResult>{corps}</ListBucketResult>".encode()

    def telecharger(self, url: str, cible: Path, plafond: int) -> int:
        cible.write_bytes(b"\x00" * self.ecrit)
        raise MeteoFrancePntError("Connexion interrompue en cours de transfert.")


def test_meteofrance_un_transfert_coupe_ne_laisse_aucun_residu(tmp_path):
    from x10_connectors import MeteoFrancePntConnector, MeteoFrancePntRequest

    with pytest.raises(MeteoFrancePntError, match="interrompue"):
        MeteoFrancePntConnector(
            destination=tmp_path,
            request=MeteoFrancePntRequest(run=RESEAU),
            transport=_TransportQuiLache(),
        ).fetch()

    assert _residus(tmp_path) == [], "ni fichier partiel, ni provisoire oublié"


class _ClientTropGros:
    """Écrit un fichier qui dépasse le plafond : le refus vient après écriture."""

    def __init__(self, taille: int, **kwargs: Any) -> None:
        self.taille = taille

    def retrieve(self, request: dict[str, Any], target: str) -> None:
        Path(target).write_bytes(b"GRIB" + b"\x00" * (self.taille - 8) + b"7777")


def test_ecmwf_un_depassement_de_plafond_ne_laisse_aucun_residu(tmp_path):
    """Le plafond d'ECMWF ne s'applique qu'après écriture ; raison de plus
    pour que le fichier refusé n'apparaisse jamais sous son nom définitif.

    Le dépassement est une erreur **de notre fait**, donc non réessayable :
    elle remonte, sans repli sur une autre origine qui échouerait pareil.
    """
    with pytest.raises(EcmwfIfsError, match="après écriture"):
        EcmwfIfsOpenDataConnector(
            destination=tmp_path,
            request=EcmwfIfsRequest(parameters=("2t",)),
            max_bytes=512,
            client_factory=lambda **kwargs: _ClientTropGros(taille=4096, **kwargs),
        ).fetch()

    assert _residus(tmp_path) == []


def test_ecmwf_une_acquisition_normale_publie_bien_la_cible(tmp_path):
    """Le contrôle de non-régression du chemin nominal : l'atomicité ne doit
    pas empêcher la publication."""
    resultat = EcmwfIfsOpenDataConnector(
        destination=tmp_path,
        request=EcmwfIfsRequest(parameters=("2t",)),
        client_factory=lambda **kwargs: _ClientTropGros(taille=1024, **kwargs),
    ).fetch()

    assert resultat.outcome == "success"
    assert _residus(tmp_path) == [tmp_path / "2t-0h.grib2"]
