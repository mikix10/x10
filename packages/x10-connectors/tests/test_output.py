"""Tests de l'écriture NetCDF, sans aucun accès réseau.

Les paquets sont fabriqués en mémoire par `fixtures_grib` ; les fichiers
produits vivent dans le `tmp_path` de pytest et disparaissent avec lui.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest
import xarray as xr
from fixtures_grib import GRILLE_PAR_DEFAUT, Champ, champs_vent, paquet

from x10_connectors.decoding import normalise, open_granule
from x10_connectors.output import (
    AXES_DECLARABLES,
    CELL_METHODS,
    CONVENTIONS,
    CRS_VARIABLE,
    ECCODES_MANQUANT,
    UDUNITS,
    TraitementStatistiqueInconnu,
    UniteNonConvertible,
    cell_methods,
    convert_units,
    global_attributes,
    grid_mapping,
    udunits,
    write_netcdf,
)
from x10_models import Retrieval

N = int(GRILLE_PAR_DEFAUT["ni"] * GRILLE_PAR_DEFAUT["nj"])


def _lignage(licence: str | None = "etalab-2.0") -> Retrieval:
    return Retrieval(
        artefacts=(),
        retrieved_at=datetime(2026, 10, 8, 3, 0, tzinfo=UTC),
        dataset="meteofrance-pnt-opendata:arome:0025",
        origin="data.gouv.fr",
        agent="x10-connectors 0.1.0",
        license=licence,
    )


def _jeu(tmp_path, champs=None):
    champs = champs or champs_vent(steps=(0,))
    return normalise(open_granule(paquet(tmp_path / "p.grib2", champs))[0])


# --- Unités --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("grib", "attendu"),
    [
        ("K", "K"),
        ("m s**-1", "m s-1"),
        ("kg m**-2 s**-1", "kg m-2 s-1"),
        ("m**2 s**-2", "m2 s-2"),
        ("K m**2 kg**-1 s**-1", "K m2 kg-1 s-1"),
        ("Degree true", "degree"),
        ("(0 - 1)", "1"),
    ],
)
def test_les_unites_connues_se_traduisent_en_udunits(grib, attendu):
    assert udunits(grib) == attendu


@pytest.mark.parametrize("grib", ["unknown", "(Code table 4.201)", "", None])
def test_une_unite_sans_sens_ne_produit_rien(grib):
    """Mieux vaut aucune unité qu'une unité inventée."""
    assert udunits(grib) is None


def test_une_unite_inconnue_fait_echouer_plutot_que_deviner():
    with pytest.raises(UniteNonConvertible, match="sans correspondance"):
        udunits("parsecs par fortnight")


def test_aucune_unite_emise_n_utilise_la_syntaxe_eccodes():
    """L'ensemble fermé, vérifié dans son intégralité.

    UDUNITS sait lire `**` — sa grammaire en fait un opérateur d'exposant —,
    mais la forme à tiret est la forme canonique, celle de sa propre suite de
    tests et celle qu'émettent les producteurs."""
    for grib, udu in UDUNITS.items():
        assert "**" not in (udu or ""), f"{grib!r} traduit en {udu!r}"


def test_udunits_valide_lui_meme_chaque_unite_emise():
    """**Vérifier au lieu d'affirmer.**

    Le test précédent compare nos cibles à une liste tenue à la main ; celui-ci
    les soumet à UDUNITS-2, dont `cf-units` embarque la bibliothèque C.

    **Piège écarté explicitement.** `cf-units` court-circuite les chaînes
    `unknown` et `no_unit`, qu'il traite comme des sentinelles internes sans
    les soumettre à UDUNITS. Elles passeraient donc cette validation alors
    qu'UDUNITS les refuse. Nous n'émettons ni l'une ni l'autre — la table les
    traduit par `None` —, mais le contrôle doit le dire plutôt que de le
    supposer.
    """
    import cf_units

    sentinelles = {cf_units._UNKNOWN_UNIT_STRING, cf_units._NO_UNIT_STRING}
    emises = {u for u in UDUNITS.values() if u is not None}
    assert not (emises & sentinelles), "une sentinelle de cf-units échapperait au contrôle"

    for unite in sorted(emises):
        # `UT_DEFINITION` force la réduction aux unités de base : une chaîne
        # que la grammaire accepterait sans savoir l'interpréter échouerait ici.
        cf_units.Unit(unite).format(cf_units.UT_DEFINITION)


