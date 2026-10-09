# Vocabulaire X10 — pierre de Rosette

Correspondance entre le vocabulaire de X10 et celui des référentiels du domaine.
Son objet est de rendre une traduction **mécanique** plutôt qu'interprétative, dans les deux sens.

Il joue pour X10 le rôle que [GeoDCAT-AP](https://semiceu.github.io/GeoDCAT-AP/) joue entre INSPIRE et DCAT : un pont documenté, pas un troisième vocabulaire.

**Vérifié le 02/10/2026** contre les sources liées. Les référentiels évoluent ; redater ce document à chaque reprise.

## Référentiels

| Sigle | Référentiel | Source |
|---|---|---|
| DCAT | W3C Data Catalog Vocabulary 3 | <https://www.w3.org/TR/vocab-dcat-3/> |
| PROV | W3C Provenance Ontology | <https://www.w3.org/TR/prov-o/> |
| INSPIRE | Directive européenne, métadonnées dérivées d'ISO 19115 | <https://inspire.ec.europa.eu/> |
| WCMP2 | WMO Core Metadata Profile 2, extension d'OGC API – Records. Appendice F du *Manual on the WMO Information System* (WMO-No. 1060), volume II | <https://github.com/wmo-im/wcmp2> |
| STAC | SpatioTemporal Asset Catalog | <https://github.com/radiantearth/stac-spec> |
| ECS | Elastic Common Schema, pour la journalisation | <https://www.elastic.co/guide/en/ecs/current/> |

## Classes

| X10 | DCAT | INSPIRE / ISO 19115 | WCMP2 | STAC | PROV |
|---|---|---|---|---|---|
| `Dataset` | `dcat:Dataset` | ressource de type *dataset* | `dataset` | `Collection` | `prov:Entity` |
| `granule` | `dcat:Distribution` d'un `dcat:Dataset` | *dataset* d'une *series* | *data granule*, relation `item` | `Item` | `prov:Entity` |
| `Distribution` | `dcat:Distribution` | *Resource locator* | entrée de `properties.links` | — | — |
| `Agent` | `dcterms:Agent` | `CI_ResponsibleParty` | entrée de `properties.contacts` | entrée de `providers` | `prov:Agent` |
| `Retrieval` | — (renvoie à PROV) | `LI_Lineage` | — | — | `prov:Activity` + `Entity` |
| `CatalogEntry` | `dcat:Catalog` partiel | — | enregistrement WCMP, partiel | — | — |

> Les rôles d'acteur ci-dessous **ne sont pas encore rapprochés de WCMP2**.
> Son `properties.contacts` porte bien des rôles, hérités d'OGC API – Records,
> mais les treize cellules demandent une vérification qui n'a pas été faite.
> Mieux vaut une colonne absente qu'une colonne devinée.

### Pourquoi « granule », et pas « paquet »

L'unité **téléchargeable** d'une collection n'avait pas de nom chez nous. Le
mot du producteur, « paquet », entre en collision deux fois : avec le paquet
**Python** — `CLAUDE.md` employait les deux sens à quelques lignes d'écart,
jusqu'à ce que ce relevé le mette au jour — et avec **GeoPackage**, norme OGC
et format `.gpkg` que X10 produira dès qu'il fera de la géographie.

**Le terme vient de l'OMM, pas d'un emprunt à la pratique satellitaire.**
WCMP2 l'emploie dans sa clause 7, qui est normative :

> *A **dataset** is the primary granularity of a WCMP record describing a
> collection of data granules.*

et sa table des relations de lien pose `item` pour « a link providing a single
data granule », `items` pour « numerous data granules » — soit exactement la
relation d'OGC API – Records, dont WCMP2 est une extension, et de STAC.

Trois sources sont à distinguer, ce que la rédaction initiale confondait :

| Source | Nature | Où `granule` y figure |
|---|---|---|
| **WCMP2 / WIS 2.0** | standard de l'OMM | clause **normative** |
| WIS2 Notification Message | standard de l'OMM | clause **informative** et exemples |
| NASA EOSDIS, CMR | pratique d'implémentation | usage répandu, sans portée normative |

Le mot n'a par ailleurs **aucun sens logiciel**, ce qui le met hors d'atteinte
des deux collisions, et il vaut pour le satellite comme pour l'océan et
l'atmosphère.

Il ne remplace pas `Distribution`, qui dit **où aller chercher** ; un granule
est ce qu'on rapporte. Et « paquet » reste employé pour désigner un produit
**nommé** du producteur — le paquet SP1, le paquet HP1 —, où le mot est le
sien et ne prête pas à confusion.

## Rôles d'acteur

Notre codelist réunit STAC et INSPIRE. Chaque terme garde l'orthographe de sa source — camelCase pour INSPIRE, dont la [codelist](https://inspire.ec.europa.eu/metadata-codelist/ResponsiblePartyRole) est gouvernée au niveau **« Legal (EU) »**, donc réglementaire.

| X10 | DCAT | INSPIRE | STAC | Sens |
|---|---|---|---|---|
| `producer` | `dcterms:creator` | `originator` | `producer` | a créé la ressource |
| `publisher` | `dcterms:publisher` | `publisher` | — | l'a publiée |
| `distributor` | `dcterms:publisher` (sens large) | `distributor` | `host` | la distribue, p. ex. un miroir |
| `resourceProvider` | — | `resourceProvider` | — | la fournit |
| `processor` | — | `processor` | `processor` | l'a transformée |
| `licensor` | `dcterms:rightsHolder` | *(aucun)* | `licensor` | la concède sous licence |
| `owner` | `dcterms:rightsHolder` | `owner` | — | la possède |
| `custodian` | — | `custodian` | — | en assume la redevabilité |
| `harvester` | — | *(aucun)* | — | l'a moissonnée et ré-exposée |
| `pointOfContact` | `dcat:contactPoint` | `pointOfContact` | — | contact pour la ressource |
| `author` | — | `author` | — | l'a rédigée |
| `user` | — | `user` | — | l'utilise |
| `principalInvestigator` | — | `principalInvestigator` | — | responsable de la collecte |

**`originator` n'est pas dans notre codelist**, délibérément. `producer` couvre le même concept et s'exporte vers `originator` ; deux termes pour une notion invitent l'incohérence. La correspondance étant bijective, l'aller-retour INSPIRE est sans perte.

**`licensor` et `harvester` n'ont aucun équivalent INSPIRE.** Le premier vient de STAC ; le second, parce qu'INSPIRE traite le moissonnage au niveau du service de découverte et non du rôle d'un acteur. Un export INSPIRE les rend par `owner` et `distributor`, avec perte de nuance — à documenter si l'export devient exigible.

## Droits et conditions

Trois notions, que notre premier modèle confondait en un champ.

| X10 | DCAT | INSPIRE |
|---|---|---|
| `Distribution.license` | `dcterms:license` | *Conditions applying to access and use* |
| `Distribution.access_rights` | `dcterms:accessRights` | [*Limitations on public access*](https://inspire.ec.europa.eu/metadata-codelist/LimitationsOnPublicAccess) |
| rôle `licensor` / `owner` | `dcterms:rightsHolder` | `owner` |

`access_rights` reprend **verbatim** la codelist INSPIRE : `noLimitations`, puis les huit alinéas de l'article 13 de la directive. Ce sont des motifs juridiques de restriction, non des licences — la confusion est fréquente et produit des métadonnées fausses.

## Lignage

| X10 `Retrieval` | PROV | INSPIRE |
|---|---|---|
| `artefacts` | `prov:Entity` | — |
| `retrieved_at` | `prov:Activity` + `endedAtTime` | *Date* de la lignée |
| `origin` | `prov:used` | — |
| `agent` | `prov:wasAssociatedWith` | — |
| `selection` | paramètres de l'`Activity` | — |

**Nous sommes plus structurés qu'INSPIRE sur ce point.** GeoDCAT-AP ramène `LI_Lineage` à `dct:provenance`, c'est-à-dire un **énoncé en texte libre**. Produire cet énoncé depuis notre structure est trivial ; l'inverse serait impossible.

## Extensions X10, sans équivalent

| Champ | Pourquoi |
|---|---|
| `Distribution.provider` | DCAT ne porte aucun agent sur une distribution — `dcterms:publisher` appartient à la ressource. Or une distribution par origine n'a de sens que si l'on sait qui la sert. Les rôles de l'agent portent la précision. |
| `Distribution.priority` | La politique de résolution entre origines redondantes. Aucun référentiel ne modélise une préférence entre miroirs. |
| `Distribution.origin` | Identifiant court de l'origine, transmis au connecteur. Commodité, pas une notion. |

## Pourquoi STAC n'est pas la cible du catalogue

STAC reste pertinent pour le catalogage d'imagerie et pour consommer les sources qui en exposent. Il **ne convient pas à la redondance** : sa spécification pose qu'il ne doit y avoir *qu'un seul* `host`, désignant un hébergeur faisant autorité. C'est précisément le cas que `Distribution` doit modéliser.

## Conformité — où nous en sommes

**Compatible, non conforme.** X10 n'émet pas de métadonnées INSPIRE et ne prétend à aucune conformité. L'alignement du vocabulaire rend cette production mécanique le jour où elle serait exigée, par exemple si X10 alimentait une infrastructure de données géographiques publique.

Trois écarts subsisteraient à combler ce jour-là : les éléments de métadonnée obligatoires du profil INSPIRE que nous ne portons pas — identifiant de ressource, emprise géographique, référentiel de coordonnées, contact de la métadonnée ; la sérialisation, INSPIRE attendant du XML ISO 19139 ; et l'énoncé de lignée en texte libre, à dériver de `Retrieval`.
