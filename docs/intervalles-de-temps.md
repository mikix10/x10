# Intervalles de temps : dire sur quelle période porte un champ agrégé

**Note technique à l'usage de qui convertit des champs de prévision du GRIB2
vers le NetCDF-CF.**

> **État constaté le 9 octobre 2026**, avec ecCodes 2.49.0, cfgrib 0.9.15.1 et
> xarray 2026.9.0, sur un granule AROME 0,025° SP1 relevé la veille. Les
> observations décrivent cette date ; **rien ne garantit leur pérennité**. La
> méthode est donnée en fin de note pour les rejouer.

## Objet

Un champ cumulé porte une valeur et une date. La date ne suffit pas : un
cumul n'a pas d'instant de validité, il a une **période**. Dire qu'un champ
vaut 12 mm « à 6 h » ne dit pas si ces douze millimètres sont tombés en une
heure ou en six.

Le risque n'est pas théorique. Relevé sur un granule de surface réel :

| Traitement | Fenêtres déclarées | Lecture |
|---|---|---|
| `accum` — pluie, rayonnement | (0→1), (0→2), (0→3), (0→4), (0→5), (0→6) | **cumul depuis le début du réseau** |
| `max` — rafales | (0→1), (1→2), (2→3), (3→4), (4→5), (5→6) | **maximum de l'heure écoulée** |

Deux champs du même fichier, portant la même date de validité, sur deux
périodes différentes. **Qui lit le cumul de l'échéance 6 h comme « la pluie
de la sixième heure » se trompe d'un facteur six**, et rien dans le fichier
ne l'en avertit.

Cette note établit ce que les conventions permettent d'écrire, ce que les
outils offrent, ce que nos données imposent — et pourquoi la réponse n'est
pas celle qu'on croit d'abord.

---

## 1. Ce que CF exige

### Les bornes de cellule, et leur règle de sommets

CF exprime l'étendue d'une cellule par un **attribut `bounds`** renvoyant à
une variable de bornes. La règle qui décide de tout se lit à la section 7.1 :

> *The vertex dimension must be of size two if the associated variable is
> one-dimensional, and of size greater than two if the associated variable
> has more than one dimension.*

Autrement dit : **seule une coordonnée unidimensionnelle peut porter des
bornes à deux sommets.** Une coordonnée bidimensionnelle en exigerait plus de
deux, ce qui décrit une cellule de surface, pas un intervalle de temps.

### Ce que `cell_methods` peut désigner

La section 7.3 autorise quatre formes de nom : une **dimension** de la
variable, une **coordonnée scalaire**, un **nom standard** valide, ou le mot
`area`. Cette latitude compte, parce que notre axe temporel porte plusieurs
noms selon qu'on regarde la dimension ou la coordonnée.

### Ce que `interval:` ne dit pas

La section 7.3.2 réserve ce champ à *« the typical interval between the
original data values to which the method was applied »* — l'espacement de la
donnée **source** agrégée. L'employer pour la longueur du cumul écrirait une
contre-vérité. Il n'y a pas de raccourci : la période relève des bornes.

---

## 2. Ce que nos données imposent

Trois structures d'intervalle coexistent dans un **même granule**, et deux
d'entre elles dans un **même jeu** une fois décodé :

| Structure | Variables | Longueur de fenêtre |
|---|---|---|
| Cumul depuis l'origine | `tp`, `ssrd`, `tsnowp`, `tgrp` | **variable** — 1 h, puis 2 h… jusqu'à 6 h |
| Glissant d'une heure | `fg10`, `efg10`, `nfg10` | constante, 1 h |
| Ponctuel | `t2m`, `r2`, `u10`, `prmsl` | aucune |

Une seule variable de bornes partagée ne peut pas les servir : à l'échéance
6 h, `tp` couvre [0 h, 6 h] et `fg10` couvre [5 h, 6 h]. **Le problème n'est
donc pas de choisir la bonne coordonnée, mais d'admettre qu'il en faut
plusieurs.**

---

## 3. Ce que `cfgrib` permet, et ce que chaque option coûte

Le paramètre `time_dims` décide de la forme de l'axe temporel. Les trois
valeurs, mesurées :

