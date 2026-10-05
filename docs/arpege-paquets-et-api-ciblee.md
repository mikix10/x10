# ARPEGE en open data : deux voies d'accès, deux résolutions, et ce qu'il faut pour les exploiter

**Note technique à l'usage d'utilisateurs avertis des données ouvertes Météo-France.**

> **État constaté le 5 octobre 2026.** Les observations ci-dessous décrivent la
> situation à cette date et **rien ne garantit leur pérennité** : les contenus,
> les volumes et les surfaces exposées évoluent. Toute décision durable gagne à
> rejouer le relevé — la méthode est décrite en fin de note et ne demande aucun
> outil particulier.

## Objet

Les prévisions du modèle ARPEGE sont publiées par **deux voies distinctes** —
des **paquets de fichiers** déposés sur un stockage objet, et une **API ciblée**
permettant de demander un champ sur un sous-domaine — et selon **deux
résolutions** aux emprises très différentes.

Cette note suit le chemin qui va de « la donnée est publiée » à « la donnée est
exploitable ». Elle vérifie d'abord que les voies sont accessibles et à quelles
conditions, réunit ensuite ce qu'il faut savoir pour décoder correctement les
fichiers, et se termine par une comparaison des contenus.

Le relevé porte sur le réseau du 5 octobre 2026 à 00 UTC, première tranche
d'échéances de chaque paquet, aux deux résolutions, et sur les services WCS
correspondants. Une note distincte traite d'AROME ; les deux modèles diffèrent
sur plusieurs points relevés ici.

---

## 1. Voie des paquets : accessible sans authentification

**Vérifié.** Le stockage objet répond aux requêtes anonymes, sans compte ni
jeton. Le listage du conteneur fonctionne également sans authentification. Le
serveur annonce `Accept-Ranges: bytes` et honore les requêtes par plage
d'octets.

**Cadence : quatre réseaux par jour**, à 00, 06, 12 et 18 UTC. Contrôlé : les
créneaux 03, 09, 15 et 21 ne contiennent pas d'ARPEGE, contrairement à AROME
qui en compte huit.

**Deux résolutions, organisées différemment :**

| | ARPEGE 0,25° | ARPEGE 0,1° |
|---|---|---|
| Emprise | **globale** | Europe |
| Paquets | **9** — SP1 à SP3, IP1 à IP4, HP1, HP2 | **8** — SP1, SP2, IP1 à IP4, HP1, HP2 |
| Tranches d'échéances | 4 : 00-24, 25-48, 49-72, 73-102 | 9 : 00-12, 13-24, … 97-102 |
| Volume par réseau | **43,0 Go** | 14,7 Go |

**Rétention.** Quatorze jours annoncés par le producteur. Au-delà, les données
archivées s'obtiennent sur demande auprès de celui-ci.

### Pas de fichier d'index, et une limite pratique au contournement

Les plages d'octets fonctionnent, mais elles n'adressent rien sans savoir où
commence le message recherché, et aucun index n'accompagne les paquets. La
comparaison utile est celle des données ouvertes de l'ECMWF, qui dépose à côté
de chaque fichier GRIB2 un index au format JSON Lines donnant, pour chaque
message, son identification complète ainsi que son décalage et sa longueur.

On peut reconstruire un tel index en parcourant les en-têtes, chaque message
GRIB2 déclarant sa longueur dans ses seize premiers octets. **Mais ARPEGE révèle
une limite qu'AROME ne montrait pas** : au-delà d'environ trois à quatre mille
requêtes de plage successives sur un même objet depuis un même processus, les
requêtes cessent de répondre sans erreur ni délai d'expiration. Le phénomène
s'est reproduit à l'identique à trois reprises, toujours autour du même nombre
de requêtes, alors que des lectures aux mêmes adresses depuis un processus neuf
répondent en moins d'une demi-seconde. Il s'agit donc d'un épuisement
cumulatif — vraisemblablement côté intermédiaire réseau — et non d'un défaut du
fichier.

La conséquence est concrète : les paquets d'AROME plafonnent à 1 550 messages et
ne rencontrent jamais ce seuil, tandis que ceux d'ARPEGE 0,25° montent à 4 200.
**Un parcours d'en-têtes à cette échelle exige un point de reprise** permettant
de redémarrer à l'offset atteint, faute de quoi chaque interruption coûte
l'intégralité du travail.

Cela renforce l'argument déjà valable pour AROME : un index reconstruit par le
consommateur doit l'être à chaque publication, soit quatre fois par jour,
alors que le producteur l'obtiendrait en une seule passe au moment où il écrit
les fichiers. La demande d'un tel index a été formulée publiquement sur la page
de discussion du jeu de données AROME, et transmise sans engagement.