def test_la_conversion_preserve_la_grandeur():
    """Une canonicalisation ne doit rien changer d'autre que l'écriture.

    La définition réduite d'UDUNITS est comparée des deux côtés : si elle est
    identique, la réécriture n'a pas altéré la grandeur. C'est une garantie
    plus forte qu'une simple validité syntaxique.
    """
    import cf_units

    for grib, udu in UDUNITS.items():
        if udu is None:
            continue
        try:
            avant = cf_units.Unit(grib).format(cf_units.UT_DEFINITION)
        except ValueError:
            # Les quatre cas nommés : `Degree true`, `(0 - 1)` et les codes de
            # table ne sont pas des unités UDUNITS, il n'y a rien à comparer.
            continue
        apres = cf_units.Unit(udu).format(cf_units.UT_DEFINITION)
        assert avant == apres, f"{grib!r} -> {udu!r} : {avant!r} devient {apres!r}"


def test_la_conversion_remplace_les_unites_du_jeu(tmp_path):
    jeu = _jeu(tmp_path)
    assert jeu["u"].attrs["units"] == "m s**-1"
    converti = convert_units(jeu)
    assert converti["u"].attrs["units"] == "m s-1"


def test_la_conversion_preserve_l_unite_d_origine_dans_les_cles_grib(tmp_path):
    converti = convert_units(_jeu(tmp_path))
    assert converti["u"].attrs["GRIB_units"] == "m s**-1"


def test_sans_strict_une_unite_inconnue_retire_l_attribut(tmp_path):
    jeu = _jeu(tmp_path)
    jeu["u"].attrs["units"] = "parsecs par fortnight"
    converti = convert_units(jeu, strict=False)
    assert "units" not in converti["u"].attrs


def test_en_strict_une_unite_inconnue_interrompt(tmp_path):
    jeu = _jeu(tmp_path)
    jeu["u"].attrs["units"] = "parsecs par fortnight"
    with pytest.raises(UniteNonConvertible):
        convert_units(jeu, strict=True)


# --- Attributs globaux ---------------------------------------------------------


def test_les_attributs_cf_attendus_sont_poses(tmp_path):
    attrs = global_attributes(_jeu(tmp_path), retrieval=_lignage())
    assert attrs["Conventions"] == CONVENTIONS
    assert "history" in attrs
    assert "institution" in attrs
    assert attrs["source"].startswith("meteofrance-pnt-opendata")
    assert attrs["title"] == "meteofrance-pnt-opendata:arome:0025"


def test_la_licence_du_lignage_voyage_avec_le_fichier(tmp_path):
    attrs = global_attributes(_jeu(tmp_path), retrieval=_lignage())
    assert attrs["license"] == "etalab-2.0"


def test_sans_lignage_ni_licence_ni_source_ne_sont_inventes(tmp_path):
    """L'absence de provenance doit se voir, non être comblée."""
    attrs = global_attributes(_jeu(tmp_path))
    assert "license" not in attrs
    assert "source" not in attrs


def test_un_lignage_sans_licence_ne_pose_pas_l_attribut(tmp_path):
    attrs = global_attributes(_jeu(tmp_path), retrieval=_lignage(licence=None))
    assert "license" not in attrs


def test_acdd_n_est_pas_declare(tmp_path):
    """Le nom `license` vient d'ACDD, mais nous n'émettons pas l'ensemble
    qu'ACDD exige : le déclarer serait prétendre à une conformité absente."""
    attrs = global_attributes(_jeu(tmp_path), retrieval=_lignage())
    assert "ACDD" not in attrs["Conventions"]


def test_une_trace_history_anterieure_est_preservee(tmp_path):
    jeu = _jeu(tmp_path)
    jeu.attrs["history"] = "ligne anterieure"
    attrs = global_attributes(jeu, retrieval=_lignage())
    assert attrs["history"].endswith("ligne anterieure")
    assert "x10-connectors" in attrs["history"]


# --- Écriture ------------------------------------------------------------------


def test_le_fichier_s_ecrit_et_se_relit(tmp_path):
    jeu = _jeu(tmp_path)
    cible = write_netcdf(jeu, tmp_path / "sortie.nc", retrieval=_lignage())
    assert cible.exists()

    relu = xr.open_dataset(cible)
    try:
        assert set(relu.data_vars) == {"u", "v", "crs"}
        np.testing.assert_allclose(relu["u"].values, jeu["u"].values, atol=1e-5)
        assert relu["u"].attrs["units"] == "m s-1"
        assert relu["u"].attrs["standard_name"] == "eastward_wind"
        assert relu.attrs["license"] == "etalab-2.0"
        assert relu.attrs["Conventions"] == CONVENTIONS
    finally:
        relu.close()


