from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from x10_models import GeoPoint, Observation, Provenance


def _observation() -> Observation:
    return Observation(
        variable="air_temperature",
        value=Decimal("18.4"),
        unit="degC",
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        location=GeoPoint(latitude=48.8566, longitude=2.3522),
        provenance=Provenance(source_name="ECMWF IFS open data", license="CC-BY-4.0"),
    )


def test_observation_roundtrips_through_json():
    obs = _observation()
    assert Observation.model_validate_json(obs.model_dump_json()) == obs


def test_observation_preserves_decimal_precision():
    assert _observation().value == Decimal("18.4")


def test_models_are_frozen():
    point = GeoPoint(latitude=0.0, longitude=0.0)
    with pytest.raises(ValidationError):
        point.latitude = 10.0


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(91.0, 0.0), (-91.0, 0.0), (0.0, 181.0), (0.0, -181.0)],
)
def test_geopoint_rejects_out_of_range_coordinates(latitude, longitude):
    with pytest.raises(ValidationError):
        GeoPoint(latitude=latitude, longitude=longitude)


def test_provenance_requires_a_source_name():
    with pytest.raises(ValidationError):
        Provenance(source_name="")
