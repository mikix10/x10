# Les sources, et la manière de les atteindre

Ce que le dépôt a arrêté sur **ce qu'il va chercher et comment** : le client
ECMWF, la voie sans authentification de Météo-France, les plages d'octets, la
place d'un secret, et ce qu'une cadence de producteur permet.

Le fil commun est une règle : **on mesure ce qu'une source sert, on ne lit pas
son descriptif**. Les relevés par source vivent à part —
[AROME](arome-paquets-et-api-ciblee.md),
[ARPEGE](arpege-paquets-et-api-ciblee.md),
[le portail Météo-France](meteofrance-portail-api.md),
[les magasins Copernicus](copernicus-data-stores.md) — et les écarts constatés
dans [divergences-observees.md](divergences-observees.md).

Ces décisions vivaient dans le guide d'agent ; elles sont ici depuis le
20/11/2026.

## Décisions arrêtées

- **Accès ECMWF : le client officiel `ecmwf-opendata`**, en extra optionnel `ecmwf` de `x10-connectors`. Il implémente déjà l'index et les plages d'octets que nos décisions visaient, et expose quatre origines — ECMWF, AWS, Azure, Google — ce qui sert la redondance. Ne pas réimplémenter.
  **Deux pièges vérifiés le 29/09/2026.** Le client n'expose **aucun délai maximal** de requête ; ses valeurs de reprise par défaut, 500 tentatives espacées de 120 s, autorisent une attente de plusieurs heures. Le connecteur les abaisse à 3 et 10 s, et un test le garantit.

- **Les données ouvertes de l'ECMWF ne servent que du GRIB2**, et là où il propose du NetCDF — le CDS Copernicus qu'il opère —, **il faut un compte**. Vérifié le 16/10/2026 : la page officielle dit « GRIB2 unless stated otherwise », les répertoires de `data.ecmwf.int` ne portent que des `.grib2` et leurs `.index`, et le registre AWS concorde. Le gain de format et le besoin de secret arrivent donc ensemble, et non l'un sans l'autre.
  **L'index d'un fichier est un document de capacités gratuit** : relevé le 16/10/2026, 2,6 Kio énumèrent les treize paramètres de vagues, 2 Mio les 8 500 messages d'un fichier d'ensemble — sans toucher à la donnée, et **sans jeton**, contrairement au `GetCapabilities` de Météo-France.

- **La requête ECMWF est ouverte au-delà du déterministe de surface**, par cinq vocabulaires fermés — `STREAMS`, `TYPES`, `LEVTYPES`, `ENSEMBLE_STREAMS`, `MEMBERS` — validés comme l'était déjà `ORIGINS`. Le modèle s'étend donc sans se casser : `Variable.realizations` porte la cinquième dimension, du nom que CF donne à cet axe.
  **Trois points mesurés le 16/10/2026 sur l'index réel.** L'ensemble sert **50 membres perturbés** — 51 avant le cycle 50r1, contrôle compris — et son contrôle se prend désormais dans `oper`/`fc` ; `scda` et `scwv` ont rejoint `oper` et `wave` au même cycle, et restent admis pour lire une archive antérieure. Un fichier d'échéance d'ensemble porte **8 500 messages**, d'où une sélection par membre qui est **une borne de volume autant qu'un filtre** : sans elle le flux est inexploitable sous le plafond.
  **La clé `number` est omise, pas posée à vide**, le client officiel la refusant hors d'un flux d'ensemble — la poser ferait échouer tout le trafic déterministe, et un test le garantit.
  **Le seuil d'énumération du contrat décide d'où se lit le compte de membres.** Au-delà de `ENUMERATION_THRESHOLD`, soit 64 valeurs, une coordonnée est caractérisée dans `geometry.grid` au lieu d'être énumérée dans `coords`. Les 50 membres d'ECMWF passent par le premier chemin ; un producteur plus fourni basculerait dans le second, et ne lire que `coords` rendrait `None` **précisément sur l'ensemble le plus volumineux**. `_realizations` consulte donc les deux, et un test couvre le chemin qu'aucune donnée réelle n'atteint aujourd'hui.
  **Le `typeOfLevel` de `levtype=sol` n'est pas supposé.** `depthBelowLandLayer` figure déjà dans `CF_VERTICAL`, mais rien ne prouve qu'ECMWF l'emploie : un test `network` le demande au producteur et nomme le type à ajouter s'il diffère. Ajouter l'entrée par déduction serait la faute même que corrige la règle « on ne devine pas ».

- **La sélection par plages d'octets ne porte jamais sur la géographie.** L'index adresse le message, et un message GRIB2 est un champ global dont la section de données est un bloc unique compressé en CCSDS — template 42, grille 1440 × 721. Un sous-domaine s'obtient après décodage, pas au téléchargement. Vrai pour tout client.

