"""GRIB2 — décodage et normalisation, sans aucun accès réseau.

Les paquets sont fabriqués en mémoire par `fixtures_grib2` : quelques
kilo-octets suffisent à exercer la géométrie, les valeurs manquantes, les
cumuls et le vent.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest
from fixtures_grib2 import DEFAULT_GRID, Field, granule, wind_fields

from x10_connectors.contract import CF_VERTICAL
from x10_connectors.grib2 import (
    ACCUMULATED_STEP_TYPES,
    AMBIGUOUS_TRIPLETS,
    CF_ACCUMULATED,
    CF_BY_PARAM_ID,
    CF_DERIVED,
    CF_STANDARD_NAMES,
    DERIVED_WIND,
    INTEGRAL_PREFIX,
    OPTIONS_CFGRIB,
    RATE_TOKENS,
    TEMPLATE_RESTRICTED,
    WITHOUT_CF_NAME,
    apply_cf_names,
    denotes_a_rate,
    drop_derived_wind,
    normalise,
    open_granule,
    triplet,
    wind_from_direction,
    wind_speed,
)

N = int(DEFAULT_GRID["ni"] * DEFAULT_GRID["nj"])


def _jeu_vent(tmp_path, steps=(0,)):
    fichier = granule(tmp_path / "vent.grib2", wind_fields(steps=steps))
    datasets = open_granule(fichier)
    assert len(datasets) == 1
    return datasets[0]


# --- Ouverture -----------------------------------------------------------------


def test_un_paquet_fabrique_tient_en_quelques_kilo_octets(tmp_path):
    fichier = granule(tmp_path / "p.grib2", wind_fields(steps=(0, 1)))
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
        Field(category=0, number=0, level_type=103, level=2),
        Field(category=3, number=1, level_type=101, level=0),
    ]
    fichier = granule(tmp_path / "mele.grib2", champs)
    assert len(open_granule(fichier)) >= 2


def test_les_valeurs_manquantes_sont_conservees(tmp_path):
    champs = [Field(category=0, number=0, missing=7, values=np.full(N, 280.0))]
    fichier = granule(tmp_path / "trous.grib2", champs)
    jeu = open_granule(fichier)[0]
    values = jeu["t"].values
    assert np.isnan(values).sum() == 7


def test_un_champ_cumule_porte_son_type_de_pas(tmp_path):
    champs = [Field(category=1, number=52, accumulation=1, values=np.zeros(N))]
    fichier = granule(tmp_path / "cumul.grib2", champs)
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
    champs = [Field(category=19, number=11, values=np.zeros(N))]
    jeu = apply_cf_names(open_granule(granule(tmp_path / "tke.grib2", champs))[0])
    nom = next(iter(jeu.data_vars))
    assert "standard_name" not in jeu[nom].attrs


def test_les_absences_de_nom_cf_sont_declarees_et_non_subies():
    assert (0, 19, 11) in WITHOUT_CF_NAME
    assert not WITHOUT_CF_NAME & set(CF_STANDARD_NAMES)


def test_un_code_ambigu_ne_recoit_aucun_nom(tmp_path):
    """`(0, 3, 6)` porte deux champs différents chez un même producteur.

    L'OMM le dit elle-même en note 124, et recommande les numéros 33 et 34 à
    sa place. Notre table posait `geopotential_height`, qui désigne l'entrée
    5 et s'exprime en mètres géopotentiels : faux deux fois. Lui substituer
    une autre supposition ne vaudrait pas mieux que de n'en poser aucune.
    """
    champs = [Field(category=3, number=6, values=np.zeros(N))]
    jeu = apply_cf_names(open_granule(granule(tmp_path / "h.grib2", champs))[0])
    nom = next(iter(jeu.data_vars))
    assert "standard_name" not in jeu[nom].attrs


def test_les_codes_ambigus_sont_declares_et_distincts_des_absences():
    """Deux manques de nature différente : l'un se corrige en proposant un nom
    à CF, l'autre non."""
    assert (0, 3, 6) in AMBIGUOUS_TRIPLETS
    assert not AMBIGUOUS_TRIPLETS & set(CF_STANDARD_NAMES)
    assert not AMBIGUOUS_TRIPLETS & WITHOUT_CF_NAME


