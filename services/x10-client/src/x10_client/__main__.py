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

from .availability import constater
from .config import ConfigurationManquante, Settings
from .report import Verdict
from .session import RequeteInconnue, Session


def _requete(args: argparse.Namespace) -> object:
    from x10_connectors import MeteoFrancePntRequest

    return MeteoFrancePntRequest(
        model=args.modele,
        grid=args.grille,
        packages=tuple(args.paquet),
        time_ranges=tuple(args.tranche),
    )


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(prog="x10_client", description=__doc__.splitlines()[0])
    sous = analyseur.add_subparsers(dest="commande")

    p = sous.add_parser("run", help="acquiert et normalise une sélection")
    p.add_argument("--modele", default="arome")
    p.add_argument("--grille", default="0025")
    p.add_argument("--paquet", action="append", required=True)
    p.add_argument("--tranche", action="append", default=[])

    sous.add_parser("constater", help="ce que le trafic passé dit des sources")

    args = analyseur.parse_args(argv)
    if args.commande is None:
        analyseur.print_help()
        return 2

    try:
        settings = Settings.from_env()
    except ConfigurationManquante as exc:
        print(f"Configuration : {exc}", file=sys.stderr)
        return 2

    if args.commande == "constater":
        constats = constater(settings.etat)
        if not constats:
            print("Aucune exécution enregistrée — rien à constater.")
            return 0
        for c in constats:
            taux = "—" if c.taux_de_succes is None else f"{c.taux_de_succes:.0%}"
            duree = "—" if c.duree_mediane_ms is None else f"{c.duree_mediane_ms:.0f} ms"
            print(
                f"{c.source:28} {c.executions:4} exécution(s), succès {taux}, "
                f"médiane {duree}, {c.octets_total / 1024 / 1024:.0f} Mio"
            )
        return 0

    try:
        rapport = Session(settings).run(_requete(args))
    except RequeteInconnue as exc:
        print(f"Requête : {exc}", file=sys.stderr)
        return 2

    print(rapport.resume())
    if rapport.acquisition.outcome != "success":
        return 1
    return 3 if rapport.verdict is Verdict.AMPUTE else 0


if __name__ == "__main__":
    raise SystemExit(main())
