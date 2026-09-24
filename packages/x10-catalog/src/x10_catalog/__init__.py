from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DataSource(BaseModel):
    """Source open data référencée par le catalogue."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    url: str | None = None
    format: str | None = None
    license: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class CatalogEntry(BaseModel):
    """Association d'une variable et d'un domaine physique à une source."""

    model_config = ConfigDict(frozen=True)

    source: DataSource
    variable: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    tags: tuple[str, ...] = ()


__all__ = ["CatalogEntry", "DataSource"]
