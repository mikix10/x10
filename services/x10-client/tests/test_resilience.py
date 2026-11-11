"""Ce qui se passe quand cela se passe mal, et ce qui en reste à l'historique.

Trois défauts mesurés le 16/10/2026, dont ces tests sont la clôture :

* une acquisition réussie **disparaissait** si le décodage échouait, parce
  que l'accumulation suivait la boucle de traitement ;
* les connecteurs n'émettant jamais `outcome="failure"`, le taux de succès
  valait structurellement `1.0` ;
* `NOT_ASSESSED` n'était produit nulle part.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fixtures_grib2_min import minimal_granule
from x10_client import ErrorType, NormaliseOptions, Session, Verdict, observe
from x10_client import session as module_session

from x10_connectors import ConnectorResult
from x10_models import Retrieval

pytest.importorskip("cfgrib")
pytest.importorskip("netCDF4")


class FakeRequest:
    """Une requête que seul le connecteur factice sait traiter."""


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setenv("X10_DESTINATION", str(tmp_path / "output"))
    return Session.from_env()


def _acquisition(artefacts: tuple[Path, ...]) -> ConnectorResult:
    return ConnectorResult(
        source="demo-source",
        outcome="success",
        run_id="r1",
        origin="demo",
        started_at=datetime.now(UTC),
        duration_ns=1_000_000,
        bytes_downloaded=2048,
        retrieval=Retrieval(
            dataset="d",
            origin="demo",
            retrieved_at=datetime.now(UTC),
            agent="a",
            artefacts=artefacts,
            license="etalab-2.0",
        ),
    )


def _wire(monkeypatch, artefacts: tuple[Path, ...] = (), *, raises: Exception | None = None):
    """Branche un connecteur factice, qui réussit ou lève."""

    class FakeConnector:
        source_name = "demo-source"

        def __init__(self, destination, request, **_):
            pass

        def fetch(self):
            if raises is not None:
                raise raises
            return _acquisition(artefacts)

    monkeypatch.setattr(module_session, "_connector_for", lambda _r: FakeConnector)


def _illisible(cible: Path) -> Path:
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(b"CECI N'EST PAS DU GRIB" * 10)
    return cible


# --- A : plus rien ne saute l'accumulation ------------------------------------


def test_un_granule_illisible_n_efface_pas_l_acquisition_reussie(session, tmp_path, monkeypatch):
    """Le défaut mesuré : `runs.jsonl` n'était pas même créé, et la
    disponibilité sous-déclarait exactement dans le cas où la source allait
    bien et où c'était nous qui échouions."""
    _wire(monkeypatch, (_illisible(tmp_path / "raw" / "illisible.grib2"),))

    report = session.run(FakeRequest())

    assert report.acquisition.outcome == "success"
    assert report.verdict is Verdict.FAILED
    assert (session.settings.state / "runs.jsonl").is_file()
    (constat,) = observe(session.settings.state)
    assert constat.runs == 1
    assert constat.successes == 1, "la source a bien répondu"
    assert constat.usable == 0, "mais nous n'en avons rien tiré"


def test_un_granule_fautif_n_emporte_pas_les_autres(session, tmp_path, monkeypatch):
    sain = minimal_granule(tmp_path / "raw" / "sain.grib2", ((0, 0),))
    _wire(monkeypatch, (sain, _illisible(tmp_path / "raw" / "casse.grib2")))

    report = session.run(FakeRequest())

    assert report.complete_count == 1
    assert report.failed_count == 1
    assert report.outputs, "le granule sain doit avoir été écrit"


def test_une_acquisition_qui_leve_est_rapportee_et_accumulee(session, monkeypatch):
    """Les connecteurs lèvent au lieu de rendre `failure`, ce qui est leur
    droit — mais sans rattrapage aucune défaillance n'entrerait jamais dans
    l'historique."""
    _wire(monkeypatch, raises=RuntimeError("le service ne répond pas"))

    report = session.run(FakeRequest())

    assert report.acquisition.outcome == "failure"
    assert "le service ne répond pas" in report.acquisition.message
    assert report.verdict is Verdict.NOT_ASSESSED
    assert report.granule_count == 0
    assert report.acquisition.source == "demo-source", "la source est nommée malgré l'échec"


def test_le_taux_de_succes_n_est_plus_structurellement_un(session, tmp_path, monkeypatch):
    """La preuve que la mesure de disponibilité n'est plus vide de sens."""
    _wire(monkeypatch, (minimal_granule(tmp_path / "raw" / "ok.grib2", ((0, 0),)),))
    session.run(FakeRequest())
    _wire(monkeypatch, raises=RuntimeError("panne"))
    session.run(FakeRequest())

    (constat,) = observe(session.settings.state)
    assert constat.runs == 2
    assert constat.success_rate == 0.5
    assert constat.usable_rate == 0.5


def test_une_requete_sans_connecteur_n_entre_pas_a_l_historique(session):
    """C'est une erreur de l'appelant, pas une défaillance de la source.
    L'inscrire ferait chuter le taux d'un producteur jamais contacté."""
    with pytest.raises(module_session.UnknownRequest):
        session.run(FakeRequest())
    assert not (session.settings.state / "runs.jsonl").exists()


# --- B : les quatre verdicts sont atteignables --------------------------------


