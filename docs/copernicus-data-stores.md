# Les magasins de données Copernicus : un jeton, trois catalogues, deux éditions

**Note technique à l'usage d'utilisateurs avertis des données ouvertes
Copernicus.**

> **État constaté le 19 octobre 2026.** Les observations ci-dessous décrivent
> la situation à cette date et **rien ne garantit leur pérennité** : les
> catalogues, les formats et les conditions d'accès évoluent. Toute décision
> durable gagne à rejouer le relevé — la méthode est en fin de note.
>
> Outillage : `ecmwf-datastores-client` 0.5.3, `eccodes` et `cfgrib` de la
> roue du projet.

## Objet

L'ECMWF opère pour l'Union européenne trois magasins de données : le
**Climate Data Store** (CDS), l'**Atmosphere Data Store** (ADS) et l'**Early
Warning Data Store** (EWDS). Cette note suit le chemin qui va de « j'ai un
compte » à « le fichier est exploitable », et s'arrête à chaque endroit où
ce qu'on attend ne correspond pas à ce qu'on obtient.

Le relevé porte sur **172 collections** décrites, **13 granules**
téléchargés sur sept régimes contrastés, et la base de paramètres que
l'ECMWF publie par ailleurs. Il n'épuise pas l'offre : 107 collections sur
172 relèvent d'un régime d'accès distinct, non instruit ici.

---

## 1. Accès : un identifiant, trois magasins

**Un seul jeton d'accès personnel ouvre les trois.** Mesuré : un UUID de
36 caractères, et les profils rendus par CDS et ADS portent le même `sub`,
le même `id` et le même `email`. C'est **une identité, trois catalogues** —
et non trois comptes, comme l'organisation du portail peut le laisser
croire.

**Ce qui diffère d'un magasin à l'autre n'est pas l'identifiant mais
l'acceptation des politiques**, tenue par magasin. ADS et EWDS répondent
`403` en nommant les politiques manquantes, là où un jeton inconnu rendrait
`401`. Lire le premier comme le second fait conclure à deux comptes
distincts ; la distinction se vérifie dans le corps de la réponse, qui porte
le code `900908` et nomme chaque politique.

**Le jeton voyage en en-tête `PRIVATE-TOKEN`**, jamais en paramètre d'URL.

### Un client officiel qui est une façade

La documentation recommande `cdsapi`. Son code montre que
`cdsapi.api.Client` porte un `__new__` qui **aiguille selon la forme de la
clé** :

| Forme de la clé | Classe réellement instanciée | Transport |
|---|---|---|
| contient `:` — ancienne forme `UID:APIKEY` | `cdsapi.api.Client` | HTTP Basic |
| sans `:` — le jeton actuel | `ecmwf.datastores.legacy_client.LegacyClient` | en-tête |

Avec un jeton moderne, ce qui s'exécute **est** `ecmwf-datastores-client`,
que `cdsapi` déclare d'ailleurs en dépendance. Ce ne sont pas deux clients à
départager mais deux noms pour un moteur. Vérifié par
`type(client).__mro__`.

> **Un piège de journalisation dans la branche morte.** Le constructeur de
> l'ancienne classe passe la clé à un journal de débogage. La branche n'est
> atteignable qu'avec une clé à deux-points, donc inatteignable avec un
> jeton actuel — mais elle existe.

**Les deux clients officiels retentent 500 fois à 120 secondes
d'intervalle**, soit plus de seize heures d'attente possibles. Voir
`X10-DIV-0009` au [registre des écarts](divergences-observees.md).

---

## 2. Le catalogue, et ce qu'il déclare

| | CDS | ADS | EWDS |
|---|---|---|---|
| Collections | 144 | 16 | 12 |
| Licences déclarées | 47 | 47 | 46 |

**L'enregistrement de collection est du STAC** — `stac_version`, `assets`,
`extent`, `providers`, `sci:doi`, `summaries`. Trois appels le décrivent
complètement :

| Appel | Ce qu'il rend |
|---|---|
| `get_collection(id).json` | l'enregistrement STAC |
| `.form` | le **vocabulaire de sélection** : variables, niveaux, échéances, formats |
| `.constraints` | les combinaisons valides entre ces axes |

### Sept jetons de format pour trois formats

| Jeton | Collections | Magasins |
|---|---|---|
| `netcdf` | 57 | les trois |
| `grib` | 44 | les trois |
| `csv` | 16 | CDS, ADS |
| `netcdf_zip` | 7 | ADS |
| `grib2` | 5 | EWDS seul |
| `netcdf4` | 1 | CDS |
| `csv_expert` | 1 | ADS |

Le vocabulaire diverge donc **entre magasins d'un même opérateur** : `grib`
ici, `grib2` là.

**49 collections servent GRIB *et* NetCDF.** C'est le gisement qui permet de
confronter une normalisation à deux expressions de la même donnée : ERA5,
ERA5-Land, CARRA, CERRA, et huit jeux CAMS.

### Un vocabulaire de sélection, qui n'est pas celui des fichiers

**1 644 noms de variables distincts** — `2m_temperature`,
`10m_u_component_of_wind` —, dont **954 n'apparaissent que dans une seule
collection**. Ce n'est ni le nom court GRIB ni le nom standard CF.

**Il ne survit pas au téléchargement** : le granule porte `2t`, `t2m`, `tp`.
C'est donc un vocabulaire de **requête**, non de donnée — il n'alourdit pas
la correspondance, mais il faut le traduire pour construire une requête.

