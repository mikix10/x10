"""Tests du connecteur Météo-France, sans aucun accès réseau.

Le transport est substitué : les listages sont fabriqués, les téléchargements
écrivent des octets inertes. Rien ne sort de la machine, et la suite reste
exécutable hors ligne.
"""

from __future__ import annotations

import json

import pytest

from x10_connectors import (
    MeteoFrancePntConnector,
    MeteoFrancePntError,
    MeteoFrancePntRequest,
    UnsafeDestinationError,
)
from x10_connectors.meteofrance_pnt import (
    CLE_VALIDE,
    ORIGIN,
    SOURCE_LICENSE,
    SOURCE_NAME,
    ObjetDistant,
)

RESEAUX = ("2026-10-05T00:00:00Z", "2026-10-05T03:00:00Z")


def _cle(run: str, modele: str, grille: str, paquet: str, tranche: str) -> str:
    return (
        f"pnt/{run}/{modele}/{grille}/{paquet}/{modele}__{grille}__{paquet}__{tranche}__{run}.grib2"
    )


def _xml_prefixes(runs: tuple[str, ...]) -> str:
    corps = "".join(f"<CommonPrefixes><Prefix>pnt/{r}/</Prefix></CommonPrefixes>" for r in runs)
    return f"<?xml version='1.0'?><ListBucketResult>{corps}</ListBucketResult>"


def _xml_objets(cles: dict[str, int]) -> str:
    corps = "".join(f"<Contents><Key>{c}</Key><Size>{t}</Size></Contents>" for c, t in cles.items())
    return f"<?xml version='1.0'?><ListBucketResult>{corps}</ListBucketResult>"


class _TransportSimule:
    """Transport de substitution : ni réseau, ni octets réels."""

    def __init__(self, *, catalogue: dict[str, dict[str, int]], taille_ecrite: int = 64) -> None:
        #: run -> {clé: taille}
        self.catalogue = catalogue
        self.taille_ecrite = taille_ecrite
        self.telecharges: list[str] = []

    def lire(self, url: str) -> bytes:
        if "delimiter=/" in url:
            return _xml_prefixes(tuple(self.catalogue)).encode()
        prefixe = url.split("prefix=")[1].split("&")[0]
        run = prefixe.split("/")[1]
        objets = {c: t for c, t in self.catalogue.get(run, {}).items() if c.startswith(prefixe)}
        return _xml_objets(objets).encode()

    def telecharger(self, url: str, cible, plafond: int) -> int:
        self.telecharges.append(url)
        if self.taille_ecrite > plafond:
            raise MeteoFrancePntError(
                f"Volume au-delà du plafond de {plafond} octets pour {cible.name!r}."
            )
        cible.write_bytes(b"\x00" * self.taille_ecrite)
        return self.taille_ecrite


def _catalogue_complet() -> dict[str, dict[str, int]]:
    return {
        run: {
            _cle(run, "arome", "0025", paquet, tranche): 1000
            for paquet in ("SP1", "SP2")
            for tranche in ("00H06H", "07H12H")
        }
        for run in RESEAUX
    }


# --- Découverte ----------------------------------------------------------------


def test_les_reseaux_se_decouvrent_par_listage(tmp_path):
    transport = _TransportSimule(catalogue=_catalogue_complet())
    connecteur = MeteoFrancePntConnector(tmp_path, transport=transport)
    assert connecteur.reseaux() == RESEAUX


def test_les_objets_portent_paquet_tranche_et_taille(tmp_path):
    transport = _TransportSimule(catalogue=_catalogue_complet())
    connecteur = MeteoFrancePntConnector(tmp_path, transport=transport)
    objets = connecteur.objets(RESEAUX[0])
    assert {o.paquet for o in objets} == {"SP1", "SP2"}
    assert {o.tranche for o in objets} == {"00H06H", "07H12H"}
    assert all(o.octets == 1000 for o in objets)


def test_le_reseau_le_plus_recent_est_retenu(tmp_path):
    transport = _TransportSimule(catalogue=_catalogue_complet())
    connecteur = MeteoFrancePntConnector(
        tmp_path, MeteoFrancePntRequest(paquets=("SP1",)), transport=transport
    )
    resultat = connecteur.fetch()
    assert resultat.retrieval is not None
    assert resultat.retrieval.selection["run"] == RESEAUX[-1]