## 2. Voie de l'API ciblée : accessible avec un compte

**Vérifié.** L'accès exige un compte sur le portail, puis un abonnement par API.
Les abonnements rattachés à une même application partagent un identifiant
unique : un seul jeton suffit alors pour toutes les API abonnées. Le jeton est
valable une heure ; le quota est de 100 requêtes par minute.

**La découverte elle-même est protégée** : `GetCapabilities` exige un jeton, et
le refus est émis par la passerelle avant d'atteindre le service.

Deux services distincts sont exposés, dont les documents de capacités déclarent
les espaces de noms INSPIRE :

| | Couvertures annoncées | Grandeurs | Types de niveau |
|---|---|---|---|
| ARPEGE 0,25° globe | 5 832 | **71** | 13 |
| ARPEGE 0,1° Europe | 4 824 | 64 | 12 |

**Le 0,1° est strictement inclus dans le 0,25°** : aucune grandeur ne lui est
propre. Sept lui manquent — les deux champs de foudre, deux variantes de CAPE,
deux flux solaires et le maximum de rafale — ainsi qu'une surface de tourbillon
potentiel supplémentaire.

---

## 3. Ce qu'il faut savoir pour exploiter les fichiers

### Les grilles, et un écart majeur avec le descriptif

| | Descriptif technique | Mesuré |
|---|---|---|
| 0,25° | « GLOB025 (53N 38N 8W 12E) » | **1440 × 721 = 1 038 240 points, 90 N → 90 S, 0 → 359,75° E** |
| 0,1° | « EURAT01 (72N 20N 32W 42E) » | 741 × 521 = 386 061 points, 72 N → 20 N, −32 → +42° E |

Le 0,1° est décrit correctement. Pour le 0,25°, le descriptif annonce une
emprise de la taille de la France alors que la donnée est **réellement
globale** — ce que le nom du produit indiquait pourtant.

À noter : 1440 × 721 est exactement le maillage des données ouvertes de l'IFS
de l'ECMWF. Deux producteurs, même grille globale à 0,25°.

### Les grilles sont pleines

Contrôlé aux deux résolutions : **aucune valeur manquante, aucun masque
binaire**. C'est une différence importante avec AROME, dont le domaine
trapézoïdal laisse environ 17 % de la grille vide et impose un masque variable
selon le paramètre. Rien de tel ici.

### Les échéances sont horaires, conformément à la description

Un écart avait été signalé publiquement en 2024 : les fichiers étaient
tri-horaires alors que la documentation annonçait le pas horaire, ce que le
producteur avait reconnu comme une erreur de documentation à corriger.

**Mesuré aujourd'hui, la production est conforme** : 25 échéances horaires de 0
à 24 h pour la première tranche à 0,25°, 13 échéances horaires de 0 à 12 h à
0,1°. Au-delà de 48 h, la description annonce un pas tri-horaire.

Contrairement à AROME, où deux paquets sur onze démarrent à l'échéance 1 faute
de diagnostic à l'instant d'analyse, **tous les paquets d'ARPEGE portent le même
jeu d'échéances**, y compris le pas 0.

### Trois gabarits de produit, dont un propre à ARPEGE

Les paquets de niveaux n'emploient que le gabarit instantané. Les paquets de
surface y ajoutent le gabarit à traitement statistique, qui porte une période de
cumul ou d'extremum — à ne pas confondre avec une valeur instantanée.

**Le paquet SP3 à 0,25° en emploie un troisième**, celui des **données
satellitaires simulées**. Aucun équivalent dans AROME. Un décodeur générique
doit donc prévoir ce cas.

### Identification des paramètres

Les fichiers n'identifient les paramètres que par des codes numériques. Sur les
**64 codes distincts** relevés, la bibliothèque ecCodes seule en laisse **12 non
résolus**, ni en nom ni en unité — le double de ce qu'on observe sur AROME.

**Le producteur publie la table manquante** sous forme d'un jeu de données
dédié, à désarchiver et à désigner par une variable d'environnement. Ce n'est
pas un contournement : c'est la réponse que le producteur apporte lui-même aux
utilisateurs signalant des champs non reconnus, à plusieurs reprises dans les
discussions publiques, y compris sur ce modèle.

Cette table résout **dix des douze** codes :

