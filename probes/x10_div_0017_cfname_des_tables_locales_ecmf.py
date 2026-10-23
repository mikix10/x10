"""X10-DIV-0017 — les tables locales GRIB1 de l'ECMWF ne nomment pas ses champs de surface.

**Correction du 22/10/2026 : le titre précédent était faux sur ses deux
membres.** Il disait qu'ecCodes « connaît le nom CF mais ne le rend pas en
édition 1 ». Il le rend : 42 fois sur la seule table 128. Et il ne « connaît »
pas le nom qu'il n'expose pas, puisque la table d'édition 1 n'en porte aucune
entrée. L'information n'est pas retenue, elle est absente de ce fichier-là.

**Ce que la mesure établit.** Sur les 3 260 `paramId` qu'ecCodes sait encoder
dans les **deux** éditions au centre `ecmf` :

| | |
|---|---|
| nommés des deux côtés | 104 |
| nommés en édition 2 seulement | **28** |
| nommés en édition 1 seulement | **0** |
| nommés dans aucune des deux | **3 128, soit 96,0 %** |

Aucun `paramId` ne reçoit deux noms différents selon l'édition. Le vrai
plafond n'est donc pas l'édition : c'est que la colonne CF d'ecCodes est
quasi vide **des deux côtés**.

**Les 28 écarts ont tous la même cause, et elle est nominative.** Leur
encodage d'édition 1 tombe dans une table **locale de l'ECMWF** — 10 en
table 128, 9 en 228, 4 en 211, 3 en 132, 1 en 131, 1 en 174, et **aucun dans
une table de l'OMM** — pour laquelle `grib1/localConcepts/ecmf/cfName.def`
n'a pas d'entrée ; leur encodage d'édition 2 retombe sur un triplet standard
que `grib2/cfName.def` couvre. Le fichier compte 208 entrées, dont 42 pour la
table 128, et `indicatorOfParameter = 167` n'y figure pas.

Ce sont les champs les plus consommés : `2t`, `10u`, `10v`, `100u`, `100v`,
`orog`, les maxima et minima de température, les quatre champs de différence
de CAMS.

**Le centre décide, pas l'édition.** Sous `lfpw` ou `kwbc`, le même `paramId`
s'encode en table 3 de l'OMM et l'édition 1 rend le nom. Ce qui varie n'est
pas la couverture par édition mais la **table d'encodage** que `codes_set`
choisit selon le centre.

**Ce que la parade coûte, et c'est nouveau.** Repasser un `paramId` d'édition 1
par une poignée d'édition 2 fait gagner 28 noms et en **perd 16** — ceux qui
n'ont aucun encodage d'édition 2. Sur les 3 528 `paramId` encodables en
édition 1 sous `ecmf` : l'édition 1 seule en nomme 120, le second passage 132,
et **l'union des deux 148**. La parade juste est donc l'union, pas la
substitution.

**La parade a une limite que notre propre registre énonce.** Elle est indexée
par `paramId`, et `X10-DIV-0016` établit que cette clé n'est pas univoque : la
hauteur significative en porte trois. La seconde forme mord plus directement
— `(0, 3, 6)` et `(0, 3, 34)` rendent tous deux `3008`, de sorte qu'un second
passage construit depuis le `paramId` **ne saurait pas de quel triplet il
part**. Sur ces deux entrées, que l'OMM a justement créées pour être
distinctes, la parade nommerait un champ pour un autre. Elle vaut donc partout
sauf là, et le dire fait partie de la parade.

**Ce n'est pas une non-conformité** : aucune clause n'oblige l'ECMWF à tenir
une concordance CF dans ses tables locales. C'est une asymétrie coûteuse à qui
ne la connaît pas.

**Cette sonde ne demande rien** : ni réseau, ni identifiant, ni fichier
externe. Les échantillons viennent de la roue.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from x10_client.probes import Assertion, Handling, Mode, Nature, Outcome, Probe, Side, Status

#: La température à 2 m : le cas le plus consommé, et celui dont l'absence de
#: nom se remarque le plus. Son encodage d'édition 1 sous `ecmf` tombe en
#: table locale 128, que la concordance CF ne couvre pas.
PARAM = 167
ATTENDU = "air_temperature"
CENTRE_LOCAL = "ecmf"
CENTRE_TEMOIN = "lfpw"

PROBE = Probe(
    identifier="X10-DIV-0017",
    title="ECMWF GRIB1 local tables carry no cfName for its most used surface parameters",
    nature=Nature.DIVERGENCE,
    status=Status.CONFIRMED,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 20),
    producer="ECMWF — ecCodes",
    artefact="définitions ecCodes, grib1/localConcepts/ecmf/cfName.def",
    workaround=(
        "L'union des deux lectures, et non la substitution : repasser le "
        "paramId par une poignée d'édition 2 gagne 28 noms et en perd 16, "
        "ceux sans encodage d'édition 2. Hors ligne, sans service."
    ),
    handling=Handling.DOCUMENTED,
    mode=Mode.AUTOMATIC,
)


def _cf_name(gabarit: str, centre: str) -> str | None:
    import eccodes

    handle = eccodes.codes_grib_new_from_samples(gabarit)
    try:
        eccodes.codes_set(handle, "centre", centre)
        eccodes.codes_set(handle, "paramId", PARAM)
        nom = eccodes.codes_get(handle, "cfName")
    except Exception:
        return None
    finally:
        eccodes.codes_release(handle)
    return None if nom in (None, "unknown") else str(nom)


def check() -> Assertion:
    """Aucune requête : tout vient des échantillons de la roue."""
    local = _cf_name("GRIB1", CENTRE_LOCAL)
    temoin = _cf_name("GRIB1", CENTRE_TEMOIN)
    edition_2 = _cf_name("GRIB2", CENTRE_LOCAL)

    if edition_2 != ATTENDU or temoin != ATTENDU:
        resultat = Outcome.CANT_TELL
        detail = (
            f"Edition 2 yields {edition_2!r} and centre {CENTRE_TEMOIN} yields "
            f"{temoin!r}, instead of {ATTENDU!r} for both; the probe can "
            "conclude nothing about the ECMWF local table."
        )
    elif local == ATTENDU:
        resultat = Outcome.PASSED
        detail = f"The ECMWF local edition 1 table now names paramId {PARAM}: {local!r}."
    else:
        resultat = Outcome.FAILED
        detail = (
            f"paramId {PARAM}: edition 1 yields {local!r} under centre "
            f"{CENTRE_LOCAL}, which encodes it into local table 128, while the "
            f"same identifier yields {temoin!r} under centre {CENTRE_TEMOIN}, "
            "which encodes it into WMO table 3. The gap is the local table, "
            "not the edition."
        )
    return Assertion(
        identifier=PROBE.identifier,
        outcome=resultat,
        detail=detail,
        observed_at=datetime.now(UTC),
    )
