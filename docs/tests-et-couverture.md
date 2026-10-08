# Tests et couverture

Comment la suite de tests est organisée, pourquoi elle l'est ainsi, et ce
qu'on attend d'une contribution. Destiné à qui écrit ou modifie du code dans
ce dépôt.

## Deux principes

**La suite par défaut ne touche pas le réseau.** Une suite qui dépend d'un
service tiers échoue quand ce service est lent, en maintenance ou
indisponible, et l'échec n'apprend alors rien sur le code. Elle doit tourner
dans un train, sur une machine coupée du monde, et donner le même verdict.

**Aucune donnée binaire n'est commise.** Les jeux de données du domaine se
comptent en centaines de mégaoctets ; en figer un fragment dans l'historique
alourdirait chaque clone à jamais, pour un échantillon qui vieillirait aussi
vite que la source.

Ces deux principes ont une conséquence commune : **les tests fabriquent ce
dont ils ont besoin**.

## Deux couches de tests

| Couche | Marqueur | Exécutée par défaut | Ce qu'elle vérifie |
|---|---|---|---|
| Hors ligne | aucun | oui | toute la logique : sélection, décodage, normalisation, journalisation, garde-fous |
| Service réel | `network` | **non** | que la source répond, et que nos hypothèses sur elle tiennent encore |

La seconde couche n'est pas facultative pour autant : elle est ce qui
détecte qu'un producteur a changé son format ou son organisation. Elle se
lance délibérément, pas à chaque sauvegarde de fichier.

```bash
uv run pytest                 # hors ligne, par defaut
uv run pytest -m network      # atteint les services reels
```

Un test qui ouvre une connexion **doit** porter `@pytest.mark.network`. Sans
cela il casse la première promesse, et son échec en intégration continue sera
mis sur le compte du code.

## Les fichiers GRIB2 se fabriquent

`packages/x10-connectors/tests/fixtures_grib.py` construit des messages GRIB2
valides **en mémoire**, par ecCodes. Sur une grille de neuf points sur cinq,
un message pèse environ trois cents octets et un paquet multi-messages
quelques kilo-octets — face aux 50 Mo à 3,6 Go d'un paquet réel.

Ils ne sont pas des maquettes : ce sont de vrais GRIB2, que la chaîne de
décodage lit comme les autres, avec leur sémantique complète — nom court,
unité, type de niveau, échéance.

Les cinq difficultés rencontrées sur les fichiers réels s'y reproduisent à
la demande :

| Difficulté | Comment la fabriquer |
|---|---|
| Valeurs manquantes, en proportion variable selon le champ | `Champ(manquants=7)` |
| Cumul, gabarit de produit distinct de l'instantané | `Champ(accumulation=1)` |
| Types de niveau mêlés dans un même fichier | plusieurs `Champ(level_type=...)` |
| Longitudes en 0 à 360, que le format impose | la grille par défaut est à cheval sur Greenwich |
| Empaquetage CCSDS, celui de la production | c'est le **défaut**, `Champ(packing=...)` pour en changer |

### L'empaquetage, et pourquoi il est le défaut

Relevé le 08/10/2026 : un paquet AROME réel encode sa section de données en
**CCSDS, gabarit 5.42**, comme les données ouvertes de l'ECMWF. L'échantillon
d'ecCodes produit du `grid_simple`, gabarit 5.0 — que la production n'emploie
pas. Les fixtures n'exerçaient donc pas le chemin que le décodage rencontre
vraiment.

CCSDS est désormais le défaut : un message complet pèse 244 octets, 254 avec
sept valeurs manquantes, et toute la suite s'en trouve exercée contre
l'empaquetage réel sans qu'aucun fichier ne soit commis.

**Deux pièges, tous deux couverts par `test_packing.py`.** `grid_second_order`
est accepté par ecCodes **sans être appliqué** : le message produit un
`grid_simple`, et une fixture qui ne relit pas se croirait en train de tester
autre chose — la fabrique relit donc et refuse. Et les empaquetages complexes
**recalculent** `bitsPerValue` par groupe au lieu de l'honorer : 11 et 6 bits
là où 12 étaient demandés, ce qui en fait une sortie et non une consigne.

