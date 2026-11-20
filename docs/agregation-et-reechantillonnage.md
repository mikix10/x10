# Agrégation statistique et rééchantillonnage : ce qu'un champ déclare, et ce que l'interpolation en fait

**Note technique à l'usage de qui convertit ou consomme des champs
météorologiques maillés.**

> **État constaté le 8 octobre 2026**, avec ecCodes 2.49.0, cfgrib 0.9.15.1 et
> les documentations publiques citées en fin de note. Les observations
> décrivent cette date ; **rien ne garantit leur pérennité**. La méthode est
> donnée pour pouvoir les rejouer.

## Objet

Un champ de prévision n'est pas une grille de nombres neutres. Il porte deux
propriétés que rien n'affiche :

- **la nature de son agrégation dans le temps** — valeur instantanée, cumul
  sur trois heures, maximum sur la période ;
- **le rapport entre sa valeur et la maille** — échantillon en un point, ou
  moyenne sur la surface de la cellule.

La première est déclarée par le GRIB. La seconde ne l'est pas. Et entre le
calcul du modèle et le fichier qu'on télécharge, **une interpolation est
intervenue**, dont le fichier ne dit rien non plus.

Cette note établit ce que l'interpolation conserve, ce qu'elle détruit, ce
que les conventions permettent de déclarer, et ce que les outils de la
chaîne font réellement. Elle se termine par la règle qu'on en tire.

---

## 1. Les champs diffusés sont rééchantillonnés

Ce n'est pas un détail d'implémentation, c'est le cas général.

| Modèle | Grille de calcul | Grille diffusée |
|---|---|---|
| IFS haute résolution | gaussienne réduite **octaédrique** O1280, ≈ 9 km | latitude-longitude régulière, 0,25° |
| AROME | Lambert conforme, 1,3 km | latitude-longitude régulière, 0,025° |
| ARPEGE | gaussienne étirée et basculée | latitude-longitude régulière, 0,1° ou 0,25° |

L'ECMWF l'écrit sans détour à propos de ses propres diffusions : les grilles
régulières *« will be interpolated from the values on the octahedral reduced
Gaussian model grid »*.

**Conséquence** : la valeur qu'on lit n'est jamais celle que le modèle a
calculée. C'est une estimation, en un point où le modèle n'a rien calculé,
obtenue par une méthode que le fichier ne nomme pas.

---

## 2. L'axe porteur de la statistique décide de tout

C'est le point central, et il n'est pas une commodité de présentation : les
conventions CF l'énoncent explicitement.

> *« It must be remembered that the method applies only to the axis designated
> in `cell_methods` by name, and different methods may apply to other axes. »*

Une méthode de cellule est une affirmation **sur un axe donné**. La syntaxe le
reflète — une liste de couples `nom: méthode` séparés par des blancs, par
exemple `lon: maximum time: mean`. Dès lors, une transformation appliquée
selon un axe ne peut altérer que les méthodes déclarées **sur cet axe**.

Un rééchantillonnage géographique agit sur les axes d'espace. Il redéfinit
les mailles : une valeur qui était la moyenne sur la maille native n'est la
moyenne d'aucune maille de la grille d'arrivée. **Le sens de l'affirmation
change.** En revanche il ne touche pas à l'axe du temps : la fenêtre
[t₀, t₀+3 h] reste la même fenêtre au point interpolé. Seule la **valeur**
peut s'en trouver dégradée.

L'illustration la plus parlante est la précipitation. Un cumul exprimé en
millimètres porte potentiellement **deux** statistiques : une somme sur le
temps, et une moyenne sur la surface de la maille. Interpoler
géographiquement rompt la seconde, pas la première. Et une intensité en
millimètres par heure, qui ne porte aucune agrégation temporelle,
s'interpole sous la seule hypothèse de continuité spatiale — il n'y a là
aucune méthode statistique à briser.

### Les deux axes ne sont pas dans la même situation

Relevé le 8 octobre 2026 sur un paquet AROME de surface réel.

