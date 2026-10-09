"""Connecteur vers les paquets de prévision numérique de Météo-France.

Les sorties des modèles AROME et ARPEGE sont republiées par data.gouv.fr sur
un stockage objet **accessible sans authentification**, sous licence ouverte.
Le connecteur n'a donc aucun secret à porter, ce qui le rend symétrique de
celui d'ECMWF.

**Ce que cette voie ne donne pas.** Les paquets et l'API ciblée du producteur
sont deux produits distincts qui ne se recouvrent pas. Prendre les paquets,
c'est renoncer au temps sensible — grêle, foudre, visibilité, type de
précipitation — aux niveaux isothermes et au sommet d'atmosphère, qui
n'existent que dans l'API ciblée. On y gagne en revanche l'absence de secret,
une archive plus profonde, et le géopotentiel aux niveaux hauteur, que l'API
n'expose pas. Le détail figure dans `docs/arome-paquets-et-api-ciblee.md` et
`docs/arpege-paquets-et-api-ciblee.md`.

**Pas de téléchargement sélectif par plage d'octets.** Le producteur ne publie
aucun fichier d'index, contrairement à ECMWF. Le reconstruire coûterait une
requête par message, à refaire à chaque publication, et se heurte à un plafond
mesuré de quelques milliers de requêtes successives. Le levier de sélection est
donc **le choix du paquet** : un paquet de surface pèse quelques dizaines de
mégaoctets, un paquet de niveaux plusieurs gigaoctets.

**Rien n'est codé en dur sur le contenu.** Réseaux, modèles, grilles et paquets
se découvrent par listage. C'est une leçon du relevé des sources : le descriptif
technique du producteur s'écarte du contenu réel sur plusieurs points, et seule
la donnée fait foi.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol
from urllib.request import Request, urlopen

from x10_models import Retrieval

from .base import AGENT, BaseConnector, ConnectorResult, ecriture_atomique, safe_target
from .observability import (
    connector_logger,
    failure_fields,
    fetch_finished_fields,
    fetch_started_fields,
)

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path

_log = connector_logger(__name__)

# --- Description de la source -------------------------------------------------
# Une source intégrée se nomme explicitement, avec sa licence et sa provenance.

SOURCE_NAME = "meteofrance-pnt-opendata"
#: Producteur au sens `dcterms:creator`.
SOURCE_PRODUCER = "Météo-France"
#: Moissonneur, qui télécharge chez le producteur et republie. Rôle `harvester`
#: de notre codelist — sans équivalent dans DCAT ni dans INSPIRE.
SOURCE_HARVESTER = "data.gouv.fr"
SOURCE_KIND = "forecast"
SOURCE_FORMAT = "grib2"
#: Identifiant SPDX de la Licence Ouverte 2.0.
SOURCE_LICENSE = "etalab-2.0"
SOURCE_URL = "https://www.data.gouv.fr/datasets/paquets-arome-resolution-0-025deg"

BASE_URL = "https://meteofrance-pnt.s3.rbx.io.cloud.ovh.net"
PREFIXE = "pnt"

#: Une seule origine : la republication par le moissonneur. Il n'y a pas de
#: miroir, donc pas de bascule — contrairement à ECMWF et ses quatre origines.
ORIGIN = "data.gouv.fr"

#: Plafond de volume par exécution. Dimensionné pour laisser passer n'importe
#: quel paquet de surface avec une marge confortable, et pour **arrêter** les
#: paquets de niveaux, qui vont de 0,5 à 3,6 Go. Les prendre doit être un acte
#: délibéré, pas un effet de bord d'une requête mal bornée.
DEFAULT_MAX_BYTES = 256 * 1024 * 1024

#: Forme admise d'une clé d'objet. Les clés viennent d'un inventaire distant :
#: c'est une entrée, et une entrée se valide. Une liste blanche stricte évite
#: d'avoir à raisonner sur ce qu'un caractère inattendu pourrait produire plus
#: loin dans la chaîne.
CLE_VALIDE = re.compile(
    r"^pnt/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
    r"/[a-z0-9-]{1,32}/[A-Za-z0-9-]{1,32}/[A-Z0-9-]{1,16}"
    r"/[A-Za-z0-9_.:-]{1,128}\.grib2$"
)

_CLE_XML = re.compile(r"<Key>(.*?)</Key>.*?<Size>(\d+)</Size>", re.S)
_PREFIXE_XML = re.compile(r"<CommonPrefixes><Prefix>(.+?)</Prefix></CommonPrefixes>")


class MeteoFrancePntError(RuntimeError):
    """Échec d'une récupération de paquets Météo-France."""


