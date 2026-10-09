"""Tests du décodage et de la normalisation, sans aucun accès réseau.

Les paquets sont fabriqués en mémoire par `fixtures_grib` : quelques
kilo-octets suffisent à exercer la géométrie, les valeurs manquantes, les
cumuls et le vent.
"""

from __future__ import annotations

import numpy as np
import pytest
from fixtures_grib import GRILLE_PAR_DEFAUT, Champ, champs_vent, paquet

from x10_connectors.decoding import (
    CF_STANDARD_NAMES,
    OPTIONS_CFGRIB,
    SANS_NOM_CF,
    VENT_DERIVE,
    apply_cf_names,
    drop_derived_wind,
    normalise,
    open_granule,
    triplet,
    wind_from_direction,
    wind_speed,
)

N = int(GRILLE_PAR_DEFAUT["ni"] * GRILLE_PAR_DEFAUT["nj"])


def _jeu_vent(tmp_path, steps=(0,)):
    fichier = paquet(tmp_path / "vent.grib2", champs_vent(steps=steps))
    jeux = open_granule(fichier)
    assert len(jeux) == 1
    return jeux[0]


# --- Ouverture -----------------------------------------------------------------


def test_un_paquet_fabrique_tient_en_quelques_kilo_octets(tmp_path):
    fichier = paquet(tmp_path / "p.grib2", champs_vent(steps=(0, 1)))
    assert fichier.stat().st_size < 4096


def test_les_quatre_champs_de_vent_sont_decodes(tmp_path):
    jeu = _jeu_vent(tmp_path)
    assert set(jeu.data_vars) == {"u", "v", "wdir", "ws"}


def test_le_triplet_grib_est_remonte(tmp_path):
    jeu = _jeu_vent(tmp_path)
    assert triplet(jeu["u"]) == (0, 2, 2)
    assert triplet(jeu["wdir"]) == (0, 2, 0)


def test_les_longitudes_sont_ramenees_en_moins_180_plus_180(tmp_path):
    """La grille d'essai est bornée à 356° E, soit -4 degres. Le format impose le
    0 a 360 ; la chaîne de décodage ramène la convention usuelle."""
    jeu = _jeu_vent(tmp_path)
    assert float(jeu.longitude.min()) < 0.0
    assert float(jeu.longitude.max()) <= 180.0


def test_un_fichier_melant_types_de_niveau_rend_plusieurs_jeux(tmp_path):
    """Un paquet réel mêle sol, hauteur et niveau de la mer ; prétendre les
    réunir dans une seule structure masquerait des champs."""
    champs = [
        Champ(category=0, number=0, level_type=103, level=2),
        Champ(category=3, number=1, level_type=101, level=0),
    ]
    fichier = paquet(tmp_path / "mele.grib2", champs)
    assert len(open_granule(fichier)) >= 2


def test_les_valeurs_manquantes_sont_conservees(tmp_path):
    champs = [Champ(category=0, number=0, manquants=7, valeurs=np.full(N, 280.0))]
    fichier = paquet(tmp_path / "trous.grib2", champs)
    jeu = open_granule(fichier)[0]
    valeurs = jeu["t"].values
    assert np.isnan(valeurs).sum() == 7


def test_un_champ_cumule_porte_son_type_de_pas(tmp_path):
    champs = [Champ(category=1, number=52, accumulation=1, valeurs=np.zeros(N))]
    fichier = paquet(tmp_path / "cumul.grib2", champs)
    jeu = open_granule(fichier)[0]
    nom = next(iter(jeu.data_vars))
    assert jeu[nom].attrs["GRIB_stepType"] == "accum"


# --- Normalisation -------------------------------------------------------------


def test_la_direction_et_la_force_sont_ecartees(tmp_path):
    jeu = drop_derived_wind(_jeu_vent(tmp_path))
    assert set(jeu.data_vars) == {"u", "v"}


def test_les_composantes_sont_conservees(tmp_path):
    jeu = normalise(_jeu_vent(tmp_path))
    assert "u" in jeu.data_vars
    assert "v" in jeu.data_vars


def test_les_noms_cf_connus_de_la_chaine_sont_repris(tmp_path):
    jeu = apply_cf_names(_jeu_vent(tmp_path))
    assert jeu["u"].attrs["standard_name"] == "eastward_wind"
    assert jeu["v"].attrs["standard_name"] == "northward_wind"


def test_notre_table_comble_ce_que_la_chaine_ne_donne_pas(tmp_path):
    """La chaîne laisse `wdir` et `ws` sans nom CF alors que CF les définit."""
    jeu = _jeu_vent(tmp_path)
    assert jeu["wdir"].attrs.get("GRIB_cfName") == "unknown"
    nomme = apply_cf_names(jeu)
    assert nomme["wdir"].attrs["standard_name"] == "wind_from_direction"
    assert nomme["ws"].attrs["standard_name"] == "wind_speed"


