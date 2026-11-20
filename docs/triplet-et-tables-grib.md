# Le triplet GRIB2 n'identifie pas un paramètre

**Note technique à l'usage de qui lit des fichiers GRIB2 et les convertit vers
un format autodécrit.**

> **État constaté les 12 et 13 octobre 2026**, avec ecCodes 2.49.0, cfgrib
> 0.9.15.1 et xarray 2026.9.0, sur des granules AROME 0,025° du réseau 06 UTC
> et sur les tables publiées par l'OMM. Les observations décrivent ces dates ;
> **rien ne garantit leur pérennité**. La méthode est donnée en fin de note
> pour les rejouer.

## Objet

Un message GRIB2 identifie son paramètre par trois entiers — discipline,
catégorie, numéro. Toute la chaîne de lecture repose sur l'idée que ce triplet
désigne une grandeur, et une seule.

**Ce n'est pas le cas, et le standard ne le prétend pas.** Cette note établit
ce que la norme de l'OMM garantit réellement, montre un cas mesuré où un même
triplet porte deux champs différents chez un même producteur, et conclut sur
ce qu'une chaîne de lecture doit mettre en place pour ne pas servir une donnée
fausse en silence.

Elle relève aussi un écart de conformité chez un producteur, et un défaut de
notre propre chaîne trouvé en chemin.

---

## 1. Ce que l'OMM standardise, et ce qu'elle ne standardise pas

Relevé sur les sources de l'OMM : le dépôt officiel `wmo-im/GRIB2`, qui porte
les tables en CSV avec leur historique, et le texte du *Manual on Codes*
WMO-No. 306, volume I.2.

### Le format lisible par machine n'est pas normatif, et l'OMM le dit

La forme qui fait foi est le **PDF** du Manual. Les tables lisibles par
machine sont une dérivée explicitement non autoritative : en cas
d'incohérence, « the Manual prevails ». Elles sont diffusées en archives zip
de fichiers CSV.

> **Conséquence directe : il n'existe aucun artefact normatif lisible par
> machine.** Chaque implémentation redérive ses tables depuis de la prose.
> ecCodes, le NCEP et EUMETSAT en produisent chacun une version, et elles
> divergent — ce que la section 3 mesure.

**Précision du 22/10/2026, parce que la phrase se lit de travers.** Un
artefact lisible par machine existe, il est **officiel**, et il n'est pas
normatif : la distribution de l'OMM et l'archive du tag v37 de `wmo-im/GRIB2`
ont la **même empreinte SHA-256**, c'est le même fichier. Ce qui manque n'est
donc pas l'artefact mais son **autorité** — et la clause de préséance ne vit
pas dans l'archive, elle vit sur la page qui la diffuse.

### Aucun engagement de stabilité, et les entrées changent

Mesuré sur l'historique du dépôt officiel : la révision de mai 2025 **réécrit
en place** les descriptions des entrées 20, 21, 22 et 24 de la table 4.2-0-3
— « sub-grid scale » devient « subgrid-scale ». Éditorial cette fois. Rien
dans le standard ne promet que ce le restera, et aucune clause n'interdit de
redéfinir une entrée existante.

### Une dépréciation qui existe, mais que la table qui nous occupe n'emploie pas

Les cinquante entrées de la table 4.2-0-3 portent toutes le statut
`Operational` — **y compris celle dont l'OMM écrit elle-même qu'il ne faut
plus l'employer**. Sur cette table, un lecteur ne peut donc pas détecter par
programme qu'un code est découragé : l'information n'y existe qu'en **note de
texte libre**.

> **Correction du 22/10/2026 : généraliser était faux.** Le mécanisme existe
> et l'OMM s'en sert. Sur l'ensemble de la table 4.2 en v37 : **1 387 entrées
> hors `Reserved` et `Missing`, dont 1 323 `Operational` et 60 `Deprecated`**
> — et il n'est pas récent, la v22 de 2019 en portait déjà cinquante. La
> table 4.2-0-1 à elle seule en compte quinze, dont l'entrée 8, *Total
> precipitation*.
>
> Ce qui reste vrai, et qui est le point utile : le registre SKOS de
> `codes.wmo.int` **ne transporte ni le statut ni les notes**. L'entrée
> dépréciée s'y présente comme une entrée ordinaire, de sorte qu'un
> consommateur qui suit les URI persistantes ne voit pas la dépréciation que
> le CSV déclare.

### Ce qui est, en revanche, solidement défini

Il serait injuste de n'en retenir que les manques. La structure des sections,
l'empaquetage, la géométrie des grilles, les gabarits de produit et les
plages réservées à l'usage local sont précisément spécifiés, et c'est ce qui
rend un lecteur générique possible. Le problème n'est pas le format : c'est
la **sémantique des paramètres**, laissée à des tables dont la gouvernance
n'offre ni stabilité, ni forme faisant autorité — et dont la dépréciation,
qui existe, ne franchit pas le registre à URI persistantes.

---

## 2. L'ambiguïté est dans le standard, documentée et non corrigée

La note 124 de l'OMM, attachée à l'entrée `4.2-0-3-6` :