def test_les_coordonnees_survivent_a_l_aller_retour(tmp_path):
    jeu = _jeu(tmp_path)
    cible = write_netcdf(jeu, tmp_path / "sortie.nc")
    relu = xr.open_dataset(cible)
    try:
        np.testing.assert_allclose(relu.latitude.values, jeu.latitude.values)
        np.testing.assert_allclose(relu.longitude.values, jeu.longitude.values)
        assert relu.longitude.attrs["units"] == "degrees_east"
    finally:
        relu.close()


def test_les_valeurs_manquantes_restent_manquantes(tmp_path):
    champs = [Champ(category=0, number=0, manquants=7, valeurs=np.full(N, 280.0))]
    jeu = normalise(open_granule(paquet(tmp_path / "trous.grib2", champs))[0])
    cible = write_netcdf(jeu, tmp_path / "trous.nc")
    relu = xr.open_dataset(cible)
    try:
        assert np.isnan(relu["t"].values).sum() == 7
    finally:
        relu.close()


def test_l_ecriture_cree_le_dossier_parent(tmp_path):
    cible = write_netcdf(_jeu(tmp_path), tmp_path / "a" / "b" / "sortie.nc")
    assert cible.exists()


def test_les_valeurs_explicites_l_emportent_sur_celles_du_lignage(tmp_path):
    attrs = global_attributes(
        _jeu(tmp_path),
        retrieval=_lignage(),
        title="Vent a 10 m, AROME 0,025",
        source="AROME 0.025 deg, Meteo-France",
        references="https://www.data.gouv.fr/datasets/paquets-arome-resolution-0-025deg",
    )
    assert attrs["title"] == "Vent a 10 m, AROME 0,025"
    assert attrs["source"] == "AROME 0.025 deg, Meteo-France"
    assert attrs["references"].startswith("https://")


def test_une_source_explicite_suffit_sans_lignage(tmp_path):
    attrs = global_attributes(_jeu(tmp_path), source="essai")
    assert attrs["source"] == "essai"
    assert "license" not in attrs


# --- Referentiel geodesique ----------------------------------------------------


def test_le_referentiel_est_decrit_et_non_suppose(tmp_path):
    """Le GRIB déclare une sphère de 6 371 229 m ; sans `grid_mapping`, le
    consommateur doit supposer, et rien ne l'avertit qu'il suppose."""
    mapping = grid_mapping(_jeu(tmp_path))
    assert mapping is not None
    assert mapping["grid_mapping_name"] == "latitude_longitude"
    assert mapping["earth_radius"] == 6371229.0
    assert "semi_major_axis" not in mapping


def test_la_variable_de_referentiel_voyage_avec_le_fichier(tmp_path):
    cible = write_netcdf(_jeu(tmp_path), tmp_path / "crs.nc")
    relu = xr.open_dataset(cible, decode_coords=False)
    try:
        assert relu[CRS_VARIABLE].attrs["earth_radius"] == 6371229.0
        for nom in ("u", "v"):
            assert relu[nom].attrs["grid_mapping"] == CRS_VARIABLE
    finally:
        relu.close()


def test_un_ellipsoide_est_decrit_par_ses_deux_axes(tmp_path):
    """WGS84 et les autres sphéroïdes n'ont pas de rayon unique : CF attend
    alors le couple d'axes, et non un `earth_radius` inventé."""
    jeu = _jeu(tmp_path)
    for var in jeu.data_vars.values():
        var.attrs.update(
            GRIB_shapeOfTheEarth=5,
            GRIB_earthIsOblate=1,
            GRIB_earthMajorAxis=6378137.0,
            GRIB_earthMinorAxis=6356752.314,
        )
        var.attrs.pop("GRIB_radius", None)
    mapping = grid_mapping(jeu)
    assert mapping is not None
    assert mapping["semi_major_axis"] == 6378137.0
    assert mapping["semi_minor_axis"] == 6356752.314
    assert "earth_radius" not in mapping


def test_le_marqueur_d_absence_d_eccodes_n_est_pas_pris_pour_un_rayon(tmp_path):
    """`INT32_MAX` signale une clé absente. Lu sans précaution il donnerait
    une Terre de 2 147 483 647 mètres, qu'aucun contrôle ne rattraperait."""
    jeu = _jeu(tmp_path)
    for var in jeu.data_vars.values():
        var.attrs["GRIB_radius"] = ECCODES_MANQUANT
    assert grid_mapping(jeu) is None


