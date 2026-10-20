"""X10-DIV-0012 — les libellés d'ecCodes ne sont pas ceux de la norme.

**Le constat.** Pour l'entrée 5 de la table 4.2-0-3, l'OMM écrit
« Geopotential height » et ecCodes affiche « Orography ». Pour l'entrée 6,
l'OMM note elle-même que le code ne dit pas s'il s'agit d'une hauteur au-
dessus du niveau de la mer ou du sol, et recommande les entrées 33 et 34 ;
ecCodes tranche néanmoins.

**Ce qui est en jeu n'est pas l'exactitude du libellé** mais son autorité :
lire ecCodes comme la norme revient à hériter de choix qu'aucune autorité
n'a validés. C'est ainsi que notre propre table avait posé
`geopotential_height` sur `(0, 3, 6)` — faux deux fois, puisque c'est
l'entrée 5 qui porte ce sens et qu'elle s'exprime en mètres
géopotentiels.

L'entrée reste au registre non pour être corrigée — ecCodes a le droit de
nommer comme il veut — mais parce qu'elle documente **une source
d'erreur récurrente** pour quiconque bâtit une correspondance.
"""

from __future__ import annotations

from datetime import date

from x10_client.probes import Handling, Mode, Nature, Probe, Side, Status

PROBE = Probe(
    identifier="X10-DIV-0012",
    title="ecCodes labels diverge from the WMO wording and arbitrate where it does not",
    nature=Nature.DIVERGENCE,
    status=Status.CONFIRMED,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 13),
    producer="ECMWF — ecCodes",
    artefact="définitions GRIB2, table 4.2-0-3",
    workaround="Les libellés d'ecCodes ne sont jamais lus comme la norme ; "
    "`(0, 3, 6)` est retiré de notre table et recensé comme ambigu.",
    handling=Handling.WORKED_AROUND,
    mode=Mode.MANUAL,
    replay_note="Comparer `name` rendu par ecCodes au texte du *Manual on Codes* "
    "pour les entrées 5 et 6 de la table 4.2-0-3.",
)
