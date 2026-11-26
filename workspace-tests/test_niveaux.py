"""Le dépôt vit à trois niveaux, et rien des deux autres n'entre ici.

**Les trois niveaux.** Ce dépôt est **public**. À côté vivent un dépôt
**privé**, qui porte ce que le public ne peut pas porter, et un **hors
dépôt**, qui ne relève d'aucun des deux — transcrits de session, relevés,
documents reçus. La règle est simple et elle n'a pas d'exception : *rien du
deuxième ni du troisième n'entre dans le premier.*

**Pourquoi un test et pas seulement une ligne de `.gitignore`.** Mesuré le
26/11/2026 : `git add -A` a indexé 6 465 lignes d'un dossier voisin nommé
`docs-local-hors-depot/`. La liste d'exclusion nommait `docs-local/`, le
voisin portait un autre nom, et **rien ne l'a vu** — c'est un contrôle
manuel qui l'a arrêté. Une liste d'exclusion dit ce qu'on a pensé à
exclure ; elle ne dit rien de ce qu'on n'a pas prévu.

Ce test ferme donc la **classe** : un chemin suivi dont un segment porte un
marqueur de niveau fait échouer la suite, quelle que soit la raison pour
laquelle `.gitignore` l'a laissé passer. C'est l'idiome du dépôt — *un
contrôle qui s'exécute vaut mieux qu'une consigne qui se lit*.

**Ce que ce test ne garantit pas**, et il faut le dire : il voit le **nom**
d'un chemin, jamais son contenu. Un document local rangé sous un nom neutre
lui échappe. C'est le contrôle de termes proscrits qui couvre cette
moitié-là, et les deux sont nécessaires.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent

#: Les marqueurs de niveau. Un segment de chemin qui en contient un désigne
#: du contenu local, privé, ou hors dépôt.
#:
#: `-local` et non `local` : fermer sur le mot nu interdirait un jour un
#: `localisation.py` parfaitement légitime, et un contrôle qui crie à tort
#: s'apprend à contourner. Le trait d'union est la convention de nommage
#: réellement employée.
MARQUEURS = ("hors-depot", "-local", "_priv")

#: Les noms de fichiers qui ne se versionnent jamais, marqueur ou non.
NOMS_INTERDITS = (".denylist", "CLAUDE.local.md")


def _fichiers_suivis() -> list[str]:
    rendu = subprocess.run(
        ["git", "ls-files"],
        cwd=RACINE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if rendu.returncode != 0:
        pytest.skip("hors d'un arbre git")
    return [ligne for ligne in rendu.stdout.splitlines() if ligne.strip()]


def test_aucun_chemin_suivi_ne_porte_un_marqueur_de_niveau() -> None:
    """C'est la garantie centrale, et elle porte sur la classe entière."""
    fautifs = [
        chemin
        for chemin in _fichiers_suivis()
        for segment in chemin.split("/")
        if any(marqueur in segment.lower() for marqueur in MARQUEURS)
    ]

    assert not fautifs, (
        "Ces chemins sont suivis par git et portent un marqueur de niveau "
        f"local, prive ou hors depot : {sorted(set(fautifs))}. "
        "Les retirer de l'index, et verifier que `.gitignore` ferme bien la "
        "classe et pas seulement le cas."
    )


def test_aucun_nom_interdit_n_est_suivi() -> None:
    """Deux fichiers qui n'ont pas de marqueur et ne doivent jamais sortir.

    `.denylist` protège des tiers : l'y versionner publierait précisément ce
    qu'il protège. `CLAUDE.local.md` porte l'identité du mainteneur et les
    chemins de son poste.
    """
    suivis = {Path(chemin).name for chemin in _fichiers_suivis()}
    fautifs = sorted(suivis & set(NOMS_INTERDITS))

    assert not fautifs, f"Ces fichiers ne se versionnent jamais : {fautifs}."


@pytest.mark.parametrize(
    "chemin",
    [
        "docs-local/une-note.md",
        "docs-local-hors-depot/plans/un-plan.md",
        "notes-local/brouillon.md",
        "x10_priv/interfaces/contrat.md",
        "transcrits-hors-depot/session.md",
        "CLAUDE.local.md",
        ".denylist",
    ],
)
def test_gitignore_ferme_la_classe(chemin: str) -> None:
    """`.gitignore` doit refuser ces chemins **avant** que le test ci-dessus
    n'ait à les attraper.

    Le second cas est celui du 26/11/2026, et il est ici nommément pour que
    la correction ne se reperde pas : c'est un dossier **voisin** de celui
    que la liste nommait.
    """
    rendu = subprocess.run(
        ["git", "check-ignore", "-q", chemin],
        cwd=RACINE,
        capture_output=True,
        check=False,
    )
    assert rendu.returncode == 0, (
        f"`{chemin}` n'est pas ignore par .gitignore. La classe des chemins "
        "locaux doit etre fermee par marqueur, pas enumeree nom par nom."
    )


@pytest.mark.parametrize(
    "chemin",
    ["AGENTS.md", "docs/vocabulaire.md", "packages/x10-models/pyproject.toml"],
)
def test_le_motif_ne_deborde_pas(chemin: str) -> None:
    """La contrepartie, et elle vaut d'être testée.

    Un motif trop large exclurait du code légitime, et la panne serait
    silencieuse : le fichier disparaîtrait simplement de l'index.
    """
    rendu = subprocess.run(
        ["git", "check-ignore", "-q", chemin],
        cwd=RACINE,
        capture_output=True,
        check=False,
    )
    assert rendu.returncode != 0, f"`{chemin}` est legitime et ne doit pas etre ignore."
