"""Constater la disponibilité d'une source, sans la solliciter.

Le principe précède la conception, et il interdit la solution évidente :
**chaque acquisition réelle dit déjà si la source a répondu**, en combien de
temps et pour quel volume. Il suffit de relire ce qu'on a déjà écrit.

Une sonde n'est légitime que là où le trafic réel ne passe pas, et alors sous
la forme la moins coûteuse — requête conditionnelle ou en-tête seul, jamais
un téléchargement complet pour vérifier qu'une source répond. **Ce module
n'en émet aucune**, et c'est son principal trait.

> Limite assumée : l'observation a des trous là où l'usage est rare. Un
> `Constat` sans exécution est donc rendu tel quel, et non comme une
> indisponibilité — ne pas savoir n'est pas la même chose que savoir que
> cela ne marche pas.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Constat:
    """Ce que le trafic passé dit d'une source. Jamais plus que cela."""

    source: str
    executions: int
    succes: int
    derniere: datetime | None
    duree_mediane_ms: float | None
    octets_total: int

    @property
    def taux_de_succes(self) -> float | None:
        """`None` quand rien n'a été observé — et non zéro.

        Rendre zéro ferait passer une absence de mesure pour un échec
        complet, ce qui est exactement le genre de silence que X10 traque
        ailleurs.
        """
        return self.succes / self.executions if self.executions else None


def _lignes(etat: Path) -> list[dict[str, Any]]:
    cible = etat / "executions.jsonl"
    if not cible.is_file():
        return []
    retenues = []
    for ligne in cible.read_text(encoding="utf-8").splitlines():
        if not ligne.strip():
            continue
        try:
            retenues.append(json.loads(ligne))
        except json.JSONDecodeError:
            # Une ligne tronquee — ecriture interrompue — ne disqualifie pas
            # les autres. On la passe plutot que de perdre tout l'historique.
            continue
    return retenues


def constater(etat: Path, source: str | None = None) -> tuple[Constat, ...]:
    """Ce que l'historique accumulé dit, source par source.

    Ne lit que des fichiers locaux. Aucun appel réseau, par construction.
    """
    par_source: dict[str, list[dict[str, Any]]] = {}
    for ligne in _lignes(etat):
        nom = str(ligne.get("source", "?"))
        if source is not None and nom != source:
            continue
        par_source.setdefault(nom, []).append(ligne)

    constats = []
    for nom, executions in sorted(par_source.items()):
        acquisitions = [e.get("acquisition") or {} for e in executions]
        durees = sorted(
            float(a["duration_ns"]) / 1e6
            for a in acquisitions
            if isinstance(a.get("duration_ns"), (int, float))
        )
        horodatages = sorted(str(e["finished_at"]) for e in executions if e.get("finished_at"))
        constats.append(
            Constat(
                source=nom,
                executions=len(executions),
                succes=sum(1 for a in acquisitions if a.get("outcome") == "success"),
                derniere=(datetime.fromisoformat(horodatages[-1]) if horodatages else None),
                duree_mediane_ms=(durees[len(durees) // 2] if durees else None),
                octets_total=sum(int(a.get("bytes_downloaded") or 0) for a in acquisitions),
            )
        )
    return tuple(constats)


__all__ = ["Constat", "constater"]
