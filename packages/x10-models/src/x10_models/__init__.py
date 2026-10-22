"""Vocabulaire de domaine partagé par les composants X10.

Les noms suivent **DCAT** et **PROV-O** plutôt qu'une invention maison. Ces
standards distinguent depuis longtemps ce que notre premier modèle confondait :
qui produit une information, qui la diffuse, qui la ré-expose, et d'où vient ce
qu'on a effectivement récupéré.

| Notion | Terme normalisé repris ici |
|---|---|
| producteur | `dcterms:creator` — `Dataset.producer` |
| diffuseur | `dcterms:publisher` — `Distribution.publisher` |
| accès concret, un par diffuseur | `dcat:Distribution` |
| lignage d'acquisition | `prov:Entity` / `Activity` / `Agent` — `Retrieval` |

Aucune sérialisation RDF n'est imposée : un export DCAT ou STAC reste possible
sans rien reprendre du modèle.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

#: Rôles d'un acteur. Vocabulaire fermé, délibérément : un champ libre se
#: dégrade en texte que personne ne peut plus agréger.
#:
#: Réunit les rôles de STAC et ceux d'INSPIRE, chacun conservant l'orthographe
#: de sa source — camelCase pour INSPIRE, dont la codelist est gouvernée au
#: niveau « Legal (EU) ». Voir `docs/vocabulaire.md` pour la correspondance.
#:
#: `producer` est notre terme canonique pour « a créé la ressource » ; il
#: s'exporte vers `originator` (INSPIRE) et `dcterms:creator` (DCAT). Ne pas
#: ajouter `originator` : deux termes pour un concept invitent l'incohérence.
AgentRole = Literal[
    # STAC
    "producer",
    "licensor",
    "harvester",
    # communs à STAC et INSPIRE
    "publisher",
    "processor",
    # INSPIRE — https://inspire.ec.europa.eu/metadata-codelist/ResponsiblePartyRole
    "distributor",
    "custodian",
    "owner",
    "user",
    "author",
    "resourceProvider",
    "pointOfContact",
    "principalInvestigator",
]

#: Restrictions d'accès public, codelist INSPIRE renvoyant aux alinéas de
#: l'article 13 de la directive.
#: https://inspire.ec.europa.eu/metadata-codelist/LimitationsOnPublicAccess
#:
#: **À ne pas confondre avec la licence.** INSPIRE sépare les conditions
#: d'usage — la licence — des motifs juridiques de restriction d'accès, et
#: DCAT fait de même avec `dcterms:license` et `dcterms:accessRights`.
AccessRights = Literal[
    "noLimitations",
    "INSPIRE_Directive_Article13_1a",
    "INSPIRE_Directive_Article13_1b",
    "INSPIRE_Directive_Article13_1c",
    "INSPIRE_Directive_Article13_1d",
    "INSPIRE_Directive_Article13_1e",
    "INSPIRE_Directive_Article13_1f",
    "INSPIRE_Directive_Article13_1g",
    "INSPIRE_Directive_Article13_1h",
]

#: Les quatre domaines physiques du périmètre.
PhysicalDomain = Literal["geo", "hydro", "oceano", "meteo"]


class Agent(BaseModel):
    """Acteur intervenant sur une donnée, et ce qu'il y fait.

    Un même organisme peut cumuler des rôles : ECMWF produit les sorties IFS
    *et* les diffuse, tout en en étant le concédant de licence.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    roles: tuple[AgentRole, ...] = Field(min_length=1)
    url: str | None = None