def test_un_champ_sans_nom_cf_connu_reste_sans_nom(tmp_path):
    """Inventer un nom standard produirait un fichier qui se dit conforme et
    ne l'est pas."""
    champs = [Champ(category=19, number=11, valeurs=np.zeros(N))]
    jeu = apply_cf_names(open_granule(paquet(tmp_path / "tke.grib2", champs))[0])
    nom = next(iter(jeu.data_vars))
    assert "standard_name" not in jeu[nom].attrs


def test_les_absences_de_nom_cf_sont_declarees_et_non_subies():
    assert (0, 19, 11) in SANS_NOM_CF
    assert not SANS_NOM_CF & set(CF_STANDARD_NAMES)


def test_le_vent_derive_est_bien_celui_qui_est_ecarte():
    assert {(0, 2, 0), (0, 2, 1)} == VENT_DERIVE
    assert set(CF_STANDARD_NAMES) >= VENT_DERIVE


# --- Reconstitution du vent ----------------------------------------------------


def test_les_formules_sont_exactes_sur_des_valeurs_non_quantifiees():
    """Sans passage par GRIB, la reconstitution doit être exacte : toute dérive
    constatée ensuite vient de la quantification, pas des formules."""
    import xarray as xr

    rng = np.random.default_rng(1)
    u = xr.DataArray(rng.normal(0, 10, 500))
    v = xr.DataArray(rng.normal(0, 10, 500))
    ff = np.hypot(u.values, v.values)
    dd = np.degrees(np.arctan2(-u.values, -v.values)) % 360.0

    np.testing.assert_allclose(wind_speed(u, v).values, ff, rtol=1e-12)
    np.testing.assert_allclose(wind_from_direction(u, v).values, dd, rtol=1e-12)


@pytest.mark.parametrize(
    ("u", "v", "attendu"),
    [
        (0.0, -1.0, 0.0),  # vent de nord
        (-1.0, 0.0, 90.0),  # vent d'est
        (0.0, 1.0, 180.0),  # vent de sud
        (1.0, 0.0, 270.0),  # vent d'ouest
    ],
)
def test_la_convention_meteorologique_est_respectee(u, v, attendu):
    import xarray as xr

    obtenu = float(wind_from_direction(xr.DataArray([u]), xr.DataArray([v])).values[0])
    assert abs(obtenu - attendu) < 1e-9


def _ecart_angulaire(a, b):
    """Écart absolu entre deux directions, en tenant compte du repliement."""
    return np.abs((a - b + 180.0) % 360.0 - 180.0)


def test_la_force_se_reconstitue_a_la_precision_du_codage(tmp_path):
    jeu = _jeu_vent(tmp_path)
    recalcule = wind_speed(jeu["u"], jeu["v"]).values
    stocke = jeu["ws"].values
    # Trois grandeurs quantifiees independamment sur 12 bits : l'ecart attendu
    # est de l'ordre du pas de quantification, pas zero.
    assert np.max(np.abs(recalcule - stocke)) < 0.05


def test_la_direction_se_reconstitue_sauf_par_vent_faible(tmp_path):
    """Le résultat qu'il fallait mesurer, et non supposer.

    La direction est mal conditionnée quand les composantes approchent de
    zéro : l'écart y explose alors même que les composantes sont justes. Le
    critère d'acceptation doit donc porter sur le vent établi, et l'absence de
    garantie par vent faible être constatée plutôt que passée sous silence.
    """
    jeu = _jeu_vent(tmp_path, steps=(0, 1))
    recalculee = wind_from_direction(jeu["u"], jeu["v"]).values
    stockee = jeu["wdir"].values
    force = wind_speed(jeu["u"], jeu["v"]).values
    ecart = _ecart_angulaire(recalculee, stockee)

    etabli = force > 3.0
    assert etabli.sum() > 10, "echantillon insuffisant pour conclure"
    assert np.max(ecart[etabli]) < 1.0

    # Et la contrepartie : plus le vent faiblit, moins la direction tient.
    faible = force < 0.5
    if faible.any():
        assert np.max(ecart[faible]) >= np.max(ecart[etabli])


def test_ecarter_le_vent_derive_allege_sans_rien_perdre(tmp_path):
    """Deux champs sur quatre disparaissent, et se recalculent."""
    complet = _jeu_vent(tmp_path)
    allege = drop_derived_wind(complet)
    assert len(allege.data_vars) == len(complet.data_vars) - 2

    reconstitue = wind_speed(allege["u"], allege["v"]).values
    np.testing.assert_allclose(reconstitue, complet["ws"].values, atol=0.05)


# --- Options d'ouverture, fixées plutôt qu'héritées -----------------------------


