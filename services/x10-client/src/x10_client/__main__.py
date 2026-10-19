"""Entrée exécutable : enchaîner la chaîne une fois, et sortir.

**Pas un ordonnanceur.** Pas de planification, pas de file, pas de service
résident : une exécution qu'un ordonnanceur extérieur appelle, et un code de
sortie qu'il sait lire.

| Code | Sens |
|---|---|
| 0 | tout est complet |
| 1 | une acquisition a échoué |
| 2 | la configuration est incomplète ou la requête inconnue |
| 3 | **acquis, mais amputé** — la donnée est là, il en manque une partie |

Le code 3 existe parce que 0 et 1 ne suffisent pas : un granule amputé n'est
ni un succès ni un échec, et laisser un ordonnanceur croire à l'un ou à
l'autre serait le silence que ce client existe pour fermer.
"""

from __future__ import annotations

import argparse
import sys

from .availability import observe
from .config import MissingConfiguration, Settings
from .report import Verdict
from .session import Session, UnknownRequest


def _request(args: argparse.Namespace) -> object:
    from x10_connectors import MeteoFrancePntRequest

    return MeteoFrancePntRequest(
        model=args.model,
        grid=args.grid,
        packages=tuple(args.package),
        time_ranges=tuple(args.time_range),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="x10_client", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("run", help="acquiert et normalise une sélection")
    p.add_argument("--model", default="arome")
    p.add_argument("--grid", default="0025")
    p.add_argument("--package", action="append", required=True)
    p.add_argument("--time-range", action="append", default=[])

    sub.add_parser("observe", help="ce que le trafic passé dit des sources")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2

    try:
        settings = Settings.from_env()
    except MissingConfiguration as exc:
        print(f"Configuration : {exc}", file=sys.stderr)
        return 2

    if args.command == "observe":
        observed = observe(settings.state)
        if not observed:
            print("Aucune exécution enregistrée — rien à constater.")
            return 0
        for c in observed:
            rate = "—" if c.success_rate is None else f"{c.success_rate:.0%}"
            duration = "—" if c.median_duration_ms is None else f"{c.median_duration_ms:.0f} ms"
            print(
                f"{c.source:28} {c.runs:4} exécution(s), succès {rate}, "
                f"médiane {duration}, {c.bytes_total / 1024 / 1024:.0f} Mio"
            )
        return 0

    try:
        report = Session(settings).run(_request(args))
    except UnknownRequest as exc:
        print(f"Requête : {exc}", file=sys.stderr)
        return 2

    print(report.summary())
    if report.acquisition.outcome != "success":
        return 1
    return 3 if report.verdict is Verdict.PARTIAL else 0


if __name__ == "__main__":
    raise SystemExit(main())