class Variable(BaseModel):
    """Une grandeur d'un jeu, **dans le vocabulaire normalisé et lui seul**.

    C'est la vue que X10 engage : les noms viennent de CF, les unités de la
    forme canonique d'UDUNITS. Rien du producteur n'entre ici — ni nom court,
    ni `typeOfLevel` d'ecCodes, ni triplet GRIB. Ces termes-là vivent dans
    `SourceTerms`, et un test interdit leur présence ici.

    **La raison tient en une phrase** : un consommateur qui s'accroche à un
    nom de producteur hérite de notre couplage à ce producteur. La vue
    normalisée existe pour qu'il n'ait pas à le faire.

    `standard_name` peut valoir `None`, et c'est assumé. CF ne couvre pas
    tout — `grib2.WITHOUT_CF_NAME` recense ce qui lui échappe —, et la règle
    arrêtée est **retirer plutôt que renommer** : une grandeur sans nom
    standard se voit comme telle, au lieu de porter une supposition. Sans
    cette soupape, un seul code exotique rendrait un jeu entier inexposable.
    """

    model_config = ConfigDict(frozen=True)

    #: Nom standard CF. `None` quand CF ne couvre pas la grandeur.
    standard_name: str | None = None
    #: Unité sous la forme canonique d'UDUNITS — `m s-1`, pas `m s**-1`.
    units: str | None = None
    #: Traitement statistique, vocabulaire CF — `time: sum`, `time: maximum`.
    cell_methods: str | None = None
    #: Référence verticale par son **nom standard CF** — `height`,
    #: `air_pressure` —, et non par le `typeOfLevel` du producteur.
    level_reference: str | None = None
    levels: tuple[float, ...] = ()
    level_units: str | None = None
    #: Nombre de membres, quand la grandeur vient d'une prévision
    #: d'ensemble. `None` pour un déterministe — et c'est une distinction,
    #: pas une valeur manquante : un champ déterministe n'a pas un membre,
    #: il n'a pas d'axe de membres.
    #:
    #: Le nom vient de CF, qui appelle `realization` l'axe d'un ensemble.
    #: C'est un **compte** et non la liste des numéros : le catalogue
    #: répond à « ce jeu est-il un ensemble, et de quelle taille », pas à
    #: « quel est le quarante-deuxième membre », qui se lit dans la donnée.
    realizations: int | None = None


class SourceTerms(BaseModel):
    """Les termes tels que la chaîne de décodage les rend. **Aucune stabilité promise.**

    > Cette vue ne promet **rien, par construction, puisqu'elle suit sa
    > source**. Si le vocabulaire amont change, elle change — c'est son objet.
    > Qui l'interroge accepte ce régime en l'interrogeant.

    **Correction du 22/10/2026 : « les termes du producteur » était faux, et
    ses exemples étaient des contre-exemples.** Ni Météo-France ni l'OMM ne
    nomment `t2m` : la table 4.2 ne porte aucune colonne d'abréviation, le
    message GRIB déclare `2t`, et `t2m` est le `cfVarName` qu'ecCodes en
    dérive — identique sous les quatre centres essayés, donc **indépendant du
    producteur**. La vue suit donc le vocabulaire d'**ecCodes**, ce qui ne la
    rend pas moins utile mais désigne le bon responsable d'un changement.

    Elle existe pour l'usage expert : savoir demander « `t2m` d'AROME 0,025° »
    quand on connaît déjà la source. Elle n'est **pas encore exposée** par une
    interface d'interrogation ; les termes sont dérivés et rangés dès la
    première passe parce que décoder le corpus est l'étape coûteuse, et la
    refaire plus tard pour cela seul serait du gâchis.

    À ne pas confondre avec le contrat de sortie de `x10-connectors`, qui
    porte aussi l'identité GRIB : celui-là est une **trace** qui constate
    qu'une source a changé, celui-ci un **vocabulaire d'interrogation**.
    """

    model_config = ConfigDict(frozen=True)

    #: Nom de la variable tel que la chaîne de décodage la nomme — `t2m`,
    #: `u10`. C'est le `cfVarName` d'ecCodes, et c'est sous ce nom que la
    #: grandeur apparaît dans nos fichiers NetCDF.
    short_name: str = Field(min_length=1)
    #: Nom court que les tables résolvent — `2t`, `10u`. C'est l'idiome de
    #: qui interroge une archive GRIB, et il diffère du précédent 949 fois
    #: sur 6 566 paramètres. **Ni l'un ni l'autre n'est une abréviation du
    #: producteur** : l'OMM n'en publie aucune, et le nom court n'est pas
    #: dans le message — c'est une clé que la bibliothèque calcule, et
    #: qu'elle a déjà renommée (ECC-2128, septembre 2025).
    #:
    #: `None` quand les tables ne résolvent pas le paramètre : la sentinelle
    #: `unknown` d'ecCodes n'est pas un nom, et la publier en serait un faux.
    grib_short_name: str | None = None
    #: Type de niveau dans le vocabulaire d'ecCodes — `heightAboveGround`.
    level_type: str | None = None
    #: Identité du champ chez le producteur, reprise telle quelle.
    grib: dict[str, str] = Field(default_factory=dict)


