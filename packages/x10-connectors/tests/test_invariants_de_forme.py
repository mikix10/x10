"""Invariants du format que la chaîne doit tenir, sur une source jamais vue.

Ces contrôles ne portent sur **aucun cas connu** : ils vérifient des
propriétés que tout GRIB2 possède, de sorte qu'ils rendent la main sur un
producteur que le dépôt n'a jamais rencontré. C'est ce qui les distingue
d'une liste, et ce qui leur permet de valoir pour la source suivante.

Chacun répond à un silence mesuré le 22/10/2026 : un défaut qui passerait
sans qu'aucune exception, aucun avertissement et aucun compte rendu ne le
signale.
"""

from __future__ import annotations

import itertools
import json
import pathlib

import numpy as np
import pytest
from fixtures_grib2 import DEFAULT_GRID, Field, granule

from x10_connectors.contract import GRIB_IDENTITY, output_contract
from x10_connectors.grib2 import GEO_KEYS, READ_KEYS, normalise, open_granule
from x10_connectors.netcdf_cf import write_netcdf

N = int(DEFAULT_GRID["ni"] * DEFAULT_GRID["nj"])

#: Clés dont l'absence est **légitime** sur un message qui n'en relève pas.
#: Les énumérer ici est le prix à payer pour que le contrôle reste utile :
#: sans cette liste il échouerait toujours, avec elle il échoue sur une clé
#: mal orthographiée.
CONDITIONNELLES = frozenset(
    {
        # Une fenêtre d'agrégation n'existe que sur un gabarit statistique.
        "indicatorOfUnitForTimeRange",
        # Une taille d'ensemble n'existe que sur un gabarit d'ensemble.
        "numberOfForecastsInEnsemble",
        # Les axes d'un ellipsoïde ne sont posés que si la Terre en est un.
        "earthMajorAxis",
        "earthMinorAxis",
        "radius",
    }
)


def _jeux(tmp_path, champs, nom="p.grib2"):
    return tuple(normalise(j) for j in open_granule(granule(tmp_path / nom, champs)))


# --- I-02 : une clé demandée doit ressortir -----------------------------------


def test_chaque_cle_demandee_ressort_en_attribut(tmp_path):
    """Une faute de frappe dans `READ_KEYS` supprime un attribut **sans un mot**.

    `cfgrib` lit les attributs sur le premier message de chaque hypercube et
    **avale toute exception** : une clé inconnue n'est pas une erreur, elle
    est absente. Rien dans le dépôt ne mentionnait `READ_KEYS` ni `GEO_KEYS`
    avant ce contrôle, de sorte qu'une clé pouvait cesser de ressortir à une
    montée de version sans que la suite le voie.
    """
    champs = [Field(category=0, number=0, accumulation=1, step=1, values=np.zeros(N))]
    jeu = _jeux(tmp_path, champs)[0]
    variable = next(iter(jeu.data_vars.values()))

    attendues = (set(READ_KEYS) | set(GEO_KEYS)) - CONDITIONNELLES
    manquantes = sorted(cle for cle in attendues if f"GRIB_{cle}" not in variable.attrs)
    assert manquantes == [], (
        f"Clé(s) demandée(s) à `cfgrib` et absente(s) des attributs : {manquantes}. "
        "Soit elles sont mal orthographiées, soit la bibliothèque a cessé de "
        "les rendre — dans les deux cas en silence."
    )


def test_une_cle_conditionnelle_ressort_quand_sa_condition_tient(tmp_path):
    """La liste des conditionnelles ne doit pas devenir une échappatoire :
    chacune doit ressortir dès que le message la porte."""
    champs = [Field(category=1, number=52, accumulation=3, step=3, values=np.zeros(N))]
    variable = next(iter(_jeux(tmp_path, champs)[0].data_vars.values()))

    assert "GRIB_indicatorOfUnitForTimeRange" in variable.attrs


# --- I-03 : les manquants se conservent ---------------------------------------


def test_les_points_manquants_traversent_la_chaine(tmp_path):
    """« Un zéro entre dans une moyenne, un `NaN` non. »

    Un manquant GRIB devenu zéro au NetCDF est un défaut attesté chez
    plusieurs producteurs, et il ne se signale pas : le fichier est lisible,
    les valeurs sont plausibles, et toute statistique est fausse.
    """
    manquants = 3
    champs = [Field(category=0, number=0, missing=manquants, values=np.ones(N))]
    jeu = _jeux(tmp_path, champs)[0]
    variable = next(iter(jeu.data_vars.values()))

    assert int(np.isnan(variable.values).sum()) == manquants
    assert "GRIB_bitmapPresent" in variable.attrs


