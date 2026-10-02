from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from x10_models import (
    Agent,
    Dataset,
    Distribution,
    GeoPoint,
    Observation,
    Provenance,
    Retrieval,
)


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


# --- Vocabulaire DCAT et PROV --------------------------------------------------


def _agent(*roles: str) -> Agent:
    return Agent(name="ECMWF", roles=roles)  # type: ignore[arg-type]


def test_un_agent_peut_cumuler_des_roles():
    agent = _agent("producer", "licensor", "publisher")
    assert len(agent.roles) == 3


@pytest.mark.parametrize("role", ["hebergeur", "owner", "", "Producer"])
def test_le_vocabulaire_des_roles_est_ferme(role):
    """Un champ libre se dégrade en texte que personne ne peut plus agréger."""
    with pytest.raises(ValidationError):
        Agent(name="x", roles=(role,))


def test_un_agent_sans_role_est_refuse():
    with pytest.raises(ValidationError):
        Agent(name="x", roles=())


@pytest.mark.parametrize("domaine", ["geo", "hydro", "oceano", "meteo"])
def test_les_quatre_domaines_physiques_sont_acceptes(domaine):
    assert (
        Dataset(identifier="j", title="t", producer=_agent("producer"), domain=domaine).domain
        == domaine
    )


def test_un_domaine_hors_perimetre_est_refuse():
    with pytest.raises(ValidationError):
        Dataset(identifier="j", title="t", producer=_agent("producer"), domain="astro")


def test_une_distribution_porte_sa_propre_licence():
    """La licence n'est pas seulement celle du jeu : un ré-exposant peut
    ajouter ses conditions."""
    distribution = Distribution(
        dataset="j",
        origin="aws",
        publisher=_agent("publisher"),
        access_url="https://exemple.invalid",
        media_type="application/x-grib2",
        license="CC-BY-4.0",
    )
    assert distribution.license == "CC-BY-4.0"
    assert distribution.priority == 100


def test_une_priorite_negative_est_refusee():
    with pytest.raises(ValidationError):
        Distribution(
            dataset="j",
            origin="aws",
            publisher=_agent("publisher"),
            access_url="https://exemple.invalid",
            media_type="application/x-grib2",
            license="CC-BY-4.0",
            priority=-1,
        )


def test_le_lignage_porte_l_origine_effectivement_retenue():
    lignage = Retrieval(
        artefacts=(Path("2t-0h.grib2"),),
        retrieved_at=datetime(2026, 10, 2, tzinfo=UTC),
        dataset="ecmwf-ifs-oper-0p25",
        origin="aws",
        selection={"parameters": ["2t"], "step": 0},
        agent="x10-connectors 0.1.0",
        license="CC-BY-4.0",
    )
    assert lignage.origin == "aws"
    assert Retrieval.model_validate_json(lignage.model_dump_json()) == lignage


def test_les_modeles_de_vocabulaire_sont_immuables():
    agent = _agent("producer")
    with pytest.raises(ValidationError):
        agent.name = "autre"
