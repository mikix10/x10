"""Ce qui s'est passé pendant une exécution.

> **Prototype interne. Ce n'est pas une interface.** Il n'est pas versionné,
> il n'est pas documenté comme contrat, et il changera. Un intégrateur nous a
> demandé un compte rendu ; nous lui avons répondu que son contenu serait
> arrêté **avec lui**. Ce module existe pour éprouver la forme d'ici là, pas
> pour la figer.

**Deux niveaux de lecture, et le premier se suffit.** `PipelineReport` est ce
qu'un consommateur lit ; `GranuleReport` est le détail de diagnostic. Le
granule **explique** le compte rendu, il n'est pas la seule façon de le lire.

La raison est une mesure du 16/10/2026. Les clés de premier niveau du JSON
accumulé étaient `source`, `run_id`, `started_at`, `finished_at`,
`acquisition`, `granules` — **`verdict` n'y figurait pas**, étant une simple
`@property`. Qui relisait `runs.jsonl` devait donc réimplémenter « le pire
des granules », c'est-à-dire connaître à la fois notre découpage et sa règle
de préséance. Or le granule est l'unité que **le producteur** publie : un
consommateur a demandé « AROME SP1, 00H06H », pas deux granules rendant
chacun N hypercubes.

D'où des `computed_field` plutôt que des champs stockés : une seule source de
vérité — les granules —, aucune divergence possible, et une présence dans le
JSON qu'une `@property` n'a pas.

**Ce qui est arrêté par ailleurs**, et ne bougera pas : le compte rendu
**référence** le contrat de sortie au lieu de le contenir. Deux réseaux
consécutifs donnent un contrat **identique** — c'est cette invariance qui en
fait un indicateur de dérive du producteur, et la verser dans un journal la
détruirait. Le contrat décrit **la source** et dure ; le compte rendu décrit
**une exécution** et passe.

Modèles Pydantic et non dataclasses : ces objets franchissent une frontière
de processus — journal, fichier d'accompagnement, réponse d'appel — et
doivent se sérialiser sans code de conversion.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from x10_connectors import ConnectorResult


class Verdict(StrEnum):
    """Ce qu'on peut dire d'un granule après l'avoir traité.

    Le vocabulaire est **fermé**, et les quatre valeurs sont distinctes pour
    un programme qui doit décider :

    | Valeur | Sens |
    |---|---|
    | `COMPLETE` | tout ce qui est entré est ressorti |
    | `PARTIAL` | la donnée est là, amputée, et ce qui manque est nommé |
    | `FAILED` | ce granule n'a pas pu être traité |
    | `NOT_ASSESSED` | on ne s'est pas prononcé |

    `FAILED` et `NOT_ASSESSED` ne se confondent pas : « j'ai essayé et je n'ai
    pas pu » n'est pas « je n'ai pas eu de quoi essayer ». Le second arrive
    quand l'acquisition elle-même a échoué, donc qu'aucun granule n'était à
    juger.

    **Chaque valeur est produite quelque part**, et un test l'exige. Une
    valeur inatteignable serait une réserve que personne n'émet et que tout
    consommateur devrait pourtant gérer — le défaut relevé le 16/10/2026 sur
    `NOT_ASSESSED`.
    """

    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    NOT_ASSESSED = "not_assessed"


class ErrorType(StrEnum):
    """Catégorie d'un échec de traitement, pour qui doit décider sans lire.

    Une phrase ne permet aucun arbitrage programmatique ; une catégorie, si.
    Le vocabulaire est **fermé et dérivé des exceptions que les paquets
    exposent déjà** — il n'invente rien et se vérifie en les relisant.
    """

    #: Le fichier n'est pas lisible comme GRIB, ou son édition est inconnue.
    DECODE = "decode"
    #: Une unité GRIB sans correspondance UDUNITS — `UnconvertibleUnitError`.
    UNITS = "units"
    #: Un `stepType` hors table — `UnknownStatisticalProcessingError`.
    CELL_METHODS = "cell_methods"
    #: Un intervalle de durée variable — `UnrepresentableIntervalError`.
    INTERVAL = "interval"
    #: L'écriture n'a rien produit, ou la pile d'écriture manque.
    WRITE = "write"
    #: Tout le reste. Son emploi fréquent signalerait une catégorie à ajouter.
    OTHER = "other"


def contract_fingerprint(json_stable: str) -> str:
    """Référence courte et stable d'un contrat de sortie.

    Douze caractères d'un SHA-256 : assez pour distinguer deux contrats,
    assez court pour se lire dans un compte rendu. Calculée sur le rendu
    **stable** du contrat, donc déterministe d'une exécution à l'autre —
    c'est ce qui permet de dire « conforme au contrat C » sans transporter C.
    """
    return hashlib.sha256(json_stable.encode("utf-8")).hexdigest()[:12]


class GranuleReport(BaseModel):
    """Ce qu'est devenu un granule acquis. **Détail de diagnostic.**

    Un consommateur n'a pas à le parcourir : `PipelineReport` répond à ses
    questions. Ce niveau existe pour qui enquête — nous, un exploitant, ou un
    producteur à qui l'on signale un écart.
    """

    model_config = ConfigDict(frozen=True)

    #: Le fichier tel qu'il a été acquis.
    source: Path

    #: Les fichiers écrits. Plusieurs, un granule rendant plusieurs jeux.
    outputs: tuple[Path, ...] = ()

    #: Identifiants de paramètre lus dans les **en-têtes de l'entrée**.
    #: Lecture d'en-têtes seule : aucune donnée n'est décompressée, donc le
    #: coût reste négligeable même sur un fichier de plusieurs centaines de
    #: mébioctets.
    parameters_in: int = 0

    #: Champs effectivement décodés.
    fields_out: int = 0

    #: Identifiants présents à l'entrée et absents de la sortie, nommés.
    #: « Il manque quelque chose » ne permet aucun arbitrage ; la liste, si.
    dropped: tuple[str, ...] = ()

    #: **Référence** au contrat, jamais le contrat. Voir le module.
    contract: str | None = None

    verdict: Verdict = Verdict.NOT_ASSESSED

    #: Catégorie de l'échec, renseignée avec `FAILED` et elle seule.
    error_type: ErrorType | None = None

    #: Pourquoi ce verdict, en clair. Vide quand il n'y a rien à dire.
    reason: str = ""


class PipelineReport(BaseModel):
    """Une exécution du client. **C'est ce qu'un consommateur lit.**

    Il doit pouvoir répondre à ses cinq questions — ai-je eu ce que j'ai
    demandé, où est-ce, qu'est-ce qui manque, sous quelle licence, puis-je
    m'en servir — **sans ouvrir `granules`**, dont la forme est celle du
    producteur et non la sienne.
    """

    model_config = ConfigDict(frozen=True)

    source: str
    run_id: str
    started_at: datetime
    finished_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    #: Le compte rendu d'acquisition, **repris tel quel** et non recopié :
    #: il porte déjà l'origine retenue, le volume, la provenance et la
    #: licence, et le redéfinir en ferait deux sources de vérité.
    acquisition: ConnectorResult

    #: Le détail, pour qui enquête. Tout ce qui suit s'en déduit.
    granules: tuple[GranuleReport, ...] = ()

    # --- Ce qu'un consommateur lit, sans connaître les granules -------------
    #
    # `computed_field` et non champs stockés : les granules restent la seule
    # source de vérité, donc rien ne peut diverger, et la valeur apparaît
    # pourtant dans le JSON — ce qu'une simple `@property` ne fait pas.

    @computed_field  # type: ignore[prop-decorator]
    @property
    def verdict(self) -> Verdict:
        """Le verdict de l'exécution : le pire de ses granules.

        Un granule amputé suffit à amputer l'exécution. Rendre « complet »
        parce que la majorité l'est serait exactement le silence que ce
        compte rendu existe pour fermer.

        L'ordre de préséance est **ici et nulle part ailleurs** : c'est
        précisément pour éviter qu'un consommateur ait à le réimplémenter que
        ce champ est sérialisé.
        """
        if not self.granules:
            return Verdict.NOT_ASSESSED
        for pire in (Verdict.FAILED, Verdict.PARTIAL, Verdict.NOT_ASSESSED):
            if any(g.verdict is pire for g in self.granules):
                return pire
        return Verdict.COMPLETE

    @computed_field  # type: ignore[prop-decorator]
    @property
    def outputs(self) -> tuple[Path, ...]:
        """Tous les fichiers écrits — « où est ma donnée », en une clé."""
        return tuple(sortie for g in self.granules for sortie in g.outputs)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def dropped(self) -> tuple[str, ...]:
        """Tout ce qui manque, dédoublonné et trié — « que n'ai-je pas eu »."""
        return tuple(sorted({code for g in self.granules for code in g.dropped}))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def license(self) -> str | None:
        """La licence de réutilisation, remontée du lignage.

        Une donnée qui quitte le système sans ses conditions d'usage n'est pas
        exploitable ; l'enfouir sous `acquisition.retrieval` revenait à parier
        que le consommateur irait l'y chercher.
        """
        return self.acquisition.retrieval.license if self.acquisition.retrieval else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def selection(self) -> dict[str, Any]:
        """Ce qui avait été demandé, remonté du lignage.

        Sans elle, un compte rendu dit ce qu'on a obtenu sans dire par rapport
        à quoi.
        """
        return self.acquisition.retrieval.selection if self.acquisition.retrieval else {}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def granule_count(self) -> int:
        return len(self.granules)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def complete_count(self) -> int:
        return sum(1 for g in self.granules if g.verdict is Verdict.COMPLETE)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def partial_count(self) -> int:
        return sum(1 for g in self.granules if g.verdict is Verdict.PARTIAL)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def failed_count(self) -> int:
        return sum(1 for g in self.granules if g.verdict is Verdict.FAILED)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def parameters_in(self) -> int:
        """Paramètres présents à l'entrée, tous granules confondus."""
        return sum(g.parameters_in for g in self.granules)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fields_out(self) -> int:
        """Champs effectivement écrits, tous granules confondus."""
        return sum(g.fields_out for g in self.granules)

    # --- Rendu lisible --------------------------------------------------------

    def summary(self) -> str:
        """Une ligne par granule, lisible à l'œil."""
        lignes = [
            f"{self.source} — {self.verdict} — {self.granule_count} granule(s), "
            f"{self.acquisition.bytes_downloaded / 1024 / 1024:.1f} Mio acquis"
        ]
        for g in self.granules:
            detail = f" dropped={', '.join(g.dropped)}" if g.dropped else ""
            cause = f" [{g.error_type}]" if g.error_type else ""
            lignes.append(
                f"  {g.source.name} : {g.verdict}{cause}, "
                f"{g.parameters_in} en entrée -> {g.fields_out} en sortie"
                f"{detail}" + (f", contrat {g.contract}" if g.contract else "")
            )
        return "\n".join(lignes)


__all__ = [
    "ErrorType",
    "GranuleReport",
    "PipelineReport",
    "Verdict",
    "contract_fingerprint",
]
