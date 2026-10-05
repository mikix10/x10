# AROME 0,025° en open data : deux voies d'accès, et ce qu'il faut pour les exploiter

**Note technique à l'usage d'utilisateurs avertis des données ouvertes Météo-France.**

> **État constaté le 5 octobre 2026.** Les observations ci-dessous décrivent la
> situation à cette date et **rien ne garantit leur pérennité** : les contenus,
> les volumes et les surfaces exposées évoluent. Toute décision durable gagne à
> rejouer le relevé — la méthode est décrite en fin de note et ne demande aucun
> outil particulier.

## Objet

Les prévisions du modèle AROME sont publiées par **deux voies distinctes** : des
**paquets de fichiers** déposés sur un stockage objet, et une **API ciblée**
permettant de demander un champ sur un sous-domaine.

Cette note suit le chemin qui va de « la donnée est publiée » à « la donnée est
exploitable ». Elle vérifie d'abord que les deux voies sont effectivement
accessibles et à quelles conditions, puis réunit ce qu'il faut savoir pour
décoder correctement les fichiers. Elle se termine par une comparaison des
contenus, dont le résultat n'est pas celui qu'on attend.

Le relevé porte sur **AROME métropole à 0,025°**, réseau du 5 octobre 2026 à
03 UTC, et sur le service WCS de la même résolution. Les autres modèles —
ARPEGE, AROME outre-mer, prévisions d'ensemble, vagues — n'ont pas été examinés
et peuvent se comporter différemment.

---

## 1. Voie des paquets : accessible sans authentification

**Vérifié.** Le stockage objet répond aux requêtes anonymes, sans compte ni
jeton. Le listage du conteneur fonctionne également sans authentification, ce
qui permet de découvrir les réseaux et les fichiers disponibles.

Le serveur annonce `Accept-Ranges: bytes` et honore les **requêtes par plage
d'octets**, qui reçoivent bien un code 206. Les jeux de données correspondants
sont référencés sur data.gouv.fr, où se trouvent aussi la documentation
technique et les discussions avec le producteur.

**Organisation.** Pour AROME 0,025°, un réseau comporte **onze paquets** — trois
de surface, cinq de niveaux isobares, trois de niveaux hauteur — chacun découpé
en **neuf tranches d'échéances** couvrant 0 à 51 heures. Huit réseaux par jour.

**Rétention.** Quatorze jours annoncés par le producteur. Au 5 octobre 2026, le
conteneur portait **118 réseaux, du 20 septembre au 5 octobre**. Au-delà, les
données archivées s'obtiennent sur demande auprès du producteur.

### Pas de fichier d'index : la pièce qui manque au téléchargement sélectif

Les plages d'octets fonctionnent, mais elles ne servent à rien sans savoir **où
commence le message recherché**. Or les paquets ne sont accompagnés d'aucun
index : les extensions habituelles `.idx`, `.index` et `.inv` renvoient toutes
une absence.

**La comparaison utile est celle des données ouvertes de l'ECMWF**, qui dépose à
côté de chaque fichier GRIB2 un fichier d'index au format JSON Lines, portant la
même racine de nom. Il contient une ligne par message, donnant son
identification complète — date, réseau, échéance, type de niveau, paramètre —
ainsi que son **décalage et sa longueur en octets** dans le fichier.

Un consommateur lit alors cet index, y sélectionne les messages voulus, et les
récupère par autant de requêtes de plage. Le transfert se limite exactement à ce
qui est utile, sans rien télécharger d'inutile.

**Rien n'empêche de reconstituer un tel index soi-même** : chaque message GRIB2
déclare sa longueur dans ses seize premiers octets, ce qui permet de parcourir
un fichier de proche en proche en ne lisant que les en-têtes. La méthode est
décrite en fin de note et fonctionne.

**Mais le calcul n'est pas en faveur du consommateur.** Un index n'est valable
que pour le fichier qu'il décrit : il faut donc le reconstruire **à chaque
publication**, soit huit fois par jour. Le relevé mesuré ici — 6 576 messages
pour une seule tranche d'échéances — conduit à environ **59 000 lectures
d'en-tête par réseau, et près de 473 000 par jour**, pour un résultat que le
producteur obtiendrait en une seule passe, au moment même où il écrit les
fichiers, et pour un coût négligeable.

