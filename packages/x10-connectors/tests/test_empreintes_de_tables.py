"""Empreintes des tables de `grib2` et de `netcdf_cf` — ce qu'elles couvrent.

**Le défaut que ces tests ferment était silencieux et mesuré le 23/10/2026.**
`cf_tables_revision` énumérait sept tables à la main, et trois constantes
décidant pourtant du nom émis lui échappaient — `RATE_TOKENS`,
`INTEGRAL_PREFIX`, `ACCUMULATED_STEP_TYPES`. Ramener `RATE_TOKENS` à une
seule entrée aurait changé le `standard_name` de tout champ cumulé **sans
déplacer l'empreinte**, qui aurait alors rendu le faux témoignage qu'elle
existe pour empêcher.

La parade n'est pas une liste plus longue — elle rouillerait pareillement —
mais une **dérivation de l'espace de noms** : une table nouvelle y entre
d'elle-même, et ce qui reste à décider est ce qu'on en **exclut**.
"""

from __future__ import annotations

import pytest

from x10_connectors import grib2, netcdf_cf
from x10_connectors.base import module_constants, table_fingerprint

MODULES = (
    pytest.param(grib2, grib2.cf_tables_revision, id="grib2"),
    pytest.param(netcdf_cf, netcdf_cf.output_tables_revision, id="netcdf_cf"),
)


def _constantes(module) -> set[str]:
    """Les constantes publiques affectées dans le module, au sens de l'empreinte."""
    return set(module_constants(module))


@pytest.mark.parametrize(("module", "empreinte"), MODULES)
def test_l_empreinte_bouge_quand_une_table_couverte_change(module, empreinte, monkeypatch):
    """Le critère qui manquait : une table modifiée déplace la signature."""
    avant = empreinte()
    empreinte.cache_clear()

    nom = "RATE_TOKENS" if module is grib2 else "CELL_METHODS"
    monkeypatch.setattr(module, nom, ("sentinelle-qui-ne-decrit-rien",))
    apres = empreinte()
    empreinte.cache_clear()

    assert apres != avant, f"{nom} ne déplace pas l'empreinte de {module.__name__}"


@pytest.mark.parametrize(("module", "empreinte"), MODULES)
def test_l_empreinte_est_stable_d_un_appel_a_l_autre(module, empreinte):
    """Un `set` sans ordre ou une expression compilée la feraient varier sans
    que rien n'ait changé — ce qui la rendrait inutile au diagnostic."""
    empreinte.cache_clear()
    premier = table_fingerprint(module, exempt=module.UNFINGERPRINTED)
    second = table_fingerprint(module, exempt=module.UNFINGERPRINTED)
    assert premier == second


@pytest.mark.parametrize(("module", "empreinte"), MODULES)
def test_chaque_exemption_nomme_une_constante_qui_existe(module, empreinte):
    """Une exemption périmée est du poids mort, et masque qu'on a cessé d'y
    réfléchir."""
    inconnues = module.UNFINGERPRINTED - _constantes(module)
    assert not inconnues, f"exemption sans constante correspondante : {sorted(inconnues)}"


@pytest.mark.parametrize(("module", "empreinte"), MODULES)
def test_le_balayage_trouve_bien_les_tables(module, empreinte):
    """Une empreinte calculée sur rien passerait au vert pour la mauvaise
    raison. Vingt-quatre constantes au 23/10/2026 dans le moins fourni des
    deux ; le seuil détecte un balayage vide, pas un compte qui bougera."""
    couvertes = _constantes(module) - set(module.UNFINGERPRINTED)
    assert len(couvertes) >= 15, f"{len(couvertes)} constante(s) couverte(s)"


@pytest.mark.parametrize(("module", "empreinte"), MODULES)
def test_un_nom_importe_n_entre_pas_dans_l_empreinte(module, empreinte):
    """**La non-régression du défaut du 23/10/2026.**

    L'empreinte filtrait `vars(module)` sur les noms en capitales, ce qui y
    faisait entrer tout ce que le module avait *importé* sous un tel nom :
    `UTC`, `TYPE_CHECKING`, et surtout `AGENT`, qui porte la version du
    paquet. Une simple montée de version déplaçait donc l'empreinte des
    tables de sortie **sans qu'aucune table ait changé** — le faux témoignage
    inverse de celui qu'elle existe pour empêcher.
    """
    importes = {"AGENT", "UTC", "TYPE_CHECKING"} & set(vars(module))
    assert importes, "le module n'importe plus aucun nom en capitales : test à revoir"
    assert not importes & _constantes(module), f"un import entre dans l'empreinte : {importes}"


def test_une_montee_de_version_du_paquet_ne_deplace_pas_l_empreinte(monkeypatch):
    """Le même défaut, pris par son effet plutôt que par sa cause."""
    netcdf_cf.output_tables_revision.cache_clear()
    avant = netcdf_cf.output_tables_revision()

    netcdf_cf.output_tables_revision.cache_clear()
    monkeypatch.setattr(netcdf_cf, "AGENT", "x10-connectors 99.0.0")
    apres = netcdf_cf.output_tables_revision()
    netcdf_cf.output_tables_revision.cache_clear()

    assert avant == apres, "la version du paquet déplace l'empreinte des tables"


def test_les_deux_empreintes_sont_distinctes():
    """Si elles coïncidaient, l'une des deux ne servirait à rien."""
    assert grib2.cf_tables_revision() != netcdf_cf.output_tables_revision()


def test_l_outillage_ecrit_les_deux_empreintes():
    """Une empreinte qui n'atteint pas le fichier ne répond à aucune question."""
    outillage = netcdf_cf._outillage()
    assert f"x10 cf tables {grib2.cf_tables_revision()}" in outillage
    assert f"x10 output tables {netcdf_cf.output_tables_revision()}" in outillage
