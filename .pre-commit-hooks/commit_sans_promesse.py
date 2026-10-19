"""Refuse un message de commit qui s'engage sur la suite.

**Un commit décrit ce qui a été fait.** Il ne promet rien, n'annonce aucun
chantier et ne laisse aucune question en suspens : l'historique est permanent
et consultable longtemps après que la promesse a été tenue — ou oubliée. Une
clause prospective ne vieillit pas, elle se périme.

Le coût réel n'est pas l'inexactitude, c'est la **dilution** : « les données
ouvertes de l'ECMWF exposent une direction de vagues » est un constat utile
qu'un « — ce dont la suite reste une question ouverte » noie aussitôt. Le
lecteur pressé retient la seconde moitié.

**La liste de motifs est délibérément courte, et n'est pas exhaustive.** Une
liste de mots ne trouve que ce qu'on y a déjà mis, et la prochaine promesse
sera tournée autrement. Ce que ce contrôle garantit est plus modeste : les
formes fréquentes ne passent plus par distraction. Le reste relève de la
relecture — c'est le même parti que le lexique public.

Ce qui reste légitime, et que le contrôle laisse passer :

* ce que **le code** fait désormais — « la clé est omise », « le test
  échouera si un producteur prend de l'avance » décrivent un comportement ;
* les renvois à une note ou à un document, qui ne promettent rien.

Appelé en `commit-msg`.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

#: Formes prospectives fréquentes. Chacune est écrite **sans accent** : le
#: message est normalisé avant comparaison, de sorte qu'une seule entrée
#: couvre « ultérieurement » et « ulterieurement », les messages du dépôt
#: étant en ASCII.
PROMESSES = (
    r"questions? ouvertes?",
    r"reste(?:nt)? ouverte?s?",
    r"reste(?:nt)? a ",
    r"rester(?:a|ont)",
    r"a trancher",
    r"a decider",
    r"a venir",
    r"plus tard",
    r"ulterieurement",
    r"prochainement",
    r"il faudra",
    r"devra|devront",
    r"ser(?:a|ont) (?:fait|faite|faits|faites|ajoute|ajoutes|traite|traites|revu|revus|repris)",
    r"prochaine?s? (?:chantier|demande|etape|version|commit)",
    r"todo|fixme",
)

MOTIF = re.compile("|".join(f"(?:{p})" for p in PROMESSES), re.IGNORECASE)

#: Lignes que le contrôle ne lit pas : commentaires de git, et tout ce qui
#: suit les ciseaux d'un commit verbeux.
CISEAUX = "------------------------ >8 ------------------------"

#: Pieds de message structurés — `Security-Review:`, `BREAKING CHANGE:`,
#: `Refs:`. Un `BREAKING CHANGE:` dit légitimement à un consommateur ce qu'il
#: **devra** faire ; c'est une consigne, pas une promesse de notre part.
#:
#: **Ils ne valent que dans le dernier bloc**, comme git lui-même les définit.
#: Reconnaître `Mot:` n'importe où ferait passer « Note: le reste viendra plus
#: tard », qui est exactement ce que l'on cherche.
PIED = re.compile(r"^(?:[A-Z][A-Za-z-]*|BREAKING CHANGE):\s")

#: Marqueurs qui ont la forme d'un pied sans en être un. Sans cette
#: exception, `TODO: reprendre la table` passerait — vérifié par un test.
JAMAIS_UN_PIED = ("todo:", "fixme:")


def _sans_accent(texte: str) -> str:
    decompose = unicodedata.normalize("NFD", texte)
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn")


def _est_pied(ligne: str) -> bool:
    if ligne.lower().startswith(JAMAIS_UN_PIED):
        return False
    return PIED.match(ligne) is not None


def lignes_lues(message: str) -> list[tuple[int, str]]:
    """Les lignes du message soumises au contrôle, numérotées à partir de 1."""
    retenues: list[tuple[int, str]] = []
    for rang, ligne in enumerate(message.splitlines(), start=1):
        if CISEAUX in ligne:
            break
        if ligne.startswith("#"):
            continue
        retenues.append((rang, ligne))
    # Le bloc de pieds se retire **par la fin**, seul endroit où git les
    # reconnaît. Les lignes vides qui le précèdent partent avec lui.
    while retenues and (not retenues[-1][1].strip() or _est_pied(retenues[-1][1])):
        retenues.pop()
    return retenues


def promesses(message: str) -> list[tuple[int, str, str]]:
    """Rang, ligne et forme fautive, pour chaque engagement sur la suite."""
    trouvees: list[tuple[int, str, str]] = []
    for rang, ligne in lignes_lues(message):
        if (trouve := MOTIF.search(_sans_accent(ligne))) is not None:
            trouvees.append((rang, ligne.strip(), trouve.group(0).strip()))
    return trouvees


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return 0
    message = Path(argv[1]).read_text(encoding="utf-8", errors="replace")

    fautives = promesses(message)
    if not fautives:
        return 0

    detail = "\n".join(f"    ligne {r} : {lg}\n      -> {m!r}" for r, lg, m in fautives)
    print(
        "Un commit decrit ce qui a ete fait, il ne s'engage pas sur la suite.\n\n"
        f"{detail}\n\n"
        "Une clause prospective ne vieillit pas, elle se perime -- et elle dilue\n"
        "le constat utile qui la precede. Retirer la clause, ou la reformuler au\n"
        "present sur ce que le code fait desormais.\n\n"
        "Ce qui reste a faire se note hors du depot, pas dans l'historique.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
