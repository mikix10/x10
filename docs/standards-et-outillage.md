# Standards et outillage : ce que la chaîne de normalisation tient, et sur quoi

**Note technique à l'usage de qui normalise des données météorologiques d'un
format de diffusion vers un format de conservation.**

> **État constaté le 19 octobre 2026**, avec ecCodes 2.49.0, cfgrib 0.9.15.1,
> xarray 2026.9.0, netCDF4 1.7.4, cf-units 3.3.1, CF-1.7 déclaré en sortie et
> le tableau des noms standards CF en version 95. Les registres cités
> évoluent, et plusieurs des artefacts décrits ici ont cessé d'être maintenus
> entre 2019 et 2024. **Rien ne garantit la pérennité de ces constats** ; la
> méthode pour les rejouer est en fin de note.

## Objet

Convertir du GRIB2 en NetCDF-CF suppose de traduire un vocabulaire dans un
autre. Cette note établit **qui fait autorité sur quoi** dans cette chaîne,
et constate que la réponse est : presque personne, sur presque rien.

Elle décrit ensuite le modèle que nous en tirons — `standards-et-outillage.yaml`,
dans ce même dossier — et explique pourquoi chacune de ses entités emprunte à
un vocabulaire existant plutôt que d'en inventer un.

Elle ne propose aucune correspondance nouvelle. Celles que nous posons vivent
dans `packages/x10-connectors/`, avec leur justification et leur date.

---

## 1. Quatre couches, et ce que chacune ne peut pas dire

| Couche | Ce qu'elle gouverne | Ce qu'elle ne peut pas dire | Qui en répond |
|---|---|---|---|
| **Standard** | le vocabulaire et ses règles | si un outil l'applique | une autorité, quand il y en a une |
| **Artefact** | une forme concrète du standard | si elle est à jour vis-à-vis de la forme normative | le diffuseur |
| **Outillage** | ce qu'une bibliothèque rend réellement | ce que le standard voulait | l'éditeur de la bibliothèque |
| **Correspondance** | ce que nous affirmons entre deux vocabulaires | rien d'autre que notre propre mesure | nous |

La distinction entre les deux premières lignes n'est pas théorique : **deux
artefacts d'un même standard divergent** dans cette chaîne, et le plus
officiel des deux est le plus périmé (§2.2).

---

## 2. Aucun standard de la chaîne n'est formalisé en exigences testables

### 2.1 Le relevé

| Standard | Langage d'exigence | Profil de conformité | Validateur |
|---|---|---|---|
| *Manual on Codes* WMO-No. 306 vol. I.2 | `shall` / `may` en minuscules, sans terminologie déclarée | aucun | aucun |
| Conventions CF | aucun, à aucune version depuis 2003 | **oui**, document distinct versionné en parallèle | tiers, non rattachés |
| UDUNITS-2 | aucun texte normatif distinct | aucun | aucun |
| netCDF | spécification de format réelle | une classe de conformité OGC | aucun |
| HDF5 | spécification de format détaillée | — | `h5check`, indépendant, site archivé |
| **Tableau des noms standards CF** | — | **XSD publié**, versionnement entier, archives v1 → v95 | validation XML |

Le dernier maillon est le seul vraiment solide, et c'est heureux : c'est
celui sur lequel nous nous appuyons le plus.

**Le document de conformité de CF mérite une mention, et une réserve.** Il
existe, il accompagne chaque édition, et il énonce : *« If there are any
discrepencies between the two, the conventions document is the ultimate
authority. »* Mais ses exigences sont des **puces non numérotées**, groupées
par section du texte principal. Il n'existe donc **aucun identifiant stable
pour une exigence CF** : on ne peut pas écrire « CF-R-2.1-001 », seulement
citer un libellé sous un numéro de section. C'est la raison pour laquelle
l'entité `Clause` du modèle exige le **texte cité** et non une référence.

**UDUNITS-2 est le cas limite** : il n'a pas de spécification distincte de
son implémentation. La grammaire est documentée dans la documentation d'API
de la bibliothèque. Valider une unité, c'est donc interroger le programme —
ce que fait notre suite de tests, en soumettant chaque unité émise à UDUNITS
et en comparant la définition réduite de part et d'autre de la conversion.