| | Axe du temps | Axes d'espace |
|---|---|---|
| L'axe est-il rééchantillonné à la diffusion ? | **non** — fenêtres exactes, en heures entières, explicitement déclarées | **oui, toujours** — de la grille native vers une latitude-longitude régulière |
| Le GRIB déclare-t-il la statistique ? | **oui**, table 4.10, exposée en clé `stepType` | **non** — le gabarit 4.15 et la table 4.15 existent pour cela et **ne sont pas employés** |
| Effet d'une interpolation spatiale | la **valeur** seule, et seulement pour les méthodes non linéaires | le **sens** : la maille n'est plus la même |

Les gabarits de produit effectivement rencontrés dans le fichier sont `4.0`
pour les 55 champs instantanés et `4.8` — traitement statistique sur un
intervalle de temps — pour les 42 autres. Aucune des clés
`spatialProcessing`, `typeOfSpatialProcessing` ou `numberOfPointsUsed` n'est
présente sur un seul message.

**Deux conséquences distinctes, qu'il faut séparer.** La première est qu'une
méthode spatiale serait rompue par le rééchantillonnage. La seconde, plus
simple et plus décisive, est que **nous n'en savons rien** : le producteur ne
déclare pas si une valeur est une moyenne de maille ou un échantillon
ponctuel. On peut le supposer par la physique — c'est d'ailleurs l'hypothèse
que fait tout remaillage conservatif —, mais supposer n'est pas déclarer.

### Les fenêtres temporelles, mesurées

Le pendant temporel du relevé de grille. Pour chaque champ agrégé du paquet :
début, fin et longueur de la période, en heures.

| Traitement | Fenêtres déclarées | Lecture |
|---|---|---|
| `accum` | (0→1), (0→2), (0→3), (0→4), (0→5), (0→6) | **cumul depuis le début du réseau** |
| `max` | (0→1), (1→2), (2→3), (3→4), (4→5), (5→6) | **maximum par heure**, fenêtres jointives |

Deux enseignements.

**L'axe du temps n'est pas interpolé.** Les bornes sont des heures entières,
exactes et contiguës ; rien n'indique un rééchantillonnage temporel. L'axe
est **échantillonné**, pas interpolé — à l'inverse exact de l'axe d'espace.

**Et les deux traitements n'ont pas la même convention de fenêtre.** Les
cumuls courent depuis l'origine du réseau, les maxima portent sur l'heure
écoulée. Qui lirait le cumul de l'échéance 6 h comme « la pluie de la sixième
heure » se tromperait d'un facteur six. `cell_methods` ne lève pas à lui seul
cette ambiguïté : il dit la nature du traitement, pas l'étendue de la
fenêtre, qui relève des bornes de coordonnée.

### Sur l'axe du temps, la linéarité décide de l'exactitude

Une fois acquis que l'axe temporel conserve son **sens**, reste la question
de la **valeur**. Une interpolation linéaire commute avec les opérations
linéaires et pas avec les autres ; la démonstration tient en une ligne, une
moyenne pondérée de sommes étant une somme de moyennes pondérées, alors
qu'une moyenne pondérée de maxima n'est pas le maximum des moyennes
pondérées.

| Agrégation temporelle | Linéaire ? | Effet de l'interpolation spatiale |
|---|---|---|
| valeur instantanée | oui | valeur exacte au sens de l'interpolation |
| moyenne sur la période | oui | idem |
| cumul sur la période | oui | idem |
| **maximum**, **minimum** | **non** | libellé toujours juste, valeur entachée d'une erreur supplémentaire |
| **écart-type**, **moyenne quadratique** | **non** | idem |

Pour les quatre dernières, la valeur reste **une estimation de** la grandeur
déclarée — comme une température interpolée reste une estimation de la
température. C'est l'exactitude qui se dégrade, pas le sens.

> Ce n'est pas un cas d'école : près d'un cinquième des messages du paquet
> mesuré sont des maxima de rafale. Le décompte figure en section 5.

