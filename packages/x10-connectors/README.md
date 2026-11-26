# x10-connectors

**La chaîne ETL de X10** : acquérir chez un producteur, décoder, normaliser,
écrire. C'est le membre le plus lourd du dépôt, et celui qui porte le métier.

## Ce qu'il fait aujourd'hui

| Module | Ce qu'il traite |
|---|---|
| `ecmwf_ifs` | ECMWF IFS open data — téléchargement sélectif par paramètre et par échéance |
| `meteofrance_pnt` | les paquets AROME et ARPEGE republiés en open data, sans authentification |
| `grib2` | décodage GRIB2 vers des tableaux `xarray`, et **le redressement des noms CF** |
| `netcdf_cf` | écriture NetCDF-CF : unité canonique, `cell_methods`, bornes de validité, licence |
| `contract` | le **contrat de sortie**, qui fige la forme et jamais les valeurs |
| `base` | téléchargement, **écriture atomique**, empreintes |
| `observability` | journalisation aux champs Elastic Common Schema |

**Les trois couches sont distinctes et le nommage le dit** : un module
transverse porte un nom fonctionnel, un module de source
`<producteur>_<produit>`, un module de format **le nom du format** et non le
sens de lecture — `netcdf_cf` écrit aujourd'hui, et relira demain.

## Ce qu'il ne fait pas, et ne doit pas faire

- **Il ignore l'existence d'un catalogue.** `x10-connectors` ne dépend pas de
  `x10-catalog` : c'est l'appelant qui résout une entrée et lui transmet
  l'ordre des origines à tenter.
- **Il ne résout aucun secret.** Il en **reçoit** un en paramètre. Le paquet
  fournit le mécanisme, l'application fournit les valeurs — et un test
  vérifie qu'aucun fichier de `packages/*/src` ne lit l'environnement.
- **Il n'ordonnance rien.** X10 est piloté, il ne pilote pas.
- **Il ne devine pas à la place du producteur.** Un champ qu'on lit sans
  savoir le nommer sort avec `standard_name = None` : une absence se voit, un
  nom inventé se propage.

## Installation

Le noyau s'installe **sans pile scientifique**. Ce qui la demande est en
extra, par connecteur :

```bash
pip install x10-connectors              # le noyau, sans dependance lourde
pip install x10-connectors[grib]        # decodage GRIB2 : cfgrib, eccodes, xarray
pip install x10-connectors[ecmwf]       # le client officiel du producteur
```

## Pour aller plus loin

La correspondance GRIB → CF et pourquoi le triplet n'identifie pas un
paramètre : [docs/triplet-et-tables-grib.md](../../docs/triplet-et-tables-grib.md).
Les écarts des sources, datés et rejouables :
[docs/divergences-observees.md](../../docs/divergences-observees.md).
