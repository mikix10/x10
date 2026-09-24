# x10-storage

Abstractions de persistance pour X10.

## Objectif

Définir une interface technique indépendante du backend concret de stockage pour les données X10.

## Rôle

Cette couche doit permettre :
- d'isoler le stockage du reste du système,
- de préparer des adaptateurs pour différents backends,
- de rester compatible avec un futur déploiement plus lourd.
