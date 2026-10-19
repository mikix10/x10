"""Les dérogations au typage sont énumérées, et toute nouvelle échoue.

**Ce que ce test protège.** La sûreté des secrets ne tient pas à du code
propre à X10 : elle tient à une **annotation de type** que Pydantic applique.
Une dérogation bien placée — `ignore_errors` dans la configuration mypy, un
`# type: ignore` sur la bonne ligne — la désactive sans que rien ne tombe en
panne, et sans qu'aucun test fonctionnel ne change de couleur.

Un échec ici signale qu'une protection a bougé, et demande une relecture
avant toute régénération.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
REFERENCE = Path(__file__).parent / "derogations.txt"

#: Clés qu'une dérogation mypy a le droit de porter. **Fermé.**
#:
#: `ignore_missing_imports` relâche la seule **résolution d'import** d'une
#: bibliothèque sans marqueur `py.typed`, ce que `CLAUDE.md` autorise
#: nommément. Tout le reste — `ignore_errors`, `disable_error_code`,
#: `strict`, `warn_unused_ignores` — désactiverait des contrôles **sur notre
#: code**, ce que la décision « `mypy --strict` ne se relâche jamais
#: globalement » proscrit.
CLES_AUTORISEES = frozenset({"module", "ignore_missing_imports", "disallow_untyped_calls"})

#: Réglages de `[tool.mypy]` dont la valeur est imposée.
MYPY_IMPOSE = {"strict": True}

#: Un `# type: ignore` doit porter son code d'erreur entre crochets. Un
#: `# type: ignore` nu masque **tout** sur la ligne, y compris une erreur
#: future et sans rapport.
TYPE_IGNORE = re.compile(r"#\s*type:\s*ignore(?P<code>\[[^\]]+\])?")

#: Même raisonnement pour ruff.
NOQA = re.compile(r"#\s*noqa(?P<code>:\s*[A-Z]+[0-9]+(?:\s*,\s*[A-Z]+[0-9]+)*)?")


def _sources() -> list[Path]:
    trouves: list[Path] = []
    for famille in ("packages", "services"):
        for membre in sorted((RACINE / famille).glob("*")):
            trouves += sorted((membre / "src").rglob("*.py"))
    return trouves


def derogations() -> str:
    """Le relevé exhaustif, rendu de façon déterministe."""
    config = tomllib.loads((RACINE / "pyproject.toml").read_text(encoding="utf-8"))
    mypy = config["tool"]["mypy"]

    lignes = [f"mypy.{cle} = {mypy.get(cle)!r}" for cle in sorted(MYPY_IMPOSE)]
    for bloc in mypy.get("overrides", []):
        modules = ", ".join(sorted(bloc.get("module", [])))
        reglages = ", ".join(f"{k}={bloc[k]!r}" for k in sorted(bloc) if k != "module")
        lignes.append(f"mypy.override [{modules}] -> {reglages}")

    for fichier, motif, etiquette in (
        (TYPE_IGNORE, TYPE_IGNORE, "type:ignore"),
        (NOQA, NOQA, "noqa"),
    ):
        del fichier
        for chemin in _sources():
            texte = chemin.read_text(encoding="utf-8")
            for trouve in motif.finditer(texte):
                code = (trouve.group("code") or "").strip(" :[]")
                relatif = chemin.relative_to(RACINE).as_posix()
                lignes.append(f"{etiquette} {relatif} -> {code or '<SANS CODE>'}")

    return "\n".join(sorted(lignes)) + "\n"


def test_les_derogations_sont_celles_de_la_reference():
    """Toute dérogation nouvelle, élargie ou retirée fait échouer la suite.

    Un échec ici n'est pas une faute : c'est le signal qu'une protection a
    bougé. Relire la ligne, vérifier qu'elle est justifiée, puis régénérer
    par `X10_DEROGATIONS_UPDATE=1 uv run pytest workspace-tests`.
    """
    courant = derogations()

    if os.environ.get("X10_DEROGATIONS_UPDATE"):
        REFERENCE.write_text(courant, encoding="utf-8", newline="\n")
        return

    assert REFERENCE.is_file(), f"{REFERENCE.name} est absent."
    assert courant == REFERENCE.read_text(encoding="utf-8"), (
        "Les dérogations au typage ont changé. **Ne pas régénérer sans "
        "comprendre** : c'est ce relevé qui empêche de désactiver "
        "silencieusement la protection des secrets."
    )


def test_aucune_derogation_mypy_ne_porte_une_cle_hors_liste():
    """La liste close, et non la seule référence.

    La référence dirait seulement qu'une valeur a changé ; ceci dit **qu'un
    type de dérogation n'a pas le droit d'exister**. Ajouter
    `ignore_errors = true` sur un module échouerait ici même si quelqu'un
    régénérait la référence sans réfléchir.
    """
    config = tomllib.loads((RACINE / "pyproject.toml").read_text(encoding="utf-8"))
    for bloc in config["tool"]["mypy"].get("overrides", []):
        hors_liste = sorted(set(bloc) - CLES_AUTORISEES)
        assert hors_liste == [], (
            f"Dérogation mypy interdite sur {bloc.get('module')} : {hors_liste}. "
            "Seule la résolution d'import se relâche, jamais un contrôle sur notre code."
        )


def test_le_mode_strict_reste_entier():
    """`strict = true` est un choix durable, pas une position provisoire."""
    config = tomllib.loads((RACINE / "pyproject.toml").read_text(encoding="utf-8"))
    for cle, attendu in MYPY_IMPOSE.items():
        assert config["tool"]["mypy"].get(cle) == attendu, f"mypy.{cle} doit valoir {attendu!r}"


def test_aucun_type_ignore_n_est_nu():
    """Un `# type: ignore` sans code masque **tout** sur sa ligne.

    Il couvrirait donc une erreur future et sans rapport — par exemple le
    jour où l'annotation d'un secret cesserait d'être correcte.
    """
    nus = [
        f"{c.relative_to(RACINE).as_posix()}:{t[: n.start()].count(chr(10)) + 1}"
        for c in _sources()
        if (t := c.read_text(encoding="utf-8"))
        for n in TYPE_IGNORE.finditer(t)
        if not n.group("code")
    ]
    assert nus == [], f"`# type: ignore` sans code d'erreur : {nus}"


def test_aucun_noqa_n_est_nu():
    """Même raisonnement pour ruff."""
    nus = [
        f"{c.relative_to(RACINE).as_posix()}:{t[: n.start()].count(chr(10)) + 1}"
        for c in _sources()
        if (t := c.read_text(encoding="utf-8"))
        for n in NOQA.finditer(t)
        if not n.group("code")
    ]
    assert nus == [], f"`# noqa` sans code de règle : {nus}"
