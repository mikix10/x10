"""La suite du client ne dépend pas des identifiants du poste qui la lance.

**Le défaut que ce fichier corrige était réel et silencieux.** Un test
affirmait `credentials.available == ("meteofrance",)` après un
`Session.from_env()` : il passait sur une machine sans identifiants, et
échouait dès qu'on en configurait un second — c'est-à-dire **exactement au
moment où le code commence à servir**. Constaté le 20/10/2026, sur le poste
du mainteneur, le jour où les identifiants ECMWF ont été posés.

La réponse n'est pas de corriger l'assertion mais de rendre la propriété
vraie par construction : **aucun test ne voit d'identifiant qu'il n'a pas
lui-même posé.** Un test qui en veut un le pose par `monkeypatch`, et il
est alors le seul présent.

Le vocabulaire est lu dans `ENVIRONMENT` plutôt que recopié : une source
ajoutée demain est neutralisée sans que personne y pense.
"""

from __future__ import annotations

import pytest
from x10_client.credentials import ENVIRONMENT


@pytest.fixture(autouse=True)
def _sans_identifiant_du_poste(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retire toute variable d'identifiant avant chaque test."""
    for parts in ENVIRONMENT.values():
        for variable in parts.values():
            monkeypatch.delenv(variable, raising=False)
