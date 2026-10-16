"""Registre des sources et politique de résolution d'origine.

Le vocabulaire — `Dataset`, `Distribution`, `Agent` — vit dans `x10-models` :
ce sont des modèles de domaine. Ce paquet porte le **registre** et le
**comportement** de résolution, qui ne sont pas des types.

La règle de dépendance est ainsi préservée : `x10-connectors` ne dépend que de
`x10-models` et n'a jamais besoin du catalogue. C'est l'appelant qui résout une
entrée et transmet au connecteur l'ordre des origines à tenter.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from x10_models import Dataset, Distribution, PhysicalDomain, Variable


class CatalogEntry(BaseModel):
    """Lie une information logique aux moyens concrets de l'obtenir.

    Plusieurs distributions pour un même jeu portent l'exigence de
    **redondance** : une information reste accessible quand un diffuseur est
    indisponible.
    """

    model_config = ConfigDict(frozen=True)

    dataset: Dataset
    distributions: tuple[Distribution, ...] = Field(min_length=1)
    tags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _distributions_se_rapportent_au_jeu(self) -> CatalogEntry:
        """Une distribution d'un autre jeu dans cette entrée serait une erreur
        de saisie silencieuse, et la résolution livrerait la mauvaise donnée."""
        etrangeres = sorted(
            {d.origin for d in self.distributions if d.dataset != self.dataset.identifier}
        )
        if etrangeres:
            raise ValueError(
                f"Distributions that do not refer to {self.dataset.identifier!r}: "
                f"{', '.join(etrangeres)}"
            )
        return self

    @model_validator(mode="after")
    def _origines_distinctes(self) -> CatalogEntry:
        """Deux distributions de même origine rendraient l'ordre ambigu."""
        origines = [d.origin for d in self.distributions]
        if len(set(origines)) != len(origines):
            raise ValueError("Two distributions cannot share the same origin.")
        return self

    def resolution_order(self) -> tuple[Distribution, ...]:
        """Distributions à tenter, de la plus préférée à la moins.

        Le tri secondaire sur l'origine rend l'ordre **déterministe** même à
        priorités égales : sans lui, deux exécutions pourraient diverger.
        """
        return tuple(sorted(self.distributions, key=lambda d: (d.priority, d.origin)))

    def origins(self) -> tuple[str, ...]:
        """Noms des origines dans l'ordre de résolution, à passer au connecteur."""
        return tuple(d.origin for d in self.resolution_order())


class Query(BaseModel):
    """Les contraintes accumulées d'une interrogation, dans le vocabulaire
    **normalisé**.

    **Un raffinement progressif, pas une recherche.** Le besoin réel ressemble
    à : « la température de surface » — trois jeux la servent — « à quelle
    échéance ? » — « à sept jours » — deux jeux restent. Une requête est donc
    un objet qu'on **resserre**, et `Registry.facets()` dit ce qui demeure
    ouvert sur l'axe suivant.

    Gelée : resserrer rend une nouvelle requête, de sorte qu'un dialogue
    puisse revenir en arrière sans avoir à défaire quoi que ce soit.
    """

    model_config = ConfigDict(frozen=True)

    standard_name: str | None = None
    level_reference: str | None = None
    level: float | None = None
    #: Échéance voulue, en heures. Retient les jeux qui vont **au moins**
    #: jusque-là — une capacité, pas une disponibilité du moment.
    step_hours: int | None = None
    domain: PhysicalDomain | None = None

    def narrow(self, **contraintes: object) -> Query:
        """Resserre la requête, et rend la nouvelle."""
        return self.model_copy(update=contraintes)


#: Axes sur lesquels on sait rendre les valeurs encore ouvertes. Vocabulaire
#: **fermé** : un axe libre se dégraderait en chaîne que personne ne peut plus
#: agréger, et un nom mal orthographié rendrait une liste vide sans le dire.
#:
#: Le jour où la vue source s'ouvrira, elle ajoutera ses propres axes ici —
#: `short_name`, `level_type` — sans rien changer au mécanisme.
FACET_AXES = ("standard_name", "level_reference", "level", "domain", "producer")


