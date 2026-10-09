# Contribuer à X10

Merci de l'intérêt porté au projet. Ce fichier dit comment mettre le dépôt en
route, ce qui est attendu d'une modification, et où trouver les règles qui ne
sont pas ici.

**Chaque règle a un seul domicile.** Ce fichier renvoie plutôt qu'il ne
recopie : une règle écrite à deux endroits finit par y être écrite
différemment.

## Mise en route

Le dépôt est un espace de travail [uv](https://docs.astral.sh/uv/). Il
n'exige ni installation préalable de Python ni environnement virtuel créé à
la main : `uv` s'en charge, à la version épinglée dans `.python-version`.

```bash
uv sync --all-packages --dev   # dependances et outillage
uv run pre-commit install      # controles avant chaque commit
```

Sous VSCode, les extensions recommandées sont proposées à l'ouverture du
dossier. Elles sont configurées pour utiliser le `ruff` et le `mypy` **du
projet**, et non leurs binaires embarqués — faute de quoi l'éditeur et
l'intégration continue divergeraient en silence.

## Avant de proposer une modification

```bash
uv run ruff check .            # lint
uv run ruff format .           # format
uv run mypy                    # typage strict
uv run pytest                  # suite hors ligne
```

La tâche VSCode **« Portes de qualité »** enchaîne lint, typage et tests.
C'est ce que vérifie l'intégration continue ; les lancer avant de pousser
évite un aller-retour.

## Tests et couverture

La suite par défaut **ne touche pas le réseau** et **aucune donnée binaire
n'est commise** : les fichiers GRIB2 dont les tests ont besoin se fabriquent
en mémoire. La couverture se lit en deux vues, dont une seule porte le seuil.

Ces choix et ce qu'ils impliquent pour une contribution sont détaillés dans
**[docs/tests-et-couverture.md](docs/tests-et-couverture.md)** — à lire avant
d'ajouter un test.

Une seconde note, **[docs/unites-et-interoperabilite.md](docs/unites-et-interoperabilite.md)**,
établit par l'exécution ce que GRIB, CF et UDUNITS exigent et ce que les
outils de la chaîne en font — à lire avant de toucher aux unités ou aux noms
standards. Une troisième,
**[docs/agregation-et-reechantillonnage.md](docs/agregation-et-reechantillonnage.md)**,
traite de ce que le rééchantillonnage des producteurs conserve ou détruit —
à lire avant de déclarer une propriété statistique sur un champ. Et
**[docs/intervalles-de-temps.md](docs/intervalles-de-temps.md)** pour la
période des champs agrégés, à lire avant de toucher aux axes temporels.

## Conventions de code

Elles vivent dans **[CLAUDE.md](CLAUDE.md)**, à la racine. Ce fichier est
écrit comme un guide pour l'assistant qui travaille sur le dépôt, mais son
contenu vaut pour tout le monde : structure des paquets, règles de typage,
choix entre Pydantic et dataclass, et surtout la section **« Décisions
arrêtées »**, qui explique *pourquoi* le code est ainsi.

Deux points à en retenir d'emblée :

- **Documentation et commentaires en français, identifiants et code en
  anglais.**
- **Toute donnée exploitée porte sa provenance et sa licence.** C'est une
  exigence produit, pas un détail de présentation.

## Commits et demandes de fusion

- **Conventional Commits** pour les messages.
- **Commits signés** : la branche `main` l'exige, un commit non signé ne peut
  pas y entrer.
- **Pas de poussée directe sur `main`.** Tout passe par une demande de
  fusion, qui déclenche l'intégration continue. La fusion se fait par
  écrasement, l'historique restant linéaire.
- **Une branche poussée ne se réécrit pas.** Pas de `--force`, pas de
  `--no-verify` : les contrôles locaux sont là pour attraper ce que la CI
  attraperait plus tard et plus cher.

Le détail de la protection de branche est versionné à côté du
[skill correspondant](.claude/skills/github-protection/).

## Ce que le dépôt ne doit pas contenir

Le dépôt est public.

- **Aucun secret**, évidemment — un contrôle automatique le vérifie à chaque
  commit.
- **Aucun identifiant personnel** : adresse de courriel, chemin absolu
  nominatif. Un contrôle le vérifie aussi. Un faux positif se corrige en
  anonymisant le fichier, jamais en affaiblissant le contrôle.
- **Aucun nom de projet utilisateur ni de source dont le responsable n'a pas
  donné son accord.** Un contrôle local compare chaque commit à une liste de
  termes, délibérément non versionnée : l'y écrire reviendrait à publier
  précisément ce qu'elle protège. Sur un clone neuf, en demander le contenu
  au mainteneur plutôt que de sauter le contrôle.

Les sources effectivement intégrées échappent à cette dernière règle : leur
nom, leur licence et leur provenance doivent au contraire être explicites.

## Signaler plutôt que contourner

Si un contrôle bloque, il a le plus souvent raison. S'il a tort, c'est le
contrôle qu'il faut corriger, et la correction intéresse tout le monde —
ouvrir un ticket vaut mieux que la contourner localement.
