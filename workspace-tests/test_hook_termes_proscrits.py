"""Le hook qui refuse un commit portant un terme de `.denylist`.

Il vit dans `workspace-tests/` parce qu'il porte sur l'outillage du dépôt et
non sur un membre.

**Aucun de ces tests ne lit la vraie liste**, et c'est nécessaire à deux
titres. `.denylist` n'est pas versionné, donc il est absent de
l'intégration continue : un test qui en dépendrait n'y tournerait jamais. Et
le faire lire par un test ferait entrer ses termes dans une sortie de
pytest, c'est-à-dire exactement là où ils ne doivent pas aller.

**La propriété la plus importante est tenue ici** : le hook ne reproduit
jamais le terme qu'il a trouvé. Il dit **où regarder**, jamais **quoi
chercher**.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent


def _hook():
    chemin = RACINE / ".pre-commit-hooks" / "termes_proscrits.py"
    spec = importlib.util.spec_from_file_location("termes_proscrits", chemin)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HOOK = _hook()

#: Un terme d'épreuve, qui ne figure dans aucune liste réelle.
FICTIF = "nomprotegefictif"


@pytest.fixture
def liste(tmp_path, monkeypatch):
    """Une liste d'épreuve, substituée à celle du dépôt."""
    fichier = tmp_path / "liste"
    fichier.write_text(f"# un commentaire\n\n{FICTIF}\n", encoding="utf-8")
    monkeypatch.setattr(HOOK, "LISTE", fichier)
    return fichier


def test_un_message_portant_un_terme_est_refuse(liste, tmp_path, capsys):
    message = tmp_path / "msg"
    message.write_text(f"fix(x): corriger\n\nvu chez {FICTIF}.\n", encoding="utf-8")

    assert HOOK.main(["--message", str(message)]) == 1


def test_le_terme_trouve_n_est_jamais_reproduit(liste, tmp_path, capsys):
    """**C'est la propriété centrale du hook.**

    Afficher la chaîne la ferait entrer dans un terminal, un journal
    d'exécution et un transcrit de session — là même où la liste existe pour
    qu'elle n'aille pas. Le rapport doit donc nommer le fichier et la ligne,
    et rien d'autre.
    """
    message = tmp_path / "msg"
    message.write_text(f"fix(x): corriger\n\nvu chez {FICTIF}.\n", encoding="utf-8")

    HOOK.main(["--message", str(message)])

    rendu = capsys.readouterr()
    assert FICTIF not in rendu.err + rendu.out, "le terme ne doit pas être reproduit"
    assert "msg:3" in rendu.err, "mais la ligne fautive doit être nommée"


def test_un_message_sans_terme_passe(liste, tmp_path):
    message = tmp_path / "msg"
    message.write_text("fix(x): corriger le decodage\n\nRien de sensible.\n", encoding="utf-8")

    assert HOOK.main(["--message", str(message)]) == 0


def test_un_commentaire_du_message_n_est_pas_examine(liste, tmp_path):
    """Git ajoute ses propres lignes commentées au message en préparation.

    Les examiner ferait échouer un commit sur un texte que git retirera
    lui-même — un faux positif pur, et un contrôle qui crie à tort s'apprend
    à contourner.
    """
    message = tmp_path / "msg"
    message.write_text(f"fix(x): corriger\n# note interne : {FICTIF}\n", encoding="utf-8")

    assert HOOK.main(["--message", str(message)]) == 0


def test_sans_liste_le_hook_refuse(tmp_path, monkeypatch, capsys):
    """Un contrôle qui ne peut pas conclure ne laisse pas passer.

    La liste n'étant pas versionnée, un clone neuf ne l'a pas. Échouer est
    le seul choix tenable : laisser passer rendrait le contrôle muet
    précisément là où personne ne sait qu'il manque.
    """
    monkeypatch.setattr(HOOK, "LISTE", tmp_path / "absente")

    assert HOOK.main(["--diff"]) == 1
    assert "absent" in capsys.readouterr().err


def test_une_liste_vide_est_traitee_comme_absente(tmp_path, monkeypatch):
    """Une liste réduite à des commentaires ne protège de rien."""
    vide = tmp_path / "liste"
    vide.write_text("# rien que des commentaires\n\n", encoding="utf-8")
    monkeypatch.setattr(HOOK, "LISTE", vide)

    assert HOOK.main(["--diff"]) == 1
