"""Connecteur vers les prévisions IFS d'ECMWF en open data.

Le service publie, à côté de chaque fichier GRIB2, un index en JSON Lines
donnant le décalage et la longueur de chaque message. Un téléchargement
sélectif par requête HTTP Byte-Range évite donc de transférer le fichier
entier : les quatre paramètres de surface pèsent environ 2,8 Mo là où le
fichier complet en fait 135.

Ce travail est déjà fait par le client officiel `ecmwf-opendata`, que ce
module se contente d'encadrer. Sa valeur propre est ailleurs : provenance,
licence, bornes de sécurité et restitution normalisée.

**La sélection ne porte pas sur la géographie.** L'index adresse le message,
et un message est un champ global dont la section de données est un bloc
unique compressé en CCSDS. Un sous-domaine s'obtient après décodage, ce qui
sort du périmètre de ce connecteur.

Dépendance optionnelle : installer l'extra `ecmwf`.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from x10_models import Retrieval

from .base import AGENT, BaseConnector, ConnectorResult, safe_target
from .observability import (
    connector_logger,
    failure_fields,
    fetch_finished_fields,
    fetch_started_fields,
)

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

_log = connector_logger(__name__)

# --- Description de la source -------------------------------------------------
# Une source intégrée se nomme explicitement, avec sa licence et sa provenance.

SOURCE_NAME = "ecmwf-ifs-opendata"
SOURCE_PROVIDER = "ECMWF"
SOURCE_KIND = "forecast"
SOURCE_FORMAT = "grib2"
SOURCE_LICENSE = "CC-BY-4.0"
SOURCE_URL = "https://data.ecmwf.int/forecasts"

#: Origines équivalentes exposées par le client officiel. Les trois miroirs
#: infonuagiques servent de repli quand le portail d'ECMWF est saturé.
ORIGINS = ("ecmwf", "aws", "azure", "google")

#: Paramètres de surface du premier périmètre : température et point de rosée
#: à 2 m, composantes du vent à 10 m.
DEFAULT_PARAMETERS = ("2t", "2d", "10u", "10v")

#: Plafond de volume par exécution. Généreux au regard des 2,8 Mo attendus,
#: mais borné bien en deçà des 135 Mo du fichier complet.
DEFAULT_MAX_BYTES = 64 * 1024 * 1024


class OpenDataClient(Protocol):
    """Ce que le connecteur attend d'un client ECMWF open data.

    Un protocole plutôt qu'un type concret : le client officiel le satisfait
    structurellement, et les tests peuvent le substituer sans réseau.
    """

    def retrieve(self, request: dict[str, Any], target: str) -> None: ...


class EcmwfIfsError(RuntimeError):
    """Échec d'une récupération ECMWF IFS."""


#: Erreurs qui **n'entraînent pas** de repli sur une autre origine : elles
#: viennent de la requête ou de nous, pas du diffuseur. Une autre origine
#: servirait la même donnée et échouerait de la même manière. Tout le reste —
#: réseau, HTTP, erreurs propres au client — déclenche une bascule.
#:
#: `UnsafeDestinationError` dérive de `ValueError` et y figure donc déjà.
NON_REESSAYABLE = (EcmwfIfsError, ValueError, TypeError)


@dataclass(frozen=True)
class EcmwfIfsRequest:
    """Sélection à télécharger.

    `date = -1` désigne la dernière exécution disponible, convention du client
    officiel. `step` est une échéance en heures.
    """

    parameters: tuple[str, ...] = DEFAULT_PARAMETERS
    step: int = 0
    time: int = 0
    date: int = -1
    #: Origines à tenter, **dans l'ordre**. Le connecteur passe à la suivante
    #: quand une origine est inaccessible. L'ordre vient en général de
    #: `CatalogEntry.origins()`, que l'appelant résout — un connecteur n'a pas
    #: à connaître le catalogue.
    origins: tuple[str, ...] = ("ecmwf",)

    def __post_init__(self) -> None:
        if not self.parameters:
            raise ValueError("Au moins un paramètre est requis.")
        if not self.origins:
            raise ValueError("Au moins une origine est requise.")
        inconnues = sorted(set(self.origins) - set(ORIGINS))
        if inconnues:
            raise ValueError(
                f"Origine(s) inconnue(s) : {', '.join(inconnues)}. Attendu parmi {ORIGINS}."
            )
        if len(set(self.origins)) != len(self.origins):
            raise ValueError("Une origine ne peut pas figurer deux fois dans l'ordre de repli.")
        if self.step < 0:
            raise ValueError("L'échéance ne peut pas être négative.")


