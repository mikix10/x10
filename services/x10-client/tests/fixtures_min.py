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
"""

from __future__ import annotations

from pathlib import Path

import pytest

eccodes = pytest.importorskip("eccodes")
np = pytest.importorskip("numpy")


def granule_minimal(cible: Path, parametres: tuple[tuple[int, int], ...]) -> Path:
    """Écrit un granule portant un message par `(catégorie, numéro)` donné."""
    octets = b""
    for categorie, numero in parametres:
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
            eccodes.codes_set(h, "parameterCategory", categorie)
            eccodes.codes_set(h, "parameterNumber", numero)
            eccodes.codes_set_values(h, np.linspace(0.0, 1.0, 24))
            octets += bytes(eccodes.codes_get_message(h))
        finally:
            eccodes.codes_release(h)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(octets)
    return cible


__all__ = ["granule_minimal"]
