"""Ce qu'un paquet publiable n'a pas le droit de faire — deux invariants.

**Ces deux garanties étaient déclarées acquises et ne l'étaient pas.** Relevé
le 23/10/2026 :

* `CLAUDE.md` écrit « Aucun fichier de `packages/` ne doit importer
  `x10_client` ni `x10_api` — **un test le vérifie** », et `PLAN.md` répète
  « et un test l'exige ». **Ce test n'existait pas.** La propriété était
  vraie en fait, et disciplinaire seulement ;
* `CLAUDE.md` justifie la règle de couche en disant qu'un test de paquet
  déplacé dans `services/` ferait dépendre la couverture d'un paquet de ce
  membre, « **soit la règle à l'envers** ». Or
  `test_aucun_paquet_ne_lit_l_environnement` vivait dans
  `services/x10-client/tests/`, et `pytest packages/` ne l'exécutait pas.

Les deux portent sur **tous** les membres, donc leur place est ici et non
dans l'un d'eux — même raison que le lexique public. Et comme lui, ils
n'importent rien : ils lisent des fichiers, donc ils tournent sans
installation.
"""

from __future__ import annotations

import ast
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
PAQUETS = RACINE / "packages"

#: Les membres de `services/`. Un paquet qui en importerait un cesserait
#: d'être validable seul par qui l'installe.
SERVICES = ("x10_client", "x10_api")

#: Ce qui trahit une lecture de l'environnement. `os.environ` et `getenv`
#: couvrent les deux formes, l'indexation et l'appel.
LECTURES_D_ENVIRONNEMENT = ("os.environ", "getenv")


def _sources_des_paquets() -> list[Path]:
    """Les sources publiées, à l'exclusion des tests et des caches."""
    return [
        chemin
        for chemin in sorted(PAQUETS.rglob("src/**/*.py"))
        if "__pycache__" not in chemin.parts
    ]


def _modules_importes(chemin: Path) -> set[str]:
    """Les modules de tête importés par un fichier, par analyse syntaxique.

    L'AST plutôt qu'une recherche de texte : `x10_client` cité dans une
    docstring ou un commentaire n'est pas un import, et le confondre
    produirait un échec que personne ne saurait lire.
    """
    arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
    tetes: set[str] = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            tetes.update(alias.name.split(".")[0] for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module and noeud.level == 0:
            tetes.add(noeud.module.split(".")[0])
    return tetes


def test_aucun_paquet_n_importe_un_membre_de_services():
    """`services/` consomme, il n'est jamais consommé par un paquet.

    La conséquence pratique est que les paquets restent **validables seuls**
    par qui les installe. Un import descendant ferait dépendre la suite d'un
    paquet d'un membre qui n'est pas publié avec lui.
    """
    fautifs = [
        f"{chemin.relative_to(RACINE).as_posix()} importe {sorted(interdits)}"
        for chemin in _sources_des_paquets()
        if (interdits := _modules_importes(chemin) & set(SERVICES))
    ]
    assert fautifs == [], "un paquet importe un service : " + "; ".join(fautifs)


def test_aucun_paquet_ne_lit_l_environnement():
    """**Le client résout, le connecteur reçoit.** Un paquet qui lirait
    l'environnement détiendrait un secret, ce que la décision « X10 ne porte
    aucun secret » interdit.

    Vérifié le 16/10/2026 : zéro occurrence. Déplacé ici le 23/10/2026, parce
    qu'une garantie sur les paquets qui ne tourne qu'avec la suite d'un
    service disparaît le jour où l'on ne construit que les paquets.
    """
    fautifs = [
        chemin.relative_to(PAQUETS).as_posix()
        for chemin in _sources_des_paquets()
        if any(motif in chemin.read_text(encoding="utf-8") for motif in LECTURES_D_ENVIRONNEMENT)
    ]
    assert fautifs == [], f"un paquet lit l'environnement : {fautifs}"


def test_le_balayage_voit_reellement_les_sources():
    """Un balayage qui ne trouve rien passe au vert pour la mauvaise raison.

    Sans ce garde-fou, une arborescence renommée rendrait les deux tests
    ci-dessus silencieusement inopérants — le mode d'échec le plus coûteux
    d'un test de propriété.
    """
    sources = _sources_des_paquets()
    # Onze sources au 23/10/2026 ; le seuil veut détecter un balayage vide,
    # pas épingler un compte qui bougera à chaque module ajouté.
    assert len(sources) >= 8, f"{len(sources)} source(s) balayée(s) : l'arborescence a bougé"
    paquets = {chemin.relative_to(PAQUETS).parts[0] for chemin in sources}
    assert paquets == {"x10-catalog", "x10-connectors", "x10-models", "x10-storage"}, paquets
