"""Le registre : tenir les entrées, et répondre à un besoin par raffinement.

L'interrogation n'est pas une recherche qui rend une liste : c'est un
**dialogue** où l'on resserre, et où le catalogue dit ce qui reste ouvert sur
l'axe suivant. Ces tests rejouent ce dialogue.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from x10_catalog import CatalogEntry, Query, Registry
from x10_models import Agent, Dataset, Distribution, Variable

MF = Agent(name="Un producteur", roles=("producer", "licensor"))
DIFFUSEUR = Agent(name="Un diffuseur", roles=("distributor",))


def _variable(nom: str, *, reference: str | None = None, niveaux: tuple[float, ...] = ()):
    return Variable(
        standard_name=nom,
        units="K",
        level_reference=reference,
        levels=niveaux,
        level_units="m" if reference else None,
    )


def _entree(
    identifiant: str,
    *,
    variables: tuple[Variable, ...] = (),
    horizon: int | None = None,
    domaine: str = "meteo",
    origines: tuple[str, ...] = ("une-origine",),
) -> CatalogEntry:
    return CatalogEntry(
        dataset=Dataset(
            identifier=identifiant,
            title=f"Jeu {identifiant}",
            producer=MF,
            domain=domaine,
            variables=variables,
            max_step_hours=horizon,
        ),
        distributions=tuple(
            Distribution(
                dataset=identifiant,
                origin=o,
                provider=DIFFUSEUR,
                access_url=f"https://exemple.invalid/{o}",
                media_type="application/x-grib2",
                license="etalab-2.0",
                priority=rang,
            )
            for rang, o in enumerate(origines)
        ),
    )


# --- Tenir le registre --------------------------------------------------------


def test_un_registre_vide_ne_trouve_rien():
    vide = Registry()
    assert vide.entries == ()
    assert vide.get("absent") is None
    assert vide.origins("absent") == ()


def test_enregistrer_rend_un_nouveau_registre():
    """Gelé et fonctionnel : un registre partagé et mutable serait un état
    que rien n'exige, et deux appelants y liraient des choses différentes
    selon l'ordre."""
    avant = Registry()
    apres = avant.register(_entree("a"))
    assert avant.entries == ()
    assert len(apres.entries) == 1


def test_deux_entrees_de_meme_identifiant_sont_refusees():
    """Elles rendraient `get` ambigu, donc faux."""
    with pytest.raises(ValidationError, match="Duplicate dataset identifiers"):
        Registry(entries=(_entree("doublon"), _entree("doublon")))


def test_get_sur_un_absent_rend_none_et_ne_leve_pas():
    """Demander si une source est connue est une question légitime ; une
    exception obligerait tout appelant à l'entourer."""
    assert Registry(entries=(_entree("a"),)).get("b") is None


def test_les_origines_suivent_l_ordre_de_resolution():
    """Réutilise `CatalogEntry.resolution_order()` plutôt que de le refaire."""
    registre = Registry(entries=(_entree("a", origines=("premiere", "seconde")),))
    assert registre.origins("a") == ("premiere", "seconde")


# --- Le dialogue --------------------------------------------------------------


@pytest.fixture
def registre():
    return Registry(
        entries=(
            _entree(
                "court",
                variables=(_variable("air_temperature", reference="height", niveaux=(2.0,)),),
                horizon=51,
            ),
            _entree(
                "long",
                variables=(
                    _variable("air_temperature", reference="height", niveaux=(2.0, 50.0)),
                    _variable("wind_speed", reference="height", niveaux=(10.0,)),
                ),
                horizon=102,
            ),
            _entree(
                "autre_domaine", variables=(_variable("sea_surface_temperature"),), domaine="oceano"
            ),
        )
    )


def test_une_requete_vide_rend_tout(registre):
    assert len(registre.matches(Query())) == 3


def test_une_grandeur_restreint_aux_jeux_qui_la_servent(registre):
    trouves = {e.dataset.identifier for e in registre.matches(Query(standard_name="wind_speed"))}
    assert trouves == {"long"}


def test_les_facettes_disent_ce_qui_reste_ouvert(registre):
    """Après « la température », quels niveaux restent atteignables — et non
    tous ceux qui existent."""
    q = Query(standard_name="air_temperature")
    assert registre.facets(q, "level") == (2.0, 50.0)
    assert registre.facets(Query(standard_name="wind_speed"), "level") == (10.0,)


def test_l_axe_contraint_est_exclu_de_sa_propre_contrainte(registre):
    """Demander les niveaux alors qu'on en a fixé un rendrait une liste d'un
    élément, ce qui n'aide personne à choisir."""
    q = Query(standard_name="air_temperature", level=2.0)
    assert registre.facets(q, "level") == (2.0, 50.0)


def test_une_echeance_hors_capacite_elimine_le_jeu(registre):
    """`max_step_hours` est une **capacité** : AROME plafonne, ARPEGE va plus
    loin. Cela ne dit rien de la présence d'un réseau à l'instant t."""
    q = Query(standard_name="air_temperature", step_hours=80)
    assert {e.dataset.identifier for e in registre.matches(q)} == {"long"}


def test_un_jeu_sans_capacite_declaree_n_est_pas_masque(registre):
    """Ne pas savoir n'est pas « ne sait pas faire ». C'est à l'appelant de
    trancher, pas à nous de le cacher."""
    sans = Registry(entries=(_entree("inconnu", variables=(_variable("air_temperature"),)),))
    assert sans.matches(Query(standard_name="air_temperature", step_hours=999))


