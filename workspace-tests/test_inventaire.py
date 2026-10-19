"""L'inventaire des tests, pour qu'une disparition se voie.

**Le problème que cela traite.** Nos garanties reposent sur des tests —
qu'un secret ne sorte pas, qu'aucune dérogation de typage ne s'ajoute, que
le vocabulaire public ne dérive pas. Un test supprimé emporte donc sa
garantie avec lui, **et la suite reste verte** : rien ne signale l'absence de
ce qui n'existe plus.

C'est la régression à l'infini du « qui garde les gardiens ». Elle n'a pas de
sortie parfaite, mais deux marches successives :

1. **Ici** : la liste des tests est une référence commitée, donc une
   suppression ou un renommage devient **une ligne de diff** à relire.
2. **En intégration continue** : le job `Tests de la base` rejoue les tests
   de `main` contre le code proposé, de sorte qu'un test **vidé de sa
   substance** sans changer de nom soit attrapé lui aussi.

Le premier est immédiat et sans dépendance ; le second voit ce que le premier
ne voit pas. Aucun des deux n'empêche quoi que ce soit : ils rendent visible.

"""

from __future__ import annotations

import ast
import os
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
REFERENCE = Path(__file__).parent / "tests-inventaire.txt"


def _fichiers() -> list[Path]:
    """Tous les fichiers de tests du dépôt, dans un ordre stable."""
    trouves: list[Path] = []
    for famille in ("packages", "services"):
        for membre in sorted((RACINE / famille).glob("*")):
            trouves += sorted((membre / "tests").rglob("test_*.py"))
    trouves += sorted((RACINE / "workspace-tests").glob("test_*.py"))
    return [f for f in trouves if "__pycache__" not in f.parts]


def inventaire() -> str:
    """Un test par ligne, qualifié par son fichier.

    Les paramétrages ne sont pas dépliés : c'est la **fonction** qui porte le
    comportement, et une liste de cas changerait à chaque ajout de donnée
    sans qu'aucune garantie ne bouge.
    """
    lignes: list[str] = []
    for chemin in _fichiers():
        relatif = chemin.relative_to(RACINE).as_posix()
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)) and noeud.name.startswith(
                "test_"
            ):
                lignes.append(f"{relatif}::{noeud.name}")
    return "\n".join(sorted(lignes)) + "\n"


def test_l_inventaire_des_tests_est_celui_de_la_reference():
    """Un test retiré ou renommé fait échouer la suite.

    Un échec ici n'est pas une faute : c'est le signal qu'une garantie a
    changé de nom ou disparu. Relire les lignes retirées, vérifier que la
    disparition est voulue, puis régénérer par
    `X10_INVENTAIRE_UPDATE=1 uv run pytest workspace-tests`.
    """
    courant = inventaire()

    if os.environ.get("X10_INVENTAIRE_UPDATE"):
        REFERENCE.write_text(courant, encoding="utf-8", newline="\n")
        return

    assert REFERENCE.is_file(), f"{REFERENCE.name} est absent."
    assert courant == REFERENCE.read_text(encoding="utf-8"), (
        "L'inventaire des tests a changé. **Lire les lignes retirées avant de "
        "régénérer** : un test supprimé emporte sa garantie, et la suite reste "
        "verte sans lui."
    )


def test_les_tests_qui_gardent_les_garanties_sont_presents():
    """Garde-fou nommé, par-dessus la référence.

    La référence dirait qu'une ligne a disparu ; ceci dit **que ces
    garanties-là ne peuvent pas disparaître**. Les régénérer sans réfléchir
    ne suffirait donc pas à les faire sauter.

    La liste est courte et volontairement nominative : elle ne couvre que ce
    dont la disparition serait silencieuse **et** grave.
    """
    attendus = {
        # Les secrets ne sortent par aucun chemin.
        "test_aucune_surface_publique_ne_laisse_passer_la_valeur",
        "test_muter_le_dictionnaire_interne_ne_fait_rien_fuir",
        "test_une_erreur_de_validation_ne_montre_pas_l_entree",
        "test_une_chaine_nue_est_coercee_en_secret",
        # Les derogations de typage ne s'ajoutent pas en silence.
        "test_aucune_derogation_mypy_ne_porte_une_cle_hors_liste",
        "test_le_mode_strict_reste_entier",
        "test_aucun_type_ignore_n_est_nu",
        # Les regles de dependance et de vocabulaire.
        "test_aucun_paquet_ne_lit_l_environnement",
        "test_le_vocabulaire_public_est_celui_de_la_reference",
        "test_le_client_n_est_importe_par_aucun_paquet",
    }
    presents = {ligne.split("::")[-1] for ligne in inventaire().splitlines()}
    manquants = sorted(attendus - presents)
    assert manquants == [], (
        f"Garanties disparues : {manquants}. Ces tests protègent les secrets, le "
        "typage ou les règles de dépendance ; les retirer demande une décision "
        "explicite, pas un renommage."
    )
