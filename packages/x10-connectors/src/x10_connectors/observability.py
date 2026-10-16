"""Journalisation structurée des connecteurs, alignée sur Elastic Common Schema.

**Cette bibliothèque émet, elle ne configure pas.** Aucun `basicConfig`, aucun
handler, aucun format imposé : seulement un `NullHandler` pour éviter le
message « no handler found ». C'est l'application qui choisit la destination
et le rendu — texte lisible en développement, JSON vers une chaîne ELK en
production. Imposer un format casserait toute application nous intégrant.

Les noms de champs suivent ECS plutôt qu'une invention maison, ce qui rend
les tableaux de bord Kibana exploitables sans travail préalable. Deux points
du schéma à respecter : `event.outcome` n'admet que `success`, `failure` ou
`unknown`, et `event.duration` se compte en **nanosecondes**.

**Piège de `logging`** : `extra=` refuse les noms d'attributs réservés de
`LogRecord` — `message`, `name`, `levelname`, `asctime`, `args` et quelques
autres lèvent une `KeyError`. Un champ ainsi nommé ferait échouer l'appel de
journalisation lui-même. `RESERVED_RECORD_ATTRIBUTES` les recense et un test
vérifie qu'aucun de nos champs n'y figure.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from .base import ConnectorResult

#: Attributs que `logging` refuse de voir écrasés par `extra=`.
RESERVED_RECORD_ATTRIBUTES = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)

#: Jeu de données ECS, pour distinguer nos événements des autres dans Kibana.
EVENT_DATASET = "x10.connector"

#: `event.category` a un vocabulaire fermé. Récupérer un fichier distant tient
#: du réseau et du fichier ; aucune valeur ne désigne l'acquisition de données.
EVENT_CATEGORY = ("network", "file")


def connector_logger(module_name: str) -> logging.Logger:
    """Journal d'un connecteur, muet tant que l'application n'a rien configuré."""
    logger = logging.getLogger(module_name)
    logger.addHandler(logging.NullHandler())
    return logger


def fetch_started_fields(
    *,
    source: str,
    run_id: str,
    origin: str | None,
    attempt: int | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Champs ECS du début d'une récupération.

    `attempt` numérote la tentative quand plusieurs origines sont essayées ;
    il passe par ici plutôt que d'être ajouté par l'appelant, afin que la
    surface journalisée reste entièrement couverte par ses tests.
    """
    fields: dict[str, Any] = {
        "event.kind": "event",
        "event.category": list(EVENT_CATEGORY),
        "event.dataset": EVENT_DATASET,
        "event.action": "fetch",
        "trace.id": run_id,
        "x10.source": source,
    }
    if origin is not None:
        fields["x10.origin"] = origin
    if attempt is not None:
        fields["x10.attempt"] = attempt
    if details:
        fields.update({f"x10.{key}": value for key, value in details.items()})
    return fields


def fetch_finished_fields(result: ConnectorResult) -> dict[str, Any]:
    """Champs ECS de la fin d'une récupération, dérivés du compte rendu."""
    fields: dict[str, Any] = {
        "event.kind": "event",
        "event.category": list(EVENT_CATEGORY),
        "event.dataset": EVENT_DATASET,
        "event.action": "fetch",
        "event.outcome": result.outcome,
        "event.duration": result.duration_ns,
        "event.start": result.started_at.isoformat(),
        "trace.id": result.run_id,
        "x10.source": result.source,
        "x10.bytes": result.bytes_downloaded,
        "x10.artefacts": len(result.retrieval.artefacts) if result.retrieval else 0,
    }
    if result.origin is not None:
        fields["x10.origin"] = result.origin
    if result.retrieval is not None:
        fields["x10.dataset"] = result.retrieval.dataset
        if result.retrieval.license is not None:
            fields["x10.license"] = result.retrieval.license
    return fields


#: Motif d'une URL dans un texte libre, chaîne de requête comprise. Volontairement
#: large : il vaut mieux rédiger un peu trop que laisser passer un jeton.
_URL_AVEC_REQUETE = re.compile(r"(https?://[^\s'\"<>]*?)\?[^\s'\"<>]*")


def redact(message: str) -> str:
    """Retire la chaîne de requête des URL d'un message.

    **Le seul chemin par lequel un secret pouvait atteindre le journal.** Une
    bibliothèque HTTP met volontiers l'adresse complète dans son message
    d'exception, et `failure_fields` la recopiait telle quelle dans
    `error.message` ; un jeton passé en paramètre d'URL s'y retrouvait.

    Le **chemin** suffit au diagnostic — il dit quel objet était demandé. La
    chaîne de requête, elle, ne sert qu'à fuir. Elle est donc remplacée par
    un marqueur plutôt que supprimée, pour que la relecture sache qu'il y
    avait quelque chose là.

    Cela ne dispense pas de la règle de fond : **un secret ne voyage jamais
    en paramètre d'URL quand un en-tête existe.** Cette fonction est le
    filet, pas la méthode.
    """
    return _URL_AVEC_REQUETE.sub(r"\1?<redacted>", message)


def failure_fields(error: BaseException) -> dict[str, Any]:
    """Champs ECS d'un échec, pour distinguer une source indisponible d'un défaut interne."""
    return {
        "event.outcome": "failure",
        "error.type": type(error).__name__,
        "error.message": redact(str(error)),
    }


class EcsJsonFormatter(logging.Formatter):
    """Rendu JSON une ligne, utilisable tel quel par une chaîne ELK.

    **Destiné aux applications**, pas à la bibliothèque : rien ici ne l'installe.
    Une application qui préfère `structlog` ou son propre format l'ignore.
    """

    def format(self, record: logging.LogRecord) -> str:
        charge: dict[str, Any] = {
            "@timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "log.level": record.levelname.lower(),
            "log.logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key.startswith(("event.", "error.", "trace.", "x10.", "service.")):
                charge[key] = value
        if record.exc_info:
            charge["error.stack_trace"] = self.formatException(record.exc_info)
        # Sortie purement ASCII, donc insensible à l'encodage du flux de
        # destination : une console Windows en cp1252 corromprait sinon les
        # accents des messages. Tout consommateur JSON décode les séquences
        # d'échappement de manière transparente.
        return json.dumps(charge, ensure_ascii=True, default=str)


__all__ = [
    "EVENT_CATEGORY",
    "EVENT_DATASET",
    "RESERVED_RECORD_ATTRIBUTES",
    "EcsJsonFormatter",
    "connector_logger",
    "failure_fields",
    "fetch_finished_fields",
    "fetch_started_fields",
    "redact",
]
