from __future__ import annotations

import ast
import hashlib
import inspect
import os
import pathlib
import re
import uuid
from collections.abc import Collection, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import ModuleType
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


def _package_version() -> str:
    """La version installée du paquet, ou `unknown` hors installation."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("x10-connectors")
    except PackageNotFoundError:  # pragma: no cover - paquet non installé
        return "unknown"


#: Agent responsable, pour le lignage et la trace `history` des sorties.
#: Defini ici plutot que dans chaque connecteur : trois copies de la meme
#: version divergent au premier oubli.
#:
#: **Dérivé des métadonnées du paquet depuis le 22/10/2026**, et non plus
#: écrit en dur : une version figée à la main est fausse dès la publication
#: suivante, et c'est précisément la trace qui doit permettre d'attribuer une
#: divergence à notre outillage plutôt qu'au producteur.
AGENT = f"x10-connectors {_package_version()}"


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
        raise UnsafeDestinationError(f"Destination path outside the intended root: {name!r}")
    return candidate


#: Suffixe des fichiers en cours d'ecriture. Le point initial les masque sur
#: les systemes POSIX, et le suffixe les designe comme des dechets quand un
#: processus a ete tue sans pouvoir faire son menage.
PARTIAL_SUFFIX = ".partiel"


class NoOutputFileError(OSError):
    """Le bloc d'écriture s'est achevé sans produire de fichier."""


@contextmanager
def atomic_write(target: Path) -> Iterator[Path]:
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
    target.parent.mkdir(parents=True, exist_ok=True)
    marque = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
    provisoire = target.with_name(f".{target.name}.{marque}{PARTIAL_SUFFIX}")
    try:
        yield provisoire
    except BaseException:
        provisoire.unlink(missing_ok=True)
        raise
    if not provisoire.exists():
        raise NoOutputFileError(f"No file produced for {target.name!r}.")
    os.replace(provisoire, target)


class BaseConnector:
    """Base commune aux connecteurs de sources externes."""

    def __init__(self, source_name: str) -> None:
        self.source_name = source_name

    def fetch(self) -> ConnectorResult:
        raise NotImplementedError("Subclasses must implement fetch().")


class FingerprintUnavailableError(RuntimeError):
    """Le source d'un module n'est pas lisible, donc son empreinte est refusée."""


def _canonical(value: object) -> object:
    """Rend une valeur sous une forme dont le `repr` est stable d'une exécution
    à l'autre.

    Un `set` n'a pas d'ordre d'itération garanti et une expression régulière
    compilée porte son adresse mémoire : sans canonicalisation, l'empreinte
    changerait sans que rien n'ait changé, ce qui la rendrait inutile au
    premier diagnostic.
    """
    if isinstance(value, re.Pattern):
        return ("re", value.pattern, value.flags)
    if isinstance(value, Mapping):
        return sorted((repr(k), _canonical(v)) for k, v in value.items())
    if isinstance(value, (set, frozenset)):
        return sorted(repr(_canonical(v)) for v in value)
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return value


def module_constants(module: ModuleType) -> dict[str, object]:
    """Les constantes publiques **affectées dans** ce module, et leurs valeurs.

    **L'affectation, pas l'espace de noms, et la nuance est le défaut qu'elle
    corrige.** Filtrer `vars(module)` sur les noms en capitales y fait entrer
    tout ce que le module a *importé* sous un tel nom. Mesuré le 23/10/2026 :
    `UTC`, `TYPE_CHECKING` et surtout `AGENT` entraient dans l'empreinte de
    `netcdf_cf`. Or `AGENT` porte la version du paquet — **une simple montée
    de version déplaçait donc l'empreinte sans qu'aucune table ait changé**,
    soit le faux témoignage inverse de celui qu'on cherchait à empêcher.

    La liste est donc dressée par analyse syntaxique du source : affectations
    de niveau module dont la cible est un nom en capitales, sans souligné
    initial. Un import, une fonction, une classe n'en est pas une.

    Lève si le source est introuvable, plutôt que de retomber sur
    `vars(module)` : un repli silencieux rendrait une empreinte différente
    sans le dire, ce qui est exactement le défaut que tout ceci corrige.
    """
    source = inspect.getsourcefile(module)
    if source is None:  # pragma: no cover - module sans source sur disque
        raise FingerprintUnavailableError(
            f"Cannot read the source of {module.__name__!r} to list its constants. "
            "The fingerprint would silently differ, so it is refused."
        )
    arbre = ast.parse(pathlib.Path(source).read_text(encoding="utf-8"), filename=source)
    noms: list[str] = []
    for noeud in arbre.body:
        cibles: list[ast.expr] = []
        if isinstance(noeud, ast.Assign):
            cibles = list(noeud.targets)
        elif isinstance(noeud, ast.AnnAssign):
            cibles = [noeud.target]
        noms += [
            c.id for c in cibles if isinstance(c, ast.Name) and c.id.isupper() and c.id[0] != "_"
        ]
    valeurs = vars(module)
    return {nom: valeurs[nom] for nom in sorted(set(noms)) if nom in valeurs}


def table_fingerprint(module: ModuleType, *, exempt: Collection[str]) -> str:
    """Empreinte des tables d'un module, **dérivée de ses affectations**.

    **Pourquoi dériver plutôt qu'énumérer.** Une empreinte bâtie sur une liste
    écrite à la main ne couvre que ce qu'on a pensé à y mettre, et le prochain
    oubli sera une table nouvelle. Mesuré le 23/10/2026 : l'empreinte des noms
    CF en couvrait sept, et trois constantes décidant pourtant du nom émis —
    `RATE_TOKENS`, `INTEGRAL_PREFIX`, `ACCUMULATED_STEP_TYPES` — lui
    échappaient. Ramener `RATE_TOKENS` à une seule entrée aurait changé le
    `standard_name` de tout champ cumulé **sans déplacer l'empreinte**, qui
    aurait alors rendu le faux témoignage qu'elle existe pour empêcher.

    Dérivée, une table nouvelle y entre d'elle-même. Ce qui reste à décider
    n'est plus *quoi couvrir* mais *quoi exclure*, et `exempt` rend chaque
    exclusion visible en une ligne de `git diff`.

    Le périmètre exact est celui de `module_constants`, dont la docstring
    explique pourquoi l'espace de noms ne convenait pas.
    """
    materiau = sorted(
        (nom, _canonical(valeur))
        for nom, valeur in module_constants(module).items()
        if nom not in exempt
    )
    return hashlib.sha256(repr(materiau).encode("utf-8")).hexdigest()[:12]


__all__ = [
    "AGENT",
    "PARTIAL_SUFFIX",
    "BaseConnector",
    "ConnectorResult",
    "FingerprintUnavailableError",
    "NoOutputFileError",
    "Outcome",
    "UnsafeDestinationError",
    "atomic_write",
    "module_constants",
    "safe_target",
    "table_fingerprint",
]