- **Deuxième source : les paquets Météo-France, par la voie sans authentification**, donc **X10 ne porte aucun secret**. Le choix exclut le temps sensible, les niveaux isothermes et le sommet d'atmosphère, réservés à l'API ciblée ; il gagne une archive plus profonde et le géopotentiel aux niveaux hauteur. Les deux voies **ne se recouvrent pas** : ce ne sont donc pas deux `Distribution` d'un même `Dataset`, que le modèle suppose interchangeables, mais deux jeux distincts. Mesures et détail dans les deux notes de `docs/`.

- **Un secret vit dans le client, jamais dans un paquet.** « X10 ne porte aucun secret » disait que les **paquets** n'en détiennent aucun, pas qu'aucune source authentifiée ne serait jamais atteinte. La règle se précise donc sans changer : **le client résout, le connecteur reçoit** un identifiant déjà résolu en paramètre. Vérifié le 16/10/2026 et désormais **exigé par un test** : zéro `os.environ` et zéro `getenv` dans `packages/*/src`.
  **Ce qui rend la chose sûre est mesuré.** `pydantic.SecretStr` rédige sur tous les chemins que X10 emprunte — `repr`, `str`, f-string, `model_dump`, `model_dump_json` —, et seul `get_secret_value()` expose. Un secret ne peut donc fuir ni dans `runs.jsonl`, ni dans un compte rendu, ni dans un message d'exception composé par interpolation.
  **Le seul chemin qui restait ouvert était l'URL.** Une bibliothèque HTTP met volontiers l'adresse complète dans son message d'exception, et `observability.failure_fields` la recopiait dans `error.message` ; un jeton passé en paramètre de requête atterrissait au journal ECS. D'où `observability.redact`, qui retire la chaîne de requête en gardant le chemin — celui-ci suffit au diagnostic, le `?…` ne sert qu'à fuir. **La fonction est le filet, pas la méthode** : un secret ne voyage jamais en paramètre d'URL quand un en-tête existe.
  **Correction du 19/10/2026 : ce n'était pas le seul chemin.** Mesuré avant la première source authentifiée, sur quatre formes réalistes de message, `redact` en couvre **une** : elle laisse passer un jeton dans le *chemin* d'une URL, un en-tête recopié dans le texte de l'exception, et un identifiant cité en clair. Les trois viennent du texte de la **bibliothèque tierce**, que notre règle sur la construction d'URL ne gouverne pas.
  **La parade est la rédaction par valeur**, `observability.SecretRedactor` : un filtre `logging` qui remplace toute occurrence d'une valeur connue. Il couvre les quatre cas et ne suppose rien de la bibliothèque — deviner la forme d'un message tiers est une course perdue. Le partage est celui déjà posé ailleurs : **le paquet fournit le mécanisme, l'application fournit les valeurs**. `Credentials.redactor()` le construit côté client, et c'est l'appelant qui l'installe, comme pour tout le reste de la journalisation.
  **Trois propriétés tiennent la parade, chacune testée** : le `repr` du filtre ne montre jamais ses valeurs ; un secret trop court est **refusé** et non ignoré, parce que le rédiger détruirait le journal sans rien protéger ; et un secret contenu dans un autre est rédigé en premier, faute de quoi le plus long ressortirait tronqué. Limite assumée : un filtre s'exécute avant le formatage, donc une trace d'appels rendue par un formateur tiers lui échappe.

- **Pas de téléchargement sélectif par plage d'octets chez Météo-France** : le producteur ne publie aucun index, et le reconstruire se fige au-delà d'environ 3 500 requêtes successives sur un même objet. Le levier de sélection est le **choix du paquet**, d'où un plafond de volume par défaut à 256 Mio — il laisse passer la surface et arrête les niveaux.

- **Sur `data.gouv.fr`, la cadence se lit au catalogue et non à l'en-tête HTTP.** Vérifié le 13/10/2026 : deux ressources d'un même jeu, publiées à quinze jours d'intervalle, rendent **le même `Last-Modified`, à la seconde près** — l'en-tête décrit l'objet de stockage et reflète une migration d'infrastructure, pas une publication. C'est l'inverse de ce qu'on suppose d'ordinaire, et l'inverse de ce qu'une première analyse avait conclu sur la cadence des champs CONSTANT.
  Corollaire sur l'empreinte : le catalogue publie un **SHA-1 par ressource**, et celui de l'archive de définitions **ne correspond pas** aux octets servis, alors que la taille annoncée est exacte à l'octet. Une empreinte publiée qui ne vérifie rien est un piège — qui la contrôle conclut à une corruption, qui ne la contrôle pas n'a aucun validateur. Le seul validateur sûr reste celui que **nous** calculons.
