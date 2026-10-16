"""Ce qu'un consommateur lit, **sans connaître la décomposition en granules**.

Le granule est l'unité que **le producteur** publie. Un consommateur a
demandé « AROME SP1, 00H06H » ; lui imposer de parcourir `granules` pour
savoir ce qu'il a obtenu, c'est lui faire porter notre mécanique.

Ces tests partent donc d'**une ligne de `runs.jsonl` et de rien d'autre**, et
n'ouvrent jamais la clé `granules`. Ils échouaient tous avant le 16/10/2026 :
`verdict` était une `@property`, donc absent du JSON.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from x10_client import GranuleReport, PipelineReport, Verdict

from x10_connectors import ConnectorResult
from x10_models import Retrieval


def _report(*granules: GranuleReport, licence: str | None = "etalab-2.0") -> PipelineReport:
    return PipelineReport(
        source="demo-source",
        run_id="r1",
        started_at=datetime.now(UTC),
        acquisition=ConnectorResult(
            source="demo-source",
            outcome="success",
            run_id="r1",
            started_at=datetime.now(UTC),
            duration_ns=1_000_000,
            bytes_downloaded=2048,
            retrieval=Retrieval(
                dataset="d",
                origin="o",
                retrieved_at=datetime.now(UTC),
                agent="a",
                artefacts=(Path("a.grib2"),),
                license=licence,
                selection={"model": "arome", "packages": ["SP1"]},
            ),
        ),
        granules=granules,
    )


def _journal(report: PipelineReport) -> dict[str, Any]:
    """La ligne telle qu'elle est écrite, relue comme un tiers la relit."""
    return json.loads(report.model_dump_json())


# --- Les cinq questions, répondues au premier niveau --------------------------


def test_le_verdict_est_dans_le_json_et_non_a_recalculer():
    """Le défaut qui a motivé ce chantier.

    Sans cette clé, un consommateur doit réimplémenter « le pire des
    granules » — donc connaître notre découpage **et** sa règle de
    préséance."""
    ligne = _journal(
        _report(
            GranuleReport(source=Path("a"), verdict=Verdict.COMPLETE),
            GranuleReport(source=Path("b"), verdict=Verdict.PARTIAL),
        )
    )
    assert ligne["verdict"] == "partial"


def test_ou_est_ma_donnee_se_lit_en_une_cle():
    ligne = _journal(
        _report(
            GranuleReport(source=Path("a"), outputs=(Path("un.nc"), Path("deux.nc"))),
            GranuleReport(source=Path("b"), outputs=(Path("trois.nc"),)),
        )
    )
    assert [Path(p).name for p in ligne["outputs"]] == ["un.nc", "deux.nc", "trois.nc"]


def test_ce_qui_manque_est_rassemble_et_dedoublonne():
    """Deux granules peuvent perdre le même paramètre ; le consommateur veut
    la liste de ce qui manque, pas le compte des occurrences."""
    ligne = _journal(
        _report(
            GranuleReport(source=Path("a"), dropped=("(0, 17, 4)", "(2, 3, 192)")),
            GranuleReport(source=Path("b"), dropped=("(0, 17, 4)",)),
        )
    )
    assert ligne["dropped"] == ["(0, 17, 4)", "(2, 3, 192)"]


def test_la_licence_remonte_au_premier_niveau():
    """Une donnée qui quitte le système sans ses conditions d'usage n'est pas
    exploitable ; l'enfouir pariait que le consommateur irait la chercher."""
    assert _journal(_report())["license"] == "etalab-2.0"


def test_la_selection_demandee_remonte_aussi():
    """Sans elle, le compte rendu dit ce qu'on a obtenu sans dire par rapport
    à quoi."""
    assert _journal(_report())["selection"]["packages"] == ["SP1"]


# --- Dans quelle mesure -------------------------------------------------------


def test_les_compteurs_evitent_toute_traversee():
    ligne = _journal(
        _report(
            GranuleReport(
                source=Path("a"), verdict=Verdict.COMPLETE, parameters_in=5, fields_out=5
            ),
            GranuleReport(source=Path("b"), verdict=Verdict.PARTIAL, parameters_in=4, fields_out=3),
            GranuleReport(source=Path("c"), verdict=Verdict.FAILED),
        )
    )
    assert ligne["granule_count"] == 3
    assert ligne["complete_count"] == 1
    assert ligne["partial_count"] == 1
    assert ligne["failed_count"] == 1
    assert ligne["parameters_in"] == 9
    assert ligne["fields_out"] == 8


def test_un_consommateur_repond_a_tout_sans_ouvrir_granules():
    """La vérification d'ensemble : la clé `granules` reste fermée."""
    ligne = _journal(
        _report(GranuleReport(source=Path("a"), outputs=(Path("x.nc"),), verdict=Verdict.COMPLETE))
    )
    sans_detail = {k: v for k, v in ligne.items() if k != "granules"}

    assert sans_detail["verdict"] == "complete"
    assert sans_detail["outputs"]
    assert sans_detail["dropped"] == []
    assert sans_detail["license"]
    assert sans_detail["selection"]
    assert sans_detail["granule_count"] == 1


# --- Les invariants de la forme -----------------------------------------------


def test_les_champs_calcules_ne_peuvent_pas_diverger_du_detail():
    """Ils sont calculés et non stockés : il n'existe pas d'état à
    désynchroniser."""
    report = _report(GranuleReport(source=Path("a"), outputs=(Path("x.nc"),)))
    assert report.outputs == (Path("x.nc"),)
    assert _journal(report)["outputs"] == ["x.nc"]


def test_l_aller_retour_tient_malgre_les_champs_calcules(tmp_path):
    """Un consommateur peut relire une ligne en modèle sans que les clés
    calculées ne la fassent échouer."""
    report = _report(GranuleReport(source=Path("a"), verdict=Verdict.COMPLETE))
    relu = PipelineReport.model_validate(_journal(report))
    assert relu.verdict is Verdict.COMPLETE
    assert relu.granule_count == 1


def test_sans_lignage_la_licence_et_la_selection_sont_vides_et_non_fausses():
    """Une acquisition en échec ne porte aucun lignage. Rendre une licence
    inventée serait pire que d'en rendre aucune."""
    echec = PipelineReport(
        source="s",
        run_id="r",
        started_at=datetime.now(UTC),
        acquisition=ConnectorResult(
            source="s",
            outcome="failure",
            run_id="r",
            started_at=datetime.now(UTC),
            duration_ns=1,
        ),
    )
    ligne = _journal(echec)
    assert ligne["license"] is None
    assert ligne["selection"] == {}
    assert ligne["verdict"] == "not_assessed"


@pytest.mark.parametrize(
    ("granules", "attendu"),
    [
        ((Verdict.COMPLETE, Verdict.COMPLETE), Verdict.COMPLETE),
        ((Verdict.COMPLETE, Verdict.PARTIAL), Verdict.PARTIAL),
        ((Verdict.PARTIAL, Verdict.FAILED), Verdict.FAILED),
        ((Verdict.COMPLETE, Verdict.NOT_ASSESSED), Verdict.NOT_ASSESSED),
        ((Verdict.FAILED, Verdict.NOT_ASSESSED), Verdict.FAILED),
    ],
    ids=[
        "tout bon",
        "un ampute suffit",
        "un echec l'emporte sur un ampute",
        "un doute suffit",
        "un echec l'emporte sur un doute",
    ],
)
def test_l_ordre_de_preseance_vit_a_un_seul_endroit(granules, attendu):
    report = _report(*(GranuleReport(source=Path("g"), verdict=v) for v in granules))
    assert report.verdict is attendu