| `time_dims` | Dimensions obtenues | `valid_time` | Bornes à 2 sommets | Ce qui est perdu |
|---|---|---|---|---|
| `("time", "step")` | `(time, step, …)` | **2D** | **impossibles** | rien |
| `("valid_time",)` | `(valid_time, …)` | 1D, `standard_name = "time"` | possibles | **date de réseau et échéance**, coordonnées *et* attributs |
| `("step",)` | `(step, …)` | absent | possibles sur `step` | la date de validité |

La deuxième ligne mérite une insistance : avec `("valid_time",)`, seuls
`GRIB_stepType` et `GRIB_stepUnits` subsistent. **On ne peut plus dire de
quel réseau vient un champ**, ce qui disqualifie l'option pour un système de
prévision — et plus encore pour un système dont la provenance est une
exigence.

---

## 4. Un obstacle que nous nous sommes créé

Le caractère bidimensionnel de `valid_time` n'est pas une fatalité du format.
Il découle d'un réglage, et c'est le nôtre :

| `squeeze` | `valid_time` | Bornes à 2 sommets |
|---|---|---|
| `True` (défaut de `cfgrib`) | 1D, dimensions `(step,)` | **légales** |
| `False` (notre choix) | 2D, dimensions `(time, step)` | **illégales** |

`squeeze=False` a été adopté pour que la structure cesse de dépendre du
contenu du fichier — un granule à une échéance rendait trois axes, un granule
à deux en rendait quatre. Ce choix reste le bon ; mais il faut savoir qu'il
**ferme la voie la plus directe** vers les bornes temporelles.

Revenir en arrière échangerait un défaut contre un autre. La solution est
ailleurs.

---

## 5. Ce que fait Unidata, et pourquoi c'est la bonne réponse

Le lecteur GRIB de netCDF-Java traite ce cas depuis des années, et sa
documentation est explicite :

> *GRIB makes extensive use of time intervals as coordinates. By following CF
> Cell Boundaries, time interval coordinates use an auxiliary coordinate to
> describe the intervals. […] a coordinate named `time1(30)` will have an
> auxiliary coordinate `time1_bounds(30,2)` containing the lower and upper
> bounds of the time interval for each coordinate.*

Et sur le point qui bloquait :

> *GRIDs that require another set of times (mixed interval variables, for
> example) will be assigned "time2", "time3", etc.*

**La réponse n'est pas de choisir une coordonnée, c'est d'en créer
plusieurs** : une par structure d'intervalle distincte, chacune
unidimensionnelle, chacune avec ses bornes à deux sommets — toutes
parfaitement légales au regard de la règle de sommets.

Le modèle de données commun d'Unidata distingue par ailleurs le *run time* du
*forecast time*, et n'emploie un axe temporel bidimensionnel que pour une
**collection de réseaux**. Pour un réseau unique — notre cas, puisqu'un
granule appartient à un réseau — la date de réseau est une **coordonnée
scalaire**, ce qui la conserve sans imposer une dimension.

### Un point où nous divergeons, délibérément

Unidata encode la structure dans le **nom de variable** :
`12_hour_Accumulation`, `Mixed_intervals_Accumulation`. Nous ne le reprenons
pas. Nos noms viennent du tableau CF et du producteur ; les réécrire romprait
la correspondance que nous avons établie, et lierait notre sortie à la
convention d'un outil plutôt qu'à un standard. L'information est déjà portée
par `cell_methods` et par les bornes, qui sont, eux, normalisés.

---

## 6. L'approche retenue

| Élément | Forme |
|---|---|
| Date de réseau | coordonnée **scalaire** — la provenance est conservée sans coûter une dimension |
| Axes temporels | **un par structure d'intervalle**, unidimensionnels |
| Bornes | une variable `…_bnds(n, 2)` par axe |
| `cell_methods` | inchangé dans son vocabulaire, désormais **relié** à des bornes |
| Noms de variables | **inchangés** — ni suffixe ni encodage de structure |

Les champs ponctuels n'ont pas de bornes : une valeur instantanée n'a pas
d'étendue, et `time: point` le dit déjà.

### Mis en œuvre, et une surprise en chemin