| Code | Nom court | Nature |
|---|---|---|
| (0, 1, 6) | `FLEVAP` | flux d'évaporation |
| (0, 1, 64) | `COLONNE_VAPO` | colonne de vapeur d'eau |
| (0, 4, 198) | `FLSOLAIRE_DD` | flux solaire direct descendant |
| (0, 5, 7) | `BT`, `V_BT_223` | températures de brillance |
| (0, 6, 1) | `NEBUL` | nébulosité totale |
| (0, 7, 199) | `CAPE_MOD` | CAPE modifiée |
| (0, 19, 201) | `VISIHYDN_PER` | visibilité par les hydrométéores |
| (2, 3, 192) | `RESERVE_GLAC` | réserve en eau gelée du sol |
| (2, 3, 193) | `RESERVE_LIQU` | réserve en eau liquide du sol |
| (2, 3, 254) | `RESERVE_EAU` | réserve en eau du sol |

Les trois dernières relèvent de la **discipline 2, produits de surface
terrestre**, absente d'AROME.

**Deux codes restent inidentifiables**, même avec le supplément officiel :
**(0, 6, 11)** et **(0, 17, 4)**, tous deux dans le paquet SP3 à 0,25°. Leurs
catégories — nuages et électrodynamique — suggèrent respectivement une grandeur
de base de nuage et un champ lié à la foudre, mais ce n'est qu'une déduction.
Le canal de discussion du jeu de données est l'endroit où faire poser la
question.

### Noms standards CF : le manque n'est pas là où on croit

Sur les 64 codes relevés, **9 seulement** reçoivent un nom standard CF par
ecCodes, soit **14 %** — moins encore que les 18 % observés sur AROME.

Il faut cependant être précis sur la nature du manque. Le tableau des noms
standards CF, dans sa version 95, compte plus de cinq mille entrées, et
contient bel et bien `wind_speed`, `wind_from_direction`, `wind_speed_of_gust`,
`air_pressure`, `visibility_in_air`, `cloud_area_fraction`, `precipitation_flux`
ou `atmosphere_boundary_layer_thickness`. **Ce n'est donc pas CF qui est
lacunaire : c'est la table de correspondance GRIB vers CF que livre ecCodes.**

La distinction a une conséquence pratique : il s'agit de compléter une table de
correspondance entre deux vocabulaires existants, pas de créer des termes.

### Vent : préférer les composantes

Les paquets portent la direction et la force du vent en plus des composantes
zonale et méridienne. **L'API ciblée, elle, n'expose aucune direction** — ni
pour ARPEGE, ni pour AROME : seulement les composantes, la vitesse et les
rafales. Les données ouvertes de l'ECMWF font de même et ne diffusent que des
composantes.

La raison dépasse la commodité. La direction est une **grandeur circulaire** :
la moyenne arithmétique de 350° et 10° vaut 180°, soit l'exact opposé de la
réponse correcte. Interpolation, ré-échantillonnage, moyenne et écart-type sont
faux sur une direction tant qu'on ne passe pas par un traitement circulaire
explicite — et celui-ci revient de toute façon à repasser par les composantes.

Conserver les composantes et dériver direction et force au moment de l'usage
évite une classe entière d'erreurs silencieuses, et réduit le volume sans perte
d'information.

### Plusieurs types de niveau dans un même fichier

Le paquet IP4 mêle niveaux isobares et surfaces de tourbillon potentiel. Les
paquets de surface mêlent le sol, le niveau moyen de la mer, des hauteurs
au-dessus du sol et, à 0,1°, l'atmosphère entière considérée comme une couche.
Un fichier ne correspond donc pas à un axe vertical unique.

### Longitudes de 0 à 360

Les emprises sont décrites en longitudes positives — 328° pour −32°. Ce n'est
pas une particularité du producteur : **le format GRIB2 impose l'intervalle
0–360 et n'admet pas de valeur négative**, là où GRIB1 acceptait des valeurs
signées.

---

## 4. Volumétrie

| | Par réseau | Par jour (4 réseaux) |
|---|---|---|
| ARPEGE 0,25° | 43,0 Go | 172 Go |
| ARPEGE 0,1° | 14,7 Go | 59 Go |
| **Total** | **57,7 Go** | **231 Go** |

Le choix des paquets pèse bien plus que celui du domaine géographique. Pour la
première tranche d'échéances à 0,25° :

| Paquets | Nature | Paramètres, cumulés par paquet | Volume |
|---|---|---|---|
| SP1 à SP3 | surface | 55 | **1 161 Mo** |
| IP1 à IP4 | niveaux isobares | 21 | 8 761 Mo |
| HP1, HP2 | niveaux hauteur | 14 | 5 867 Mo |