class InventorySource(BaseModel):
    """Sous quoi un inventaire a été dérivé. **Datée, et c'est le point.**

    À ne pas confondre avec `Retrieval`, qui dit d'où vient la **donnée**.
    Celle-ci dit d'où vient notre **lecture** de la donnée.

    Un inventaire dérivé de fichiers vaut pour une version d'outillage, une
    version de tables déclarée par le producteur, et un état du jeu à une
    date. Les standards bougent — l'OMM a réécrit quatre entrées en place en
    mai 2025, sans mécanisme de dépréciation — et les producteurs ne les
    suivent pas au même rythme : notre ecCodes connaît les tables jusqu'à la
    37 quand AROME en déclare 15.

    Sans ces quatre champs, une divergence future serait **inattribuable** :
    impossible de dire si le producteur a bougé ou si notre outillage a
    changé.
    """

    model_config = ConfigDict(frozen=True)

    derived_at: datetime
    #: La chaîne qui a lu — `"eccodes 2.49.0"`.
    toolchain: str = Field(min_length=1)
    #: Version de tables maîtresses **déclarée par le producteur**.
    tables_version: int | None = None
    #: Empreintes des granules dérivés, pour pouvoir rejouer à l'identique.
    granules: tuple[str, ...] = ()


class Dataset(BaseModel):
    """Information logique, indépendante de tout moyen d'accès.

    « Température à 2 m, IFS 0.25° » existe qu'on la télécharge ou non. Les
    moyens de l'obtenir sont des `Distribution`.
    """

    model_config = ConfigDict(frozen=True)

    identifier: str = Field(min_length=1)
    title: str = Field(min_length=1)
    #: `dcterms:creator` — qui a créé la ressource. `originator` sous INSPIRE.
    producer: Agent
    #: `dcterms:publisher` — qui l'a publiée. DCAT porte cette propriété sur la
    #: ressource, donc ici et non sur la distribution. Souvent le producteur.
    publisher: Agent | None = None
    domain: PhysicalDomain
    #: L'inventaire **normalisé**, celui qu'on expose.
    variables: tuple[Variable, ...] = ()
    #: Les mêmes grandeurs dans les termes du producteur, dans l'ordre de
    #: `variables`. Vide tant que la vue source n'est pas dérivée.
    source_terms: tuple[SourceTerms, ...] = ()
    #: Échéance maximale servie, en heures. **Capacité du jeu**, statique —
    #: à ne pas confondre avec la présence d'un réseau donné, que dit
    #: l'historique d'exécution et non le catalogue.
    max_step_hours: int | None = Field(default=None, ge=0)
    #: Sous quoi l'inventaire a été dérivé. `None` quand il est saisi à la main.
    inventory_source: InventorySource | None = None