def test_sans_information_aucun_referentiel_n_est_invente(tmp_path):
    jeu = _jeu(tmp_path)
    for var in jeu.data_vars.values():
        for cle in list(var.attrs):
            if cle.startswith("GRIB_shapeOfTheEarth"):
                del var.attrs[cle]
    assert grid_mapping(jeu) is None
    cible = write_netcdf(jeu, tmp_path / "sans.nc")
    relu = xr.open_dataset(cible, decode_coords=False)
    try:
        assert CRS_VARIABLE not in relu.variables
    finally:
        relu.close()


# --- Service reel --------------------------------------------------------------


@pytest.mark.network
def test_ecriture_depuis_un_paquet_reel(tmp_path):
    """Confirme que la table d'unites couvre un paquet entier.

    Les fixtures ne produisent que les unites qu'on leur demande ; seul un
    fichier reel dit si une unite echappe a la table."""
    from x10_connectors import MeteoFrancePntConnector, MeteoFrancePntRequest

    resultat = MeteoFrancePntConnector(
        tmp_path,
        MeteoFrancePntRequest(model="arome", grid="0025", paquets=("SP1",), tranches=("00H06H",)),
    ).fetch()
    assert resultat.retrieval is not None

    ecrits = 0
    types_vus: set[str] = set()
    for n, jeu in enumerate(open_granule(resultat.retrieval.artefacts[0])):
        decode = normalise(jeu)
        types_vus |= {
            str(v.attrs["GRIB_stepType"])
            for v in decode.data_vars.values()
            if "GRIB_stepType" in v.attrs
        }
        # Resout par variable : un jeu reel mele les traitements, ce que les
        # fixtures ne montraient pas.
        cell_methods(decode)
        assert grid_mapping(decode) is not None

        cible = write_netcdf(decode, tmp_path / f"sortie-{n}.nc", retrieval=resultat.retrieval)
        relu = xr.open_dataset(cible, decode_coords=False)
        try:
            assert relu.attrs["license"] == resultat.retrieval.license
            assert relu[CRS_VARIABLE].attrs["grid_mapping_name"] == "latitude_longitude"
            for var in relu.data_vars.values():
                assert "**" not in var.attrs.get("units", "")
                assert var.attrs.get("cell_methods", "time: point").startswith("time: ")
        finally:
            relu.close()
        ecrits += 1
    assert ecrits >= 1
    # Un paquet de surface reel porte instantanes, cumuls et maxima. Si l'un
    # disparait, c'est le producteur qui a change.
    assert {"instant", "accum", "max"} <= types_vus, types_vus


# --- Methodes de cellule -------------------------------------------------------

#: Table 4.10 du GRIB2, le `stepType` qu'ecCodes en tire, et la methode CF.
TRAITEMENTS = [
    (0, "avg", "time: mean"),
    (1, "accum", "time: sum"),
    (2, "max", "time: maximum"),
    (3, "min", "time: minimum"),
    (5, "rms", "time: root_mean_square"),
    (6, "sd", "time: standard_deviation"),
    (11, "sum", "time: sum"),
]


def _jeu_traite(tmp_path, code):
    champs = [Champ(category=1, number=8, accumulation=3, traitement=code, step=s) for s in (3, 6)]
    return normalise(open_granule(paquet(tmp_path / f"t{code}.grib2", champs))[0])


@pytest.mark.parametrize(("code", "step_type", "methode"), TRAITEMENTS)
def test_chaque_traitement_statistique_donne_sa_methode_cf(tmp_path, code, step_type, methode):
    jeu = _jeu_traite(tmp_path, code)
    assert {str(v.attrs["GRIB_stepType"]) for v in jeu.data_vars.values()} == {step_type}
    assert set(cell_methods(jeu).values()) == {methode}


def test_un_instantane_est_declare_comme_tel(tmp_path):
    """`time: point` n'est pas une formalité : c'est ce qui dit qu'il n'y a
    eu aucune agrégation, là où l'absence d'attribut ne dit rien."""
    assert set(cell_methods(_jeu(tmp_path)).values()) == {"time: point"}


def test_un_cumul_ne_peut_plus_passer_pour_un_instantane(tmp_path):
    """Le danger que cette table écarte.

    Décodés, un cumul et un instantané ont mêmes dimensions, même unité,
    mêmes coordonnées. Sans `cell_methods`, un consommateur moyenne des
    cumuls — la faute déjà écartée sur les directions de vent.
    """
    cible = write_netcdf(_jeu_traite(tmp_path, 1), tmp_path / "cumul.nc")
    relu = xr.open_dataset(cible, decode_coords=False)
    try:
        # Les vraies variables de données sont celles qui pointent vers le
        # référentiel ; `valid_time` remonte ici en variable faute de
        # décodage des coordonnées.
        methodes = {
            v.attrs.get("cell_methods")
            for v in relu.data_vars.values()
            if v.attrs.get("grid_mapping") == CRS_VARIABLE
        }
        assert methodes == {"time: sum"}
    finally:
        relu.close()


