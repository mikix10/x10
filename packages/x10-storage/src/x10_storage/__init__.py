from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StorageRecord:
    """Enregistrement générique confié à un backend de persistance."""

    key: str
    payload: dict[str, Any] = field(default_factory=dict)


class StorageAdapter:
    """Interface de persistance, indépendante du backend concret."""

    def save(self, record: StorageRecord) -> None:
        raise NotImplementedError("Subclasses must implement save().")

    def load(self, key: str) -> StorageRecord | None:
        raise NotImplementedError("Subclasses must implement load().")


__all__ = ["StorageAdapter", "StorageRecord"]
