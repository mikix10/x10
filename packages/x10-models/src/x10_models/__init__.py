from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class GeoPoint(BaseModel):
    """Position géographique en WGS84."""

    model_config = ConfigDict(frozen=True)

    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    elevation_m: float | None = None


class Provenance(BaseModel):
    """Origine d'une donnée : qui la produit, sous quelle licence, quand elle a été récupérée."""

    model_config = ConfigDict(frozen=True)

    source_name: str = Field(min_length=1)
    source_url: str | None = None
    retrieval_time: datetime | None = None
    license: str | None = None


class Observation(BaseModel):
    """Mesure ponctuelle d'une variable, horodatée et localisée.

    Réservé aux séries ponctuelles (stations, bouées). Les champs maillés
    (GRIB/NetCDF) restent dans des tableaux ; voir CLAUDE.md.
    """

    model_config = ConfigDict(frozen=True)

    variable: str = Field(min_length=1)
    value: Decimal
    unit: str = Field(min_length=1)
    timestamp: datetime
    location: GeoPoint
    provenance: Provenance | None = None


__all__ = ["GeoPoint", "Observation", "Provenance"]