### 2.2 Deux artefacts de l'OMM, désynchronisés — le piège le plus coûteux

| Artefact | Statut apparent | Version | Entrées en table 4.2 |
|---|---|---|---|
| `codes.wmo.int` | point d'entrée *linked data* officiel, « stable » | `owl:versionInfo 6`, modifié **2014-09-03** | **590**, disciplines 4 et 20 **absentes** |
| `wmo-im/GRIB2` | « working documents », licence MIT | **v37, 2026-06-08** | **1 582** |

**Onze versions de table d'écart.** Le premier sert pourtant du SKOS par
terme, avec des URI déréférençables — ce qui en fait le choix naturel pour
qui veut des identifiants, et le mauvais choix pour qui veut les tables. Son
RDF porte d'ailleurs encore une colonne pointant vers un projet de
correspondance hors service depuis 2019.

La clause de préséance — *« If there are inconsistencies between the entries
available below and the Manual on Codes […] the Manual prevails »* — ne
figure sur **aucun des deux artefacts**, mais sur une page web intermédiaire.

### 2.3 Le contraste est interne à l'OMM

L'OMM **sait** produire du normatif testable, et le fait sur la même période,
dans la même organisation :

- langage d'exigence déclaré, suivant la *OGC Policy Directive 49* et les
  directives ISO/IEC — *« "SHALL" (not "must") is the verb form used to
  indicate a requirement to be strictly followed »* ;
- **quatorze exigences numérotées** pour son profil de métadonnées ;
- une **suite de tests abstraits normative**, en correspondance une pour une
  avec les exigences ;
- une **suite exécutable** déployée en service, qui refuse la publication
  d'une fiche non conforme.

La capacité existe. Elle n'a pas été appliquée au format de données.

**Et c'est l'ordre de grandeur qu'il faut retenir : quatorze exigences.** Une
formalisation qui aboutit dans ce domaine se compte en dizaines, pas en
centaines.

---

## 3. La correspondance GRIB vers CF n'a jamais été livrée

C'est le constat qui décide de notre posture, et il est mesuré.

### 3.1 CF l'a portée, puis retirée

Le tableau des noms standards a longtemps porté un élément `grib` par entrée.
Mesure directe sur les versions archivées :

| Version | Date | Entrées | Avec `grib` |
|---|---|---|---|
| v10 | 2008-10-21 | 1 103 | **116** |
| v30 | 2015-12-03 | 2 674 | 116 |
| v50 | 2018-03-14 | 4 039 | 115 |
| v70 | 2019-12-10 | 4 380 | 115 |
| v86 | 2024-09-05 | 4 872 | 113 |
| **v87** | **2024-11-12** | 4 891 | **0** |
| v95 | 2026-09-16 | 5 097 | 0 |

Le tableau a quadruplé en seize ans ; la colonne n'a pas bougé d'une entrée,
puis elle a disparu. Le motif du retrait est écrit dans la discussion qui l'a
précédé : l'information avait été mise là très tôt comme *« a kind of
advertisement for the possible use of standard names »*, et *« no one has
volunteered to keep them up-to-date »*.

**Ces 113 codes étaient tous de l'édition 1 du format** — des entiers
simples, parfois préfixés pour désigner une table locale. Le champ était
mono-entier, donc structurellement incapable de porter un triplet.
**Il n'a jamais existé de correspondance GRIB2 vers CF portée par CF.**

### 3.2 Les autres tentatives

| Tentative | Volume | Sort |
|---|---|---|
| Registre de correspondances désigné par une feuille de route institutionnelle de 2014 | 2 057 correspondances RDF | **hors service** ; le dépôt n'a pas bougé depuis 2019 |
| Correspondance d'une bibliothèque de lecture GRIB | 83 entrées GRIB2 | **instantané figé** du registre ci-dessus, au 12 février 2016. L'en-tête « AUTO-GENERATED » a depuis été retiré, faute de source à régénérer |
| Correspondance dans un serveur de vocabulaires océanographique | **14 paires** | gelée au 14 novembre 2012, et exprimée par un prédicat d'identité stricte qui ne convient pas |
| Une table d'une dizaine de lignes, même clé que la nôtre, publiée par un service météorologique national | 11 lignes | publiée et abandonnée **le même jour** |