@dataclass(frozen=True)
class ObjetDistant:
    """Un paquet disponible sur le stockage objet."""

    cle: str
    paquet: str
    tranche: str
    octets: int

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.cle}"

    @property
    def nom_local(self) -> str:
        """Nom de fichier portable.

        Les noms distants portent l'horodatage du réseau, donc des `:`, que
        Windows refuse dans un nom de fichier. La substitution est faite ici,
        une fois, plutôt que découverte à l'exécution sur un autre système.
        """
        return self.cle.rsplit("/", 1)[-1].replace(":", "-")


class Transport(Protocol):
    """Ce que le connecteur attend d'un accès HTTP.

    Un protocole plutôt qu'un client concret : les tests le substituent et
    n'atteignent jamais le réseau.
    """

    def lire(self, url: str) -> bytes: ...

    def telecharger(self, url: str, cible: Path, plafond: int) -> int: ...


class TransportHttp:  # couvert par les tests reseau
    """Accès HTTP par la bibliothèque standard.

    Aucune dépendance ajoutée : le noyau doit rester installable sans pile
    tierce. Le téléchargement est **borné pendant le transfert** et non après
    écriture, ce qui permet d'interrompre avant d'avoir rempli le disque.
    """

    def __init__(self, *, timeout: int = 60, bloc: int = 1024 * 1024) -> None:
        self.timeout = timeout
        self.bloc = bloc

    def lire(self, url: str) -> bytes:
        with urlopen(Request(url), timeout=self.timeout) as reponse:
            contenu: bytes = reponse.read()
        return contenu

    def telecharger(self, url: str, cible: Path, plafond: int) -> int:
        recu = 0
        with urlopen(Request(url), timeout=self.timeout) as reponse, cible.open("wb") as sortie:
            while True:
                morceau = reponse.read(self.bloc)
                if not morceau:
                    break
                recu += len(morceau)
                if recu > plafond:
                    sortie.close()
                    cible.unlink(missing_ok=True)
                    raise MeteoFrancePntError(
                        f"Volume au-delà du plafond de {plafond} octets pour {cible.name!r}. "
                        "Le transfert a été interrompu. Relever `max_bytes` si la prise "
                        "d'un paquet de niveaux est délibérée."
                    )
                sortie.write(morceau)
        return recu


@dataclass(frozen=True)
class MeteoFrancePntRequest:
    """Sélection à télécharger.

    `run = None` désigne le réseau le plus récent qui porte la sélection.
    `tranches = ()` prend toutes les tranches d'échéances disponibles.
    """

    model: str = "arome"
    grid: str = "0025"
    paquets: tuple[str, ...] = ("SP1",)
    tranches: tuple[str, ...] = ()
    run: str | None = None

    def __post_init__(self) -> None:
        if not self.model or not self.grid:
            raise ValueError("Le modèle et la grille sont requis.")
        if not self.paquets:
            raise ValueError("Au moins un paquet est requis.")
        if len(set(self.paquets)) != len(self.paquets):
            raise ValueError("Un paquet ne peut pas figurer deux fois dans la sélection.")


