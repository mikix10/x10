"""L'assemblage : acquérir, décoder, normaliser, écrire, contracter.

Cet enchaînement n'existait jusqu'ici **que dans du code de test**. Ce module
lui donne un domicile — il ne le retire pas aux tests, qui doivent continuer
d'exercer la chaîne au niveau des paquets, sans ce client.

**Rien ici n'est de la logique de domaine.** Pas une unité convertie, pas un
nom résolu, pas une borne calculée : tout cela appartient aux paquets. Ce
module appelle, configure, et rend compte.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from x10_connectors import BaseConnector, ConnectorResult, contract, grib2, netcdf_cf
from x10_models import Retrieval

from .config import Settings
from .report import (
    GranuleReport,
    PipelineReport,
    Verdict,
    empreinte_de_contrat,
)

#: Correspondance requête → connecteur, résolue **paresseusement**.
#: L'import d'`EcmwfIfsOpenDataConnector` tire le client officiel, qui est un
#: extra : le résoudre au chargement du module rendrait le client
#: ininstallable sans lui.
_CONNECTEURS = {
    "MeteoFrancePntRequest": ("meteofrance_pnt", "MeteoFrancePntConnector"),
    "EcmwfIfsRequest": ("ecmwf_ifs", "EcmwfIfsOpenDataConnector"),
}


class RequeteInconnue(TypeError):
    """Aucun connecteur ne correspond à cette requête."""


#: Les deux connecteurs héritent de `BaseConnector` mais **ne partagent pas
#: de signature de construction** : la classe de base définit le comportement,
#: pas l'instanciation. `type[BaseConnector]` mentirait donc ; un appelable
#: rendant un connecteur dit exactement ce qu'on sait.
FabriqueDeConnecteur = Callable[..., BaseConnector]


def _connecteur_pour(requete: object) -> FabriqueDeConnecteur:
    nom = type(requete).__name__
    if nom not in _CONNECTEURS:
        connus = ", ".join(sorted(_CONNECTEURS))
        raise RequeteInconnue(f"{nom} : aucun connecteur connu. Attendu l'un de {connus}.")
    import importlib

    module_nom, classe = _CONNECTEURS[nom]
    module = importlib.import_module(f"x10_connectors.{module_nom}")
    fabrique: FabriqueDeConnecteur = getattr(module, classe)
    return fabrique


@dataclass(frozen=True)
class Session:
    """Une configuration résolue, et les opérations qu'elle permet."""

    settings: Settings

    @classmethod
    def from_env(cls, environnement: dict[str, str] | None = None) -> Session:
        return cls(settings=Settings.from_env(environnement))

    # --- Acquisition ---------------------------------------------------------

    def acquire(self, requete: object) -> ConnectorResult:
        """Télécharge, et rien de plus. Le compte rendu est celui du paquet."""
        self.settings.destination.mkdir(parents=True, exist_ok=True)
        fabrique = _connecteur_pour(requete)
        supplement = (
            {"max_bytes": self.settings.max_bytes} if self.settings.max_bytes is not None else {}
        )
        connecteur = fabrique(self.settings.destination, requete, **supplement)
        resultat: ConnectorResult = connecteur.fetch()
        return resultat

    # --- Normalisation -------------------------------------------------------

    def _traiter(self, source: Path, retrieval: Retrieval | None = None) -> GranuleReport:
        """Décode, normalise, écrit et contracte **un** granule.

        **Le client rend compte, il ne refuse pas.** `open_granule` lève par
        défaut quand des champs se recouvrent au nommage, et c'est juste pour
        une bibliothèque : une perte silencieuse est pire qu'un échec. Mais
        le grain de l'arbitrage appartient à l'appelant, et ici l'appelant
        est un client dont le métier est de dire ce qui s'est passé. Il
        reprend donc la lecture en mode tolérant et **nomme ce qui manque**,
        plutôt que de s'arrêter sur un granule dont le reste est bon.

        Qui veut l'arrêt appelle `grib2.open_granule` directement.

        Le lignage est **transmis à l'écriture** : une donnée qui quitte le
        système sans sa licence n'est pas exploitable, et c'est `netcdf_cf`
        qui sait l'inscrire dans le fichier.
        """
        entree = grib2.file_triplets(source)
        perdus: tuple[str, ...] = ()
        verdict = Verdict.COMPLET
        motif = ""

        try:
            jeux = grib2.open_granule(source)
        except grib2.DroppedFieldsError:
            jeux = grib2.open_granule(source, errors="ignore")
            perdus = tuple(str(t) for t in sorted(grib2.dropped_fields(source, jeux)))
            verdict = Verdict.AMPUTE
            motif = (
                f"{len(perdus)} paramètre(s) présents à l'entrée n'apparaissent "
                "pas au décodage : deux paramètres y partagent un nom court."
            )

        normalises = tuple(grib2.normalise(jeu) for jeu in jeux)
        reference = empreinte_de_contrat(contract.output_contract(normalises).json_stable())

        sorties = []
        for rang, jeu in enumerate(normalises):
            cible = self.settings.destination / f"{source.stem}__{rang:02d}.nc"
            sorties.append(netcdf_cf.write_netcdf(jeu, cible, retrieval=retrieval))

        return GranuleReport(
            source=source,
            sorties=tuple(sorties),
            parametres_en_entree=len(entree),
            champs_en_sortie=sum(len(j.data_vars) for j in normalises),
            perdus=perdus,
            contrat=reference,
            verdict=verdict,
            motif=motif,
        )

    # --- L'enchaînement complet ----------------------------------------------

    def run(self, requete: object) -> PipelineReport:
        """Acquiert puis traite, et rend un compte rendu de bout en bout."""
        debut = datetime.now(UTC)
        acquisition = self.acquire(requete)

        artefacts = acquisition.retrieval.artefacts if acquisition.retrieval else ()
        granules = tuple(self._traiter(Path(a), acquisition.retrieval) for a in artefacts)

        rapport = PipelineReport(
            source=acquisition.source,
            run_id=acquisition.run_id,
            started_at=debut,
            acquisition=acquisition,
            granules=granules,
        )
        self._accumuler(rapport)
        return rapport

    # --- Constater, ne pas tester --------------------------------------------

    def _accumuler(self, rapport: PipelineReport) -> Path:
        """Ajoute le compte rendu à l'état, pour en déduire la disponibilité.

        **Aucune requête n'est émise ici.** La disponibilité se constate sur
        le trafic réel — une acquisition dit déjà si la source a répondu, en
        combien de temps et pour quel volume. Sonder pour vérifier qu'on peut
        sonder dépenserait un crédit fini auprès du producteur, et pour rien.

        Une ligne par exécution, ajoutée en fin de fichier : le format se
        relit, se coupe et s'analyse sans rien charger en mémoire.
        """
        self.settings.etat.mkdir(parents=True, exist_ok=True)
        cible = self.settings.etat / "executions.jsonl"
        with cible.open("a", encoding="utf-8", newline="\n") as flux:
            flux.write(json.dumps(json.loads(rapport.model_dump_json()), ensure_ascii=False))
            flux.write("\n")
        return cible


__all__ = ["RequeteInconnue", "Session"]
