from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, ClassVar

import pytest

from x10_connectors import (
    EcmwfIfsError,
    EcmwfIfsOpenDataConnector,
    EcmwfIfsRequest,
    UnsafeDestinationError,
)

# Les constantes propres a une source se prennent au module : deux sources ne
# peuvent pas partager un meme nom dans l'espace plat du paquet.
from x10_connectors.ecmwf_ifs import (
    DEFAULT_PARAMETERS,
    SOURCE_LICENSE,
    SOURCE_NAME,
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
        {"origins": ("un-nuage-inconnu",)},
        {"step": -6},
    ],
)
def test_la_requete_refuse_une_selection_invalide(kwargs):
    with pytest.raises(ValueError):
        EcmwfIfsRequest(**kwargs)


def test_les_origines_couvrent_les_miroirs_infonuagiques():
    from x10_connectors.ecmwf_ifs import ORIGINS

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
        EcmwfIfsRequest(origins=("aws",)),
        client_factory=_fabrique(clients),
    )
    connecteur.fetch()

    assert clients[0].kwargs["source"] == "aws"


# --- Résultat et provenance ---------------------------------------------------


def test_le_resultat_porte_la_provenance_et_la_licence(tmp_path):
    resultat = EcmwfIfsOpenDataConnector(tmp_path, client_factory=_fabrique([])).fetch()

    assert resultat.outcome == "success"
    assert resultat.source == SOURCE_NAME
    assert resultat.retrieval is not None
    assert resultat.retrieval.license == SOURCE_LICENSE
    assert resultat.retrieval.origin == "ecmwf"
    assert len(resultat.retrieval.artefacts) == len(DEFAULT_PARAMETERS)


def test_les_artefacts_existent_et_sont_sous_la_racine(tmp_path):
    resultat = EcmwfIfsOpenDataConnector(tmp_path, client_factory=_fabrique([])).fetch()

    assert resultat.retrieval is not None
    for chemin in resultat.retrieval.artefacts:
        assert chemin.exists()
        assert chemin.is_relative_to(tmp_path.resolve())


# --- Sécurité ------------------------------------------------------------------


def test_un_parametre_qui_remonte_l_arborescence_est_refuse(tmp_path):
    connecteur = EcmwfIfsOpenDataConnector(
        tmp_path,
        EcmwfIfsRequest(parameters=("../evade",)),
        client_factory=_fabrique([]),
    )
    # Depuis la mise en commun du garde-fou de chemin, l'erreur est celle de
    # `base`. Elle derive de ValueError, donc reste non reessayable.
    with pytest.raises(UnsafeDestinationError, match="hors de la racine"):
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

    assert resultat.outcome == "success"
    assert resultat.retrieval is not None
    assert len(resultat.retrieval.artefacts) == 4
    for chemin in resultat.retrieval.artefacts:
        donnees = chemin.read_bytes()
        assert donnees[:4] == b"GRIB", f"{chemin.name} n'est pas un GRIB"
        assert donnees[7] == 2, "edition GRIB attendue : 2"
        assert struct.unpack(">Q", donnees[8:16])[0] == len(donnees)
        assert donnees[-4:] == b"7777"


# --- Bascule d'origine ---------------------------------------------------------


class _ClientDefaillant:
    """Echoue sur certaines origines, reussit sur les autres."""

    tentatives: ClassVar[list[str]] = []
    en_panne: ClassVar[set[str]] = set()

    def __init__(self, source: str, **kwargs: Any) -> None:
        self.source = source
        self.kwargs = kwargs
        _ClientDefaillant.tentatives.append(source)

    def retrieve(self, request: dict[str, Any], target: str) -> None:
        if self.source in self.en_panne:
            raise ConnectionError(f"{self.source} ne repond pas")
        Path(target).write_bytes(b"GRIB" + b"\x00" * 1016 + b"7777")


def _fabrique_defaillante(en_panne: set[str]):
    _ClientDefaillant.tentatives = []
    _ClientDefaillant.en_panne = en_panne

    def fabrique(**kwargs: Any) -> _ClientDefaillant:
        return _ClientDefaillant(**kwargs)

    return fabrique


def test_une_origine_inaccessible_entraine_un_repli(tmp_path):
    connecteur = EcmwfIfsOpenDataConnector(
        tmp_path,
        EcmwfIfsRequest(parameters=("2t",), origins=("ecmwf", "aws", "google")),
        client_factory=_fabrique_defaillante({"ecmwf"}),
    )
    resultat = connecteur.fetch()

    assert _ClientDefaillant.tentatives == ["ecmwf", "aws"]
    assert resultat.outcome == "success"


def test_le_lignage_porte_l_origine_retenue_et_non_celle_demandee(tmp_path):
    resultat = EcmwfIfsOpenDataConnector(
        tmp_path,
        EcmwfIfsRequest(parameters=("2t",), origins=("ecmwf", "aws")),
        client_factory=_fabrique_defaillante({"ecmwf"}),
    ).fetch()

    assert resultat.origin == "aws"
    assert resultat.retrieval is not None
    assert resultat.retrieval.origin == "aws"


def test_l_echec_de_toutes_les_origines_est_propage(tmp_path):
    connecteur = EcmwfIfsOpenDataConnector(
        tmp_path,
        EcmwfIfsRequest(parameters=("2t",), origins=("ecmwf", "aws")),
        client_factory=_fabrique_defaillante({"ecmwf", "aws"}),
    )
    with pytest.raises(ConnectionError):
        connecteur.fetch()

    assert _ClientDefaillant.tentatives == ["ecmwf", "aws"]


def test_une_erreur_de_notre_fait_n_entraine_aucun_repli(tmp_path):
    """Le plafond de volume vaut pour toutes les origines : réessayer
    ailleurs téléchargerait la même donnée trop volumineuse."""
    connecteur = EcmwfIfsOpenDataConnector(
        tmp_path,
        EcmwfIfsRequest(parameters=("2t",), origins=("ecmwf", "aws", "google")),
        max_bytes=100,
        client_factory=_fabrique_defaillante(set()),
    )
    with pytest.raises(EcmwfIfsError, match="plafond"):
        connecteur.fetch()

    assert _ClientDefaillant.tentatives == ["ecmwf"], "aucun repli ne doit avoir lieu"


def test_un_fichier_partiel_ne_survit_pas_a_une_bascule(tmp_path):
    """Sans nettoyage, un artefact de l'origine en panne subsisterait."""
    EcmwfIfsOpenDataConnector(
        tmp_path,
        EcmwfIfsRequest(parameters=("2t", "10u"), origins=("ecmwf", "aws")),
        client_factory=_fabrique_defaillante({"ecmwf"}),
    ).fetch()

    assert sorted(p.name for p in tmp_path.iterdir()) == ["10u-0h.grib2", "2t-0h.grib2"]