Autrement dit, chaque réutilisateur refait, en permanence et de façon redondante,
un travail qui ne demanderait qu'une écriture de plus côté producteur. **C'est
typiquement une fonction qui gagne à être demandée plutôt que contournée.**

La demande a d'ailleurs déjà été formulée publiquement, en juin 2026, sur la page
de discussion du jeu de données ; la réponse du producteur, en juillet 2026,
indique que la suggestion est transmise, sans engagement de délai ni de
faisabilité. Les lecteurs que la fonction intéresse peuvent l'appuyer par la même
voie — c'est le canal prévu, et les échanges qui s'y tiennent reçoivent des
réponses.

## 2. Voie de l'API ciblée : accessible avec un compte

**Vérifié.** L'accès exige la création d'un compte sur le portail, puis un
**abonnement par API**. Les abonnements rattachés à une même application
partagent un identifiant unique : **un seul jeton suffit alors pour toutes les
API abonnées**, contrairement à ce que laisse croire la présence d'un bouton de
génération sur chaque fiche.

Le jeton est valable **une heure** et se régénère à partir de l'identifiant
d'application. Le quota est de **100 requêtes par minute** depuis janvier 2026.
Une requête sans jeton reçoit un code 401, une requête sans abonnement un 403 —
distinction utile au diagnostic.

**La découverte elle-même est protégée.** La requête `GetCapabilities` exige un
jeton, et le refus est émis par la passerelle avant d'atteindre le service. Il
n'est donc pas possible de consulter le catalogue des couches avant de s'être
inscrit.

**Nature du service.** Il s'agit de services **OGC WMS et WCS**, dont le
document de capacités déclare les espaces de noms INSPIRE. Les identifiants de
couverture encodent la grandeur, le type de niveau et l'horodatage. Pour le
périmètre examiné, le document annonçait **8 654 couvertures**.

C'est cette voie, et elle seule, qui permet de demander un **sous-domaine
géographique au moment de la requête**.

---

## 3. Ce qu'il faut savoir pour exploiter les fichiers

### Identifier les paramètres

Les fichiers n'identifient les paramètres que par des **codes numériques** —
discipline, catégorie, numéro. Le nom ne s'obtient qu'en appliquant des tables
de code. La bibliothèque ecCodes embarque les tables de l'OMM et de nombreuses
tables locales, et résout l'essentiel des codes rencontrés.

**Six codes y échappent** : (0, 1, 6), (0, 1, 64), (0, 1, 75) et (0, 6, 1), qui
appartiennent pourtant à la plage normalisée, ainsi que (0, 1, 201) et
(0, 16, 192), qui relèvent de la plage réservée aux définitions locales. Les
fichiers déclarant une version de table locale nulle, ils n'indiquent pas
quelle table appliquer.

**Le producteur publie la table manquante.** Un jeu de données dédié met à
disposition une archive de définitions ecCodes, à désarchiver et à désigner par
la variable d'environnement `ECCODES_DEFINITION_PATH`. Le recours à cette table
n'est pas une astuce de contournement : c'est la réponse que le producteur
apporte lui-même aux utilisateurs signalant des champs non reconnus, à deux
reprises au moins dans les discussions publiques du jeu de données.

Cette table résout bien les six codes :

| Code | Nom court |
|---|---|
| (0, 1, 6) | `FLEVAP` |
| (0, 1, 64) | `COLONNE_VAPO` |
| (0, 1, 75) | `GRAUPEL`, `GRAUPEL_INS` |
| (0, 1, 201) | `CLD_GRAUPL` |
| (0, 6, 1) | `NEBUL` |
| (0, 16, 192) | `RFLCTVT` |

**Mais elle ne donne que l'identité, pas les unités.** L'archive contient
environ 1 100 définitions de noms courts, et seulement deux entrées de nom long
et deux d'unité, toutes relatives à la grêle. **Aucun nom standard CF n'y
figure.**

La chaîne complète est donc :

1. code numérique → nom court, par la table officielle, **exploitable par
   programme** ;
2. nom court → nom long et unité, par le glossaire des paramètres, **disponible
   en PDF seulement** ;
3. → nom standard CF : **rien, nulle part**.

