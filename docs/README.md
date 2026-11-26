# Les notes techniques de X10

**Chaque note porte les décisions arrêtées de son sujet, avec la mesure et la
date qui les fondent.** Elles ne décrivent pas le code — le code se lit — mais
**pourquoi il est ainsi**, et ce qui a été écarté.

> **À consulter avant de trancher dans un domaine couvert ici.** La plupart
> des questions qui s'y posent ont déjà reçu une réponse mesurée, et la
> rouvrir sans mesure nouvelle est précisément ce que le critère C2 écarte.

## Par sujet

| Note | Ce qu'elle tranche |
| [socle-et-paquetage](socle-et-paquetage.md) | Python, Pydantic, volumétrie, build, langue, journalisation ECS, écriture atomique, lexique public |
| [catalogue](catalogue.md) | les deux vues, la gradation, l'inventaire dérivé, les facettes, les origines |
| [sources-et-acces](sources-et-acces.md) | ECMWF, Météo-France, plages d'octets, place d'un secret, cadence |
| [triplet-et-tables-grib](triplet-et-tables-grib.md) | la correspondance GRIB vers CF, les versions de tables, les deux contrôles |
| [formats-de-sortie](formats-de-sortie.md) | NetCDF-CF, options de `cfgrib`, référentiel géodésique, compression |
| [tests-et-couverture](tests-et-couverture.md) | corpus hors ligne, deux vues de couverture, contrat de sortie, signatures, CodeQL |
| [vocabulaire](vocabulaire.md) | DCAT, PROV-O, INSPIRE, licence contre droits d'accès, le mot `granule` |
| [agregation-et-reechantillonnage](agregation-et-reechantillonnage.md) | composantes vectorielles, méthode par axe, ce qu'on refuse d'hériter |
| [intervalles-de-temps](intervalles-de-temps.md) | `cell_methods`, périodes d'agrégation, hypercubes non homogènes |
| [unites-et-interoperabilite](unites-et-interoperabilite.md) | la forme canonique d'UDUNITS, et sa validation |
| [standards-et-outillage](standards-et-outillage.md) | le modèle LinkML de la chaîne, et les vocabulaires ajoutés |
| [divergences-observees](divergences-observees.md) | le registre engendré depuis les sondes, et ce qu'une sonde établit |

## Les relevés par source

Établis **par la mesure et non par le descriptif du producteur** — ce qu'une
source sert réellement, et où elle s'écarte de ce qu'elle annonce.

| Note | Source |
|---|---|
| [arome-paquets-et-api-ciblee](arome-paquets-et-api-ciblee.md) | AROME 0,025°, les deux voies d'accès |
| [arpege-paquets-et-api-ciblee](arpege-paquets-et-api-ciblee.md) | ARPEGE, aux deux résolutions |
| [meteofrance-portail-api](meteofrance-portail-api.md) | le portail d'API et ses services |
| [copernicus-data-stores](copernicus-data-stores.md) | CDS, ADS et EWDS — un jeton, trois catalogues |

## Deux fichiers engendrés, jamais tenus à la main

`divergences.tsv` est régénéré depuis les sondes de `probes/`, et
`standards-et-outillage.yaml` porte le modèle LinkML de la chaîne. Les
modifier à la main serait rendre faux le test qui les vérifie.
