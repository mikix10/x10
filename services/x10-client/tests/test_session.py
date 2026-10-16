"""L'assemblage de la chaîne, et lui seul.

Ces tests portent sur ce que le client **ajoute** : enchaîner, compter,
qualifier, accumuler. Ils ne portent ni sur le décodage ni sur l'écriture,
qui sont éprouvés par les tests de `x10-connectors` et doivent le rester —
les y reprendre ferait dépendre la couverture d'un paquet d'un membre de
`services/`, soit la règle de dépendance à l'envers.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fixtures_grib2_min import minimal_granule
from x10_client import PipelineReport, Session, Verdict
from x10_client import session as module_session

from x10_connectors import ConnectorResult
from x10_models import Retrieval

pytest.importorskip("cfgrib")
pytest.importorskip("netCDF4")


class FakeRequest:
    """Une requête que seul le connecteur factice sait traiter."""


def _result(artefacts: tuple[Path, ...]) -> ConnectorResult:
    return ConnectorResult(
        source="source-factice",
        outcome="success",
        run_id="essai",
        origin="factice",
        started_at=datetime.now(UTC),
        duration_ns=1_000_000,
        bytes_downloaded=1234,
        retrieval=Retrieval(
            dataset="jeu-factice",
            origin="factice",
            retrieved_at=datetime.now(UTC),
            agent="x10-client (essai)",
            artefacts=artefacts,
            license="etalab-2.0",
        ),
    )


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setenv("X10_DESTINATION", str(tmp_path / "output"))
    return Session.from_env()


def _wire(monkeypatch, artefacts: tuple[Path, ...]) -> None:
    """Remplace la résolution de connecteur par un double qui ne télécharge rien."""

    class FakeConnector:
        def __init__(self, destination, request, **_):
            self.destination = destination

        def fetch(self):
            return _result(artefacts)

    monkeypatch.setattr(module_session, "_connector_for", lambda _r: FakeConnector)


# --- Le chemin nominal --------------------------------------------------------


def test_un_granule_sain_est_enchaine_jusqu_a_la_sortie(session, tmp_path, monkeypatch):
    source = minimal_granule(tmp_path / "healthy.grib2", ((0, 0), (2, 2)))
    _wire(monkeypatch, (source,))

    report = session.run(FakeRequest())

    assert report.verdict is Verdict.COMPLETE
    assert len(report.granules) == 1
    granule = report.granules[0]
    assert granule.parameters_in == 2
    assert granule.fields_out == 2
    assert granule.dropped == ()
    assert granule.outputs, "la chaîne doit avoir écrit quelque chose"
    assert all(p.exists() for p in granule.outputs)


def test_le_compte_rendu_reference_le_contrat_sans_le_contenir(session, tmp_path, monkeypatch):
    """La séparation arrêtée : une référence, jamais le contrat lui-même.

    Elle protège l'invariance du contrat, qui est ce qui en fait un
    indicateur de dérive."""
    source = minimal_granule(tmp_path / "ref.grib2", ((0, 0),))
    _wire(monkeypatch, (source,))

    granule = session.run(FakeRequest()).granules[0]

    assert granule.contract is not None
    assert len(granule.contract) == 12, "une empreinte courte, pas un document"
    serialised = granule.model_dump_json()
    assert "variables" not in serialised, "le contrat ne doit pas y être recopié"


def test_deux_executions_du_meme_granule_rendent_la_meme_reference(session, tmp_path, monkeypatch):
    """Sinon la référence ne vaudrait rien comme point de comparaison."""
    source = minimal_granule(tmp_path / "stable.grib2", ((0, 0),))
    _wire(monkeypatch, (source,))

    first = session.run(FakeRequest()).granules[0].contract
    second = session.run(FakeRequest()).granules[0].contract
    assert first == second


# --- Le chemin amputé ---------------------------------------------------------


def test_un_granule_ampute_est_rapporte_et_non_refuse(session, tmp_path, monkeypatch):
    """Deux paramètres irrésolus partagent un nom court : l'un disparaît.

    La bibliothèque lève, et elle a raison. Le client, lui, **rend compte** :
    le grain de l'arbitrage appartient à l'appelant, et ici l'appelant a pour
    métier de dire ce qui s'est passé.
    """
    source = minimal_granule(tmp_path / "partial.grib2", ((16, 192), (16, 193)))
    _wire(monkeypatch, (source,))

    report = session.run(FakeRequest())
    granule = report.granules[0]

    assert report.verdict is Verdict.PARTIAL
    assert granule.parameters_in == 2
    assert granule.fields_out == 1
    assert granule.dropped == ("(0, 16, 193)",)
    assert "short name" in granule.reason
    assert granule.outputs, "ce qui reste est écrit : amputé n'est pas perdu"


def test_un_seul_granule_ampute_ampute_l_execution(session, tmp_path, monkeypatch):
    """Rendre « complet » parce que la majorité l'est serait le silence même
    que ce compte rendu existe pour fermer."""
    healthy = minimal_granule(tmp_path / "a.grib2", ((0, 0),))
    partial = minimal_granule(tmp_path / "b.grib2", ((16, 192), (16, 193)))
    _wire(monkeypatch, (healthy, partial))

    report = session.run(FakeRequest())
    assert {g.verdict for g in report.granules} == {Verdict.COMPLETE, Verdict.PARTIAL}
    assert report.verdict is Verdict.PARTIAL


# --- L'accumulation, qui n'émet aucune requête --------------------------------


def test_chaque_execution_s_ajoute_a_l_etat(session, tmp_path, monkeypatch):
    source = minimal_granule(tmp_path / "trace.grib2", ((0, 0),))
    _wire(monkeypatch, (source,))

    session.run(FakeRequest())
    session.run(FakeRequest())

    journal = session.settings.state / "runs.jsonl"
    lines = [json.loads(x) for x in journal.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2
    assert all(x["source"] == "source-factice" for x in lines)
    assert PipelineReport.model_validate(lines[0]).verdict is Verdict.COMPLETE


def test_l_etat_se_pose_sous_la_destination_par_defaut(tmp_path, monkeypatch):
    monkeypatch.setenv("X10_DESTINATION", str(tmp_path / "ici"))
    monkeypatch.delenv("X10_STATE", raising=False)
    assert Session.from_env().settings.state == (tmp_path / "ici" / ".x10").resolve()


# --- Ce que le client refuse de faire ------------------------------------------


def test_une_requete_sans_connecteur_leve_clairement(session):
    with pytest.raises(module_session.UnknownRequest, match="no known connector"):
        session.acquire(FakeRequest())


def test_le_client_n_est_importe_par_aucun_paquet():
    """La règle de dépendance : `services/` consomme, il n'est jamais consommé."""
    root = Path(__file__).resolve().parents[3] / "packages"
    offenders = [
        p
        for p in root.rglob("*.py")
        if "__pycache__" not in p.parts and "x10_client" in p.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"un paquet importe le client : {offenders}"


def test_la_resolution_de_connecteur_se_fait_sans_reseau():
    """Associer une requête à sa classe ne télécharge rien — et la résolution
    est **paresseuse** pour que le client reste installable sans l'extra du
    client officiel ECMWF."""
    from x10_connectors import MeteoFrancePntConnector, MeteoFrancePntRequest

    assert module_session._connector_for(MeteoFrancePntRequest()) is MeteoFrancePntConnector


def test_l_enchainement_n_ajoute_aucune_requete(session, tmp_path, monkeypatch):
    """La règle du module `availability`, vérifiée sur la chaîne entière.

    Décoder, normaliser, écrire, contracter et accumuler se font **sur le
    disque**. Seule l'acquisition parle au producteur, et elle est ici
    remplacée par un double : toute connexion ouverte pendant ce test serait
    donc une sollicitation ajoutée par le client.
    """
    import socket

    source = minimal_granule(tmp_path / "muet.grib2", ((0, 0),))
    _wire(monkeypatch, (source,))

    def forbidden(*_args, **_kwargs):
        raise AssertionError("l'enchaînement a ouvert une connexion")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)

    assert session.run(FakeRequest()).verdict is Verdict.COMPLETE
