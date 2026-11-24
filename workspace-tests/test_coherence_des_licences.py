"""La licence d'une source est déclarée à deux endroits — ils doivent s'accorder.

**Le défaut que ce contrôle ferme, mesuré le 24/11/2026.** Un connecteur
porte sa licence en constante de module — `SOURCE_LICENSE` — et le catalogue
la porte en donnée, sur chaque `Distribution`. **Ce sont deux déclarations
indépendantes du même fait, et rien ne vérifiait qu'elles s'accordent.** La
valeur qui finit dans le fichier produit vient de la première ; celle qu'un
consommateur lit au catalogue vient de la seconde. Deux réponses possibles à
« sous quelle licence est cette donnée » est une de trop.

**Pourquoi un contrôle et non une source unique.** Faire lire le catalogue au
connecteur violerait la règle de dépendance — `x10-connectors` ignore
`x10-catalog`, et doit continuer. Faire lire le connecteur au catalogue
l'inverserait. Le seul endroit qui voit les deux est ici, et c'est la raison
d'être de ce dossier. **La duplication subsiste donc, mais elle est gardée.**

**La table est tenue à la main, et c'est délibéré.** Deux sources ne
justifient pas une mécanique de découverte : elle serait fausse sur un
échantillon de deux, et le dépôt refuse ailleurs exactement cela. Une
troisième source ajoute une ligne.

Comme les autres contrôles de ce dossier, il **n'importe rien** : il lit les
sources par analyse syntaxique et le catalogue en JSON, donc il tourne sans
installation.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CONNECTEURS = RACINE / "packages" / "x10-connectors" / "src" / "x10_connectors"
CATALOGUE = RACINE / "packages" / "x10-catalog" / "src" / "x10_catalog" / "data"

#: Le connecteur qui sert chaque famille de jeux, et le préfixe d'identifiant
#: sous lequel le catalogue les range. Deux lignes, tenues à la main.
PRODUCTEURS = {
    "meteofrance_pnt.py": "meteofrance-",
    "ecmwf_ifs.py": "ecmwf-",
}

#: Le nom de la constante que chaque connecteur expose.
CONSTANTE = "SOURCE_LICENSE"


def _licence_declaree(module: Path) -> str:
    """La valeur de `SOURCE_LICENSE`, lue sans importer le module.

    Importer exigerait la pile du domaine ; l'analyse syntaxique ne demande
    rien et ne peut rien exécuter.
    """
    arbre = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    for noeud in arbre.body:
        if not isinstance(noeud, ast.Assign):
            continue
        for cible in noeud.targets:
            if isinstance(cible, ast.Name) and cible.id == CONSTANTE:
                valeur = noeud.value
                assert isinstance(valeur, ast.Constant), (
                    f"{module.name} : {CONSTANTE} doit être une chaîne littérale, "
                    f"sinon ce contrôle ne peut plus la lire."
                )
                assert isinstance(valeur.value, str)
                return valeur.value
    raise AssertionError(f"{module.name} ne déclare pas {CONSTANTE}.")


def _entrees_du_catalogue() -> list[tuple[str, str, str]]:
    """Chaque distribution, par `(identifiant du jeu, origine, licence)`."""
    entrees: list[tuple[str, str, str]] = []
    for fichier in sorted(CATALOGUE.glob("*.json")):
        contenu = json.loads(fichier.read_text(encoding="utf-8"))
        for entree in contenu["entries"]:
            identifiant = entree["dataset"]["identifier"]
            for distribution in entree["distributions"]:
                entrees.append((identifiant, distribution["origin"], distribution["license"]))
    return entrees


def test_chaque_connecteur_declare_une_licence() -> None:
    """Un connecteur sans licence déclarée émettrait une sortie sans licence."""
    for module in PRODUCTEURS:
        chemin = CONNECTEURS / module
        assert chemin.exists(), f"{module} a disparu : la table est à reprendre."
        assert _licence_declaree(chemin), f"{module} déclare une licence vide."


def test_le_catalogue_declare_la_meme_licence_que_le_connecteur() -> None:
    """Deux déclarations du même fait, et elles ne peuvent pas diverger."""
    licences = {
        prefixe: _licence_declaree(CONNECTEURS / module) for module, prefixe in PRODUCTEURS.items()
    }

    comparaisons = 0
    for identifiant, origine, licence in _entrees_du_catalogue():
        for prefixe, attendue in licences.items():
            if not identifiant.startswith(prefixe):
                continue
            comparaisons += 1
            assert licence == attendue, (
                f"{identifiant} via {origine} : le catalogue dit {licence!r}, "
                f"le connecteur dit {attendue!r}. Une des deux déclarations "
                f"est fausse, et c'est celle du connecteur qui part dans le "
                f"fichier produit."
            )

    # **Un contrôle qui ne compare rien passe.** Le catalogue peut perdre une
    # entrée, ou un préfixe changer, sans que rien ne le signale — c'est le
    # mode de ruine que le dépôt a déjà mesuré sur un test supprimé.
    assert comparaisons, (
        "Aucune distribution n'a été comparée : soit le catalogue est vide, "
        "soit les préfixes de PRODUCTEURS ne correspondent plus aux "
        "identifiants de jeux."
    )
