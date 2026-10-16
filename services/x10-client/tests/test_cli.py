"""L'entrée exécutable, et ses codes de sortie.

Le code de sortie est **la seule chose qu'un ordonnanceur lit**. Le tester
n'est donc pas une formalité de couverture : c'est le seul endroit où se
vérifie que « amputé » ne se présente pas comme un succès.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from x10_client import GranuleReport, PipelineReport, Verdict
from x10_client.__main__ import main

from x10_connectors import ConnectorResult


def _report(verdict: Verdict, outcome: str = "success") -> PipelineReport:
    return PipelineReport(
        source="source-essai",
        run_id="r1",
        started_at=datetime.now(UTC),
        acquisition=ConnectorResult(
            source="source-essai",
            outcome=outcome,
            run_id="r1",
            started_at=datetime.now(UTC),
            duration_ns=1,
            bytes_downloaded=42,
        ),
        granules=(GranuleReport(source=Path("g.grib2"), verdict=verdict),),
    )


@pytest.fixture
def destination(tmp_path, monkeypatch):
    monkeypatch.setenv("X10_DESTINATION", str(tmp_path))
    return tmp_path


def _stub_run(monkeypatch, report: PipelineReport) -> None:
    from x10_client import session as module_session

    monkeypatch.setattr(module_session.Session, "run", lambda _s, _r: report)


# --- Les codes de sortie ------------------------------------------------------


def test_sans_commande_l_aide_s_affiche_et_le_code_vaut_deux(capsys):
    assert main([]) == 2
    assert "observe" in capsys.readouterr().out


def test_une_configuration_absente_sort_en_deux(monkeypatch, capsys):
    monkeypatch.delenv("X10_DESTINATION", raising=False)
    assert main(["observe"]) == 2
    assert "X10_DESTINATION" in capsys.readouterr().err


def test_une_execution_complete_sort_en_zero(destination, monkeypatch, capsys):
    _stub_run(monkeypatch, _report(Verdict.COMPLETE))
    assert main(["run", "--package", "SP1"]) == 0
    assert "complete" in capsys.readouterr().out


def test_une_acquisition_echouee_sort_en_un(destination, monkeypatch):
    _stub_run(monkeypatch, _report(Verdict.NOT_ASSESSED, outcome="failure"))
    assert main(["run", "--package", "SP1"]) == 1


def test_une_execution_amputee_sort_en_trois(destination, monkeypatch, capsys):
    """Ni 0 ni 1 : la donnée est là, il en manque une partie. Laisser un
    ordonnanceur croire à l'un ou à l'autre serait le silence même que ce
    client existe pour fermer."""
    _stub_run(monkeypatch, _report(Verdict.PARTIAL))
    assert main(["run", "--package", "SP1"]) == 3
    assert "partial" in capsys.readouterr().out


def test_une_requete_sans_connecteur_sort_en_deux(destination, monkeypatch, capsys):
    from x10_client import session as module_session

    monkeypatch.setattr(
        module_session,
        "_connector_for",
        lambda _r: (_ for _ in ()).throw(module_session.UnknownRequest("aucun connecteur connu")),
    )
    assert main(["run", "--package", "SP1"]) == 2
    assert "Requête" in capsys.readouterr().err


# --- `constater` ---------------------------------------------------------------


def test_constater_sans_historique_le_dit_au_lieu_de_se_taire(destination, capsys):
    assert main(["observe"]) == 0
    assert "Aucune exécution" in capsys.readouterr().out


def test_constater_rend_une_ligne_par_source(destination, monkeypatch, capsys):
    _stub_run(monkeypatch, _report(Verdict.COMPLETE))
    main(["run", "--package", "SP1"])

    # Le `run` ci-dessus court-circuite l'accumulation : on l'écrit à la main,
    # car ce test porte sur l'affichage et non sur l'enchaînement.
    state = destination / ".x10"
    state.mkdir(parents=True, exist_ok=True)
    (state / "runs.jsonl").write_text(
        '{"source": "arome", "finished_at": "2026-10-15T12:00:00+00:00", '
        '"acquisition": {"outcome": "success", "duration_ns": 3000000, '
        '"bytes_downloaded": 1048576}}\n',
        encoding="utf-8",
    )
    assert main(["observe"]) == 0
    output = capsys.readouterr().out
    assert "arome" in output
    assert "100%" in output