@pytest.mark.parametrize(("code", "step_type"), [(4, "diff"), (7, "cov"), (9, "ratio")])
def test_un_traitement_que_cf_ne_couvre_pas_n_emet_rien(tmp_path, code, step_type):
    """Recensé plutôt que rapproché de force d'une méthode voisine : `range`
    n'est pas une différence fin moins début, et CF n'a ni covariance ni
    rapport."""
    jeu = _jeu_traite(tmp_path, code)
    assert {str(v.attrs["GRIB_stepType"]) for v in jeu.data_vars.values()} == {step_type}
    assert cell_methods(jeu) == {}


def test_un_traitement_inconnu_interrompt_plutot_que_de_se_taire(tmp_path):
    """Se taire produirait un cumul qui se présente comme un instantané."""
    jeu = _jeu(tmp_path)
    for var in jeu.data_vars.values():
        var.attrs["GRIB_stepType"] = "sorcellerie"
    with pytest.raises(TraitementStatistiqueInconnu, match="inconnu"):
        cell_methods(jeu)


def test_des_traitements_meles_dans_un_jeu_sont_resolus_un_a_un(tmp_path):
    """Le cas que les fixtures ne montraient pas, et qu'un fichier réel a
    révélé.

    On pouvait croire `cfgrib` capable de séparer les traitements
    statistiques, puisqu'il éclate un paquet en plusieurs jeux. Il groupe en
    fait par **forme d'hypercube**. Mesuré le 08/10/2026 sur un paquet AROME
    de surface : un même jeu réunit quatre champs cumulés et un instantané.
    """
    jeu = _jeu(tmp_path)
    noms = sorted(jeu.data_vars)
    jeu[noms[0]].attrs["GRIB_stepType"] = "accum"
    jeu[noms[1]].attrs["GRIB_stepType"] = "instant"
    assert cell_methods(jeu) == {noms[0]: "time: sum", noms[1]: "time: point"}


def test_une_variable_sans_traitement_declare_n_emet_rien(tmp_path):
    jeu = _jeu(tmp_path)
    for var in jeu.data_vars.values():
        var.attrs.pop("GRIB_stepType", None)
    assert cell_methods(jeu) == {}


def test_toutes_les_methodes_emises_sont_au_tableau_de_cf():
    """Ensemble fermé, vérifié dans son intégralité contre le tableau E.1
    du standard, lu le 08/10/2026."""
    tableau_e1 = {
        "point",
        "sum",
        "anomaly_wrt",
        "maximum",
        "maximum_absolute_value",
        "median",
        "mid_range",
        "minimum",
        "minimum_absolute_value",
        "mean",
        "mean_absolute_value",
        "mean_of_upper_decile",
        "mode",
        "range",
        "root_mean_square",
        "standard_deviation",
        "sum_of_squares",
        "variance",
    }
    for methode in CELL_METHODS.values():
        axe, nom = methode.split(": ")
        assert axe == "time"
        assert nom in tableau_e1, f"{nom!r} absent du tableau E.1"


def test_aucune_methode_n_est_declaree_hors_de_l_axe_temporel(tmp_path):
    """Seul le temps se traduit depuis le GRIB. Une méthode spatiale cesse
    d'être vraie dès que le producteur rééchantillonne — ce que tous font."""
    assert AXES_DECLARABLES == ("time",)
    for methode in CELL_METHODS.values():
        assert methode.split(": ")[0] in AXES_DECLARABLES


def test_une_methode_heritee_est_retiree_et_non_recopiee(tmp_path):
    """Le vrai danger n'est pas d'émettre `area:`, c'est de le **recopier**.

    Un attribut hérité est une affirmation dont personne n'a vérifié qu'elle
    tient encore après le traitement subi.
    """
    jeu = _jeu_traite(tmp_path, 4)  # `diff`, sans équivalent CF : rien à émettre
    for var in jeu.data_vars.values():
        var.attrs["cell_methods"] = "area: mean"
    cible = write_netcdf(jeu, tmp_path / "herite.nc")
    relu = xr.open_dataset(cible, decode_coords=False)
    try:
        for v in relu.data_vars.values():
            if v.attrs.get("grid_mapping") == CRS_VARIABLE:
                assert "cell_methods" not in v.attrs
    finally:
        relu.close()
