"""Le vocabulaire public du dépôt, figé dans un fichier relisible.

**Ce test ne juge pas la langue, et c'est délibéré.** Une liste de mots
français ne trouverait que ce qu'on y aurait déjà mis, et le prochain mot
français sera un mot nouveau. Ce qu'il garantit est plus modeste et plus
sûr : **aucun ajout au vocabulaire public ne passe sans être vu**. Ajouter
un champ produit une ligne de `git diff` qu'un relecteur lit — et c'est lui,
pas une liste, qui voit qu'elle est française.

C'est exactement la mécanique du contrat de sortie de `x10-connectors` :
une référence versionnée, relisible, qui ne décide de rien et rend la dérive
visible. Elle existe ici parce que le dépôt s'est fait prendre une fois —
`x10-client` est né avec 18 de ses 25 champs sérialisés en français, et
aucune porte de qualité ne l'a vu.

**Portée : ce qu'un tiers lit.** Les champs de modèles et de dataclasses,
les **champs calculés** — un `@computed_field` est sérialisé, donc c'est une
clé comme une autre —, les membres d'énumération avec leur valeur, et les
entrées d'`__all__`. Pas les variables locales, qui ne franchissent aucune
frontière.

**Ce test vit hors des paquets**, parce qu'il porte sur tous les membres :
le placer dans l'un d'eux ferait dépendre sa suite des sources des autres, et
un paquet doit rester validable seul. Il ne fait qu'analyser des fichiers —
rien n'est importé, donc il tourne même sans installation.

Le dossier s'appelle `workspace-tests/` et non `tests/` : chaque membre a
déjà son `tests/`, et un `tests/` à la racine dirait « les tests » au lieu de
dire sa portée. `workspace` est le mot que le dépôt emploie partout ailleurs
pour ce qui est transverse.

Régénérer après un ajout délibéré :

```bash
X10_LEXIQUE_UPDATE=1 uv run pytest workspace-tests/test_lexique_public.py
```
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
REFERENCE = Path(__file__).parent / "lexique-public.txt"

#: Attributs de classe qui sont de la mécanique et non du vocabulaire.
IGNORES = frozenset({"model_config", "__all__"})


def _sources() -> list[Path]:
    """Tous les modules des `src/`, membre par membre, dans un ordre stable."""
    trouves: list[Path] = []
    for famille in ("packages", "services"):
        for membre in sorted((RACINE / famille).glob("*")):
            trouves += sorted((membre / "src").rglob("*.py"))
    return trouves


def _module_nom(chemin: Path) -> str:
    """`x10_connectors.base` depuis le chemin du fichier."""
    parties = chemin.relative_to(RACINE).parts
    debut = parties.index("src") + 1
    parties = parties[debut:]
    if parties[-1] == "__init__.py":
        parties = parties[:-1]
    else:
        parties = (*parties[:-1], parties[-1].removesuffix(".py"))
    return ".".join(parties)


def _nom_decorateur(noeud: ast.expr) -> str:
    """Le nom d'un décorateur, qu'il soit nu, appelé ou qualifié."""
    if isinstance(noeud, ast.Call):
        noeud = noeud.func
    if isinstance(noeud, ast.Attribute):
        return noeud.attr
    return noeud.id if isinstance(noeud, ast.Name) else ""


def _entrees(chemin: Path) -> list[str]:
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    module = _module_nom(chemin)
    lignes: list[str] = []

    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.ClassDef):
            enumeration = any(
                isinstance(b, ast.Name) and b.id.endswith("Enum") for b in noeud.bases
            )
            for corps in noeud.body:
                # Champ annoté : modèle Pydantic ou dataclass.
                if (
                    isinstance(corps, ast.AnnAssign)
                    and isinstance(corps.target, ast.Name)
                    and corps.target.id not in IGNORES
                ):
                    lignes.append(f"{module}.{noeud.name}.{corps.target.id}")
                # Membre d'énumération : le nom **et** la valeur émise.
                if enumeration and isinstance(corps, ast.Assign):
                    for cible in corps.targets:
                        if not isinstance(cible, ast.Name) or cible.id in IGNORES:
                            continue
                        valeur = (
                            repr(corps.value.value)
                            if isinstance(corps.value, ast.Constant)
                            else "<calculée>"
                        )
                        lignes.append(f"{module}.{noeud.name}.{cible.id} = {valeur}")
                # Champ calculé : `@computed_field` **est sérialisé**, donc
                # c'est une clé que lit un tiers, au même titre qu'un champ
                # déclaré. L'omettre le ferait échapper à la relecture —
                # exactement le trou que ce fichier existe pour fermer, et
                # trouvé en l'exerçant le 16/10/2026.
                if isinstance(corps, ast.FunctionDef) and any(
                    _nom_decorateur(d) == "computed_field" for d in corps.decorator_list
                ):
                    lignes.append(f"{module}.{noeud.name}.{corps.name}")

        if (
            isinstance(noeud, ast.Assign)
            and any(isinstance(c, ast.Name) and c.id == "__all__" for c in noeud.targets)
            and isinstance(noeud.value, (ast.List, ast.Tuple))
        ):
            for element in noeud.value.elts:
                if isinstance(element, ast.Constant) and isinstance(element.value, str):
                    lignes.append(f"{module}.__all__: {element.value}")

    return lignes


def lexique() -> str:
    """Rendu déterministe : trié, un terme par ligne, fin de ligne POSIX."""
    termes: set[str] = set()
    for chemin in _sources():
        termes.update(_entrees(chemin))
    return "\n".join(sorted(termes)) + "\n"


def test_le_vocabulaire_public_est_celui_de_la_reference():
    """Toute entrée nouvelle au vocabulaire public passe par une relecture.

    Un échec ici n'est pas une faute : c'est le signal qu'un terme s'ajoute
    ou disparaît. Relire la ligne, vérifier qu'elle est en anglais, puis
    régénérer.
    """
    courant = lexique()

    if os.environ.get("X10_LEXIQUE_UPDATE"):
        REFERENCE.write_text(courant, encoding="utf-8", newline="\n")
        return

    assert REFERENCE.is_file(), (
        f"{REFERENCE.name} est absent. Le régénérer par "
        "`X10_LEXIQUE_UPDATE=1 uv run pytest workspace-tests/test_lexique_public.py`."
    )
    attendu = REFERENCE.read_text(encoding="utf-8")
    assert courant == attendu, (
        "Le vocabulaire public a changé. Relire les lignes ajoutées ou "
        "retirées — un terme qu'un tiers lit doit être en anglais —, puis "
        "régénérer par `X10_LEXIQUE_UPDATE=1 uv run pytest "
        "workspace-tests/test_lexique_public.py`."
    )


def test_la_reference_couvre_les_six_familles_de_termes():
    """Garde-fou de l'extracteur lui-même.

    Un relevé qui cesserait silencieusement de voir une famille rendrait le
    fichier stable pour une mauvaise raison, et la barrière deviendrait
    décorative sans que rien ne le signale.
    """
    termes = lexique()
    assert "x10_models.Retrieval.license" in termes, "champ de modèle Pydantic"
    assert "x10_storage.StorageRecord.key" in termes, "champ de dataclass"
    assert "x10_client.report.Verdict.PARTIAL = 'partial'" in termes, "valeur d'énumération"
    assert "x10_connectors.__all__: ConnectorResult" in termes, "entrée d'__all__"
    assert "x10_connectors.base.ConnectorResult.message" in termes, "champ d'un sous-module"
    assert "x10_client.report.PipelineReport.verdict" in termes, "champ calculé"