Le même axe `variable` est par ailleurs encodé par **trois types de widget**
selon la collection, le dernier imbriquant ses valeurs dans des groupes.
Une lecture naïve en manque 43 sur 172.

---

## 3. Ce que le téléchargement livre réellement

### Le format se détecte aux octets, jamais à l'extension

Une requête ERA5 portant quatre variables de surface, avec
`data_format: "netcdf"` et **`download_format: "unarchived"`**, rend un
fichier dont les quatre premiers octets sont `PK\x03\x04`. Il contient :

```
data_stream-oper_stepType-instant.nc    59 421 o
data_stream-oper_stepType-accum.nc      26 947 o
```

Le service **découpe sa sortie NetCDF par `stepType`** quand une requête
mêle instantané et cumul, là où le GRIB livre un seul fichier. Même requête,
même donnée : un fichier d'un côté, deux de l'autre. Voir `X10-DIV-0006`.

### ERA5 et CAMS sont en GRIB **édition 1**

C'est le fait le plus structurant de la note, et il surprend :

| Jeu | Édition | Identification du paramètre |
|---|---|---|
| ERA5 surface, isobare, ensemble, Land | **1** | `table2Version`, `indicatorOfParameter` |
| CAMS EAC4 | **1** | idem |
| CARRA, CERRA | 2 | triplet, `tablesVersion` 23 |

L'édition 1 ne porte **ni** `discipline`, **ni** `parameterCategory`, **ni**
`parameterNumber`. Toute correspondance indexée par le triplet GRIB2 lui est
donc inapplicable telle quelle. La voie praticable passe par `paramId`, qui
vaut la même chose dans les deux éditions — voir
[triplet-et-tables-grib.md](triplet-et-tables-grib.md) et `X10-DIV-0013`.

### Le coût annoncé n'est pas un volume

`estimate_costs` rend un coût avant soumission, ce qui est une courtoisie
réelle. Il ne mesure pas la taille :

| Jeu | coût GRIB | coût NetCDF | octets GRIB | octets NetCDF |
|---|---|---|---|---|
| ERA5 surface | 4,0 | 24,0 | 20 440 | 86 697 |
| CARRA | **1,0** | **1,0** | 2 713 849 | **23 702 082** |

Sur ERA5 le coût suit le format d'un facteur six ; sur CARRA il annonce la
même valeur des deux côtés pour un facteur **8,7** réel. C'est un plafond de
service, pas une prédiction. Voir `X10-DIV-0014`.

### Les files d'attente se comptent en heures

Une extraction CERRA de quatre champs sur un seul pas de temps a demandé
**4 h 04**. Les autres ont tenu entre 7 et 260 secondes. Un ordonnanceur qui
suppose une réponse en minutes se trompe de deux ordres de grandeur.

---

## 4. La base de paramètres, et ce qu'elle apporte

L'ECMWF publie par ailleurs une base lisible par machine et **libre
d'accès** : `codes.ecmwf.int/parameter-database/api/v1/`. **8 230
paramètres**, trois encodages déclarés — `grib1`, `grib2`, et `netcdf` dont
l'unique clé est `cfName`.

| Combinaison déclarée | Paramètres | |
|---|---|---|
| `grib2` seul | 3 984 | 48,4 % |
| `grib1` + `grib2` | 3 603 | 43,8 % |
| `grib1` seul | 475 | 5,8 % |
| **portant un `cfName`** | **168** | **2,0 %** |

**La colonne CF est quasi vide** — la température à 2 m elle-même n'en a
pas. Ce qui sert est le **pont entre éditions**, à 45,2 %. Voir
`X10-DIV-0015`.

Et le chemin principal n'a pas besoin de ce service : **ecCodes traduit déjà
`paramId` en nom CF hors ligne**, il ne le fait simplement pas sur un
message d'édition 1. Voir `X10-DIV-0017`.

---

## 5. Reproduire ce relevé

Aucun outil particulier, et un identifiant obtenu en s'inscrivant.

```python
from ecmwf.datastores import Client

client = Client(url="https://cds.climate.copernicus.eu/api", key=JETON)
client.check_authentication()  # identité, et politiques manquantes
page = client.get_collections()  # puis page.next jusqu'à épuisement
collection = client.get_collection("reanalysis-era5-single-levels")
collection.json, collection.form, collection.constraints
```

Le format d'un fichier reçu se lit à ses quatre premiers octets :
`PK\x03\x04` pour un ZIP, `CDF\x01` pour un NetCDF classique, `\x89HDF` pour
un NetCDF-4, `GRIB` pour un GRIB — dont l'édition est à l'octet 8.

Les sondes `X10-DIV-0015` et `X10-DIV-0016` rejouent les mesures de la
section 4 sans identifiant ; voir [`probes/`](../probes).

---

## Licence

Les données relèvent de la licence **CC-BY-4.0**, déclarée par chaque
collection dans son enregistrement STAC et reprise dans la provenance de
chaque granule que nous conservons.

---

## Références

- [divergences-observees.md](divergences-observees.md) — le registre des
  écarts, où chaque constat de cette note porte un identifiant.
- [triplet-et-tables-grib.md](triplet-et-tables-grib.md) — pourquoi le
  triplet GRIB2 n'identifie pas un paramètre.
- [standards-et-outillage.md](standards-et-outillage.md) — pourquoi aucune
  autorité ne gouverne la correspondance GRIB vers CF.
- [arome-paquets-et-api-ciblee.md](arome-paquets-et-api-ciblee.md) et
  [meteofrance-portail-api.md](meteofrance-portail-api.md) — l'autre
  producteur, dont plusieurs traits diffèrent sensiblement.