class MeteoFrancePntConnector(BaseConnector):
    """Télécharge des paquets GRIB2 depuis la republication open data."""

    def __init__(
        self,
        destination: Path,
        request: MeteoFrancePntRequest | None = None,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        run_id: str | None = None,
        transport: Transport | None = None,
    ) -> None:
        super().__init__(SOURCE_NAME)
        self.destination = destination
        self.request = request or MeteoFrancePntRequest()
        self.max_bytes = max_bytes
        self.run_id = run_id or str(uuid.uuid4())
        self.transport: Transport = transport or TransportHttp()

    # --- Découverte -----------------------------------------------------------

    def _lister(self, prefixe: str, *, delimiter: bool = False) -> str:
        url = f"{BASE_URL}/?list-type=2&prefix={prefixe}&max-keys=1000"
        if delimiter:
            url += "&delimiter=/"
        return self.transport.lire(url).decode("utf-8", "replace")

    def reseaux(self) -> tuple[str, ...]:
        """Réseaux présents sur le stockage, du plus ancien au plus récent."""
        xml = self._lister(f"{PREFIXE}/", delimiter=True)
        trouves = {p.removeprefix(f"{PREFIXE}/").rstrip("/") for p in _PREFIXE_XML.findall(xml)}
        return tuple(sorted(t for t in trouves if t))

    def objets(self, run: str) -> tuple[ObjetDistant, ...]:
        """Paquets disponibles pour un réseau, un modèle et une grille."""
        prefixe = f"{PREFIXE}/{run}/{self.request.model}/{self.request.grid}/"
        xml = self._lister(prefixe)
        sortie: list[ObjetDistant] = []
        for cle, taille in _CLE_XML.findall(xml):
            if not CLE_VALIDE.match(cle):
                continue
            morceaux = cle.split("/")
            nom = morceaux[-1]
            tranche = nom.split("__")[-2] if nom.count("__") >= 3 else ""
            sortie.append(
                ObjetDistant(cle=cle, paquet=morceaux[-2], tranche=tranche, octets=int(taille))
            )
        return tuple(sorted(sortie, key=lambda o: (o.paquet, o.tranche)))

    def _selection(self) -> tuple[str, tuple[ObjetDistant, ...]]:
        """Résout le réseau et les objets à prendre.

        Sans réseau imposé, parcourt les réseaux du plus récent au plus ancien
        et retient le premier qui porte la sélection : le réseau le plus récent
        n'est pas toujours complet, la production étant en cours.
        """
        candidats = [self.request.run] if self.request.run else list(reversed(self.reseaux()))
        if not candidats:
            raise MeteoFrancePntError("Aucun réseau disponible sur le stockage objet.")

        for run in candidats:
            if run is None:  # pragma: no cover - garde de typage
                continue
            disponibles = self.objets(run)
            retenus = tuple(
                o
                for o in disponibles
                if o.paquet in self.request.paquets
                and (not self.request.tranches or o.tranche in self.request.tranches)
            )
            manquants = set(self.request.paquets) - {o.paquet for o in retenus}
            if retenus and not manquants:
                return run, retenus

        raise MeteoFrancePntError(
            f"Aucun réseau ne porte la sélection demandée : modèle {self.request.model!r}, "
            f"grille {self.request.grid!r}, paquets {', '.join(sorted(self.request.paquets))}."
        )

    # --- Récupération ---------------------------------------------------------

    def _champs_debut(self, run: str) -> dict[str, object]:
        return fetch_started_fields(
            source=SOURCE_NAME,
            run_id=self.run_id,
            origin=ORIGIN,
            details={
                "model": self.request.model,
                "grid": self.request.grid,
                "packages": list(self.request.paquets),
                "run": run,
            },
        )

    def fetch(self) -> ConnectorResult:
        racine = self.destination.resolve()
        racine.mkdir(parents=True, exist_ok=True)

        started_at = datetime.now(UTC)
        debut = time.perf_counter_ns()

        try:
            run, objets = self._selection()
        except Exception as erreur:
            _log.error(
                "Sélection Météo-France impossible",
                extra={
                    **fetch_started_fields(source=SOURCE_NAME, run_id=self.run_id, origin=ORIGIN),
                    **failure_fields(erreur),
                    "event.duration": time.perf_counter_ns() - debut,
                },
            )
            raise

        _log.info("Récupération Météo-France démarrée", extra=self._champs_debut(run))

        artefacts: list[Path] = []
        recu = 0
        try:
            for objet in objets:
                cible = safe_target(racine, objet.nom_local)
                # L'atomicité est posée ici et non dans le transport : un
                # transport injecté en bénéficie sans rien savoir, et c'est
                # l'appelant qui connaît le nom définitif.
                with ecriture_atomique(cible) as provisoire:
                    recu += self.transport.telecharger(objet.url, provisoire, self.max_bytes - recu)
                artefacts.append(cible)
        except Exception as erreur:
            for fait in artefacts:
                fait.unlink(missing_ok=True)
            _log.error(
                "Récupération Météo-France en échec",
                extra={
                    **self._champs_debut(run),
                    **failure_fields(erreur),
                    "event.duration": time.perf_counter_ns() - debut,
                },
            )
            raise

        resultat = ConnectorResult(
            source=SOURCE_NAME,
            outcome="success",
            message=(
                f"{len(artefacts)} paquet(s) GRIB2 récupéré(s) pour le réseau {run}, {recu} octets."
            ),
            run_id=self.run_id,
            origin=ORIGIN,
            started_at=started_at,
            duration_ns=time.perf_counter_ns() - debut,
            bytes_downloaded=recu,
            retrieval=Retrieval(
                artefacts=tuple(artefacts),
                retrieved_at=datetime.now(UTC),
                dataset=f"{SOURCE_NAME}:{self.request.model}:{self.request.grid}",
                origin=ORIGIN,
                selection={
                    "model": self.request.model,
                    "grid": self.request.grid,
                    "packages": list(self.request.paquets),
                    "slices": [o.tranche for o in objets],
                    "run": run,
                },
                agent=AGENT,
                license=SOURCE_LICENSE,
            ),
        )
        _log.info("Récupération Météo-France terminée", extra=fetch_finished_fields(resultat))
        return resultat


__all__ = [
    "AGENT",
    "BASE_URL",
    "CLE_VALIDE",
    "DEFAULT_MAX_BYTES",
    "ORIGIN",
    "PREFIXE",
    "SOURCE_FORMAT",
    "SOURCE_HARVESTER",
    "SOURCE_KIND",
    "SOURCE_LICENSE",
    "SOURCE_NAME",
    "SOURCE_PRODUCER",
    "SOURCE_URL",
    "MeteoFrancePntConnector",
    "MeteoFrancePntError",
    "MeteoFrancePntRequest",
    "ObjetDistant",
    "Transport",
    "TransportHttp",
]