def test_aucun_missing_value_n_est_emis(tmp_path):
    """`missing_value` et `_FillValue` coexistant sur une variable, le guide
    de netCDF écrit que le premier « is not treated in any special way » —
    alors que `netCDF4` et `xarray` le masquent tout de même. Deux lecteurs
    conformes en tirent deux résultats. Nous n'en émettons qu'un."""
    champs = [Field(category=0, number=0, missing=2, values=np.ones(N))]
    cible = write_netcdf(_jeux(tmp_path, champs)[0], tmp_path / "manquants.nc")

    import netCDF4

    with netCDF4.Dataset(cible) as lu:
        for nom, var in lu.variables.items():
            assert "missing_value" not in var.ncattrs(), nom


# --- I-04 : une identité désigne un message et un seul ------------------------


def test_deux_entrees_du_contrat_ne_partagent_pas_une_identite(tmp_path):
    """La docstring du contrat promet qu'« une divergence nomme la variable
    **et** désigne les messages responsables ».

    La promesse ne tient que si l'identité est injective. Mesuré le
    22/10/2026 sur le flux de vagues d'ECMWF, elle ne l'est pas : six
    hauteurs par bande de période rendent la même. Ce contrôle dira si le
    trou est refermé le jour où l'on ajoutera les clés manquantes, et il
    échouera si une source nouvelle en ouvre un autre.
    """
    champs = [
        Field(category=0, number=0, values=np.zeros(N)),
        Field(category=2, number=2, values=np.zeros(N)),
        Field(category=1, number=52, accumulation=1, step=1, values=np.zeros(N)),
    ]
    contrat = output_contract(_jeux(tmp_path, champs))

    identites: dict[tuple[str, ...], list[str]] = {}
    for nom, fiche in contrat.variables.items():
        cle = tuple(fiche.grib.get(k, "") for k in GRIB_IDENTITY)
        identites.setdefault(cle, []).append(nom)
    partagees = {cle: noms for cle, noms in identites.items() if len(noms) > 1}
    assert partagees == {}, (
        f"Identité producteur partagée par plusieurs variables : {partagees}. "
        "Le contrat ne saurait plus désigner le message responsable."
    )


# --- I-05 : le temps est monotone, les bornes ne se recouvrent pas ------------


def test_l_axe_du_temps_est_monotone_et_sans_doublon(tmp_path):
    """Des échéances qui se recouvrent produisent un fichier que l'aval lit
    sans protester et qui fausse toute agrégation.

    `CLAUDE.md` nomme `index.is_unique` comme la détection en une ligne, et
    rien ne l'appliquait.
    """
    champs = [Field(category=0, number=0, step=pas, values=np.zeros(N)) for pas in (0, 1, 2)]
    jeu = _jeux(tmp_path, champs)[0]

    valides = np.atleast_1d(np.asarray(jeu["valid_time"].values)).ravel()
    assert len(set(valides.tolist())) == len(valides), "échéances en doublon"
    assert bool(np.all(np.diff(valides.astype("int64")) > 0)), "axe du temps non monotone"


def test_les_bornes_de_periode_ne_se_recouvrent_pas(tmp_path):
    """Deux cumuls dont les fenêtres se chevauchent ne sont pas sommables, et
    rien dans le fichier ne le dirait."""
    champs = [
        Field(category=1, number=52, accumulation=1, step=pas, values=np.zeros(N))
        for pas in (1, 2, 3)
    ]
    cible = write_netcdf(_jeux(tmp_path, champs)[0], tmp_path / "bornes.nc")

    import netCDF4

    with netCDF4.Dataset(cible) as lu:
        # La variable de bornes se trouve par l'attribut `bounds` de la
        # coordonnée, comme CF le prescrit — et non par son nom, que rien
        # n'impose. Chercher un suffixe faisait sauter le contrôle en
        # silence, ce qu'un garde-fou ne doit jamais faire.
        porteuses = [n for n, v in lu.variables.items() if "bounds" in v.ncattrs()]
        assert porteuses, "aucune coordonnée ne déclare de bornes"
        nom_bornes = lu.variables[porteuses[0]].getncattr("bounds")
        bornes = lu.variables[nom_bornes][:]
    plat = np.asarray(bornes).reshape(-1, 2)
    ordonne = plat[np.argsort(plat[:, 0])]
    chevauchements = [
        (float(a[0]), float(a[1]), float(b[0]))
        for a, b in itertools.pairwise(ordonne)
        if b[0] < a[1]
    ]
    assert chevauchements == [], f"fenêtres qui se recouvrent : {chevauchements}"


