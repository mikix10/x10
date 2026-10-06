---
name: github-protection
description: Poser, vérifier ou modifier la protection de la branche main de X10 sur GitHub (ruleset versionné, appliqué par gh api). À invoquer pour toute question de protection de branche, de vérifications obligatoires en CI, ou quand un push direct sur main est refusé.
---

# Protection de `main` — X10

La configuration est définie dans deux fichiers versionnés, à côté de celui-ci : `ruleset-main.json` pour la protection de branche, `repo-settings.json` pour les réglages du dépôt. Elle est **versionnée** : on la relit, on la modifie en revue, on la restaure à l'identique. Ne jamais la régler à la souris sans reporter le changement dans ce JSON, sinon les deux divergent en silence.

## Prérequis

`gh` doit être authentifié **en tant que mikix10** — c'est un jeton distinct de celui de git :

```bash
gh auth status
```

Si ce n'est pas le cas, l'utilisateur doit lancer `gh auth login` lui-même : le flux OAuth exige un navigateur ou un code d'appareil, impossible depuis une session non interactive.

## Pas d'étape d'activation

`ruleset-main.json` porte `"enforcement": "active"` : la règle est effective dès sa création, il n'y a pas de second geste.

Le piège est dans l'interface web, où un ruleset créé à la souris expose un sélecteur de statut. Il est facile de le laisser sur *Disabled* et de se croire protégé. Vérifier après coup, quel que soit le chemin emprunté :

```bash
gh api repos/mikix10/x10/rulesets --jq '.[] | "\(.name): \(.enforcement)"'
```

## Appliquer

```bash
gh api -X POST repos/mikix10/x10/rulesets \
  --input .claude/skills/github-protection/ruleset-main.json
```

Mettre à jour un ruleset existant (récupérer son `id` via la liste ci-dessous) :

```bash
gh api -X PUT repos/mikix10/x10/rulesets/<id> \
  --input .claude/skills/github-protection/ruleset-main.json
```

## Vérifier

```bash
gh api repos/mikix10/x10/rulesets
gh api repos/mikix10/x10/rulesets/<id> --jq '.enforcement, (.rules[].type)'
```

Test réel — ce push doit être **refusé** :

```bash
git push origin main
```

## Contenu de la règle

| Règle | Effet |
|---|---|
| `deletion` | `main` ne peut pas être supprimée |
| `non_fast_forward` | force push interdit |
| `required_linear_history` | pas de commit de fusion, cohérent avec le squash |
| `required_signatures` | tout commit doit être signé |
| `pull_request` | PR obligatoire, **0 approbation requise**, squash uniquement |
| `required_status_checks` | `Lint et typage`, `Tests (Python 3.12)`, `Build des packages`, `Portabilite (Python 3.12 / windows-latest)`, `Portabilite (Python 3.12 / macos-latest)`, branche à jour avant merge |

## Renommer ou ajouter un job de CI : l'ordre compte

**Un contexte requis qui ne correspond à aucun job bloque toute fusion,
définitivement** — la vérification n'arrive jamais, et rien ne signale
pourquoi. C'est le piège le plus coûteux de ce ruleset.

Il se déclenche dès qu'on renomme un job, qu'on introduit une matrice — le
nom affiché change alors, `Tests (Python 3.12)` devenant par exemple
`Tests (3.12, ubuntu-latest)` — ou qu'on inscrit un contexte avant que le job
existe.

Deux règles, dans cet ordre :

1. **Ajouter un job** : fusionner d'abord le workflow, constater que le
   nouveau contexte apparaît bien sur une demande de fusion, **puis**
   seulement l'inscrire au ruleset. L'inscrire d'abord bloquerait la
   demande de fusion qui apporte le job.
2. **Renommer ou supprimer un job requis** : retirer d'abord le contexte du
   ruleset, fusionner le workflow, réinscrire le nouveau nom. Sans cela, la
   demande de fusion qui porte le renommage est bloquée par son propre
   changement.

Dans les deux cas, le fichier JSON peut être mis à jour en même temps que le
workflow : c'est son **application** qui doit attendre.

## Dérive : GitHub complète les paramètres omis

À la création, l'API renseigne d'elle-même les paramètres absents du JSON, avec ses propres valeurs par défaut. Le fichier versionné cesse alors de décrire la règle en vigueur, ce qui est précisément ce que ce skill cherche à éviter.

**Après toute création ou modification, comparer et resynchroniser :**

```bash
gh api repos/mikix10/x10/rulesets/<id> --jq '.rules[] | {type, parameters}'
```

Tout paramètre ajouté par GitHub doit être reporté explicitement dans `ruleset-main.json`, même s'il conserve la valeur par défaut. Un paramètre implicite est un paramètre qu'on ne relit pas.

C'est ainsi qu'est apparu `require_extra_approval_for_unattributed_changes`, ajouté à `true` lors de la première création.

## Trois pièges à ne pas reproduire

**Les approbations.** `required_approving_review_count` est à **0** et doit le rester tant que le projet a un seul mainteneur : GitHub interdit d'approuver sa propre PR, donc exiger une approbation bloquerait tout merge. La PR reste obligatoire — c'est elle qui déclenche la CI avant fusion.

