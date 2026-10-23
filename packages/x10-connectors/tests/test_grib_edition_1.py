"""GRIB **édition 1** : lecture, identité et nommage.

L'édition 1 n'est pas un vestige. Mesuré le 20/10/2026 : ERA5 et CAMS chez
Copernicus, MFWAM, WaveWatch III et HYCOM2D chez Météo-France — la réanalyse
la plus utilisée au monde, et tout l'océan.

**La lecture n'a jamais été en cause.** `cfgrib` ouvre ces granules sans
difficulté, y compris avec nos options entières. L'unique obstacle était
`file_triplets`, qui demandait `discipline` sans garde ; voir X10-DIV-0013
au registre des écarts.

Ces tests tournent **hors ligne**, sur des messages construits en mémoire.
"""

from __future__ import annotations

from pathlib import Path

import fixtures_grib2 as f2
import fixtures_grib_edition_1 as f1
import pytest
import xarray as xr

from x10_connectors.grib2 import (
    CF_BY_PARAM_ID,
    PARAM_ID_UNRESOLVED,
    apply_cf_names,
    cf_name_for_param_id,
    dropped_fields,
    file_identities,
    file_triplets,
    identity,
    open_granule,
    param_id,
)

#: La température à 2 m dans la table locale d'ECMWF : le champ le plus
#: courant qui soit, et celui dont l'absence de nom se remarquerait le plus.
TEMPERATURE = f1.Champ(table2_version=128, indicator=167)
#: La composante zonale du vent à 10 m, dans la même table.
VENT_U = f1.Champ(table2_version=128, indicator=165)


@pytest.fixture
def granule_edition_1(tmp_path: Path) -> Path:
    return f1.granule(tmp_path / "edition1.grib", [TEMPERATURE, VENT_U])


def test_un_granule_d_edition_1_s_ouvre(granule_edition_1: Path) -> None:
    """Le cas qui levait : la chaîne entière, sur un fichier d'édition 1."""
    jeux = open_granule(granule_edition_1)
    variables = {str(n) for ds in jeux for n in ds.data_vars}
    assert variables == {"t2m", "u10"}


def test_les_triplets_d_un_fichier_d_edition_1_sont_vides_sans_lever(
    granule_edition_1: Path,
) -> None:
    """Un fichier d'édition 1 n'a aucun triplet, et le dire n'est pas échouer.

    Sans la garde, `eccodes.codes_get(h, "discipline")` levait
    `KeyValueNotFoundError`, et l'exception remontait jusqu'à `open_granule`.
    Rendre l'ensemble vide est la réponse juste : la fonction dit quels
    triplets le fichier contient, et il n'en contient aucun.
    """
    assert file_triplets(granule_edition_1) == frozenset()


def test_l_identite_suit_l_edition_du_message(granule_edition_1: Path, tmp_path: Path) -> None:
    """Chaque édition identifie ses paramètres à sa façon, et on ne l'uniformise pas.

    L'édition est préfixée pour qu'un triplet et un couple ne puissent pas
    se confondre par accident.
    """
    assert file_identities(granule_edition_1) == {(1, 128, 167), (1, 128, 165)}

    edition_2 = f2.granule(tmp_path / "edition2.grib", [f2.Field(category=0, number=0)])
    identites = file_identities(edition_2)
    assert all(code[0] == 2 and len(code) == 4 for code in identites)


def test_un_champ_perdu_est_detecte_en_edition_1(granule_edition_1: Path) -> None:
    """La détection de perte ne doit pas devenir aveugle hors de l'édition 2.

    Elle reposait sur le triplet ; sur un fichier d'édition 1 elle aurait
    rendu « rien perdu » quoi qu'il arrive — un silence pire que l'échec,
    puisque le compte rendu aurait dit `success`.
    """
    assert dropped_fields(granule_edition_1, ()) == {(1, 128, 167), (1, 128, 165)}
    assert dropped_fields(granule_edition_1, open_granule(granule_edition_1)) == frozenset()


def test_le_nom_cf_vient_du_second_passage_par_param_id(granule_edition_1: Path) -> None:
    """ecCodes connaît le nom mais ne l'expose pas en édition 1.

    Le granule porte `cfName = unknown` sur ses deux champs ; les deux se
    nomment pourtant, parce que leur `paramId` est relu par un handle
    d'édition 2. Voir X10-DIV-0017.
    """
    noms = {
        str(n): v.attrs.get("standard_name")
        for ds in open_granule(granule_edition_1)
        for n, v in apply_cf_names(ds).data_vars.items()
    }
    assert noms == {"t2m": "air_temperature", "u10": "eastward_wind"}


def test_eccodes_ne_rend_pas_le_nom_sur_un_message_d_edition_1(
    granule_edition_1: Path,
) -> None:
    """L'asymétrie elle-même, constatée plutôt que supposée.

    C'est elle qui justifie le second passage : sans ce constat, on pourrait
    croire que l'édition 1 n'est pas nommable.
    """
    bruts = [
        v.attrs.get("GRIB_cfName")
        for ds in open_granule(granule_edition_1)
        for v in ds.data_vars.values()
    ]
    assert all(nom in (None, "unknown") for nom in bruts), bruts
    assert cf_name_for_param_id(167) == "air_temperature"


def test_un_param_id_nul_n_identifie_rien() -> None:
    """Zéro veut dire « non résolu », pas « paramètre zéro ».

    Deux champs de tables locales de Météo-France le portent tous les deux ;
    s'en servir comme identité les confondrait, et c'est exactement la
    confusion que la détection de perte existe pour voir.
    """
    variable = xr.DataArray([0.0], attrs={"GRIB_paramId": PARAM_ID_UNRESOLVED})
    assert param_id(variable) is None
    assert identity(variable) is None


def test_un_identifiant_deja_tranche_n_est_pas_redemande_a_eccodes() -> None:
    """Un `paramId` qu'ecCodes ignore le fait écrire sur la sortie d'erreur.

    Une bibliothèque n'a pas à polluer la sortie de l'application qui
    l'intègre. Nous ne pouvons pas l'en empêcher ; nous pouvons ne pas la
    provoquer pour un identifiant dont nous avons déjà tranché le nom.
    """
    orphelin = 3100
    assert orphelin in CF_BY_PARAM_ID
    assert cf_name_for_param_id(orphelin) is None


def test_notre_table_par_param_id_comble_ce_qu_aucune_autre_voie_n_atteint() -> None:
    """Le dernier recours, et il reste un recours.

    Trois champs sur quatorze étaient déjà nommés, six le sont par le second
    passage ; cette table ne vise que le reste.
    """
    variable = xr.DataArray([0.0], attrs={"GRIB_paramId": 3100})
    nomme = apply_cf_names(xr.Dataset({"swh": variable}))
    assert nomme["swh"].attrs["standard_name"] == CF_BY_PARAM_ID[3100]
