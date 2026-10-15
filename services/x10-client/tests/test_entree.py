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


def _rapport(verdict: Verdict, outcome: str = "success") -> PipelineReport:
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


def _executer(monkeypatch, rapport: PipelineReport) -> None:
    from x10_client import session as module_session

    monkeypatch.setattr(module_session.Session, "run", lambda _s, _r: rapport)


# --- Les codes de sortie ------------------------------------------------------


def test_sans_commande_l_aide_s_affiche_et_le_code_vaut_deux(capsys):
    assert main([]) == 2
    assert "constater" in capsys.readouterr().out


def test_une_configuration_absente_sort_en_deux(monkeypatch, capsys):
    monkeypatch.delenv("X10_DESTINATION", raising=False)
    assert main(["constater"]) == 2
    assert "X10_DESTINATION" in capsys.readouterr().err


def test_une_execution_complete_sort_en_zero(destination, monkeypatch, capsys):
    _executer(monkeypatch, _rapport(Verdict.COMPLET))
    assert main(["run", "--paquet", "SP1"]) == 0
    assert "complet" in capsys.readouterr().out


def test_une_acquisition_echouee_sort_en_un(destination, monkeypatch):
    _executer(monkeypatch, _rapport(Verdict.NON_EVALUE, outcome="failure"))
    assert main(["run", "--paquet", "SP1"]) == 1


def test_une_execution_amputee_sort_en_trois(destination, monkeypatch, capsys):
    """Ni 0 ni 1 : la donnée est là, il en manque une partie. Laisser un
    ordonnanceur croire à l'un ou à l'autre serait le silence même que ce
    client existe pour fermer."""
    _executer(monkeypatch, _rapport(Verdict.AMPUTE))
    assert main(["run", "--paquet", "SP1"]) == 3
    assert "ampute" in capsys.readouterr().out


def test_une_requete_sans_connecteur_sort_en_deux(destination, monkeypatch, capsys):
    from x10_client import session as module_session

    monkeypatch.setattr(
        module_session,
        "_connecteur_pour",
        lambda _r: (_ for _ in ()).throw(module_session.RequeteInconnue("aucun connecteur connu")),
    )
    assert main(["run", "--paquet", "SP1"]) == 2
    assert "Requête" in capsys.readouterr().err


# --- `constater` ---------------------------------------------------------------


def test_constater_sans_historique_le_dit_au_lieu_de_se_taire(destination, capsys):
    assert main(["constater"]) == 0
    assert "Aucune exécution" in capsys.readouterr().out


def test_constater_rend_une_ligne_par_source(destination, monkeypatch, capsys):
    _executer(monkeypatch, _rapport(Verdict.COMPLET))
    main(["run", "--paquet", "SP1"])

    # Le `run` ci-dessus court-circuite l'accumulation : on l'écrit à la main,
    # car ce test porte sur l'affichage et non sur l'enchaînement.
    etat = destination / ".x10"
    etat.mkdir(parents=True, exist_ok=True)
    (etat / "executions.jsonl").write_text(
        '{"source": "arome", "finished_at": "2026-10-15T12:00:00+00:00", '
        '"acquisition": {"outcome": "success", "duration_ns": 3000000, '
        '"bytes_downloaded": 1048576}}\n',
        encoding="utf-8",
    )
    assert main(["constater"]) == 0
    sortie = capsys.readouterr().out
    assert "arome" in sortie
    assert "100%" in sortie
