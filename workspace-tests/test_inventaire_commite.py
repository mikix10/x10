"""L'inventaire commité se charge, et il dit d'où il vient.

**Pourquoi ce test.** Mesuré le 26/11/2026 : `meteofrance.json` est la seule
référence que le dépôt qualifie de **dérivée** — « l'inventaire est dérivé
des fichiers, jamais des descriptifs » — et **aucun test ne la régénérait ni
ne la vérifiait**. Les cinq autres références engendrées ont chacune leur
test ; celle-ci était tenue à la main, exactement ce que le critère C5
existe pour empêcher.

**Ce test ne la régénère pas, et il faut dire pourquoi.** La régénérer
demande de retélécharger six granules chez le producteur : c'est un test
`network`, et il dépense du crédit chez un tiers à chaque exécution. Ce qui
se vérifie **hors ligne**, c'est que le fichier se charge dans le modèle du
domaine et qu'il **porte sa provenance** — ce qui transforme une
affirmation de prose en propriété tenue.

**Ce qu'il ne garantit donc pas** : que l'inventaire décrive encore ce que
le producteur sert aujourd'hui. Seule une re-dérivation le dirait, et sa
date est dans le fichier.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from x10_catalog import Registry

INVENTAIRE = (
    Path(__file__).resolve().parent.parent
    / "packages"
    / "x10-catalog"
    / "src"
    / "x10_catalog"
    / "data"
    / "meteofrance.json"
)


def test_l_inventaire_commite_se_charge_dans_le_registre() -> None:
    """Il doit être lisible par le code qui l'expédie, pas seulement valide.

    Un JSON bien formé mais que `Registry` refuserait serait un fichier mort
    embarqué dans une roue, et personne ne s'en apercevrait : aucun module de
    `src/` ne le charge aujourd'hui.
    """
    registre = Registry.from_file(INVENTAIRE)

    assert registre.entries, "l'inventaire commite ne porte aucune entree"


def test_chaque_entree_dit_d_ou_son_inventaire_vient() -> None:
    """C'est la propriété que la prose affirme, et qu'il fallait tenir.

    « Dérivé des fichiers » n'est vérifiable par personne si l'entrée ne dit
    pas **de quels fichiers** ni **quand**. Sans cette trace, une divergence
    future serait inattribuable : impossible de dire si le producteur a bougé
    ou si notre outillage a changé.
    """
    brut = json.loads(INVENTAIRE.read_text(encoding="utf-8"))

    manquants = [
        entree["dataset"].get("identifier", "?")
        for entree in brut["entries"]
        if not entree["dataset"].get("inventory_source")
    ]

    assert not manquants, (
        f"Ces entrees ne declarent pas leur source d'inventaire : {manquants}. "
        "Une entree derivee des fichiers doit dire desquels, et quand."
    )


@pytest.mark.parametrize("champ", ["derived_at", "granules", "toolchain"])
def test_la_source_d_inventaire_est_complete(champ: str) -> None:
    """Trois champs, et chacun répond à une question distincte.

    `derived_at` dit **quand**, `granules` dit **de quoi**, `toolchain` dit
    **avec quoi**. Il en manque un et la trace cesse d'être attribuable.
    """
    brut = json.loads(INVENTAIRE.read_text(encoding="utf-8"))

    vides = [
        entree["dataset"].get("identifier", "?")
        for entree in brut["entries"]
        if not (entree["dataset"].get("inventory_source") or {}).get(champ)
    ]

    assert not vides, f"`{champ}` est absent ou vide pour : {vides}."
