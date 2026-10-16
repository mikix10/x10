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
class Availability:
    """Ce que le trafic passé dit d'une source. Jamais plus que cela."""

    source: str
    runs: int

    #: Exécutions où **la source a répondu**. C'est la disponibilité au sens
    #: strict : elle ne dit rien de ce que nous avons su faire de la donnée.
    successes: int

    #: Exécutions où la donnée est ressortie **complète**. Toujours inférieur
    #: ou égal à `successes` : une source peut très bien répondre et nous
    #: livrer de l'inexploitable, et confondre les deux masquerait exactement
    #: cette situation.
    usable: int

    last_run: datetime | None
    median_duration_ms: float | None
    bytes_total: int

    @property
    def success_rate(self) -> float | None:
        """Part des exécutions où la source a répondu.

        `None` quand rien n'a été observé — et non zéro. Rendre zéro ferait
        passer une absence de mesure pour un échec complet, ce qui est
        exactement le genre de silence que X10 traque ailleurs.
        """
        return self.successes / self.runs if self.runs else None

    @property
    def usable_rate(self) -> float | None:
        """Part des exécutions dont la donnée est sortie complète.

        L'écart avec `success_rate` est le signal intéressant : il mesure ce
        qui échoue **chez nous** une fois la source servie.
        """
        return self.usable / self.runs if self.runs else None


def _lines(state: Path) -> list[dict[str, Any]]:
    target = state / "runs.jsonl"
    if not target.is_file():
        return []
    kept = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            kept.append(json.loads(line))
        except json.JSONDecodeError:
            # Une ligne tronquee — ecriture interrompue — ne disqualifie pas
            # les autres. On la passe plutot que de perdre tout l'historique.
            continue
    return kept


def observe(state: Path, source: str | None = None) -> tuple[Availability, ...]:
    """Ce que l'historique accumulé dit, source par source.

    Ne lit que des fichiers locaux. Aucun appel réseau, par construction.
    """
    by_source: dict[str, list[dict[str, Any]]] = {}
    for line in _lines(state):
        name = str(line.get("source", "?"))
        if source is not None and name != source:
            continue
        by_source.setdefault(name, []).append(line)

    observed = []
    for name, runs in sorted(by_source.items()):
        acquisitions = [e.get("acquisition") or {} for e in runs]
        durations = sorted(
            float(a["duration_ns"]) / 1e6
            for a in acquisitions
            if isinstance(a.get("duration_ns"), (int, float))
        )
        timestamps = sorted(str(e["finished_at"]) for e in runs if e.get("finished_at"))
        observed.append(
            Availability(
                source=name,
                runs=len(runs),
                successes=sum(1 for a in acquisitions if a.get("outcome") == "success"),
                # Le verdict est sérialisé depuis le 16/10/2026 ; avant, il
                # fallait le recalculer depuis les granules, donc connaître
                # notre découpage. Un historique antérieur n'en porte pas, et
                # `"complete"` absent compte alors comme inexploitable — ce
                # qui est le bon défaut : on ne sait pas, donc on n'affirme pas.
                usable=sum(1 for e in runs if e.get("verdict") == "complete"),
                last_run=(datetime.fromisoformat(timestamps[-1]) if timestamps else None),
                median_duration_ms=(durations[len(durations) // 2] if durations else None),
                bytes_total=sum(int(a.get("bytes_downloaded") or 0) for a in acquisitions),
            )
        )
    return tuple(observed)


__all__ = ["Availability", "observe"]