### Le cas à part des grandeurs circulaires

Une direction en degrés ne s'interpole pas composante par composante : entre
350° et 10°, la moyenne arithmétique donne 180°, l'exact opposé de la réponse
juste. Le résultat n'est pas imprécis, il est faux, et aucun contrôle de
conformité ne le détecte. La parade est de travailler en composantes et de
recalculer la direction à la demande.

### Les méthodes conservatives existent, mais ne sont pas la voie par défaut

L'ECMWF propose une méthode de **moyenne de maille** qui *« preserves the
integral of the source grid boxes to the target grid box »*, et la dit
*« suitable for many parameters of interest, such as fluxes […] or integral
parameters […] including precipitation-related parameters »* — précisément
les grandeurs dont la statistique porte sur l'espace.

Elle n'est pas dans la chaîne de diffusion. La documentation de **MIR**, le
moteur d'interpolation de MARS, est explicite : *« MIR implements only linear
and nearest-neighbour interpolation methods. It does not provide any support
for conservative remapping. »* Elle avertit même, chiffres à l'appui, qu'en
dégradation de résolution *« MIR may not produce sufficiently accurate
results »*.

## 3. Le principe : ne pas laisser l'outil décider de la méthode

C'est le point le plus important de cette note, et il n'est pas technique.

L'ECMWF le formule ainsi : *« It is up to the user to know how to use the
data […] The objective is to preserve most of the signal when processing
data. »* Et plus loin, la raison d'être des méthodes **statistiques**
d'interpolation : *« If the field values represent an alert level, then the
maximum value in each grid box should likely be preserved. For categorical
data, such as vegetation type, consider whether the most common value in a
grid box is the one to be preserved. »*

Autrement dit : **le choix de la méthode dépend de la grandeur, et ce choix
n'appartient pas à l'outil.** Une bibliothèque d'interpolation validée reste
validée **dans son domaine** ; employée hors de ce domaine, sa validation ne
transfère rien. Le fait qu'un traitement ait été produit par un outil reconnu
ne dit rien de la justesse du résultat si la méthode ne convenait pas à la
grandeur.

C'est également ce que dit, en une phrase, l'article qui résume la question :
*« regridding or postprocessing in general are destructive procedures ».*

---

## 4. Ce que CF permet de déclarer, et ce que son silence signifie

L'attribut `cell_methods` des conventions CF sert exactement à déclarer la
nature de l'agrégation. Trois points de lecture comptent.

**L'absence n'est pas neutre.** CF énonce que *« the default interpretation
for variables that do not have the `cell_methods` attribute specified depends
on whether the quantity is extensive […] or intensive »* — somme sur
l'intervalle pour une grandeur extensive, instantané ou moyenne pour une
intensive. Le standard qualifie lui-même cette ambiguïté de problématique et
**recommande** de renseigner l'attribut. Ne rien écrire ne dit donc pas « je
ne sais pas » : cela renvoie à un défaut qui peut être faux.

**`interval:` ne dit pas la durée d'un cumul.** La section 7.3.2 réserve ce
champ à *« the typical interval between the original data values to which the
method was applied »* — l'espacement de la donnée source agrégée. L'employer
pour la période de cumul écrirait une contre-vérité. La période relève des
**bornes de coordonnée**.

**Le `time` de `time: sum` est un nom standard**, ce que la section 7.3
autorise explicitement, et non nécessairement une dimension. La distinction
compte dès lors que la chaîne de décodage nomme `time` la date de réseau et
`valid_time` la date effective : c'est la seconde qui porte
`standard_name = "time"`, donc c'est d'elle qu'il s'agit.

---

## 5. Ce que les outils font réellement

Relevé par recherche de code dans les dépôts publics, le 8 octobre 2026.

| Outil | Occurrences de `cell_methods` |
|---|---|
| ecCodes | **0** |
| cfgrib | **0** |
| earthkit-data | 1, une simple liste d'attributs CF reconnus |

