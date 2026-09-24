from __future__ import annotations

import pytest
from pydantic import ValidationError

from x10_catalog import CatalogEntry, DataSource


def _source() -> DataSource:
    return DataSource(
        name="ecmwf-ifs-oper",
        provider="ECMWF",
        kind="forecast",
        url="https://data.ecmwf.int/forecasts",
        format="grib2",
        license="CC-BY-4.0",
    )


def test_entry_roundtrips_through_json():
    entry = CatalogEntry(
        source=_source(),
        variable="2t",
        domain="meteo",
        tags=("surface", "temperature"),
    )
    assert CatalogEntry.model_validate_json(entry.model_dump_json()) == entry


def test_metadata_defaults_are_not_shared_between_instances():
    first = _source()
    second = _source()
    first.metadata["resolution"] = "0.25"
    assert second.metadata == {}


def test_source_rejects_an_empty_provider():
    with pytest.raises(ValidationError):
        DataSource(name="x", provider="", kind="forecast")