Et le diagnostic est partagé, daté, stable :

| Date | Constat |
|---|---|
| 2012 | *« there are no canonical machine-readable GRIB parameter tables »*, avec un appel à un effort communautaire de correspondance vers CF |
| 2014 | *« endless amount of work to clarify semantics — but probably can get 80/20 »* ; *« Creating parameter mappings is a non-trivial task! »* |
| 2024 | *« ongoing problem »* ; et, au même atelier CF, les mêmes termes qu'en 2014 |

Du côté de CF, un aveu structurel plus ancien encore, de 2008 : *« I hope
that there are not any `exactMatch` mappings, that would be a bad sign »*, et
*« there is probably not a one-to-one correspondence »*.

### 3.3 Pourquoi la couverture des outils est si faible

La correspondance livrée par la bibliothèque de référence est **générée**.
Son en-tête l'annonce, et le script générateur joint sur un identifiant
**local au centre européen**, hérité de l'édition 1 du format.

Conséquence mécanique : **un nom CF n'existe que pour un paramètre qui
possède cet identifiant historique**. Un modèle dont les paramètres n'y
figurent pas ressort sans nom standard, quelle que soit la banalité du champ.
Les ratios que nous observions — neuf codes sur cinquante et un pour un
modèle, neuf sur soixante-quatre pour un autre — ne sont donc **ni un oubli
ni un accident** : c'est le comportement nominal.

### 3.4 La raison de fond

Toutes les sources convergent : **un triplet ne détermine pas un nom CF**. Il
faut aussi le type de surface, le traitement statistique, la convention de
signe des flux, et l'unité. C'est ce que nous avons mesuré de notre côté sur
deux cas, et c'est ce qui fait qu'une table à clé simple est soit fausse,
soit incomplète.

> **Conclusion qui engage ce dépôt.** Il n'existe pas d'autorité pour une
> correspondance de GRIB vers CF, et il ne peut pas en exister tant qu'aucune
> des deux communautés n'en assume la charge. La réponse n'est pas de chercher
> la bonne référence : c'est d'**assumer la nôtre et de la rendre
> défendable** — datée, justifiée, confrontée au fichier réel, et confrontable
> à celles des autres.

---

## 4. Le modèle, et d'où vient chaque terme

Le schéma est dans `standards-et-outillage.yaml`. Il est écrit en **LinkML**,
pour trois raisons : il se relit ligne à ligne dans un `git diff`, chaque
entité y **déclare le terme normalisé** auquel elle correspond, et il
**engendre** le code plutôt que de le dupliquer — vérifié le 19/10/2026, la
génération produit douze classes Pydantic importables et validantes.

| Entité | Terme normalisé | Pourquoi celui-là |
|---|---|---|
| `Scheme` | `skos:ConceptScheme` + `adms:Asset` | un vocabulaire de termes est un *concept scheme* ; ADMS est le profil DCAT fait pour décrire les référentiels sémantiques |
| `Artefact` | `dcat:Distribution`, normativité par `prov:hadPrimarySource` | la normativité est une **relation** entre deux artefacts, pas une propriété de l'un d'eux |
| `Term` | `skos:Concept`, **référencé, jamais frappé** | voir la règle ci-dessous |
| `FieldIdentity` | **aucun** | ISO 25964-2 nomme la *relation* d'équivalence composée, pas l'objet composé |
| `Mapping` | une ligne **SSSOM** | seul format qui sache dire qu'une correspondance a été **examinée et refusée** |
| `Rule` | **aucun** | la cible n'est pas un concept mais une expression — une unité canonique, une méthode de cellule |
| `Clause` | `dcterms:conformsTo` | avec le texte cité, faute d'identifiant d'exigence (§2.1) |
| `Dependency` | `prov:SoftwareAgent` | un outil est un agent ; son inventaire reste dans le fichier de verrouillage |
| `Observation` | `prov:Activity` + `prov:wasRevisionOf` | une mesure est une activité datée, et elle peut en corriger une autre |
| `Divergence` | spécialise `Observation` | un écart outil/standard est une observation particulière |
| `Invariant` / `Verdict` | `earl:TestCriterion` / `earl:Assertion` | EARL admet le résultat `untested`, ce qui rend visible un contrôle absent |