def test_le_vent_derive_est_bien_celui_qui_est_ecarte():
    assert {(0, 2, 0), (0, 2, 1)} == DERIVED_WIND
    assert set(CF_STANDARD_NAMES) >= DERIVED_WIND


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
        champs = [Field(category=0, number=0, step=s) for s in steps]
        jeu = normalise(open_granule(granule(tmp_path / f"e{n}.grib2", champs))[0])
        dims.append(jeu["t"].dims)
    # Cinq axes, toujours les mêmes : temps, échéance et niveau vertical
    # subsistent même de longueur 1. C'est exactement la stabilité recherchée,
    # et elle rend une référence de structure tenable.
    assert dims[0] == dims[1] == ("time", "step", "heightAboveGround", "latitude", "longitude")


def test_les_valeurs_sont_restituees_en_float32(tmp_path):
    """La donnée est quantifiée sur 12 bits ; un `float64` doublerait
    l'empreinte sans porter la moindre information de plus."""
    jeu = normalise(open_granule(granule(tmp_path / "d.grib2", [Field(category=0, number=0)]))[0])
    assert jeu["t"].dtype == "float32"


def test_aucun_fichier_d_index_n_est_depose(tmp_path):
    """`indexpath=""` : par défaut cfgrib écrit un `.idx` à côté de la donnée."""
    source = granule(tmp_path / "i.grib2", [Field(category=0, number=0)])
    open_granule(source)
    assert [p.name for p in tmp_path.iterdir()] == [source.name]


def _paquet_corrompu(tmp_path):
    sain = granule(tmp_path / "sain.grib2", [Field(category=0, number=0)])
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
    datasets = open_granule(_paquet_corrompu(tmp_path), errors="warn")
    assert len(datasets) == 1


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
        champs = [Field(category=0, number=0, member=m, members=total) for m in range(total)]
        jeu = normalise(open_granule(granule(tmp_path / f"ens{total}.grib2", champs))[0])
        assert jeu["t"].dims == attendu
        assert jeu["t"].sizes["number"] == total


def test_un_deterministe_n_a_pas_d_axe_de_membre(tmp_path):
    """La distinction doit rester lisible dans l'autre sens aussi : un champ
    déterministe ne porte pas de clé d'ensemble, donc pas d'axe."""
    jeu = normalise(open_granule(granule(tmp_path / "det.grib2", [Field(category=0, number=0)]))[0])
    assert "number" not in jeu["t"].dims


def test_cumul_et_ensemble_ne_se_combinent_pas_en_silence(tmp_path):
    """Relèverait du gabarit 4.11 ; mieux vaut refuser que produire un
    message dont la sémantique ne serait pas celle qu'on croit."""
    with pytest.raises(ValueError, match=r"4.11"):
        granule(tmp_path / "x.grib2", [Field(category=0, number=0, member=0, accumulation=1)])


# --- Vagues : un triplet pour sept champs -------------------------------------


def test_la_hauteur_significative_totale_est_nommee(tmp_path):
    """Gabarit 4.0 : c'est bien la hauteur significative, et CF la nomme."""
    champs = [Field(discipline=10, category=0, number=3, level_type=1, level=0, values=np.zeros(N))]
    jeu = apply_cf_names(open_granule(granule(tmp_path / "swh.grib2", champs))[0])
    nom = next(iter(jeu.data_vars))
    assert jeu[nom].attrs["standard_name"] == "sea_surface_wave_significant_height"


def test_le_meme_triplet_sous_un_autre_gabarit_n_est_pas_nomme(tmp_path):
    """Sept messages d'ECMWF portent `(10, 0, 3)`, relevé le 19/10/2026.

    Un seul, de gabarit 4.0, est la hauteur significative totale ; les six
    autres, de gabarit 4.104, sont des hauteurs par bande de période. Les
    nommer comme le total serait faux **et dangereux** : des hauteurs par
    bande se composent en somme quadratique, de sorte qu'un consommateur les
    additionnant sous un même nom obtiendrait une valeur sans signification.
    """
    champs = [Field(discipline=10, category=0, number=3, level_type=1, level=0, values=np.zeros(N))]
    jeu = open_granule(granule(tmp_path / "bande.grib2", champs))[0]
    nom = next(iter(jeu.data_vars))
    jeu[nom].attrs["GRIB_productDefinitionTemplateNumber"] = 104

    assert "standard_name" not in apply_cf_names(jeu)[nom].attrs