**Aucun outil de la chaîne GRIB vers NetCDF n'émet `cell_methods`.**
L'information existe pourtant dans le GRIB — ecCodes la résout depuis la
table 4.10 et l'expose en clé `stepType` — et elle est perdue à la
conversion. Un cumul et un instantané ressortent alors avec les mêmes
dimensions, la même unité et les mêmes coordonnées, sans rien pour les
distinguer.

### Vérifié sur un paquet du producteur

Le relevé de code ne suffisait pas ; un fichier réel a été passé dans les
deux chaînes. Paquet de surface AROME 0,025°, échéances 0 à 6 h, 58 Mo,
**97 messages**.

Ce qu'il contient :

| `stepType` | Messages | Exemples | Méthode CF |
|---|---|---|---|
| `instant` | 55 | `2t`, `2r`, `10u`, `10v`, `prmsl` | `time: point` |
| `accum` | 24 | `tp`, `ssrd`, `tsnowp`, `tgrp` | `time: sum` |
| `max` | **18** | `max_10efg`, `max_10nfg`, `max_i10fg` | `time: maximum` |

**Dix-huit messages sur quatre-vingt-dix-sept portent un maximum** — une
statistique non linéaire, sur une grille rééchantillonnée. Ce n'est donc pas
un cas d'école : près d'un cinquième d'un paquet de surface est concerné.

Deux constats sur le convertisseur officiel, soumis au même fichier :

- **il échoue.** `cfgrib to_netcdf` s'interrompt sur
  `DatasetBuildError: key='heightAboveGround' value=10.0 new_value=2.0` : un
  paquet de surface mêle les niveaux 2 m et 10 m, qu'un hypercube unique ne
  peut pas réunir. Il faut ouvrir un tel fichier comme **plusieurs** jeux —
  cinq pour celui-ci ;
- **le fichier partiel qu'il laisse ne porte ni `cell_methods` ni
  `grid_mapping`** sur aucune de ses variables. Ses attributs globaux sont
  les sept déjà connus, et une variable type n'expose que `units`,
  `long_name`, `standard_name` et `calendar`.

### Le piège que seul le fichier réel révèle

On pouvait croire qu'ouvrir un paquet en plusieurs jeux séparait du même coup
les traitements statistiques. **C'est faux** : le découpage se fait par
**forme d'hypercube**, pas par traitement. Dans le paquet mesuré, un même jeu
réunit quatre champs cumulés — rayonnement, précipitations totales, neige,
grésil — et un champ instantané.

Une méthode de cellule unique par jeu y serait donc fausse : la résolution
doit être **par variable**. Aucune fixture synthétique ne le montrait, parce
qu'elles ne produisaient que des jeux homogènes. C'est la seconde fois qu'un
fichier du producteur corrige une hypothèse que les tests hors ligne
confortaient — la première ayant été une unité absente de la table.

---

## 6. Les outils de nouvelle génération n'apportent pas de réponse

La question méritait d'être posée : une pile plus récente traite-t-elle mieux
le problème ? Vérification faite, non.

- **`earthkit-regrid`** est **déprécié depuis Earthkit 1.0**, ses fonctions
  passant à `earthkit-geo` ; sa maturité est annoncée « Emerging », et il
  **s'appuie sur MIR** comme moteur. Il hérite donc exactement des mêmes
  limites : linéaire et plus proche voisin, pas de remaillage conservatif.
- **`earthkit-meteo`** ne traite pas l'interpolation. Il apporte en revanche
  une confirmation utile : son module de vent expose `speed(u, v)` et
  `direction(u, v)` comme **fonctions dérivées des composantes**, avec deux
  conventions explicites. La direction s'y calcule, elle ne s'y transporte
  pas — ce qui est la seule façon correcte de traiter une grandeur
  circulaire.

---

## 7. L'approche retenue

**La règle se décide axe par axe**, puisque c'est l'axe qui porte la
statistique. Les deux axes n'étant pas dans la même situation, ils n'appellent
pas le même traitement — et c'est la raison de fond des trois règles qui
suivent, plutôt qu'une prudence générale.

