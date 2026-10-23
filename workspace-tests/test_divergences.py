"""Le registre des écarts, dérivé du catalogue et jamais tenu à la main.

**C'est le piège qui a tué toutes les tentatives que le dépôt a recensées** :
une colonne qu'un humain doit penser à mettre à jour ne l'est jamais. Le
registre `docs/divergences.tsv` est donc **engendré** depuis les modules de
`probes/`, et ce test échoue si le fichier commité diffère. Un ajout au
registre produit alors une ligne de `git diff` qu'un relecteur lit — la même
mécanique que `lexique-public.txt` et que le contrat de sortie.

Le test vérifie aussi la cohérence que le modèle ne peut pas porter seul :
numérotation sans trou ni doublon, et un fichier par entrée.

Régénérer après un ajout délibéré :

```bash
X10_DIVERGENCES_UPDATE=1 uv run pytest workspace-tests/test_divergences.py
```

**Il importe, contrairement au test du lexique**, parce qu'il charge de vrais
modules de catalogue. Aucun d'eux n'atteint le réseau à l'import : une sonde
ne sollicite une source que dans `check()`, jamais au chargement.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from x10_client.probes import Mode, Nature, Outcome, Probe, Replay, as_tsv, load, run

RACINE = Path(__file__).resolve().parent.parent
CATALOGUE = RACINE / "probes"
REGISTRE = RACINE / "docs" / "divergences.tsv"


@pytest.fixture(scope="module")
def registered():
    """Le catalogue, chargé une fois — le chargement contrôle déjà beaucoup."""
    return load(CATALOGUE)


def test_le_registre_commite_est_celui_du_catalogue(registered) -> None:
    """Le fichier versionné dérive du catalogue, et rien ne les laisse diverger."""
    attendu = as_tsv(i.probe for i in registered)
    if os.environ.get("X10_DIVERGENCES_UPDATE"):
        REGISTRE.write_text(attendu, encoding="utf-8")
        pytest.skip("registre regenere")
    assert REGISTRE.exists(), f"{REGISTRE.name} manque ; regenerer avec X10_DIVERGENCES_UPDATE=1"
    assert REGISTRE.read_text(encoding="utf-8") == attendu


def test_aucune_ligne_du_registre_ne_finit_par_un_blanc(registered) -> None:
    """La dernière colonne est obligatoire, et rien ne doit le défaire.

    Un champ facultatif en fin de ligne y laisserait une tabulation finale,
    que le hook `trailing-whitespace` retirerait — et la retirer décalerait
    tous les champs d'un cran, rendant le registre faux sans que rien ne le
    signale. Ce test tient la propriété pour que le prochain réordonnancement
    de colonnes se voie, plutôt que d'exclure le hook ou d'ajouter une
    colonne factice.
    """
    from x10_client.probes import COLUMNS, Probe, as_tsv

    assert Probe.model_fields[COLUMNS[-1]].is_required(), COLUMNS[-1]
    for ligne in as_tsv(e.probe for e in registered).splitlines():
        assert ligne == ligne.rstrip(), repr(ligne[-40:])


def test_la_numerotation_est_continue_et_sans_doublon(registered) -> None:
    """Un trou signale une entrée perdue ; un retrait garde son numéro.

    Une entrée retirée reste au catalogue en statut `withdrawn`, de sorte
    qu'un message de commit de l'an prochain désigne toujours la même chose.
    """
    numeros = sorted(int(i.probe.identifier.rsplit("-", 1)[1]) for i in registered)
    assert numeros == list(range(1, len(numeros) + 1))


def test_chaque_entree_a_son_module_et_un_seul(registered) -> None:
    """Le nom de fichier porte l'identifiant : on retrouve une entrée sans index."""
    for entry in registered:
        attendu = entry.probe.identifier.lower().replace("-", "_")
        assert entry.origine is not None
        assert entry.origine.stem.startswith(attendu), entry.origine.name


def test_une_non_conformite_cite_toujours_sa_clause(registered) -> None:
    """Annoncer une violation sans référence opposable serait une opinion.

    Le modèle le refuse déjà ; ce test le constate sur le catalogue réel,
    parce que c'est la promesse que le registre fait à ceux qu'il nomme.
    """
    for entry in registered:
        if entry.probe.nature is Nature.NON_CONFORMITY:
            assert entry.probe.clause, entry.probe.identifier


def test_une_sonde_automatique_ne_touche_pas_le_reseau_a_l_import(registered) -> None:
    """Le chargement a déjà eu lieu : s'il avait appelé, le test serait lent.

    Le contrôle est structurel plutôt que chronométré — on vérifie qu'aucun
    module ne lance d'appel au niveau du module, là où un `obtenir(...)` hors
    fonction passerait inaperçu jusqu'au premier `pytest`.
    """
    appel = re.compile(
        r"^(fetch|meteofrance_headers|cds_headers|meteofrance_token)\(", re.MULTILINE
    )
    for chemin in CATALOGUE.glob("*.py"):
        assert not appel.search(chemin.read_text(encoding="utf-8")), chemin.name


def test_executer_sans_sonde_rend_untested_et_jamais_passed(registered) -> None:
    """`passed` est une bonne nouvelle : elle ne doit pas s'obtenir par défaut.

    Une entrée sans moyen de rejeu rend `untested`. Confondre les deux ferait
    croire qu'une source a été corrigée alors que personne n'a regardé.
    """
    sans_sonde = [i.probe.identifier for i in registered if i.check is None]
    assert sans_sonde, "le catalogue devrait compter des entrees non outillees"
    rapport = run(registered, only=sans_sonde)
    assert {c.outcome for c in rapport.assertions} == {Outcome.UNTESTED}
    assert rapport.newly_fixed == ()


def test_une_sonde_qui_leve_rend_canttell(registered) -> None:
    """Ne pas pouvoir conclure n'est pas une bonne nouvelle.

    C'est le cas le plus probable en exploitation — service indisponible,
    identifiant absent — et le plus dangereux s'il était lu comme un succès.
    """
    from x10_client.probes import Registered

    def tombe() -> Outcome:
        raise RuntimeError("le service ne repond pas")

    temoin = Registered(probe=registered[0].probe, check=tombe)
    rapport = run([temoin])
    assert rapport.assertions[0].outcome is Outcome.CANT_TELL
    assert rapport.newly_fixed == ()


def test_le_rejeu_restreint_doit_se_justifier() -> None:
    """Par défaut le rejeu est libre : nos sources s'ouvrent à qui s'inscrit.

    C'est ce qui rend le registre contradictoire plutôt que déclaratif. Une
    restriction doit donc nommer son motif, sinon elle se glisserait par
    commodité.
    """
    with pytest.raises(ValueError, match="restricted replay"):
        Probe(
            identifier="X10-DIV-9999",
            title="t",
            nature=Nature.DIVERGENCE,
            side="source",
            observed_on="2026-10-20",
            producer="p",
            artefact="a",
            workaround="w",
            handling="endured",
            mode=Mode.UNTESTED,
            replay=Replay.RESTRICTED,
        )
