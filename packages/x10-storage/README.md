# x10-storage

**Une ébauche, et elle le dit.** Vingt-cinq lignes, deux méthodes qui lèvent
`NotImplementedError`, **aucun appelant dans le dépôt**.

Ce `README` existe pour empêcher un malentendu : qui installe ce paquet
n'obtient pas une couche de persistance, il obtient une interface que rien
n'a encore éprouvée.

## Ce qui est posé

`StorageAdapter` — `save(record)` et `load(key)` — et `StorageRecord`, une
dataclass `key` + `payload`.

## Ce qui est déjà connu de ses limites

Trois constats, écrits avant d'implémenter parce qu'ils décident de la forme :

- **Le modèle est clé → document, et ce qui arrive est fichier +
  métadonnées.** Un granule ne tient pas dans un `dict`. Y mettre un chemin
  ferait de ce paquet un index, pas un magasin — et le modèle actuel ne dit
  pas lequel des deux il est.
- **`load(key)` ne répond pas à la question qu'on pose.** La question réelle
  est « qu'ai-je, pour quelle grandeur, quel réseau, quelle échéance ? » :
  une **recherche**, pas un `get`. `x10-catalog` en porte déjà la forme avec
  `Query` et `facets()`.
- **`StorageRecord` est donné ailleurs comme l'exemple de l'objet purement
  interne**, donc dataclass mutable. Le jour où il franchit une frontière, il
  devient un modèle Pydantic gelé — ou il disparaît.

## Deux propriétés épinglées avant qu'il y ait du code

**Il n'importera pas `x10-catalog`** : la politique de résolution d'origine
sert à aller chercher chez un producteur, et n'a rien à faire dans le
composant qui détient ce qui est déjà là. **Et il n'émettra aucune requête
sortante.** Les deux s'épinglent **avant**, pas après — c'est l'enseignement
explicite de `workspace-tests/test_surface_reseau.py`.

## Quand il sera écrit

Quand un second cas réel existera : c'est leur **différence** qui dictera
l'abstraction, pas le premier seul. Voir
[docs/catalogue.md](../../docs/catalogue.md) pour la forme d'interrogation
déjà retenue ailleurs.
