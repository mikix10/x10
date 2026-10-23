"""GRIB2 — un paramètre de la plage locale sans table locale déclarée.

**Un invariant du format, pas un cas connu.** La section 1 donne à son
octet 11 la valeur zéro pour dire que les tables locales ne sont pas
employées, et que seules les entrées des tables maîtresses hors plage
réservée à l'usage local sont valides. Un code de cette plage dans un tel
fichier n'a donc aucune table où être lu.

Mesuré le 12/10/2026 sur 863 messages d'AROME 0,025° : quarante-deux portent
`(0, 16, 192)` alors que tous déclarent `localTablesVersion = 0`. Le
producteur publie bien la définition — `RFLCTVT` — mais hors du mécanisme
que le format prévoit pour la désigner, de sorte qu'aucun lecteur ne peut la
trouver depuis le fichier.
"""

from __future__ import annotations

import logging

import pytest
from fixtures_grib2 import Field, granule

grib2 = pytest.importorskip("x10_connectors.grib2")


# --- Le constat qui justifie le contrôle -------------------------------------


def test_eccodes_ne_resout_rien_et_ne_dit_rien(tmp_path):
    """Le cœur du sujet : trois clés à `unknown`, aucune exception."""
    eccodes = pytest.importorskip("eccodes")
    h = eccodes.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    try:
        eccodes.codes_set(h, "centre", 85)
        eccodes.codes_set(h, "discipline", 0)
        eccodes.codes_set(h, "parameterCategory", 16)
        eccodes.codes_set(h, "parameterNumber", 192)
        assert eccodes.codes_get(h, "localTablesVersion") == 0
        for key in ("shortName", "name", "units"):
            assert eccodes.codes_get(h, key) == "unknown", (
                f"{key} devrait rester indéterminé — si ecCodes le résout "
                "désormais, c'est une table locale embarquée, à relever"
            )
    finally:
        eccodes.codes_release(h)


# --- Le signalement ----------------------------------------------------------


def test_un_parametre_de_la_plage_normalisee_ne_declenche_rien(tmp_path):
    chemin = granule(tmp_path / "granule.grib2", [Field(category=0, number=0)])
    assert grib2.check_local_tables(grib2.open_granule(chemin)) is None


def test_un_numero_de_la_plage_locale_sans_table_locale_est_signale(tmp_path):
    chemin = granule(tmp_path / "granule.grib2", [Field(category=16, number=192)])
    ecart = grib2.check_local_tables(grib2.open_granule(chemin))
    assert ecart is not None
    assert "(0, 16, 192)" in ecart
    assert "no local table" in ecart


def test_une_categorie_de_la_plage_locale_est_signalee_aussi(tmp_path):
    """Le format réserve la plage dans les trois composantes, pas seulement
    dans le numéro de paramètre."""
    chemin = granule(tmp_path / "granule.grib2", [Field(category=192, number=1)])
    ecart = grib2.check_local_tables(grib2.open_granule(chemin))
    assert ecart is not None
    assert "(0, 192, 1)" in ecart


def test_une_table_locale_declaree_leve_le_signalement(tmp_path):
    """Le même code, mais le fichier dit cette fois où aller le lire."""
    chemin = granule(
        tmp_path / "granule.grib2",
        [Field(category=16, number=192, local_tables=1)],
    )
    assert grib2.check_local_tables(grib2.open_granule(chemin)) is None


def test_le_signalement_compte_les_codes_sans_les_repeter(tmp_path):
    """Deux échéances d'un même code ne font qu'un écart : c'est le code qui
    est en cause, pas le message.

    Les deux codes portent des types de niveau distincts, donc des hypercubes
    distincts. Sans cela ils se recouvriraient au nommage — voir
    `test_grib2_dropped_fields`.
    """
    chemin = granule(
        tmp_path / "granule.grib2",
        [
            Field(category=16, number=192, step=0),
            Field(category=16, number=192, step=1),
            Field(category=16, number=193, level_type=1, level=0, step=0),
            Field(category=16, number=193, level_type=1, level=0, step=1),
        ],
    )
    ecart = grib2.check_local_tables(grib2.open_granule(chemin, errors="ignore"))
    assert ecart is not None
    assert "2 parameter(s)" in ecart


def test_un_granule_vide_ne_declenche_rien():
    assert grib2.check_local_tables(()) is None


# --- Le branchement ----------------------------------------------------------


def test_l_ouverture_journalise_l_ecart_une_fois(tmp_path, caplog):
    chemin = granule(
        tmp_path / "granule.grib2",
        [Field(category=16, number=192, step=0), Field(category=16, number=192, step=1)],
    )
    with caplog.at_level(logging.WARNING, logger="x10_connectors"):
        grib2.open_granule(chemin)
    alertes = [e for e in caplog.records if "local-use range" in e.getMessage()]
    assert len(alertes) == 1, "une seule fois par granule, pas une fois par hypercube"
    assert alertes[0].__dict__["x10.granule"] == str(chemin)


def test_l_ouverture_ne_journalise_rien_sur_un_granule_conforme(tmp_path, caplog):
    chemin = granule(tmp_path / "granule.grib2", [Field(category=0, number=0)])
    with caplog.at_level(logging.WARNING, logger="x10_connectors"):
        grib2.open_granule(chemin)
    assert not [e for e in caplog.records if "local-use range" in e.getMessage()]


# --- L'écart ne refuse pas de servir ------------------------------------------


def test_le_granule_reste_decodable(tmp_path):
    """Le contrôle informe l'exploitant ; il ne retire rien du résultat."""
    datasets = grib2.open_granule(
        granule(
            tmp_path / "granule.grib2",
            [Field(category=16, number=192), Field(category=0, number=0)],
        )
    )
    assert sum(len(j.data_vars) for j in datasets) == 2
