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

from . import contract, decoding, ecmwf_ifs, meteofrance_pnt, output
from .base import (
    AucunFichierProduit,
    BaseConnector,
    ConnectorResult,
    Outcome,
    UnsafeDestinationError,
    ecriture_atomique,
    safe_target,
)
from .contract import Contract, Divergences, compare_contracts, output_contract
from .decoding import GribIndisponible
from .ecmwf_ifs import (
    EcmwfIfsError,
    EcmwfIfsOpenDataConnector,
    EcmwfIfsRequest,
    OpenDataClient,
)
from .meteofrance_pnt import (
    MeteoFrancePntConnector,
    MeteoFrancePntError,
    MeteoFrancePntRequest,
    Transport,
)
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
from .output import UniteNonConvertible, write_netcdf

__all__ = [
    "EVENT_CATEGORY",
    "EVENT_DATASET",
    "RESERVED_RECORD_ATTRIBUTES",
    "AucunFichierProduit",
    "BaseConnector",
    "ConnectorResult",
    "Contract",
    "Divergences",
    "EcmwfIfsError",
    "EcmwfIfsOpenDataConnector",
    "EcmwfIfsRequest",
    "EcsJsonFormatter",
    "GribIndisponible",
    "MeteoFrancePntConnector",
    "MeteoFrancePntError",
    "MeteoFrancePntRequest",
    "OpenDataClient",
    "Outcome",
    "Transport",
    "UniteNonConvertible",
    "UnsafeDestinationError",
    "compare_contracts",
    "connector_logger",
    "contract",
    "decoding",
    "ecmwf_ifs",
    "ecriture_atomique",
    "failure_fields",
    "fetch_finished_fields",
    "fetch_started_fields",
    "meteofrance_pnt",
    "output",
    "output_contract",
    "safe_target",
    "write_netcdf",
]