# --- M-11 : le chemin de l'autre centre est exercé hors ligne -----------------


def test_le_chemin_du_centre_europeen_est_exerce(tmp_path):
    """**Troisième occurrence d'un même motif**, et c'est pourquoi ce test
    existe : un comportement propre à un producteur n'était couvert par aucun
    test hors ligne, alors que la fabrique savait déjà poser le centre.

    Le dépôt a déjà écrit deux fois qu'un fichier du producteur avait corrigé
    une hypothèse que les tests hors ligne confortaient.
    """
    champs = [Field(category=0, number=0, centre=98, values=np.zeros(N))]
    jeu = _jeux(tmp_path, champs)[0]

    # Le centre est un attribut **global** : il vaut pour le granule entier.
    assert jeu.attrs["GRIB_centre"] == "ecmf"


# --- I-01 : la cohérence vaut aussi pour ce que la chaîne produit ------------

#: Le relevé des unités canoniques, engendré depuis le tableau CF officiel.
#: Lu comme une **donnée**, sans import : il vit au niveau transverse parce
#: qu'il sert deux membres.
UNITES_CANONIQUES = (
    pathlib.Path(__file__).resolve().parents[3] / "workspace-tests" / "cf-canonical-units.json"
)


def test_ce_que_la_chaine_produit_est_dimensionnellement_coherent(tmp_path):
    """Le contrôle transverse ne regarde que des **fichiers commités**.

    Une source nouvelle, ou une version d'ecCodes qui change un nom,
    reproduirait le défaut de nommage que le dépôt a corrigé le 22/10/2026 —
    un nom de débit sur un champ cumulé — et rien ne le verrait avant la
    prochaine régénération de référence. Ce contrôle-ci porte sur la sortie
    **telle que la chaîne vient de l'écrire**.

    Il reste un test et non un garde-fou d'exécution : `cf-units` est au
    groupe de développement, et le noyau doit rester installable sans pile
    scientifique.
    """
    cf_units = pytest.importorskip("cf_units")
    canoniques = dict(json.loads(UNITES_CANONIQUES.read_text(encoding="utf-8"))["units"])

    champs = [
        Field(category=0, number=0, values=np.full(N, 288.0)),
        Field(category=2, number=2, values=np.zeros(N)),
        Field(category=1, number=52, accumulation=1, step=1, values=np.zeros(N)),
        Field(category=4, number=7, accumulation=1, step=1, values=np.zeros(N)),
    ]
    cible = write_netcdf(_jeux(tmp_path, champs)[0], tmp_path / "coherence.nc")

    import netCDF4

    fautifs = []
    with netCDF4.Dataset(cible) as lu:
        for nom, var in lu.variables.items():
            attrs = set(var.ncattrs())
            if not {"standard_name", "units"} <= attrs:
                continue
            # **Bornes aux variables de données, et c'est une lacune nommée.**
            # Les noms des coordonnées — `forecast_reference_time`,
            # `latitude`, `height` — sont posés par la chaîne de décodage et
            # non par nos tables : les soumettre ici demanderait un relevé
            # canonique qu'aucun fichier commité n'alimente. Le redressement
            # que ce contrôle protège porte sur les variables de données.
            if not {"latitude", "longitude"} <= set(var.dimensions):
                continue
            standard, unite = var.getncattr("standard_name"), var.getncattr("units")
            attendue = canoniques.get(standard)
            if attendue is None:
                fautifs.append(f"{nom} : {standard} absent du relevé canonique")
            elif not cf_units.Unit(unite).is_convertible(cf_units.Unit(attendue)):
                fautifs.append(f"{nom} : {standard} émis en {unite!r}, canonique {attendue!r}")
    assert fautifs == [], (
        "La chaîne vient d'écrire un couple que CF déclare incompatible : " + " / ".join(fautifs)
    )