class EcmwfIfsOpenDataConnector(BaseConnector):
    """Télécharge une sélection de messages GRIB2 depuis ECMWF open data.

    Le client officiel n'expose **aucun délai maximal** de requête, et ses
    valeurs de reprise par défaut — 500 tentatives espacées de 120 secondes —
    autorisent une attente de plusieurs heures. Les valeurs retenues ici sont
    délibérément basses.
    """

    def __init__(
        self,
        destination: Path,
        request: EcmwfIfsRequest | None = None,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_retries: int = 3,
        retry_after: int = 10,
        run_id: str | None = None,
        client_factory: Callable[..., OpenDataClient] | None = None,
    ) -> None:
        super().__init__(SOURCE_NAME)
        self.destination = destination
        self.request = request or EcmwfIfsRequest()
        self.max_bytes = max_bytes
        self.max_retries = max_retries
        self.retry_after = retry_after
        #: Fourni par l'appelant quand il en a un — l'identifiant d'exécution
        #: d'un ordonnanceur corrèle alors nos journaux aux siens.
        self.run_id = run_id or str(uuid.uuid4())
        self._client_factory = client_factory

    def _client(self, origin: str) -> OpenDataClient:  # couvert par les tests reseau
        if self._client_factory is not None:
            return self._client_factory(
                source=origin,
                maximum_retries=self.max_retries,
                retry_after=self.retry_after,
            )
        try:
            from ecmwf.opendata import Client
        except ImportError as exc:  # pragma: no cover - depend de l'extra
            raise EcmwfIfsError(
                "Le client officiel est absent. Installer l'extra : "
                "uv sync --all-packages --extra ecmwf"
            ) from exc
        client: OpenDataClient = Client(
            source=origin,
            model="ifs",
            resol="0p25",
            verify=True,
            maximum_retries=self.max_retries,
            retry_after=self.retry_after,
        )
        return client

    def _mars_request(self, parameter: str) -> dict[str, Any]:
        return {
            "date": self.request.date,
            "time": self.request.time,
            "step": self.request.step,
            "stream": "oper",
            "type": "fc",
            "levtype": "sfc",
            "param": parameter,
        }

    def _download(self, root: Path, origin: str) -> tuple[list[Path], int]:
        client = self._client(origin)
        artefacts: list[Path] = []
        downloaded = 0
        for parameter in self.request.parameters:
            target = safe_target(root, f"{parameter}-{self.request.step}h.grib2")
            client.retrieve(request=self._mars_request(parameter), target=str(target))

            if not target.exists():
                raise EcmwfIfsError(f"Aucun fichier produit pour le paramètre {parameter!r}.")
            downloaded += target.stat().st_size
            if downloaded > self.max_bytes:
                target.unlink(missing_ok=True)
                raise EcmwfIfsError(
                    f"Volume téléchargé au-delà du plafond de {self.max_bytes} octets. "
                    "Le contrôle est effectué après écriture : le client n'expose pas "
                    "le flux, il n'est donc pas interrompible en cours de transfert."
                )
            artefacts.append(target)
        return artefacts, downloaded

    def _champs_debut(self, origin: str, attempt: int) -> dict[str, Any]:
        return fetch_started_fields(
            source=SOURCE_NAME,
            run_id=self.run_id,
            origin=origin,
            attempt=attempt,
            details={
                "parameters": list(self.request.parameters),
                "step": self.request.step,
            },
        )

    def _tenter(self, root: Path, origin: str) -> tuple[list[Path], int]:
        """Une tentative sur une origine. Nettoie derrière elle en cas d'échec,
        faute de quoi un fichier partiel subsisterait avant la bascule."""
        try:
            return self._download(root, origin)
        except Exception:
            for reste in root.glob(f"*-{self.request.step}h.grib2"):
                reste.unlink(missing_ok=True)
            raise

    def fetch(self) -> ConnectorResult:
        root = self.destination.resolve()
        root.mkdir(parents=True, exist_ok=True)

        started_at = datetime.now(UTC)
        debut = time.perf_counter_ns()
        origines = self.request.origins

        artefacts: list[Path] = []
        downloaded = 0
        retenue = ""
        for rang, origin in enumerate(origines, start=1):
            _log.info(
                "Récupération ECMWF IFS démarrée",
                extra=self._champs_debut(origin, rang),
            )
            try:
                artefacts, downloaded = self._tenter(root, origin)
            except NON_REESSAYABLE as erreur:
                # Un défaut de notre fait ou de la requête : une autre origine
                # servirait la même donnée et échouerait de la même manière.
                _log.error(
                    "Récupération ECMWF IFS en échec, sans repli",
                    extra={
                        **self._champs_debut(origin, rang),
                        **failure_fields(erreur),
                        "event.duration": time.perf_counter_ns() - debut,
                    },
                )
                raise
            except Exception as erreur:
                # Un repli reste un incident mineur ; l'échec de la dernière
                # origine est terminal et doit remonter comme tel.
                dernier = rang == len(origines)
                journalise = _log.error if dernier else _log.warning
                journalise(
                    "Toutes les origines sont inaccessibles"
                    if dernier
                    else "Origine inaccessible, repli sur la suivante",
                    extra={
                        **self._champs_debut(origin, rang),
                        **failure_fields(erreur),
                        "event.duration": time.perf_counter_ns() - debut,
                    },
                )
                if dernier:
                    raise
                continue
            retenue = origin
            break

        resultat = ConnectorResult(
            source=SOURCE_NAME,
            outcome="success",
            message=(
                f"{len(artefacts)} message(s) GRIB2 récupéré(s) depuis l'origine "
                f"{retenue!r}, {downloaded} octets."
            ),
            run_id=self.run_id,
            origin=retenue,
            started_at=started_at,
            duration_ns=time.perf_counter_ns() - debut,
            bytes_downloaded=downloaded,
            retrieval=Retrieval(
                artefacts=tuple(artefacts),
                retrieved_at=datetime.now(UTC),
                dataset=SOURCE_NAME,
                origin=retenue,
                selection={
                    "parameters": list(self.request.parameters),
                    "step": self.request.step,
                    "time": self.request.time,
                    "date": self.request.date,
                },
                agent=AGENT,
                license=SOURCE_LICENSE,
            ),
        )
        _log.info("Récupération ECMWF IFS terminée", extra=fetch_finished_fields(resultat))
        return resultat


__all__ = [
    "AGENT",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_PARAMETERS",
    "NON_REESSAYABLE",
    "ORIGINS",
    "SOURCE_FORMAT",
    "SOURCE_KIND",
    "SOURCE_LICENSE",
    "SOURCE_NAME",
    "SOURCE_PROVIDER",
    "SOURCE_URL",
    "EcmwfIfsError",
    "EcmwfIfsOpenDataConnector",
    "EcmwfIfsRequest",
    "OpenDataClient",
]
