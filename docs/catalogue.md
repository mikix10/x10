# Le catalogue — ce qu'il promet, et ce qu'il refuse de faire

Le catalogue dit **ce qui existe et où le prendre**. Il ne va rien chercher,
il ne traduit aucun besoin en requête de producteur, et il expose deux vues
dont une seule engage.

Ces décisions ont été prises entre le 16/10 et le 19/10/2026, en construisant
`Registry` et en peuplant le catalogue depuis un inventaire dérivé des
fichiers. Elles vivaient dans le guide d'agent ; elles sont ici depuis le
20/11/2026, parce qu'un guide relu à chaque session n'est pas l'endroit d'un
dossier de conception.

Voir aussi [vocabulaire.md](vocabulaire.md) pour les termes eux-mêmes, et
[sources-et-acces.md](sources-et-acces.md) pour ce qui se passe en amont.

## Décisions arrêtées

- **Le catalogue expose deux vues, et elles ne promettent pas la même chose.** La vue **normalisée** — `Variable` : nom standard CF, unité UDUNITS canonique, `cell_methods`, référence verticale par son **nom standard CF** — engage : nous répondons de sa stabilité. La vue **source** — `SourceTerms` : nom court du producteur, `typeOfLevel` d'ecCodes, triplet GRIB — ne promet **rien, par construction, puisqu'elle suit le producteur**. Si Météo-France renomme `t2m`, elle change, c'est son objet ; qui l'interroge accepte ce régime en l'interrogeant.
  **Cette phrase s'écrit partout où la vue source apparaît** — docstring du modèle, `README` du paquet, toute documentation de l'interrogation. Ce n'est pas une précaution de rédaction : c'est la contrepartie qui la rend acceptable. Sans elle un intégrateur s'y adosserait en croyant à une interface.
  **Pourquoi les deux.** Un consommateur qui s'accroche à un nom de producteur hérite de notre couplage à ce producteur ; la vue normalisée existe pour qu'il n'ait pas à le faire. Mais l'interdire tout court priverait l'expert qui connaît déjà la source. Les deux vues, nettement séparées, valent mieux qu'une seule mal définie. Un test interdit tout terme d'ecCodes dans la vue normalisée, sur le modèle du lexique public.
  La vue source est **dérivée et rangée dès la première passe sans être exposée** : décoder le corpus est l'étape coûteuse — 538 Mio de granules — et la refaire plus tard pour cela seul serait du gâchis.

- **On n'expose que ce qu'on sait lire, et la limite est graduée.** Trois niveaux : un champ qu'on ne sait pas **lire** est invisible ; un champ qu'on lit sans savoir le **nommer** est exposé avec `standard_name=None` et l'écart se voit ; le reste est exposé pleinement. Le niveau intermédiaire n'est pas une concession, c'est déjà la pratique — `convert_units(strict=False)` omet l'unité au lieu d'échouer, `WITHOUT_CF_NAME` recense ce que CF ne couvre pas. Sans cette soupape, un seul code exotique rendrait un granule entier inexposable.
  **Conséquence de dimensionnement, à ne pas lire de travers** : le facteur de coût n'est pas le nombre de **formats** mais le nombre de **vocabulaires sources**. NetCDF et Zarr sont déjà CF — un lecteur suffit —, là où GRIB a coûté une table bâtie à la main. Et la charge est **récurrente**, non d'entrée.

- **L'inventaire est dérivé des fichiers, et il est daté.** Jamais des descriptifs techniques des producteurs, qui se sont révélés incomplets. Chaque jeu porte un `InventorySource` : date, chaîne d'outillage, version de tables **déclarée par le producteur**, empreintes des granules lus. Sans ces quatre champs, une divergence future serait **inattribuable** — impossible de dire si le producteur a bougé ou si notre outillage a changé, alors que les deux arrivent : l'OMM a réécrit quatre entrées en place en mai 2025, et notre ecCodes connaît les tables jusqu'à la 37 quand AROME en déclare 15.
  Corollaire assumé : un inventaire dérivé d'un corpus **partiel** sous-estime ce qu'une source sait faire. Les empreintes disent sur quoi il a été établi, donc l'écart est attribuable plutôt que caché.

- **Capacité et disponibilité sont deux questions.** `Dataset.max_step_hours` dit jusqu'où un jeu **sait** aller — statique, donc une facette de recherche. Il ne dit pas si le réseau de 12 h est là maintenant : cela se lit dans l'historique d'exécution du client. Les confondre ferait d'un incident de diffusion une absence de capacité.

- **L'interrogation du catalogue est un raffinement, pas une recherche.** Le besoin réel est un dialogue — « la température de surface », puis « à quelle échéance ? », puis on restreint. D'où `Query` qu'on resserre et `Registry.facets()` qui rend **les valeurs encore ouvertes sur un axe**, compte tenu de ce qui est déjà contraint. L'axe interrogé est exclu de sa propre contrainte, sans quoi il rendrait une liste d'un élément.
  **Un mécanisme, deux jeux de facettes** : les facettes normalisées sont implémentées, celles de la vue source ouvriront sans rien réarchitecturer. `FACET_AXES` est fermé — un axe mal orthographié rendrait une liste vide sans le dire, donc il lève.

