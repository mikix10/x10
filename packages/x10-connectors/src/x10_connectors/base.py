from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from x10_models import Retrieval

#: Vocabulaire fermé d'`event.outcome` dans Elastic Common Schema. Le statut
#: adopte ces valeurs plutôt que les siennes : une correspondance de moins à
#: tenir entre le résultat et le journal.
Outcome = Literal["success", "failure", "unknown"]


class ConnectorResult(BaseModel):
    """Compte rendu d'une opération de connecteur.

    Modèle Pydantic et non dataclass : cet objet **franchit des frontières de
    processus** — journaux structurés, XCom d'un ordonnanceur, réponse d'API —
    et doit donc se sérialiser en JSON sans code de conversion. Les chemins et
    les horodatages sont pris en charge nativement.

    Il porte la provenance et la licence : une donnée sans son origine n'est
    pas exploitable, c'est une exigence produit.
    """

    source: str
    outcome: Outcome
    message: str = ""

    #: Identifiant corrélant les événements d'une même exécution. Fourni par
    #: l'appelant quand il en a un — l'identifiant d'exécution d'un
    #: ordonnanceur, par exemple —, engendré sinon.
    run_id: str

    #: Origine effectivement retenue, lorsque la source en expose plusieurs.
    origin: str | None = None

    started_at: datetime
    #: Durée en **nanosecondes**, unité attendue par `event.duration` d'ECS.
    duration_ns: int = Field(ge=0)
    bytes_downloaded: int = Field(default=0, ge=0)

    #: Lignage de ce qui a été acquis : artefacts, origine effectivement
    #: retenue, licence. Le compte rendu dit **comment l'appel s'est passé**,
    #: le lignage dit **d'où vient la donnée** — deux questions distinctes.
    retrieval: Retrieval | None = None


#: Agent responsable, pour le lignage et la trace `history` des sorties.
#: Defini ici plutot que dans chaque connecteur : trois copies de la meme
#: version divergent au premier oubli.
AGENT = "x10-connectors 0.1.0"


class UnsafeDestinationError(ValueError):
    """Un nom de fichier conduirait hors de la racine de destination."""


def safe_target(root: Path, name: str) -> Path:
    """Compose un chemin de destination et refuse toute sortie de la racine.

    Le nom vient de la requête ou d'un inventaire distant ; dans les deux cas
    c'est une entrée comme une autre, et une traversée de chemin y est
    possible. La vérification porte sur le chemin **résolu**, seul moyen de
    neutraliser aussi bien `..` qu'un lien symbolique.
    """
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise UnsafeDestinationError(f"Chemin de destination hors de la racine prévue : {name!r}")
    return candidate


#: Suffixe des fichiers en cours d'ecriture. Le point initial les masque sur
#: les systemes POSIX, et le suffixe les designe comme des dechets quand un
#: processus a ete tue sans pouvoir faire son menage.
SUFFIXE_PARTIEL = ".partiel"


class AucunFichierProduit(OSError):
    """Le bloc d'écriture s'est achevé sans produire de fichier."""


@contextmanager
def ecriture_atomique(cible: Path) -> Iterator[Path]:
    """Écrit sous un nom provisoire, et ne publie qu'une fois l'écriture finie.

    **Rien n'apparaît sous son nom définitif avant d'être complet.** Sans cela,
    un processus interrompu en cours de transfert — dépassement de délai d'un
    ordonnanceur, conteneur évincé — laisse un fichier partiel que *rien ne
    distingue d'un fichier entier*. La reprise le trouve, le croit bon, et
    l'erreur ressort trois étapes plus loin, voire jamais : sur une donnée
    tronquée qui se décode.

    C'est le défaut le plus grave que la projection des contrats ait relevé,
    précisément parce qu'il se produit sous le régime pour lequel X10 est
    conçu — la reprise par un ordonnanceur — et qu'il ne se signale pas.

    Trois propriétés, chacune nécessaire :

    **Le renommage est atomique.** `os.replace` l'est sur les systèmes POSIX
    comme sous Windows. Un lecteur concurrent voit l'ancien fichier ou le
    nouveau, jamais un état intermédiaire.

    **Le provisoire est un voisin de la cible**, donc sur le même système de
    fichiers. Un renommage entre systèmes de fichiers n'est pas atomique — il
    copie puis supprime —, et `os.replace` échouerait de toute façon.

    **Le nom provisoire est unique par processus.** Deux instances écrivant la
    même cible ne se marchent pas dessus, ce qui conditionne l'exécution en
    plusieurs exemplaires.

    En cas d'échec, le provisoire est retiré et **la cible précédente reste
    intacte** : une acquisition ratée ne détruit pas la précédente.

    Limite assumée : un processus tué sans remontée d'exception laisse le
    provisoire en place. C'est un déchet, non un faux fichier complet, et son
    nom le désigne comme tel.
    """
    cible.parent.mkdir(parents=True, exist_ok=True)
    marque = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
    provisoire = cible.with_name(f".{cible.name}.{marque}{SUFFIXE_PARTIEL}")
    try:
        yield provisoire
    except BaseException:
        provisoire.unlink(missing_ok=True)
        raise
    if not provisoire.exists():
        raise AucunFichierProduit(f"Aucun fichier produit pour {cible.name!r}.")
    os.replace(provisoire, cible)


class BaseConnector:
    """Base commune aux connecteurs de sources externes."""

    def __init__(self, source_name: str) -> None:
        self.source_name = source_name

    def fetch(self) -> ConnectorResult:
        raise NotImplementedError("Subclasses must implement fetch().")


__all__ = [
    "AGENT",
    "SUFFIXE_PARTIEL",
    "AucunFichierProduit",
    "BaseConnector",
    "ConnectorResult",
    "Outcome",
    "UnsafeDestinationError",
    "ecriture_atomique",
    "safe_target",
]
