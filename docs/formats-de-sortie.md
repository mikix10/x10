# Formats de sortie : NetCDF-4, compression et interopérabilité

**Note technique à l'usage de qui diffuse des champs météorologiques, ou
cherche à les consommer avec un outillage contraint.**

> **État constaté le 9 octobre 2026**, avec netCDF4 1.7.4 (libnetcdf 4.9.3),
> xarray 2026.9.0, cfgrib 0.9.15.1, et le manuel de CDO 2.6.4. Mesures faites
> sur un granule AROME 0,025° de surface. Les observations décrivent cette
> date ; **rien ne garantit leur pérennité**.

## Objet

Écrire du NetCDF suppose trois choix que rien n'impose et que peu de monde
explicite : **quel modèle de données**, **quelle compression**, et **quel
découpage**. S'y ajoute une question qu'on ne se pose qu'au moment de
diffuser : **sous quel type de média** servir le fichier.

Cette note établit par la mesure ce que chacun coûte et ce qu'il permet, et
ce que les producteurs de référence ont eux-mêmes retenu. Elle corrige au
passage trois idées reçues, dont deux que l'auteur de ces lignes avançait une
heure plus tôt.

---

## 1. Types de média : le classement n'est pas celui qu'on croit

Relevé dans le registre IANA des types de média.

| Format | Type enregistré | Depuis | Arbre |
|---|---|---|---|
| **GRIB** | `application/grib` | **5 juillet 2024** | **standards**, déposé par l'OMM |
| **HDF5** | `application/vnd.hdfgroup.hdf5` | **17 mars 2026** | vendeur, The HDF Group |
| HDF4 | `application/vnd.hdfgroup.hdf4` | — | vendeur |
| **NetCDF** | *aucun* | — | — |

Le classement surprend : GRIB occupe l'arbre des **standards**, sans préfixe
de vendeur, quand HDF5 n'a obtenu qu'une entrée **vendeur** en mars 2026 et
que NetCDF n'y figure pas.

### Mais l'enregistrement de GRIB ne décrit pas un fichier

La fiche elle-même l'indique, et c'est le point le plus instructif de ce
relevé :

```
Required parameters:     edition=3
Published specification: Manual on Codes (WMO-No. 306), Volume I.2
                         FM 92–XIV GRIB
Magic number(s):   N/A
File extension(s): N/A
Person to contact: (equipe WIS 2.0 de l'OMM)
```

**Ni extension de fichier, ni nombre magique.** L'omission n'est pas un
oubli : un message GRIB commence bien par les octets `GRIB` et se termine par
`7777`, donc le nombre magique existe. Le déclarer « N/A » revient à dire que
**ce n'est pas un format de fichier qui est enregistré**, mais la forme de
code — le *message*. Ce que GRIB normalise, en effet : l'OMM ne définit pas
de conteneur, et ce qu'on appelle couramment « un fichier GRIB » n'est qu'une
concaténation de messages, sans structure propre.

Le contact déclaré donne la raison d'être : l'équipe **WIS 2.0** de
l'OMM. Un type de média y sert à déclarer, dans les liens d'un message
de notification, ce qui va être transféré. C'est un usage de **protocole**,
pas d'identification de fichier sur disque — et l'enregistrement s'éclaire
entièrement vu ainsi.

> Une tension non résolue, signalée pour ce qu'elle vaut : le paramètre
> requis nomme l'**édition 3**, alors que la spécification citée est le
> chapitre **FM 92** du Manuel des codes. La formulation de la fiche — *where
> edition is the parameter name and 3 is the value of the parameter* — se lit
> aussi bien comme un exemple de syntaxe que comme une valeur imposée.

### Ce que cela change en pratique