def test_un_reseau_incomplet_fait_reculer_vers_le_precedent(tmp_path):
    """La production est en cours : le dernier réseau n'est pas toujours complet.

    Reculer vaut mieux qu'échouer — et mieux que livrer une sélection partielle
    en la faisant passer pour complète."""
    catalogue = _catalogue_complet()
    recent = RESEAUX[-1]
    catalogue[recent] = {c: t for c, t in catalogue[recent].items() if "SP2" not in c}
    transport = _TransportSimule(catalogue=catalogue)
    connecteur = MeteoFrancePntConnector(
        tmp_path, MeteoFrancePntRequest(paquets=("SP1", "SP2")), transport=transport
    )
    resultat = connecteur.fetch()
    assert resultat.retrieval is not None
    assert resultat.retrieval.selection["run"] == RESEAUX[0]


def test_une_selection_introuvable_echoue_clairement(tmp_path):
    transport = _TransportSimule(catalogue=_catalogue_complet())
    connecteur = MeteoFrancePntConnector(
        tmp_path, MeteoFrancePntRequest(paquets=("IP9",)), transport=transport
    )
    with pytest.raises(MeteoFrancePntError, match="Aucun réseau ne porte la sélection"):
        connecteur.fetch()


# --- Sécurité ------------------------------------------------------------------


@pytest.mark.parametrize(
    "cle",
    [
        "pnt/2026-10-05T00:00:00Z/arome/0025/SP1/../../../evade.grib2",
        "pnt/2026-10-05T00:00:00Z/arome/0025/SP1/fichier.sh",
        "https://ailleurs.example/pnt/x.grib2",
        "pnt/pas-un-reseau/arome/0025/SP1/x.grib2",
    ],
)
def test_une_cle_hors_forme_attendue_est_ignoree(cle):
    assert CLE_VALIDE.match(cle) is None


def test_une_cle_malformee_n_est_pas_retenue_par_l_inventaire(tmp_path):
    run = RESEAUX[0]
    catalogue = {
        run: {
            _cle(run, "arome", "0025", "SP1", "00H06H"): 10,
            f"pnt/{run}/arome/0025/SP1/../evade.grib2": 10,
        }
    }
    transport = _TransportSimule(catalogue=catalogue)
    connecteur = MeteoFrancePntConnector(tmp_path, transport=transport)
    objets = connecteur.objets(run)
    assert len(objets) == 1
    assert "evade" not in objets[0].cle


def test_le_nom_local_est_portable():
    """Les noms distants portent l'horodatage, donc des deux-points, que
    Windows refuse dans un nom de fichier."""
    objet = ObjetDistant(
        cle=_cle(RESEAUX[0], "arome", "0025", "SP1", "00H06H"),
        paquet="SP1",
        tranche="00H06H",
        octets=1,
    )
    assert ":" not in objet.nom_local
    assert objet.nom_local.endswith(".grib2")


def test_un_nom_local_qui_remonte_l_arborescence_est_refuse(tmp_path):
    from x10_connectors.base import safe_target

    with pytest.raises(UnsafeDestinationError, match="hors de la racine"):
        safe_target(tmp_path, "../evade.grib2")


def test_le_plafond_de_volume_interrompt_et_nettoie(tmp_path):
    transport = _TransportSimule(catalogue=_catalogue_complet(), taille_ecrite=4096)
    connecteur = MeteoFrancePntConnector(
        tmp_path, MeteoFrancePntRequest(paquets=("SP1",)), max_bytes=100, transport=transport
    )
    with pytest.raises(MeteoFrancePntError, match="plafond"):
        connecteur.fetch()
    assert list(tmp_path.glob("*.grib2")) == []


def test_le_plafond_porte_sur_le_cumul_et_non_sur_chaque_fichier(tmp_path):
    """Un plafond appliqué fichier par fichier ne bornerait rien dès lors que
    la sélection en compte plusieurs."""
    transport = _TransportSimule(catalogue=_catalogue_complet(), taille_ecrite=80)
    connecteur = MeteoFrancePntConnector(
        tmp_path,
        MeteoFrancePntRequest(paquets=("SP1",), tranches=("00H06H", "07H12H")),
        max_bytes=100,
        transport=transport,
    )
    with pytest.raises(MeteoFrancePntError, match="plafond"):
        connecteur.fetch()


# --- Compte rendu et lignage ---------------------------------------------------


