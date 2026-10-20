"""X10-DIV-0011 — une empreinte publiée qui ne vérifie rien.

**Le constat.** Le catalogue publie un SHA-1 par ressource. Celui de
l'archive de définitions **ne correspond pas** aux octets servis, alors que
la taille annoncée est exacte à l'octet.

**Pourquoi une empreinte fausse est pire qu'une empreinte absente.** Qui la
contrôle conclut à une corruption et rejette une donnée saine ; qui ne la
contrôle pas n'a aucun validateur. Les deux comportements raisonnables
mènent au mauvais résultat.

Le seul validateur sûr reste donc celui que **nous** calculons, et c'est ce
que fait le relevé d'inventaire.
"""

from __future__ import annotations

from datetime import date

from x10_client.probes import Handling, Mode, Nature, Probe, Side, Status

PROBE = Probe(
    identifier="X10-DIV-0011",
    title="Published SHA-1 does not match the served bytes, while the size does",
    nature=Nature.DATA_QUALITY,
    status=Status.CONFIRMED,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 13),
    producer="data.gouv.fr",
    artefact="catalogue de ressources, champ checksum",
    workaround="Empreinte recalculée par nous à l'acquisition, et consignée.",
    handling=Handling.WORKED_AROUND,
    mode=Mode.MANUAL,
    replay_note="Télécharger la ressource, calculer son SHA-1, et le comparer au "
    "champ du catalogue. Non automatisée : l'archive pèse plusieurs "
    "dizaines de mégaoctets.",
)
