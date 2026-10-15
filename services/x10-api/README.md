# x10-api

Première couche de démonstration API pour X10.

**L'API sert, le client consomme.** C'est la phrase qui distingue ce membre
de [`x10-client`](../x10-client/README.md), et elle décide de ce qui a sa
place ici : une surface HTTP exposée à des systèmes extérieurs, pas un
appelant de la chaîne.

## Objectif

Préparer la base d'un service applicatif capable d'exposer des données X10 via une API HTTP.

## Étapes prévues

- définir les endpoints de base,
- exposer les catalogues et données normalisées,
- préparer les intégrations avec les packages X10,
- sécuriser et documenter l'API.
