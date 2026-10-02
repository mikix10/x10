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


@pytest.mark.parametrize("role", ["hebergeur", "originator", "", "Producer", "Distributor"])
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
        provider=_agent("distributor"),
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
            provider=_agent("distributor"),
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


# --- Alignement INSPIRE ---------------------------------------------------------


@pytest.mark.parametrize(
    "role",
    [
        "distributor",
        "custodian",
        "owner",
        "user",
        "author",
        "resourceProvider",
        "pointOfContact",
        "principalInvestigator",
    ],
)
def test_les_roles_inspire_sont_acceptes(role):
    """La codelist INSPIRE est gouvernee au niveau « Legal (EU) »."""
    assert Agent(name="x", roles=(role,)).roles == (role,)


def test_originator_n_est_pas_un_role_car_producer_le_couvre():
    """Deux termes pour un concept invitent l'incoherence : `producer` est
    canonique et s'exporte vers `originator` sous INSPIRE."""
    with pytest.raises(ValidationError):
        Agent(name="x", roles=("originator",))


def _distribution(**surcharges: object) -> Distribution:
    champs: dict[str, object] = {
        "dataset": "j",
        "origin": "aws",
        "provider": Agent(name="AWS", roles=("distributor",)),
        "access_url": "https://exemple.invalid",
        "media_type": "application/x-grib2",
        "license": "CC-BY-4.0",
    }
    champs.update(surcharges)
    return Distribution(**champs)  # type: ignore[arg-type]


def test_l_acces_est_sans_limitation_par_defaut():
    assert _distribution().access_rights == "noLimitations"


@pytest.mark.parametrize(
    "limitation",
    ["INSPIRE_Directive_Article13_1a", "INSPIRE_Directive_Article13_1h"],
)
def test_les_limitations_de_l_article_13_sont_acceptees(limitation):
    assert _distribution(access_rights=limitation).access_rights == limitation


@pytest.mark.parametrize("limitation", ["restricted", "confidentiel", "article13"])
def test_une_limitation_hors_codelist_est_refusee(limitation):
    with pytest.raises(ValidationError):
        _distribution(access_rights=limitation)


def test_licence_et_restriction_d_acces_sont_deux_notions():
    """INSPIRE separe les conditions d'usage des motifs juridiques de
    restriction ; DCAT fait de meme avec license et accessRights."""
    distribution = _distribution(
        license="CC-BY-4.0", access_rights="INSPIRE_Directive_Article13_1d"
    )
    assert distribution.license == "CC-BY-4.0"
    assert distribution.access_rights == "INSPIRE_Directive_Article13_1d"


def test_le_jeu_distingue_son_producteur_de_son_editeur():
    """DCAT porte `dcterms:publisher` sur la ressource, pas sur la distribution."""
    jeu = Dataset(
        identifier="j",
        title="t",
        producer=Agent(name="ECMWF", roles=("producer",)),
        publisher=Agent(name="ECMWF", roles=("publisher",)),
        domain="meteo",
    )
    assert jeu.producer.name == jeu.publisher.name
    assert jeu.producer.roles != jeu.publisher.roles
