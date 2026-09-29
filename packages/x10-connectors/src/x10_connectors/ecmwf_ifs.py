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

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from x10_models import Provenance

from .base import BaseConnector, ConnectorResult

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

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
    origin: str = "ecmwf"

    def __post_init__(self) -> None:
        if not self.parameters:
            raise ValueError("Au moins un paramètre est requis.")
        if self.origin not in ORIGINS:
            raise ValueError(f"Origine inconnue : {self.origin!r}. Attendu l'une de {ORIGINS}.")
        if self.step < 0:
            raise ValueError("L'échéance ne peut pas être négative.")


def _safe_target(root: Path, name: str) -> Path:
    """Compose un chemin de destination et refuse toute sortie de la racine.

    Le nom est construit à partir de la requête, jamais repris d'une réponse
    distante ; la vérification reste nécessaire, une valeur de requête étant
    une entrée comme une autre.
    """
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise EcmwfIfsError(f"Chemin de destination hors de la racine prévue : {name!r}")
    return candidate


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
        client_factory: Callable[..., OpenDataClient] | None = None,
    ) -> None:
        super().__init__(SOURCE_NAME)
        self.destination = destination
        self.request = request or EcmwfIfsRequest()
        self.max_bytes = max_bytes
        self.max_retries = max_retries
        self.retry_after = retry_after
        self._client_factory = client_factory

    def _client(self) -> OpenDataClient:
        if self._client_factory is not None:
            return self._client_factory(
                source=self.request.origin,
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
            source=self.request.origin,
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

    def fetch(self) -> ConnectorResult:
        root = self.destination.resolve()
        root.mkdir(parents=True, exist_ok=True)
        client = self._client()

        artefacts: list[Path] = []
        downloaded = 0
        for parameter in self.request.parameters:
            target = _safe_target(root, f"{parameter}-{self.request.step}h.grib2")
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

        provenance = Provenance(
            source_name=SOURCE_NAME,
            source_url=SOURCE_URL,
            retrieval_time=datetime.now(UTC),
            license=SOURCE_LICENSE,
        )
        return ConnectorResult(
            source=SOURCE_NAME,
            status="ok",
            message=(
                f"{len(artefacts)} message(s) GRIB2 récupéré(s) depuis l'origine "
                f"{self.request.origin!r}, {downloaded} octets."
            ),
            provenance=provenance,
            artefacts=tuple(artefacts),
        )


__all__ = [
    "DEFAULT_MAX_BYTES",
    "DEFAULT_PARAMETERS",
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
