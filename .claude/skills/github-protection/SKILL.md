---
name: github-protection
description: Poser, vérifier ou modifier la protection de la branche main de X10 sur GitHub (ruleset versionné, appliqué par gh api). À invoquer pour toute question de protection de branche, de vérifications obligatoires en CI, ou quand un push direct sur main est refusé.
---

# Protection de `main` — X10

La protection est définie dans `ruleset-main.json`, à côté de ce fichier. Elle est **versionnée** : on la relit, on la modifie en revue, on la restaure à l'identique. Ne jamais la régler à la souris sans reporter le changement dans ce JSON, sinon les deux divergent en silence.

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
| `required_status_checks` | `Lint et typage`, `Tests (Python 3.12)`, `Build des packages`, branche à jour avant merge |

## Deux pièges à ne pas reproduire

**Les approbations.** `required_approving_review_count` est à **0** et doit le rester tant que le projet a un seul mainteneur : GitHub interdit d'approuver sa propre PR, donc exiger une approbation bloquerait tout merge. La PR reste obligatoire — c'est elle qui déclenche la CI avant fusion.

**Le canari 3.13.** Le job `Tests (Python 3.13)` est **délibérément absent** des vérifications obligatoires. Avec `continue-on-error: true` dans le workflow, il remonte toujours `success`, même quand les tests échouent. L'exiger donnerait une garantie illusoire.

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
