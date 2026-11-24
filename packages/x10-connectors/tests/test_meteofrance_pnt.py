"""Source Météo-France PNT — le connecteur, sans aucun accès réseau.

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
    ORIGIN,
    SOURCE_LICENSE,
    SOURCE_NAME,
    VALID_KEY,
    RemoteObject,
)

RESEAUX = ("2026-10-05T00:00:00Z", "2026-10-05T03:00:00Z")


def _cle(run: str, modele: str, grid: str, package: str, time_range: str) -> str:
    nom = f"{modele}__{grid}__{package}__{time_range}__{run}.grib2"
    return f"pnt/{run}/{modele}/{grid}/{package}/{nom}"


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
                f"Volume above the {plafond} byte ceiling for {cible.name!r}."
            )
        cible.write_bytes(b"\x00" * self.taille_ecrite)
        return self.taille_ecrite


def _catalogue_complet() -> dict[str, dict[str, int]]:
    return {
        run: {
            _cle(run, "arome", "0025", package, time_range): 1000
            for package in ("SP1", "SP2")
            for time_range in ("00H06H", "07H12H")
        }
        for run in RESEAUX
    }


# --- Découverte ----------------------------------------------------------------


def test_les_reseaux_se_decouvrent_par_listage(tmp_path):
    transport = _TransportSimule(catalogue=_catalogue_complet())
    connecteur = MeteoFrancePntConnector(tmp_path, transport=transport)
    assert connecteur.reseaux() == RESEAUX


class _TransportFige:
    """Transport qui rend un listage figé, pour éprouver le parseur seul."""

    def __init__(self, xml: str) -> None:
        self.xml = xml

    def lire(self, url: str) -> bytes:
        if "delimiter=/" in url:
            return _xml_prefixes((RESEAUX[0],)).encode()
        return self.xml.encode()

    def telecharger(self, url, cible, plafond) -> int:
        raise AssertionError("ce transport ne telecharge pas")


def _listage(*blocs: str) -> str:
    return f"<?xml version='1.0'?><ListBucketResult>{''.join(blocs)}</ListBucketResult>"


def _contents(cle: str, **champs: str) -> str:
    corps = "".join(f"<{nom}>{valeur}</{nom}>" for nom, valeur in champs.items())
    return f"<Contents><Key>{cle}</Key>{corps}</Contents>"


def _objets_de(tmp_path, xml: str):
    connecteur = MeteoFrancePntConnector(tmp_path, transport=_TransportFige(xml))
    return connecteur.objects(RESEAUX[0])


def test_la_date_que_l_origine_declare_est_lue(tmp_path):
    """La Licence Ouverte exige une date de dernière mise à jour, et le
    listage la rend déjà : nous la jetions."""
    cle = _cle(RESEAUX[0], "arome", "0025", "SP1", "00H06H")
    xml = _listage(
        _contents(cle, LastModified="2026-11-24T13:15:33.000Z", ETag='"abc"', Size="1000")
    )
    (objet,) = _objets_de(tmp_path, xml)
    assert objet.last_modified is not None
    assert objet.last_modified.year == 2026
    assert objet.last_modified.hour == 13
    assert objet.last_modified.tzinfo is not None, "la date sort en UTC, jamais naïve"


def test_un_objet_sans_date_reste_servi(tmp_path):
    """L'absence d'un champ accessoire ne retire pas un granule."""
    cle = _cle(RESEAUX[0], "arome", "0025", "SP1", "00H06H")
    (objet,) = _objets_de(tmp_path, _listage(_contents(cle, Size="1000")))
    assert objet.size_bytes == 1000
    assert objet.last_modified is None


def test_une_date_illisible_ne_fait_pas_disparaitre_l_objet(tmp_path):
    """Une date que nous ne savons pas lire est une métadonnée perdue ; le
    granule, lui, n'est pas perdu. L'inverse serait la classe de défaut la
    plus coûteuse — une donnée absente sans que rien ne le signale."""
    cle = _cle(RESEAUX[0], "arome", "0025", "SP1", "00H06H")
    xml = _listage(_contents(cle, LastModified="pas une date", Size="1000"))
    (objet,) = _objets_de(tmp_path, xml)
    assert objet.size_bytes == 1000
    assert objet.last_modified is None


def test_un_objet_sans_taille_ne_vole_pas_celle_du_suivant(tmp_path):
    r"""**Le défaut que la lecture par bloc ferme.**

    Une expression régulière traversante — `<Key>(.*?)</Key>.*?<Size>(\d+)`
    — appariait la clé d'un objet sans taille avec la taille de l'objet
    **suivant**, et consommait ce dernier au passage : une taille fausse sur
    le premier, et le second disparaissait sans un mot. Lire chaque bloc
    `<Contents>` séparément rend les deux cas distincts.
    """
    premier = _cle(RESEAUX[0], "arome", "0025", "SP1", "00H06H")
    second = _cle(RESEAUX[0], "arome", "0025", "SP2", "07H12H")
    xml = _listage(_contents(premier), _contents(second, Size="4242"))

    objets = _objets_de(tmp_path, xml)

    assert [o.package for o in objets] == ["SP2"], "l'objet sans taille est écarté, lui seul"
    assert objets[0].size_bytes == 4242, "et le suivant garde la sienne"


def test_les_objets_portent_paquet_tranche_et_taille(tmp_path):
    transport = _TransportSimule(catalogue=_catalogue_complet())
    connecteur = MeteoFrancePntConnector(tmp_path, transport=transport)
    objets = connecteur.objects(RESEAUX[0])
    assert {o.package for o in objets} == {"SP1", "SP2"}
    assert {o.time_range for o in objets} == {"00H06H", "07H12H"}
    assert all(o.size_bytes == 1000 for o in objets)


def test_le_reseau_le_plus_recent_est_retenu(tmp_path):
    transport = _TransportSimule(catalogue=_catalogue_complet())
    connecteur = MeteoFrancePntConnector(
        tmp_path, MeteoFrancePntRequest(packages=("SP1",)), transport=transport
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
        tmp_path, MeteoFrancePntRequest(packages=("SP1", "SP2")), transport=transport
    )
    resultat = connecteur.fetch()
    assert resultat.retrieval is not None
    assert resultat.retrieval.selection["run"] == RESEAUX[0]


def test_une_selection_introuvable_echoue_clairement(tmp_path):
    transport = _TransportSimule(catalogue=_catalogue_complet())
    connecteur = MeteoFrancePntConnector(
        tmp_path, MeteoFrancePntRequest(packages=("IP9",)), transport=transport
    )
    with pytest.raises(MeteoFrancePntError, match="No model run carries the requested selection"):
        connecteur.fetch()


# --- Sécurité ------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "pnt/2026-10-05T00:00:00Z/arome/0025/SP1/../../../evade.grib2",
        "pnt/2026-10-05T00:00:00Z/arome/0025/SP1/fichier.sh",
        "https://ailleurs.example/pnt/x.grib2",
        "pnt/pas-un-reseau/arome/0025/SP1/x.grib2",
    ],
)
def test_une_cle_hors_forme_attendue_est_ignoree(key):
    assert VALID_KEY.match(key) is None


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
    objets = connecteur.objects(run)
    assert len(objets) == 1
    assert "evade" not in objets[0].key


def test_le_nom_local_est_portable():
    """Les noms distants portent l'horodatage, donc des deux-points, que
    Windows refuse dans un nom de fichier."""
    objet = RemoteObject(
        key=_cle(RESEAUX[0], "arome", "0025", "SP1", "00H06H"),
        package="SP1",
        time_range="00H06H",
        size_bytes=1,
    )
    assert ":" not in objet.local_name
    assert objet.local_name.endswith(".grib2")


def test_un_nom_local_qui_remonte_l_arborescence_est_refuse(tmp_path):
    from x10_connectors.base import safe_target

    with pytest.raises(UnsafeDestinationError, match="outside the intended root"):
        safe_target(tmp_path, "../evade.grib2")


def test_le_plafond_de_volume_interrompt_et_nettoie(tmp_path):
    transport = _TransportSimule(catalogue=_catalogue_complet(), taille_ecrite=4096)
    connecteur = MeteoFrancePntConnector(
        tmp_path, MeteoFrancePntRequest(packages=("SP1",)), max_bytes=100, transport=transport
    )
    with pytest.raises(MeteoFrancePntError, match="ceiling"):
        connecteur.fetch()
    assert list(tmp_path.glob("*.grib2")) == []


def test_le_plafond_porte_sur_le_cumul_et_non_sur_chaque_fichier(tmp_path):
    """Un plafond appliqué fichier par fichier ne bornerait rien dès lors que
    la sélection en compte plusieurs."""
    transport = _TransportSimule(catalogue=_catalogue_complet(), taille_ecrite=80)
    connecteur = MeteoFrancePntConnector(
        tmp_path,
        MeteoFrancePntRequest(packages=("SP1",), time_ranges=("00H06H", "07H12H")),
        max_bytes=100,
        transport=transport,
    )
    with pytest.raises(MeteoFrancePntError, match="ceiling"):
        connecteur.fetch()


# --- Compte rendu et lignage ---------------------------------------------------


def test_le_compte_rendu_porte_provenance_licence_et_selection(tmp_path):
    transport = _TransportSimule(catalogue=_catalogue_complet())
    connecteur = MeteoFrancePntConnector(
        tmp_path,
        MeteoFrancePntRequest(packages=("SP1",), time_ranges=("00H06H",)),
        transport=transport,
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
        tmp_path,
        MeteoFrancePntRequest(packages=("SP1",), time_ranges=("00H06H",)),
        transport=transport,
    )
    resultat = connecteur.fetch()
    repris = type(resultat).model_validate(json.loads(resultat.model_dump_json()))
    assert repris == resultat


def test_une_requete_sans_paquet_est_refusee():
    with pytest.raises(ValueError, match="At least one package"):
        MeteoFrancePntRequest(packages=())


def test_un_paquet_en_double_est_refuse():
    with pytest.raises(ValueError, match="twice"):
        MeteoFrancePntRequest(packages=("SP1", "SP1"))


# --- Service reel --------------------------------------------------------------


@pytest.mark.network
def test_telechargement_reel_d_un_paquet_de_surface(tmp_path):
    """Atteint le service réel. Lancer par `uv run pytest -m network`."""
    import struct

    resultat = MeteoFrancePntConnector(
        tmp_path,
        MeteoFrancePntRequest(
            model="arome", grid="0025", packages=("SP1",), time_ranges=("00H06H",)
        ),
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

    from x10_connectors.grib2 import open_granule, wind_from_direction, wind_speed

    resultat = MeteoFrancePntConnector(
        tmp_path,
        MeteoFrancePntRequest(
            model="arome", grid="0025", packages=("SP1",), time_ranges=("00H06H",)
        ),
    ).fetch()
    assert resultat.retrieval is not None

    cible = None
    for jeu in open_granule(resultat.retrieval.artefacts[0]):
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
