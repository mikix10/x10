from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

import pytest

from x10_connectors import (
    DEFAULT_PARAMETERS,
    SOURCE_LICENSE,
    SOURCE_NAME,
    EcmwfIfsError,
    EcmwfIfsOpenDataConnector,
    EcmwfIfsRequest,
)


class _ClientSimule:
    """Remplace le client officiel : enregistre les requêtes, écrit un leurre."""

    def __init__(self, taille: int = 1024, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.taille = taille
        self.requetes: list[dict[str, Any]] = []

    def retrieve(self, request: dict[str, Any], target: str) -> None:
        self.requetes.append(request)
        Path(target).write_bytes(b"GRIB" + b"\x00" * (self.taille - 8) + b"7777")


def _fabrique(enregistre: list[_ClientSimule], taille: int = 1024):
    def fabrique(**kwargs: Any) -> _ClientSimule:
        client = _ClientSimule(taille=taille, **kwargs)
        enregistre.append(client)
        return client

    return fabrique


# --- Requête -----------------------------------------------------------------


def test_la_requete_par_defaut_porte_les_quatre_parametres_de_surface():
    assert EcmwfIfsRequest().parameters == DEFAULT_PARAMETERS
    assert DEFAULT_PARAMETERS == ("2t", "2d", "10u", "10v")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"parameters": ()},
        {"origin": "un-nuage-inconnu"},
        {"step": -6},
    ],
)
def test_la_requete_refuse_une_selection_invalide(kwargs):
    with pytest.raises(ValueError):
        EcmwfIfsRequest(**kwargs)


def test_les_origines_couvrent_les_miroirs_infonuagiques():
    from x10_connectors import ORIGINS

    assert set(ORIGINS) == {"ecmwf", "aws", "azure", "google"}


# --- Sélection transmise au client -------------------------------------------


def test_une_requete_mars_est_emise_par_parametre(tmp_path):
    clients: list[_ClientSimule] = []
    connecteur = EcmwfIfsOpenDataConnector(tmp_path, client_factory=_fabrique(clients))

    connecteur.fetch()

    emises = clients[0].requetes
    assert [r["param"] for r in emises] == list(DEFAULT_PARAMETERS)
    assert {r["levtype"] for r in emises} == {"sfc"}
    assert {r["type"] for r in emises} == {"fc"}


def test_les_bornes_de_reprise_sont_abaissees(tmp_path):
    """Le client officiel tolère 500 reprises espacées de 120 s par défaut."""
    clients: list[_ClientSimule] = []
    EcmwfIfsOpenDataConnector(tmp_path, client_factory=_fabrique(clients)).fetch()

    assert clients[0].kwargs["maximum_retries"] == 3
    assert clients[0].kwargs["retry_after"] == 10


def test_l_origine_demandee_est_transmise(tmp_path):
    clients: list[_ClientSimule] = []
    connecteur = EcmwfIfsOpenDataConnector(
        tmp_path,
        EcmwfIfsRequest(origin="aws"),
        client_factory=_fabrique(clients),
    )
    connecteur.fetch()

    assert clients[0].kwargs["source"] == "aws"


# --- Résultat et provenance ---------------------------------------------------


def test_le_resultat_porte_la_provenance_et_la_licence(tmp_path):
    resultat = EcmwfIfsOpenDataConnector(tmp_path, client_factory=_fabrique([])).fetch()

    assert resultat.status == "ok"
    assert resultat.source == SOURCE_NAME
    assert resultat.provenance is not None
    assert resultat.provenance.license == SOURCE_LICENSE
    assert resultat.provenance.retrieval_time is not None
    assert len(resultat.artefacts) == len(DEFAULT_PARAMETERS)


def test_les_artefacts_existent_et_sont_sous_la_racine(tmp_path):
    resultat = EcmwfIfsOpenDataConnector(tmp_path, client_factory=_fabrique([])).fetch()

    for chemin in resultat.artefacts:
        assert chemin.exists()
        assert chemin.is_relative_to(tmp_path.resolve())


# --- Sécurité ------------------------------------------------------------------


def test_un_parametre_qui_remonte_l_arborescence_est_refuse(tmp_path):
    connecteur = EcmwfIfsOpenDataConnector(
        tmp_path,
        EcmwfIfsRequest(parameters=("../evade",)),
        client_factory=_fabrique([]),
    )
    with pytest.raises(EcmwfIfsError, match="hors de la racine"):
        connecteur.fetch()


def test_le_plafond_de_volume_interrompt_et_supprime_l_artefact(tmp_path):
    connecteur = EcmwfIfsOpenDataConnector(
        tmp_path,
        EcmwfIfsRequest(parameters=("2t",)),
        max_bytes=100,
        client_factory=_fabrique([], taille=4096),
    )
    with pytest.raises(EcmwfIfsError, match="plafond"):
        connecteur.fetch()

    assert list(tmp_path.iterdir()) == []


# --- Intégration, à la demande -------------------------------------------------


@pytest.mark.network
def test_telechargement_reel_de_messages_grib2(tmp_path):
    """Atteint le service réel. Lancer par `uv run pytest -m network`."""
    resultat = EcmwfIfsOpenDataConnector(tmp_path, EcmwfIfsRequest(step=0)).fetch()

    assert resultat.status == "ok"
    assert len(resultat.artefacts) == 4
    for chemin in resultat.artefacts:
        donnees = chemin.read_bytes()
        assert donnees[:4] == b"GRIB", f"{chemin.name} n'est pas un GRIB"
        assert donnees[7] == 2, "edition GRIB attendue : 2"
        assert struct.unpack(">Q", donnees[8:16])[0] == len(donnees)
        assert donnees[-4:] == b"7777"
