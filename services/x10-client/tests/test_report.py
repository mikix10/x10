"""Le compte rendu : son verdict, sa référence au contrat, son accumulation.

Prototype interne — ces tests fixent donc des **propriétés**, pas un format.
Celle qui compte et qui ne bougera pas : le compte rendu référence le contrat
de sortie au lieu de le contenir.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from x10_client import GranuleReport, PipelineReport, Verdict
from x10_client.report import contract_fingerprint

from x10_connectors import ConnectorResult


def _acquisition(
    outcome: str = "success", size_bytes: int = 1024, duration_ns: int = 2_000_000
) -> ConnectorResult:
    return ConnectorResult(
        source="source-essai",
        outcome=outcome,
        run_id="r1",
        started_at=datetime.now(UTC),
        duration_ns=duration_ns,
        bytes_downloaded=size_bytes,
    )


def _granule_report(verdict: Verdict, **suite: Any) -> GranuleReport:
    return GranuleReport(source=Path("g.grib2"), verdict=verdict, **suite)


# --- L'empreinte de contrat ---------------------------------------------------


def test_le_meme_contrat_donne_la_meme_empreinte():
    """C'est toute l'utilité de la référence : pouvoir dire « conforme au
    contrat C » sans transporter C."""
    assert contract_fingerprint('{"a": 1}') == contract_fingerprint('{"a": 1}')


def test_un_contrat_different_donne_une_empreinte_differente():
    assert contract_fingerprint('{"a": 1}') != contract_fingerprint('{"a": 2}')


def test_l_empreinte_est_courte_et_lisible():
    """Douze caractères : assez pour distinguer, assez court pour se lire
    dans une ligne de compte rendu."""
    fingerprint = contract_fingerprint('{"a": 1}')
    assert len(fingerprint) == 12
    assert all(c in "0123456789abcdef" for c in fingerprint)


# --- Le verdict ---------------------------------------------------------------


def test_sans_granule_le_verdict_est_non_evalue():
    """`NOT_ASSESSED` n'est pas un échec : c'est l'aveu qu'on ne s'est pas
    prononcé. Rendre « complet » sur zéro granule serait une affirmation."""
    report = PipelineReport(
        source="s", run_id="r1", started_at=datetime.now(UTC), acquisition=_acquisition()
    )
    assert report.verdict is Verdict.NOT_ASSESSED


@pytest.mark.parametrize(
    ("granules", "expected"),
    [
        ((Verdict.COMPLETE, Verdict.COMPLETE), Verdict.COMPLETE),
        ((Verdict.COMPLETE, Verdict.PARTIAL), Verdict.PARTIAL),
        ((Verdict.COMPLETE, Verdict.NOT_ASSESSED), Verdict.NOT_ASSESSED),
        ((Verdict.PARTIAL, Verdict.NOT_ASSESSED), Verdict.PARTIAL),
    ],
    ids=["tout bon", "un ampute suffit", "un doute suffit", "ampute l'emporte sur le doute"],
)
def test_le_verdict_d_une_execution_est_le_pire_de_ses_granules(granules, expected):
    report = PipelineReport(
        source="s",
        run_id="r1",
        started_at=datetime.now(UTC),
        acquisition=_acquisition(),
        granules=tuple(_granule_report(v) for v in granules),
    )
    assert report.verdict is expected


def test_le_resume_nomme_ce_qui_manque():
    """« Il manque quelque chose » ne permet aucun arbitrage ; la liste, si."""
    report = PipelineReport(
        source="s",
        run_id="r1",
        started_at=datetime.now(UTC),
        acquisition=_acquisition(),
        granules=(
            _granule_report(Verdict.PARTIAL, dropped=("(0, 17, 4)",), contract="abc123abc123"),
        ),
    )
    summary = report.summary()
    assert "(0, 17, 4)" in summary
    assert "abc123abc123" in summary
    assert "partial" in summary


# --- La sérialisation ---------------------------------------------------------


def test_le_compte_rendu_se_serialise_sans_code_de_conversion():
    """La raison d'être du choix Pydantic : cet objet franchit une frontière
    de processus, et les chemins comme les horodatages doivent passer."""
    report = PipelineReport(
        source="s",
        run_id="r1",
        started_at=datetime.now(UTC),
        acquisition=_acquisition(),
        granules=(_granule_report(Verdict.COMPLETE, outputs=(Path("a.nc"),)),),
    )
    reloaded = PipelineReport.model_validate(json.loads(report.model_dump_json()))
    assert reloaded.granules[0].outputs == (Path("a.nc"),)
    assert reloaded.started_at == report.started_at


def test_l_acquisition_est_reprise_telle_quelle():
    """La redéfinir en ferait deux sources de vérité, et la seconde
    divergerait au premier champ ajouté au compte rendu du connecteur."""
    acquisition = _acquisition(size_bytes=4096)
    report = PipelineReport(
        source="s", run_id="r1", started_at=datetime.now(UTC), acquisition=acquisition
    )
    assert report.acquisition == acquisition
    assert json.loads(report.model_dump_json())["acquisition"]["bytes_downloaded"] == 4096
