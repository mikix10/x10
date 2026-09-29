from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from x10_models import Provenance


@dataclass
class ConnectorResult:
    """Compte rendu d'une opération de connecteur.

    Porte les artefacts produits et leur provenance : une donnée sans son
    origine ni sa licence n'est pas exploitable, c'est une exigence produit.
    """

    source: str
    status: str
    message: str = ""
    provenance: Provenance | None = None
    artefacts: tuple[Path, ...] = field(default_factory=tuple)


class BaseConnector:
    """Base commune aux connecteurs de sources externes."""

    def __init__(self, source_name: str) -> None:
        self.source_name = source_name

    def fetch(self) -> ConnectorResult:
        raise NotImplementedError("Subclasses must implement fetch().")


__all__ = ["BaseConnector", "ConnectorResult"]
