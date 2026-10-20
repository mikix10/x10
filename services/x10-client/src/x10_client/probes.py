"""Le mécanisme des sondes — le catalogue des écarts vit ailleurs.

**Le paquet fournit le mécanisme, l'application fournit les valeurs.** C'est
le partage que le dépôt pratique déjà pour `SecretRedactor`, et il décide de
ce fichier : ici le type, le chargeur, l'exécuteur et le rendu ; dans
`probes/`, à la racine du dépôt, un module par écart observé.

**Pourquoi cette séparation plutôt qu'un seul endroit.** Une sonde suit un
producteur par définition : elle change quand il change. La ranger dans la
surface publique que nous nous engageons à tenir contredirait la distinction
que le dépôt trace entre la vue **normalisée**, dont nous répondons, et la
vue **source**, qui ne promet rien. Le mécanisme, lui, est stable et
générique — un intégrateur peut écrire ses propres sondes avec.

**Une sonde n'est pas un test `pytest`**, et le mot est choisi pour éviter la
confusion. Un test dit si *notre* code est juste ; une sonde dit si un
constat daté sur un **tiers** tient toujours. Elle atteint un service réel,
exige des identifiants, et son résultat n'a aucune raison d'être vert.

**Le vocabulaire des verdicts vient d'EARL**, comme le modèle de
`docs/standards-et-outillage.yaml` le prévoit. Attention au sens, qui est
contre-intuitif : le sujet de l'assertion est **le producteur**, et le
critère est la clause. Un écart toujours présent donne donc `failed`, et
`passed` est la bonne nouvelle — la source a été corrigée.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from types import ModuleType

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Préfixe des identifiants. **Monotone et jamais réutilisé** : une entrée
#: retirée garde son numéro et son motif, sans quoi un commit de l'an
#: prochain citerait un numéro qui désigne autre chose.
PREFIX = "X10-DIV-"

#: Un module dont le nom commence par ceci n'est pas une sonde mais un
#: utilitaire partagé du catalogue.
PRIVATE = "_"


class Nature(StrEnum):
    """Ce qu'est l'écart, et il ne faut pas confondre les trois.

    Les ranger dans le même casier abîmerait un signalement : on ne parle pas
    de la même façon à un producteur selon qu'il viole une clause écrite ou
    qu'il surprend sans rien enfreindre.
    """

    #: Une clause écrite est violée, et elle est citable. `clause` est alors
    #: **obligatoire** — sans référence opposable, ce n'est qu'une opinion.
    NON_CONFORMITY = "non_conformity"
    #: Surprenant, mais rien ne l'interdit. Le plus souvent un usage établi
    #: qui contredit l'esprit d'une norme sans en violer la lettre.
    DIVERGENCE = "divergence"
    #: Ni l'un ni l'autre : une faute de saisie, un doublon, une coquille.
    #: C'est le signalement le plus facile à faire accepter.
    DATA_QUALITY = "data_quality"


class Side(StrEnum):
    """De qui relève l'écart.

    La colonne existe pour qu'une liste transmise à un producteur puisse être
    filtrée : « X10 ne lit pas le GRIB1 » est un manque de notre fait, et
    l'envoyer serait du bruit.
    """

    SOURCE = "source"
    X10 = "x10"


class Handling(StrEnum):
    """Ce que X10 en a fait — et une date seule ne le dirait pas.

    Dans un an, « 20/10/2026 » ne dira pas si l'écart a été contourné,
    seulement documenté, ou subi faute de parade.
    """

    #: Du code le neutralise.
    WORKED_AROUND = "worked_around"
    #: Rien à changer, mais il fallait l'écrire quelque part.
    DOCUMENTED = "documented"
    #: Connu, sans parade possible à ce jour.
    ENDURED = "endured"
    #: L'écart ne nous atteint pas.
    NOT_APPLICABLE = "not_applicable"


class Status(StrEnum):
    """Ce que nous savons de l'écart — et nous pouvons nous tromper.

    La distinction n'est pas une précaution de rédaction : elle existe parce
    que le dépôt s'est trompé trois fois en une journée sur ce corpus — un
    `__new__` non vu dans `cdsapi`, une heuristique qui accusait la mauvaise
    couche, un `401` lu comme un succès. Un registre qui nomme des
    organismes doit pouvoir dire « nous l'avons vu une fois et nous ne
    l'avons pas reproduit ».

    Une entrée ne monte en grade que sur preuve, et jamais l'inverse sans
    motif écrit.
    """

    #: Observé, et rejoué au moins une fois depuis.
    CONFIRMED = "confirmed"
    #: Observé une fois, non reproduit ou cause non établie.
    UNDER_INVESTIGATION = "under_investigation"
    #: Nous nous étions trompés. L'identifiant reste, avec son motif.
    WITHDRAWN = "withdrawn"


class Replay(StrEnum):
    """Qui peut rejouer la sonde.

    Par défaut **libre** : les identifiants que nos sources demandent
    s'obtiennent en s'inscrivant, donc quiconque le fait peut vérifier nos
    dires. C'est ce qui rend le registre contradictoire plutôt que déclaratif.
    """

    OPEN = "open"
    RESTRICTED = "restricted"


class Mode(StrEnum):
    """Comment le constat est vérifié, au sens d'EARL.

    `UNTESTED` n'est pas un aveu gênant : un invariant qu'on sait non outillé
    vaut mieux qu'un invariant qu'on ignore.
    """

    AUTOMATIC = "automatic"
    MANUAL = "manual"
    UNTESTED = "untested"


class Outcome(StrEnum):
    """Le résultat d'un rejeu, dans le vocabulaire d'EARL.

    **Le sujet est le producteur, pas nous.** `FAILED` dit donc que l'écart
    est toujours là, et `PASSED` que la source a été corrigée.
    """

    #: L'écart est toujours présent.
    FAILED = "failed"
    #: L'écart a disparu — la source a bougé, et le registre doit suivre.
    PASSED = "passed"
    #: La sonde n'a pas pu conclure : service indisponible, identifiant
    #: absent, réponse inattendue. Ce n'est **pas** un succès.
    CANT_TELL = "cantTell"
    #: Aucune sonde n'existe pour cet écart.
    UNTESTED = "untested"


class Probe(BaseModel):
    """Un écart observé, daté, et la façon de le rejouer.

    Modèle **gelé** et sérialisable : il franchit la frontière, puisqu'il
    alimente le registre versionné et tout compte rendu d'exécution.
    """

    model_config = ConfigDict(frozen=True)

    #: `X10-DIV-0001`. Stable à jamais : les messages de commit le citent.
    identifier: str = Field(min_length=len(PREFIX) + 1)
    #: Une ligne, au présent, qui dit l'écart et non ses conséquences.
    title: str = Field(min_length=1)
    nature: Nature
    side: Side
    status: Status = Status.UNDER_INVESTIGATION
    #: Le jour où nous l'avons constaté, pas celui où le producteur a changé.
    observed_on: date
    #: Le motif, obligatoire quand l'entrée est retirée.
    status_note: str | None = None
    #: Le nom du producteur ou de l'outil. Les sources que nous exploitons
    #: se nomment explicitement : c'est une exigence produit.
    producer: str = Field(min_length=1)
    #: Ce sur quoi porte le constat : une API, un format, une table.
    artefact: str = Field(min_length=1)
    #: Standard, version et section. **Obligatoire** pour une non-conformité.
    clause: str | None = None
    #: Ce que X10 fait en attendant, et où le lire.
    workaround: str = Field(min_length=1)
    handling: Handling
    #: La version de X10 où la parade est entrée, quand il y en a une.
    handled_in: str | None = None
    mode: Mode
    replay: Replay = Replay.OPEN
    #: Le motif d'une restriction, ou la commande à rejouer à la main.
    replay_note: str | None = None
    #: Rempli quand la source a corrigé, et seulement sur un rejeu.
    fixed_on: date | None = None

    @model_validator(mode="after")
    def _une_non_conformite_cite_sa_clause(self) -> Probe:
        """La règle du point 4, tenue par construction plutôt que par discipline.

        Annoncer une non-conformité sans référence opposable est une opinion.
        Le modèle refuse donc de la porter.
        """
        if self.nature is Nature.NON_CONFORMITY and not self.clause:
            raise ValueError(
                f"{self.identifier}: a non-conformity must cite its clause "
                "(standard, version and section)."
            )
        if not self.identifier.startswith(PREFIX):
            raise ValueError(f"{self.identifier!r} must start with {PREFIX!r}.")
        if self.mode is Mode.MANUAL and not self.replay_note:
            raise ValueError(f"{self.identifier}: a manual probe must document how to replay it.")
        if self.replay is Replay.RESTRICTED and not self.replay_note:
            raise ValueError(f"{self.identifier}: a restricted replay must name its reason.")
        if self.status is Status.WITHDRAWN and not self.status_note:
            raise ValueError(f"{self.identifier}: a withdrawn entry must say why.")
        return self


class Assertion(BaseModel):
    """Le résultat d'un rejeu — sérialisé, donc un modèle.

    `duration_ns` est en **nanosecondes**, comme `event.duration` d'ECS : le
    dépôt a déjà tranché cette unité, autant ne pas en avoir deux.
    """

    model_config = ConfigDict(frozen=True)

    identifier: str
    outcome: Outcome
    #: Ce que la sonde a vu, en une phrase. Lu par un tiers, donc en anglais.
    detail: str = ""
    observed_at: datetime
    duration_ns: int = 0


class ProbeReport(BaseModel):
    """Le compte rendu d'une exécution, lisible et sérialisable."""

    model_config = ConfigDict(frozen=True)

    started_at: datetime
    assertions: tuple[Assertion, ...] = ()

    @property
    def still_failing(self) -> tuple[str, ...]:
        """Les écarts toujours présents — le cas nominal, hélas."""
        return tuple(c.identifier for c in self.assertions if c.outcome is Outcome.FAILED)

    @property
    def newly_fixed(self) -> tuple[str, ...]:
        """Ceux que la source a corrigés : le registre est à mettre à jour."""
        return tuple(c.identifier for c in self.assertions if c.outcome is Outcome.PASSED)


