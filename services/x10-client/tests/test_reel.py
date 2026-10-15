"""La chaîne entière sur une source réelle. Marqué `network`, donc exclu par défaut.

**Un seul test**, sur les sélections que les tests de `x10-connectors`
acquièrent déjà : notre crédit auprès d'un producteur est un bien commun et
fini, et un test de bout en bout qui invente sa propre sélection le dépense
sans rien démontrer de plus.

Ce qui est vérifié est un **invariant**, pas un cas connu : un granule dont
des paramètres disparaissent au décodage est rapporté amputé **et** nomme ce
qui manque. Un producteur qui corrigerait son paquet demain ne ferait pas
échouer ce test ; un producteur qui en casserait un autre le ferait.
"""

from __future__ import annotations

import pytest
from x10_client import Session, Verdict, constater

pytest.importorskip("cfgrib")
pytest.importorskip("netCDF4")


@pytest.mark.network
@pytest.mark.parametrize(
    ("modele", "paquet", "tranche"),
    [
        ("arome", "SP1", "00H06H"),
        ("arpege", "SP3", "049H072H"),
    ],
    ids=["surface AROME, attendu complet", "SP3 ARPEGE, amputé au 13/10/2026"],
)
def test_la_chaine_entiere_sur_un_granule_reel(tmp_path, monkeypatch, modele, paquet, tranche):
    """Acquérir, décoder, normaliser, écrire, contracter, rendre compte.

    **La mesure du 13/10/2026, qui est la raison de ce test.** Sur ARPEGE
    0,25° SP3 `049H072H` — 143 Mio —, 20 triplets entrent et 18 champs
    sortent : `(0, 17, 4)`, `(2, 3, 192)` et `(2, 3, 193)` disparaissent au
    nommage, sept triplets du fichier partageant `paramId = 0`. Avant ce
    chantier, l'enchaînement n'existait que dans du code de test et personne
    ne l'avait vu.
    """
    from x10_connectors import MeteoFrancePntRequest

    monkeypatch.setenv("X10_DESTINATION", str(tmp_path))
    session = Session.from_env()

    rapport = session.run(
        MeteoFrancePntRequest(model=modele, grid="0025", packages=(paquet,), time_ranges=(tranche,))
    )

    assert rapport.acquisition.outcome == "success"
    assert rapport.granules, "une acquisition réussie doit produire au moins un granule"

    for granule in rapport.granules:
        # L'invariant : ce qui manque est **nommé**, et le verdict le dit.
        assert (granule.verdict is Verdict.AMPUTE) == bool(granule.perdus)
        assert granule.champs_en_sortie > 0
        assert granule.champs_en_sortie <= granule.parametres_en_entree
        assert granule.contrat is not None
        assert all(sortie.is_file() for sortie in granule.sorties)

    assert rapport.verdict is not Verdict.NON_EVALUE

    # La licence suit la donnée jusque dans le fichier écrit : une sortie qui
    # la perd n'est pas exploitable par qui la reçoit.
    import netCDF4

    with netCDF4.Dataset(rapport.granules[0].sorties[0]) as fichier:
        assert getattr(fichier, "license", ""), "la licence doit atteindre le fichier"
        assert "CF-" in fichier.Conventions

    # L'exécution s'est accumulée, et se relit sans émettre une seule requête.
    (constat,) = constater(session.settings.etat)
    assert constat.executions == 1
    assert constat.taux_de_succes == 1.0
    assert constat.octets_total == rapport.acquisition.bytes_downloaded
