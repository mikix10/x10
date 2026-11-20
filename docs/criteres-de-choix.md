# Les critères de choix, et leur ordre

Onze critères gouvernent les décisions du dépôt. Ils n'ont pas été posés
d'avance : ils ont été **dégagés des décisions déjà prises**, puis vérifiés
contre elles. C'est pourquoi chacun porte ici les cas qui l'ont produit —
un critère sans cas est une intention.

Le guide [AGENTS.md](../AGENTS.md) en donne la liste et l'ordre. Cette note
donne ce qui ne tient pas dans un guide : les exemples, les tensions entre
critères, et la règle qui dit quand arrêter d'instruire.

## L'ordre de préséance, et il est unique

> **L'ordre est celui du coût d'ignorer.** Une valeur fausse qui ne se
> signale pas passe avant un refus de servir, qui passe avant une imprécision
> de prose.

Ce n'est pas un ordre inventé pour l'occasion : c'est **C1 rendu transitif**,
et il a ordonné des chantiers réels avant d'être écrit.

## C1 — Entre deux défauts, le plus cher est celui qui ne se voit pas

Un échec bruyant se corrige ; une sortie fausse se propage. **C1 arbitre les
dix autres**, et huit décisions l'appliquent sans qu'il ait été nommé :

- `standard_name = "unknown"` retiré, « valeur **pire qu'une absence** » ;
- un nom CF inventé, qualifié en propres termes de « défaut le plus coûteux
  de notre correspondance » — il produit un fichier qui se dit conforme, ne
  casse rien, et ne se voit pas ;
- `errors='warn'` passé à `'raise'` : l'appelant recevait un tuple amputé et
  le compte rendu disait `success` ;
- l'écriture atomique : un fichier partiel que **rien ne distingue d'un
  fichier entier** ;
- le lexique public, les signatures de commits, les deux disjonctions
  manquantes, le marqueur de couverture.

## C2 — Mesurer plutôt qu'affirmer, et une inexistence se mesure comme le reste

**La précision est opérante** : la moitié des corrections datées du dépôt
portent sur un énoncé **négatif ou exclusif** — « aucun », « le seul »,
« jamais ».

> *Test : la phrase dit-elle qu'une chose n'existe pas ? Alors elle se
> mesure.*

Exemples : « les données ouvertes de l'ECMWF n'exposent aucune direction »
était faux, `mwd` figure à l'index des vagues. « Aucun mécanisme de
dépréciation » était vrai d'une sous-table et faux de la table : 60 entrées
`Deprecated` sur 1 387.

> **Réserve de rigueur.** C2 est une **méthode d'établissement** plus qu'un
> critère de choix : elle dit comment on obtient une prémisse, pas comment on
> tranche entre deux prémisses établies. Elle figure parmi les critères parce
> qu'elle gouverne l'entrée de toutes les autres.

## C3 — Ne pas deviner à la place du producteur

`netcdf_cf.grid_mapping` rend **`None`** quand le producteur ne déclare rien ;
`(0, 3, 6)` a été **retiré** de la table plutôt que renommé, parce que
« remplacer une supposition par une autre ne vaut rien » ; un `typeOfLevel`
inconnu n'est pas traduit.

## C4 — Fermer la classe, pas le cas

Deux noms CF écrits en dur ont été trouvés dans deux fonctions. Ils sont
passés en table, **et une analyse du code interdit désormais qu'un nom CF
réapparaisse en littéral**. Même forme pour les empreintes de tables : un
test exige que toute exemption nomme une constante existante, et il a
effectivement attrapé une exemption devenue orpheline le 19/11/2026.

## C5 — Rendre l'écart lisible dans un `git diff` plutôt que le trancher

Cinq références sont **engendrées** et commitées : vocabulaire public,
inventaire des tests, dérogations de typage, registre des écarts, contrat de
sortie. Chaque ajout produit **une ligne qu'un relecteur lit**.

> C'est le piège qui a tué les tentatives recensées ailleurs : *une colonne
> qu'un humain doit penser à mettre à jour ne l'est jamais.*

## C6 — Le paquet fournit le mécanisme, l'application fournit les valeurs

`SecretRedactor` filtre des valeurs que l'application lui donne ; les sondes
vivent dans `probes/` et leur mécanisme dans `x10_client` ; la journalisation
n'installe aucun handler. Le corollaire est la règle des secrets : **le
client résout, le connecteur reçoit**.

## C7 — Deux notions voisines, deux noms, et on écrit ce que produirait la confusion

C'est le critère le plus productif du dépôt. Licence / droits d'accès /
authentification sont **trois** notions, pas une. Capacité et disponibilité
sont deux questions. `Retrieval` décrit l'acquisition d'un artefact,
`Provenance` l'attribution d'une valeur. `source` et `history` ne disent pas
la même chose en CF.

**La seconde moitié du critère compte autant que la première** : on écrit ce
que la confusion produirait. « Les confondre produit des métadonnées
fausses » est ce qui rend la distinction tenable par un relecteur qui ne la
connaît pas.

## C8 — Pas de mécanique générale sous trois cas