**Une règle gouverne l'ensemble** : *nous n'énonçons jamais **dans** un
schéma que nous ne gouvernons pas ; nous énonçons **à propos** de lui.* Nos
tables ne sont pas des concepts, ce sont des **assertions tierces sur les
concepts d'autrui**.

### 4.1 Pourquoi SKOS ne suffit pas pour la couche correspondance

SKOS était le candidat évident, et il a été écarté pour deux raisons
indépendantes.

**La distinction `exactMatch` / `closeMatch` ne mécanise aucun arbitrage.**
SKOS définit `closeMatch` comme *« sufficiently similar that they can be used
interchangeably in **some** information retrieval applications »* — sans dire
lesquelles. Classer une correspondance en `closeMatch` plutôt qu'en
`exactMatch` est exactement le même jugement, rangé dans un casier.

**Et ce casier est piégé en sortie.** Notre sortie est l'attribut CF
`standard_name` : une chaîne unique, sans qualificatif de degré. Un
`closeMatch` y est donc **inémettable** — au mieux il finirait en commentaire.
L'introduire créerait une catégorie que le format cible ne sait pas porter, et
la tentation permanente de l'aplatir à l'écriture. Déclarer la correspondance
refusée, et laisser l'absence visible, est plus juste.

SKOS garde néanmoins une place, et une seule : **un outil qui publie un
vocabulaire est un schéma de concepts non normatif**. C'est le cas de la
bibliothèque de lecture GRIB, qui nomme une entrée « Orography » là où le
standard écrit « Geopotential height », et qui tranche une ambiguïté que le
standard laisse ouverte. Le modèle distingue donc l'outil-agent de
l'outil-vocabulaire.

### 4.2 Ce que SSSOM apporte, et ce qu'il ne couvre pas

Il porte `predicate_modifier`, dont la valeur `Not` signifie « correspondance
examinée et refusée ». C'est la seule place normalisée pour nos tables
d'exception — et la différence entre « nous avons regardé et il n'y a rien »
et « personne n'a regardé » est précisément ce qu'un registre doit conserver.

Il porte aussi `subject_source_version` et `object_source_version` : la
version de chaque schéma au moment de l'assertion. C'est ce qui rend une
correspondance relisible dans l'état où elle a été posée.

Ce qu'il ne couvre pas, et que le modèle ajoute en extension : **le motif**
d'une non-correspondance. Les trois que nous rencontrons ne se corrigent pas
de la même façon — cible absente du vocabulaire visé, sujet sous-déterminé
par le code du producteur, ou cible existante mais exigeant une précision que
le producteur ne déclare pas. Seul le premier se corrige en proposant un nom.

> **Réserve sur les identifiants.** Les termes du vocabulaire SSSOM ne
> déréférencent pas — vérifié le 19/10/2026. Ce sont des identifiants valides,
> pas des adresses consultables.

---

## 5. La maintenabilité est la variable qui discrimine

**Aucune des tentatives du §3.2 n'est morte d'avoir eu tort. Toutes sont
mortes de ne pas avoir été tenues.**

C'est le fait le plus utile de l'enquête, et il change ce qu'il faut
construire : pas un instantané, un **processus**. Trois aptitudes en
découlent, et elles sont réalisables — vérifié :