> « Number 33 (Geometric altitude above mean sea level) or number 34
> (Geometric height above ground level) should be used instead of number 6
> (Geometric height), **because it does not indicate whether this is
> referring to height above mean sea level or height above ground**. »

| Valeur | Libellé OMM | Unité | Statut |
|---|---|---|---|
| 5 | Geopotential height | **gpm** | Operational |
| **6** | **Geometric height** | m | Operational **← note 124** |
| 33 | Geometric altitude above mean sea level | m | Operational |
| 34 | Geometric height above ground level | m | Operational |

L'OMM a donc créé 33 et 34 **pour lever cette ambiguïté**, et laisse le 6
opérationnel. Un producteur qui l'emploie ne viole rien.

### Et elle se constate dans les fichiers

Mesuré le 13/10/2026 sur la grille AROME 0,025°, 1121 × 717 points. Le même
triplet `(0, 3, 6)`, chez le même producteur, à la même date :

| | Champs CONSTANT | Paquet SP2, réseau 06 UTC |
|---|---|---|
| Rôle | relief du modèle | **autre champ**, non identifié |
| Valeurs manquantes | aucune | **17,2 %**, `missingValue = 9999`, bitmap présent |
| Étendue du masque | — | un **cadre** en bordure de domaine, pas la mer |
| min / max | −132,85 / 4 118,90 | −91,01 / **4 031,99** |

La démonstration ne tient pas aux extrema. Le relief se **dérive** du
géopotentiel que porte le paquet HP2, par `relief = z / g − h` : la
dérivation reproduit les champs CONSTANT au centimètre, et s'écarte du champ
SP2 de **0,85 m en médiane en terrain plat** et de **44 m au-dessus de
1 000 m**, avec des excursions jusqu'à ±500 m. L'écart croît avec le relief :
la signature de deux reliefs d'origines ou de résolutions différentes, pas
celle d'un même champ.

La table de définitions que publie le producteur nomme ce code `ALTITUDE`.
Sans préciser laquelle.

---

## 3. Quatre couches d'erreur, chacune ajoutée par un acteur

| Couche | Ce qu'elle fait | Verdict |
|---|---|---|
| OMM | définit `6` sans dire par rapport à quoi, le note, le garde opérationnel | **ambiguïté assumée** |
| Producteur | emploie `6` pour deux champs distincts | **conforme, et indécidable** |
| ecCodes | nomme `6` « Geometrical height above ground » | **tranche sans mandat** |
| Chaîne de lecture | en déduit un nom standard | **faux** |

Notre propre table posait `geopotential_height` pour ce code. C'était faux
deux fois : `geopotential_height` correspond à l'entrée **5**, et s'exprime en
mètres géopotentiels quand le champ est en mètres.

**Les libellés d'ecCodes sont d'ecCodes, pas du standard.** Il nomme par
ailleurs l'entrée 5 « Orography » là où l'OMM écrit « Geopotential height ».
Une chaîne qui lit ces libellés comme la norme hérite de choix qu'aucune
autorité n'a validés.

> **Il n'existe donc pas, et il ne peut pas exister, d'autorité pour une
> correspondance de GRIB vers CF.** Ce n'est pas une lacune d'un projet : c'est
> une propriété du paysage. La réponse n'est pas de chercher la bonne
> référence, mais d'**assumer la sienne et de la rendre défendable** — chaque
> entrée datée, justifiée par le texte de l'OMM, et confrontée au fichier réel.

---

## 4. Un écart de conformité mesuré

La section 1 règle l'usage des tables locales. Son octet 11,
`localTablesVersion`, à zéro signifie que les tables locales ne sont pas
employées, et que **seules les entrées des tables maîtresses hors plage
réservée à l'usage local sont valides**.

Mesuré le 12/10/2026 sur quatre paquets d'AROME 0,025°, réseau 06 UTC,
**863 messages** :

| | Valeur |
|---|---|
| Centre | `lfpw`, sur la totalité des messages |
| `tablesVersion` | 15, sur la totalité des messages |
| `localTablesVersion` | **0**, sur la totalité des messages |
| Paramètres de la plage locale | `(0, 16, 192)`, sur **42 messages** du paquet HP3 |

Le fichier déclare n'employer aucune table locale tout en émettant un
paramètre de la plage locale. Les deux informations se contredisent dans le
même message, et la conséquence est vérifiable : ecCodes rend `shortName`,
`name` **et** `units` à `unknown`.

L'information existe pourtant — la table que publie le producteur résout ce
code en `RFLCTVT`. Ce qui manque est le moyen, pour un lecteur, de savoir
depuis le fichier qu'une table locale s'applique, et laquelle.

**C'est un invariant du format, pas un cas particulier d'un producteur.** Un
contrôle qui le teste rend donc la main sur une source jamais rencontrée,
sans qu'aucune règle nominative ait été écrite.

---

## 5. La table du producteur est une référence, pas une installation

Le producteur publie ses définitions ecCodes en archive, et renvoie vers elle
les utilisateurs signalant des champs non reconnus. La tentation est de la
désigner par `ECCODES_DEFINITION_PATH` et de passer à autre chose.

