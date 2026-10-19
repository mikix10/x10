"""x10-client — assembler la chaîne X10, et rendre compte de ce qu'elle a fait.

**L'API sert, le client consomme.** Ce membre appelle le socle ; il n'en fait
pas partie, et rien ne doit en dépendre.

Il n'implémente aucune logique de domaine : il assemble une acquisition, un
décodage, une normalisation, une écriture et un contrat de sortie, puis rend
un compte rendu. Tout ce qui décode, convertit ou interprète appartient aux
paquets — un client qui s'en chargerait deviendrait un paquet fantôme, et le
socle se viderait sans que personne le décide.
"""

from __future__ import annotations

from .availability import Availability, observe
from .config import MissingConfiguration, Settings
from .options import DEFAULT_OPTIONS, NormaliseOptions
from .report import (
    ErrorType,
    GranuleReport,
    PipelineReport,
    Verdict,
    contract_fingerprint,
)
from .session import Session, UnknownRequest

__all__ = [
    "DEFAULT_OPTIONS",
    "Availability",
    "ErrorType",
    "GranuleReport",
    "MissingConfiguration",
    "NormaliseOptions",
    "PipelineReport",
    "Session",
    "Settings",
    "UnknownRequest",
    "Verdict",
    "contract_fingerprint",
    "observe",
]
