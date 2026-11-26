"""Refuse un commit qui porterait un terme de `.denylist`.

**Pourquoi un hook.** Le dépôt est public et son historique est permanent :
un nom de projet utilisateur ou de source non consentante qui y entre n'en
sort plus. *Un contrôle qui s'exécute vaut mieux qu'une consigne qui se
lit.*

**Deux portées, deux appels.** `--diff` lit ce qui est indexé, `--message`
lit le message de commit : le skill impose les deux, et un terme proscrit
passe aussi volontiers par l'un que par l'autre.

**Le rapport ne cite jamais le terme trouvé.** Il donne le fichier et la
ligne. Afficher la chaîne la ferait entrer dans un terminal, un journal
d'exécution et un transcrit — c'est-à-dire exactement là où la liste existe
pour qu'elle n'aille pas. Le mainteneur sait ce que contient sa liste ; le
hook lui dit **où regarder**.

**Le motif n'impose pas de frontière de mot, et c'est délibéré.** C'est le
comportement de la commande manuelle qu'il remplace, `grep -i -E -f`.
Imposer une frontière raterait un terme logé dans un chemin, une URL ou un
identifiant — c'est-à-dire là où une fuite se produit réellement. Le prix
est un faux positif possible sur un terme court : il est visible, il se
lève en une seconde, et un manque, lui, est définitif.

**Absence de `.denylist` : le hook échoue.** La liste n'est pas versionnée,
délibérément — l'écrire dans un fichier suivi reviendrait à publier ce
qu'elle protège. Sur un clone qui ne l'a pas, le contrôle ne peut pas
conclure, et un contrôle qui ne peut pas conclure ne doit pas laisser
passer.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

LISTE = Path(".denylist")

ABSENTE = """Controle des termes proscrits impossible : `.denylist` est absent.

Cette liste n'est pas versionnee, et c'est voulu : l'ecrire dans un fichier
suivi reviendrait a publier ce qu'elle protege. Sur un clone neuf, en
demander le contenu au mainteneur -- voir « Confidentialite des tiers »
dans AGENTS.md.

Le commit est refuse : un controle qui ne peut pas conclure ne laisse pas
passer.
"""


def _motif() -> re.Pattern[str] | None:
    """Les entrées de la liste, en une alternation insensible à la casse."""
    if not LISTE.is_file():
        return None
    entrees = [
        ligne.strip()
        for ligne in LISTE.read_text(encoding="utf-8", errors="replace").splitlines()
        if ligne.strip() and not ligne.lstrip().startswith("#")
    ]
    if not entrees:
        return None
    return re.compile("|".join(entrees), re.IGNORECASE)


def _lignes_du_diff() -> list[tuple[str, int, str]]:
    """Les lignes **ajoutées** par ce qui est indexé, avec leur fichier."""
    rendu = subprocess.run(
        ["git", "diff", "--cached", "--unified=0"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    fichier, numero = "?", 0
    trouvees: list[tuple[str, int, str]] = []
    for ligne in rendu.stdout.splitlines():
        if ligne.startswith("+++ b/"):
            fichier, numero = ligne[6:], 0
        elif ligne.startswith("@@"):
            marque = re.search(r"\+(\d+)", ligne)
            numero = int(marque.group(1)) if marque else 0
        elif ligne.startswith("+") and not ligne.startswith("+++"):
            trouvees.append((fichier, numero, ligne[1:]))
            numero += 1
    return trouvees


def main(argv: list[str]) -> int:
    motif = _motif()
    if motif is None:
        print(ABSENTE, file=sys.stderr)
        return 1

    if "--message" in argv:
        chemins = [a for a in argv if not a.startswith("--")]
        a_examiner = [
            (chemin, numero, texte)
            for chemin in chemins
            for numero, texte in enumerate(
                Path(chemin).read_text(encoding="utf-8", errors="replace").splitlines(), 1
            )
            if not texte.lstrip().startswith("#")
        ]
    else:
        a_examiner = _lignes_du_diff()

    fautives = [(f, n) for f, n, texte in a_examiner if motif.search(texte)]
    if not fautives:
        return 0

    print("Terme proscrit dans ce commit.\n", file=sys.stderr)
    for fichier, numero in fautives[:20]:
        print(f"  {fichier}:{numero}", file=sys.stderr)
    if len(fautives) > 20:
        print(f"  ... et {len(fautives) - 20} autres", file=sys.stderr)
    print(
        "\nLe terme n'est pas affiche : il entrerait dans un terminal, un\n"
        "journal et un transcrit, c'est-a-dire la ou la liste existe pour\n"
        "qu'il n'aille pas. Voir « Confidentialite des tiers » dans AGENTS.md.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
