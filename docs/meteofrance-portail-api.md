# Le portail d'API Météo-France : vingt-deux services, et une suite océanique

**Note technique à l'usage d'utilisateurs avertis des données ouvertes
Météo-France.**

> **État constaté le 20 octobre 2026.** Les observations ci-dessous décrivent
> la situation à cette date et **rien ne garantit leur pérennité**. Toute
> décision durable gagne à rejouer le relevé — la méthode est en fin de note.

## Objet

Deux notes de ce dossier traitent déjà des **paquets** AROME et ARPEGE
republiés en open data, et évoquent l'API ciblée sans l'explorer. Celle-ci
porte sur le **portail d'API** lui-même : ce qu'il expose, comment on le
découvre, et ce qu'il livre.

Le relevé porte sur les **22 API** du catalogue, **398 opérations**,
**35 documents de capacités WCS** totalisant environ **96 000 couvertures**,
et **14 granules** téléchargés dans les deux formats que le service déclare.

Elle complète [arome-paquets-et-api-ciblee.md](arome-paquets-et-api-ciblee.md)
et [arpege-paquets-et-api-ciblee.md](arpege-paquets-et-api-ciblee.md) ; elle
ne les remplace pas.

---

## 1. Le catalogue des API est libre d'accès

**Correction à nos propres notes.** Elles affirment que « la découverte
elle-même est protégée ». C'est vrai du `GetCapabilities` des couches ;
c'est **faux du catalogue des API**.

`https://portail-api.meteofrance.fr/api/am/devportal/v3/apis` rend les
**22 API sans aucune authentification** — le jeton le fait même échouer en
`401`, relevant d'un autre domaine d'authentification. On peut donc
inventorier l'offre entière sans compte, comme avec l'index de
`data.ecmwf.int`.

Chaque API y publie sa **définition OpenAPI**, d'où les 398 opérations. Il
n'y a donc aucun chemin à deviner — et c'est ce qui corrige l'erreur la plus
facile à commettre : **quatre préfixes de contexte coexistent**,
`/public/`, `/previnum/`, `/pro/` et `/partner/`, et supposer `/public/`
pour tous produit des `404` qui ressemblent à des refus d'abonnement.

### Les vingt-deux

| Famille | API |
|---|---|
| Prévision numérique, API ciblée | AROME, AROME-PI, ARPEGE, PE-AROME, PE-ARPEGE, WavesModels |
| Paquets | PaquetAROME, PaquetAROME-OM, PaquetAROMEIFS, PaquetARPEGE, PaquetENVIRONNEMENT, PaquetWAVESMODELS |
| Observation | DonneesPubliquesObservation, DonneesPubliquesPaquetObservation, DonneesPubliquesClimatologie |
| Avertissement | DonneesPubliquesVigilance, DonneesPubliquesBRA, DonneesPubliquesMeteoForets |
| Radar | DonneesPubliquesRadar, DonneesPubliquesPaquetRadar, RadarOpera |
| Précipitations immédiates | PrevisionImmediatePrecipitations |

**L'abonnement se souscrit par API**, et une même application les partage :
un seul jeton vaut pour toutes celles auxquelles le compte est abonné. Le
jeton s'obtient depuis un identifiant d'application de longue durée et vaut
**3 600 secondes exactement**.

Trois codes à distinguer, et les confondre mène à des conclusions fausses :

| Code | Sens |
|---|---|
| `401` | pas de jeton, ou jeton refusé |
| `403` avec `"code":"900908"` | jeton valide, **pas d'abonnement** à cette API |
| `404` avec `"No matching resource"` | la passerelle ne connaît pas ce contexte — le chemin est faux |

Un `404` rendu par le **service** et non par la passerelle se reconnaît à sa
forme : il est en français et porte une autre structure.

---

## 2. Une suite océanique, et c'est la découverte

`WavesModels` est la plus grosse API du portail — **85 opérations,
17 services WCS** — et expose trois familles que nos notes précédentes
ignoraient :

| Modèle | Domaine | Résolution |
|---|---|---|
| **MFWAM** | global et France | 0,1° et 0,025° |
| **WaveWatch III** | neuf domaines outre-mer | 0,002° à 0,01° |
| **HYCOM2D** | Atlantique et Méditerranée | 0,041° |