def test_le_dialogue_complet_se_rejoue(registre):
    q = Query(standard_name="air_temperature")
    assert len(registre.matches(q)) == 2
    assert registre.facets(q, "level") == (2.0, 50.0)
    q = q.narrow(level=50.0)
    assert {e.dataset.identifier for e in registre.matches(q)} == {"long"}


def test_narrow_ne_modifie_pas_la_requete_d_origine(registre):
    """Un dialogue doit pouvoir revenir en arrière sans rien défaire."""
    q = Query(standard_name="air_temperature")
    q.narrow(level=50.0)
    assert q.level is None


def test_un_axe_inconnu_leve_plutot_que_de_rendre_le_vide(registre):
    """Un nom mal orthographié rendrait une liste vide sans le dire."""
    with pytest.raises(ValueError, match="Unknown facet axis"):
        registre.facets(Query(), "niveau")


@pytest.mark.parametrize("axe", ["standard_name", "level_reference", "level", "domain", "producer"])
def test_chaque_axe_declare_sait_repondre(registre, axe):
    """Une facette déclarée mais muette serait pire qu'absente."""
    assert isinstance(registre.facets(Query(), axe), tuple)


# --- Charger et exporter ------------------------------------------------------


def test_le_rendu_json_est_deterministe(registre):
    """Deux dérivations sur les mêmes fichiers doivent donner le même texte,
    sans quoi un `git diff` montrerait du bruit."""
    assert registre.to_json() == registre.to_json()
    assert '"identifier": "court"' in registre.to_json()


def test_un_registre_se_relit_depuis_son_json(registre, tmp_path):
    cible = tmp_path / "registre.json"
    cible.write_text(registre.to_json(), encoding="utf-8")
    relu = Registry.from_file(cible)
    assert relu == registre


def test_l_export_rend_des_enregistrements_ogc_api_records(registre):
    """Garantie que notre modèle **n'empêche pas** l'export, vérifiée plutôt
    qu'affirmée. Ce n'est pas une prétention de conformité complète."""
    records = registre.to_records()
    assert len(records) == 3
    for r in records:
        assert r["type"] == "Feature"
        assert r["id"]
        assert "time" in r
        assert r["properties"]["title"]
        assert r["properties"]["type"] == "dataset"
        assert isinstance(r["links"], list)
        assert all({"href", "rel", "type"} <= set(lien) for lien in r["links"])
    assert json.dumps(records)  # serialisable tel quel


def test_l_export_liste_les_grandeurs_en_mots_cles(registre):
    record = next(r for r in registre.to_records() if r["id"] == "long")
    assert record["properties"]["keywords"] == ["air_temperature", "wind_speed"]


# --- La règle de dépendance ---------------------------------------------------


def test_le_catalogue_n_importe_pas_les_connecteurs():
    """Un registre ne décode rien : il reçoit des `Variable` déjà normalisées
    et ignore d'où elles viennent. L'inverse ferait entrer la pile GRIB dans
    un paquet qui n'en a aucun besoin."""
    from pathlib import Path

    import x10_catalog

    racine = Path(x10_catalog.__file__).parent
    fautifs = [p for p in racine.rglob("*.py") if "x10_connectors" in p.read_text(encoding="utf-8")]
    assert fautifs == [], f"le catalogue importe les connecteurs : {fautifs}"


# --- Les axes de requête que rien n'exerçait ----------------------------------
#
# Relevé à la relecture du 16/10/2026 : `level_reference` et `domain` étaient
# déclarés dans `Query` et dans `FACET_AXES`, et aucun test ne les exerçait
# **comme filtres**. Une capacité annoncée que rien ne prouve est la même
# faute qu'un verdict inatteignable.


def test_filtrer_par_reference_verticale(registre):
    sol = Registry(
        entries=(
            _entree("en_altitude", variables=(_variable("x", reference="height", niveaux=(2.0,)),)),
            _entree(
                "en_pression",
                variables=(_variable("x", reference="air_pressure", niveaux=(850.0,)),),
            ),
        )
    )
    trouves = sol.matches(Query(level_reference="air_pressure"))
    assert [e.dataset.identifier for e in trouves] == ["en_pression"]


def test_filtrer_par_domaine(registre):
    """Le fixture porte un jeu océano ; sans ce test, rien ne vérifiait que
    la contrainte de domaine le distingue."""
    trouves = registre.matches(Query(domain="oceano"))
    assert [e.dataset.identifier for e in trouves] == ["autre_domaine"]
    assert len(registre.matches(Query(domain="meteo"))) == 2


def test_les_contraintes_se_cumulent(registre):
    """Deux axes posés ensemble restreignent plus qu'un seul."""
    large = registre.matches(Query(domain="meteo"))
    etroit = registre.matches(Query(domain="meteo", standard_name="wind_speed"))
    assert len(etroit) < len(large)
    assert [e.dataset.identifier for e in etroit] == ["long"]


def test_la_facette_de_domaine_rend_les_domaines_servis(registre):
    assert registre.facets(Query(), "domain") == ("meteo", "oceano")


def test_la_facette_de_producteur_rend_les_producteurs(registre):
    assert registre.facets(Query(), "producer") == ("Un producteur",)


def test_la_facette_de_reference_verticale_se_restreint(registre):
    """Après une grandeur, quelles références verticales restent."""
    assert registre.facets(Query(standard_name="wind_speed"), "level_reference") == ("height",)