« Concevoir une mécanique générale sur un échantillon de un produit une
mécanique fausse. » Le seuil est écrit quatre fois dans le dépôt, et il a
retenu : le catalogue ne construit aucune requête de producteur, parce qu'il
n'y a que deux sources ; `x10-storage` n'est pas généralisé sur un seul
appelant.

Et le critère **se lève quand l'échantillon arrive** : la chaîne a traversé
un troisième producteur le 22/10/2026 sans rien perdre, ce qui a cessé de
rendre la clause applicable à la correspondance GRIB → CF.

## C9 — Un contrôle qui s'exécute vaut mieux qu'une consigne qui se lit

Deux garanties que la documentation déclarait acquises **n'étaient pas
outillées**, et il a fallu un audit pour s'en apercevoir. Depuis : la surface
réseau est épinglée par un test, l'absence de lecture d'environnement dans
les paquets aussi, et chaque dérogation de typage figure dans une référence
engendrée.

## C10 — Une autorité se vérifie avant d'être reprise

Les libellés d'ecCodes sont **d'ecCodes**, pas de la norme : il nomme
l'entrée 5 « Orography » là où l'OMM écrit « Geopotential height ». Un SHA-1
publié par un producteur **ne correspond pas aux octets servis**. Un en-tête
`Last-Modified` décrit l'objet de stockage, pas la publication.

> Corollaire : **remonter à la source primaire n'est pas une politesse
> bibliographique**, c'est ce qui sépare un fait daté d'un fait redaté.

## C11 — Une révision reste écrite à côté de l'énoncé qu'elle corrige

Le dépôt s'est contredit une quinzaine de fois par la mesure, et l'a écrit à
chaque fois : « `**` est valide en UDUNITS — j'avais soutenu le contraire » ;
« poser `tablesVersion` ne commute pas la résolution » ; « le gabarit si »
était trop fort. Une correction qui efface l'énoncé qu'elle corrige fait
perdre **pourquoi** on y avait cru.

## Trois tensions réelles, et leur résolution

Elles ne sont pas des cas de conscience : chacune a été tranchée par un cas.

**Ne pas deviner contre exposer.** Elles ne s'opposent jamais, parce que
**ce qui cède est l'affirmation, jamais le champ**. `(0, 3, 6)` est retiré de
la table, le champ reste ; `grid_mapping` rend `None`, le fichier est écrit ;
l'unité est omise, la variable sort. *Ne pas deviner* l'emporte sur
**nommer** ; *exposer* l'emporte sur **refuser**.

**Lever contre signaler.** Ce n'est pas une tension mais un discriminant
mesuré : **on signale quand l'écart peut être porté par la sortie elle-même,
on lève quand il ne le peut pas.** Une métadonnée dégradée se signale ; un
champ qui disparaît est **de la donnée en moins**, et il lève.

**Fidélité à la source contre exploitabilité.** L'exploitabilité l'emporte
**à condition que la forme d'origine reste lisible à côté** : `GRIB_units`
conserve `m s**-1`. Quand la condition ne peut pas être tenue, l'affirmation
est **abandonnée, pas traduite**.

## Quand arrêter d'instruire

Le dépôt sait compter ce qu'une question coûte **aux autres** — à un
producteur, à une équipe tierce. Il ne comptait pas ce qu'elle lui coûte à
lui.

> **Une question paie quand elle change une table, un contrôle, un refus, ou
> une affirmation fausse. Elle coûte pour rien quand elle ne change qu'une
> formulation déjà exacte.**

Nuance imposée par C1 : corriger une justification **fausse** paie ; polir
une justification déjà juste, non.

Trois déclencheurs observables, et leur coût d'outillage est **nul**,
délibérément — un hook qui prétendrait mesurer l'effort d'une question serait
un faux positif permanent :

- **Entrée** — nommer le fichier que la réponse changera, et l'énoncé qui
  serait faux si la réponse était l'autre. Si ni l'un ni l'autre ne vient,
  c'est une question de forme : on tranche en une passe et on consigne en une
  ligne l'option retenue et celle écartée.
- **Arrêt** — deux tours d'argument **sans mesure nouvelle** closent la
  question.
- **Déséquilibre** — une demi-journée sans mesure, sans contrôle et sans
  correction d'un énoncé faux est une demi-journée dépensée.

## Une règle de rédaction, pour que les critères se transposent

**Tout critère porte au moins un exemple hors du domaine qui l'a produit, ou
dit explicitement pourquoi il n'en a pas.**

La quasi-totalité des exemples du dépôt sont météorologiques — un `stepType`,
une unité `J m**-2`, un cumul AROME. Un principe dont tous les exemples
viennent d'un seul domaine finit par être lu comme une règle de ce domaine,
et le lecteur suivant ne le transpose pas.

C10 en donne l'illustration : côté météo, un SHA-1 publié qui ne vérifie
rien ; côté géographie, **le même contenu à l'octet servi sous deux dates
séparées de 45 heures**. Les deux pièges sont **symétriques et non
identiques** — l'un est un faux négatif, l'autre un faux positif de masse —
et les parades sont opposées. C'est la paire qui dit la règle, pas l'une des
deux.