def test_les_quatre_verdicts_sont_produits_par_la_chaine(session, tmp_path, monkeypatch):
    """Une valeur inatteignable serait une réserve que personne n'émet et que
    tout consommateur devrait pourtant gérer."""
    sain = minimal_granule(tmp_path / "raw" / "a.grib2", ((0, 0),))
    ampute = minimal_granule(tmp_path / "raw" / "b.grib2", ((16, 192), (16, 193)))
    _wire(monkeypatch, (sain, ampute, _illisible(tmp_path / "raw" / "c.grib2")))
    produits = {g.verdict for g in session.run(FakeRequest()).granules}

    _wire(monkeypatch, raises=RuntimeError("panne"))
    produits.add(session.run(FakeRequest()).verdict)

    assert produits == set(Verdict), "chaque valeur du vocabulaire doit être émise"


def test_un_echec_porte_sa_categorie_et_non_une_phrase_seule(session, tmp_path, monkeypatch):
    _wire(monkeypatch, (_illisible(tmp_path / "raw" / "x.grib2"),))
    granule = session.run(FakeRequest()).granules[0]
    assert granule.verdict is Verdict.FAILED
    assert granule.error_type is ErrorType.DECODE
    assert granule.reason


# --- C : les étapes publiques -------------------------------------------------


def test_normalise_rejoue_une_acquisition_sans_retelecharger(session, tmp_path, monkeypatch):
    """L'usage qui motivait ce paquet : un carnet garde son `ConnectorResult`
    et rejoue la normalisation sans rien redemander au producteur."""
    import socket

    acquisition = _acquisition((minimal_granule(tmp_path / "raw" / "g.grib2", ((0, 0),)),))

    def forbidden(*_a, **_k):
        raise AssertionError("normalise() a ouvert une connexion")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)

    premier = session.normalise(acquisition)
    second = session.normalise(acquisition)
    assert premier[0].contract == second[0].contract


def test_normalise_granule_traite_un_fichier_sans_acquisition(session, tmp_path):
    """Un granule conservé hors dépôt se traite sans passer par un connecteur."""
    granule = session.normalise_granule(minimal_granule(tmp_path / "seul.grib2", ((0, 0),)))
    assert granule.verdict is Verdict.COMPLETE
    assert granule.outputs


def test_appele_directement_normalise_granule_leve(session, tmp_path):
    """Le défaut est celui de la bibliothèque : qui l'appelle veut la trace."""
    with pytest.raises(Exception, match=r"(?i)edition|grib|support"):
        session.normalise_granule(_illisible(tmp_path / "x.grib2"))


def test_la_meme_entree_leve_ou_rend_compte_selon_l_option(session, tmp_path):
    """La divergence entre appel direct et `run()` cesse d'être une surprise
    câblée : c'est une valeur par défaut qu'on lit."""
    source = _illisible(tmp_path / "y.grib2")
    granule = session.normalise_granule(source, options=NormaliseOptions(errors="report"))
    assert granule.verdict is Verdict.FAILED


def test_write_false_n_ecrit_rien_et_rend_tout_de_meme_le_contrat(session, tmp_path):
    """Le contrat se calcule sur les jeux décodés, pas sur les fichiers."""
    source = minimal_granule(tmp_path / "sec.grib2", ((0, 0),))
    granule = session.normalise_granule(source, options=NormaliseOptions(write=False))
    assert granule.outputs == ()
    assert granule.contract is not None
    assert granule.fields_out == 1
    assert not list(session.settings.destination.glob("*.nc"))


def test_la_tolerance_au_recouvrement_est_une_option(session, tmp_path):
    source = minimal_granule(tmp_path / "rec.grib2", ((16, 192), (16, 193)))

    tolere = session.normalise_granule(source)
    assert tolere.verdict is Verdict.PARTIAL

    with pytest.raises(Exception, match="do not appear"):
        session.normalise_granule(source, options=NormaliseOptions(dropped_fields="raise"))


def test_l_unite_intraduisible_est_toleree_de_bout_en_bout(session, tmp_path):
    """`strict_units` doit gouverner toute la chaîne, pas la seule écriture.

    Le code GRIB2 `(0, 15, 1)` — réflectivité de base — sort d'ecCodes en
    `dB`, absente de la table fermée `UDUNITS`. L'option existe exactement
    pour ce cas ; encore faut-il qu'elle soit consultée **avant** que quoi
    que ce soit ne lève.

    Mesuré le 23/10/2026 : le contrat de sortie était calculé avant
    l'écriture et sans l'option, de sorte que `strict_units=False` paraissait
    sans effet. Le granule échouait trois lignes avant d'atteindre le code
    que l'option gouverne.
    """
    source = minimal_granule(tmp_path / "db.grib2", ((15, 1),))

    with pytest.raises(Exception, match="UDUNITS"):
        session.normalise_granule(source)

    tolere = session.normalise_granule(source, options=NormaliseOptions(strict_units=False))
    assert tolere.verdict is Verdict.COMPLETE
    assert tolere.outputs


def test_run_est_la_composition_des_etapes_publiques(session, tmp_path, monkeypatch):
    """Si les deux chemins divergeaient, le découpage serait faux."""
    source = minimal_granule(tmp_path / "raw" / "comp.grib2", ((0, 0), (2, 2)))
    _wire(monkeypatch, (source,))

    enchaine = session.run(FakeRequest())
    a_la_main = session.normalise(session.acquire(FakeRequest()))

    assert enchaine.granules[0].contract == a_la_main[0].contract
    assert enchaine.granules[0].fields_out == a_la_main[0].fields_out


def test_chaque_execution_laisse_une_ligne_relisible(session, tmp_path, monkeypatch):
    _wire(monkeypatch, (minimal_granule(tmp_path / "raw" / "j.grib2", ((0, 0),)),))
    session.run(FakeRequest())
    session.run(FakeRequest())

    lignes = (session.settings.state / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lignes) == 2
    assert all(json.loads(x)["verdict"] == "complete" for x in lignes)
