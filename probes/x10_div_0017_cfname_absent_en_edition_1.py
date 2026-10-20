"""X10-DIV-0017 — ecCodes connaît le nom CF, mais ne le rend pas en édition 1.

**Le constat tient en deux lignes**, sur les échantillons que la roue
embarque elle-même :

```
échantillon GRIB1, paramId 167  →  shortName 2t,  cfName unknown
échantillon GRIB2, paramId 167  →  shortName 2t,  cfName air_temperature
```

Même bibliothèque, même paramètre, même table de concepts. **L'information
est présente ; elle n'est simplement pas exposée sur un message d'édition
1.** Vérifié ensuite sur les fichiers réels : les quatre champs d'un granule
ERA5 sortent tous en `cfName = unknown`, et trois des quatre se nomment dès
qu'on repasse leur `paramId` par un handle d'édition 2.

**Pourquoi c'est l'entrée la plus rentable du registre.** Elle explique à
elle seule six des quatorze champs non nommés du diagnostic GRIB1, et sa
parade ne coûte rien : un second passage, hors ligne, sans réseau ni
service. C'est ce qui ramène le résidu de cinq champs à deux.

**Ce n'est pas une non-conformité** : aucune clause n'oblige ecCodes à
exposer `cfName` sur toute édition. C'est une asymétrie surprenante, et
qui coûte cher à qui ne la connaît pas — il conclurait que l'édition 1
n'est pas nommable, alors qu'elle l'est à 64 %.

**Cette sonde est la seule du registre à ne rien demander** : ni réseau, ni
identifiant, ni fichier externe. Les échantillons viennent de la roue.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from x10_client.probes import Assertion, Handling, Mode, Nature, Outcome, Probe, Side, Status

#: La température à 2 m : le paramètre le plus courant qui soit, et celui
#: dont l'absence de nom se remarque le plus.
PARAM = 167
ATTENDU = "air_temperature"

PROBE = Probe(
    identifier="X10-DIV-0017",
    title="ecCodes resolves the CF name from paramId but does not expose it on a GRIB1 message",
    nature=Nature.DIVERGENCE,
    status=Status.CONFIRMED,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 20),
    producer="ECMWF — ecCodes",
    artefact="définitions ecCodes, clé cfName",
    workaround=(
        "Un second passage : le `paramId` du message est relu par un handle "
        "d'édition 2, qui rend le nom. Hors ligne, sans service."
    ),
    handling=Handling.DOCUMENTED,
    mode=Mode.AUTOMATIC,
)


def _cf_name(gabarit: str) -> str | None:
    import eccodes

    handle = eccodes.codes_grib_new_from_samples(gabarit)
    try:
        eccodes.codes_set(handle, "paramId", PARAM)
        nom = eccodes.codes_get(handle, "cfName")
    except Exception:
        return None
    finally:
        eccodes.codes_release(handle)
    return None if nom in (None, "unknown") else str(nom)


def check() -> Assertion:
    """Aucune requête : tout vient des échantillons de la roue."""
    en_edition_1 = _cf_name("GRIB1")
    en_edition_2 = _cf_name("GRIB2")

    if en_edition_2 != ATTENDU:
        resultat = Outcome.CANT_TELL
        detail = (
            f"The GRIB2 sample yields {en_edition_2!r} instead of {ATTENDU!r}; "
            "the probe can conclude nothing about edition 1."
        )
    elif en_edition_1 == ATTENDU:
        resultat = Outcome.PASSED
        detail = "Edition 1 now exposes cfName; the asymmetry is gone."
    else:
        resultat = Outcome.FAILED
        detail = (
            f"paramId {PARAM}: edition 1 yields {en_edition_1!r} while edition 2 "
            f"yields {en_edition_2!r}, from the same definitions."
        )
    return Assertion(
        identifier=PROBE.identifier,
        outcome=resultat,
        detail=detail,
        observed_at=datetime.now(UTC),
    )
