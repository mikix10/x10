"""X10-DIV-0018 — ecCodes accorde l'unité au cumul, mais pas le nom CF.

**Le constat, sur les échantillons que la roue embarque elle-même.** Posez
`shortName = ssrd` sur une poignée d'édition 2, puis faites varier le seul
`stepType` :

```
stepType instant  →  units W m**-2  ·  cfName unknown
stepType accum    →  units J m**-2  ·  cfName surface_downwelling_shortwave_flux_in_air
```

L'unité suit le traitement statistique — c'est juste, un cumul de flux est
une énergie. Le nom CF, lui, **n'apparaît que dans le cas cumulé**, et c'est
le nom du **débit**. Autrement dit ecCodes ne nomme ce paramètre que là où ce
nom est faux : CF donne à `surface_downwelling_shortwave_flux_in_air`
l'unité canonique `W m-2`, et `J m-2` ne lui est pas convertible.

Mesuré le 22/10/2026 sur ecCodes 2.49.0, sous `centre=ecmf` comme sous
`centre=lfpw` — le comportement ne dépend pas du centre. `strd`, de forme
identique, n'est nommé dans aucun des deux cas : la divergence est propre à
ce paramètre, et non à la classe entière.

**Pourquoi cela nous atteint sans que nous l'ayons demandé.** `cfgrib`
recopie `cfName` dans `standard_name` — `dataset.py`, « if "GRIB_cfName" in
data_var_attrs » —, de sorte que le nom fautif arrive **déjà posé** avant que
nos propres tables soient consultées. Une correction placée dans la branche
« notre table » ne l'aurait jamais vu ; c'est ce qui a motivé de déplacer le
redressement après le choix du nom, quelle qu'en soit l'origine.

**Ce n'est pas une non-conformité.** Aucune clause n'oblige ecCodes à
accorder `cfName` au `stepType` ; la bibliothèque expose ce que ses tables
disent du paramètre, et le paramètre est bien un débit. C'est une divergence,
et elle est d'autant plus coûteuse qu'elle est cohérente d'apparence : le
fichier produit se dit conforme à CF, et rien dans la chaîne ne proteste.

**À distinguer de `X10-DIV-0008`**, qui porte sur la même faute vue de
l'autre bout : là, c'est **notre** table qui posait un nom de débit sur un
cumul, pour un triplet qu'ecCodes ne nomme pas du tout. Deux causes, un seul
symptôme, une seule parade.

**Cette sonde ne demande rien** : ni réseau, ni identifiant, ni fichier
externe. Les échantillons viennent de la roue.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from x10_client.probes import Assertion, Handling, Mode, Nature, Outcome, Probe, Side, Status

#: Le rayonnement solaire descendant, diffusé en cumul par Météo-France comme
#: par ECMWF. C'est le cas mesuré ; `strd` se comporte à l'identique.
SHORT_NAME = "ssrd"
RATE_UNIT = "W m**-2"
ACCUMULATED_UNIT = "J m**-2"
#: Le nom que CF réserve au débit, et son unité canonique au tableau v95.
RATE_NAME = "surface_downwelling_shortwave_flux_in_air"
CANONICAL_UNIT = "W m-2"

PROBE = Probe(
    identifier="X10-DIV-0018",
    title="ecCodes adapts units to an accumulation but keeps the rate's CF name",
    nature=Nature.DIVERGENCE,
    status=Status.CONFIRMED,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 22),
    producer="ECMWF — ecCodes",
    artefact="définitions ecCodes, clés units et cfName",
    workaround=(
        "Le nom retenu est redressé après le choix, quelle qu'en soit "
        "l'origine : `grib2.denotes_a_rate` reconnaît un débit par ses "
        "jetons, `CF_ACCUMULATED` lui substitue l'intégrale, et le nom est "
        "retiré faute d'intégrale publiée par CF."
    ),
    handling=Handling.WORKED_AROUND,
    mode=Mode.AUTOMATIC,
)


def _releve(step_type: str) -> tuple[str | None, str | None]:
    """Unité et nom CF du même paramètre sous un `stepType` donné."""
    import eccodes

    handle = eccodes.codes_grib_new_from_samples("GRIB2")
    try:
        eccodes.codes_set(handle, "shortName", SHORT_NAME)
        eccodes.codes_set(handle, "stepType", step_type)
        unite = str(eccodes.codes_get(handle, "units"))
        nom = str(eccodes.codes_get(handle, "cfName"))
    except Exception:
        return None, None
    finally:
        eccodes.codes_release(handle)
    return unite, (None if nom == "unknown" else nom)


def check() -> Assertion:
    """Aucune requête : tout vient des échantillons de la roue."""
    unite_debit, nom_debit = _releve("instant")
    unite_cumul, nom_cumul = _releve("accum")

    if (unite_debit, unite_cumul) != (RATE_UNIT, ACCUMULATED_UNIT):
        resultat = Outcome.CANT_TELL
        detail = (
            f"Units go from {unite_debit!r} to {unite_cumul!r} instead of "
            f"{RATE_UNIT!r} to {ACCUMULATED_UNIT!r}; the measured behaviour "
            "has changed and the probe concludes nothing."
        )
    elif nom_cumul != RATE_NAME:
        resultat = Outcome.PASSED
        detail = (
            f"The accumulated case now yields cfName {nom_cumul!r} rather than "
            f"the rate name {RATE_NAME!r}."
        )
    else:
        resultat = Outcome.FAILED
        detail = (
            f"{SHORT_NAME}: cfName is {nom_debit!r} when instantaneous and "
            f"{nom_cumul!r} when accumulated, so the only case that gets a "
            f"name is the one where it is wrong — CF gives {RATE_NAME!r} the "
            f"canonical unit {CANONICAL_UNIT!r}, while the message carries "
            f"{unite_cumul!r}."
        )
    return Assertion(
        identifier=PROBE.identifier,
        outcome=resultat,
        detail=detail,
        observed_at=datetime.now(UTC),
    )