@dataclass(frozen=True)
class Registered:
    """Une sonde et, s'il y en a une, la fonction qui la rejoue.

    Dataclass et non modèle : purement interne au processus, et elle porte un
    appelable que personne n'a de raison de sérialiser.
    """

    probe: Probe
    check: Callable[[], Assertion] | None = None
    origine: Path | None = None


class InvalidCatalogue(RuntimeError):
    """Le catalogue se contredit — un identifiant en double, un mode sans sonde."""


def _load_module(path: Path) -> ModuleType:
    """Charge un module par son chemin, son dossier étant rendu importable.

    Le catalogue n'est pas un paquet installé et n'a pas vocation à le
    devenir ; ses modules partagent pourtant un utilitaire d'accès. Le
    dossier est donc ajouté à `sys.path` **le temps du chargement**, ce qui
    évite d'imposer une installation pour une poignée de fichiers.
    """
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise InvalidCatalogue(f"Cannot load probe module {path.name}.")
    module = importlib.util.module_from_spec(spec)
    folder = str(path.parent)
    added = folder not in sys.path
    if added:
        sys.path.insert(0, folder)
    try:
        spec.loader.exec_module(module)
    finally:
        if added:
            sys.path.remove(folder)
    return module


def load(folder: Path) -> tuple[Registered, ...]:
    """Charge le catalogue d'un dossier, en contrôlant sa cohérence.

    Les modules sont chargés **par chemin** et non par import : le catalogue
    n'est pas un paquet installé, et il n'a aucune raison de le devenir.

    Deux incohérences lèvent plutôt que de passer : un identifiant en double,
    qui casserait la référence depuis un message de commit, et un mode
    `automatic` sans fonction de rejeu, qui promettrait une vérification
    inexistante.
    """
    registered: list[Registered] = []
    seen: set[str] = set()
    for path in sorted(folder.glob("*.py")):
        if path.name.startswith(PRIVATE):
            continue
        module = _load_module(path)
        probe = getattr(module, "PROBE", None)
        if not isinstance(probe, Probe):
            raise InvalidCatalogue(f"{path.name} does not expose a PROBE of type Probe.")
        check = getattr(module, "check", None)
        if probe.mode is Mode.AUTOMATIC and check is None:
            raise InvalidCatalogue(
                f"{probe.identifier}: mode is automatic but {path.name} has no check()."
            )
        if probe.mode is not Mode.AUTOMATIC and check is not None:
            raise InvalidCatalogue(
                f"{probe.identifier}: {path.name} has a check() but mode is {probe.mode.value}."
            )
        if probe.identifier in seen:
            raise InvalidCatalogue(f"Duplicate identifier {probe.identifier}.")
        seen.add(probe.identifier)
        registered.append(Registered(probe=probe, check=check, origine=path))
    return tuple(registered)


