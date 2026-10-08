from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from x10_models import Retrieval

#: Vocabulaire fermé d'`event.outcome` dans Elastic Common Schema. Le statut
#: adopte ces valeurs plutôt que les siennes : une correspondance de moins à
#: tenir entre le résultat et le journal.
Outcome = Literal["success", "failure", "unknown"]


class ConnectorResult(BaseModel):
    """Compte rendu d'une opération de connecteur.

    Modèle Pydantic et non dataclass : cet objet **franchit des frontières de
    processus** — journaux structurés, XCom d'un ordonnanceur, réponse d'API —
    et doit donc se sérialiser en JSON sans code de conversion. Les chemins et
    les horodatages sont pris en charge nativement.

    Il porte la provenance et la licence : une donnée sans son origine n'est
    pas exploitable, c'est une exigence produit.
    """

    source: str
    outcome: Outcome
    message: str = ""

    #: Identifiant corrélant les événements d'une même exécution. Fourni par
    #: l'appelant quand il en a un — l'identifiant d'exécution d'un
    #: ordonnanceur, par exemple —, engendré sinon.
    run_id: str

    #: Origine effectivement retenue, lorsque la source en expose plusieurs.
    origin: str | None = None

    started_at: datetime
    #: Durée en **nanosecondes**, unité attendue par `event.duration` d'ECS.
    duration_ns: int = Field(ge=0)
    bytes_downloaded: int = Field(default=0, ge=0)

    #: Lignage de ce qui a été acquis : artefacts, origine effectivement
    #: retenue, licence. Le compte rendu dit **comment l'appel s'est passé**,
    #: le lignage dit **d'où vient la donnée** — deux questions distinctes.
    retrieval: Retrieval | None = None


#: Agent responsable, pour le lignage et la trace `history` des sorties.
#: Defini ici plutot que dans chaque connecteur : trois copies de la meme
#: version divergent au premier oubli.
AGENT = "x10-connectors 0.1.0"


class UnsafeDestinationError(ValueError):
    """Un nom de fichier conduirait hors de la racine de destination."""


def safe_target(root: Path, name: str) -> Path:
    """Compose un chemin de destination et refuse toute sortie de la racine.

    Le nom vient de la requête ou d'un inventaire distant ; dans les deux cas
    c'est une entrée comme une autre, et une traversée de chemin y est
    possible. La vérification porte sur le chemin **résolu**, seul moyen de
    neutraliser aussi bien `..` qu'un lien symbolique.
    """
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise UnsafeDestinationError(f"Chemin de destination hors de la racine prévue : {name!r}")
    return candidate


class BaseConnector:
    """Base commune aux connecteurs de sources externes."""

    def __init__(self, source_name: str) -> None:
        self.source_name = source_name

    def fetch(self) -> ConnectorResult:
        raise NotImplementedError("Subclasses must implement fetch().")


__all__ = [
    "AGENT",
    "BaseConnector",
    "ConnectorResult",
    "Outcome",
    "UnsafeDestinationError",
    "safe_target",
]
