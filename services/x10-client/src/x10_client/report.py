"""Ce qui s'est passé pendant une exécution.

> **Prototype interne. Ce n'est pas une interface.** Il n'est pas versionné,
> il n'est pas documenté comme contrat, et il changera. Un intégrateur nous a
> demandé un compte rendu ; nous lui avons répondu que son contenu serait
> arrêté **avec lui**. Ce module existe pour éprouver la forme d'ici là, pas
> pour la figer.

**Ce qui est en revanche arrêté**, et ne bougera pas : le compte rendu
**référence** le contrat de sortie au lieu de le contenir.

La raison est mesurée. Deux réseaux consécutifs donnent un contrat
**identique** — c'est cette invariance qui en fait un indicateur de dérive du
producteur. Les informations d'exécution, elles, diffèrent à chaque fois par
construction. Les verser dans le contrat détruirait la seule propriété qui le
distingue d'un journal.

Le contrat décrit **la source** et dure ; le compte rendu décrit **une
exécution** et passe. C'est leur comparaison qui produit le verdict.

Modèles Pydantic et non dataclasses : ces objets franchissent une frontière
de processus — journal, fichier d'accompagnement, réponse d'appel — et
doivent se sérialiser sans code de conversion.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from x10_connectors import ConnectorResult


class Verdict(StrEnum):
    """Ce qu'on peut dire d'un granule après l'avoir traité.

    Le vocabulaire est **fermé**, et `NON_EVALUE` n'est pas un échec : c'est
    l'aveu qu'on n'a pas pu se prononcer. Un consommateur qui est un
    programme a besoin de distinguer « je sais que c'est incomplet » de « je
    ne sais pas » — une réserve qu'il ne saurait pas interpréter serait une
    réserve perdue.
    """

    COMPLET = "complet"
    AMPUTE = "ampute"
    NON_EVALUE = "non_evalue"


def empreinte_de_contrat(json_stable: str) -> str:
    """Référence courte et stable d'un contrat de sortie.

    Douze caractères d'un SHA-256 : assez pour distinguer deux contrats,
    assez court pour se lire dans un compte rendu. Calculée sur le rendu
    **stable** du contrat, donc déterministe d'une exécution à l'autre —
    c'est ce qui permet de dire « conforme au contrat C » sans transporter C.
    """
    return hashlib.sha256(json_stable.encode("utf-8")).hexdigest()[:12]


class GranuleReport(BaseModel):
    """Ce qu'est devenu un granule acquis."""

    model_config = ConfigDict(frozen=True)

    #: Le fichier tel qu'il a été acquis.
    source: Path

    #: Les fichiers écrits. Plusieurs, un granule rendant plusieurs jeux.
    sorties: tuple[Path, ...] = ()

    #: Identifiants de paramètre lus dans les **en-têtes de l'entrée**.
    #: Lecture d'en-têtes seule : aucune donnée n'est décompressée, donc le
    #: coût reste négligeable même sur un fichier de plusieurs centaines de
    #: mébioctets.
    parametres_en_entree: int = 0

    #: Champs effectivement décodés.
    champs_en_sortie: int = 0

    #: Identifiants présents à l'entrée et absents de la sortie, nommés.
    #: « Il manque quelque chose » ne permet aucun arbitrage ; la liste, si.
    perdus: tuple[str, ...] = ()

    #: **Référence** au contrat, jamais le contrat. Voir le module.
    contrat: str | None = None

    verdict: Verdict = Verdict.NON_EVALUE

    #: Pourquoi ce verdict, en clair. Vide quand il n'y a rien à dire.
    motif: str = ""


class PipelineReport(BaseModel):
    """Une exécution du client, de l'acquisition à l'écriture."""

    model_config = ConfigDict(frozen=True)

    source: str
    run_id: str
    started_at: datetime
    finished_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    #: Le compte rendu d'acquisition, **repris tel quel** et non recopié :
    #: il porte déjà l'origine retenue, le volume, la provenance et la
    #: licence, et le redéfinir en ferait deux sources de vérité.
    acquisition: ConnectorResult

    granules: tuple[GranuleReport, ...] = ()

    @property
    def verdict(self) -> Verdict:
        """Le verdict de l'exécution : le pire de ses granules.

        Un granule amputé suffit à amputer l'exécution. Rendre « complet »
        parce que la majorité l'est serait exactement le silence que ce
        compte rendu existe pour fermer.
        """
        if not self.granules:
            return Verdict.NON_EVALUE
        if any(g.verdict is Verdict.AMPUTE for g in self.granules):
            return Verdict.AMPUTE
        if any(g.verdict is Verdict.NON_EVALUE for g in self.granules):
            return Verdict.NON_EVALUE
        return Verdict.COMPLET

    def resume(self) -> str:
        """Une ligne par granule, lisible à l'œil."""
        lignes = [
            f"{self.source} — {self.verdict} — {len(self.granules)} granule(s), "
            f"{self.acquisition.bytes_downloaded / 1024 / 1024:.1f} Mio acquis"
        ]
        for g in self.granules:
            detail = f" perdus={', '.join(g.perdus)}" if g.perdus else ""
            lignes.append(
                f"  {g.source.name} : {g.verdict}, "
                f"{g.parametres_en_entree} en entrée -> {g.champs_en_sortie} en sortie"
                f"{detail}" + (f", contrat {g.contrat}" if g.contrat else "")
            )
        return "\n".join(lignes)


__all__ = [
    "GranuleReport",
    "PipelineReport",
    "Verdict",
    "empreinte_de_contrat",
]
