"""Ce que le client lit de son environnement, et rien d'autre.

**Dataclass et non modèle Pydantic**, par la règle du dépôt : le critère est
le franchissement de frontière, pas le rôle de l'objet. Ces réglages ne
quittent jamais le processus. Le compte rendu, lui, en sort — il est donc un
modèle Pydantic, voir `report`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class MissingConfiguration(RuntimeError):
    """Un réglage obligatoire n'est pas dans l'environnement."""


#: Sous-dossier où s'accumulent les comptes rendus, sous la destination.
#: Un point en tête : ce n'est pas de la donnée, et cela ne doit pas se
#: confondre avec ce que l'utilisateur est venu chercher.
DEFAULT_STATE_DIR = ".x10"


@dataclass(frozen=True)
class Settings:
    """Les réglages d'une session, résolus une fois pour toutes.

    Rien n'est codé en dur, et rien n'est deviné : un réglage absent dont
    l'absence empêche de travailler **lève**, au lieu de retenir un défaut
    qui enverrait des fichiers quelque part d'inattendu.
    """

    #: Où déposer les artefacts acquis et les sorties écrites.
    destination: Path

    #: Où accumuler les comptes rendus, pour en déduire la disponibilité.
    state: Path

    #: Plafond de volume par acquisition. `None` laisse celui du connecteur,
    #: qui en a un : ne pas en imposer un ici évite d'en avoir deux.
    max_bytes: int | None = None

    @classmethod
    def from_env(cls, environment: dict[str, str] | None = None) -> Settings:
        """Résout les réglages depuis l'environnement.

        `environnement` sert aux tests ; en usage normal on lit `os.environ`.
        """
        env = os.environ if environment is None else environment

        raw = env.get("X10_DESTINATION", "").strip()
        if not raw:
            raise MissingConfiguration(
                "X10_DESTINATION is not set. The client does not choose where to "
                "write on your behalf."
            )
        destination = Path(raw).expanduser().resolve()

        raw_state = env.get("X10_STATE", "").strip()
        state = (
            Path(raw_state).expanduser().resolve() if raw_state else destination / DEFAULT_STATE_DIR
        )

        ceiling = env.get("X10_MAX_BYTES", "").strip()
        max_bytes = int(ceiling) if ceiling else None
        if max_bytes is not None and max_bytes <= 0:
            raise MissingConfiguration(
                f"X10_MAX_BYTES is {max_bytes}, which would allow no download at "
                "all. Remove the variable to keep the connector's own "
                "ceiling."
            )

        return cls(destination=destination, state=state, max_bytes=max_bytes)


__all__ = ["DEFAULT_STATE_DIR", "MissingConfiguration", "Settings"]
