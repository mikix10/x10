# x10-catalog

Le registre des sources, et la politique de résolution d'origine.

Le vocabulaire — `Dataset`, `Distribution`, `Agent`, `Variable` — vit dans
`x10-models` : ce sont des modèles de domaine. Ce paquet porte le
**comportement** : enregistrer, chercher, résoudre. Un `Registry` est un
`dcat:Catalog`, une `CatalogEntry` en décrit une ressource.

## Interroger, par raffinement

L'interrogation n'est pas une recherche qui rend une liste : c'est un
dialogue où l'on resserre, et où le catalogue dit ce qui reste ouvert sur
l'axe suivant.

```python
from x10_catalog import Query, Registry

registre = Registry.from_file(chemin)

q = Query(standard_name="air_temperature")
registre.matches(q)  # qui sert cette grandeur
registre.facets(q, "level")  # à quels niveaux, vu ce qui est déjà posé
registre.origins("un-jeu")  # les origines à tenter, dans l'ordre
```

`facets()` exclut l'axe demandé de sa propre contrainte : demander les
niveaux alors qu'on en a fixé un rendrait une liste d'un élément, ce qui
n'aide personne à choisir.

**Le registre ne construit aucune requête de producteur.** C'est l'appelant
qui résout une entrée et transmet l'ordre des origines au connecteur — un
connecteur ignore l'existence d'un catalogue, et ce paquet n'importe jamais
`x10-connectors`.

## Deux vues, et elles ne promettent pas la même chose

| Vue | On demande | Ce qu'elle promet |
|---|---|---|
| **normalisée** | « la température à 2 m » | les noms viennent de CF et d'UDUNITS, et nous répondons de leur stabilité |
| **source** | « `t2m` d'AROME 0,025° » | **rien, par construction, puisqu'elle suit le producteur** |

Si le producteur renomme `t2m`, la vue source change — c'est son objet. Qui
l'interroge accepte ce régime en l'interrogeant. La vue normalisée existe
précisément pour qu'un consommateur n'ait pas à s'accrocher au vocabulaire
d'un producteur et à hériter de notre couplage à lui.

> La vue source est **dérivée et rangée** dans `Dataset.source_terms`, mais
> **aucune interface ne l'expose encore**. Les termes sont pris dès la
> première passe parce que décoder le corpus est l'étape coûteuse ; l'ouvrir
> demandera d'écrire cette promesse — c'est-à-dire son absence — partout où
> elle apparaîtra.

## Ce que le catalogue peut dire, et ce qu'il ne dit pas

**Il n'expose que ce que la chaîne sait lire**, et la limite est graduée :

| Situation | Exposable ? |
|---|---|
| On ne sait pas lire le champ | non — il est invisible |
| On sait lire, on ne sait pas nommer | oui, `standard_name=None`, l'écart se voit |
| On sait lire et nommer | pleinement |

**Capacité n'est pas disponibilité.** `max_step_hours` dit jusqu'où un jeu
*sait* aller — une propriété statique. Il ne dit pas si le réseau de 12 h est
présent à l'instant où l'on demande : cela se lit dans l'historique
d'exécution, pas ici. Les confondre ferait d'un incident de diffusion une
absence de capacité.

## L'inventaire est dérivé des fichiers, et il est daté

Les entrées de `data/` sont **dérivées de granules réels**, jamais des
descriptifs techniques des producteurs — qui se sont déjà révélés incomplets.
Chaque jeu porte donc un `InventorySource` : la date, la chaîne d'outillage,
la version de tables que le producteur déclarait, et les empreintes des
granules lus.

Sans cela, une divergence future serait **inattribuable** : impossible de
dire si le producteur a bougé ou si notre outillage a changé. Les standards
bougent — l'OMM a réécrit quatre entrées en place en mai 2025 — et les
producteurs ne les suivent pas au même rythme.

> Corollaire assumé : un inventaire dérivé d'un corpus partiel **sous-estime**
> ce qu'une source sait faire. `InventorySource.granules` dit exactement sur
> quoi il a été établi, donc l'écart est attribuable plutôt que caché.

## Exporter

`to_records()` rend des enregistrements **OGC API - Records**, dont WCMP2 est
l'extension de l'OMM. Ce n'est pas une prétention de conformité complète :
c'est la garantie, vérifiée par un test, que le modèle **n'empêche pas**
l'export.

STAC n'est pas la cible du modèle — sa spécification impose un `host` unique,
ce qui exclut notre redondance d'origines.