Pour les paramètres concernés, l'unité doit être reprise à la main depuis un
document destiné à la lecture humaine.

### La couverture en noms standards CF est faible

Sur les 51 codes relevés dans les onze paquets, **9 seulement** se voient
attribuer un nom standard CF, soit **18 %**. Sont couverts la température, les
humidités spécifique et relative, les composantes zonale et méridienne du vent,
la vitesse verticale, le tourbillon relatif, la pression de surface et le
géopotentiel.

Ne le sont pas, entre autres, la direction et la force du vent, les rafales,
l'ensemble des précipitations, des variables nuageuses et des flux radiatifs, la
CAPE, l'énergie cinétique turbulente et la hauteur de couche limite. Produire un
NetCDF conforme aux conventions CF suppose donc de porter sa propre table de
correspondance pour la majorité des champs.

### La grille n'est pas pleine

Le domaine natif d'AROME est **trapézoïdal** depuis 2019, alors que le format
GRIB n'admet que des grilles rectangulaires. Les fichiers contiennent donc un
nombre important de valeurs manquantes, signalées par un masque binaire.

Sur le message examiné — direction du vent à 10 m — la grille compte 803 757
points pour **665 679 valeurs réelles, soit 138 078 manquantes (17,2 %)**.

Le descriptif technique signale explicitement que **le masque peut différer d'un
paramètre à l'autre**, et recommande soit de redécouper le domaine en une zone
rectangulaire sans valeur manquante, soit d'identifier précisément ces valeurs.
Un masque unique appliqué à un paquet entier serait donc faux.

### L'axe temporel n'est pas uniforme

Dans la tranche d'échéances 00H-06H, neuf paquets sur onze portent sept
échéances, de 0 à 6 heures. **Les paquets HP3 et IP4 n'en portent que six, de 1
à 6 heures.** Il ne s'agit pas d'une lacune : ces paquets contiennent des
diagnostics de prévision — réflectivité, énergie cinétique turbulente — qui
n'existent pas à l'instant d'analyse.

La plage annoncée dans le nom du fichier ne préjuge donc pas des échéances
réellement présentes.

### Cumuls et extremums : un gabarit distinct, et une anomalie connue

Les paquets de surface SP1, SP2 et SP3 emploient **deux gabarits de définition
du produit** : le gabarit instantané et le gabarit à traitement statistique, qui
porte une période de cumul ou d'extremum. Les huit autres paquets n'emploient
que le gabarit instantané. Un décodage ignorant cette distinction interpréterait
des cumuls comme des valeurs instantanées.

**Une anomalie d'encodage affectant précisément ces champs cumulés est documentée
par le producteur** depuis septembre 2026, avec une page dédiée sur son portail
de documentation. Il convient de la consulter avant d'exploiter un cumul.

### Plusieurs types de niveau dans un même fichier

Le paquet IP5 mêle des niveaux isobares et des surfaces de tourbillon potentiel
à 1,5 et 2 PVU. Le paquet SP1 mêle le sol, le niveau moyen de la mer et des
hauteurs au-dessus du sol. Un fichier ne correspond donc pas à un axe vertical
unique.

### Longitudes de 0 à 360

L'emprise est décrite de 348,0° à 16,0° en longitude, c'est-à-dire de −12° à
+16°. Ce n'est pas une particularité du producteur : **le format GRIB2 impose
les longitudes dans l'intervalle 0–360 et n'admet pas de valeur négative**, là
où GRIB1 acceptait des valeurs signées. Tout découpage géographique doit en
tenir compte.

### Géométrie uniforme

La grille est **identique sur les onze paquets** : 1121 × 717 points, soit
803 757, de 55,4 N à 37,5 N, au pas de 0,025°, sur une Terre sphérique. Une
seule géométrie à gérer, ce qui est une simplification appréciable.

---

## 4. Volumétrie

Pour AROME 0,025°, un réseau complet représente **11 paquets × 9 tranches
d'échéances, soit 24,3 Go**. À raison de huit réseaux par jour, la production
avoisine **195 Go par jour** pour ce seul modèle et cette seule résolution.

La répartition est très inégale, et le choix des paquets pèse bien plus que
celui du domaine géographique :

