"""Exige une relecture de sécurité déclarée quand un chemin sensible change.

Il impose de déclarer la relecture dans le message de commit, de sorte que
l'affirmation reste dans l'historique, qui est permanent et vérifiable.

**Pourquoi un hook et non un skill.** Un skill est une consigne adressée à
celui qui travaille ; elle s'oublie. Un hook s'exécute quoi qu'il arrive.

**Pourquoi par chemin et non par membre.** Une règle du genre « relecture
avant tout commit sur `x10-client` » viserait mal deux fois : elle se
déclencherait sur un README — et une barrière qui se déclenche sur tout
s'apprend à écarter d'un geste — tout en manquant `observability.py`, qui
vit dans `x10-connectors`, et le bloc `[tool.mypy]`, qui vit à la racine.

Usage, dans le message de commit :

    Security-Review: 2026-10-16

Appelé en `commit-msg` : c'est le seul moment où le message **et** la liste
des fichiers indexés sont disponibles ensemble.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

#: Chemins dont une modification demande une relecture. **Fermé et court** :
#: ce sont les endroits où un changement d'apparence anodine désarme une
#: protection sans rien casser.
SENSIBLES = (
    # Les secrets : leur lecture, leur rédaction, leur typage.
    "services/x10-client/src/x10_client/credentials.py",
    "packages/x10-connectors/src/x10_connectors/observability.py",
    # Les références qui rendent visible un affaiblissement.
    "workspace-tests/derogations.txt",
    "workspace-tests/tests-inventaire.txt",
    "workspace-tests/lexique-public.txt",
    # Les garde-fous eux-mêmes.
    ".pre-commit-config.yaml",
    ".pre-commit-hooks/",
    ".github/workflows/",
)

#: Le `pyproject.toml` racine n'est sensible que par son bloc de typage : le
#: viser en entier ferait lever le hook à chaque ajout de dépendance.
RACINE_PYPROJECT = "pyproject.toml"
BLOC_TYPAGE = re.compile(r"^[-+].*\b(strict|ignore_errors|disable_error_code|overrides)\b", re.M)

MARQUEUR = re.compile(r"^Security-Review:\s*\S+", re.M)


def _indexes() -> list[str]:
    sortie = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [ligne.strip() for ligne in sortie.stdout.splitlines() if ligne.strip()]


def _typage_modifie() -> bool:
    """Le `pyproject.toml` racine a-t-il changé **sur son typage** ?"""
    sortie = subprocess.run(
        ["git", "diff", "--cached", "--unified=0", "--", RACINE_PYPROJECT],
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(BLOC_TYPAGE.search(sortie.stdout))


def concernes(fichiers: list[str]) -> list[str]:
    """Les chemins sensibles effectivement touchés."""
    touches = [f for f in fichiers for motif in SENSIBLES if f == motif or f.startswith(motif)]
    if RACINE_PYPROJECT in fichiers and _typage_modifie():
        touches.append(f"{RACINE_PYPROJECT} (bloc de typage)")
    return sorted(set(touches))


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return 0
    message = Path(argv[1]).read_text(encoding="utf-8", errors="replace")

    touches = concernes(_indexes())
    if not touches or MARQUEUR.search(message):
        return 0

    detail = "\n".join(f"    {f}" for f in touches)
    print(
        "Relecture de securite requise.\n\n"
        "Ce commit touche des chemins dont une modification peut desarmer une\n"
        "protection sans rien casser :\n\n"
        f"{detail}\n\n"
        "Relire le skill `security`, verifier que la protection tient toujours,\n"
        "puis ajouter au message de commit une ligne :\n\n"
        "    Security-Review: <date>\n\n"
        "L'affirmation reste dans l'historique du depot.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