def test_un_gabarit_illisible_ne_fait_poser_aucun_nom(tmp_path):
    """Mieux vaut un champ sans nom qu'un champ mal nommé."""
    champs = [Field(discipline=10, category=0, number=3, level_type=1, level=0, values=np.zeros(N))]
    jeu = open_granule(granule(tmp_path / "sans.grib2", champs))[0]
    nom = next(iter(jeu.data_vars))
    jeu[nom].attrs.pop("GRIB_productDefinitionTemplateNumber", None)

    assert "standard_name" not in apply_cf_names(jeu)[nom].attrs


def test_seuls_les_triplets_de_la_table_sont_restreints():
    """Une restriction qui ne porte sur aucun nom serait sans effet."""
    assert set(TEMPLATE_RESTRICTED) <= set(CF_STANDARD_NAMES)


def test_le_coefficient_de_trainee_des_vagues_reste_sans_nom():
    """CF a bien un coefficient de traînée de surface, mais il ne dit rien
    des vagues — or c'est la distinction que trace le code de l'OMM."""
    assert (10, 0, 16) in WITHOUT_CF_NAME


def test_la_bathymetrie_est_ambigue_et_non_absente():
    """CF offre cinq profondeurs de fond selon le niveau de référence, et le
    message n'en déclare aucun. Rien à proposer à CF : un choix à ne pas
    faire."""
    assert (10, 4, 7) in AMBIGUOUS_TRIPLETS


# --- Le tableau CF officiel, à la demande --------------------------------------

#: Le tableau des noms standards, forme XML. C'est la source normative de CF,
#: et la seule façon de vérifier un nom autrement qu'en l'affirmant.
CF_TABLE_URL = (
    "https://cfconventions.org/Data/cf-standard-names/current/src/cf-standard-name-table.xml"
)


@pytest.mark.network
def test_chaque_nom_cf_emis_existe_au_tableau_officiel():
    """Rend automatique ce que `CLAUDE.md` exigeait à la main.

    **Un nom inventé produirait un fichier qui se dit conforme sans
    l'être** — le défaut le plus coûteux de notre correspondance, puisqu'il
    ne casse rien et ne se voit pas. La table est bâtie par nous, faute
    d'autorité exploitable par programme côté OMM ; la contrepartie est de la
    confronter au tableau que CF, lui, publie.

    Marqué `network` : la suite hors ligne ne télécharge rien, et le tableau
    pèse 4,4 Mio.
    """
    import urllib.request
    from xml.etree import ElementTree

    with urllib.request.urlopen(CF_TABLE_URL, timeout=120) as reponse:
        racine = ElementTree.parse(reponse).getroot()

    officiels = {e.get("id") for e in racine.iter("entry")}
    alias = {e.get("id") for e in racine.iter("alias")}
    assert len(officiels) > 4000, "tableau CF inattendu : trop peu d'entrées"

    emis = noms_cf_emis()
    inconnus = sorted(emis - officiels)
    perimes = sorted(emis & alias)
    assert inconnus == [], (
        f"Nom(s) absent(s) du tableau CF {racine.findtext('version_number')} : "
        f"{inconnus}. Un nom inventé rend un fichier non conforme en silence."
    )
    assert perimes == [], (
        f"Nom(s) devenus des alias, donc dépréciés par CF : {perimes}. "
        "Reprendre le nom courant que le tableau désigne."
    )