**Mesuré le 13/10/2026 : c'est une perte nette.** L'archive porte à sa racine
un `grib2/shortName.def` de **753 entrées** qui **masque** celui d'ecCodes,
bien plus fourni, le chemin fourni étant consulté en premier. Sur 33 codes
interrogés à `tablesVersion = 15` et centre `lfpw` :

| | Sans l'archive | Avec l'archive |
|---|---|---|
| `(0, 1, 64)`, `(0, 1, 75)`, `(0, 1, 201)`, `(0, 6, 1)`, `(0, 16, 192)` | `unknown` | **résolus** |
| `(0, 0, 10)`, `(0, 0, 11)`, `(0, 1, 52)`, `(0, 3, 5)`, `(0, 3, 34)`, `(0, 19, 0)` | `slhtf`, `ishf`, `tprate`, `orog`, `h`, `vis` | **`unknown`** |
| `(0, 7, 6)` | unité `m**2 s**-2` | unité **`unknown`** |

Cinq codes gagnés, six perdus, une unité perdue. L'archive se **consulte**
pour les codes qu'ecCodes ne résout pas ; elle ne s'installe pas dans une
chaîne de décodage.

Deux détails du même relevé. L'archive livre une table **maîtresse**,
`grib2/tables/15/4.5.table`, et un dossier `grib2/tables/local/<centre>`
**vide** : le producteur diffuse des concepts, pas des tables locales — ce qui
est cohérent avec son `localTablesVersion = 0`, et laisse le lecteur sans
moyen normalisé de trouver ces définitions. Et le séparateur de chemins est
celui du système : la roue Python ajoute d'elle-même `/MEMFS/definitions` à la
suite du chemin fourni, avec un `;` sous Windows — y écrire un `:` fait
échouer ecCodes au démarrage, le `D:` d'un chemin absolu étant alors coupé.

### Le catalogue date l'archive, l'en-tête HTTP ne la date pas

Deux ressources de ce jeu de données, publiées à quinze jours d'intervalle,
rendent **le même `Last-Modified`, à la seconde près**. L'en-tête décrit donc
l'objet de stockage, pas la publication : il reflète une migration de
l'infrastructure, et non une mise à jour de la donnée.

| Source | Ressource de janvier | Ressource de janvier, quinze jours plus tard |
|---|---|---|
| `last_modified` du catalogue | 15/01/2026 10:37:52 | 30/01/2026 13:33:55 |
| `Last-Modified` HTTP | **02/07/2026 15:45:29** | **02/07/2026 15:45:29** |

> **Conséquence pour qui veut dater un actif de contexte** : sur cette
> plateforme, c'est la **métadonnée du catalogue** qui porte la cadence, pas
> l'en-tête HTTP. L'inverse de ce qu'on suppose d'ordinaire, et l'inverse de
> ce qu'une version antérieure de notre propre analyse avait conclu.

Le catalogue publie par ailleurs une **empreinte SHA-1** par ressource. Celle
de l'archive **ne correspond pas** aux octets servis, relevé le 13/10/2026,
alors que la taille annoncée est exacte à l'octet. Une empreinte publiée qui
ne vérifie rien est un piège : qui la contrôle conclut à une corruption, qui
ne la contrôle pas n'a aucun validateur.

---

## 6. Un défaut de la chaîne de lecture, trouvé en chemin

Tout ce qui précède porte sur ce que d'autres publient. Le relevé a aussi
révélé un défaut du côté lecteur, et il mérite d'être connu de qui emploie
`cfgrib`.

> **Réécrit le 22/10/2026 : le mécanisme décrit ici était faux.** Nous
> l'attribuions au nom court. Mesuré depuis : `cfgrib` nomme d'après
> `cfVarName`, le nom court n'étant qu'un repli, et `open_datasets` — notre
> seul appel — découpe le fichier **par `paramId`**. La perte se produit donc
> **avant tout nommage**.

**Deux triplets qu'ecCodes résout en un même `paramId` ne donnent qu'une
variable.** Le second n'est jamais lu.

| | Mesure |
|---|---|
| Messages dans le fichier | 4 — deux échéances de `(0, 16, 192)`, deux de `(0, 16, 193)` |
| `paramId` rendu | **0** pour les quatre : aucun n'est résolu |
| Champs décodés | **1** |
| Attributs et valeurs du survivant | cohérents, ceux de `(0, 16, 192)` |

La bonne nouvelle est que ce n'est pas un mélange : le champ survivant est
entier et porte sa propre identité. La mauvaise est que l'autre **disparaît
sans un mot**, et qu'un compte rendu d'exécution dirait `success`.

**Aucune option ne le signale** — ni `errors="warn"`, ni `errors="raise"`,
sous aucun des deux appels : le paramètre porte sur les messages illisibles,
et le recouvrement est en amont. La mention de `compat="equals"` que portait
cette note était un emprunt à la décision sur l'assemblage `xarray` : X10 ne
le passe nulle part.

### Et le recouvrement ne touche pas que les codes exotiques

C'est le point qu'on n'attend pas. Les codes irrésolus reçoivent tous
`paramId = 0` et se recouvrent donc entre eux — les codes `(0, 6, 11)` et
`(0, 17, 4)` du paquet SP3 d'ARPEGE 0,25° sont dans ce cas, résolus ni par
ecCodes ni par la table du producteur.