def test_le_compte_rendu_porte_provenance_licence_et_selection(tmp_path):
    transport = _TransportSimule(catalogue=_catalogue_complet())
    connecteur = MeteoFrancePntConnector(
        tmp_path, MeteoFrancePntRequest(paquets=("SP1",), tranches=("00H06H",)), transport=transport
    )
    resultat = connecteur.fetch()

    assert resultat.source == SOURCE_NAME
    assert resultat.outcome == "success"
    assert resultat.origin == ORIGIN
    assert resultat.bytes_downloaded == 64

    lignage = resultat.retrieval
    assert lignage is not None
    assert lignage.license == SOURCE_LICENSE
    assert lignage.origin == ORIGIN
    assert lignage.selection["model"] == "arome"
    assert lignage.selection["packages"] == ["SP1"]
    assert len(lignage.artefacts) == 1


def test_le_compte_rendu_fait_l_aller_retour_json(tmp_path):
    transport = _TransportSimule(catalogue=_catalogue_complet())
    connecteur = MeteoFrancePntConnector(
        tmp_path, MeteoFrancePntRequest(paquets=("SP1",), tranches=("00H06H",)), transport=transport
    )
    resultat = connecteur.fetch()
    repris = type(resultat).model_validate(json.loads(resultat.model_dump_json()))
    assert repris == resultat


def test_une_requete_sans_paquet_est_refusee():
    with pytest.raises(ValueError, match="Au moins un paquet"):
        MeteoFrancePntRequest(paquets=())


def test_un_paquet_en_double_est_refuse():
    with pytest.raises(ValueError, match="deux fois"):
        MeteoFrancePntRequest(paquets=("SP1", "SP1"))


# --- Service reel --------------------------------------------------------------


@pytest.mark.network
def test_telechargement_reel_d_un_paquet_de_surface(tmp_path):
    """Atteint le service réel. Lancer par `uv run pytest -m network`."""
    import struct

    resultat = MeteoFrancePntConnector(
        tmp_path,
        MeteoFrancePntRequest(model="arome", grid="0025", paquets=("SP1",), tranches=("00H06H",)),
    ).fetch()

    assert resultat.outcome == "success"
    assert resultat.retrieval is not None
    assert resultat.retrieval.license == SOURCE_LICENSE
    chemin = resultat.retrieval.artefacts[0]
    donnees = chemin.read_bytes()
    assert donnees[:4] == b"GRIB"
    assert donnees[7] == 2, "edition GRIB attendue : 2"
    assert struct.unpack(">Q", donnees[8:16])[0] <= len(donnees)
    assert donnees[-4:] == b"7777"


@pytest.mark.network
def test_le_vent_se_reconstitue_depuis_les_composantes_sur_donnees_reelles(tmp_path):
    """La vérification qui justifie d'écarter direction et force.

    Mesurée le 06/10/2026 sur 4,66 millions de points d'un paquet AROME SP1 :
    écart maximal de 0,015 m/s sur la force, et de 0,25 degré sur la direction
    dès que le vent dépasse 3 m/s. La seule dégradation est sous 0,5 m/s, où la
    direction n'a de toute façon pas de sens physique.
    """
    import numpy as np

    from x10_connectors.decoding import open_package, wind_from_direction, wind_speed

    resultat = MeteoFrancePntConnector(
        tmp_path,
        MeteoFrancePntRequest(model="arome", grid="0025", paquets=("SP1",), tranches=("00H06H",)),
    ).fetch()
    assert resultat.retrieval is not None

    cible = None
    for jeu in open_package(resultat.retrieval.artefacts[0]):
        if {"u10", "v10", "wdir10", "si10"} <= set(jeu.data_vars):
            cible = jeu
            break
    assert cible is not None, "les quatre champs de vent attendus sont absents"

    dd_stock = cible["wdir10"].values
    ff_stock = cible["si10"].values
    dd_calc = wind_from_direction(cible["u10"], cible["v10"]).values
    ff_calc = wind_speed(cible["u10"], cible["v10"]).values

    fini = np.isfinite(dd_stock) & np.isfinite(ff_stock)
    # Le domaine est trapezoidal : environ 17 % de la grille est absente.
    assert 0.10 < 1 - fini.mean() < 0.25

    assert np.max(np.abs(ff_calc - ff_stock)[fini]) < 0.05

    ecart = np.abs((dd_calc - dd_stock + 180.0) % 360.0 - 180.0)[fini]
    etabli = ff_stock[fini] > 3.0
    assert np.max(ecart[etabli]) < 1.0
