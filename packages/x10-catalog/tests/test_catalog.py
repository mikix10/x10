from __future__ import annotations

import pytest
from pydantic import ValidationError

from x10_catalog import CatalogEntry
from x10_models import Agent, Dataset, Distribution

ECMWF = Agent(name="ECMWF", roles=("producer", "licensor"), url="https://www.ecmwf.int")

JEU = Dataset(
    identifier="ecmwf-ifs-oper-0p25",
    title="IFS HRES, champs de surface, 0.25 degre",
    producer=ECMWF,
    domain="meteo",
    variables=("2t", "2d", "10u", "10v"),
)


def _distribution(origin: str, priority: int, dataset: str = JEU.identifier) -> Distribution:
    return Distribution(
        dataset=dataset,
        origin=origin,
        publisher=Agent(name=origin, roles=("publisher",)),
        access_url=f"https://exemple.invalid/{origin}",
        media_type="application/x-grib2",
        license="CC-BY-4.0",
        priority=priority,
    )


def _entree(*distributions: Distribution) -> CatalogEntry:
    return CatalogEntry(dataset=JEU, distributions=distributions or (_distribution("ecmwf", 10),))


# --- Redondance et ordre de résolution ----------------------------------------


def test_une_information_peut_avoir_plusieurs_origines():
    entree = _entree(
        _distribution("ecmwf", 10),
        _distribution("aws", 20),
        _distribution("google", 30),
        _distribution("azure", 40),
    )
    assert len(entree.distributions) == 4


def test_les_origines_sont_restituees_par_priorite_croissante():
    entree = _entree(
        _distribution("azure", 40),
        _distribution("ecmwf", 10),
        _distribution("google", 30),
        _distribution("aws", 20),
    )
    assert entree.origins() == ("ecmwf", "aws", "google", "azure")


def test_l_ordre_reste_deterministe_a_priorites_egales():
    """Sans tri secondaire, deux exécutions pourraient diverger."""
    entree = _entree(
        _distribution("google", 10),
        _distribution("aws", 10),
        _distribution("azure", 10),
    )
    assert entree.origins() == ("aws", "azure", "google")
    assert entree.origins() == _entree(*reversed(entree.distributions)).origins()


# --- Cohérence de l'entrée ------------------------------------------------------


def test_une_distribution_d_un_autre_jeu_est_refusee():
    """Une erreur de saisie silencieuse livrerait la mauvaise donnée."""
    with pytest.raises(ValidationError, match="ne se rapportant pas"):
        _entree(
            _distribution("ecmwf", 10),
            _distribution("aws", 20, dataset="un-autre-jeu"),
        )


def test_deux_distributions_de_meme_origine_sont_refusees():
    with pytest.raises(ValidationError, match="même origine"):
        _entree(_distribution("aws", 10), _distribution("aws", 20))


def test_une_entree_sans_distribution_est_refusee():
    with pytest.raises(ValidationError):
        CatalogEntry(dataset=JEU, distributions=())


# --- Sérialisation --------------------------------------------------------------


def test_l_entree_se_relit_depuis_son_json():
    entree = _entree(_distribution("ecmwf", 10), _distribution("aws", 20))
    assert CatalogEntry.model_validate_json(entree.model_dump_json()) == entree


def test_la_licence_peut_differer_d_une_origine_a_l_autre():
    """Un ré-exposant peut ajouter ses conditions à celles du producteur."""
    propre = _distribution("ecmwf", 10)
    reexpose = Distribution(
        dataset=JEU.identifier,
        origin="aws",
        publisher=Agent(name="un re-exposant", roles=("harvester", "publisher")),
        access_url="https://exemple.invalid/aws",
        media_type="application/x-grib2",
        license="CC-BY-4.0 AND conditions-du-reexposant",
        priority=20,
    )
    entree = _entree(propre, reexpose)
    assert {d.license for d in entree.distributions} == {
        "CC-BY-4.0",
        "CC-BY-4.0 AND conditions-du-reexposant",
    }