Mais des codes **parfaitement résolus** collisionnent aussi. Recompté le
22/10/2026 au niveau de surface : sur **458 triplets** résolus des
disciplines 0 et 10 — et non 365 —, **six `paramId` sont portés par deux
triplets chacun**.

| `paramId` | Triplets | Ce que c'est |
|---|---|---|
| 3008 | `(0, 3, 6)`, `(0, 3, 34)` | les deux entrées que l'OMM a créées pour être distinctes |
| 229 | `(0, 2, 38)`, `(0, 2, 62)` | deux tensions de surface |
| 230 | `(0, 2, 37)`, `(0, 2, 63)` | idem |
| 140101, 140102, 140218 | — | trois paires du domaine des vagues |

**Ce sont les seuls qui fassent disparaître un champ.** Le cas de `h` est le
plus parlant : `(0, 3, 6)` et `(0, 3, 34)` ne partagent **pas un nom**, ils
partagent le `paramId` 3008 — la collision est en amont du nommage, et
**aucune liste de noms n'aurait pu l'attraper**. C'est l'argument du contrôle
contre la liste, et il est plus fort que celui que nous avancions.

**Trois vrais recouvrements de nom existent par ailleurs** — `tmax` pour une
température maximale et une période de houle, `cdct`, `tcond` — et ils ne
perdent **rien** sur notre chemin : le découpage par `paramId` les sépare en
jeux distincts, où ils portent le même nom sans se recouvrir. La cinquième
ligne de notre tableau précédent, `~` pour trois codes, était une fausse
alerte : leurs `cfVarName` sont distincts.

**Le compte dépend du type de niveau**, ce que la mesure d'origine ne disait
pas : 458 triplets et six collisions en surface, 393 et deux à
`heightAboveGround`.

> **C'est ce qui fait pencher pour un contrôle plutôt qu'une liste.** Une
> liste de codes connus aurait manqué les trois quarts de ce tableau, et
> n'aurait rien dit d'une source jamais rencontrée.

**La détection tient en une comparaison** : les identifiants présents dans les
en-têtes du fichier, confrontés à ceux des champs décodés. Le relevé des
en-têtes ne décompresse aucune donnée, et son coût reste négligeable sur un
granule de plusieurs centaines de mébioctets.

---

## 7. Ce que X10 en fait

| Constat | Réponse |
|---|---|
| `(0, 3, 6)` est ambigu | l'entrée est **retirée** de la table GRIB → CF et inscrite dans un ensemble `AMBIGUOUS_TRIPLETS`, distinct de `WITHOUT_CF_NAME` |
| Un code de la plage locale sans table locale | `grib2.check_local_tables`, un invariant du format — il **signale**, il ne refuse pas de servir |
| Deux codes irrésolus se recouvrent | `grib2.dropped_fields`, sous le même paramètre `errors` que les messages illisibles — **lève** par défaut |
| La table du producteur | consultée comme référence, **pas installée** dans la chaîne |
| Les écarts constatés | remontés au producteur, datés et reproductibles |

Distinguer `AMBIGUOUS_TRIPLETS` de `WITHOUT_CF_NAME` n'est pas cosmétique : l'un se
corrige en proposant un nom au tableau CF, l'autre non. Les confondre ferait
porter à CF un manque qui est celui du code GRIB.

**Le choix de retirer plutôt que de renommer** mérite d'être explicite.
Remplacer une supposition par une autre n'aurait rien valu : un champ sans
`standard_name` se voit comme tel, là où un nom faux se propage dans tout ce
qui lit le fichier.

Noter aussi que les deux contrôles **n'ont pas le même régime**, et que la
différence est de fond. Un code mal nommé est une métadonnée dégradée : on
livre, on signale. Un champ disparu est de la donnée en moins : on lève. La
tolérance reste accessible à qui l'assume, par le paramètre qui gouvernait
déjà les messages illisibles.

### Ce qui n'est délibérément pas construit

Un registre complet des divergences — assertions datées par source,
résolutions justifiées, non-conformités caractérisées par une condition
testable — a été conçu, et n'est pas écrit. La raison tient en une ligne :
**un seul cas de triplet ambigu est établi**, et concevoir une mécanique
générale sur un échantillon de un produit une mécanique fausse.

Ce qui est écrit est ce qui tient sur un cas : une exclusion nommée, et deux
contrôles qui testent des **invariants du format** plutôt que des cas connus
— donc qui valent pour des sources jamais rencontrées. Le registre viendra
quand les cas le demanderont, pas avant.

---

## 8. Rejouer ces mesures

Les codes et leurs libellés, à une version de tables donnée :

```python
import eccodes

h = eccodes.codes_grib_new_from_samples("regular_ll_sfc_grib2")
eccodes.codes_set(h, "tablesVersion", 37)  # avant les parametres
eccodes.codes_set(h, "centre", 85)
eccodes.codes_set(h, "discipline", 0)
eccodes.codes_set(h, "parameterCategory", 3)
eccodes.codes_set(h, "parameterNumber", 6)
print({c: eccodes.codes_get(h, c) for c in ("shortName", "name", "units", "cfName")})
eccodes.codes_release(h)
```

