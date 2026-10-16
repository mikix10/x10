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
from x10_client import Session, Verdict, observe

pytest.importorskip("cfgrib")
pytest.importorskip("netCDF4")


@pytest.mark.network
@pytest.mark.parametrize(
    ("model", "package", "time_range"),
    [
        ("arome", "SP1", "00H06H"),
        ("arpege", "SP3", "049H072H"),
    ],
    ids=["surface AROME, attendu complet", "SP3 ARPEGE, amputé au 13/10/2026"],
)
def test_la_chaine_entiere_sur_un_granule_reel(tmp_path, monkeypatch, model, package, time_range):
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

    report = session.run(
        MeteoFrancePntRequest(
            model=model, grid="0025", packages=(package,), time_ranges=(time_range,)
        )
    )

    assert report.acquisition.outcome == "success"
    assert report.granules, "une acquisition réussie doit produire au moins un granule"

    for granule in report.granules:
        # L'invariant : ce qui manque est **nommé**, et le verdict le dit.
        assert (granule.verdict is Verdict.PARTIAL) == bool(granule.dropped)
        assert granule.fields_out > 0
        assert granule.fields_out <= granule.parameters_in
        assert granule.contract is not None
        assert all(output.is_file() for output in granule.outputs)

    assert report.verdict is not Verdict.NOT_ASSESSED

    # La licence suit la donnée jusque dans le fichier écrit : une sortie qui
    # la perd n'est pas exploitable par qui la reçoit.
    import netCDF4

    with netCDF4.Dataset(report.granules[0].outputs[0]) as handle:
        assert getattr(handle, "license", ""), "la licence doit atteindre le fichier"
        assert "CF-" in handle.Conventions

    # L'exécution s'est accumulée, et se relit sans émettre une seule requête.
    (availability,) = observe(session.settings.state)
    assert availability.runs == 1
    assert availability.success_rate == 1.0
    assert availability.bytes_total == report.acquisition.bytes_downloaded