**1. Déclarer l'agrégation temporelle.** Trois conditions sont réunies, et
elles le sont toutes les trois : l'axe du temps n'est pas rééchantillonné à
la diffusion, le GRIB déclare la statistique, et le sens du libellé survit à
une interpolation spatiale. Omettre renverrait de surcroît le lecteur au
défaut CF, qui est ambigu. La correspondance se fait par table fermée, chaque
méthode vérifiée présente au tableau E.1 du standard, et par **variable** et
non par jeu. Un traitement que CF ne couvre pas n'émet rien ; un traitement
inconnu interrompt l'écriture plutôt que de laisser passer un cumul déguisé
en instantané.

**2. Ne pas déclarer d'agrégation spatiale par simple recopie.** Les trois
conditions précédentes sont ici toutes en défaut : les axes d'espace **sont**
rééchantillonnés, le producteur ne déclare **rien** — le gabarit 4.15 existe
et n'est pas employé —, et une méthode `area:` perdrait son sens puisque la
maille change. La raison décisive est la deuxième : nous n'avons tout
simplement pas l'information.

La nuance porte sur « par recopie ». Rien n'interdit de déclarer une
agrégation spatiale **calculée par soi-même**, en connaissance de cause. Ce
qui est proscrit, c'est d'hériter d'un attribut dont nul n'a vérifié qu'il
survit au traitement subi — d'où le retrait explicite de tout `cell_methods`
préexistant lorsqu'il n'y a rien à déclarer.

**3. Documenter plutôt que corriger.** Les champs sont rééchantillonnés en
amont, par une méthode que nous ne choisissons pas et que le fichier ne nomme
pas. Le prétendre conservé serait faux ; le passer sous silence laisserait le
consommateur découvrir seul que son maximum interpolé n'est pas tout à fait
un maximum, ou que le cumul de l'échéance 6 h n'est pas la pluie de la
sixième heure. La présente note est le support de cette information.

### Ce qui reste ouvert

Cette note établit pourquoi **nous** ne déclarons pas d'agrégation spatiale.
Elle ne dit pas quelles agrégations spatiales **mériteraient** de l'être, ni
lesquelles un producteur aurait raison de déclarer.

La question demande une source mieux résolue que les modèles. Un champ de
modèle ne permet guère de la trancher : sa maille est l'unité de calcul, et
rien d'extérieur ne vient dire ce qu'elle représente. Une **mosaïque de
radars de précipitation** se prête bien mieux à l'exercice — mieux
échantillonnée dans le temps comme dans l'espace, elle permet de comparer ce
qu'un champ agrégé affirme à ce qu'une observation plus fine montre, et donc
de **vérifier** plutôt que de postuler quelle statistique un champ
représente.

C'est l'occasion naturelle de reprendre le sujet, et de compléter le gabarit
4.15 d'exemples réels plutôt que d'en rester à son existence théorique.

---

## 8. Comment rejouer ces vérifications

| Vérification | Méthode |
|---|---|
| Grille native contre grille diffusée | documentation d'implémentation du cycle IFS ; descriptifs techniques des paquets pour AROME et ARPEGE |
| Méthodes offertes par le moteur de diffusion | page « MARS interpolation with MIR » |
| Méthodes conservatives et statistiques | article de la newsletter 169 |
| Correspondance table 4.10 vers `stepType` | encoder un message au gabarit 4.8 pour chaque valeur de `typeOfStatisticalProcessing`, puis relire la clé `stepType` |
| Absence de déclaration spatiale | relire `spatialProcessing`, `typeOfSpatialProcessing` et `numberOfPointsUsed` sur chaque message d'un paquet réel |
| Fenêtres temporelles | relire `startStep`, `endStep`, `lengthOfTimeRange` et `indicatorOfUnitForTimeRange` sur les champs agrégés |
| Noms de méthodes valides | lire `appe.adoc` dans les sources des conventions |
| Silence des outils | rechercher `cell_methods` dans le code des dépôts concernés |

