"""Les chiffres du dépôt, engendrés plutôt que recopiés.

**Pourquoi ce fichier.** Mesuré le 26/11/2026 : `docs/divergences-observees.md`
donnait **quatre** comptes différents de ses propres entrées — 17, dix-sept,
quatorze, 17 — quand le registre en portait **20** ; `docs/tests-et-couverture.md`
annonçait deux taux de couverture incompatibles à quelques lignes d'écart ;
et deux notes parlaient de « cinq paquets » quand le workspace en compte six.
Aucune de ces phrases n'était fausse le jour où elle a été écrite.

C'est le piège que le dépôt connaît et qu'il s'était épargné partout
ailleurs : *une colonne qu'un humain doit penser à mettre à jour ne l'est
jamais*. Cinq références étaient déjà engendrées — le lexique public,
l'inventaire des tests, les dérogations de typage, le registre des écarts, le
contrat de sortie. Les chiffres sont la sixième, et la dernière qui restait à
la main.

**La règle qui en découle, et elle est dans `AGENTS.md`** : un chiffre dans la
prose est **daté** — c'est alors une mesure à un instant, et elle reste vraie —
ou bien il **renvoie ici**. Ce qu'il ne peut plus être, c'est présent, nu et
périmé.

**Ce que ce fichier ne porte pas**, et c'est délibéré : rien qui demande le
réseau, rien qui demande d'exécuter la suite. Le taux de couverture n'y est
donc pas — il se lit de `coverage report`, et le dater dans la prose reste la
seule forme honnête.

Régénérer : `X10_CHIFFRES_UPDATE=1 uv run pytest workspace-tests/test_chiffres.py`
"""

from __future__ import annotations

import csv
import os
import re
import subprocess
from collections import Counter
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
REFERENCE = Path(__file__).resolve().parent / "chiffres.txt"

EN_TETE = (
    "# Engendre par workspace-tests/test_chiffres.py -- ne pas editer a la main.\n"
    "# Regenerer : X10_CHIFFRES_UPDATE=1 uv run pytest workspace-tests/test_chiffres.py\n"
)


def _lignes_python(dossier: Path) -> int:
    if not dossier.is_dir():
        return 0
    return sum(
        len(fichier.read_text(encoding="utf-8").splitlines())
        for fichier in sorted(dossier.rglob("*.py"))
    )


def _membres() -> list[Path]:
    """Les membres du workspace, dans l'ordre des deux dossiers racine."""
    return [
        chemin.parent
        for groupe in ("packages", "services")
        for chemin in sorted((RACINE / groupe).glob("x10-*/pyproject.toml"))
    ]


def _chiffres() -> list[str]:
    lignes: list[str] = []

    membres = _membres()
    lignes.append(f"workspace.membres\t{len(membres)}")
    total = 0
    for membre in membres:
        n = _lignes_python(membre / "src")
        total += n
        lignes.append(f"src.{membre.name}\t{n}")
    lignes.append(f"src.total\t{total}")

    # L'index git fait foi : un `rglob` ramasse les environnements
    # virtuels, et le compte passe de 42 fichiers a 1 314 sans que rien ne
    # le signale. Mesure du 26/11/2026, corrigee le jour meme.
    suivis = subprocess.run(
        ["git", "ls-files", "*test_*.py"],
        cwd=RACINE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.split()
    fichiers = sorted(RACINE / chemin for chemin in suivis)
    fonctions = sum(
        len(re.findall(r"^def test_", f.read_text(encoding="utf-8"), re.M)) for f in fichiers
    )
    lignes.append(f"tests.fichiers\t{len(fichiers)}")
    lignes.append(f"tests.fonctions\t{fonctions}")

    for nom, fichier in (
        ("lexique.termes", "workspace-tests/lexique-public.txt"),
        ("typage.derogations", "workspace-tests/derogations.txt"),
    ):
        chemin = RACINE / fichier
        compte = len(
            [
                ligne
                for ligne in chemin.read_text(encoding="utf-8").splitlines()
                if ligne.strip() and not ligne.lstrip().startswith("#")
            ]
        )
        lignes.append(f"{nom}\t{compte}")

    with (RACINE / "docs" / "divergences.tsv").open(encoding="utf-8") as flux:
        ecarts = list(csv.DictReader(flux, delimiter="\t"))
    lignes.append(f"ecarts.entrees\t{len(ecarts)}")
    for colonne in ("status", "mode"):
        if ecarts and colonne in ecarts[0]:
            for valeur, compte in sorted(Counter(e[colonne] for e in ecarts).items()):
                lignes.append(f"ecarts.{colonne}.{valeur}\t{compte}")
    lignes.append(f"sondes\t{len(list((RACINE / 'probes').glob('x10_div_*.py')))}")

    lignes.append(f"docs.notes\t{len(list((RACINE / 'docs').glob('*.md')))}")
    lignes.append(f"skills\t{len(list((RACINE / '.claude' / 'skills').glob('*/SKILL.md')))}")

    return lignes


def test_les_chiffres_du_depot_sont_a_jour() -> None:
    """Le fichier commité décrit-il encore le dépôt ?

    Un écart n'est pas une faute : c'est le signal qu'un chiffre a bougé et
    qu'une phrase qui le cite doit peut-être changer. La régénération produit
    **une ligne de `git diff` qu'un relecteur lit**, ce qui est tout l'objet
    du dispositif.
    """
    attendu = EN_TETE + "\n".join(_chiffres()) + "\n"

    if os.environ.get("X10_CHIFFRES_UPDATE"):
        REFERENCE.write_text(attendu, encoding="utf-8", newline="\n")
        return

    assert REFERENCE.is_file(), (
        f"{REFERENCE.name} est absent. Le creer : "
        "X10_CHIFFRES_UPDATE=1 uv run pytest workspace-tests/test_chiffres.py"
    )
    obtenu = REFERENCE.read_text(encoding="utf-8")
    assert obtenu == attendu, (
        "Les chiffres du depot ont change. Regenerer avec "
        "X10_CHIFFRES_UPDATE=1, relire le diff, et verifier qu'aucune phrase "
        "de la documentation ne cite une valeur devenue fausse."
    )