| Aptitude | Ce qui la porte | Faisable ? |
|---|---|---|
| **Tracer un ajout** — qui, quand, sur quelle mesure | `Mapping` et `Observation` | oui, le format le prévoit |
| **Relire une table dans sa version X** | `Artefact` et les champs de version de SSSOM | **oui** : CF archive v1 à v95 ; les tables GRIB2 lisibles par machine sont publiées en versions successives ; et les définitions de la bibliothèque de lecture étant **compilées dans sa roue**, la version du paquet *est* la version des tables. Seule exception, le registre *linked data* officiel, qui ne versionne pas ses entrées |
| **Comparer n-1 et n** | `prov:wasRevisionOf` | oui — et c'est nécessaire : ce dépôt a déjà **trois énoncés retournés**, dont aucun n'est tracé comme révision |

---

## 6. Les dépendances ont leur cycle de vie

Nous bénéficions d'outils que nous ne gouvernons pas. Le dépôt a déjà le bon
réflexe — écrire les options plutôt que d'hériter de leurs défauts, au motif
que « s'en remettre à eux revient à laisser une version mineure de la
bibliothèque changer nos sorties sans que rien ne le signale ». Ce réflexe
n'était ni généralisé ni vérifié.

**Mesure du 19/10/2026 :**

| | |
|---|---|
| Options exposées par le backend de lecture GRIB | **20** |
| Options que nous fixons | **8** |
| **Héritées sans être recensées** | **12** |

Et la docstring annonçait **dix-huit** paramètres là où il y en a vingt, sur
la **même version de la bibliothèque** qu'au relevé du 8 octobre. Ce n'est
donc pas une dérive de la dépendance : c'est un comptage inexact de notre
part, qu'aucune relecture n'a attrapé. La docstring est corrigée, et les
douze options héritées y sont désormais nommées.

> **C'est l'argument le plus direct en faveur d'un contrôle plutôt que d'une
> vigilance.** La règle était juste, l'intention était bonne, et le chiffre
> sur lequel elle reposait était faux. Un contrôle par introspection de
> signature l'aurait signalé le jour même — et signalerait de même un
> paramètre apparu dans une version future.

D'où, dans le modèle, le lien `Observation → prov:used → Dependency` : une
montée de version **désigne mécaniquement** les mesures à rejouer. C'est le
seul bénéfice du modèle qui soit à la fois chiffrable et récurrent.

---

## 7. Les invariants, et ceux qui manquent

La « cohérence d'ensemble » n'est pas une qualité diffuse : c'est un
ensemble énumérable de propriétés, chacune vérifiée ou non.

Un invariant est une **entité**, pas une propriété d'un test. Sans cela,
celui qu'aucun test ne porte n'aurait nulle part où exister — et c'est
exactement le cas qu'il faut rendre visible.

| Invariant | Mode |
|---|---|
| Tout nom CF émis existe au tableau officiel et n'est pas devenu un alias | automatique, test réseau |
| Toute unité émise est acceptée par UDUNITS, et la conversion préserve la définition réduite | automatique |
| Les ensembles d'exception sont deux à deux disjoints | automatique, **sur une paire des trois** |
| La version de tables déclarée par un producteur reste inférieure à celle que notre outillage résout | automatique, test réseau |
| Les noms de la table de références verticales existent au tableau CF | **non outillé** |
| Aucun défaut de dépendance n'est hérité sans être recensé | **non outillé** |
| Les tables d'exception sont confrontées à une table tierce de clé compatible | **non outillé** |
| Aucune assertion n'est tracée comme révision d'une précédente | **non outillé** |

Les quatre derniers sont des `untested` assumés. Les écrire est l'objet du
modèle ; les outiller est un travail distinct.

---

## 8. Ce que le formalisme ne sait pas porter

Le schéma dit la structure. Il ne dit pas **pourquoi** une correspondance a
été refusée, pourquoi un registre officiel donne des identifiants sans donner
d'autorité, ni ce qu'une mesure a coûté à établir. Cette matière-là est dans
les tableaux de cette note et dans les docstrings du code — et c'est là
qu'est l'essentiel du travail.

C'est aussi la raison pour laquelle cette note **ne contient aucun
diagramme**. Un diagramme de classes montre des cardinalités ; il ne porte
pas la colonne qui fait la valeur de nos tables. Et un bloc de diagramme se
relit mal dans un `git diff`, ce que le dépôt exige de toutes ses références.
Qui veut une vue graphique l'engendre depuis le schéma.

