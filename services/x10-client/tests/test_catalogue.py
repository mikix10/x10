"""La boucle fermée : du besoin au téléchargement, en passant par le registre.

**Aucune méthode n'est ajoutée au client pour cela, et c'est délibéré.** Tout
ce qu'un assemblage ferait ici serait de réexporter `registry.origins()` et
`registry.matches()` sous un autre nom. Un client qui enveloppe sans rien
ajouter devient un paquet fantôme, et le socle se vide sans que personne le
décide — la règle est écrite dans le `README` du membre.

Ces tests sont donc la **démonstration exécutable** que la boucle se ferme
avec les pièces existantes, et l'exemple que le `README` reprend.
"""

from __future__ import annotations

import pytest

from x10_catalog import CatalogEntry, Query, Registry
from x10_models import Agent, Dataset, Distribution, Variable

PRODUCTEUR = Agent(name="Un producteur", roles=("producer", "licensor"))
DIFFUSEUR = Agent(name="Un diffuseur", roles=("distributor",))


@pytest.fixture
def registre():
    """Deux jeux, dont un à plusieurs origines — le cas où l'ordre compte."""
    jeux = (
        ("jeu-une-origine", ("seule",), 51),
        ("jeu-redondant", ("preferee", "secours"), 102),
    )
    entrees = []
    for identifiant, origines, horizon in jeux:
        entrees.append(
            CatalogEntry(
                dataset=Dataset(
                    identifier=identifiant,
                    title=identifiant,
                    producer=PRODUCTEUR,
                    domain="meteo",
                    variables=(
                        Variable(
                            standard_name="air_temperature",
                            units="K",
                            level_reference="height",
                            levels=(2.0,),
                            level_units="m",
                        ),
                    ),
                    max_step_hours=horizon,
                ),
                distributions=tuple(
                    Distribution(
                        dataset=identifiant,
                        origin=origine,
                        provider=DIFFUSEUR,
                        access_url=f"https://exemple.invalid/{origine}",
                        media_type="application/x-grib2",
                        license="etalab-2.0",
                        priority=rang,
                    )
                    for rang, origine in enumerate(origines)
                ),
            )
        )
    return Registry(entries=tuple(entrees))


def test_du_besoin_aux_origines_a_tenter(registre):
    """La boucle, en trois lignes : chercher, choisir, obtenir l'ordre.

    C'est l'appelant qui résout et transmet l'ordre des origines ; un
    connecteur ignore l'existence d'un catalogue.
    """
    candidats = registre.matches(Query(standard_name="air_temperature", step_hours=80))

    assert [e.dataset.identifier for e in candidats] == ["jeu-redondant"]
    assert registre.origins("jeu-redondant") == ("preferee", "secours")


def test_la_sortie_du_registre_est_l_entree_du_connecteur():
    """Le point entier de la boucle : **aucune traduction** entre les deux.

    L'ordre de repli que le registre calcule est passé tel quel à la requête,
    et c'est ce passage qui est vérifié — pas qu'un objet rende ce qu'on vient
    de lui donner.
    """
    from x10_connectors.ecmwf_ifs import ORIGINS, EcmwfIfsRequest

    # Un registre dont les origines sont celles qu'ECMWF connaît, déclarées
    # dans le désordre et avec des priorités qui le remettent.
    entree = CatalogEntry(
        dataset=Dataset(
            identifier="ifs",
            title="IFS",
            producer=PRODUCTEUR,
            domain="meteo",
        ),
        distributions=tuple(
            Distribution(
                dataset="ifs",
                origin=origine,
                provider=DIFFUSEUR,
                access_url=f"https://exemple.invalid/{origine}",
                media_type="application/x-grib2",
                license="CC-BY-4.0",
                priority=rang,
            )
            for rang, origine in enumerate(("google", "aws", "ecmwf"))
        ),
    )
    ordre = Registry(entries=(entree,)).origins("ifs")
    assert ordre == ("google", "aws", "ecmwf")
    assert set(ordre) <= set(ORIGINS)

    requete = EcmwfIfsRequest(origins=ordre)
    assert requete.origins == ordre, "l'ordre de repli traverse sans traduction"


def test_une_origine_inconnue_du_connecteur_est_refusee_a_la_construction():
    """Le registre ne valide pas contre le vocabulaire d'un connecteur — il
    ne le connaît pas. C'est la requête qui refuse, et c'est la bonne place :
    chaque source a ses origines."""
    from x10_connectors.ecmwf_ifs import EcmwfIfsRequest

    entree = CatalogEntry(
        dataset=Dataset(identifier="x", title="X", producer=PRODUCTEUR, domain="meteo"),
        distributions=(
            Distribution(
                dataset="x",
                origin="un-diffuseur-maison",
                provider=DIFFUSEUR,
                access_url="https://exemple.invalid/x",
                media_type="application/x-grib2",
                license="CC-BY-4.0",
            ),
        ),
    )
    ordre = Registry(entries=(entree,)).origins("x")
    assert ordre == ("un-diffuseur-maison",), "le registre l'accepte"

    with pytest.raises(ValueError, match="Unknown origin"):
        EcmwfIfsRequest(origins=ordre)


def test_le_registre_reel_se_charge_et_repond(registre):
    """Le catalogue commité, dérivé de granules réels, est utilisable tel
    quel par un client."""
    from pathlib import Path

    import x10_catalog

    source = Path(x10_catalog.__file__).parent / "data" / "meteofrance.json"
    reel = Registry.from_file(source)

    assert len(reel.entries) == 2
    trouves = reel.matches(Query(standard_name="air_temperature"))
    assert trouves, "la température doit être servie par au moins un jeu"
    assert reel.origins(trouves[0].dataset.identifier) == ("data.gouv.fr",)


def test_le_catalogue_reel_porte_la_provenance_de_sa_derivation():
    """Sans elle, une divergence future serait inattribuable : impossible de
    dire si le producteur a bougé ou si notre outillage a changé."""
    from pathlib import Path

    import x10_catalog

    reel = Registry.from_file(Path(x10_catalog.__file__).parent / "data" / "meteofrance.json")
    for entree in reel.entries:
        source = entree.dataset.inventory_source
        assert source is not None
        assert source.toolchain.startswith("eccodes ")
        assert source.tables_version is not None
        assert source.granules, "les granules dérivés doivent être nommés"
