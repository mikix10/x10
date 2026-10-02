"""Vocabulaire de domaine partagé par les composants X10.

Les noms suivent **DCAT** et **PROV-O** plutôt qu'une invention maison. Ces
standards distinguent depuis longtemps ce que notre premier modèle confondait :
qui produit une information, qui la diffuse, qui la ré-expose, et d'où vient ce
qu'on a effectivement récupéré.

| Notion | Terme normalisé repris ici |
|---|---|
| producteur | `dcterms:creator` — `Dataset.producer` |
| diffuseur | `dcterms:publisher` — `Distribution.publisher` |
| accès concret, un par diffuseur | `dcat:Distribution` |
| lignage d'acquisition | `prov:Entity` / `Activity` / `Agent` — `Retrieval` |

Aucune sérialisation RDF n'est imposée : un export DCAT ou STAC reste possible
sans rien reprendre du modèle.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

#: Rôles d'un acteur, vocabulaire fermé repris de STAC. Fermé délibérément :
#: un champ libre se dégrade en texte que personne ne peut plus agréger.
AgentRole = Literal["producer", "publisher", "processor", "licensor", "harvester"]

#: Les quatre domaines physiques du périmètre.
PhysicalDomain = Literal["geo", "hydro", "oceano", "meteo"]


class Agent(BaseModel):
    """Acteur intervenant sur une donnée, et ce qu'il y fait.

    Un même organisme peut cumuler des rôles : ECMWF produit les sorties IFS
    *et* les diffuse, tout en en étant le concédant de licence.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    roles: tuple[AgentRole, ...] = Field(min_length=1)
    url: str | None = None


class Dataset(BaseModel):
    """Information logique, indépendante de tout moyen d'accès.

    « Température à 2 m, IFS 0.25° » existe qu'on la télécharge ou non. Les
    moyens de l'obtenir sont des `Distribution`.
    """

    model_config = ConfigDict(frozen=True)

    identifier: str = Field(min_length=1)
    title: str = Field(min_length=1)
    producer: Agent
    domain: PhysicalDomain
    variables: tuple[str, ...] = ()


class Distribution(BaseModel):
    """Accès concret à un `Dataset`, chez un diffuseur donné.

    **Une distribution par origine**, et non une distribution à plusieurs URL :
    chacune porte sa priorité et sa licence, ce sur quoi s'appuie la politique
    de résolution. Des miroirs du même fichier restent des distributions
    distinctes.

    La licence figure ici et pas seulement sur le `Dataset` : un ré-exposant
    peut ajouter ses propres conditions à celles du producteur.
    """

    model_config = ConfigDict(frozen=True)

    dataset: str = Field(min_length=1)
    origin: str = Field(min_length=1)
    publisher: Agent
    access_url: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    license: str = Field(min_length=1)
    #: Plus la valeur est basse, plus l'origine est préférée.
    priority: int = Field(default=100, ge=0)


class Retrieval(BaseModel):
    """Lignage d'une acquisition, structuré comme PROV-O.

    Répond à « d'où vient ce fichier » : les artefacts produits (`prov:Entity`),
    quand (`prov:Activity`), depuis quelle distribution (`prov:used`), et par
    quel agent (`prov:wasAssociatedWith`).

    `origin` porte l'origine **effectivement retenue**, qui peut différer de
    celle demandée si une bascule a eu lieu.

    Le lignage de transformation — `prov:wasDerivedFrom` — n'est pas modélisé :
    rien n'est encore transformé, et le concevoir sans dérivation à décrire
    serait spéculatif.
    """

    model_config = ConfigDict(frozen=True)

    artefacts: tuple[Path, ...] = ()
    retrieved_at: datetime
    dataset: str = Field(min_length=1)
    origin: str = Field(min_length=1)
    selection: dict[str, Any] = Field(default_factory=dict)
    #: Agent responsable, avec sa version : `x10-connectors 0.1.0`.
    agent: str = Field(min_length=1)
    license: str | None = None


class GeoPoint(BaseModel):
    """Position géographique en WGS84."""

    model_config = ConfigDict(frozen=True)

    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    elevation_m: float | None = None


class Provenance(BaseModel):
    """Attribution légère portée par une **valeur** de donnée.

    À ne pas confondre avec `Retrieval`, qui décrit l'acquisition d'un
    **artefact**. Les deux répondent à des questions différentes : « à qui cette
    valeur est-elle attribuée » et « comment ce fichier est-il arrivé ». Un
    `Retrieval` peut produire la `Provenance` des valeurs qui en dérivent.
    """

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


__all__ = [
    "Agent",
    "AgentRole",
    "Dataset",
    "Distribution",
    "GeoPoint",
    "Observation",
    "PhysicalDomain",
    "Provenance",
    "Retrieval",
]