> **Piège de méthode, à ne pas reproduire.** L'échantillon d'ecCodes porte
> `tablesVersion = 4`. Interroger un triplet sans fixer cette version fait
> sortir des codes récents en `unknown`, et accuse à tort la table qu'on
> vérifie.

Les déclarations de tables d'un granule, et ses paramètres de la plage
locale : parcourir les messages avec `codes_grib_new_from_file`, relever
`centre`, `tablesVersion`, `localTablesVersion` et le triplet, et retenir
ceux dont une composante atteint 192.

Le relief dérivé du géopotentiel : `relief = z / g − h`, avec `g = 9,80665`,
`z` le géopotentiel d'un niveau hauteur et `h` ce niveau. La valeur ne dépend
pas du niveau choisi — vérifié à 0,102 m près entre 10 m et 3 000 m.

Les textes de l'OMM se consultent sur le dépôt `wmo-im/GRIB2`, dont
l'historique git donne les révisions des tables, et dans le *Manual on Codes*
WMO-No. 306 volume I.2, qui fait foi.

---

## Références

- WMO-No. 306, *Manual on Codes*, volume I.2 — la forme normative, en PDF.
- Dépôt `wmo-im/GRIB2` — tables en CSV, dérivées et non autoritatives, avec
  leur historique.
- Table 4.2-0-3 de l'OMM, et sa note 124.
- Documentation ecCodes, clés `shortName`, `cfName`, `tablesVersion`,
  `localTablesVersion`.
- Tableau des noms standards CF, version 95.
- [docs/unites-et-interoperabilite.md](unites-et-interoperabilite.md) — le
  pendant de cette note sur les unités.

---

## Décisions arrêtées, déplacées du guide le 20/11/2026

*Elles occupaient la moitié d'un fichier relu à chaque session. Le guide
y renvoie désormais ; le texte est inchangé.*

- **La correspondance GRIB vers CF nous incombe, mais le vocabulaire CF ne manque pas.** Le tableau CF, version 95, compte plus de cinq mille noms et contient `wind_speed`, `wind_from_direction`, `visibility_in_air` et le reste ; c'est **la table de correspondance livrée par ecCodes** qui est incomplète — 9 codes sur 51 pour AROME, 9 sur 64 pour ARPEGE. `grib2.CF_STANDARD_NAMES` comble le manque, **chaque nom vérifié présent au tableau officiel**. Un nom inventé produirait un fichier qui se dit conforme sans l'être, et `WITHOUT_CF_NAME` recense ce que CF ne couvre réellement pas.
  Piège associé : la chaîne de décodage pose `standard_name = "unknown"`, valeur **pire qu'une absence**. Elle est retirée.

- **La discipline 10 est ouverte, et la vérification des noms CF n'est plus une affirmation.** Cinq noms y sont posés — hauteur significative, direction moyenne, période moyenne, période de passage par zéro, période de pic —, chacun relevé au tableau CF version 95. **Le nom qui semble évident n'est pas toujours le bon** : `sea_surface_wave_mean_from_direction` désigne chez CF une grandeur *spectrale*, « the wave direction in each frequency band », que sa description distingue explicitement du paramètre global ; `mwd` étant global, c'est le nom générique qui convient. Un test marqué `network` confronte désormais **toute** la table au tableau officiel que CF publie, et échoue sur un nom absent ou devenu un alias. C'était le défaut le plus coûteux de notre correspondance : un nom inventé produit un fichier qui se dit conforme sans l'être, ne casse rien, et ne se voit pas.
  **Deux champs restent sans nom, pour deux raisons distinctes.** `cdww`, « Coefficient of drag with waves », rejoint `WITHOUT_CF_NAME` : CF a bien `surface_drag_coefficient_for_momentum_in_air`, mais il ne dit rien des vagues — or c'est exactement la distinction que l'OMM trace en nommant le code ainsi, et l'effacer confondrait un coefficient calculé par un modèle de vagues avec un coefficient qui ne l'est pas. `wmb`, « Model bathymetry », rejoint `AMBIGUOUS_TRIPLETS` sous une **seconde forme d'ambiguïté** : ce n'est pas le code qui désigne plusieurs champs, c'est CF qui exige une précision que le producteur ne déclare pas — cinq profondeurs de fond selon le niveau de référence, et rien dans le message ne dit lequel. Le classement reste juste : rien à proposer à CF, seulement un choix que nous ne pouvons pas faire.
  **Deux unités manquaient, et elles bloquaient le flux entier** : `s` et `dimensionless` levaient à l'écriture, donc trois des douze champs de vagues auraient échoué trois étapes plus loin. `dimensionless` n'est pas lisible par UDUNITS — vérifié —, alors que `1`, sa forme canonique, l'est.

