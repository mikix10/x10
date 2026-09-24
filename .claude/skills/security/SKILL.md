---
name: security
description: Relecture de sécurité pour X10 — secrets, chaîne d'approvisionnement, et surface d'attaque propre à l'ingestion de fichiers distants (SSRF, traversée de chemin, bombes de décompression, XXE). À invoquer avant toute intégration d'une nouvelle source de données, d'un nouveau moyen d'accès ou d'une nouvelle surface d'exposition, ainsi qu'en cas de suspicion de fuite de secret.
---

# Relecture de sécurité — X10

Document vivant, à compléter au fil des sources et des moyens d'accès intégrés. Si une relecture fait apparaître un risque non listé ici, l'ajouter.

## Quand l'invoquer

- Intégration d'une **nouvelle source de données** ou d'un nouveau producteur.
- Nouveau **moyen ou protocole d'accès** : HTTP Byte-Range, S3, FTP, API authentifiée, OPeNDAP.
- Nouvelle **surface d'exposition** : endpoint d'API, format de sortie, téléversement.
- Toute PR touchant `x10-connectors` ou `x10-api`.
- Avant une publication sur PyPI.
- Dès qu'une fuite de secret est suspectée.

## 1. Secrets

### Prévention

- `gitleaks` tourne en hook `pre-commit` : un secret est bloqué avant le commit.
- Le *push protection* GitHub bloque côté serveur un push contenant un jeton reconnu.
- `detect-private-key` en `pre-commit` couvre les clés privées.
- `.env`, `.env.*` et `.pypirc` sont ignorés par git.

### En cas de fuite — l'ordre compte

**L'historique git est permanent.** Un secret commité puis retiré au commit suivant reste lisible dans l'historique, et sur un dépôt public il est moissonné en quelques minutes.

1. **Révoquer et faire tourner le secret.** C'est la seule action qui referme réellement la brèche, et elle passe avant tout le reste.
2. Vérifier les journaux d'usage du service concerné.
3. Seulement ensuite, envisager la réécriture d'historique — utile pour l'hygiène, sans effet sur un secret déjà moissonné.
4. Consigner l'incident.

Ne jamais inverser 1 et 3. Nettoyer l'historique en laissant le jeton actif donne l'illusion d'avoir traité le problème.

## 2. Chaîne d'approvisionnement

- `uv.lock` est commité, la CI installe avec `--locked` : les versions sont figées et vérifiées.
- Les actions GitHub sont épinglées sur des **SHA complets**, pas sur des tags. Un tag est mutable ; un SHA non.
- Toute nouvelle dépendance du domaine (`cfgrib`, `eccodes`, `ecmwf-opendata`, `xarray`) reste cantonnée à `x10-connectors`, en extra optionnel. Le noyau ne doit pas être contaminé.
- Ces bibliothèques enveloppent du code natif (ecCodes est en C) : leur surface de bug mémoire est réelle sur des fichiers malformés. Raison de plus pour ne pas les rendre obligatoires.

## 3. Relecture de code — surface d'attaque propre à X10

X10 télécharge des fichiers décrits par un catalogue et les transforme. Les entrées sont donc **distantes et non maîtrisées**, même quand la source est réputée fiable.

### URL et requêtes sortantes

- Une URL venant du catalogue est une **entrée non fiable**. Valider le schéma (`https` uniquement) et l'hôte contre une liste connue avant toute requête.
- Refuser les redirections vers des adresses privées ou de bouclage — c'est le cas SSRF classique.
- Toujours poser un `timeout` explicite. Jamais de requête sans délai maximal.
- Ne jamais désactiver la vérification TLS, même « temporairement pour tester ».

### Écriture des fichiers téléchargés

- Le nom de fichier ne doit **jamais** provenir directement de la réponse distante (`Content-Disposition`, dernier segment d'URL). Traversée de chemin garantie à terme.
- Construire le chemin de destination soi-même, puis vérifier qu'il reste sous la racine prévue après résolution.

### Volumétrie

- Plafonner la taille téléchargée. Ne pas se fier au `Content-Length` annoncé : il peut mentir.
- GRIB, NetCDF et les archives compressées se prêtent aux **bombes de décompression** : une entrée de quelques Mo peut en produire plusieurs Go.
- Ne pas charger un champ maillé entier en mémoire sans borne.

### Parsing

- Métadonnées XML : utiliser `defusedxml`, jamais `xml.etree` nu. Les entités externes permettent la lecture de fichiers locaux et le SSRF.
- Jamais de `pickle`, `eval` ou `yaml.load` non sûr sur une donnée distante.

### Exposition par l'API

- Ne pas refléter dans une réponse d'erreur un chemin de système de fichiers, une URL interne ou une trace d'exception.
- Valider les paramètres d'emprise et de pagination : une requête peut demander un volume dissuasif.

## 4. Divulgation

**Ne jamais décrire une faille non corrigée et non publiée dans un message de commit, une PR ou une issue publique.** Sur un dépôt public, `fix: prevent path traversal in the GRIB writer` est une notice d'exploitation offerte à tous ceux qui n'ont pas encore mis à jour.

La marche à suivre : avis de sécurité GitHub (GHSA) en mode privé, correctif préparé et publié, puis publication de l'avis avec la description. Le commit de correctif référence l'avis, il ne détaille pas l'exploit.

## 5. À mettre en place plus tard

- **Dependabot** et **CodeQL** : gratuits sur dépôt public, différés tant que le code métier se résume à des stubs — ils ne produiraient que du bruit. À activer dès que `x10-connectors` contient du code réel.
- **SECURITY.md** : politique de divulgation publique, à écrire au moment de la première publication PyPI, quand le projet aura des utilisateurs à qui s'adresser.
- **Montée de version des actions GitHub** : `checkout` et `upload-artifact` sont en v4, `setup-uv` en v5, alors que v7 et v10 existent. Épinglés sur SHA donc immuables, mais en retard. À traiter comme un changement fonctionnel à part entière, testé, pas glissé dans un commit de sécurité.
