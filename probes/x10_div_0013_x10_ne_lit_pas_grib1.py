"""X10-DIV-0013 — X10 ne lit pas le GRIB édition 1, pour une seule ligne.

**Le manque est le nôtre**, et c'est pourquoi il porte son propre numéro :
transmis à un producteur, il serait du bruit.

## Ce que le diagnostic du 20/10/2026 a établi

**La lecture n'est pas en cause.** Les huit granules d'édition 1 du corpus
s'ouvrent par `cfgrib`, y compris avec la totalité de nos `OPTIONS_CFGRIB`
et les dix-huit clés de `READ_KEYS`. Bissectées une à une, **aucune** ne
fait échouer l'ouverture — pas même `discipline` ni `tablesVersion`, que
l'édition 1 ne possède pourtant pas.

**L'échec vient de notre code, en un point unique.** `file_triplets`
interroge `discipline` sans garde :

```python
seen.add((int(eccodes.codes_get(h, "discipline")), ...))
```

Son `try/finally` libère le handle mais ne rattrape rien ; la
`KeyValueNotFoundError` remonte par `dropped_fields` jusqu'à
`open_granule`. Une garde suffit à rendre la lecture.

## Ce que coûterait la nomenclature, chiffré

Sur les **14 champs distincts** des huit granules d'édition 1 :

| Verdict | Champs | Ce qu'il faut |
|---|---|---|
| `eccodes_direct` | 3 | rien — déjà nommés |
| `eccodes_paramid` | 6 | un second passage hors ligne par `paramId` |
| `sans_nom` | 5 | du travail, et trois causes distinctes |

**`paramId` est le bon axe.** Il vaut la même chose dans les deux
éditions — `167` pour la température à 2 m dans ERA5 comme dans AROME et
CERRA — là où le triplet n'existe qu'en édition 2. Notre correspondance,
entièrement indexée par le triplet, devra donc le porter aussi.

Les cinq sans nom se répartissent en trois causes qui ne se traitent pas
pareil : `tp` d'ERA5, dont le triplet GRIB2 est un code **local**
`(0, 1, 193)` ; `swh` de MFWAM sous un `paramId` qu'ecCodes ignore, voir
X10-DIV-0016 ; et deux champs à `paramId = 0`, de tables locales, que rien
nulle part ne nomme.

**Résidu après travail : deux champs sur quatorze**, tous deux de tables
locales de Météo-France.

## L'ampleur, qui justifie d'en faire un chantier

ERA5 et CAMS chez Copernicus, MFWAM, WaveWatch III et HYCOM2D chez
Météo-France. La réanalyse la plus utilisée au monde, et tout l'océan.

Trois issues, et la décision est prise depuis le 20/10/2026 : **lire**,
plutôt que refuser explicitement ou convertir en amont.
"""

from __future__ import annotations

from datetime import date

from x10_client.probes import Handling, Mode, Nature, Probe, Side, Status

PROBE = Probe(
    identifier="X10-DIV-0013",
    title="X10 cannot read GRIB edition 1, which carries ERA5, CAMS and the whole ocean suite",
    nature=Nature.DIVERGENCE,
    status=Status.CONFIRMED,
    side=Side.X10,
    observed_on=date(2026, 10, 20),
    producer="X10",
    artefact="x10-connectors, grib2.file_triplets et CF_STANDARD_NAMES",
    workaround=(
        "Aucun à ce jour. Le chantier est décidé : une garde dans "
        "`file_triplets` pour la lecture, puis `paramId` comme second axe "
        "d'indexation de la correspondance."
    ),
    handling=Handling.ENDURED,
    mode=Mode.UNTESTED,
    replay_note=(
        "Appeler `grib2.open_granule` sur un granule d'édition 1 ; attendu "
        "`KeyValueNotFoundError` levée par `file_triplets`. Deviendra un test "
        "une fois la garde posée, et une sonde n'a pas à porter un granule."
    ),
)