- **Un axe de membres ne se reconnaît pas à sa présence.** Mesuré le 19/10/2026 sur trois gabarits : un déterministe `4.0` ne porte aucune clé d'ensemble, un ensemble `4.1` déclare sa taille et un numéro de perturbation, et le gabarit `4.104` des hauteurs de vagues **remplit les octets d'ensemble de zéros**. `cfgrib` en tire alors un axe `number` de longueur 1, et `Variable.realizations` valait 1 sur une prévision déterministe — défaut introduit le matin même et corrigé le soir. Le discriminant retenu est `numberOfForecastsInEnsemble`, strictement positif : il ne suppose aucune liste de gabarits, qu'il faudrait redériver d'une table de l'OMM.

- **La version des tables de l'OMM est comparée, pas supposée.** Chaque message GRIB2 déclare la version de tables maîtresses contre laquelle il a été écrit. `grib2.check_tables_version` la confronte à `tablesVersionLatest` — la plus récente que notre ecCodes sache résoudre — et **signale l'écart une fois par granule**, la version étant une propriété du fichier et non de chacun de ses hypercubes.
  **Pourquoi il le faut, vérifié le 09/10/2026.** Les définitions d'ecCodes ne sont pas absentes de la roue : elles y sont **compilées**, `codes_definition_path()` rendant `/MEMFS/definitions`. La version connue est donc une **propriété de la version du paquet**, pas un réglage. Et demander une version supérieure **ne lève rien** : `tablesVersion = 40` est accepté et relu tel quel, un paramètre non résolu sortant en `shortName='unknown'`, `units='unknown'`, sans un mot.
  **Ce qui nous protégeait était accidentel.** Une unité `unknown` heurte la table UDUNITS fermée de `netcdf_cf`, qui lève — mais trois étapes plus loin, par un garde-fou qui n'a pas été conçu pour cela.
  **Correction du 13/10/2026 : la justification initiale supposait une commutation qui n'existe pas.** Il était écrit qu'« un paramètre redéfini par une version ultérieure se résoudrait silencieusement ». Mesuré depuis : **poser `tablesVersion` ne commute pas la résolution d'ecCodes**. Entre la v1 et la v37, 493 triplets donnent un résultat identique, et `(0, 3, 34)` — entrée récente de la table 4.2-0-3 — se résout déjà en v1. Le nom court provient d'une base de paramètres **indépendante de la version**, pas des tables versionnées. Le contrôle reste juste et utile — un producteur en avance sur notre outillage est un signal réel — mais il ne protège pas d'une redéfinition, et prétendre le contraire donnerait une garantie illusoire. Répondre à « une entrée a-t-elle jamais été redéfinie ? » exigerait de diffuser les fichiers de table entre éditions ; c'est une investigation délimitée, non engagée.
  **Mesuré sur donnée réelle le 09/10/2026** : notre roue 2.49.0 connaît les tables jusqu'à la **37**, et AROME 0,025° SP1 déclare la **15** — vingt-deux versions de marge. Le risque est donc faible aujourd'hui ; c'est précisément ce qu'on ignorait avant de le mesurer. Un test `network` le vérifie et échouera le jour où un producteur prendra de l'avance.
  **L'écart ne lève pas**, délibérément : une table plus récente n'est pas une panne, la plupart des paramètres continuant de se résoudre. C'est un signal pour l'exploitant, pas un refus de servir.

- **Le triplet GRIB2 n'identifie pas un paramètre, et la norme ne le prétend pas.** Enquête, mesures et méthode **ci-dessus**.
  **Et personne d'autre n'a livré cette correspondance — vérifié le 19/10/2026.** CF a porté un élément `grib` par entrée de son tableau : **GRIB édition 1 uniquement**, 113 entrées sur 4 872, gelées seize ans, **retirées en v87 le 12/11/2024** au motif écrit que personne ne les maintenait. Le registre désigné par la feuille de route de l'atelier ECMWF de 2014 est hors service depuis 2019, et la table d'une bibliothèque de lecture qui en dérive est un instantané figé de 2016 dont l'en-tête « AUTO-GENERATED » a été retiré faute de source. Les correspondances vivantes plafonnent toutes autour de **6 %** des paramètres de la table 4.2. **Nous ne refaisons pas un travail fait : nous reprenons un travail que plusieurs ont commencé et qu'aucun n'a tenu.**
  **La faible couverture d'ecCodes a une cause mécanique**, et elle n'est pas un oubli : son générateur joint sur un identifiant GRIB1 **local au centre européen**, de sorte qu'un nom CF n'existe que pour un paramètre portant cet héritage. Nos 9 codes sur 51 et 9 sur 64 sont le comportement nominal.