---

## Références

| Ressource | Adresse |
|---|---|
| « Advanced regridding in Metview », newsletter 169 | <https://www.ecmwf.int/en/newsletter/169/computing/advanced-regridding-metview> |
| MARS interpolation with MIR | <https://confluence.ecmwf.int/display/UDOC/MARS+interpolation+with+MIR> |
| Grille gaussienne réduite octaédrique | <https://confluence.ecmwf.int/display/FCST/Introducing+the+octahedral+reduced+Gaussian+grid> |
| Implémentation du cycle IFS 41r2, résolution et diffusion | <https://confluence.ecmwf.int/display/FCST/Implementation+of+IFS+cycle+41r2> |
| Conventions CF, section 7.3 et annexe E | <https://cfconventions.org/cf-conventions/cf-conventions.html> |
| Sources des conventions CF | <https://github.com/cf-convention/cf-conventions> |
| Table 4.10 du format GRIB2, traitements statistiques dans le temps | <https://codes.ecmwf.int/grib/format/grib2/ctables/4/10/> |
| Table 4.15 du format GRIB2, traitements statistiques dans l'espace | <https://codes.ecmwf.int/grib/format/grib2/ctables/4/15/> |
| earthkit-meteo | <https://github.com/ecmwf/earthkit-meteo> |
| earthkit-regrid | <https://github.com/ecmwf/earthkit-regrid> |
| cfgrib | <https://github.com/ecmwf/cfgrib> |

Rien de ce qui précède n'aurait pu être vérifié sans les documentations
publiques et les codes sous licence libre que ces équipes maintiennent.
Qu'elles en soient ici remerciées.

---

## Décisions arrêtées, déplacées du guide le 20/11/2026

*Elles occupaient la moitié d'un fichier relu à chaque session. Le guide
y renvoie désormais ; le texte est inchangé.*

- **Les grandeurs vectorielles se stockent en composantes.** Direction et force du vent sont **écartées au décodage** et recalculées à la demande. La direction est une grandeur circulaire : la moyenne arithmétique de 350° et 10° vaut 180°, soit l'exact opposé de la réponse juste, et interpolation, ré-échantillonnage et écart-type sont faux de la même façon.
  **Vérifié le 06/10/2026 sur 4,66 millions de points réels** d'un paquet AROME SP1 : la reconstitution depuis les composantes donne un écart maximal de **0,015 m/s sur la force** et de **0,25° sur la direction dès 3 m/s**. La seule dégradation est sous 0,5 m/s — jusqu'à 44° — là où la direction n'a pas de sens physique. Deux champs sur quatre disparaissent sans perte.
  Corollaire : ce qui est intrinsèquement scalaire, une rafale maximale, reste scalaire.
  **Correction du 16/10/2026 : « les données ouvertes de l'ECMWF n'exposent aucune direction » était faux.** Mesuré sur l'index du flux `wave` : `mwd`, direction moyenne des vagues, y figure parmi treize paramètres. La phrase reste vraie de l'API ciblée de Météo-France, et du vent partout.
  **La règle se dédouble donc, et c'est son application qui dépend de CF, pas son principe.** Quand CF offre les deux, les **composantes** l'emportent toujours — c'est le cas du vent, `eastward_wind` et `northward_wind` existant au tableau. Quand CF n'offre que l'angle, l'**angle est conservé** : décomposer exigerait deux noms que CF n'a pas, et les inventer serait précisément la faute que la table entière évite. C'est le cas de `mwd`, ECMWF ne publiant d'ailleurs aucune composante de vagues.
  **Ce que le fichier dit alors, faute de pouvoir mieux.** Une grandeur circulaire n'admet **aucune combinaison linéaire** — et c'est le terme juste, plus large que « non interpolable » : moyenne, écart-type, interpolation et rééchantillonnage en sont tous, et aucun n'est défini sur un cercle. `netcdf_cf.CIRCULAR_COMMENT` l'écrit dans l'attribut `comment` de la variable, avec la marche à suivre — passer par les vecteurs unitaires. La détection est une **règle et non une liste** : CF documente la construction `X_from_direction` et `X_to_direction` dans la description de chacun de ces noms, et une liste de dizaines d'entrées rouillerait.
  **Le plafond est connu** : CF n'offre rien de plus structuré qu'un commentaire en texte libre. Rien n'empêchera un consommateur de moyenner des angles ; le fichier ne peut que le dire. Même limite que pour le lignage, que `history` ne sait pas structurer.