def test_la_direction_des_vagues_est_nommee_et_non_ecartee(tmp_path):
    """Contrairement à celle du vent, elle est conservée.

    La règle des composantes ne change pas ; son application dépend de ce que
    CF offre. Il existe des noms pour les composantes du vent, aucun pour
    celles d'une direction de vagues, et ECMWF n'en publie pas. En inventer
    deux serait la faute que la table entière évite.
    """
    champs = [
        Field(discipline=10, category=0, number=14, level_type=1, level=0, values=np.zeros(N))
    ]
    jeu = apply_cf_names(open_granule(granule(tmp_path / "mwd.grib2", champs))[0])
    nom = next(iter(jeu.data_vars))

    assert jeu[nom].attrs["standard_name"] == "sea_surface_wave_from_direction"
    assert (10, 0, 14) not in DERIVED_WIND


def test_le_nom_retenu_n_est_pas_celui_de_la_grandeur_spectrale():
    """`sea_surface_wave_mean_from_direction` serait le choix naïf, et il est
    faux : CF en fait « the wave direction in each frequency band », grandeur
    spectrale que sa description distingue du paramètre global. `mwd` est
    global."""
    assert CF_STANDARD_NAMES[(10, 0, 14)] == "sea_surface_wave_from_direction"


def noms_cf_emis() -> set[str]:
    """Tous les noms standards CF que la chaîne peut écrire dans un fichier.

    **Cinq sources, et c'est le point.** Le contrôle ne balayait d'abord que
    la première, de sorte que des gisements entiers échappaient à la
    vérification : les références verticales, les grandeurs que nous
    calculons, la table indexée par `paramId` qu'a demandée l'édition 1, et
    les intégrales qui remplacent un nom de débit sur un cumul. Les énumérer
    ici resterait fragile sans `test_aucun_nom_cf_n_est_ecrit_en_dur`, qui
    prouve par analyse du code qu'aucune sixième source n'existe.
    """
    return (
        set(CF_STANDARD_NAMES.values())
        | set(CF_BY_PARAM_ID.values())
        | set(CF_DERIVED)
        | {nom for nom, _ in CF_VERTICAL.values()}
        | set(CF_ACCUMULATED.values())
    )


def test_le_releve_des_noms_cf_couvre_les_cinq_sources():
    """Un garde-fou du garde-fou : si une table cessait d'être relevée, le
    test réseau passerait en ne vérifiant plus rien."""
    emis = noms_cf_emis()
    assert set(CF_STANDARD_NAMES.values()) <= emis
    assert set(CF_BY_PARAM_ID.values()) <= emis
    assert set(CF_DERIVED) <= emis
    assert {nom for nom, _ in CF_VERTICAL.values()} <= emis
    assert set(CF_ACCUMULATED.values()) <= emis
    assert len(emis) >= len(CF_STANDARD_NAMES) + len(CF_DERIVED)


def test_aucun_nom_cf_n_est_ecrit_en_dur():
    """Un nom CF posé en dur échappe au contrôle qui le confronte au tableau.

    C'est exactement ce qui s'était produit : `wind_speed` et
    `wind_from_direction` vivaient dans le corps de deux fonctions, donc
    invisibles du test réseau. Ce contrôle ferme la classe plutôt que le cas
    — il analyse le code et exige que **tout** `standard_name` émis vienne
    d'une table, jamais d'un littéral.
    """
    import ast

    racine = pathlib.Path(__file__).resolve().parents[1] / "src" / "x10_connectors"
    fautifs: list[str] = []
    for chemin in sorted(racine.rglob("*.py")):
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            # Forme `{"standard_name": "air_temperature"}`.
            if isinstance(noeud, ast.Dict):
                for cle, valeur in zip(noeud.keys, noeud.values, strict=True):
                    if (
                        isinstance(cle, ast.Constant)
                        and cle.value == "standard_name"
                        and isinstance(valeur, ast.Constant)
                        and isinstance(valeur.value, str)
                    ):
                        fautifs.append(f"{chemin.name}:{noeud.lineno} -> {valeur.value!r}")
            # Forme `attrs["standard_name"] = "air_temperature"`.
            if isinstance(noeud, ast.Assign) and isinstance(noeud.value, ast.Constant):
                for cible in noeud.targets:
                    if (
                        isinstance(cible, ast.Subscript)
                        and isinstance(cible.slice, ast.Constant)
                        and cible.slice.value == "standard_name"
                        and isinstance(noeud.value.value, str)
                    ):
                        fautifs.append(f"{chemin.name}:{noeud.lineno} -> {noeud.value.value!r}")

    assert fautifs == [], (
        "Nom(s) CF écrit(s) en dur, donc hors du contrôle qui les confronte au "
        f"tableau officiel : {fautifs}. Les poser dans une table — "
        "`CF_STANDARD_NAMES`, `CF_DERIVED` ou `CF_VERTICAL` — et les relever "
        "dans `noms_cf_emis`."
    )