- **Le catalogue ne construit aucune requête de producteur**, et `x10-catalog` n'importe jamais `x10-connectors` — un test le vérifie. Traduire « température à 2 m sur telle emprise » en `MeteoFrancePntRequest` exigerait un langage de sélection général, et nous avons **deux sources** : concevoir une mécanique générale sur un si petit échantillon produit une mécanique fausse. L'appelant garde la main, comme avec `CatalogEntry.origins()`.

- **Une `Distribution` par origine**, et non une distribution à plusieurs URL. Chacune porte sa priorité et sa licence — un ré-exposant peut ajouter ses conditions —, ce sur quoi s'appuie la résolution. **STAC ne convient pas ici** : sa spécification pose qu'il ne doit y avoir qu'un seul `host`, ce qui exclut la redondance.

- **Bascule d'origine, mais pas sur n'importe quelle erreur.** Un échec d'accès entraîne un repli sur l'origine suivante ; une erreur de notre fait ou de la requête — plafond de volume, chemin invalide, paramètre absurde — n'en entraîne aucun, puisqu'une autre origine servirait la même donnée et échouerait pareillement. Voir `NOT_RETRYABLE`.

- **`Retrieval` porte l'origine effectivement retenue**, qui peut différer de celle demandée. `Provenance` subsiste avec un rôle distinct : attribution d'une **valeur**, là où `Retrieval` décrit l'acquisition d'un **artefact**.

- **Le catalogue n'atteint aucune requête sortante, et c'est épinglé.** Vérifié le 19/10/2026 : toutes les URL requêtées sont des constantes de module, et `Distribution.access_url` n'est lu que pour être décrit — jamais pour aller chercher. La surface SSRF est donc **nulle**, par propriété et non par vigilance. `workspace-tests/test_surface_reseau.py` le constate et échouera le jour où un module émetteur de requêtes se mettra à le lire : un échec y est le signal qu'une relecture est due **avant** d'élargir la liste. Le même fichier interdit toute URL `http://` en clair dans les sources.
  Le pas suivant du catalogue — « l'appelant résout une entrée et le connecteur va la chercher » — casserait cette propriété **sans bruit**. C'est précisément pourquoi elle est épinglée avant, et non après.
  **Un jeton de courte durée n'est pas une variable d'environnement.** Mesuré sur Météo-France : l'identifiant d'application permet d'obtenir un jeton valable **une heure**. Poser ce jeton dans l'environnement condamnerait toute exécution de plus d'une heure. C'est donc l'identifiant **de longue durée** qui est configuré, et le connecteur — seul à connaître le protocole de sa source — qui fait l'échange.
  **Une variable par source**, nommée d'après elle : un secret partagé entre deux sources serait impossible à révoquer pour l'une sans casser l'autre. Et `Settings` ne porte aucun secret, `Credentials` étant un objet distinct : afficher la configuration reste ainsi sans risque.
  **La source est l'émetteur de l'identifiant, pas le catalogue**, et c'est une mesure qui l'a tranché. Le 19/10/2026, un seul jeton d'accès personnel ECMWF — un UUID de 36 caractères — est reconnu par **trois** magasins, CDS, ADS et EWDS, dont deux rendent le même `sub`, le même `id` et le même `email`. Une entrée par catalogue aurait stocké le même secret trois fois, sans qu'aucune révocation séparée soit possible puisque le compte est unique. D'où une seule entrée, `ecmwf_datastores`.
  **La bascule du producteur date de 2024 — l'ancien CDS et l'ancien ADS annoncés pour décommissionnement au 26/09/2024 —, mais l'annonce ne dit pas qu'un même jeton ouvre les trois magasins.** C'est notre relevé, donc notre date, et il a une péremption annoncée : les conditions d'usage de l'ADS changent le 28/10/2026, ce qui ramènerait le `403` jusqu'à nouvelle acceptation.
  **Le piège qui déguise cela en deux comptes** : l'acceptation des politiques est tenue **par magasin** et non par compte. ADS et EWDS répondent `403` en nommant les politiques manquantes, là où un jeton inconnu rendrait `401` ; lire le premier comme le second conclut à deux identifiants distincts, et le modèle en porte la trace pour longtemps. Une première sonde l'avait d'ailleurs conclu, à tort.
  **À ne pas confondre avec `access_rights`.** La codelist INSPIRE porte les motifs **juridiques** de restriction d'accès. « Cette distribution exige une authentification » est une propriété **technique** du moyen d'accès. Après licence et droits d'accès, c'est une troisième notion à garder distincte — les confondre produirait des métadonnées fausses.