| Paquets | Nature | Paramètres, cumulés par paquet | Volume par tranche |
|---|---|---|---|
| SP1 à SP3 | surface | 37 | **161 Mo** |
| IP1 à IP5 | niveaux isobares | 26 | 1 630 Mo |
| HP1 à HP3 | niveaux hauteur | 17 | 1 368 Mo |

Les comptes de paramètres s'additionnent paquet par paquet et se recouvrent
partiellement d'un paquet à l'autre ; le nombre de codes distincts sur
l'ensemble est de 51.

Les trois paquets de surface concentrent le plus grand nombre de paramètres dans
le plus petit volume : s'y limiter divise la volumétrie par dix-neuf.

Le rapport entre volume et nombre de messages varie d'un facteur cinq selon le
paquet, la compression rendant très différemment selon la nature du champ. Un
dimensionnement se raisonne donc en messages autant qu'en octets.

---

## 5. Conclusion : les deux voies ne se recouvrent pas

On suppose volontiers que les deux voies sont emboîtées, les paquets livrant en
bloc ce que l'API sert au détail. **Le relevé montre qu'il n'en est rien :
aucune des deux ne contient l'autre.**

| | Paquets | API ciblée |
|---|---|---|
| Authentification | aucune | compte, jeton d'une heure |
| Grandeurs distinctes | 51 | **69** |
| Types de niveau | 5 | **13** |
| Géopotentiel aux niveaux hauteur | **oui** | non |
| Grêle, foudre, visibilité, type de précipitation | non | **oui** |
| Sous-domaine à la requête | non | **oui** |
| Profondeur d'archive constatée | **16 jours** | 5 jours |

### Seize grandeurs exposées par la seule API

Elles relèvent pour l'essentiel du **temps sensible** : grêle ; densité
d'impacts de foudre, cumulée et moyennée sur trois heures ; visibilité minimale
sur 60 minutes, avec et sans précipitation ; type de précipitation sur
60 minutes, et sa variante sévère ; inhibition convective ; CAPE de couche
moyenne ; hauteur de neige ; équivalent en eau de la neige accumulée ;
température du thermomètre mouillé ; divergence relative ; et trois champs
exprimés en dBZ — réflectivité, réflectivité maximale, taux de précipitation.

S'y ajoutent des types de niveau absents des paquets : le **sommet de
l'atmosphère** et **six surfaces isothermes**.

### Ce que seuls les paquets contiennent

Le **géopotentiel aux niveaux hauteur-sol**, présent dans le paquet HP2. Dans
l'API, le géopotentiel n'est disponible qu'aux surfaces isobares et aux surfaces
de tourbillon potentiel.

S'y ajoute une profondeur d'archive plus grande : 16 jours de réseaux présents
sur le stockage objet, contre 5 jours d'horodatages annoncés par le service WCS.
C'est l'inverse de ce que l'on pourrait supposer.

### Conséquence

Les deux voies ne sont **pas substituables**. Basculer de l'une à l'autre en cas
d'indisponibilité ne dégraderait pas la latence : cela livrerait autre chose. Le
choix se fait sur le contenu visé, non sur la commodité d'accès — et couvrir les
deux périmètres suppose d'exploiter les deux voies.

### Écarts entre le descriptif technique et le contenu réel

Le descriptif technique des paquets, dans sa version du 1er avril 2025, annonce
pour le paquet **HP1** : « T, HU, U, V, DD, FF, P, Z sur 24 niveaux (20 à
3000 m) ».

| | Annoncé | Constaté le 5 octobre 2026 |
|---|---|---|
| Paramètres | 8 | **7** — le géopotentiel est absent |
| Niveaux | 24, à partir de 20 m | **25, à partir de 10 m** |

Le géopotentiel est bien présent, mais dans **HP2**, où il est également
documenté. L'écart porte donc sur la ligne décrivant HP1.

Ce n'est pas un reproche : un descriptif rédigé une fois ne peut pas suivre
l'évolution continue d'une chaîne de production. C'est un rappel de méthode —
**pour un traitement automatisé, le contenu doit être déduit des fichiers, le
descriptif servant de garde-fou plutôt que de source**.

---

## Reproduire ce relevé

Aucun outil particulier n'est nécessaire.