---

## Rejouer ces vérifications

**Les éléments de correspondance retirés du tableau CF.** Télécharger deux
versions encadrant le retrait et compter :

```bash
for v in 86 87; do
  curl -sS -o "t$v.xml" \
    "https://cfconventions.org/Data/cf-standard-names/$v/src/cf-standard-name-table.xml"
done
python - <<'EOF'
from xml.etree import ElementTree as ET
for v in (86, 87):
    r = ET.parse(f"t{v}.xml").getroot()
    e = list(r.iter("entry"))
    g = sum(1 for x in e if (x.findtext("grib") or "").strip())
    print(v, r.findtext("last_modified")[:10], len(e), "entrees, grib =", g)
EOF
```

**Les deux artefacts de l'OMM.** Comparer la date du registre *linked data*
et la dernière version publiée des tables lisibles par machine ; compter les
lignes de paramètres des fichiers séparés par discipline et catégorie.

**Les options héritées de la bibliothèque de lecture.** Introspection de la
signature du backend, confrontée à ce que le code fixe :

```bash
uv run python -c "
import inspect
from cfgrib.xarray_plugin import CfGribBackend
from x10_connectors.grib2 import OPTIONS_CFGRIB
noms = set(inspect.signature(CfGribBackend.open_dataset).parameters) - {'self', 'filename_or_obj'}
fixes = set(OPTIONS_CFGRIB) | {'read_keys', 'errors', 'values_dtype'}
print(len(noms), 'exposees,', len(fixes), 'fixees,', len(noms - fixes), 'heritees')
print(sorted(noms - fixes))
"
```

**Le schéma lui-même.** Il est validé par LinkML, et sa génération est
vérifiable, sans l'ajouter aux dépendances :

```bash
uvx --from linkml linkml lint docs/standards-et-outillage.yaml
PYTHONUTF8=1 uvx --from linkml gen-pydantic docs/standards-et-outillage.yaml
```

Les trois avertissements de casse de préfixe sont délibérés : ce sont les
formes que les schémas sources déclarent eux-mêmes.

---

## Références

- Conventions CF, texte et document de conformité —
  <https://cfconventions.org/conventions.html>
- Tableau des noms standards CF, et son schéma —
  <https://cfconventions.org/Data/cf-standard-names/current/src/cf-standard-name-table.xml>,
  <https://cfconventions.org/Data/schema-files/cf-standard-name-table-2.0.xsd>
- Retrait des éléments de correspondance — <https://github.com/cf-convention/cf-conventions/pull/552>
  et la discussion <https://github.com/cf-convention/cf-conventions/issues/367>
- Registre des codes de l'OMM — <https://codes.wmo.int/grib2>
- Tables GRIB2 lisibles par machine — <https://github.com/wmo-im/GRIB2>
- Clause de préséance du *Manual on Codes* — <https://community.wmo.int/node/37787>
- Profil de métadonnées de l'OMM, exigences et suite de tests abstraits —
  <https://wmo-im.github.io/wcmp2/standard/wcmp2-STABLE.html>
- Atelier « Closing the GRIB/NetCDF gap », actes —
  <https://www.ecmwf.int/node/20960>
- SKOS — <https://www.w3.org/TR/skos-reference/>
- SSSOM, spécification et schéma — <https://mapping-commons.github.io/sssom/>,
  <https://github.com/mapping-commons/sssom>
- EARL — <https://www.w3.org/TR/EARL10-Schema/>
- ADMS — <https://www.w3.org/TR/vocab-adms/>
- PROV-O — <https://www.w3.org/TR/prov-o/>
- LinkML — <https://linkml.io/linkml/>

Notes connexes de ce dépôt : [vocabulaire.md](vocabulaire.md) pour la
correspondance de notre vocabulaire de catalogue vers DCAT, PROV-O et
INSPIRE ; [triplet-et-tables-grib.md](triplet-et-tables-grib.md) pour
l'enquête sur l'ambiguïté des codes ;
[unites-et-interoperabilite.md](unites-et-interoperabilite.md) pour la
validation des unités.
