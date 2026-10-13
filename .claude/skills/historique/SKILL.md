---
name: historique
description: Répondre à une question portant sur l'historique de nos échanges — qui a proposé quoi, quand une décision a basculé, ce qui a été affirmé puis corrigé — en fouillant le transcrit de session plutôt qu'en se fiant à la mémoire. À invoquer dès qu'une question porte sur le fil de la conversation et non sur l'état du code.
---

# Fouiller l'historique des échanges

Le transcrit de session est une **source primaire**, et la mémoire de
conversation n'en est pas une. Dès qu'une question porte sur ce qui a été dit
— par qui, quand, et ce qui a changé depuis —, elle se traite par la mesure,
exactement comme une question sur la donnée.

Ce n'est pas une précaution de principe. Éprouvé le 12/10/2026 : j'ai d'abord
répondu de mémoire à une question sur les apports du mainteneur, et **j'ai
omis deux contributions décisives** — Unidata et INSPIRE — que le transcrit
montrait pourtant reconnues noir sur blanc au moment où elles ont été faites.

## Quand l'invoquer

- « qu'est-ce que je t'ai apporté », « qu'ai-je dit sur X »
- « quand avons-nous décidé Y », « pourquoi avons-nous changé d'avis »
- « où t'es-tu trompé », « qu'as-tu affirmé sans mesurer »
- toute rétrospective, tout point d'étape qui s'appuie sur le fil

**Ne pas l'invoquer** pour une question sur l'état du code, les décisions
arrêtées ou la configuration : `CLAUDE.md`, le code et `git log` font foi,
et ils sont plus sûrs.

## Où est le transcrit

Sous `~/.claude/projects/<dossier-de-projet>/<session>.jsonl`, le nom de
dossier étant le chemin du dépôt dont les séparateurs sont remplacés par des
tirets — `D:\x10` donne `d--x10`.

**Ne jamais écrire ce chemin en dur** : il est nominatif, et la règle du
point unique l'interdit partout ailleurs que dans `CLAUDE.local.md`.
`extraire.py` le déduit.

Une session compactée reste **un seul fichier** : le transcrit porte donc
tout l'historique, pas la seule fenêtre courante. Au 12/10/2026 : 33 Mio,
1 154 tours de parole, toute l'histoire du projet.

## Organisation des fichiers produits

Toujours la même, pour qu'une analyse se retrouve et se compare à une autre.

```
<depot>-hors-depot/info/
    AAAAMMDD_<sujet-en-kebab-case>/
        fil.md               le fil lisible, outils et raisonnement retires
        releve-brut.json     les occurrences, avec l'amont qui les a declenchees
        releve-trie.md       les memes, groupees par categorie, dedoublonnees
        <synthese>.md        ce qu'on en tire, redige
```

La racine se déduit du dépôt — `x10` donne `x10-hors-depot/info` — et
`X10_HORS_DEPOT` la surcharge.

> **L'emplacement et le nom du dossier se font confirmer avant d'être créés.**
> Sans exception, et avant toute écriture. Ces dossiers s'accumulent et
> servent à se repérer des mois plus tard : c'est le mainteneur qui sait sous
> quel nom il les retrouvera. Vérifié le 12/10/2026 — le nom qu'il a retenu
> n'était pas celui que j'aurais choisi.
>
> `--simulation` résout la source et la destination, dit si le dossier existe
> déjà, et **n'écrit rien**. C'est ce chemin-là qu'on soumet, exact, plutôt
> qu'une intention approximative.

**Rien de tout cela n'entre dans un dépôt, ni public ni privé.** Un transcrit
contient l'intégralité de ce qui a été dit : discussions non abouties,
hypothèses fausses, et tout ce que la règle de confidentialité des tiers
écarte. Le dossier daté est un plan de travail, pas une publication. Seule
la **synthèse** peut être reprise, après relecture.

### Le dossier hors dépôt appartient à celui qui l'exploite

`<dépôt>-hors-depot` n'est **pas** une ressource partagée, et rien ici ne le
provisionne. **Il revient à chaque utilisateur de s'assurer que le sien
existe, qu'il est accessible en écriture, et qu'il lui est propre.** Son
contenu n'a de sens que pour lui : relevés de transcrit, et archives locales
des plans produits lors d'un travail assisté par agent.

