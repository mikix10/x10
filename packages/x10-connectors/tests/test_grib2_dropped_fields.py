"""GRIB2 — deux paramètres de même nom court, et l'un écrase l'autre.

**Le troisième silence de la chaîne**, mesuré le 13/10/2026. `cfgrib` nomme
ses variables d'après le nom court qu'ecCodes résout. Deux codes qu'ecCodes
ne sait pas résoudre reçoivent donc tous deux `unknown`, et le second écrase
le premier **à l'intérieur d'un même jeu**. Quatre messages entrent, un champ
sort — sans exception, sans avertissement, et le compte rendu dirait
`success` sur une donnée amputée.

C'est exactement la faute pour laquelle `errors` a été passé à `"raise"` :
une sortie fausse se propage là où un échec visible se corrige. La perte est
donc traitée sous le même paramètre.

Le cas n'est pas théorique : `(0, 6, 11)` et `(0, 17, 4)`, du paquet SP3
d'ARPEGE 0,25°, ne sont résolus ni par ecCodes ni par la table publiée par
le producteur.
"""

from __future__ import annotations

import logging

import numpy as np
import pytest
from fixtures_grib2 import Field, granule

grib2 = pytest.importorskip("x10_connectors.grib2")


# --- Le constat --------------------------------------------------------------


def test_deux_codes_irresolus_se_recouvrent_au_nommage(tmp_path):
    """Le cœur du sujet. Si `cfgrib` les distinguait, ce module serait inutile."""
    chemin = granule(
        tmp_path / "granule.grib2",
        [
            Field(category=16, number=192, values=np.full(45, 111.0)),
            Field(category=16, number=193, values=np.full(45, 222.0)),
        ],
    )
    datasets = grib2.open_granule(chemin, errors="ignore")
    champs = [(nom, v) for jeu in datasets for nom, v in jeu.data_vars.items()]
    assert len(champs) == 1, "deux messages, un seul champ : c'est la perte"
    nom, var = champs[0]
    assert nom == "unknown"
    # Le survivant reste cohérent : ses attributs et ses valeurs sont du même
    # paramètre. La faute est une disparition, pas un mélange.
    assert grib2.triplet(var) == (0, 16, 192)
    assert np.unique(np.asarray(var.values)).tolist() == [111.0]


def test_ni_errors_raise_ni_compat_equals_ne_le_voient(tmp_path):
    """Les deux garde-fous existants portent ailleurs : sur les messages
    illisibles pour l'un, sur la fusion de jeux pour l'autre."""
    chemin = granule(
        tmp_path / "granule.grib2",
        [Field(category=16, number=192), Field(category=16, number=193)],
    )
    cfgrib = pytest.importorskip("cfgrib")
    datasets = cfgrib.open_datasets(
        str(chemin),
        backend_kwargs={**grib2.OPTIONS_CFGRIB, "errors": "raise"},
    )
    assert sum(len(j.data_vars) for j in datasets) == 1, (
        "cfgrib perd le champ sans rien lever, options strictes comprises"
    )


def test_le_recouvrement_ne_touche_pas_que_les_codes_irresolus(tmp_path):
    """Deux codes **parfaitement résolus** peuvent partager un nom court.

    Relevé le 13/10/2026 sur 365 codes des disciplines 0 et 10 : cinq noms
    courts en désignent plusieurs. `(0, 3, 6)` et `(0, 3, 34)` reçoivent
    tous deux `h` — et `tmax` désigne aussi bien une température maximale
    qu'une période de houle. Le défaut n'est donc pas réservé aux codes
    exotiques, et c'est ce qui justifie un contrôle plutôt qu'une liste.
    """
    chemin = granule(
        tmp_path / "granule.grib2",
        [
            Field(category=3, number=6, values=np.full(45, 111.0)),
            Field(category=3, number=34, values=np.full(45, 222.0)),
        ],
    )
    datasets = grib2.open_granule(chemin, errors="ignore")
    assert sum(len(j.data_vars) for j in datasets) == 1
    assert grib2.dropped_fields(chemin, datasets) == {(2, 0, 3, 34)}


# --- La lecture des en-têtes --------------------------------------------------


