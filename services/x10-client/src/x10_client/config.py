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


class ConfigurationManquante(RuntimeError):
    """Un réglage obligatoire n'est pas dans l'environnement."""


#: Sous-dossier où s'accumulent les comptes rendus, sous la destination.
#: Un point en tête : ce n'est pas de la donnée, et cela ne doit pas se
#: confondre avec ce que l'utilisateur est venu chercher.
ETAT_PAR_DEFAUT = ".x10"


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
    etat: Path

    #: Plafond de volume par acquisition. `None` laisse celui du connecteur,
    #: qui en a un : ne pas en imposer un ici évite d'en avoir deux.
    max_bytes: int | None = None

    @classmethod
    def from_env(cls, environnement: dict[str, str] | None = None) -> Settings:
        """Résout les réglages depuis l'environnement.

        `environnement` sert aux tests ; en usage normal on lit `os.environ`.
        """
        env = os.environ if environnement is None else environnement

        brut = env.get("X10_DESTINATION", "").strip()
        if not brut:
            raise ConfigurationManquante(
                "X10_DESTINATION n'est pas définie. Le client ne choisit pas "
                "où écrire à votre place."
            )
        destination = Path(brut).expanduser().resolve()

        etat_brut = env.get("X10_ETAT", "").strip()
        etat = (
            Path(etat_brut).expanduser().resolve() if etat_brut else destination / ETAT_PAR_DEFAUT
        )

        plafond = env.get("X10_MAX_BYTES", "").strip()
        max_bytes = int(plafond) if plafond else None
        if max_bytes is not None and max_bytes <= 0:
            raise ConfigurationManquante(
                f"X10_MAX_BYTES vaut {max_bytes}, ce qui n'autoriserait aucun "
                "téléchargement. Retirer la variable pour laisser le plafond "
                "du connecteur."
            )

        return cls(destination=destination, etat=etat, max_bytes=max_bytes)


__all__ = ["ETAT_PAR_DEFAUT", "ConfigurationManquante", "Settings"]