def test_la_structure_ne_depend_pas_du_nombre_d_echeances(tmp_path):
    """`squeeze=False`, et c'est le réglage le plus insidieux de cfgrib.

    Son défaut `True` écrase les dimensions de longueur 1 : un paquet à une
    échéance rendait `(latitude, longitude)` quand un paquet à deux rendait
    `(step, latitude, longitude)`. La même donnée et le même code produisaient
    deux structures selon le contenu du fichier.
    """
    dims = []
    for n, steps in ((1, (0,)), (2, (0, 1))):
        champs = [Champ(category=0, number=0, step=s) for s in steps]
        jeu = normalise(open_granule(paquet(tmp_path / f"e{n}.grib2", champs))[0])
        dims.append(jeu["t"].dims)
    # Cinq axes, toujours les mêmes : temps, échéance et niveau vertical
    # subsistent même de longueur 1. C'est exactement la stabilité recherchée,
    # et elle rend une référence de structure tenable.
    assert dims[0] == dims[1] == ("time", "step", "heightAboveGround", "latitude", "longitude")


def test_les_valeurs_sont_restituees_en_float32(tmp_path):
    """La donnée est quantifiée sur 12 bits ; un `float64` doublerait
    l'empreinte sans porter la moindre information de plus."""
    jeu = normalise(open_granule(paquet(tmp_path / "d.grib2", [Champ(category=0, number=0)]))[0])
    assert jeu["t"].dtype == "float32"


def test_aucun_fichier_d_index_n_est_depose(tmp_path):
    """`indexpath=""` : par défaut cfgrib écrit un `.idx` à côté de la donnée."""
    source = paquet(tmp_path / "i.grib2", [Champ(category=0, number=0)])
    open_granule(source)
    assert [p.name for p in tmp_path.iterdir()] == [source.name]


def _paquet_corrompu(tmp_path):
    sain = paquet(tmp_path / "sain.grib2", [Champ(category=0, number=0)])
    cible = tmp_path / "corrompu.grib2"
    cible.write_bytes(sain.read_bytes() + b"GRIB" + b"\x00" * 40)
    return cible


def test_un_message_illisible_interrompt_par_defaut(tmp_path):
    """`errors="raise"`, là où cfgrib retient `"warn"`.

    Le défaut journalise puis poursuit : l'appelant reçoit un tuple
    d'apparence normale, amputé de champs, sans exception ni avertissement.
    Le compte rendu dirait `success` sur une donnée incomplète.
    """
    with pytest.raises(Exception, match=r"(?i)edition|grib|support"):
        open_granule(_paquet_corrompu(tmp_path))


def test_la_tolerance_reste_accessible_a_qui_l_assume(tmp_path):
    jeux = open_granule(_paquet_corrompu(tmp_path), errors="warn")
    assert len(jeux) == 1


def test_les_options_qui_decident_de_la_forme_sont_ecrites():
    """Garde-fou de refactorisation : ces quatre clés ne doivent pas
    retomber silencieusement sur les défauts de la bibliothèque."""
    assert OPTIONS_CFGRIB["squeeze"] is False
    assert OPTIONS_CFGRIB["indexpath"] == ""
    assert OPTIONS_CFGRIB["encode_cf"] == ("parameter", "time", "geography", "vertical")
    assert OPTIONS_CFGRIB["time_dims"] == ("time", "step")


def test_un_ensemble_garde_son_axe_de_membre_meme_a_un_seul_membre(tmp_path):
    """Le cas que `squeeze=True` rendait indétectable.

    Mesuré le 08/10/2026 : sous le défaut de cfgrib, un ensemble réduit à un
    membre rendait `(latitude, longitude)` — **exactement ce que rend un
    déterministe**. L'appartenance à un ensemble disparaissait du fichier, et
    rien ne permettait plus de la retrouver.
    """
    attendu = ("number", "time", "step", "heightAboveGround", "latitude", "longitude")
    for total in (1, 3):
        champs = [Champ(category=0, number=0, membre=m, membres=total) for m in range(total)]
        jeu = normalise(open_granule(paquet(tmp_path / f"ens{total}.grib2", champs))[0])
        assert jeu["t"].dims == attendu
        assert jeu["t"].sizes["number"] == total


def test_un_deterministe_n_a_pas_d_axe_de_membre(tmp_path):
    """La distinction doit rester lisible dans l'autre sens aussi : un champ
    déterministe ne porte pas de clé d'ensemble, donc pas d'axe."""
    jeu = normalise(open_granule(paquet(tmp_path / "det.grib2", [Champ(category=0, number=0)]))[0])
    assert "number" not in jeu["t"].dims


def test_cumul_et_ensemble_ne_se_combinent_pas_en_silence(tmp_path):
    """Relèverait du gabarit 4.11 ; mieux vaut refuser que produire un
    message dont la sémantique ne serait pas celle qu'on croit."""
    with pytest.raises(ValueError, match=r"4.11"):
        paquet(tmp_path / "x.grib2", [Champ(category=0, number=0, membre=0, accumulation=1)])