def test_les_triplets_du_fichier_sont_tous_releves(tmp_path):
    chemin = granule(
        tmp_path / "granule.grib2",
        [
            Field(category=0, number=0),
            Field(category=16, number=192),
            Field(category=16, number=193),
        ],
    )
    assert grib2.file_triplets(chemin) == {
        (0, 0, 0),
        (0, 16, 192),
        (0, 16, 193),
    }


def test_un_echeancier_ne_compte_qu_une_fois(tmp_path):
    """C'est un ensemble de codes, pas un compte de messages."""
    chemin = granule(
        tmp_path / "granule.grib2",
        [Field(category=0, number=0, step=s) for s in range(4)],
    )
    assert grib2.file_triplets(chemin) == {(0, 0, 0)}


# --- La détection -------------------------------------------------------------


def test_aucune_perte_sur_un_granule_ordinaire(tmp_path):
    chemin = granule(
        tmp_path / "granule.grib2",
        [Field(category=0, number=0), Field(category=2, number=2)],
    )
    datasets = grib2.open_granule(chemin)
    assert grib2.dropped_fields(chemin, datasets) == frozenset()


def test_la_perte_est_nommee_par_le_code_disparu(tmp_path):
    chemin = granule(
        tmp_path / "granule.grib2",
        [Field(category=16, number=192), Field(category=16, number=193)],
    )
    datasets = grib2.open_granule(chemin, errors="ignore")
    assert grib2.dropped_fields(chemin, datasets) == {(2, 0, 16, 193)}


def test_des_types_de_niveau_distincts_ne_perdent_rien(tmp_path):
    """Deux hypercubes distincts, donc deux jeux : le nom ne collisionne pas."""
    chemin = granule(
        tmp_path / "granule.grib2",
        [
            Field(category=16, number=192),
            Field(category=16, number=193, level_type=1, level=0),
        ],
    )
    datasets = grib2.open_granule(chemin)
    assert grib2.dropped_fields(chemin, datasets) == frozenset()


# --- Le branchement -----------------------------------------------------------


def test_l_ouverture_leve_par_defaut(tmp_path):
    chemin = granule(
        tmp_path / "granule.grib2",
        [Field(category=16, number=192), Field(category=16, number=193)],
    )
    with pytest.raises(grib2.DroppedFieldsError) as capture:
        grib2.open_granule(chemin)
    assert "GRIB2 (0, 16, 193)" in str(capture.value)


def test_la_tolerance_reste_accessible_et_journalise(tmp_path, caplog):
    chemin = granule(
        tmp_path / "granule.grib2",
        [Field(category=16, number=192), Field(category=16, number=193)],
    )
    with caplog.at_level(logging.WARNING, logger="x10_connectors"):
        datasets = grib2.open_granule(chemin, errors="warn")
    assert len(datasets) == 1
    alertes = [e for e in caplog.records if "do not appear in the" in e.getMessage()]
    assert len(alertes) == 1
    assert alertes[0].__dict__["x10.granule"] == str(chemin)


def test_ignore_ne_journalise_rien(tmp_path, caplog):
    """Qui demande le silence l'obtient, et l'assume."""
    chemin = granule(
        tmp_path / "granule.grib2",
        [Field(category=16, number=192), Field(category=16, number=193)],
    )
    with caplog.at_level(logging.WARNING, logger="x10_connectors"):
        grib2.open_granule(chemin, errors="ignore")
    assert not [e for e in caplog.records if "do not appear in the" in e.getMessage()]


# --- Le relevé n'accuse pas le décodage d'un message illisible ---------------


def test_un_message_illisible_est_passe_sans_accuser_le_decodage(tmp_path):
    """Le relevé dit ce que le fichier contient. D'un message qu'on ne sait
    pas lire on ne peut rien affirmer, et le compter comme perdu imputerait
    au décodage une faute qui n'est pas la sienne — la lisibilité relève du
    paramètre `errors`, en amont."""
    chemin = tmp_path / "granule.grib2"
    valide = granule(tmp_path / "valide.grib2", [Field(category=0, number=0)])
    chemin.write_bytes(valide.read_bytes() + b"GRIB" + b"\x00" * 24)
    assert grib2.file_triplets(chemin) == {(0, 0, 0)}
