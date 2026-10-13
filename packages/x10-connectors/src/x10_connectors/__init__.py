"""Connecteurs de sources externes.

**Les constantes propres à une source ne sont pas réexportées ici.** Chaque
connecteur décrit la sienne — nom, licence, format, plafond de volume — et deux
sources ne peuvent pas se partager un même nom dans un espace plat. Elles se
prennent au module : `from x10_connectors.ecmwf_ifs import SOURCE_LICENSE`.

Ne sont réexportés que les éléments **communs** — base, compte rendu,
journalisation, garde-fou de chemin — et les points d'entrée de chaque
connecteur, dont les noms sont déjà qualifiés par leur source.
"""

from __future__ import annotations

from . import contract, ecmwf_ifs, grib2, meteofrance_pnt, netcdf_cf
from .base import (
    BaseConnector,
    ConnectorResult,
    NoOutputFileError,
    Outcome,
    UnsafeDestinationError,
    atomic_write,
    safe_target,
)
from .contract import Contract, Divergences, compare_contracts, output_contract
from .ecmwf_ifs import (
    EcmwfIfsError,
    EcmwfIfsOpenDataConnector,
    EcmwfIfsRequest,
    OpenDataClient,
)
from .grib2 import GribUnavailableError
from .meteofrance_pnt import (
    MeteoFrancePntConnector,
    MeteoFrancePntError,
    MeteoFrancePntRequest,
    Transport,
)
from .netcdf_cf import UnconvertibleUnitError, write_netcdf
from .observability import (
    EVENT_CATEGORY,
    EVENT_DATASET,
    RESERVED_RECORD_ATTRIBUTES,
    EcsJsonFormatter,
    connector_logger,
    failure_fields,
    fetch_finished_fields,
    fetch_started_fields,
)

__all__ = [
    "EVENT_CATEGORY",
    "EVENT_DATASET",
    "RESERVED_RECORD_ATTRIBUTES",
    "BaseConnector",
    "ConnectorResult",
    "Contract",
    "Divergences",
    "EcmwfIfsError",
    "EcmwfIfsOpenDataConnector",
    "EcmwfIfsRequest",
    "EcsJsonFormatter",
    "GribUnavailableError",
    "MeteoFrancePntConnector",
    "MeteoFrancePntError",
    "MeteoFrancePntRequest",
    "NoOutputFileError",
    "OpenDataClient",
    "Outcome",
    "Transport",
    "UnconvertibleUnitError",
    "UnsafeDestinationError",
    "atomic_write",
    "compare_contracts",
    "connector_logger",
    "contract",
    "ecmwf_ifs",
    "failure_fields",
    "fetch_finished_fields",
    "fetch_started_fields",
    "grib2",
    "meteofrance_pnt",
    "netcdf_cf",
    "output_contract",
    "safe_target",
    "write_netcdf",
]