Un fichier NetCDF-4 **est** un fichier HDF5 : il peut donc légitimement être
servi en `application/vnd.hdfgroup.hdf5`. Mais ce type ne dit rien de la
sémantique NetCDF, et encore moins des conventions CF. Les types
`application/netcdf` et `application/x-netcdf` sont d'usage courant et
**n'ont aucune existence au registre**.

Aucun des trois formats ne dispose donc d'un type qui désigne sans ambiguïté
*un fichier de ce format* : GRIB enregistre une forme de code pour un usage
de protocole, HDF5 désigne un conteneur sans rien dire de son contenu, et
NetCDF n'a rien. C'est une information utile à qui conçoit une interface de
diffusion, et une raison de ne pas faire reposer la négociation de contenu
sur le seul type de média.

---

## 2. NetCDF-4 ou modèle classique : la question est mal posée

On lit souvent que les outils classiques exigent le « modèle de données
classique ». L'introduction du manuel de CDO le dit en effet :

> *NetCDF datasets are only supported for the classic data model and arrays
> up to 4 dimensions.*

Mais la liste des formats d'entrée-sortie du même manuel contredit la lecture
littérale qu'on en fait :

| Code | Format |
|---|---|
| `nc1` | NetCDF |
| `nc2` | NetCDF 64 bits |
| **`nc4`** | **NetCDF-4 (HDF5)** |
| `nc4c` | NetCDF-4 classique |
| `nc5` | NetCDF version 5 |

CDO lit et écrit donc le **format** NetCDF-4, avec ses options propres de
découpage et de filtres. Le « modèle classique » vise les **fonctionnalités**,
et le manuel n'en nomme qu'une :

> *NetCDF-4 added support for hierarchical groups. **Groups are not
> compatible with the NetCDF classic data model.** If the dataset contains
> more than one group, use the `group` key to select just one of them.*

**Conclusion** : NetCDF-4 en s'interdisant les **groupes** est le compromis
juste. Il n'y a pas lieu de se rabattre sur `NETCDF4_CLASSIC`, qui
restreindrait en plus les entiers 64 bits, les chaînes et les types non
signés — sans contrepartie.

> Une bibliothèque qui n'écrit pas de groupe sans qu'on le lui demande rend
> cette conformité gratuite. Elle mérite néanmoins d'être **vérifiée par un
> test** plutôt que supposée : c'est une propriété du fichier produit, pas une
> intention.

---

## 3. Ce que les producteurs ont retenu

| Chaîne | Format |
|---|---|
| `grib_to_netcdf`, l'outil historique | défaut `-k 2` : NetCDF3 64 bits classique |
| **Nouveau CDS Copernicus** | **cfgrib → NetCDF-4**, « including compression options » |
| CEMS-Flood | « version 4 data model (NetCDF-4) and CF 1.7 » |
| Ancien CDS, maintenu | `"data_format": "netcdf_legacy"` → NetCDF3 |

Le mouvement va donc **vers** NetCDF-4, et la compression y est citée comme
motif. Fait notable : le nouveau CDS emploie **cfgrib**, c'est-à-dire la même
pile que celle décrite ici.

### Le précédent qui compte : servir, puis convertir

Le CDS n'a pas dégradé son format de stockage pour les consommateurs
contraints. Il a adopté le format moderne **et conservé une voie de
conversion** explicite, `netcdf_legacy`, pour qui a besoin de NetCDF3.

C'est la séparation à retenir : **la fidélité au stockage, l'adaptation à la
diffusion**. Un format de stockage choisi pour satisfaire l'outil le plus
ancien perd de l'information pour tout le monde ; une conversion à la demande
n'en perd pour personne.

---

## 4. Compression et découpage : inséparables, mais pas pour la raison qu'on croit

### Ils sont techniquement liés

| Configuration | Taille | Découpage |
|---|---|---|
| sans compression | **42,97 Mio** | contigu |
| zlib 4, découpage automatique | **12,80 Mio** | `[4, 1, 359, 561]` |
| zlib 4, un bloc par échéance | 12,84 Mio | `[1, 1, 717, 1121]` |
| zlib 6, un bloc par échéance | 12,61 Mio | — |

