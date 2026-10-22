"""X10-DIV-0019 — ERA5-Land a permuté trois composantes d'évapotranspiration.

**La première entrée du registre qui ne soit pas un défaut de description.**
Les dix-huit précédentes portent sur ce qu'un producteur dit de sa donnée ;
celle-ci porte sur la donnée elle-même, sous une description **parfaite**.

Le producteur l'écrit lui-même, en titre de ses problèmes connus : « Swapped
value of the components of the total evapotranspiration ». Trois variables
sont concernées — `evabs`, `evaow`, `evavt` : évaporation du sol nu, des eaux
libres, de la végétation.

**Ce que cela nous apprend sur la portée de nos contrôles.** Aucun de nos
garde-fous ne peut voir cela, et ce n'est pas une lacune à combler : le nom
standard est juste, l'unité est juste, la méthode de cellule est juste, les
bornes sont justes, la géométrie est juste. Un fichier portant des valeurs
permutées est **conforme**. La vérification dimensionnelle du 22/10/2026 le
dirait sain, et elle aurait raison dans son ordre.

**La seule parade connue est la redondance** — un second chemin vers la même
grandeur, et un écart qu'on mesure. C'est ce qui a permis de trouver les trois
défauts de donnée documentés d'ERA5, tous par comparaison. À nuancer
cependant : conclure de là que la redondance est la *seule* parade serait une
sélection sur la variable dépendante, puisque la comparaison est précisément
la méthode qui produit les cas connus.

**Pourquoi `manual`.** Une sonde automatique devrait disposer d'une seconde
source de la même grandeur, au même pas et sur la même emprise. Ce n'est pas
hors de portée — c'est un chantier, et le déclarer `manual` le dit, là où ne
rien inscrire l'aurait caché.
"""

from __future__ import annotations

from datetime import date

from x10_client.probes import Handling, Mode, Nature, Probe, Side, Status

PROBE = Probe(
    identifier="X10-DIV-0019",
    title="ERA5-Land swapped three components of total evapotranspiration",
    nature=Nature.DATA_QUALITY,
    status=Status.CONFIRMED,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 22),
    producer="ECMWF — Copernicus Climate Data Store",
    artefact="ERA5-Land, variables evabs, evaow, evavt",
    workaround="Aucune de notre fait : la description est exacte, donc aucun "
    "contrôle de forme ne peut voir l'écart. Seule une seconde "
    "source de la même grandeur le révélerait.",
    handling=Handling.ENDURED,
    mode=Mode.MANUAL,
    replay_note="Relire la page des problèmes connus d'ERA5-Land, section "
    "« Swapped value of the components of the total "
    "evapotranspiration ».",
)
