from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from x10_connectors import (
    RESERVED_RECORD_ATTRIBUTES,
    ConnectorResult,
    EcmwfIfsOpenDataConnector,
    EcmwfIfsRequest,
    EcsJsonFormatter,
    failure_fields,
    fetch_finished_fields,
    fetch_started_fields,
)
from x10_models import Retrieval


class _ClientSimule:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def retrieve(self, request: dict[str, object], target: str) -> None:
        Path(target).write_bytes(b"GRIB" + b"\x00" * 1016 + b"7777")


class _ClientEnPanne:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def retrieve(self, request: dict[str, object], target: str) -> None:
        raise ConnectionError("la source ne repond pas")


def _fabrique(client: type) -> object:
    def fabrique(**kwargs: object) -> object:
        return client(**kwargs)

    return fabrique


def _lignage(*artefacts: Path) -> Retrieval:
    return Retrieval(
        artefacts=artefacts,
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        dataset="source-de-test",
        origin="aws",
        agent="x10-connectors 0.1.0",
        license="CC-BY-4.0",
    )


def _resultat() -> ConnectorResult:
    return ConnectorResult(
        source="source-de-test",
        outcome="success",
        run_id="essai-1",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        duration_ns=1_500_000,
        bytes_downloaded=2_795_916,
        origin="aws",
        retrieval=_lignage(),
    )


# --- Le piège des noms réservés ------------------------------------------------


def test_aucun_champ_emis_ne_heurte_un_attribut_reserve():
    """`extra=` leve une KeyError sur un nom reserve : la journalisation
    echouerait elle-meme, ce qui est la pire facon d'echouer."""
    champs = {
        **fetch_started_fields(source="s", run_id="r", origin="o", attempt=1, details={"step": 0}),
        **fetch_finished_fields(_resultat()),
        **failure_fields(ValueError("x")),
    }
    collisions = set(champs) & RESERVED_RECORD_ATTRIBUTES
    assert collisions == set(), f"champs en collision avec LogRecord : {collisions}"


def test_les_champs_emis_passent_reellement_dans_extra(caplog):
    journal = logging.getLogger("essai.extra")
    with caplog.at_level(logging.INFO, logger="essai.extra"):
        journal.info("test", extra=fetch_finished_fields(_resultat()))

    assert caplog.records[0].__dict__["event.outcome"] == "success"


# --- Conformité au schéma ------------------------------------------------------


def test_la_duree_est_en_nanosecondes_comme_l_exige_le_schema():
    champs = fetch_finished_fields(_resultat())
    assert champs["event.duration"] == 1_500_000
    assert isinstance(champs["event.duration"], int)


def test_l_issue_suit_le_vocabulaire_ferme_du_schema():
    assert fetch_finished_fields(_resultat())["event.outcome"] in {
        "success",
        "failure",
        "unknown",
    }
    assert failure_fields(ValueError("x"))["event.outcome"] == "failure"


def test_un_echec_distingue_le_type_d_erreur():
    """Permet de separer une source indisponible d'un defaut interne."""
    champs = failure_fields(ConnectionError("la source ne repond pas"))
    assert champs["error.type"] == "ConnectionError"
    assert "ne repond pas" in champs["error.message"]


# --- La bibliothèque émet, elle ne configure pas -------------------------------


def test_la_bibliotheque_n_installe_aucun_handler_sur_la_racine():
    avant = list(logging.getLogger().handlers)
    import importlib

    import x10_connectors.observability as obs

    importlib.reload(obs)
    assert list(logging.getLogger().handlers) == avant


def test_le_journal_du_connecteur_est_muet_par_defaut():
    from x10_connectors import connector_logger

    journal = connector_logger("essai.muet")
    assert any(isinstance(h, logging.NullHandler) for h in journal.handlers)


# --- Émission par le connecteur ------------------------------------------------


def test_le_connecteur_emet_un_debut_et_une_fin_correles(tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger="x10_connectors.ecmwf_ifs"):
        EcmwfIfsOpenDataConnector(
            tmp_path,
            EcmwfIfsRequest(parameters=("2t",)),
            run_id="execution-42",
            client_factory=_fabrique(_ClientSimule),
        ).fetch()

    traces = [r.__dict__.get("trace.id") for r in caplog.records]
    assert traces == ["execution-42", "execution-42"]
    assert caplog.records[-1].__dict__["event.outcome"] == "success"
    assert caplog.records[-1].__dict__["x10.bytes"] == 1024


def test_l_identifiant_d_execution_est_engendre_s_il_n_est_pas_fourni(tmp_path):
    resultat = EcmwfIfsOpenDataConnector(
        tmp_path,
        EcmwfIfsRequest(parameters=("2t",)),
        client_factory=_fabrique(_ClientSimule),
    ).fetch()

    assert len(resultat.run_id) == 36


