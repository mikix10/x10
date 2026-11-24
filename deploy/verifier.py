"""Verification de deploiement : l'image demarre, decode, et atteint ses sources.

Trois constats, et rien de plus. Ce script ne collecte pas, n'ecrit rien et
n'ouvre aucun identifiant : il repond a la question « cette image est-elle
exploitable la ou elle tourne ».

**Les hotes ne sont pas ecrits ici.** Ils sont importes des connecteurs, de
sorte que ce script ne puisse pas deriver de ce que le code fait reellement
-- une URL recopiee de memoire est la faute que ce depot a deja payee.

Code de sortie : 0 si tout passe, 1 sinon. C'est ce code qui constitue le
verdict quand le script tourne comme tache d'un orchestrateur.
"""

from __future__ import annotations

import argparse
import platform
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

#: Delai maximal d'une sonde reseau, en secondes. Court : on mesure
#: l'atteignabilite, pas le debit.
TIMEOUT_S = 15


@dataclass(frozen=True)
class Check:
    """Resultat d'un controle, tel qu'il sera imprime puis totalise."""

    name: str
    passed: bool
    detail: str
    #: Duree du controle, en millisecondes. Observation, pas verdict -- mais
    #: elle decide quelque chose : si l'installation depuis le depot coute
    #: plus qu'une tache programmee ne peut payer a chaque execution, l'image
    #: publiee cesse d'etre un confort et devient necessaire.
    duration_ms: float | None = None


def _runtime_checks() -> list[Check]:
    """Ce que l'image porte : interpreteur, systeme, pile de decodage."""
    checks = [
        Check("python", True, f"{platform.python_version()} / {platform.machine()}"),
    ]

    try:
        import eccodes

        checks.append(
            Check("eccodes", True, str(eccodes.codes_definition_path())),
        )
    except Exception as exc:
        checks.append(Check("eccodes", False, f"{type(exc).__name__}: {exc}"))

    try:
        import cfgrib

        checks.append(Check("cfgrib", True, cfgrib.__version__))
    except Exception as exc:
        checks.append(Check("cfgrib", False, f"{type(exc).__name__}: {exc}"))

    return checks


def _table_checks(expected_cf: str | None, expected_output: str | None) -> list[Check]:
    """Les deux empreintes de tables, et leur comparaison si elle est demandee.

    Elles sont la raison d'etre de cette verification : deux deploiements qui
    rendent la meme empreinte lisent la donnee de la meme facon. Un ecart dit
    que les tables different, donc que le sens peut differer.
    """
    checks: list[Check] = []
    for label, module, function, expected in (
        ("tables cf", "x10_connectors.grib2", "cf_tables_revision", expected_cf),
        (
            "tables sortie",
            "x10_connectors.netcdf_cf",
            "output_tables_revision",
            expected_output,
        ),
    ):
        try:
            imported = __import__(module, fromlist=[function])
            revision = str(getattr(imported, function)())
        except Exception as exc:
            checks.append(Check(label, False, f"{type(exc).__name__}: {exc}"))
            continue

        if expected is None:
            checks.append(Check(label, True, revision))
        elif revision == expected:
            checks.append(Check(label, True, f"{revision} (conforme)"))
        else:
            checks.append(
                Check(label, False, f"{revision}, attendu {expected}"),
            )
    return checks


def _probe(label: str, url: str) -> Check:
    """Une requete, un verdict. Tout code HTTP rendu vaut atteignabilite."""
    request = urllib.request.Request(url, method="GET")
    started = time.monotonic()

    def elapsed() -> float:
        return (time.monotonic() - started) * 1000

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            return Check(label, True, f"HTTP {response.status}", elapsed())
    except urllib.error.HTTPError as exc:
        # Un 401 ou un 403 prouve que l'hote repond : c'est ce qu'on mesure.
        return Check(label, True, f"HTTP {exc.code}", elapsed())
    except Exception as exc:
        return Check(label, False, f"{type(exc).__name__}: {exc}", elapsed())


def _network_checks() -> list[Check]:
    """Le sortant vers les producteurs que les connecteurs declarent."""
    try:
        from x10_connectors.ecmwf_ifs import SOURCE_URL as ecmwf_url
        from x10_connectors.meteofrance_pnt import BASE_URL as meteofrance_url
    except Exception as exc:
        return [Check("sources", False, f"{type(exc).__name__}: {exc}")]

    return [
        _probe("sortant ecmwf", f"{ecmwf_url}/"),
        _probe("sortant meteofrance", f"{meteofrance_url}/?list-type=2&max-keys=1"),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expect-cf-tables",
        default=None,
        help="empreinte attendue des tables GRIB vers CF ; comparee si fournie",
    )
    parser.add_argument(
        "--expect-output-tables",
        default=None,
        help="empreinte attendue des tables de sortie ; comparee si fournie",
    )
    parser.add_argument(
        "--skip-network",
        action="store_true",
        help="ne pas sonder les producteurs, pour un environnement sans sortant",
    )
    args = parser.parse_args(argv)

    started = time.monotonic()
    checks = _runtime_checks()
    checks += _table_checks(args.expect_cf_tables, args.expect_output_tables)
    if not args.skip_network:
        checks += _network_checks()
    total_ms = (time.monotonic() - started) * 1000

    width = max(len(check.name) for check in checks)
    for check in checks:
        marker = "ok  " if check.passed else "ECHEC"
        duree = "" if check.duration_ms is None else f"  [{check.duration_ms:.0f} ms]"
        print(f"{marker} {check.name.ljust(width)}  {check.detail}{duree}")

    failed = [check.name for check in checks if not check.passed]
    if failed:
        print(f"\n{len(failed)} controle(s) en echec : {', '.join(failed)}")
        print(f"{len(checks)} controles en {total_ms:.0f} ms")
        return 1
    print(f"\n{len(checks)} controles, tous passes, en {total_ms:.0f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