Depuis le 9 octobre 2026. Deux points méritent d'être ajoutés à l'analyse
qui précède, parce que la mise en œuvre les a révélés.

**La longueur de fenêtre ne peut pas se lire dans un attribut.** `cfgrib`
prend ses attributs au **premier message** du groupe. Sur des fenêtres
variables — les cumuls croissent de une à six heures — l'attribut rend `1`
pour les six échéances, et des bornes bâties dessus seraient fausses à cinq
reprises sur six. Il faut la remonter en **coordonnée**, ce que permet
l'option `extra_coords`.

**Et cette option résout d'elle-même le problème des axes multiples.** La
coordonnée distingue les hypercubes : `cfgrib` sépare désormais les cumuls
des instantanés qu'il réunissait. Sur le granule mesuré, cinq jeux deviennent
six, et **chacun est homogène en structure d'intervalle**. Puisque nous
écrivons un fichier par jeu, chaque fichier n'a qu'un seul axe temporel — et
la solution d'Unidata, plusieurs axes dans un même fichier, devient inutile.
Elle reste la bonne réponse pour un serveur de collection comme THREDDS ;
elle ne l'est pas pour qui produit des fichiers.

Résultat sur le granule réel, dernière échéance :

| Champs | `cell_methods` | Fenêtre |
|---|---|---|
| rafales | `time: maximum` | 17 h → 18 h |
| cumuls | `time: sum` | **12 h → 18 h** |

Même date de validité, six heures d'écart. C'était l'objet de cette note.

---

## 7. Comment rejouer ces vérifications

| Vérification | Méthode |
|---|---|
| Règle de sommets | lire la section 7.1 des conventions CF |
| Ce que `cell_methods` peut désigner | section 7.3 |
| Ce que `interval:` signifie | section 7.3.2 |
| Effet de `time_dims` | ouvrir un même granule avec les trois valeurs et comparer les dimensions, puis les attributs survivants |
| Effet de `squeeze` sur la dimension de `valid_time` | même granule, les deux valeurs |
| Structures d'intervalle réelles | relire `startStep`, `endStep`, `lengthOfTimeRange` et `indicatorOfUnitForTimeRange` sur chaque message d'un granule de surface |

---

## Références

| Ressource | Adresse |
|---|---|
| Conventions CF, sections 7.1 et 7.3 | <https://cfconventions.org/cf-conventions/cf-conventions.html> |
| Sources des conventions CF | <https://github.com/cf-convention/cf-conventions> |
| Fichiers GRIB dans le modèle de données commun | <https://docs.unidata.ucar.edu/netcdf-java/current/userguide/grib_files_cdm.html> |
| Collections GRIB | <https://docs.unidata.ucar.edu/netcdf-java/5.9/userguide/grib_feature_collections_ref.html> |
| Agrégation de collections de réseaux | <https://docs.unidata.ucar.edu/netcdf-java/dev/userguide/fmrc_ref.html> |
| cfgrib | <https://github.com/ecmwf/cfgrib> |
| Table 4.10 du format GRIB2 | <https://codes.ecmwf.int/grib/format/grib2/ctables/4/10/> |

Rien de ce qui précède n'aurait pu être établi sans les conventions, les
documentations et les codes que ces équipes publient librement. Qu'elles en
soient ici remerciées.

---

## Décisions arrêtées, déplacées du guide le 20/11/2026

*Elles occupaient la moitié d'un fichier relu à chaque session. Le guide
y renvoie désormais ; le texte est inchangé.*

- **La nature du traitement statistique est déclarée.** Décodés, un cumul et un instantané ont mêmes dimensions, même unité, mêmes coordonnées : sans `cell_methods`, rien ne les distingue et un consommateur moyenne des cumuls — la faute même écartée sur les directions de vent. `netcdf_cf.CELL_METHODS` traduit les huit `stepType` qu'ecCodes tire de la table 4.10, **chaque méthode vérifiée présente au tableau E.1 de CF**, et la résolution se fait **par variable**. `WITHOUT_CELL_METHOD` recense les quatre que CF ne couvre pas — `diff`, `cov`, `ratio`, `stdanom` —, et un `stepType` inconnu **lève** : se taire produirait un cumul qui se présente comme un instantané.
  **Deux points de lecture de CF.** Le `time` de `time: sum` est le **nom standard**, ce que la section 7.3 autorise, et non la dimension `time` qui porte chez `cfgrib` la date de réseau — la coordonnée concernée est `valid_time`. Et **`interval:` ne dit pas la période de cumul** : la section 7.3.2 s'en sert pour l'espacement de la donnée source agrégée. L'employer ainsi écrirait une contre-vérité.

