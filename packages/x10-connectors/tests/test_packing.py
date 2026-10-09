"""Tests de l'empaquetage de la section de données, sans accès réseau.

**Pourquoi un fichier dédié.** Un relevé du 08/10/2026 a montré que les
fixtures produisaient du `grid_simple` — gabarit 5.0, le plus simple — alors
que les fichiers réels emploient **CCSDS, gabarit 5.42** : vérifié sur un
paquet AROME, et déjà connu des données ouvertes de l'ECMWF. Le chemin de
décodage n'était donc jamais exercé contre ce qu'il rencontre en production.

L'écart se comble sans aucune donnée réelle : ecCodes sait écrire CCSDS en
mémoire, et un message complet tient en deux cent cinquante octets.
"""

from __future__ import annotations

import numpy as np
import pytest
from fixtures_grib import (
    GRILLE_PAR_DEFAUT,
    PACKING_PAR_DEFAUT,
    VALEUR_MANQUANTE,
    Champ,
    EmpaquetageNonApplique,
    message,
    paquet,
)

from x10_connectors.decoding import normalise, open_granule

N = int(GRILLE_PAR_DEFAUT["ni"] * GRILLE_PAR_DEFAUT["nj"])

#: Empaquetages que les fichiers réels emploient ou pourraient employer, et
#: que cette installation d'ecCodes sait écrire. Les gabarits sont ceux de la
#: table 5.0 du format GRIB2.
#:
#: Le dernier élément dit si `bitsPerValue` est **honoré tel quel**. Relevé le
#: 08/10/2026 : les empaquetages complexes le **recalculent** par groupe, au
#: minimum nécessaire — 11 bits et 6 bits là où 12 étaient demandés. La clé y
#: est donc une sortie, non une consigne, et qui la lit pour en déduire la
#: précision demandée se trompe.
EMPAQUETAGES = [
    ("grid_simple", 0, True),
    ("grid_ccsds", 42, True),
    ("grid_complex", 2, False),
    ("grid_complex_spatial_differencing", 3, False),
]


def _cles(brut: bytes) -> dict[str, object]:
    import eccodes

    h = eccodes.codes_new_from_message(brut)
    try:
        return {
            "packingType": eccodes.codes_get(h, "packingType"),
            "template": eccodes.codes_get(h, "dataRepresentationTemplateNumber"),
            "bits": eccodes.codes_get(h, "bitsPerValue"),
        }
    finally:
        eccodes.codes_release(h)


def test_le_defaut_est_celui_des_fichiers_reels():
    """CCSDS, et non l'empaquetage simple de l'échantillon d'ecCodes."""
    assert PACKING_PAR_DEFAUT == "grid_ccsds"
    assert _cles(message(Champ(category=0, number=0)))["template"] == 42


@pytest.mark.parametrize(("packing", "template", "bits_honores"), EMPAQUETAGES)
def test_chaque_empaquetage_est_reellement_ecrit(packing, template, bits_honores):
    cles = _cles(message(Champ(category=0, number=0, packing=packing)))
    assert cles["packingType"] == packing
    assert cles["template"] == template
    if bits_honores:
        assert cles["bits"] == 12
    else:
        # Recalculé par groupe ; jamais au-delà de ce qui a été demandé.
        assert 0 < cles["bits"] <= 12


@pytest.mark.parametrize(("packing", "_template", "bits_honores"), EMPAQUETAGES)
def test_le_decodage_restitue_les_valeurs_quel_que_soit_l_empaquetage(
    tmp_path, packing, _template, bits_honores
):
    valeurs = np.linspace(250.0, 300.0, N)
    champ = Champ(category=0, number=0, packing=packing, valeurs=valeurs)
    jeu = normalise(open_granule(paquet(tmp_path / f"{packing}.grib2", [champ]))[0])
    # 12 bits sur une plage de 50 K donnent un pas de quantification de
    # l'ordre du centième de kelvin. Les empaquetages complexes descendent
    # plus bas, d'où une tolérance distincte : le but est de vérifier que le
    # décodage restitue la grandeur, pas de mesurer leur précision.
    np.testing.assert_allclose(
        jeu["t"].values.reshape(-1), valeurs, atol=0.02 if bits_honores else 1.0
    )


@pytest.mark.parametrize(("packing", "_template", "_bits"), EMPAQUETAGES)
def test_les_valeurs_manquantes_survivent_a_chaque_empaquetage(tmp_path, packing, _template, _bits):
    """Le masque binaire et l'empaquetage sont deux mécanismes distincts, et
    leur combinaison est précisément ce qu'un paquet réel porte."""
    champ = Champ(category=0, number=0, packing=packing, manquants=7, valeurs=np.full(N, 280.0))
    jeu = normalise(open_granule(paquet(tmp_path / f"{packing}-trous.grib2", [champ]))[0])
    valeurs = jeu["t"].values.reshape(-1)
    assert int(np.isnan(valeurs).sum()) == 7
    assert VALEUR_MANQUANTE not in valeurs


def test_un_empaquetage_non_applique_est_refuse():
    """Le piège qui justifie la relecture.

    `grid_second_order` est accepté par ecCodes **sans être appliqué** : le
    message produit porte un `grid_simple`. Sans relecture, une fixture se
    croirait en train d'exercer un empaquetage qu'elle n'a jamais écrit, et
    le test serait vert sur une hypothèse fausse.
    """
    with pytest.raises(EmpaquetageNonApplique, match="sans l'appliquer"):
        message(Champ(category=0, number=0, packing="grid_second_order"))


def test_un_paquet_peut_meler_les_empaquetages(tmp_path):
    """Rien n'oblige un producteur à l'uniformité d'un message à l'autre."""
    champs = [
        Champ(category=0, number=0, packing="grid_simple"),
        Champ(category=0, number=0, packing="grid_ccsds", step=1),
    ]
    jeux = open_granule(paquet(tmp_path / "mele.grib2", champs))
    assert sum(jeu["t"].size for jeu in jeux) == 2 * N


def test_ccsds_reste_minuscule():
    """La raison pour laquelle aucun fichier réel n'est nécessaire."""
    assert len(message(Champ(category=0, number=0))) < 400