- **Une correspondance n'est pas un livrable, c'est un processus.** C'est la leçon des tentatives passées : aucune n'est morte d'avoir eu tort, toutes sont mortes de ne pas avoir été tenues. Trois aptitudes en découlent, et elles sont réalisables — tracer un ajout, **relire une table dans sa version X**, comparer n-1 et n. La deuxième est acquise : CF archive v1 à v95, les tables GRIB2 lisibles par machine sont publiées en versions, et les définitions d'ecCodes étant compilées dans la roue, **la version du paquet est la version des tables**.
  **Corollaire sur les dépendances, mesuré le 19/10/2026.** Le backend de `cfgrib` expose **vingt** options ; nous en fixons **huit** ; **douze sont héritées**. La docstring d'`OPTIONS_CFGRIB` en annonçait dix-huit — sur la même version de la bibliothèque, donc **un comptage inexact de notre part**, pas une dérive. La règle « on écrit les options plutôt que de les hériter » reposait sur ce chiffre. Les douze héritées sont désormais nommées dans la docstring ; les contrôler par introspection de signature reste à faire.
  **Quatre points établis sur les sources de l'OMM, le 13/10/2026.** La forme normative est le **PDF** du *Manual on Codes* ; les tables lisibles par machine sont une dérivée explicitement non autoritative — « the Manual prevails ». Il n'existe donc **aucun artefact normatif exploitable par programme** : un artefact lisible par machine existe bel et bien, il est officiel, et il n'est pas normatif. **Mesuré le 22/10/2026** : la distribution de l'OMM et l'archive du tag v37 de `wmo-im/GRIB2` ont la **même empreinte SHA-256** — c'est le même fichier —, et la clause de préséance vit sur la page de l'OMM, non dans l'archive. Aucun engagement de stabilité : la révision de mai 2025 a **réécrit en place** quatre entrées de la table 4.2-0-3.
  **Correction du 22/10/2026 : « aucun mécanisme de dépréciation » était vrai d'une table et faux de la table.** La 4.2-0-3 porte bien cinquante entrées toutes `Operational`, y compris celle que l'OMM dit de ne plus employer. Mais sur l'ensemble de la table 4.2 en v37 : **1 387 entrées hors `Reserved` et `Missing`, dont 1 323 `Operational` et 60 `Deprecated`** — et le mécanisme n'est pas récent, la v22 de 2019 en portait déjà cinquante. Ce qui reste vrai, et qui est le point utile : le registre SKOS de `codes.wmo.int` **ne transporte ni le statut ni les notes**, de sorte que l'entrée dépréciée s'y présente comme une entrée ordinaire. Généraliser d'une sous-table à la table était la faute ; elle valait d'être mesurée.
  **D'où la conclusion qui engage le projet** : il n'existe pas, et il ne peut pas exister, d'autorité pour notre correspondance GRIB → CF. Ce n'est pas une lacune de notre travail mais une propriété du paysage. La réponse n'est pas de chercher la bonne référence, c'est d'**assumer la nôtre et de la rendre défendable** — datée, justifiée par le texte de l'OMM, confrontée au fichier réel.
  **`(0, 3, 6)` est retiré de `CF_STANDARD_NAMES`.** La note 124 de l'OMM recommande elle-même les numéros 33 et 34 à sa place, « because it does not indicate whether this is referring to height above mean sea level or height above ground ». Mesuré sur la grille AROME 0,025° : le code porte le relief du modèle dans les champs CONSTANT et un **autre** champ dans le paquet SP2 — masqué sur 17,2 %, s'écartant du relief de 44 m en médiane au-dessus de 1 000 m, la dérivation `z/g − h` depuis HP2 reproduisant CONSTANT au centimètre. Notre table posait `geopotential_height`, **faux deux fois** : c'est l'entrée 5, et elle s'exprime en mètres géopotentiels. `AMBIGUOUS_TRIPLETS` le recense, **distinct de `WITHOUT_CF_NAME`** — l'un se corrige en proposant un nom à CF, l'autre non. **Retirer plutôt que renommer** : remplacer une supposition par une autre ne vaut rien, et un champ sans `standard_name` se voit comme tel.
  **Les libellés d'ecCodes sont d'ecCodes, pas du standard.** Il nomme l'entrée 5 « Orography » là où l'OMM écrit « Geopotential height », et tranche sur le 6 sans mandat. Les lire comme la norme, c'est hériter de choix qu'aucune autorité n'a validés.
  **Confirmation la plus nette, mesurée le 19/10/2026 sur le flux de vagues d'ECMWF : sept messages portent `(10, 0, 3)`.** Un seul, de gabarit `4.0`, est la hauteur significative totale ; les six autres, de gabarit `4.104`, sont des hauteurs significatives **par bande de période** — 10 à 12 s, 12 à 14 s, et ainsi de suite. Le triplet ne les sépare pas. D'où `grib2.TEMPLATE_RESTRICTED`, qui n'autorise un nom que sous les gabarits vérifiés, et `productDefinitionTemplateNumber` ajouté aux clés lues et à `GRIB_IDENTITY` : sans lui, l'identité d'un champ est incomplète.
  **Correction du 22/10/2026 : « le gabarit si » était trop fort, et ne pouvait pas être vrai.** Rejoué sur le granule réel, le gabarit et le type de niveau séparent **conjointement** la hauteur totale — `4.0`, `surface` — des six hauteurs par bande — `4.104`, `meanSea`. Mais **aucune des sept composantes de `GRIB_IDENTITY` ne sépare les six bandes entre elles** : elles rendent une seule et même identité. L'entrée 104 de la table 4.0 le dit elle-même, « for waves selected by period range » : la bande vit **à l'intérieur** du gabarit, dans les clés `typeOfWavePeriodInterval` et les bornes d'intervalle. Ce qui les sépare dans le fichier n'est ni le triplet ni le gabarit, c'est le `paramId` qu'ecCodes résout depuis ces octets — 140114 à 140119 contre 140229 — et dont `cfgrib` tire le nom de variable. Fermer l'identité exigerait d'ajouter les clés de bande ; aucune perte n'est observée aujourd'hui, et l'écart est épinglé plutôt que comblé à l'aveugle.
  Pourquoi cela ne pouvait pas rester en l'état : des hauteurs par bande se composent en **somme quadratique**, non en somme. Un consommateur qui les additionnerait sous le nom du total obtiendrait une valeur sans signification — et rien ne le lui signalerait. CF n'ayant aucun nom pour une hauteur restreinte à une bande, les six restent sans nom standard, et l'absence se voit.