**Côté paquets.** Le conteneur répond aux requêtes anonymes et accepte les
requêtes par plage d'octets. Comme chaque message GRIB2 déclare sa propre
longueur dans ses seize premiers octets, on parcourt un fichier de proche en
proche en ne lisant que les en-têtes — quelques kilo-octets par message au lieu
du champ entier. Les sections 1, 3 et 4 de chaque message donnent respectivement
le centre et la date de référence, la géométrie, puis le paramètre, le niveau et
l'échéance. Le relevé complet des onze paquets d'une tranche d'échéances, soit
6 576 messages, demande environ trois minutes en parcourant les paquets en
parallèle.

**Côté API ciblée.** Après création d'un compte et abonnement, l'identifiant
d'application permet d'obtenir un jeton valable une heure. La requête
`GetCapabilities` du service WCS renvoie alors le catalogue complet — environ
2,8 Mo pour le périmètre examiné. Les identifiants de couverture encodent la
grandeur, le type de niveau et l'horodatage, ce qui permet de les dénombrer
directement.

## Licence

Les données relèvent de la **Licence Ouverte 2.0**, qui autorise la
réutilisation, y compris commerciale, sous réserve de mentionner la paternité.
On lit parfois qu'une redistribution commerciale des données brutes serait
exclue : cette affirmation ne correspond pas aux termes de la licence.

## Remerciements

Ce relevé n'aurait aucun sens sans une démarche d'ouverture qui mérite d'être
saluée.

Merci à **Météo-France** de publier ses sorties de modèle en données ouvertes,
d'en documenter le contenu, de maintenir un portail d'API et d'en relever les
quotas, de mettre à disposition les tables de définition nécessaires au décodage
de ses paramètres propres, et de signaler explicitement les difficultés d'usage
— la question des valeurs manquantes sur grille trapézoïdale comme l'anomalie
sur les cumuls sont documentées par le producteur lui-même, ce qui est loin
d'être systématique. Les échanges publics sur les pages des jeux de données
témoignent d'un support attentif et constituent une source d'information à part
entière.

Merci à **data.gouv.fr** de référencer ces jeux de données, d'héberger la
documentation technique aux côtés des données, d'accueillir ces discussions, et
d'opérer le service qui republie les paquets de modèle sur un stockage
accessible sans authentification.

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
| Anomalie sur les cumuls AROME et ARPEGE | <https://confluence-meteofrance.atlassian.net/wiki/spaces/OpenDataMeteoFrance/pages/1862467624/> |
| Jeu de données « Paquets Arome 0,025° » | <https://www.data.gouv.fr/datasets/paquets-arome-resolution-0-025deg> |
| Discussions du même jeu de données | <https://www.data.gouv.fr/datasets/paquets-arome-resolution-0-025deg/#/discussions> |
| **Définition des gribs de Météo-France** | <https://www.data.gouv.fr/datasets/definition-des-gribs-de-meteo-france> |
| Dataservice « API Modèle AROME » | <https://www.data.gouv.fr/dataservices/api-modele-arome> |
| Descriptif technique des paquets AROME | <https://static.data.gouv.fr/resources/paquets-arome-resolution-0-025deg/20250401-061917/descriptiontechnique-paquetsarome-donneespubliques-v4-20250401.pdf> |
| Glossaire des paramètres ARPEGE/AROME | <https://static.data.gouv.fr/resources/paquets-arome-resolution-0-025deg/20241127-114612/description-parametres-modeles-arpege-arome-v2-185.pdf> |
| Licence Ouverte 2.0 | <https://www.etalab.gouv.fr/licence-ouverte-open-licence/> |
| Conventions CF | <https://cfconventions.org/> |
| ecCodes | <https://confluence.ecmwf.int/display/ECC> |
| Données ouvertes de l'ECMWF, où figurent les fichiers d'index | <https://data.ecmwf.int/forecasts/> |
| Présentation des données ouvertes de l'ECMWF | <https://www.ecmwf.int/en/forecasts/datasets/open-data> |
| Client de référence exploitant ces index | <https://github.com/ecmwf/ecmwf-opendata> |

Le descriptif technique, le glossaire et l'archive de définitions sont attachés
aux jeux de données eux-mêmes : les adresses ci-dessus désignent une version
datée, et une version plus récente peut exister sur la page du jeu de données.