# --- Un nom de débit ne peut pas nommer un cumul -------------------------------


def test_la_regle_reconnait_un_debit_ou_que_le_mot_se_trouve():
    """La détection est une règle, pas une liste — comme pour les directions.

    **Par jetons et non par terminaison** : CF compose ses noms par mots, et
    le débit n'est pas toujours en dernier. Une règle par suffixe manquait
    `surface_downwelling_shortwave_flux_in_air`, qui est précisément l'un des
    deux cas mesurés.
    """
    assert denotes_a_rate("precipitation_flux")
    assert denotes_a_rate("surface_downwelling_shortwave_flux_in_air")
    assert denotes_a_rate("water_flux_into_sea_water")
    assert denotes_a_rate("lwe_precipitation_rate")
    assert denotes_a_rate("air_temperature") is False
    assert denotes_a_rate("surface_snow_amount") is False
    assert denotes_a_rate(None) is False
    assert all("_" not in jeton for jeton in RATE_TOKENS)


def test_une_integrale_n_est_pas_un_debit():
    """Sans cette exclusion le redressement ne serait pas idempotent.

    L'intégrale d'un flux porte encore le mot `flux`. Un second passage la
    prendrait pour un débit dont aucune table ne connaît l'intégrale — et la
    **retirerait**, détruisant le nom que le premier passage venait de poser.
    """
    for cible in CF_ACCUMULATED.values():
        assert denotes_a_rate(cible) is False, (
            f"{cible!r} serait repris pour un débit au second passage, "
            "et retiré faute d'intégrale connue."
        )
    assert any(cible.startswith(INTEGRAL_PREFIX) for cible in CF_ACCUMULATED.values()), (
        "aucune cible ne porte la construction de CF pour une intégrale "
        "temporelle : l'exclusion de `denotes_a_rate` ne serait plus exercée."
    )


def test_les_types_de_pas_cumules_rendent_bien_une_somme():
    """Apparie `ACCUMULATED_STEP_TYPES` à la table qui décide du sens.

    Ne retenir que `accum` laisserait passer `sum`, que
    `netcdf_cf.CELL_METHODS` traite identiquement : la moitié des cumuls
    échapperait au redressement **sans un mot**, et c'est précisément le
    régime d'erreur que ce dispositif existe pour fermer.
    """
    from x10_connectors.netcdf_cf import CELL_METHODS

    sommes = {pas for pas, methode in CELL_METHODS.items() if methode == "time: sum"}
    assert set(ACCUMULATED_STEP_TYPES) == sommes, (
        f"`ACCUMULATED_STEP_TYPES` vaut {sorted(ACCUMULATED_STEP_TYPES)} quand "
        f"`CELL_METHODS` rend `time: sum` pour {sorted(sommes)}. Un écart "
        "laisserait un cumul porter le nom d'un débit."
    )


def test_la_table_des_cumuls_ne_se_chaine_pas():
    """Une valeur qui serait aussi une clé produirait un redressement en deux
    temps selon l'ordre d'itération — donc un résultat non déterministe."""
    boucles = sorted(set(CF_ACCUMULATED) & set(CF_ACCUMULATED.values()))
    assert boucles == [], f"nom à la fois source et cible du redressement : {boucles}"


