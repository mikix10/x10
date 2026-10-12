"""Extrait le fil d'une session Claude Code, et y cherche des motifs.

Outil du skill `historique`. Il répond aux questions portant sur l'historique
de nos échanges — qui a proposé quoi, quand une décision a basculé, ce que
j'ai affirmé puis corrigé — en fouillant le transcrit plutôt qu'en se fiant
à la mémoire.

    python extraire.py --sujet contrib-metier
    python extraire.py --sujet revirements --motif "je me suis tromp" --motif "j'avais tort"

Les sorties vont **hors du dépôt**, dans un dossier daté. Rien de ce qui en
sort n'est publiable en l'état : un transcrit contient tout ce qui a été dit.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from datetime import date
from pathlib import Path

ICI = Path(__file__).resolve()
#: Racine du dépôt, déduite de l'emplacement du skill : `.claude/skills/<nom>/`.
DEPOT = ICI.parents[3]

#: Motifs par défaut : les tournures par lesquelles l'assistant reconnaît un
#: apport, une correction ou une anticipation. Volontairement larges — on
#: relit, on ne compte pas.
MOTIFS_DEFAUT = {
    "correction": [
        r"vous av(ez|iez) raison",
        r"j'(ai eu|avais) tort",
        r"je me suis tromp",
        r"m'(avait|a) échappé",
        r"je n'avais pas vu",
        r"erreur de ma part",
        r"j'ai omis",
        r"trop absolu",
    ],
    "apport": [
        r"votre (remarque|question|proposition|point|intuition|formulation|exemple)",
        r"vous (m'avez|avez) (dit|signalé|pointé|indiqué|rappelé)",
        r"ce que vous (décrivez|soulevez|proposez)",
        r"vous (soulevez|touchez|anticipez)",
        r"sans votre",
        r"pas bête",
    ],
    "anticipation": [
        r"je n'aurais pas (vu|trouvé|pensé|ouvert)",
        r"que je n'avais pas (anticipé|vu|prévu)",
        r"heureusement que",
    ],
    "contradiction": [
        r"je vous contredis",
        r"je ne suis pas d'accord",
        r"c'est à nuancer",
    ],
}


def transcrit(session: Path | None) -> Path:
    """Localise le transcrit JSONL de la session en cours.

    Jamais de chemin nominatif en dur : il se déduit du répertoire personnel
    et du chemin du dépôt, dont Claude Code tire le nom de dossier de projet
    en remplaçant les séparateurs par des tirets.
    """
    if session is not None:
        return session
    #: Chaque séparateur est remplacé **individuellement**, et non par série :
    #: `D:\x10` donne `d--x10`, les deux tirets venant du `:` puis du `\`.
    #: Les fusionner donnerait `d-x10`, qui n'existe pas.
    slug = re.sub(r"[:\\/]", "-", str(DEPOT)).lower().rstrip("-")
    racine = Path.home() / ".claude" / "projects"
    projets = racine / slug
    if not projets.is_dir():
        voisins = sorted(p.name for p in racine.iterdir() if p.is_dir()) if racine.is_dir() else []
        raise SystemExit(
            f"Aucun dossier de projet en {projets}.\n"
            f"Dossiers presents : {', '.join(voisins) or 'aucun'}.\n"
            "Passer --session avec le chemin du transcrit."
        )
    fichiers = sorted(projets.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not fichiers:
        raise SystemExit(f"Aucun transcrit dans {projets}.")
    return fichiers[0]


def racine_sortie() -> Path:
    """Dossier de travail hors dépôt, surchargeable par `X10_HORS_DEPOT`."""
    surcharge = os.environ.get("X10_HORS_DEPOT")
    if surcharge:
        return Path(surcharge)
    return DEPOT.parent / f"{DEPOT.name}-hors-depot" / "info"


def _texte(message: dict) -> str:
    """Concatène les blocs texte, en ignorant outils et raisonnement.

    Le contenu est tantôt une chaîne, tantôt une liste de blocs typés
    `text`, `tool_use`, `tool_result` ou `thinking`. Seul le premier compte.
    """
    contenu = message.get("content")
    if isinstance(contenu, str):
        return contenu
    if not isinstance(contenu, list):
        return ""
    blocs = [b.get("text", "") for b in contenu if isinstance(b, dict) and b.get("type") == "text"]
    return "\n".join(b for b in blocs if b)


def lire_tours(source: Path) -> list[tuple[str, str]]:
    """Rend la suite (rôle, texte) des tours de parole réels.

    **Les retours d'outil arrivent en `role="user"`** : sans filtre, ils
    passeraient pour des propos du mainteneur et fausseraient tout amont.
    """
    tours: list[tuple[str, str]] = []
    with source.open(encoding="utf-8") as flux:
        for ligne in flux:
            ligne = ligne.strip()
            if not ligne:
                continue
            try:
                enregistre = json.loads(ligne)
            except json.JSONDecodeError:
                continue
            message = enregistre.get("message")
            if not isinstance(message, dict) or message.get("role") not in ("user", "assistant"):
                continue
            texte = _texte(message).strip()
            if not texte:
                continue
            if message["role"] == "user" and texte.startswith(
                ("<system-reminder>", "Result of calling", "<task-notification>")
            ):
                continue
            tours.append((message["role"], texte))
    return tours


def _sans_accent(valeur: str) -> str:
    plat = unicodedata.normalize("NFKD", valeur)
    return "".join(c for c in plat if not unicodedata.combining(c))


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--sujet", required=True, help="suffixe du dossier daté, en kebab-case")
    analyseur.add_argument("--session", type=Path, help="transcrit JSONL, sinon le plus récent")
    analyseur.add_argument(
        "--motif",
        action="append",
        default=[],
        help="motif supplémentaire ; répétable. Classé en « demande »",
    )
    analyseur.add_argument("--role", choices=("assistant", "user", "tous"), default="assistant")
    analyseur.add_argument(
        "--simulation",
        action="store_true",
        help="résout source et destination, n'écrit rien. À soumettre avant de peupler",
    )
    options = analyseur.parse_args()

    source = transcrit(options.session)
    sortie = racine_sortie() / f"{date.today():%Y%m%d}_{options.sujet}"

    # L'emplacement et le nom du dossier se **confirment avant** d'être créés :
    # ces dossiers s'accumulent, et un nom choisi par l'outil se retrouve mal.
    if options.simulation:
        print(f"source      : {source}  ({source.stat().st_size // 1_048_576} Mio)")
        print(f"destination : {sortie}")
        print(f"existe deja : {'oui' if sortie.exists() else 'non'}")
        print("produirait  : fil.md, releve-brut.json, releve-trie.md")
        print("\nRien n'a ete cree. Soumettre ce chemin, puis relancer sans --simulation.")
        return 0

    sortie.mkdir(parents=True, exist_ok=True)

    tours = lire_tours(source)
    print(f"source  : {source}  ({source.stat().st_size // 1_048_576} Mio)")
    print(f"sortie  : {sortie}")
    print(f"tours   : {len(tours)}")

    # --- 1. Le fil lisible, toujours produit ---------------------------------
    fil = sortie / "fil.md"
    with fil.open("w", encoding="utf-8") as cible:
        cible.write(f"# Fil de la session — extrait le {date.today():%d/%m/%Y}\n\n")
        cible.write(f"Source : `{source.name}`, {len(tours)} tours de parole.\n")
        cible.write("Appels d'outils et raisonnement retirés ; seul le texte échangé subsiste.\n")
        for role, texte in tours:
            cible.write(f"\n## {'Mainteneur' if role == 'user' else 'Assistant'}\n\n{texte}\n")
    print(f"fil     : {fil.stat().st_size // 1024} Kio")

    # --- 2. Le relevé --------------------------------------------------------
    motifs = {k: list(v) for k, v in MOTIFS_DEFAUT.items()}
    if options.motif:
        motifs = {"demande": options.motif}
    compiles = {k: [re.compile(m, re.IGNORECASE) for m in v] for k, v in motifs.items()}

    releves: list[dict[str, str]] = []
    for index, (role, texte) in enumerate(tours):
        if options.role != "tous" and role != options.role:
            continue
        for phrase in re.split(r"(?<=[.!?])\s+", texte):
            for categorie, regexps in compiles.items():
                if any(r.search(phrase) for r in regexps):
                    amont = next(
                        (
                            " ".join(tours[p][1].split())[:240]
                            for p in range(index - 1, -1, -1)
                            if tours[p][0] == "user"
                        ),
                        "",
                    )
                    releves.append(
                        {
                            "categorie": categorie,
                            "phrase": " ".join(phrase.split())[:400],
                            "amont": amont,
                        }
                    )
                    break

    (sortie / "releve-brut.json").write_text(
        json.dumps(releves, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    trie = sortie / "releve-trie.md"
    with trie.open("w", encoding="utf-8") as cible:
        cible.write(f"# Relevé — {len(releves)} occurrences\n")
        for categorie in motifs:
            items = [x for x in releves if x["categorie"] == categorie]
            cible.write(f"\n\n## {categorie} — {len(items)}\n")
            vus: set[str] = set()
            for x in items:
                if x["phrase"][:60] in vus:
                    continue
                vus.add(x["phrase"][:60])
                cible.write(f"\n---\n\n**Amont** : {x['amont']}\n\n**Dit** : {x['phrase']}\n")

    print(f"relevé  : {len(releves)} occurrences")
    for categorie in motifs:
        print(f"  {categorie:15} {sum(1 for r in releves if r['categorie'] == categorie)}")
    # Les accents ne passent pas sur une console cp1252 : on aplatit l'affichage,
    # jamais les fichiers, qui restent en UTF-8.
    print(_sans_accent(f"trie    : {trie}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
