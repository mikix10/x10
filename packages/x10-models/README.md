# x10-models

Package centralisant les modèles de données partagés pour X10.

## Objectif

Définir des structures de données cohérentes pour les observations géo-hydro-océano-météo, avec :
- localisation géographique,
- provenance,
- horodatage,
- représentation unifiée des valeurs.

## Exemple

Les modèles sont des `pydantic.BaseModel` immuables (`frozen=True`) : les valeurs sont validées à la construction (bornes géographiques, champs non vides) et sérialisables en JSON.

## Exemple

```python
from datetime import UTC, datetime
from decimal import Decimal

from x10_models import GeoPoint, Observation, Provenance

obs = Observation(
    variable="air_temperature",
    value=Decimal("18.4"),
    unit="degC",
    timestamp=datetime.now(UTC),
    location=GeoPoint(latitude=48.8566, longitude=2.3522),
    provenance=Provenance(source_name="Open-Meteo", source_url="https://open-meteo.com"),
)

obs.model_dump_json()
```

## Portée

`Observation` vaut pour les séries ponctuelles (stations, bouées). Les champs maillés
(GRIB/NetCDF) restent dans des tableaux `xarray`/`numpy` : on n'instancie jamais un modèle
par point de grille.
