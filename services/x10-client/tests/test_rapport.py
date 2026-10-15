"""Le compte rendu : son verdict, sa référence au contrat, son accumulation.

Prototype interne — ces tests fixent donc des **propriétés**, pas un format.
Celle qui compte et qui ne bougera pas : le compte rendu référence le contrat
de sortie au lieu de le contenir.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from x10_client import Constat, GranuleReport, PipelineReport, Verdict, constater
from x10_client.report import empreinte_de_contrat

from x10_connectors import ConnectorResult


def _acquisition(
    outcome: str = "success", octets: int = 1024, duree_ns: int = 2_000_000
) -> ConnectorResult:
    return ConnectorResult(
        source="source-essai",
        outcome=outcome,
        run_id="r1",
        started_at=datetime.now(UTC),
        duration_ns=duree_ns,
        bytes_downloaded=octets,
    )


def _granule(verdict: Verdict, **suite: Any) -> GranuleReport:
    return GranuleReport(source=Path("g.grib2"), verdict=verdict, **suite)


# --- L'empreinte de contrat ---------------------------------------------------


def test_le_meme_contrat_donne_la_meme_empreinte():
    """C'est toute l'utilité de la référence : pouvoir dire « conforme au
    contrat C » sans transporter C."""
    assert empreinte_de_contrat('{"a": 1}') == empreinte_de_contrat('{"a": 1}')


def test_un_contrat_different_donne_une_empreinte_differente():
    assert empreinte_de_contrat('{"a": 1}') != empreinte_de_contrat('{"a": 2}')


def test_l_empreinte_est_courte_et_lisible():
    """Douze caractères : assez pour distinguer, assez court pour se lire
    dans une ligne de compte rendu."""
    empreinte = empreinte_de_contrat('{"a": 1}')
    assert len(empreinte) == 12
    assert all(c in "0123456789abcdef" for c in empreinte)


# --- Le verdict ---------------------------------------------------------------


def test_sans_granule_le_verdict_est_non_evalue():
    """`NON_EVALUE` n'est pas un échec : c'est l'aveu qu'on ne s'est pas
    prononcé. Rendre « complet » sur zéro granule serait une affirmation."""
    rapport = PipelineReport(
        source="s", run_id="r1", started_at=datetime.now(UTC), acquisition=_acquisition()
    )
    assert rapport.verdict is Verdict.NON_EVALUE


@pytest.mark.parametrize(
    ("granules", "attendu"),
    [
        ((Verdict.COMPLET, Verdict.COMPLET), Verdict.COMPLET),
        ((Verdict.COMPLET, Verdict.AMPUTE), Verdict.AMPUTE),
        ((Verdict.COMPLET, Verdict.NON_EVALUE), Verdict.NON_EVALUE),
        ((Verdict.AMPUTE, Verdict.NON_EVALUE), Verdict.AMPUTE),
    ],
    ids=["tout bon", "un ampute suffit", "un doute suffit", "ampute l'emporte sur le doute"],
)
def test_le_verdict_d_une_execution_est_le_pire_de_ses_granules(granules, attendu):
    rapport = PipelineReport(
        source="s",
        run_id="r1",
        started_at=datetime.now(UTC),
        acquisition=_acquisition(),
        granules=tuple(_granule(v) for v in granules),
    )
    assert rapport.verdict is attendu


def test_le_resume_nomme_ce_qui_manque():
    """« Il manque quelque chose » ne permet aucun arbitrage ; la liste, si."""
    rapport = PipelineReport(
        source="s",
        run_id="r1",
        started_at=datetime.now(UTC),
        acquisition=_acquisition(),
        granules=(_granule(Verdict.AMPUTE, perdus=("(0, 17, 4)",), contrat="abc123abc123"),),
    )
    resume = rapport.resume()
    assert "(0, 17, 4)" in resume
    assert "abc123abc123" in resume
    assert "ampute" in resume


# --- La sérialisation ---------------------------------------------------------


def test_le_compte_rendu_se_serialise_sans_code_de_conversion():
    """La raison d'être du choix Pydantic : cet objet franchit une frontière
    de processus, et les chemins comme les horodatages doivent passer."""
    rapport = PipelineReport(
        source="s",
        run_id="r1",
        started_at=datetime.now(UTC),
        acquisition=_acquisition(),
        granules=(_granule(Verdict.COMPLET, sorties=(Path("a.nc"),)),),
    )
    relu = PipelineReport.model_validate(json.loads(rapport.model_dump_json()))
    assert relu.granules[0].sorties == (Path("a.nc"),)
    assert relu.started_at == rapport.started_at


def test_l_acquisition_est_reprise_telle_quelle():
    """La redéfinir en ferait deux sources de vérité, et la seconde
    divergerait au premier champ ajouté au compte rendu du connecteur."""
    acquisition = _acquisition(octets=4096)
    rapport = PipelineReport(
        source="s", run_id="r1", started_at=datetime.now(UTC), acquisition=acquisition
    )
    assert rapport.acquisition == acquisition
    assert json.loads(rapport.model_dump_json())["acquisition"]["bytes_downloaded"] == 4096


# --- Constater, sur ce qui a été accumulé -------------------------------------


def _journal(etat: Path, lignes: list[dict[str, Any]]) -> None:
    etat.mkdir(parents=True, exist_ok=True)
    (etat / "executions.jsonl").write_text(
        "\n".join(json.dumps(x) for x in lignes) + "\n", encoding="utf-8"
    )


def _ligne(
    source: str, outcome: str, duree_ns: int, octets: int, decalage_h: int = 0
) -> dict[str, Any]:
    horodatage = datetime.now(UTC) - timedelta(hours=decalage_h)
    return {
        "source": source,
        "finished_at": horodatage.isoformat(),
        "acquisition": {
            "outcome": outcome,
            "duration_ns": duree_ns,
            "bytes_downloaded": octets,
        },
    }


def test_sans_historique_on_ne_constate_rien(tmp_path):
    assert constater(tmp_path) == ()


def test_le_taux_est_none_et_non_zero_quand_rien_n_est_observe():
    """Zéro ferait passer une absence de mesure pour un échec complet — le
    genre de silence que X10 traque ailleurs."""
    vide = Constat(
        source="s",
        executions=0,
        succes=0,
        derniere=None,
        duree_mediane_ms=None,
        octets_total=0,
    )
    assert vide.taux_de_succes is None


def test_le_constat_se_deduit_du_trafic_deja_passe(tmp_path):
    _journal(
        tmp_path,
        [
            _ligne("arome", "success", 2_000_000, 1000, decalage_h=2),
            _ligne("arome", "failure", 4_000_000, 0, decalage_h=1),
            _ligne("arome", "success", 6_000_000, 2000, decalage_h=0),
        ],
    )
    (constat,) = constater(tmp_path)
    assert constat.source == "arome"
    assert constat.executions == 3
    assert constat.succes == 2
    assert constat.taux_de_succes == pytest.approx(2 / 3)
    assert constat.duree_mediane_ms == pytest.approx(4.0)
    assert constat.octets_total == 3000


def test_les_sources_sont_distinguees(tmp_path):
    _journal(tmp_path, [_ligne("arome", "success", 1, 1), _ligne("ifs", "failure", 1, 0)])
    assert [c.source for c in constater(tmp_path)] == ["arome", "ifs"]
    assert [c.source for c in constater(tmp_path, "ifs")] == ["ifs"]


def test_une_ligne_tronquee_ne_perd_pas_l_historique(tmp_path):
    """Une écriture interrompue laisse une ligne incomplète. La rejeter avec
    tout le fichier coûterait plus que de la passer."""
    tronquee = '{"source": "aro'
    (tmp_path / "executions.jsonl").write_text(
        json.dumps(_ligne("arome", "success", 1, 10)) + "\n" + tronquee + "\n",
        encoding="utf-8",
    )
    (constat,) = constater(tmp_path)
    assert constat.executions == 1


def test_constater_n_emet_aucune_requete(tmp_path, monkeypatch):
    """Le trait principal du module, vérifié plutôt qu'affirmé."""
    import socket

    def interdit(*_args, **_kwargs):
        raise AssertionError("constater() a tenté d'ouvrir une connexion")

    monkeypatch.setattr(socket.socket, "connect", interdit)
    monkeypatch.setattr(socket, "create_connection", interdit)
    _journal(tmp_path, [_ligne("arome", "success", 1, 10)])
    assert constater(tmp_path)[0].executions == 1


def test_une_ligne_vide_est_passee_sans_bruit(tmp_path):
    """Un journal en ajout finit souvent par un saut de ligne, et un fichier
    recopié en gagne parfois un second."""
    (tmp_path / "executions.jsonl").write_text(
        json.dumps(_ligne("arome", "success", 1, 10)) + "\n\n   \n", encoding="utf-8"
    )
    (constat,) = constater(tmp_path)
    assert constat.executions == 1