Les comptes de paramètres s'additionnent paquet par paquet et se recouvrent
partiellement ; le nombre de codes distincts sur l'ensemble est de 64.

Comme pour AROME, les paquets de surface concentrent le plus grand nombre de
paramètres dans le plus petit volume. La répartition est cependant différente
entre résolutions : à 0,1°, deux paquets de surface portent 26 et 25 paramètres,
tandis qu'à 0,25° trois paquets en portent 14, 19 et 22. **Les deux résolutions
ne sont donc pas le même produit à deux maillages**, et un traitement ne se
transpose pas de l'une à l'autre sans vérification.

Autre différence structurante : le paquet IP1 porte **34 niveaux isobares
jusqu'à 1 hPa** à 0,25°, contre 24 niveaux s'arrêtant à 100 hPa à 0,1°. Seule la
résolution globale monte dans la stratosphère.

---

## 5. Conclusion : les deux voies ne se recouvrent pas

Comme pour AROME, l'hypothèse d'un emboîtement ne tient pas : **aucune des deux
voies ne contient l'autre.**

### Exposé par la seule API ciblée

Couverture nuageuse convective ; convergence d'humidité ; inhibition convective ;
CAPE de couche moyenne ; variantes sur 180 minutes du type de précipitation et
de la visibilité ; hauteur de neige et équivalent en eau de la neige accumulée ;
divergence relative. S'y ajoutent des types de niveau absents des paquets : le
**sommet de l'atmosphère** et **cinq surfaces isothermes**, sur lesquelles
reposent des grandeurs comme l'altitude d'une isotherme.

### Présent dans les seuls paquets

Le **géopotentiel aux niveaux hauteur-sol**, dans le paquet HP2 — l'API ne
l'expose qu'aux surfaces isobares et de tourbillon potentiel. Exactement la même
asymétrie que pour AROME.

La **réserve en eau du sol** : l'API expose les réserves gelée et liquide, mais
pas la réserve totale, que les paquets portent.

Et la **direction du vent**, que l'API n'expose pas du tout.

### Conséquence

Les deux voies ne sont **pas substituables**. Basculer de l'une à l'autre en cas
d'indisponibilité ne dégraderait pas la latence : cela livrerait autre chose. Le
choix se fait sur le contenu visé, et couvrir les deux périmètres suppose
d'exploiter les deux voies.

### Un paquet absent de la documentation

Le descriptif technique, dans sa version du 2 janvier 2024, liste huit paquets
pour la résolution 0,25°. Le stockage en porte **neuf** : **`SP3` n'y figure
pas**. Ce paquet est pourtant bien servi par la voie authentifiée et fidèlement
repris — c'est l'omission qui est documentaire.

Ce n'est pas un reproche : un descriptif rédigé une fois ne peut pas suivre
l'évolution continue d'une chaîne de production. C'est un rappel de méthode —
**pour un traitement automatisé, le contenu doit être déduit des fichiers, le
descriptif servant de garde-fou plutôt que de source**.

---

## La chaîne de production, et ce qu'elle explique

Le producteur ne documente pas publiquement l'articulation entre les deux
voies, mais le service qui alimente le stockage objet est publié en logiciel
libre, et son code la révèle.

Ce service interroge, avec un identifiant d'application du portail, des points
d'entrée dédiés aux paquets, distincts de ceux des services OGC. Il télécharge,
dépose sur un stockage objet et publie les ressources, en conservant une
quinzaine de jours.

La chaîne est donc : **une même production de modèle en amont, puis deux
familles de produits distinctes sur la même passerelle** — les paquets d'un
côté, les couvertures ciblées de l'autre — dont seule la première est reprise
sur le stockage objet.

Cela éclaire les écarts relevés plus haut : **ils proviennent d'une décision de
produit en amont, et non du mécanisme de republication**. La preuve en est que
la republication ne perd rien : les listes de paquets déclarées dans la
configuration du service correspondent exactement à ce que porte le stockage,
`SP3` compris.

---

## Reproduire ce relevé

Aucun outil particulier n'est nécessaire.

**Côté paquets.** Le conteneur répond aux requêtes anonymes et accepte les
requêtes par plage. Chaque message GRIB2 déclarant sa longueur dans ses seize
premiers octets, on parcourt un fichier de proche en proche en ne lisant que les
en-têtes — quelques kilo-octets par message au lieu du champ entier. Les
sections 1, 3 et 4 donnent respectivement le centre et la date de référence, la
géométrie, puis le paramètre, le niveau et l'échéance. Le relevé présenté ici
couvre 17 paquets et 31 970 messages, soit 18,55 Go adressés.

