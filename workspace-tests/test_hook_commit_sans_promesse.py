"""Le hook qui refuse un message de commit s'engageant sur la suite.

Il vit dans `workspace-tests/` parce qu'il porte sur l'outillage du dépôt et
non sur un membre : le placer dans l'un d'eux ferait dépendre sa suite d'un
fichier qui ne lui appartient pas.

**Ce que ces tests tiennent avant tout, ce sont les faux positifs.** Un
contrôle qui se déclenche à tort s'apprend à contourner, et une barrière
qu'on contourne ne protège plus de rien. Les cas légitimes sont donc aussi
nombreux ici que les cas fautifs.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent


def _hook():
    chemin = RACINE / ".pre-commit-hooks" / "commit_sans_promesse.py"
    spec = importlib.util.spec_from_file_location("commit_sans_promesse", chemin)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HOOK = _hook()


@pytest.mark.parametrize(
    "message",
    [
        "fix: corriger le decodage -- ce dont la suite reste une question ouverte",
        "feat: ouvrir la requete\n\nLe reste des flux sera ajoute plus tard.",
        "chore: menage\n\nTODO: reprendre la table des unites.",
        "refactor: separer les vues\n\nLa vue source devra etre exposee.",
        "docs: noter la mesure\n\nUn prochain chantier traitera les vagues.",
        "feat: poser le registre\n\nLes facettes de la vue source restent a ouvrir.",
    ],
)
def test_une_clause_prospective_est_refusee(message):
    assert HOOK.promesses(message) != []


@pytest.mark.parametrize(
    "message",
    [
        # Un comportement du code au futur n'est pas une promesse de travail.
        "test: confronter la version des tables\n\nLe test echouera si un\n"
        "producteur prend de l'avance sur notre ecCodes.",
        # Un constat sur ce qui subsiste, sans engagement.
        "feat: deux connecteurs\n\nRestent des ebauches : l'API n'expose rien.",
        # Le pied de message structure n'est pas lu.
        "chore: menage\n\nSecurity-Review: 2026-10-19",
        # Un renvoi a une note ne promet rien.
        "docs: mesurer les unites\n\nMethode et mesures dans docs/unites.md.",
        # Le cas nominal.
        "ci: declencher aussi sur un changement d'etiquette",
    ],
)
def test_un_constat_legitime_passe(message):
    assert HOOK.promesses(message) == []


def test_les_commentaires_de_git_ne_sont_pas_lus():
    """Git ajoute son propre texte au message, que l'auteur n'ecrit pas."""
    message = "fix: corriger le decodage\n\n# A trancher plus tard.\n"
    assert HOOK.promesses(message) == []


def test_le_diff_d_un_commit_verbeux_n_est_pas_lu():
    """`git commit --verbose` colle le diff sous une ligne de ciseaux."""
    message = (
        "fix: corriger le decodage\n\n"
        f"# {HOOK.CISEAUX}\n"
        "diff --git a/x.py b/x.py\n"
        "+# TODO: reprendre ceci\n"
    )
    assert HOOK.promesses(message) == []


def test_l_accent_ne_change_rien():
    """Les messages du depot sont en ASCII, la prose ne l'est pas toujours."""
    accentue = HOOK.promesses("fix: corriger\n\nÀ traiter ultérieurement.")
    brut = HOOK.promesses("fix: corriger\n\nA traiter ulterieurement.")
    assert accentue != [] and brut != []


def test_le_refus_nomme_la_ligne_et_la_forme_fautive():
    """Un refus qui dit seulement « non » oblige a relire tout le message."""
    (rang, ligne, forme), *reste = HOOK.promesses(
        "feat: ouvrir la requete\n\nLe reste sera ajoute plus tard.\n"
    )
    assert reste == []
    assert rang == 3
    assert "plus tard" in ligne
    assert forme in {"sera ajoute", "plus tard"}


def test_le_hook_rend_zero_sans_argument():
    """Appele sans fichier de message, il ne bloque rien."""
    assert HOOK.main(["commit_sans_promesse.py"]) == 0


def test_le_hook_refuse_le_fichier_fautif_et_accepte_l_autre(tmp_path):
    fautif = tmp_path / "fautif.txt"
    fautif.write_text("feat: ouvrir\n\nLe reste viendra plus tard.\n", encoding="utf-8")
    sain = tmp_path / "sain.txt"
    sain.write_text("feat: ouvrir la requete a l'ensemble\n", encoding="utf-8")

    assert HOOK.main(["hook", str(fautif)]) == 1
    assert HOOK.main(["hook", str(sain)]) == 0