Trois conséquences à tenir, quel que soit le dépôt :

- **ne jamais le supposer présent** — le résoudre, et le créer au besoin ;
- **ne jamais y écrire ce qui concerne un tiers** sans y avoir appliqué les
  règles de confidentialité du dépôt d'origine ;
- **ne jamais le partager ni le synchroniser** vers un emplacement collectif :
  ce qu'il contient n'a été relu par personne.

## La démarche, en cinq temps

```bash
# 1. Proposer, et attendre.
python .claude/skills/historique/extraire.py --sujet contrib-metier --simulation

# 2 et 3. Une fois le chemin confirmé.
python .claude/skills/historique/extraire.py --sujet contrib-metier
python .claude/skills/historique/extraire.py --sujet revirements \
    --motif "je me suis tromp" --motif "la mesure contredit"
```

**1. Soumettre l'emplacement.** `--simulation` rend le chemin exact sans rien
créer. On le propose, on attend la réponse, et on accepte le nom retenu —
c'est celui sous lequel le dossier sera retrouvé.

**2. Extraire le fil.** Le JSONL est à 97 % de l'appel d'outil ; le texte
seul tient en 900 Kio contre 33 Mio. C'est ce qui rend la fouille possible.

**3. Chercher large, trier ensuite.** Les motifs par défaut couvrent les
tournures de reconnaissance d'un apport. Pour une autre question, passer
`--motif`, répétable.

**4. Relire un par un.** Le comptage automatique sert à **trouver**, jamais
à conclure. Voir les pièges.

**5. Rédiger la synthèse** dans le même dossier, en citant le transcrit
plutôt qu'en le paraphrasant. Une citation datée vaut dix souvenirs.

## Pièges vérifiés le 12/10/2026

**Les retours d'outil arrivent en `role="user"`.** Sans filtre, ils passent
pour des propos du mainteneur et faussent tout « amont ». `extraire.py`
écarte `<system-reminder>`, `Result of calling` et `<task-notification>`.

**La console du poste est en `cp1252`.** Afficher un relevé qui contient un
seul emoji lève une `UnicodeEncodeError` et perd le travail. **Écrire dans
un fichier, lire le fichier** ; ne jamais `print` un extrait brut.

**Le comptage par mot-clé déborde.** Chercher `OMM` ramène « recommande »,
« commit », « comme ». Sur 166 occurrences relevées ce jour-là, la moitié du
volume venait de faux positifs de cette sorte. Le relevé trouve ; l'œil
tranche.

**Le contenu d'un message est tantôt une chaîne, tantôt une liste de blocs**
typés `text`, `tool_use`, `tool_result`, `thinking`. Ne prendre que `text`.

**Corollaire : `extraire.py` ne voit pas les plans, et c'est normal.** Un
plan soumis en mode plan voyage dans un bloc `tool_use`, pas dans un bloc
`text` — le filtre ci-dessus l'écarte donc, à juste titre pour l'usage
visé. Vérifié le 13/10/2026 : le fichier de plan de session est un brouillon
que l'outil réutilise, de sorte qu'un plan écrase le précédent et que le
transcrit en est la **seule** trace. Les retrouver tous demande une
recherche distincte :

```bash
grep -c ExitPlanMode "<le transcrit>.jsonl"   # puis lire input.plan
```

La réponse à chaque appel dit son sort, et trois formes existent —
approbation, refus, et erreur « you are not in plan mode ». Les distinguer
évite d'archiver comme retenu ce qui a été écarté.

## Les deux angles morts de la méthode

À énoncer dans toute synthèse, parce qu'ils biaisent systématiquement.

**Elle ne voit que ce qui a été reconnu sur le moment.** Un apport que je
n'ai pas su identifier alors ne laisse aucune trace à chercher.

**Elle sous-compte ce qui empêche.** Une référence qui a évité un travail,
ou qui a servi d'étalon sans être adoptée, ne produit ni code ni
remerciement — donc rien à relever. C'est exactement ce qui est arrivé à
Unidata, décisif et absent de ma première réponse.

> **Corollaire à dire au mainteneur** : là où il a le sentiment d'avoir
> apporté quelque chose et où le relevé ne le compte pas, il a probablement
> raison. L'absence de trace n'est pas une absence d'apport.
