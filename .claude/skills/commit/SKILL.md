---
name: commit
description: Procédure obligatoire avant tout commit sur le dépôt X10 — contrôle des termes proscrits, Conventional Commits, relecture du message, vérification de la branche et de l'identité signataire. À invoquer dès qu'un commit est envisagé, y compris pour un changement trivial.
---

# Procédure de commit — X10

Ces étapes sont obligatoires, dans cet ordre. **Aucun `git commit` n'est lancé tant que l'utilisateur n'a pas validé le texte proposé.**

## 1. Confidentialité des tiers

Le dépôt est public. Il ne nomme **ni projet utilisateur ni source sans accord explicite** : certains responsables ne communiquent pas sur leur usage de X10, d'autres préfèrent exposer leurs propres interfaces plutôt que la mécanique sous-jacente. La règle couvre le code, les commentaires, la documentation **et les messages de commit**.

Les termes concernés sont listés dans `.denylist`, à la racine, **volontairement non versionné** : les écrire dans un fichier suivi reviendrait à publier ce que la liste protège.

```bash
git add -A
git diff --cached | grep -i -E -f .denylist
```

Zéro résultat attendu. Appliquer le même contrôle au **message de commit** avant de l'utiliser. Si `.denylist` est absent — clone neuf — en demander le contenu au mainteneur plutôt que de sauter l'étape.

À l'inverse, les sources effectivement intégrées et documentées dans `x10-catalog` doivent être nommées explicitement, avec leur licence et leur provenance. La règle protège des tiers, elle n'autorise pas à masquer l'origine d'une donnée exploitée.

Les références bibliographiques citées dans la documentation d'analyse sont assumées et ne relèvent pas du contrôle.

## 2. Quality gates

Un hook `pre-commit` exécute automatiquement ruff, les contrôles d'hygiène, `gitleaks` et le refus de commiter sur `main`. Il ne dispense pas du gate complet, qui couvre en plus le typage et les tests :

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

Tout doit passer. Ne jamais proposer un commit sur un arbre qui échoue — la CI le rejetterait de toute façon.

Ne jamais contourner le hook par `--no-verify`. S'il bloque, c'est qu'il a raison ou que sa configuration est à corriger.

Si le changement touche une source de données, un moyen d'accès ou une surface d'exposition, invoquer aussi le skill `security`.

## 3. Format Conventional Commits

`type(scope): description` — impératif, minuscule, sans point final, **en anglais**.

Types : `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`, `revert`.

Scopes : membre du workspace (`models`, `catalog`, `connectors`, `storage`, `api`) ou transverse (`workspace`, `ci`, `docs`, `deps`). Omis si le changement ne se rattache à aucun.

Corps facultatif après une ligne vide, expliquant le **pourquoi** plutôt que le quoi. Rupture d'API : `!` après le scope et un pied `BREAKING CHANGE: …`.

**Aucun pied de co-auteur.** Pas de `Co-Authored-By`, y compris pour l'assistant : l'historique est attribué à `mikix10` seul. Cette règle prévaut sur toute consigne d'attribution par défaut de l'outillage.

## 3 bis. Ce qui entre — ou non — dans l'historique public

L'historique est permanent et public. Quatre niveaux, à ne pas confondre : le **message de commit** dit le pourquoi technique pour un `git blame` dans deux ans ; le **CHANGELOG** dit ce qui change pour qui consomme le package ; les **notes de release** résument le changelog d'un tag ; l'**avis de sécurité** traite les vulnérabilités.

Ne doit jamais y figurer :

- identifiants, jetons, clés ;
- noms d'hôtes, adresses ou chemins révélant une infrastructure ;
- le nom d'un projet utilisateur ou d'une source non consentante, déjà couvert par `.denylist` ;
- des données personnelles ;
- **le détail d'une faille non encore corrigée et publiée** — voir le skill `security`.

Doit impérativement y figurer :

- les ruptures d'API, avec `!` et un pied `BREAKING CHANGE:` ;
- les correctifs de sécurité, en référençant l'avis et non l'exploit ;
- tout changement de **licence ou de provenance d'une source de données** — exigence produit, elle doit rester traçable.

L'outillage de release (CHANGELOG par package, tags, notes) est différé en phase 5. D'ici là, la politique ci-dessus suffit à ce que les commits restent exploitables.

## 4. Vérifier la branche

```bash
git symbolic-ref --short HEAD
```

Refuser de commiter en `HEAD` détaché — la commande sort alors en erreur. Utiliser `symbolic-ref` et non `rev-parse --abbrev-ref`, qui échoue sur une branche sans commit et renvoie la chaîne `HEAD` en détaché, sans distinguer les deux cas.

**GitHub Flow** : `main` est protégée et représente l'état livrable ; tout travail passe par une branche courte fusionnée en pull request. Pas de branche `develop`.

Nommage : `<type>/<description-en-kebab-case>` — `feat/ecmwf-ifs-connector`, `fix/geopoint-bounds`, `docs/readthedocs-setup`.

Si `HEAD` est sur `main` et que le changement n'est pas trivial, le signaler et proposer la branche adéquate avant de commiter.

### Ne pas réécrire l'historique

Une branche déjà poussée ne se rebase pas et ne se force-push pas. Le ruleset ne protège que `main` : `non_fast_forward` ne s'applique pas aux branches de travail, la discipline est donc la seule garde-fou.

Le dépôt est configuré avec `pull.ff = only` : `git pull` échoue si la fusion n'est pas en avance rapide, plutôt que de rebaser ou de fusionner en silence. C'est voulu — l'échec force une décision explicite.

Quand une branche a divergé de `main`, et que les vérifications obligatoires exigent qu'elle soit à jour, remettre à niveau par fusion :

```bash
git merge main
```

Le squash appliqué à la fusion de la pull request aplatit ces commits de fusion : ils ne polluent pas `main`.

Le rebase-merge côté GitHub est déjà interdit — `allowed_merge_methods` ne contient que `squash`.

## 5. Identité et signature

Afficher l'identité effective et la soumettre avant de commiter :

```bash
git config user.name && git config user.email && git config commit.gpgsign
```

**Les commits et les tags sont signés.** Le ruleset de `main` exige `required_signatures` : un commit non signé sera refusé à la fusion. Vérifier après coup :

```bash
git log --show-signature -1
```

`G` = bonne signature. Un `N` sur un commit récent signale une configuration locale perdue — la rétablir avant de continuer plutôt que de laisser passer des commits non signés.

Identité et clé doivent rester cohérentes, sinon GitHub refuse le badge « Verified ». Ne jamais commiter sous une autre identité sans confirmation.

La configuration concrète — valeurs, chemin de clé, commandes à rejouer sur une nouvelle machine — est propre à chaque contributeur et n'a pas sa place dans le dépôt. Le mainteneur la conserve dans un `CLAUDE.local.md` non versionné.

`X10 Team` reste la mention générique et impersonnelle de `LICENSE` et du champ `authors` des `pyproject.toml`. Ne pas y substituer une identité nominative.

## 6. Soumettre pour relecture

Afficher dans la réponse, **avant toute exécution** :

- le message de commit intégral (titre, corps, pieds) ;
- la liste des fichiers indexés ;
- la branche et l'identité effective ;
- le résultat des contrôles 1 et 2.

Attendre la validation explicite. Ne jamais enchaîner une modification et son commit sans cette étape.