def run(registered: Iterable[Registered], *, only: Iterable[str] | None = None) -> ProbeReport:
    """Rejoue les sondes, unitairement ou collectivement.

    `seulement` restreint à une liste d'identifiants — c'est ce qui permet de
    resonder par parties plutôt que de solliciter toutes les sources d'un
    coup. Une sonde sans fonction de rejeu rend `untested` sans rien
    demander à personne.

    Une exception levée par une sonde donne `cantTell` et **jamais**
    `passed` : ne pas pouvoir conclure n'est pas une bonne nouvelle.
    """
    selected = set(only) if only is not None else None
    started = datetime.now(UTC)
    assertions: list[Assertion] = []
    for entry in registered:
        identifier = entry.probe.identifier
        if selected is not None and identifier not in selected:
            continue
        if entry.check is None:
            assertions.append(
                Assertion(
                    identifier=identifier,
                    outcome=Outcome.UNTESTED,
                    detail=f"No probe; mode is {entry.probe.mode.value}.",
                    observed_at=datetime.now(UTC),
                )
            )
            continue
        start = time.perf_counter_ns()
        try:
            assertion = entry.check()
        except Exception as exc:
            assertion = Assertion(
                identifier=identifier,
                outcome=Outcome.CANT_TELL,
                detail=f"{type(exc).__name__}: {exc}"[:300],
                observed_at=datetime.now(UTC),
            )
        assertions.append(
            assertion.model_copy(update={"duration_ns": time.perf_counter_ns() - start})
        )
    return ProbeReport(started_at=started, assertions=tuple(assertions))