Mesuré sur deux variables réelles, sept échéances, grille 717 × 1121.

**Sans compression, le stockage est contigu ; l'activer force le
découpage.** On ne choisit donc pas l'un sans l'autre : HDF5 ne sait
compresser que des blocs.

### Mais la forme des blocs ne décide pas de la taille

C'est le résultat contre-intuitif de ce relevé. Sur données réelles, le
découpage automatique fait **marginalement mieux** qu'un bloc par échéance.
Passer du niveau 4 au niveau 6 gagne 2 %.

> **Correction.** La même mesure sur un champ **synthétique lisse** donnait un
> gain de 40 % au découpage manuel. C'était un artefact : une donnée trop
> régulière se comprime d'une façon qui ne ressemble en rien à un champ
> météorologique. Mesurer sur du réel a renversé la conclusion.

Le gain de la compression, lui, est franc : **facteur 3,4**.

### La forme des blocs se choisit pour la lecture

Puisqu'elle ne change pas la taille, elle n'a qu'un seul effet : la quantité
lue pour satisfaire une requête.

| Motif de lecture | Découpage adapté |
|---|---|
| un champ entier à une échéance | un bloc par échéance |
| une série temporelle en un point | blocs petits en espace, longs en temps |
| un sous-domaine sur toutes les échéances | blocs couvrant le sous-domaine |

Il n'y a pas de forme universelle : **le découpage encode une hypothèse sur
l'usage**. À défaut de connaître celui-ci, le découpage automatique est un
choix défendable, et la mesure montre qu'il ne coûte rien en volume.

---

## 5. Et si la cible devient Zarr ?

La question se pose avant de régler quoi que ce soit, puisqu'un choix fait
aujourd'hui pour préparer demain serait du travail perdu s'il ne se
transmettait pas. Mesuré sur le même jeu réel, converti par `xarray`.

### Rien ne se transmet, et c'est la réponse

| | NetCDF-4 écrit | Zarr obtenu |
|---|---|---|
| Découpage | `[4, 1, 359, 561]` | **`[2, 1, 180, 561]`** |
| Codec | zlib niveau 4 | **zstd** |
| Fichiers | 1 | **79** |

Zarr **réencode depuis la structure logique** : il n'hérite ni de la forme
des blocs ni du codec. **Régler aujourd'hui le découpage d'un NetCDF pour
préparer une migration Zarr n'aurait donc aucun effet.** Les deux réglages
sont locaux à leur conteneur.

Ce qui se transmet, en revanche, est **la structure** — dimensions,
coordonnées, attributs, valeurs, dates. Aller-retour vérifié exact, y compris
la coordonnée scalaire de date de réseau. C'est précisément ce que le contrat
de sortie surveille, et cela traverse donc le changement de conteneur.

### Les défauts de Zarr sont plus faibles, pas le format

| Configuration | Taille |
|---|---|
| Zarr, défauts | 17,02 Mio |
| Zarr, un bloc par échéance | 17,09 Mio |
| Zarr, zstd niveau 9 | 15,36 Mio |
| **Zarr, blosc zstd 5 + mélange d'octets** | **12,87 Mio** |
| **Zarr, blosc zstd 9 + mélange de bits** | **11,48 Mio** |
| *NetCDF-4, zlib 4* | *12,80 Mio* |

L'écart initial de 33 % ne venait pas du conteneur mais d'un **codec
manquant** : `netCDF4` active le **mélange d'octets** d'office avec zlib,
Zarr non. Rétabli, Zarr égale NetCDF ; en mélange de bits, il le dépasse de
10 %.

> La leçon dépasse Zarr : sur des flottants, le mélange d'octets pèse plus
> que le niveau de compression. Passer de zstd 9 sans mélange à zstd 5 avec
> mélange gagne 16 %, là où monter de 5 à 9 n'en gagne que 2.