HYCOM2D porte notamment la **surcote** — `EXTRA_TROPICAL_STORM_SURGE` — avec
ses maxima 3 h et 24 h. Le vocabulaire océanique compte par ailleurs des
grandeurs qu'aucune table usuelle ne couvre : indice de Benjamin-Feir,
corrélation crête-creux, dérive de Stokes en composantes, hauteur de vague
individuelle maximale, et des partitions de houle primaire et secondaire —
chacune avec sa hauteur, sa période et sa direction.

**Ces modèles sont servis en GRIB édition 1**, là où AROME et ARPEGE sont en
édition 2 ; voir la section 4.

### Trente-cinq services, environ 96 000 couvertures

| Famille | Services WCS | Couvertures |
|---|---|---|
| AROME, AROME-OM, PA-AROME, AROME-PI, AROME-IFS | 12 | ~57 000 |
| ARPEGE et PA-ARPEGE | 6 | ~24 300 |
| MFWAM | 2 | 975 |
| WaveWatch III | 11 | ~2 900 |
| HYCOM2D | 4 | 234 |

---

## 3. Le vocabulaire des couvertures, et ses défauts

Un identifiant de couverture vaut
`GRANDEUR__NIVEAU___HORODATAGE[_PÉRIODE]`, soit **260 couples (grandeur,
niveau) distincts**. Il est le seul vocabulaire que nous ayons rencontré à
encoder **le niveau et la période d'agrégation dans la même chaîne** — le
suffixe `_PT9H` d'un cumul en est un.

**Trois défauts d'orthographe y coexistent**, mesurés :

| Forme | Occurrences |
|---|---|
| `GROUND_OR_WATER_SURFACE` | 95 |
| `GROUND_OR_WATER_SUFACE` | 1 — un `R` manquant |
| `LEVEL_OF_ADIABATIC_CONDENSATION` | 3 |
| `LEVEL_OF_ADIABATIC_CONDESATION` | 3 — un `N` manquant |
| `LEVEL_OF_ADIABATIC_CONDESATION ` | 1 — avec une espace finale |

Plus un `U_COMPOSANT_SURFACE_STOKES_DRIFT`, mot français dans un vocabulaire
anglais.

Ce n'est pas une curiosité : **qui normalise sur la forme correcte perd
silencieusement une couverture**, et qui groupe par niveau en obtient deux
là où il y en a un. C'est la démonstration concrète de ce que vaut une vue
qui suit son producteur. Voir `X10-DIV-0002` au
[registre des écarts](divergences-observees.md).

---

## 4. Extraire une couverture, et ce que le service enseigne

`GetCoverage` exige un découpage sur **tous les axes sauf deux**, et le dit
lui-même — ce qui en fait une API apprenable par ses erreurs :

| Requête | Réponse du service |
|---|---|
| `subset=lat(...)&long(...)` | « Slicing on height is mandatory » |
| `+ height(2.0)` | « height must be in : 2 10 20 35 50 75 … » |
| `+ height(2)` | « Slicing on time is mandatory » |
| `+ time("…Z")` | « time must be in : … » — **en listant la valeur envoyée** |
| `+ time(…Z)` **sans guillemets** | **200** |

**La dernière ligne est une non-conformité.** OGC WCS 2.0 exige des
guillemets autour d'une valeur temporelle ; le service ne les accepte pas,
tout en affichant la valeur citée parmi les valeurs valides. Un client écrit
depuis la spécification échoue, et le message ne l'aide pas. Voir
`X10-DIV-0001`.

Les axes et leurs valeurs admises se lisent dans `DescribeCoverage`, et
c'est la seule façon fiable de construire une requête.

### Deux formats, et deux unités

Les définitions déclarent **`application/wmo-grib`** (44 opérations) et
**`image/tiff`** (36). Les deux sont servis.

**Le GeoTIFF convertit la température en Celsius et ne déclare aucune
unité.** Mesuré sur la même couverture :

| | minimum | maximum | unité déclarée |
|---|---|---|---|
| GRIB | 277,9517 | 295,0835 | `K` |
| GeoTIFF | 4,8017 | 21,9335 | **aucune** |

