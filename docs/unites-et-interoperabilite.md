# Unités : du GRIB2 au NetCDF-CF, ce que les standards exigent et ce que les outils en font

**Note technique à l'usage de qui convertit des données météorologiques du
GRIB2 vers le NetCDF-CF.**

> **État constaté le 8 octobre 2026**, avec ecCodes 2.49.0, cfgrib 0.9.15.1,
> xarray 2026.9.0, netCDF4 1.7.4 (libnetcdf 4.9.3) et cf-units 3.3.1
> (UDUNITS-2 embarqué). Les observations décrivent ces versions ; **rien ne
> garantit leur pérennité**. La méthode est donnée en fin de note pour pouvoir
> les rejouer.

## Objet

Convertir un champ GRIB2 en NetCDF-CF paraît trivial du côté des unités : on
recopie la chaîne que porte le message. Trois standards se rencontrent
pourtant à cet endroit — GRIB, CF et UDUNITS — et **aucun outil de la chaîne
ne vérifie la cohérence de l'ensemble**. Le fichier produit peut donc déclarer
une conformité qu'il n'a pas, sans qu'aucune étape n'ait protesté.

Cette note établit, par lecture des sources et par exécution, ce que chaque
pièce exige réellement et ce que chaque outil fait réellement. Elle corrige au
passage deux idées reçues, dont une que ce dépôt a lui-même portée.

---

## 1. Les trois pièces, et qui exige quoi

| Pièce | Ce qu'elle impose | Ce qu'elle ne fait pas |
|---|---|---|
| **Conventions CF**, § 3.1 | l'attribut `units` doit être analysable par UDUNITS, et physiquement cohérent avec le `standard_name` | ne fournit aucun analyseur |
| **UDUNITS-2** | la grammaire et la bibliothèque de référence qui dit si une chaîne est valide | ignore tout de CF et des `standard_name` |
| **ecCodes** | la chaîne `units` effectivement portée par le message, issue de sa base de paramètres | ne vise pas UDUNITS |

Le point à retenir est l'**absence de boucle de contrôle** : CF délègue à
UDUNITS, UDUNITS ne connaît pas CF, et ecCodes ne cherche à satisfaire ni l'un
ni l'autre. La cohérence est entièrement à la charge de qui convertit.

---

## 2. Ce que la grammaire UDUNITS accepte réellement

Lecture de `lib/scanner.l` et `lib/parser.y` dans les sources d'UDUNITS-2,
confirmée par exécution. Les règles qui comptent :

| Construction | Rôle dans la grammaire |
|---|---|
| deux unités juxtaposées | **multiplication** |
| `-`, `.`, `*`, `·`, une suite d'espaces | **multiplication**, toutes équivalentes |
| `^` et `**` suivis d'un entier signé | **exposant** |
| un entier signé collé à un identifiant | **exposant** |

### Conséquence n° 1 : `**` est une syntaxe valide

Les quatre écritures ci-dessous désignent la même unité, et UDUNITS les réduit
toutes à la même définition canonique :

| Écriture | Définition rendue par UDUNITS |
|---|---|
| `m s-1` | `m.s-1` |
| `m.s-1` | `m.s-1` |
| `m s**-1` | `m.s-1` |
| `m s^-1` | `m.s-1` |

**C'est une idée reçue que ce dépôt a d'abord véhiculée.** Il y était écrit
qu'un fichier portant les unités d'ecCodes, en `**`, « se dit conforme sans
l'être ». C'est faux : un contrôleur CF ne le rejetterait pas. L'affirmation a
été corrigée, et la vérification qui l'a défaite est la raison d'être de cette
note.

### Conséquence n° 2 : le tiret est surchargé, donc l'espacement est piégeux

Le même caractère `-` vaut multiplication dans un contexte et ouvre un exposant
dans l'autre ; c'est la **correspondance la plus longue** qui tranche. Dès lors
qu'on aère l'écriture, le `-` redevient une multiplication :

| Écriture | Résultat |
|---|---|
| `m s-1` | valide, m·s⁻¹ |
| `m s - 1` | **refusée par UDUNITS** |

À retenir : **ne jamais embellir une unité en ajoutant des espaces.** Une mise
en forme qui paraît cosmétique change l'analyse.

### Conséquence n° 3 : la forme canonique est celle à tiret collé

La suite de tests d'UDUNITS n'emploie que `s-1`, `K-1`, `m.s-1`, `m2.s-2`,
`kg.m2.s-3`, `kg2.m4.s-6` : la forme `**` n'y figure nulle part. C'est aussi
ce qu'émettent les producteurs de NetCDF examinés. Convertir vers cette forme
n'est donc pas une question de conformité mais d'**interopérabilité** : un
consommateur qui n'embarque pas un analyseur UDUNITS complet, et beaucoup se
contentent de découper sur les séparateurs, peut lire `m s**-1` comme un
produit.

---

## 3. Ce que les outils font réellement

### ecCodes : `"unknown"` est une chaîne, pas une absence