**Le canari 3.13.** Le job `Tests (Python 3.13)` est **délibérément absent** des vérifications obligatoires. Avec `continue-on-error: true` dans le workflow, il remonte toujours `success`, même quand les tests échouent. L'exiger donnerait une garantie illusoire.

**Les changements non attribués.** `require_extra_approval_for_unattributed_changes` est à **`false`**, et doit le rester tant que le projet a un seul mainteneur. À `true`, un commit dont l'auteur n'est rattaché à aucun compte GitHub exige une approbation supplémentaire — impossible à fournir seul, donc blocage dur sans autre issue que de désactiver le ruleset. C'est la même trappe que les approbations obligatoires, par une autre porte. À repasser à `true` le jour où un second contributeur peut approuver.

Un workflow déclenché uniquement par `workflow_dispatch` ne doit jamais figurer dans les vérifications obligatoires : n'étant pas déclenché par les pull requests, son statut ne remonterait jamais et **toute fusion serait bloquée définitivement**.

## Réglages du dépôt

`repo-settings.json` couvre ce que l'interface expose sous **Settings → General**. Sans lui, ces réglages ne vivraient que dans l'interface : illisibles en revue, et un changement passerait inaperçu.

```bash
gh api -X PATCH repos/mikix10/x10 --input .claude/skills/github-protection/repo-settings.json
```

Vérifier, et détecter toute dérive :

```bash
gh api repos/mikix10/x10 --jq 'to_entries[] | select(.key | IN("has_issues","has_projects","has_wiki","has_discussions","has_downloads","allow_squash_merge","allow_merge_commit","allow_rebase_merge","allow_auto_merge","allow_update_branch","delete_branch_on_merge","squash_merge_commit_title","squash_merge_commit_message","web_commit_signoff_required")) | "\(.key) = \(.value)"'
```

### Pourquoi ces valeurs

| Réglage | Raison |
|---|---|
| `allow_squash_merge` seul | `required_linear_history` interdit les commits de fusion ; le rebase-merge réécrit l'historique. Le squash est la seule méthode cohérente. |
| `allow_update_branch` | **Indispensable** avec `strict_required_status_checks_policy` : dès que `main` avance, les PR deviennent périmées. Ce réglage fournit le bouton « Update branch », qui fusionne `main` dans la branche en un clic — sans rebase, conforme à la règle de non-réécriture. |
| `allow_auto_merge` | Programme la fusion dès l'ouverture : elle part quand les vérifications passent. Confort réel pour un mainteneur seul, sans affaiblir aucune règle. |
| `delete_branch_on_merge` | Évite l'accumulation de branches mortes. |
| `has_wiki`, `has_projects`, `has_discussions` | Désactivés : fonctions inutilisées, donc surface en moins. |
| `has_downloads` | Fonction vestigiale, laissée désactivée. |
| `squash_merge_commit_message` | `COMMIT_MESSAGES` préserve le message Conventional Commits quand la branche n'a qu'un commit. Sur une branche à plusieurs commits, tous les messages sont concaténés : passer à `PR_BODY` si cela devient verbeux. |

Les champs propres au dépôt — `name`, `description`, `homepage` — sont **volontairement absents** : c'est ce qui rend le fichier réutilisable tel quel.

## Réutiliser sur un autre dépôt

Les deux fichiers sont écrits pour servir de modèle de configuration. Aucun ne contient le nom du dépôt : celui-ci est passé en argument.

```bash
gh api -X PATCH repos/<owner>/<repo> --input repo-settings.json
gh api -X POST  repos/<owner>/<repo>/rulesets --input ruleset-main.json
```

`ruleset-main.json` cible `~DEFAULT_BRANCH` et non un nom en dur, il s'applique donc quelle que soit la branche par défaut.

**Un seul point à adapter** : les `required_status_checks` portent les noms des jobs de la CI de X10 — `Lint et typage`, `Tests (Python 3.12)`, `Build des packages` et les deux contextes de portabilité. Sur un autre dépôt, les remplacer par les noms exacts de ses propres jobs. Un nom qui ne correspond à aucun job existant **bloque toute fusion définitivement**, la vérification ne remontant jamais.

Deux réglages ne passent pas par ces fichiers et restent à faire dans l'interface : la *push protection* du secret scanning, et l'auto-fermeture des tickets liés à une PR fusionnée, qu'aucun champ de l'API REST n'expose à ce jour.

## Escape hatch

`bypass_actors` est vide : même le propriétaire du dépôt est soumis à la règle. C'est voulu.

Si un déblocage est un jour nécessaire, ne pas ajouter d'acteur en dérogation permanente — cela vide la règle de son sens et reste invisible. Passer plutôt l'`enforcement` à `disabled` le temps de l'opération, puis le remettre à `active` :

```bash
gh api -X PUT repos/mikix10/x10/rulesets/<id> -f enforcement=disabled
# … opération …
gh api -X PUT repos/mikix10/x10/rulesets/<id> -f enforcement=active
```

La désactivation est tracée dans l'historique du ruleset, une dérogation permanente ne l'est pas.

## Réglages complémentaires hors ruleset

Dans **Settings → General → Pull Requests** (pas couvert par l'API ruleset) :

- n'autoriser que le *squash merge* ;
- cocher la suppression automatique des branches fusionnées.
