from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from x10_connectors import BaseConnector, ConnectorResult


def _resultat(**surcharges: object) -> ConnectorResult:
    champs: dict[str, object] = {
        "source": "source-de-test",
        "outcome": "success",
        "run_id": "essai-1",
        "started_at": datetime(2026, 1, 1, tzinfo=UTC),
        "duration_ns": 1_000,
    }
    champs.update(surcharges)
    return ConnectorResult(**champs)  # type: ignore[arg-type]


class _StubConnector(BaseConnector):
    def fetch(self) -> ConnectorResult:
        return _resultat(source=self.source_name)


def test_base_connector_requires_a_fetch_implementation():
    with pytest.raises(NotImplementedError):
        BaseConnector("source-de-test").fetch()


def test_subclass_reports_its_source():
    assert _StubConnector("source-de-test").fetch().source == "source-de-test"


def test_le_resultat_se_serialise_en_json():
    """Il traverse XCom et les journaux : la sérialisation n'est pas optionnelle."""
    from pathlib import Path

    from x10_models import Retrieval

    lignage = Retrieval(
        artefacts=(Path("a/b.grib2"),),
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        dataset="un-jeu",
        origin="aws",
        agent="x10-connectors 0.1.0",
    )
    charge = _resultat(retrieval=lignage).model_dump_json()

    assert '"outcome":"success"' in charge
    assert "b.grib2" in charge
    assert '"origin":"aws"' in charge
    assert "2026-01-01T00:00:00Z" in charge


def test_le_resultat_se_relit_depuis_son_json():
    original = _resultat(bytes_downloaded=2_795_916)
    assert ConnectorResult.model_validate_json(original.model_dump_json()) == original


@pytest.mark.parametrize("valeur", ["ok", "OK", "partial", ""])
def test_le_statut_suit_le_vocabulaire_ecs(valeur):
    """event.outcome n'admet que success, failure ou unknown."""
    with pytest.raises(ValidationError):
        _resultat(outcome=valeur)


@pytest.mark.parametrize(("champ", "valeur"), [("duration_ns", -1), ("bytes_downloaded", -1)])
def test_les_mesures_ne_peuvent_pas_etre_negatives(champ, valeur):
    with pytest.raises(ValidationError):
        _resultat(**{champ: valeur})