La précision de quantification est réglable — `Champ(bits=12)`, la valeur des
fichiers réels — ce qui permet de mesurer une perte réelle plutôt
qu'idéalisée. C'est ainsi que la reconstitution du vent depuis ses
composantes a pu être vérifiée.

## La couverture, en deux vues

### Pourquoi un seuil unique ne convient pas

Une partie du code n'est atteignable que par le réseau : l'implémentation
HTTP du connecteur Météo-France et le fabricant de client ECMWF. La suite par
défaut ne l'exécute pas, **par construction**.

Un seuil global est alors mal posé dans les deux sens. Haut, il sanctionne
une exclusion délibérée et pousse à écrire des simulacres sans valeur. Bas,
il ne se déclenche qu'après un effondrement, et ne protège donc rien au
quotidien.

### La solution : deux lectures d'une même mesure

Les exclusions de coverage.py s'appliquent **au rapport et non à la mesure**.
Un seul passage de tests produit donc deux chiffres selon la façon dont on le
relit.

| Vue | Fichier | Exclut le code réseau | Rôle |
|---|---|---|---|
| Informative | `pyproject.toml` | non | affiche le taux réel, sans rien masquer |
| Barrière | `.coveragerc-offline` | oui | porte le seuil de **90 %** |

Au 08/10/2026 : **93 %** en vue informative, **96 %** en vue barrière. La
couverture est mesurée **par branches**, plus stricte que par lignes, parce
que ce sont les conditionnelles non éprouvées qui comptent — bascule
d'origine, repli de réseau.

### Le marqueur, et le piège à ne pas reproduire

Le code atteignable seulement par le réseau porte, sur la ligne qui introduit
le bloc :

```python
class TransportHttp:  # couvert par les tests reseau
```

**Ce marqueur ne doit jamais contenir `pragma: no cover`.** Les exclusions
par défaut de coverage.py reconnaissent cette formule : le code disparaîtrait
alors des **deux** vues, y compris de celle dont le seul rôle est de montrer
l'écart. Le chiffre affiché monterait, et la couverture deviendrait un
indicateur de confort.

```bash
# Taux reel, et rapport navigable dans htmlcov/
uv run pytest --cov --cov-report=term-missing:skip-covered --cov-report=html

# Barriere : seuil sur le code atteignable hors ligne
uv run coverage report --rcfile=.coveragerc-offline
```

Sous VSCode, la tâche **« Couverture »** enchaîne les deux, dans le même
ordre qu'en intégration continue — un échec local est donc un échec de CI.

## Ce qu'on attend d'une contribution

- **Un test qui atteint un service distant porte `@pytest.mark.network`.**
- **Aucun fichier de données n'est ajouté au dépôt.** Si un cas réclame une
  forme de fichier qui n'existe pas encore, elle s'ajoute à
  `fixtures_grib.py`.
- **Du code atteignable seulement par le réseau porte le marqueur de
  couverture**, afin que la barrière continue de mesurer ce qu'elle prétend
  mesurer.
- **La barrière reste franchie.** Elle a six points de marge ; du code non
  testé les consomme, et c'est son rôle.
- **Les portes de qualité passent** : `ruff check`, `ruff format --check`,
  `mypy --strict`, et la suite hors ligne. La tâche VSCode **« Portes de
  qualité »** les enchaîne.

## Pourquoi pas de service de couverture en ligne

La barrière est locale et le rapport part en artefact de l'intégration
continue. Aucun jeton, aucune action tierce supplémentaire dans la chaîne
d'approvisionnement — le dépôt épingle ses actions par empreinte et restreint
son jeton, il serait incohérent d'y ajouter un téléverseur sans nécessité.

La question se repose à la publication de la 1.0.0 : les courbes de tendance
et le commentaire de couverture différentielle sur les demandes de fusion
prennent leur sens quand le projet a une histoire et plusieurs contributeurs.