Sur un paramètre que sa base ne reconnaît pas, ecCodes ne laisse pas la clé
vide : il renvoie littéralement la chaîne `unknown`, pour l'unité comme pour
le nom CF et pour le nom court de la variable.

| Paramètre du message | `units` | `cfName` |
|---|---|---|
| reconnu (température) | `K` | `air_temperature` |
| non reconnu | `unknown` | `unknown` |

C'est **pire qu'une absence** : un consommateur qui teste la présence de
l'attribut reçoit une valeur vraie, et l'écrit dans son fichier de sortie.
`unknown` n'est ni une unité UDUNITS ni un nom standard CF ; une variable qui
le porte est non conforme tout en ayant l'air renseignée. La parade est de
**retirer** ces valeurs plutôt que de les propager.

### cfgrib : recopie sans aucun contrôle

`units` figure dans la liste des clés lues sur le message ; cfgrib la place
dans `GRIB_units` puis la recopie **verbatim** dans `units`. Aucune
validation, aucune conversion.

Deux détails utiles :

- les unités que cfgrib **fabrique lui-même**, pour les coordonnées, sont
  déjà canoniques : `degrees_north`, `degrees_east`, `m`, `Pa`, `1`,
  `seconds since 1970-01-01T00:00:00`. Seules les unités **héritées du
  producteur** posent question ;
- quand aucune unité n'est disponible, cfgrib écrit `"1"`, c'est-à-dire
  **sans dimension**. C'est une affirmation, non un aveu d'ignorance. Ce repli
  ne se déclenche pas derrière ecCodes, qui fournit toujours `unknown` ; il
  reste un piège pour qui alimente cfgrib autrement.

### cfgrib ne dépend pas d'UDUNITS, et c'est instructif

Son unique conversion d'unités, dans `cf2cdm/cfunits.py`, est une **table
codée en dur** couvrant deux dimensions — pression et longueur — qui lève une
exception sur tout le reste. L'ECMWF, auteur de la bibliothèque, a donc choisi
une table fermée plutôt qu'une dépendance à UDUNITS. C'est un précédent utile
pour qui hésite.

### xarray et netCDF4 : `units` est un attribut opaque

Ni l'un ni l'autre n'interprète l'attribut. Un fichier NetCDF portant
`units = "parsecs par fortnight"` s'écrit et se relit sans le moindre
avertissement.

### Un validateur portable existe — contrairement à ce qu'on lit souvent

`cfchecker`, le contrôleur de référence, réclame la bibliothèque C UDUNITS-2
installée séparément, ce qui le rend malcommode hors Linux. **Mais `cf-units`
publie des roues binaires avec UDUNITS-2 embarqué** pour Windows, Linux et
macOS, en ABI stable — donc une seule roue pour toutes les versions de Python
à partir de 3.11. Il est sous licence BSD-3-Clause et n'amène que `cftime`,
`jinja2` et `numpy`.

Valider chaque unité émise contre UDUNITS lui-même est donc à portée, sur les
trois systèmes, pour un coût d'installation négligeable. La seule lacune
relevée est l'absence de roue pour Linux ARM.

> **Mis en œuvre.** Depuis le 8 octobre 2026, la suite de tests de ce dépôt
> soumet chaque unité émise à UDUNITS, et compare la **définition réduite**
> de part et d'autre de la conversion — ce qui prouve que la canonicalisation
> ne change pas la grandeur, garantie plus forte qu'une validité syntaxique.

Un avertissement cependant : `cf-units` **court-circuite** les chaînes
`unknown` et `no_unit`, qu'il traite comme des sentinelles internes sans les
soumettre à UDUNITS. Elles passent donc sa validation alors qu'UDUNITS les
refuserait. Un test qui s'appuie sur lui doit les écarter explicitement.

---

## 4. La correspondance ecCodes vers UDUNITS, vérifiée

Les vingt chaînes d'unité relevées sur les sources exploitées ici, soumises à
UDUNITS dans leur forme d'origine puis dans leur forme canonique. La colonne de
droite est la **définition réduite** que rend UDUNITS : son identité de part et
d'autre prouve que la conversion ne change pas la grandeur.

| Chaîne ecCodes | Acceptée telle quelle | Forme canonique | Définition réduite, identique des deux côtés |
|---|---|---|---|
| `%` | oui | `%` | `0.01 1` |
| `K` | oui | `K` | `K` |
| `Pa` | oui | `Pa` | `m-1.kg.s-2` |
| `m` | oui | `m` | `m` |
| `J kg**-1` | oui | `J kg-1` | `m2.s-2` |
| `J m**-2` | oui | `J m-2` | `kg.s-2` |
| `K m**2 kg**-1 s**-1` | oui | `K m2 kg-1 s-1` | `m2.kg-1.s-1.K` |
| `N m**-2` | oui | `N m-2` | `m-1.kg.s-2` |
| `Pa s**-1` | oui | `Pa s-1` | `m-1.kg.s-3` |
| `W m**-2` | oui | `W m-2` | `kg.s-3` |
| `kg kg**-1` | oui | `kg kg-1` | `1` |
| `kg m**-2` | oui | `kg m-2` | `m-2.kg` |
| `kg m**-2 s**-1` | oui | `kg m-2 s-1` | `m-2.kg.s-1` |
| `m s**-1` | oui | `m s-1` | `m.s-1` |
| `m**2 s**-2` | oui | `m2 s-2` | `m2.s-2` |
| `s**-1` | oui | `s-1` | `s-1` |
| **`Degree true`** | **non** | `degree` | `0.0174532925199433 rad`, soit pi/180 |
| **`(0 - 1)`** | **non** | `1` | `1` |
| **`(Code table 4.201)`** | **non** | *aucune unité émise* | — |
| **`unknown`** | **non** | *aucune unité émise* | — |