def test_toute_cle_de_la_table_des_cumuls_est_un_debit():
    """Une clé qui n'est pas un débit ne serait jamais consultée : la règle
    filtre avant la table. Elle serait morte sans que rien ne le dise."""
    inertes = sorted(nom for nom in CF_ACCUMULATED if not denotes_a_rate(nom))
    assert inertes == [], (
        f"clé(s) que la règle n'atteindra jamais : {inertes}. "
        "`denotes_a_rate` filtre avant `CF_ACCUMULATED`."
    )


def _jeu_cumul(tmp_path, *, number: int, nom_pose: str | None = None):
    """Un champ cumulé, éventuellement muni d'un `standard_name` déjà posé.

    Le second cas reproduit le chemin de la chaîne de décodage : `cfgrib`
    recopie `cfName` dans `standard_name`, donc le nom fautif arrive **avant**
    que nos tables soient consultées.
    """
    champs = [
        Field(
            category=1 if number == 52 else 4,
            number=number,
            accumulation=1,
            step=1,
            values=np.zeros(N),
        )
    ]
    jeu = open_granule(granule(tmp_path / f"cumul-{number}.grib2", champs))[0]
    if nom_pose is not None:
        for variable in jeu.data_vars:
            jeu[variable].attrs["standard_name"] = nom_pose
    return jeu


def test_un_nom_de_debit_de_notre_table_est_redresse_sur_un_cumul(tmp_path):
    """Cas `(0, 1, 52)` : l'OMM le nomme « Total precipitation rate », deux
    producteurs l'emploient pour un cumul, et **notre** table y posait
    `precipitation_flux` sur une grandeur en `kg m-2`. Voir `X10-DIV-0008`."""
    jeu = apply_cf_names(_jeu_cumul(tmp_path, number=52))
    noms = {jeu[v].attrs.get("standard_name") for v in jeu.data_vars}

    assert "precipitation_flux" not in noms
    assert noms == {"precipitation_amount"}


def test_un_nom_de_debit_venu_du_decodeur_est_redresse_aussi(tmp_path):
    """La correction porte sur le **nom retenu**, pas sur la branche qui l'a
    produit.

    Mesuré le 22/10/2026 sous ecCodes 2.49.0, rejoué sous 2.50.0 par
    `uv run --no-project --with eccodes==2.50.0 python` : sur `(0, 4, 7)`, le
    décodeur résout **deux paramètres distincts** selon le traitement
    statistique, et celui du cumul porte le nom CF du débit avec l'unité du
    cumul. Et `cfgrib` recopiant `cfName` dans `standard_name`, ce nom arrive
    déjà posé : une correction placée dans la branche « notre table » ne
    l'aurait jamais vu.
    """
    jeu = _jeu_cumul(tmp_path, number=7, nom_pose="surface_downwelling_shortwave_flux_in_air")
    sortie = apply_cf_names(jeu)
    noms = {sortie[v].attrs.get("standard_name") for v in sortie.data_vars}

    assert noms == {"integral_wrt_time_of_surface_downwelling_shortwave_flux_in_air"}


def test_un_debit_sans_integrale_connue_sort_sans_nom(tmp_path):
    """Le repli, et c'est lui qui ferme la classe.

    CF n'offre pas d'intégrale pour tout débit — pour les flux de chaleur il
    nomme la forme *downward* quand le GRIB compte *upward*, et une table
    nom→nom ne sait pas changer un signe. Le champ sort alors **sans nom**,
    donc visible, plutôt que faux en silence.
    """
    jeu = _jeu_cumul(tmp_path, number=7, nom_pose="an_invented_rate")
    sortie = apply_cf_names(jeu)

    assert "an_invented_rate" not in CF_ACCUMULATED
    for variable in sortie.data_vars:
        assert "standard_name" not in sortie[variable].attrs


def test_un_instantane_garde_le_nom_du_debit(tmp_path):
    """Le redressement ne doit pas déborder : hors cumul, un débit est un
    débit, et `precipitation_flux` reste juste."""
    champs = [Field(category=1, number=52, values=np.zeros(N))]
    jeu = apply_cf_names(open_granule(granule(tmp_path / "instant.grib2", champs))[0])
    noms = {jeu[v].attrs.get("standard_name") for v in jeu.data_vars}

    assert noms == {"precipitation_flux"}