def test_un_echec_est_journalise_avant_d_etre_propage(tmp_path, caplog):
    with (
        caplog.at_level(logging.WARNING, logger="x10_connectors.ecmwf_ifs"),
        pytest.raises(ConnectionError),
    ):
        EcmwfIfsOpenDataConnector(
            tmp_path,
            EcmwfIfsRequest(parameters=("2t",)),
            client_factory=_fabrique(_ClientEnPanne),
        ).fetch()

    echec = caplog.records[-1]
    assert echec.__dict__["event.outcome"] == "failure"
    assert echec.__dict__["error.type"] == "ConnectionError"
    assert echec.__dict__["event.duration"] > 0


# --- Rendu JSON pour une chaîne ELK --------------------------------------------


def test_le_formateur_produit_une_ligne_json_exploitable():
    enregistrement = logging.LogRecord(
        name="x10_connectors.essai",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Récupération terminée",
        args=(),
        exc_info=None,
    )
    enregistrement.__dict__.update(fetch_finished_fields(_resultat()))

    charge = json.loads(EcsJsonFormatter().format(enregistrement))

    assert charge["message"] == "Récupération terminée"
    assert charge["log.level"] == "info"
    assert charge["event.outcome"] == "success"
    assert charge["event.duration"] == 1_500_000
    assert charge["x10.origin"] == "aws"


def test_le_formateur_ignore_les_attributs_hors_schema():
    enregistrement = logging.LogRecord(
        name="x10_connectors.essai",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="test",
        args=(),
        exc_info=None,
    )
    enregistrement.__dict__["bruit_interne"] = "a ne pas exporter"

    assert "bruit_interne" not in json.loads(EcsJsonFormatter().format(enregistrement))


def test_le_formateur_resiste_a_un_flux_non_utf8():
    """Les messages sont en français ; une console cp1252 corromprait les accents."""
    enregistrement = logging.LogRecord(
        name="x10_connectors.essai",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Récupération terminée",
        args=(),
        exc_info=None,
    )
    rendu = EcsJsonFormatter().format(enregistrement)

    assert rendu.isascii(), "la sortie doit rester ASCII pour survivre a tout flux"
    assert json.loads(rendu)["message"] == "Récupération terminée"


# --- Surface journalisée : fermée et opposable ---------------------------------
#
# Le contrat d'interface garantit que X10 n'emet ni identite, ni secret, ni
# chemin. Ces tests rendent la garantie opposable : ajouter un champ devient un
# acte delibere qui casse un test nomme, et non un effet de bord qui elargit la
# surface journalisee en silence.

CHAMPS_DEBUT = {
    "event.action",
    "x10.attempt",
    "event.category",
    "event.dataset",
    "event.kind",
    "trace.id",
    "x10.origin",
    "x10.parameters",
    "x10.source",
    "x10.step",
}

CHAMPS_FIN = {
    "event.action",
    "event.category",
    "event.dataset",
    "event.duration",
    "event.kind",
    "event.outcome",
    "event.start",
    "trace.id",
    "x10.artefacts",
    "x10.bytes",
    "x10.dataset",
    "x10.license",
    "x10.origin",
    "x10.source",
}

CHAMPS_ECHEC = {"error.message", "error.type", "event.outcome"}


def test_la_surface_emise_au_demarrage_est_exactement_celle_du_contrat():
    champs = fetch_started_fields(
        source="s",
        run_id="r",
        origin="o",
        attempt=1,
        details={"parameters": ["2t"], "step": 0},
    )
    assert set(champs) == CHAMPS_DEBUT


def test_la_surface_emise_a_la_fin_est_exactement_celle_du_contrat():
    assert set(fetch_finished_fields(_resultat())) == CHAMPS_FIN


def test_la_surface_emise_en_echec_est_exactement_celle_du_contrat():
    assert set(failure_fields(ValueError("x"))) == CHAMPS_ECHEC


def test_aucun_chemin_de_fichier_n_est_journalise():
    """Un chemin de destination porte souvent un nom d'utilisateur.

    Les journaux n'en comptent que le nombre ; les chemins complets ne vivent
    que dans le resultat, qui ne transite pas par la meme voie.
    """
    resultat = _resultat()
    resultat.retrieval = _lignage(Path("repertoire-temoin/2t-0h.grib2"))

    emis = json.dumps(fetch_finished_fields(resultat), default=str)

    assert "repertoire-temoin" not in emis
    assert "grib2" not in emis
    assert fetch_finished_fields(resultat)["x10.artefacts"] == 1