- **Un jeu `cfgrib` n'est pas homogène en traitement statistique.** Le découpage en plusieurs jeux se fait par **forme d'hypercube**, pas par `stepType` : mesuré le 08/10/2026 sur un paquet AROME de surface réel, où un même jeu réunit quatre champs cumulés et un instantané. Une méthode de cellule par jeu y serait fausse. Les fixtures ne le montraient pas — elles ne produisent que des jeux homogènes —, et c'est la **seconde fois** qu'un fichier du producteur corrige une hypothèse que les tests hors ligne confortaient, après l'unité `J m**-2`. Le test marqué `network` vérifie désormais la résolution par variable, la présence du référentiel, et que le paquet porte bien les trois traitements attendus.
  Au même relevé : **18 messages sur 97 portent un maximum**, statistique non linéaire sur grille rééchantillonnée. Et le convertisseur officiel `cfgrib to_netcdf` **échoue** sur ce fichier — niveaux 2 m et 10 m dans un hypercube unique —, le fichier partiel qu'il laisse ne portant ni `cell_methods` ni `grid_mapping`.

- **La période des champs agrégés est déclarée.** `cell_methods` dit la nature du traitement, pas la durée sur laquelle il porte.
  **Le fond du problème n'est pas l'implémentation.** Une **date** ne peut pas représenter un **intervalle** : un cumul sur [0, 6 h] n'a pas de date de validité, il a une période. Or la chaîne de décodage ne produit qu'un `valid_time` scalaire, qui vaut la **fin de l'échéance** et non l'étendue de validité du champ. Le défaut est donc dans la représentation, pas dans une clé manquante : CF y répond par des **bornes de coordonnée**, que `GRIB_lengthOfTimeRange` et `indicatorOfUnitForTimeRange` permettraient de construire.
  Conséquence pratique mesurée le 08/10/2026 : les cumuls AROME courent depuis le début du réseau — (0→1), (0→2), … (0→6) — tandis que les maxima portent sur l'heure écoulée. Deux champs du même fichier, portant le même `valid_time`, n'ont pas la même période de validité.
  **Fait.** Enquête, mesures et références **ci-dessus**. `netcdf_cf.cf_shape` réduit l'axe de réseau en **coordonnée scalaire** — cinq dimensions deviennent quatre, rien n'est perdu — et `netcdf_cf.time_bounds` en déduit les bornes. Vérifié le 09/10/2026 sur un granule réel : les rafales portent (17 h → 18 h) à la dernière échéance, les cumuls (12 h → 18 h). La distinction est enfin dans le fichier.
  **La longueur de fenêtre se lit en coordonnée, jamais en attribut.** `cfgrib` prend l'attribut au **premier message** : sur des fenêtres variables — les cumuls AROME croissent de une à six heures — il rend `1` partout, et les bornes seraient fausses à cinq échéances sur six. D'où `extra_coords` dans `OPTIONS_CFGRIB`, dix-septième des dix-huit options.
  **Effet de bord bienvenu** : la coordonnée distingue les hypercubes, donc `cfgrib` sépare désormais cumuls et instantanés qu'il réunissait — cinq jeux deviennent six sur un granule de surface, et **chacun est homogène en structure d'intervalle**. Le découpage que nous allions coder vient d'une option.
  **Deux garde-fous.** Les unités de durée variable — mois, année — **lèvent** plutôt que de produire une fenêtre fausse selon la date ; et la valeur `'undef'` que `cfgrib` pose sur un champ sans intervalle est une **chaîne**, pas un manquant, donc traitée nommément.
  La solution d'Unidata — plusieurs axes temporels dans un fichier — n'a pas été reprise : elle convient à THREDDS qui sert une collection, alors que nous écrivons **un fichier par jeu**, chacun n'ayant dès lors qu'un seul axe.
