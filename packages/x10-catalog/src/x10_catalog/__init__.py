"""Registre des sources et politique de résolution d'origine.

Le vocabulaire — `Dataset`, `Distribution`, `Agent` — vit dans `x10-models` :
ce sont des modèles de domaine. Ce paquet porte le **registre** et le
**comportement** de résolution, qui ne sont pas des types.

La règle de dépendance est ainsi préservée : `x10-connectors` ne dépend que de
`x10-models` et n'a jamais besoin du catalogue. C'est l'appelant qui résout une
entrée et transmet au connecteur l'ordre des origines à tenter.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from x10_models import Dataset, Distribution


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
                f"Distributions ne se rapportant pas à {self.dataset.identifier!r} : "
                f"{', '.join(etrangeres)}"
            )
        return self

    @model_validator(mode="after")
    def _origines_distinctes(self) -> CatalogEntry:
        """Deux distributions de même origine rendraient l'ordre ambigu."""
        origines = [d.origin for d in self.distributions]
        if len(set(origines)) != len(origines):
            raise ValueError("Deux distributions ne peuvent pas partager la même origine.")
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


__all__ = ["CatalogEntry"]