- **Deux contrôles de conformité, et ils testent des invariants du format, pas des cas connus.** C'est ce qui leur permet de rendre la main sur une source jamais rencontrée, sans qu'aucune règle nominative soit écrite. Les modéliser plus avant attendra le troisième cas : concevoir une mécanique générale sur un échantillon de un produit une mécanique fausse.
  **`grib2.check_local_tables` — un code de la plage locale sans table locale.** La section 1 donne à son octet 11 la valeur zéro pour dire que les tables locales ne sont pas employées, donc que seules les entrées hors plage réservée sont valides. Mesuré le 12/10/2026 sur 863 messages d'AROME 0,025° : tous déclarent `localTablesVersion = 0`, et 42 portent `(0, 16, 192)`. ecCodes rend alors `shortName`, `name` **et** `units` à `unknown`. Le contrôle **signale**, il ne refuse pas de servir : c'est une métadonnée dégradée, le reste du fichier est bon.
  **`grib2.dropped_fields` — un champ qui disparaît au décodage, et celui-là lève.** **Correction du 22/10/2026 : le mécanisme n'est pas celui que nous décrivions.** `cfgrib` ne nomme pas d'après le nom court mais d'après `cfVarName`, le nom court n'étant qu'un repli ; et `open_datasets` — notre seul appel — découpe le fichier **par `paramId`**. Le recouvrement se produit donc **avant tout nommage** : ce que nous rencontrons est une collision de `paramId`, deux triplets distincts qu'ecCodes résout en un même identifiant. Quatre messages entrent, un champ sort, sans exception ni avertissement, et le compte rendu dirait `success`. Aucune option ne le signale — ni `errors="warn"`, ni `errors="raise"`, sous aucun des deux appels. La mention de `compat="equals"` était un emprunt : X10 ne le passe nulle part. Deux paramètres de `paramId` distincts partageant un nom de variable, eux, **ne perdent rien** sous `open_datasets`, qui les rend dans deux jeux séparés. C'est de la **donnée en moins**, pas une métadonnée dégradée, donc le même régime que `errors`, dont le paramètre gouverne désormais les deux.
  **Le recouvrement ne touche pas que les codes exotiques**, et c'est ce qui fait pencher pour un contrôle plutôt qu'une liste. Recompté le 22/10/2026, au niveau de surface : **458 triplets des disciplines 0 et 10 se résolvent**, et **six `paramId` sont portés par deux triplets chacun** — 229, 230, 3008, 140101, 140102, 140218. Ce sont les seuls qui fassent disparaître un champ. Le cas emblématique reste `(0, 3, 6)` et `(0, 3, 34)`, qui ne partagent **pas un nom** mais le `paramId` 3008 : la collision est en amont du nommage, et aucune liste de noms ne l'aurait attrapée — ce qui renforce l'argument du contrôle contre la liste au lieu de l'affaiblir. Le compte dépend du **type de niveau** : 458 triplets et six collisions en surface, 393 et deux à `heightAboveGround`.
  **La détection tient en une comparaison** : les triplets des en-têtes confrontés à ceux des champs décodés, sans décompresser aucune donnée. Un message illisible y est **passé, non compté perdu** — d'un message qu'on ne sait pas lire on ne peut rien affirmer, et l'imputer au décodage l'accuserait d'une faute qui n'est pas la sienne.

- **La table de définitions d'un producteur se consulte, elle ne s'installe pas.** Mesuré le 13/10/2026 sur l'archive publiée par Météo-France : la désigner par `ECCODES_DEFINITION_PATH` est une **perte nette**. Son `grib2/shortName.def` de 753 entrées **masque** celui d'ecCodes, le chemin fourni étant consulté en premier — cinq codes gagnés, **six perdus**, et une unité perdue qui ferait lever notre table UDUNITS trois étapes plus loin. L'archive livre d'ailleurs une table **maîtresse** et un dossier de tables locales **vide** : le producteur diffuse des concepts, pas des tables locales.
  Deux pièges d'outillage au passage. La roue Python **ajoute d'elle-même** `/MEMFS/definitions` à la suite du chemin fourni, avec le séparateur du système — y écrire un `:` sous Windows fait échouer ecCodes au démarrage, le `D:` d'un chemin absolu étant alors coupé. Et l'échantillon d'ecCodes porte `tablesVersion = 4` : interroger un triplet sans fixer cette version fait sortir des codes récents en `unknown`, et accuse à tort la table qu'on vérifie.
