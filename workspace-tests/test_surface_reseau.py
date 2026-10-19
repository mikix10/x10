"""La surface de requêtes sortantes, et ce qui doit rester vrai d'elle.

**Ce que ces tests protègent.** X10 télécharge des fichiers décrits par un
catalogue. Une URL venue du catalogue serait une **entrée non maîtrisée**, et
la faire atteindre une requête ouvrirait la porte au SSRF — une entrée du
registre pointant vers une adresse interne, et le connecteur l'irait
chercher.

Aujourd'hui ce chemin **n'existe pas** : toutes les URL requêtées sont des
constantes de module, et `Distribution.access_url` n'est lu que pour être
décrit. C'est une propriété réelle, vérifiée le 19/10/2026 — et **fragile** :
le pas suivant du catalogue, « l'appelant résout une entrée et le connecteur
va la chercher », la casserait sans que rien ne le signale.

Ces tests la constatent, pour que sa perte soit une décision et non un
accident.
"""

from __future__ import annotations

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

#: Les seuls modules qui ont le droit de mentionner `access_url` : celui qui
#: le **définit**, et celui qui l'**exporte** en métadonnée. Aucun des deux ne
#: requête quoi que ce soit.
LECTEURS_ADMIS = {
    "packages/x10-models/src/x10_models/__init__.py",
    "packages/x10-catalog/src/x10_catalog/__init__.py",
}

#: Une URL en clair dans le code. Les constantes de source en sont, et elles
#: doivent toutes être en TLS.
URL_LITTERALE = re.compile(r"""["'](http://[^"'\s]+)["']""")


def _sources() -> list[Path]:
    trouves: list[Path] = []
    for famille in ("packages", "services"):
        for membre in sorted((RACINE / famille).glob("*")):
            trouves += sorted((membre / "src").rglob("*.py"))
    return trouves


def test_aucune_url_du_catalogue_n_atteint_une_requete():
    """`access_url` ne doit être lu que pour être décrit, jamais pour aller
    chercher.

    Un échec ici n'est pas forcément une faute : c'est le signal qu'un chemin
    du catalogue vers le réseau vient d'apparaître. Il demande alors une
    relecture de sécurité — validation du schéma, de l'hôte, et refus des
    redirections vers une adresse privée — avant d'élargir cette liste.
    """
    lecteurs = {
        c.relative_to(RACINE).as_posix()
        for c in _sources()
        if "access_url" in c.read_text(encoding="utf-8")
    }
    nouveaux = sorted(lecteurs - LECTEURS_ADMIS)
    assert nouveaux == [], (
        f"`access_url` est désormais lu par : {nouveaux}. Si ce module émet "
        "une requête, la surface SSRF vient de s'ouvrir — valider schéma et "
        "hôte avant d'ajouter le fichier à `LECTEURS_ADMIS`."
    )


def test_aucune_url_en_clair_n_est_requetee():
    """Pas de `http://` dans les sources : le transport est chiffré partout.

    Le skill de sécurité l'exige — « ne jamais désactiver la vérification
    TLS » —, et une constante en clair est la façon la plus discrète de la
    contourner.
    """
    fautifs = [
        f"{c.relative_to(RACINE).as_posix()} -> {m.group(1)}"
        for c in _sources()
        for m in URL_LITTERALE.finditer(c.read_text(encoding="utf-8"))
    ]
    assert fautifs == [], f"URL non chiffrée(s) dans les sources : {fautifs}"