- **Une méthode statistique s'applique à un axe, et l'axe décide du traitement.** CF l'énonce : « the method applies only to the axis designated in `cell_methods` by name, and different methods may apply to other axes ». Les deux axes ne sont donc pas dans la même situation, ce qui est la raison de fond de nos règles et non une prudence générale.
  **Mesuré le 08/10/2026 sur un paquet AROME de surface.** L'axe du **temps** n'est pas rééchantillonné à la diffusion — fenêtres en heures entières, exactes et contiguës —, le GRIB déclare sa statistique en table 4.10, et une interpolation spatiale n'en change que la valeur. Les axes d'**espace** sont toujours rééchantillonnés, le producteur n'en déclare rien — **le gabarit 4.15 et la table 4.15 existent pour cela et ne sont pas employés**, aucune clé `spatialProcessing` sur un seul des 97 messages —, et une méthode `area:` y perdrait son sens puisque la maille change. La raison décisive de ne pas déclarer de méthode spatiale est donc qu'**on ne la connaît pas**, avant même celle de sa fragilité.
  Illustration : un cumul en millimètres porte **deux** statistiques, une somme sur le temps et une moyenne sur la maille ; l'interpolation géographique rompt la seconde et pas la première. Une intensité en mm/h ne porte aucune agrégation temporelle et s'interpole sous la seule hypothèse de continuité spatiale.
  **Piège de lecture relevé au même endroit** : les cumuls courent depuis le début du réseau — (0→1), (0→2), … (0→6) — tandis que les maxima portent sur l'heure écoulée — (0→1), (1→2), … Qui lit le cumul de l'échéance 6 h comme « la pluie de la sixième heure » se trompe d'un facteur six.

- **Ne pas laisser l'outil décider de la méthode.** Les champs diffusés sont **rééchantillonnés** — l'IFS depuis une gaussienne réduite octaédrique, AROME depuis un Lambert — et l'ECMWF qualifie lui-même le rééchantillonnage de **procédure destructrice**. Le critère est la linéarité : une interpolation linéaire commute avec `sum`, `mean` et le point, pas avec `maximum`, `minimum`, l'écart-type ni la moyenne quadratique. Une bibliothèque validée reste validée **dans son domaine** ; employée hors de ce domaine, sa validation ne transfère rien. Fondements, mesures et références **ci-dessus**.
  Corollaire : **aucune méthode `area:` n'est déclarée par recopie**, puisqu'une agrégation spatiale cesse d'être vraie au rééchantillonnage et que le GRIB ne dit pas si une valeur est une moyenne de maille. Rien n'interdirait d'en déclarer une **calculée par nous** ; ce qui est proscrit est d'hériter. Voir `netcdf_cf.DECLARABLE_AXES`, et le retrait explicite de tout `cell_methods` préexistant quand il n'y a rien à déclarer.
  **Vérifié le 08/10/2026 : aucun outil de la chaîne n'émet `cell_methods`** — zéro occurrence dans ecCodes comme dans cfgrib. Et `earthkit-regrid`, qu'on pouvait espérer porteur d'une réponse, est **déprécié depuis Earthkit 1.0** et s'appuie sur MIR, qui n'offre que linéaire et plus proche voisin, sans remaillage conservatif. En revanche `earthkit-meteo` confirme notre règle des composantes : il expose `speed(u, v)` et `direction(u, v)` en fonctions dérivées.
