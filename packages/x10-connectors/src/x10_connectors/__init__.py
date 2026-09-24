from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConnectorResult:
    """Compte rendu d'une opération de connecteur."""

    source: str
    status: str
    message: str = ""


class BaseConnector:
    """Base commune aux connecteurs de sources externes."""

    def __init__(self, source_name: str) -> None:
        self.source_name = source_name

    def fetch(self) -> ConnectorResult:
        raise NotImplementedError("Subclasses must implement fetch().")


__all__ = ["BaseConnector", "ConnectorResult"]