#: Les colonnes du registre versionné, dans cet ordre.
COLUMNS = (
    "identifier",
    "title",
    "nature",
    "status",
    "side",
    "producer",
    "artefact",
    "observed_on",
    "clause",
    "handling",
    "handled_in",
    "mode",
    "replay",
    "replay_note",
    "fixed_on",
    "status_note",
    # **La dernière colonne est obligatoire, et ce n'est pas une question de
    # mise en forme.** Un champ facultatif en fin de ligne y laisserait une
    # tabulation finale, que `trailing-whitespace` retirerait — et la retirer
    # décalerait tous les champs d'un cran. Fermer la ligne sur un champ que
    # le modèle exige non vide évite à la fois d'exclure le hook et d'ajouter
    # une colonne factice dont personne ne saurait quoi faire.
    "workaround",
)


def as_tsv(probes: Iterable[Probe]) -> str:
    """Rend le registre, trié par identifiant.

    Le TSV est **dérivé** du catalogue et jamais tenu à la main : une colonne
    qu'un humain doit penser à mettre à jour ne l'est pas, et c'est ce qui a
    tué toutes les tentatives de correspondance que le dépôt a recensées.
    """

    def cell(value: object) -> str:
        """Une cellule sans séparateur, sans saut de ligne et sans blanc de bord.

        L'élagage n'est pas cosmétique : un blanc en fin de dernière cellule
        suffirait à rouvrir le problème que l'ordre des colonnes ferme.
        """
        if value is None:
            return ""
        return str(value).replace("\t", " ").replace("\n", " ").replace("\r", "").strip()

    lines = ["\t".join(COLUMNS)]
    for probe in sorted(probes, key=lambda s: s.identifier):
        data = probe.model_dump()
        lines.append("\t".join(cell(data[c]) for c in COLUMNS))
    return "\n".join(lines) + "\n"


__all__ = [
    "COLUMNS",
    "PREFIX",
    "PRIVATE",
    "Assertion",
    "Handling",
    "InvalidCatalogue",
    "Mode",
    "Nature",
    "Outcome",
    "Probe",
    "ProbeReport",
    "Registered",
    "Replay",
    "Side",
    "Status",
    "as_tsv",
    "load",
    "run",
]
