"""X10-DIV-0018 — ecCodes porte un nom CF de débit sur une entrée de cumul.

**Correction du 22/10/2026 : le symptôme est réel, le mécanisme que cette
sonde décrivait était faux.** Elle disait qu'ecCodes « adapte l'unité au cumul
mais garde le nom CF du débit ». Il n'adapte rien : sur le triplet
`(0, 4, 7)`, il résout **deux paramètres distincts** que seul le traitement
statistique départage.

| `stepType` | `paramId` | nom court | `units` | `cfName` |
|---|---|---|---|---|
| `instant` | 260087 | `sdswrf` | `W m**-2` | *aucun* |
| `accum` | 169 | `ssrd` | `J m**-2` | `surface_downwelling_shortwave_flux_in_air` |

Le nom CF appartient donc à l'entrée **169**, celle du cumul — et c'est le nom
du **débit**, auquel CF donne l'unité canonique `W m-2`, posé sur une entrée
qui déclare `J m-2`. Les deux ne sont pas convertibles. Ce n'est pas une
adaptation d'unité, c'est **une entrée de table incohérente**.

**Et ce n'est pas une singularité.** Sur les 88 paramètres qui portent un
`cfName` dans les disciplines 0 et 10 — celles que X10 lit —, **onze déclarent
une unité dimensionnellement incompatible** avec l'unité canonique que CF
donne à ce nom. Dix le font sur le seul cas cumulé ; le onzième, `acpcp`, le
fait sous tous les traitements, sa cible CF étant une épaisseur en mètres
quand il déclare `kg m**-2`. `ssrd` est un échantillon, pas une exception.

**Pourquoi cela nous atteint sans que nous l'ayons demandé.** `cfgrib` recopie
`cfName` dans `standard_name`, de sorte que le nom fautif arrive **déjà posé**
avant que nos tables soient consultées. Une correction placée dans la branche
« notre table » ne l'aurait jamais vu ; c'est ce qui a imposé de redresser
**après** le choix du nom, quelle qu'en soit l'origine.

**Divergence et non non-conformité, et la distinction se défend.** La clause
existe : CF exige que l'unité d'une variable portant un `standard_name` soit
physiquement équivalente à l'unité canonique, modifiée par `cell_methods`
selon l'annexe E — où la table E.1 donne à `sum` la colonne `u`, unités
**inchangées**. L'OMM dit la même chose à la note 3 de sa table 4.2-0-1 :
« Statistical process 1 (Accumulation) does not change units ». Mais **CF lie
un fichier, pas une bibliothèque de lecture** : ecCodes n'écrit aucun NetCDF
et n'est donc pas le sujet de la clause. Le fichier non conforme serait celui
que *nous* écririons en recopiant le nom — et c'est ce que le redressement
empêche.

**Cette sonde ne demande rien** : ni réseau, ni identifiant, ni fichier
externe. Les échantillons viennent de la roue.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from x10_client.probes import Assertion, Handling, Mode, Nature, Outcome, Probe, Side, Status

#: Le rayonnement solaire descendant, diffusé en cumul par Météo-France comme
#: par ECMWF. C'est le cas mesuré ; dix autres partagent le défaut.
TRIPLET = (0, 4, 7)
#: Le nom que CF réserve au débit, et son unité canonique au tableau v95.
RATE_NAME = "surface_downwelling_shortwave_flux_in_air"
CANONICAL_UNIT = "W m-2"
ACCUMULATED_UNIT = "J m**-2"

PROBE = Probe(
    identifier="X10-DIV-0018",
    title="ecCodes carries a rate CF name on an accumulation entry, with incompatible units",
    nature=Nature.DIVERGENCE,
    status=Status.CONFIRMED,
    side=Side.SOURCE,
    observed_on=date(2026, 10, 22),
    producer="ECMWF — ecCodes",
    artefact="définitions ecCodes, concordance cfName du paramId 169",
    workaround=(
        "Le nom retenu est redressé après le choix, quelle qu'en soit "
        "l'origine : `grib2.denotes_a_rate` reconnaît un débit par ses "
        "jetons, `CF_ACCUMULATED` lui substitue l'intégrale, et le nom est "
        "retiré faute d'intégrale publiée par CF."
    ),
    handling=Handling.WORKED_AROUND,
    mode=Mode.AUTOMATIC,
)


def _releve(step_type: str) -> dict[str, object]:
    """Ce que le triplet rend sous un traitement statistique donné."""
    import eccodes

    handle = eccodes.codes_grib_new_from_samples("GRIB2")
    try:
        discipline, categorie, numero = TRIPLET
        eccodes.codes_set(handle, "discipline", discipline)
        eccodes.codes_set(handle, "parameterCategory", categorie)
        eccodes.codes_set(handle, "parameterNumber", numero)
        if step_type != "instant":
            eccodes.codes_set(handle, "productDefinitionTemplateNumber", 8)
            eccodes.codes_set(handle, "typeOfStatisticalProcessing", 1)
        return {
            "paramId": eccodes.codes_get(handle, "paramId"),
            "shortName": str(eccodes.codes_get(handle, "shortName")),
            "units": str(eccodes.codes_get(handle, "units")),
            "cfName": str(eccodes.codes_get(handle, "cfName")),
        }
    except Exception as exc:
        return {"erreur": type(exc).__name__}
    finally:
        eccodes.codes_release(handle)


def check() -> Assertion:
    """Aucune requête : tout vient des échantillons de la roue."""
    instantane = _releve("instant")
    cumul = _releve("accum")

    if "erreur" in instantane or "erreur" in cumul:
        resultat = Outcome.CANT_TELL
        detail = f"The triplet could not be set: instantaneous {instantane}, accumulated {cumul}."
    elif cumul.get("cfName") != RATE_NAME:
        resultat = Outcome.PASSED
        detail = (
            f"The accumulated entry now yields cfName {cumul.get('cfName')!r} "
            f"rather than the rate name {RATE_NAME!r}."
        )
    elif cumul.get("units") != ACCUMULATED_UNIT:
        resultat = Outcome.CANT_TELL
        detail = (
            f"The accumulated entry yields units {cumul.get('units')!r} instead "
            f"of {ACCUMULATED_UNIT!r}; the measured behaviour has changed."
        )
    else:
        resultat = Outcome.FAILED
        detail = (
            f"Triplet {TRIPLET}: statistical processing selects two distinct "
            f"parameters — {instantane.get('shortName')!r} "
            f"(paramId {instantane.get('paramId')}) when instantaneous, "
            f"{cumul.get('shortName')!r} (paramId {cumul.get('paramId')}) when "
            f"accumulated. The accumulated one declares units "
            f"{cumul.get('units')!r} and cfName {RATE_NAME!r}, whose canonical "
            f"unit is {CANONICAL_UNIT!r}. The two are not convertible."
        )
    return Assertion(
        identifier=PROBE.identifier,
        outcome=resultat,
        detail=detail,
        observed_at=datetime.now(UTC),
    )