class Distribution(BaseModel):
    """Accès concret à un `Dataset`, chez un diffuseur donné.

    **Une distribution par origine**, et non une distribution à plusieurs URL :
    chacune porte sa priorité et sa licence, ce sur quoi s'appuie la politique
    de résolution. Des miroirs du même fichier restent des distributions
    distinctes.

    La licence figure ici et pas seulement sur le `Dataset` : un ré-exposant
    peut ajouter ses propres conditions à celles du producteur.
    """

    model_config = ConfigDict(frozen=True)

    dataset: str = Field(min_length=1)
    origin: str = Field(min_length=1)
    #: **Extension X10.** DCAT ne porte aucun agent sur une `Distribution` —
    #: `dcterms:publisher` appartient à la ressource. Or une distribution par
    #: origine n'a de sens que si l'on sait qui la sert. Les rôles de l'agent
    #: portent la précision : `distributor` pour un miroir, `resourceProvider`
    #: pour un fournisseur, `publisher` quand c'est l'éditeur lui-même.
    provider: Agent
    #: `dcat:accessURL`
    access_url: str = Field(min_length=1)
    #: `dcat:mediaType`
    media_type: str = Field(min_length=1)
    #: `dcterms:license` — les conditions d'usage.
    license: str = Field(min_length=1)
    #: `dcterms:accessRights` — les restrictions juridiques d'accès, distinctes
    #: de la licence. Sans objet pour de l'open data, essentiel dès qu'une
    #: source est à diffusion restreinte.
    access_rights: AccessRights = "noLimitations"
    #: Plus la valeur est basse, plus l'origine est préférée.
    priority: int = Field(default=100, ge=0)


class Retrieval(BaseModel):
    """Lignage d'une acquisition, structuré comme PROV-O.

    Répond à « d'où vient ce fichier » : les artefacts produits (`prov:Entity`),
    quand (`prov:Activity`), depuis quelle distribution (`prov:used`), et par
    quel agent (`prov:wasAssociatedWith`).

    `origin` porte l'origine **effectivement retenue**, qui peut différer de
    celle demandée si une bascule a eu lieu.

    Le lignage de transformation — `prov:wasDerivedFrom` — n'est pas modélisé :
    rien n'est encore transformé, et le concevoir sans dérivation à décrire
    serait spéculatif.
    """

    model_config = ConfigDict(frozen=True)

    artefacts: tuple[Path, ...] = ()
    retrieved_at: datetime
    dataset: str = Field(min_length=1)
    origin: str = Field(min_length=1)
    selection: dict[str, Any] = Field(default_factory=dict)
    #: Agent responsable, avec sa version : `x10-connectors 0.1.0`.
    agent: str = Field(min_length=1)
    license: str | None = None


class GeoPoint(BaseModel):
    """Position géographique en WGS84."""

    model_config = ConfigDict(frozen=True)

    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    elevation_m: float | None = None


class Provenance(BaseModel):
    """Attribution légère portée par une **valeur** de donnée.

    À ne pas confondre avec `Retrieval`, qui décrit l'acquisition d'un
    **artefact**. Les deux répondent à des questions différentes : « à qui cette
    valeur est-elle attribuée » et « comment ce fichier est-il arrivé ». Un
    `Retrieval` peut produire la `Provenance` des valeurs qui en dérivent.
    """

    model_config = ConfigDict(frozen=True)

    source_name: str = Field(min_length=1)
    source_url: str | None = None
    retrieval_time: datetime | None = None
    license: str | None = None


class Observation(BaseModel):
    """Mesure ponctuelle d'une variable, horodatée et localisée.

    Réservé aux séries ponctuelles (stations, bouées). Les champs maillés
    (GRIB/NetCDF) restent dans des tableaux ; voir CLAUDE.md.
    """

    model_config = ConfigDict(frozen=True)

    variable: str = Field(min_length=1)
    value: Decimal
    unit: str = Field(min_length=1)
    timestamp: datetime
    location: GeoPoint
    provenance: Provenance | None = None


__all__ = [
    "AccessRights",
    "Agent",
    "AgentRole",
    "Dataset",
    "Distribution",
    "GeoPoint",
    "InventorySource",
    "Observation",
    "PhysicalDomain",
    "Provenance",
    "Retrieval",
    "SourceTerms",
    "Variable",
]