### Le coût propre à Zarr : le nombre d'objets

Un NetCDF est **un** fichier ; le même jeu en Zarr en compte **79** par
défaut, 29 avec un bloc par échéance, 17 avec un bloc unique. Sur un stockage
objet, ce sont autant de requêtes, et c'est là que la forme des blocs cesse
d'être neutre — non pour le volume, mais pour le nombre d'accès.

C'est la seule contrainte que Zarr ajoute vraiment. Elle ne concerne pas le
format NetCDF que nous écrivons aujourd'hui.

---

## 6. La limite des quatre dimensions

L'autre contrainte de CDO, celle-là bien réelle :

> *arrays up to 4 dimensions. These dimensions should only be used by the
> horizontal and vertical grid and the time.*

Une sortie portant `(time, step, niveau, latitude, longitude)` en compte
**cinq** — la date de réseau et l'échéance étant deux axes temporels.

La remise en forme qui ramène à quatre consiste à faire de la date de réseau
une **coordonnée scalaire** plutôt qu'une dimension de longueur 1, et à
porter l'axe sur la date de validité. Mesuré : elle donne exactement
`(valid_time, niveau, latitude, longitude)`, et **ne perd rien** — la date de
réseau conserve sa valeur.

**Mais sa justification principale n'est pas CDO.** Les conventions CF
n'autorisent des bornes de cellule à deux sommets que sur une coordonnée
**unidimensionnelle** ; un axe temporel 2D ne peut donc pas porter la période
d'un champ cumulé. La compatibilité avec CDO n'est qu'un effet secondaire
d'un changement que CF impose par ailleurs. Voir
[docs/intervalles-de-temps.md](intervalles-de-temps.md).

---

## 7. Comment rejouer ces vérifications

| Vérification | Méthode |
|---|---|
| Types de média | télécharger le registre IANA des types de média et y chercher `hdf`, `netcdf`, `grib` |
| Portée d'un enregistrement | lire la **fiche** du type, pas la seule ligne du registre : les champs *magic number* et *file extension* disent s'il s'agit d'un format de fichier |
| Formats lus par CDO | la table des formats de son manuel, et la section sur le mot-clé `group` |
| Choix des producteurs | documentation de `grib_to_netcdf`, annonces de migration du CDS |
| Compression et découpage | écrire un même jeu réel avec et sans `zlib`, relire `chunking()` et `filters()` |
| Dimensions après remise en forme | écraser l'axe de réseau, basculer l'axe sur la date de validité, compter les dimensions |
| Ce que Zarr hérite du NetCDF | convertir un jeu déjà écrit, puis relire la forme des blocs et les codecs obtenus |

**Un avertissement de méthode** : ne pas mesurer la compression sur un champ
synthétique. Une donnée lisse se comprime d'une façon qui ne prédit rien du
comportement réel, et conduit à des conclusions inverses.

---

## Références

| Ressource | Adresse |
|---|---|
| Registre IANA des types de média | <https://www.iana.org/assignments/media-types/media-types.xhtml> |
| CDO, manuel | <https://code.mpimet.mpg.de/projects/cdo/> |
| `grib_to_netcdf` | <https://confluence.ecmwf.int/display/ECC/grib_to_netcdf> |
| Conversion GRIB vers netCDF sur le nouveau CDS | <https://confluence.ecmwf.int/display/CKB/GRIB+to+netCDF+conversion+on+new+CDS+and+ADS+systems> |
| Conventions CF | <https://cfconventions.org/cf-conventions/cf-conventions.html> |
| Modèle de données NetCDF | <https://docs.unidata.ucar.edu/netcdf-c/current/> |

Rien de ce qui précède n'aurait pu être établi sans les manuels, les
registres et les codes que ces organismes publient librement. Qu'ils en
soient ici remerciés.