class Registry(BaseModel):
    """La collection d'entrées, et l'interrogation. Un `dcat:Catalog`.

    `CatalogEntry` décrit une entrée ; ce registre est le conteneur qui
    manquait, et c'est lui qui porte le **comportement** — enregistrer,
    chercher, résoudre.

    **Gelé et fonctionnel** : `register` rend un nouveau registre plutôt que
    de muter celui-ci. Un registre partagé et mutable serait un état que rien
    n'exige, et deux appelants y liraient des choses différentes selon
    l'ordre.
    """

    model_config = ConfigDict(frozen=True)

    entries: tuple[CatalogEntry, ...] = ()

    @model_validator(mode="after")
    def _identifiants_uniques(self) -> Registry:
        """Deux entrées homonymes rendraient `get` ambigu, donc faux."""
        identifiants = [e.dataset.identifier for e in self.entries]
        doublons = sorted({i for i in identifiants if identifiants.count(i) > 1})
        if doublons:
            raise ValueError(f"Duplicate dataset identifiers: {', '.join(doublons)}")
        return self

    # --- Tenir le registre ----------------------------------------------------

    def register(self, entry: CatalogEntry) -> Registry:
        """Rend un nouveau registre portant cette entrée de plus."""
        return Registry(entries=(*self.entries, entry))

    def get(self, identifier: str) -> CatalogEntry | None:
        """L'entrée d'un jeu, ou `None`.

        **Ne lève pas** : demander si une source est connue est une question
        légitime, et une exception obligerait tout appelant à l'entourer.
        """
        for entry in self.entries:
            if entry.dataset.identifier == identifier:
                return entry
        return None

    def origins(self, identifier: str) -> tuple[str, ...]:
        """Origines à tenter pour ce jeu, dans l'ordre de résolution.

        Réutilise `CatalogEntry.resolution_order()`. C'est ce qu'un connecteur
        attend — il ignore le catalogue, et c'est l'appelant qui lui transmet
        cet ordre.
        """
        entry = self.get(identifier)
        return entry.origins() if entry is not None else ()

    # --- Interroger -----------------------------------------------------------

    def matches(self, query: Query) -> tuple[CatalogEntry, ...]:
        """Les entrées qui satisfont **toutes** les contraintes posées."""
        return tuple(e for e in self.entries if _satisfait(e, query))

    def facets(self, query: Query, axis: str) -> tuple[Any, ...]:
        """Les valeurs encore ouvertes sur un axe, vu les contraintes posées.

        C'est la pièce qui porte le dialogue : après « la température de
        surface », `facets(query, "level")` dit quels niveaux restent
        atteignables, et non tous ceux qui existent.

        L'axe contraint est **exclu de sa propre contrainte** : demander les
        niveaux disponibles alors qu'on en a déjà fixé un rendrait une liste
        d'un élément, ce qui n'aide personne à choisir.
        """
        if axis not in FACET_AXES:
            connus = ", ".join(FACET_AXES)
            raise ValueError(f"Unknown facet axis {axis!r}. Expected one of {connus}.")

        contraignable = axis in type(query).model_fields
        ouverte = query.model_copy(update={axis: None}) if contraignable else query
        valeurs: set[Any] = set()
        for entry in self.matches(ouverte):
            if axis == "domain":
                valeurs.add(entry.dataset.domain)
            elif axis == "producer":
                valeurs.add(entry.dataset.producer.name)
            else:
                for variable in entry.dataset.variables:
                    if not _variable_satisfait(variable, ouverte):
                        continue
                    if axis == "level":
                        valeurs.update(variable.levels)
                    else:
                        valeur = getattr(variable, axis)
                        if valeur is not None:
                            valeurs.add(valeur)
        return tuple(sorted(valeurs, key=str))

    # --- Charger et exporter --------------------------------------------------

    @classmethod
    def from_file(cls, source: Path) -> Registry:
        """Charge un registre depuis son JSON.

        L'inventaire est **engendré** depuis des fichiers réels ; sa place est
        en données, pas en source Python. En JSON il se relit en revue, et un
        `git diff` montre exactement ce qu'un producteur a changé.
        """
        return cls.model_validate(json.loads(source.read_text(encoding="utf-8")))

    def to_json(self) -> str:
        """Rendu déterministe, destiné à être versionné et relu.

        Clés triées et indentation fixe, comme le contrat de sortie : deux
        dérivations sur les mêmes fichiers donnent le même texte.
        """
        return json.dumps(
            self.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False
        )

    def to_records(self) -> tuple[dict[str, Any], ...]:
        """Export au format **OGC API - Records**, dont WCMP2 est l'extension
        de l'OMM.

        Ce n'est pas une prétention de conformité complète : c'est la garantie
        que notre modèle **n'empêche pas** l'export, vérifiée plutôt
        qu'affirmée. Les champs obligatoires d'un enregistrement — `id`,
        `type`, `time`, `properties`, `links` — sont présents et typés.

        STAC n'est pas la cible : sa spécification impose un `host` unique, ce
        qui exclut notre redondance d'origines.
        """
        records = []
        for entry in self.entries:
            jeu = entry.dataset
            records.append(
                {
                    "id": jeu.identifier,
                    "type": "Feature",
                    "geometry": None,
                    "time": None,
                    "properties": {
                        "title": jeu.title,
                        "type": "dataset",
                        "themes": [{"concepts": [{"id": jeu.domain}]}],
                        "contacts": [
                            {"name": jeu.producer.name, "roles": list(jeu.producer.roles)}
                        ],
                        "keywords": sorted(
                            v.standard_name for v in jeu.variables if v.standard_name
                        ),
                    },
                    "links": [
                        {
                            "href": d.access_url,
                            "rel": "item",
                            "type": d.media_type,
                            "title": d.origin,
                        }
                        for d in entry.resolution_order()
                    ],
                }
            )
        return tuple(records)


def _variable_satisfait(variable: Variable, query: Query) -> bool:
    """Une grandeur répond-elle aux contraintes qui la concernent ?"""
    if query.standard_name is not None and variable.standard_name != query.standard_name:
        return False
    if query.level_reference is not None and variable.level_reference != query.level_reference:
        return False
    return not (query.level is not None and query.level not in variable.levels)


def _satisfait(entry: CatalogEntry, query: Query) -> bool:
    """Une entrée répond-elle à toutes les contraintes ?"""
    jeu = entry.dataset
    if query.domain is not None and jeu.domain != query.domain:
        return False
    # Une capacité d'echeance inconnue ne disqualifie pas : on ne sait pas,
    # donc on n'affirme pas. C'est a l'appelant de trancher sur un jeu non
    # renseigne plutot qu'a nous de le masquer.
    if (
        query.step_hours is not None
        and jeu.max_step_hours is not None
        and jeu.max_step_hours < query.step_hours
    ):
        return False
    if query.standard_name is None and query.level_reference is None and query.level is None:
        return True
    return any(_variable_satisfait(v, query) for v in jeu.variables)


__all__ = ["CatalogEntry", "Query", "Registry"]
