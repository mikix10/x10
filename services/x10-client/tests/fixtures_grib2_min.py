"""Un granule GRIB2 minuscule, bâti en mémoire, pour exercer l'assemblage.

**Ce n'est pas une copie des fixtures de `x10-connectors`**, et il ne faut
pas la faire grossir vers elles. Celles-là exercent le décodage dans ses
détails — valeurs manquantes, cumuls, ensembles, empaquetage ; celle-ci veut
seulement un fichier que la chaîne accepte, pour vérifier que le client
l'enchaîne correctement.

**Pourquoi ne pas réutiliser les leurs.** Elles vivent dans le dossier de
tests d'un autre membre, et aucun `conftest.py` ni réglage `pythonpath` ne
les met sur le chemin d'import. Elles ne sont atteignables d'ici que par un
effet d'ordre de collecte — donc plus du tout dès qu'on lance
`pytest services/x10-client` seul. La suite d'un membre doit tenir seule.

**Et pourquoi `_min` plutôt que `fixtures_grib2`** : pytest ajoute chaque
dossier de tests au chemin d'import, faute d'`__init__.py`. Deux modules
`fixtures_grib2` s'y trouveraient alors en même temps lors d'une exécution
complète, et le second serait simplement masqué. Le suffixe n'est pas une
coquetterie, c'est ce qui évite la collision.
"""

from __future__ import annotations

from pathlib import Path

import pytest

eccodes = pytest.importorskip("eccodes")
np = pytest.importorskip("numpy")


def minimal_granule(target: Path, parameters: tuple[tuple[int, int], ...]) -> Path:
    """Écrit un granule portant un message par `(catégorie, numéro)` donné."""
    size_bytes = b""
    for category, number in parameters:
        h = eccodes.codes_grib_new_from_samples("regular_ll_sfc_grib2")
        try:
            eccodes.codes_set(h, "centre", 85)
            eccodes.codes_set(h, "Ni", 6)
            eccodes.codes_set(h, "Nj", 4)
            eccodes.codes_set(h, "latitudeOfFirstGridPointInDegrees", 50.0)
            eccodes.codes_set(h, "longitudeOfFirstGridPointInDegrees", 0.0)
            eccodes.codes_set(h, "latitudeOfLastGridPointInDegrees", 47.0)
            eccodes.codes_set(h, "longitudeOfLastGridPointInDegrees", 5.0)
            eccodes.codes_set(h, "iDirectionIncrementInDegrees", 1.0)
            eccodes.codes_set(h, "jDirectionIncrementInDegrees", 1.0)
            eccodes.codes_set(h, "discipline", 0)
            eccodes.codes_set(h, "parameterCategory", category)
            eccodes.codes_set(h, "parameterNumber", number)
            eccodes.codes_set_values(h, np.linspace(0.0, 1.0, 24))
            size_bytes += bytes(eccodes.codes_get_message(h))
        finally:
            eccodes.codes_release(h)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(size_bytes)
    return target


__all__ = ["minimal_granule"]