**Prévoir un point de reprise** : au-delà de quelques milliers de requêtes
successives, le parcours se fige, et seule une reprise à l'offset atteint permet
d'aboutir sur les plus gros paquets.

**Côté API ciblée.** Après création d'un compte et abonnement, l'identifiant
d'application permet d'obtenir un jeton valable une heure. La requête
`GetCapabilities` du service WCS renvoie le catalogue complet — de l'ordre de
1,5 à 1,9 Mo ici. Les identifiants de couverture encodent la grandeur, le type
de niveau et l'horodatage, ce qui permet de les dénombrer directement.

## Licence

Les données relèvent de la **Licence Ouverte 2.0**, qui autorise la
réutilisation, y compris commerciale, sous réserve de mentionner la paternité.

## Remerciements

Ce relevé n'aurait aucun sens sans une démarche d'ouverture qui mérite d'être
saluée.

Merci à **Météo-France** de publier ses sorties de modèle en données ouvertes, y
compris la résolution globale, d'en documenter le contenu, de maintenir un
portail d'API et d'en relever les quotas, et de mettre à disposition les tables
de définition nécessaires au décodage de ses paramètres propres. Les échanges
publics sur les pages des jeux de données témoignent d'un support attentif :
plusieurs des points éclaircis ici l'ont été grâce à des réponses apportées à
d'autres réutilisateurs, y compris la reconnaissance franche d'une erreur de
documentation sur les pas de temps, depuis corrigée dans la production.

Merci à **data.gouv.fr** de référencer ces jeux de données, d'héberger la
documentation technique aux côtés des données, d'accueillir ces discussions,
d'opérer le service de republication sur un stockage accessible sans
authentification, et d'en publier le code sous licence libre — c'est ce dernier
point qui a permis d'établir l'articulation entre les deux voies d'accès.

Les écarts relevés ici entre documentation et contenu ne sont pas des critiques :
ils illustrent la difficulté réelle de tenir à jour la description d'une chaîne
de production qui évolue, et plaident pour que les réutilisateurs vérifient par
eux-mêmes plutôt que de présumer.

## Références

| Ressource | Adresse |
|---|---|
| Portail des API | <https://portail-api.meteofrance.fr/> |
| Documentation open data | <https://confluence-meteofrance.atlassian.net/wiki/spaces/OpenDataMeteoFrance/> |
| Modèles et données de prévision | <https://confluence-meteofrance.atlassian.net/wiki/spaces/OpenDataMeteoFrance/pages/621019138/> |
| Jeu de données « Paquets Arpège 0,25° » | <https://www.data.gouv.fr/datasets/paquets-arpege-resolution-0-25deg> |
| Jeu de données « Paquets Arpège 0,1° » | <https://www.data.gouv.fr/datasets/paquets-arpege-resolution-0-1deg> |
| Discussions du jeu de données 0,1° | <https://www.data.gouv.fr/datasets/paquets-arpege-resolution-0-1deg/#/discussions> |
| Dataservice « API Modèle ARPEGE » | <https://www.data.gouv.fr/dataservices/api-modele-arpege> |
| **Définition des gribs de Météo-France** | <https://www.data.gouv.fr/datasets/definition-des-gribs-de-meteo-france> |
| Descriptif technique des paquets ARPEGE | <https://static.data.gouv.fr/resources/paquets-arpege-resolution-0-25deg/20240228-192954/description-paquets-modele-arpege.pdf> |
| Glossaire des paramètres ARPEGE/AROME | <https://static.data.gouv.fr/resources/paquets-arome-resolution-0-025deg/20241127-114612/description-parametres-modeles-arpege-arome-v2-185.pdf> |
| Service de republication, code source | <https://github.com/datagouv/mf-data-extract-service> |
| Licence Ouverte 2.0 | <https://www.etalab.gouv.fr/licence-ouverte-open-licence/> |
| Conventions CF, tableau des noms standards | <https://cfconventions.org/Data/cf-standard-names/current/build/cf-standard-name-table.html> |
| ecCodes | <https://confluence.ecmwf.int/display/ECC> |
| Données ouvertes de l'ECMWF, où figurent les fichiers d'index | <https://data.ecmwf.int/forecasts/> |
| Présentation des données ouvertes de l'ECMWF | <https://www.ecmwf.int/en/forecasts/datasets/open-data> |

Le descriptif technique, le glossaire et l'archive de définitions sont attachés
aux jeux de données eux-mêmes : les adresses ci-dessus désignent une version
datée, et une version plus récente peut exister sur la page du jeu de données.
