"""X10-DIV-0020 — dix-huit mois de moyennes mensuelles fausses, et non remplacées.

Le producteur l'écrit en toutes lettres à ses problèmes connus : « Incorrect
values of monthly averaged reanalysis of accumulated fields from September
2022 to February 2024 », et surtout — c'est le point — **« Incorrect data from
September 2022 to February 2024 will not be replaced on CDS discs nor MARS
tapes. »**

**Ce n'est pas un incident, c'est un état permanent.** La donnée reste servie,
par le même chemin, sous le même identifiant, avec les mêmes métadonnées, et
elle est fausse sur dix-huit mois. Rien dans le fichier ne le dira jamais.

**Et cela nomme une notion que notre modèle n'a pas.** Le dépôt distingue déjà
trois choses qu'on confond volontiers : la **licence**, qui dit les conditions
d'usage ; les **droits d'accès**, qui disent les motifs juridiques de
restriction ; et l'**exigence d'authentification**, qui est une propriété
technique du moyen d'accès. Il en manque une quatrième : **l'erratum**, qui
dit qu'une distribution est erronée sur une période donnée.

Sans elle, notre catalogue sert ces dix-huit mois comme si de rien n'était.
`Distribution` n'a aucun champ pour le porter, et `CatalogEntry` aucun moyen
de l'exprimer.

**C'est exprimable dans un catalogue et pas dans un fichier**, et la
distinction compte : un fichier est figé dès l'écriture, une entrée de
catalogue se corrige après coup. Une part de ce que la description ne peut pas
dire relève donc du catalogue, pas du format — ce qui est une bien meilleure
nouvelle que de conclure à l'inexprimable.

**Pourquoi `manual`.** Une sonde automatique devrait lire la page des
problèmes connus et en extraire des périodes, ce qu'aucun producteur ne publie
sous forme exploitable. Le déclarer est plus honnête que de ne rien inscrire.
"""

from __future__ import annotations

from datetime import date

from x10_client.probes import Handling, Mode, Nature, Probe, Side, Status

PROBE = Probe(
    identifier="X10-DIV-0020",
    title="ERA5-Land monthly accumulated fields are wrong for 18 months and will not be replaced",
    nature=Nature.DATA_QUALITY,
    status=Status.CONFIRMED,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 22),
    producer="ECMWF — Copernicus Climate Data Store",
    artefact="ERA5-Land, moyennes mensuelles de champs cumulés, 09/2022 à 02/2024",
    workaround="Aucune : le producteur déclare que la donnée ne sera pas "
    "remplacée. Il faudrait une notion d'erratum au catalogue pour "
    "que l'entrée porte sa période erronée — elle n'existe pas.",
    handling=Handling.ENDURED,
    mode=Mode.MANUAL,
    replay_note="Relire la page des problèmes connus d'ERA5-Land : la phrase "
    "« will not be replaced on CDS discs nor MARS tapes » y est "
    "verbatim.",
)