Le partage est net, et c'est le résultat le plus utile de ce relevé : **les
seize chaînes à exposant sont déjà valides** et leur réécriture est une pure
canonicalisation ; **les quatre seules que UDUNITS refuse sont exactement les
quatre qui ne sont pas des unités** — une convention d'azimut, une fraction,
un renvoi à une table de codes, et un aveu d'ignorance.

Les deux dernières ne doivent recevoir **aucune unité**. `(Code table 4.201)`
désigne un type de précipitation, qui relève en CF d'une variable de drapeau
avec `flag_values` et `flag_meanings` — pas d'une grandeur continue.

---

## 5. Ce qui en découle pour qui convertit

1. **Recopier l'unité du GRIB sans la regarder est un risque**, modéré sur la
   syntaxe — `**` passe — mais réel sur les quatre cas qui ne sont pas des
   unités.
2. **Traiter `unknown` comme une absence**, et retirer l'attribut plutôt que
   l'écrire. Même règle pour `standard_name`.
3. **Ne jamais deviner une conversion** : une unité hors du périmètre connu
   doit interrompre l'écriture, pas produire un fichier faux. Une erreur à
   l'écriture se corrige ; un fichier faux se propage.
4. **Conserver l'unité d'origine** dans un attribut distinct — `GRIB_units` —
   pour que la conversion reste auditable.
5. **Ne pas aérer les unités** : l'espacement autour du tiret change
   l'analyse, et peut la faire échouer.
6. **Valider pour de bon**, maintenant qu'une bibliothèque UDUNITS portable
   existe, plutôt que de s'en remettre à une liste tenue à la main. Comparer
   les **définitions réduites** de part et d'autre d'une conversion, et non
   les seuls libellés : c'est ce qui distingue « la chaîne est analysable » de
   « la grandeur est inchangée ».

---

## 6. Comment rejouer ces vérifications

Aucune donnée n'est nécessaire, et rien ne demande d'accès réseau au-delà de
l'installation des bibliothèques.

| Vérification | Méthode |
|---|---|
| Règles de la grammaire | lire `lib/scanner.l` et `lib/parser.y` dans les sources d'UDUNITS-2 |
| Formes acceptées, définitions réduites | installer `cf-units` et soumettre chaque chaîne, en demandant la définition plutôt que le libellé |
| Comportement d'ecCodes sur un paramètre inconnu | encoder un message GRIB2 avec un couple catégorie/numéro non attribué, puis relire ses clés |
| Recopie par cfgrib | lire `cfgrib/dataset.py`, autour de la liste des clés lues et de la fonction qui pose les attributs CF |
| Table de conversion de cfgrib | lire `cf2cdm/cfunits.py` |
| Absence de contrôle par xarray et netCDF4 | écrire un fichier portant une unité absurde, puis le relire |

Comparer les **définitions réduites** plutôt que les libellés est le point de
méthode : c'est ce qui permet d'affirmer qu'une réécriture conserve la
grandeur, au lieu de supposer qu'elle le fait.

---

## Références

| Ressource | Adresse |
|---|---|
| Conventions CF, § 3.1 « Units » | <https://cfconventions.org/cf-conventions/cf-conventions.html> |
| Tableau des noms standards CF | <https://cfconventions.org/Data/cf-standard-names/current/build/cf-standard-name-table.html> |
| UDUNITS-2, code source | <https://github.com/Unidata/UDUNITS-2> |
| UDUNITS-2, documentation | <https://docs.unidata.ucar.edu/udunits/current/> |
| ecCodes | <https://confluence.ecmwf.int/display/ECC> |
| Base de paramètres GRIB de l'ECMWF | <https://codes.ecmwf.int/grib/param-db/> |
| cfgrib, code source | <https://github.com/ecmwf/cfgrib> |
| cf-units, liaison Python vers UDUNITS-2 | <https://github.com/SciTools/cf-units> |
| cf-checker | <https://github.com/cedadev/cf-checker> |

Rien de ce qui précède n'aurait pu être vérifié si les mainteneurs
d'UDUNITS-2, d'ecCodes, de cfgrib et de cf-units ne publiaient pas leurs
sources sous licence libre. Qu'ils en soient ici remerciés.