Exactement 273,15 d'écart. La seule trace est une étiquette GDAL de bande,
qui n'est pas un emplacement normalisé. **Et la conversion est
sélective** — précipitation, hauteur de vague et surcote sortent identiques
— ce qui interdit de la traiter par une règle de format. Voir
`X10-DIV-0005`.

Le GeoTIFF conserve en revanche la géoréférence et masque correctement les
valeurs manquantes, là où le GRIB expose 9 999 en clair. **C'est une sortie
de visualisation**, non un format d'échange : ni nom standard, ni
`cell_methods`, ni bornes temporelles.

### Les éditions du GRIB, et une table locale inconnue

| Modèle | Édition |
|---|---|
| AROME 0,025°, ARPEGE 0,1° | 2 |
| MFWAM, HYCOM2D | **1** |

Et dans un même granule MFWAM, la hauteur significative se résout
normalement — `swh` — tandis que la direction moyenne des vagues sort avec
`shortName` et `units` à `unknown` : c'est `var200 of table 2 of center 85`,
un paramètre d'une **table locale** que l'outillage public ne porte pas. Une
grandeur **circulaire** anonyme est celle qu'il est le plus coûteux de
laisser passer. Voir `X10-DIV-0004`.

---

## 5. Le versant non maillé

- **Paquets** — une hiérarchie auto-descriptive, `/models/{M}/grids/{g}/packages/{p}`,
  navigable par des liens portant la relation **OGC API**
  `http://www.opengis.net/def/rel/ogc/1.0/data`. 97 triplets relevés sans
  qu'aucun nom de grille ne soit supposé. C'est une **déclaration du
  producteur**, à confronter à un inventaire dérivé des fichiers plutôt
  qu'à y substituer.
- **Observation** — `liste-stations` rend du **CSV à point-virgule**, non du
  JSON : `Id_station;Id_omm;Nom_usuel;Latitude;Longitude;Altitude;…`.
  L'API expose aussi `/liste-bouees`, `/bouees`, `/liste-bateaux` et
  `/bateaux`.
- **Vigilance** — un produit JSON structuré, versionné, avec périodes de
  validité et niveaux par domaine.
- **Radar** — mosaïques et stations, navigables comme les paquets.
- **Climatologie** — un mécanisme en **deux temps**, `commande-station` puis
  `commande/fichier` : asynchrone, donc un régime d'acquisition distinct de
  tous les autres.

Chaque document porte `attribution: "Source : Météo-France"` — la mention de
paternité que la licence exige, livrée dans la charge utile.

---

## 6. Reproduire ce relevé

Le catalogue, sans aucun identifiant :

```bash
curl -s 'https://portail-api.meteofrance.fr/api/am/devportal/v3/apis?limit=200'
```

Le jeton, depuis un identifiant d'application :

```bash
curl -s -X POST -H "Authorization: Basic $X10_MF_APPLICATION_ID" \
  'https://portail-api.meteofrance.fr/token?grant_type=client_credentials'
```

Puis, pour un service donné, `GetCapabilities` et `DescribeCoverage` avant
tout `GetCoverage` — les axes se lisent, ils ne se supposent pas.

Les sondes `X10-DIV-0001`, `X10-DIV-0002` et `X10-DIV-0003` rejouent trois
des constats de cette note en moins de deux secondes chacune ; voir
[`probes/`](../probes).

---

## Licence

Les données relèvent de la **Licence Ouverte 2.0** (Etalab), qui autorise la
réutilisation y compris commerciale sous réserve de mentionner la paternité.

---

## Références

- [arome-paquets-et-api-ciblee.md](arome-paquets-et-api-ciblee.md) et
  [arpege-paquets-et-api-ciblee.md](arpege-paquets-et-api-ciblee.md) — la
  voie des paquets, et le contenu des modèles.
- [divergences-observees.md](divergences-observees.md) — le registre des
  écarts, où chaque constat porte un identifiant.
- [copernicus-data-stores.md](copernicus-data-stores.md) — l'autre
  producteur, dont le GRIB édition 1 pose le même problème.
