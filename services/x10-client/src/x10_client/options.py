"""Les décisions que la chaîne prend, rendues lisibles et modifiables.

Chacune de ces options correspond à un choix que `session` faisait **en dur**
avant le 16/10/2026. Les écrire ne change pas le comportement par défaut : ce
sont les mêmes valeurs, désormais nommées, bornées et remplaçables.

**Un modèle plutôt que des `**kwargs`.** Les réglages se lisent en un endroit
avec leurs bornes, se valident à la construction, et se sérialisent dans un
compte rendu si on le veut un jour.

> **Et cinq champs, pas vingt.** Le motif a un mode de ruine connu : l'objet
> d'options absorbe des préoccupations qui n'en sont pas. Relevé le
> 16/10/2026 sur un paquet voisin, `DownloadOptions` y porte vingt et un
> champs dont `notify_webhook` et `notify_email` — la notification n'est pas
> une option de téléchargement. La règle qu'on se donne : **un champ n'entre
> ici que s'il correspond à une décision que la chaîne prend déjà.** Ni cache,
> ni reprise, ni notification : trois fonctions que nous n'avons pas, et les
> déclarer en options ferait croire qu'elles existent.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from x10_connectors.netcdf_cf import COMPRESSION


class NormaliseOptions(BaseModel):
    """Comment traiter un granule, et que faire quand cela se passe mal."""

    model_config = ConfigDict(frozen=True)

    #: Ce qu'on fait d'une étape qui lève.
    #:
    #: `"raise"` est le défaut **de la bibliothèque** : qui appelle
    #: `normalise_granule` directement veut l'exception, avec sa trace.
    #: `"report"` rend un `GranuleReport` en `FAILED` portant la catégorie et
    #: le motif ; c'est ce que `run()` passe, parce que rendre compte est son
    #: métier et qu'un granule fautif ne doit pas emporter les autres.
    errors: Literal["raise", "report"] = "raise"

    #: Ce qu'on fait d'un recouvrement de noms courts, qui fait **disparaître
    #: des champs** au décodage.
    #:
    #: `grib2.open_granule` lève, et c'est juste pour une bibliothèque : une
    #: perte silencieuse est pire qu'un échec. `"tolerate"` reprend la lecture
    #: en mode permissif et **nomme ce qui manque**, verdict `PARTIAL` — un
    #: granule dont le reste est bon vaut mieux que rien. `"raise"` rend la
    #: décision à l'appelant qui préfère s'arrêter.
    dropped_fields: Literal["raise", "tolerate"] = "tolerate"

    #: Écrire les sorties NetCDF, ou s'arrêter au décodage.
    #:
    #: `False` sert l'exploration : un carnet qui veut le contrat et le compte
    #: des champs sans remplir un disque. Le contrat est rendu dans les deux
    #: cas, puisqu'il se calcule sur les jeux décodés et non sur les fichiers.
    write: bool = True

    #: Refuser une unité GRIB sans correspondance UDUNITS, plutôt que de
    #: deviner. Passé à `netcdf_cf.write_netcdf`.
    strict_units: bool = True

    #: Niveau de compression `zlib` des sorties. Le défaut est celui mesuré
    #: par le paquet — facteur 3,4 au niveau 4, le niveau 6 ne gagnant que 2 %
    #: de plus. `0` désactive la compression.
    compress: int = Field(default=COMPRESSION, ge=0, le=9)


#: Les défauts, pour n'avoir pas à construire l'objet quand on n'en change
#: rien. Le modèle étant gelé, une instance unique est sans risque.
DEFAULT_OPTIONS = NormaliseOptions()


__all__ = ["DEFAULT_OPTIONS", "NormaliseOptions"]
