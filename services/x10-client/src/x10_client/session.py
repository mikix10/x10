"""L'assemblage : acquérir, décoder, normaliser, écrire, contracter.

Cet enchaînement n'existait jusqu'ici **que dans du code de test**. Ce module
lui donne un domicile — il ne le retire pas aux tests, qui doivent continuer
d'exercer la chaîne au niveau des paquets, sans ce client.

**Rien ici n'est de la logique de domaine.** Pas une unité convertie, pas un
nom résolu, pas une borne calculée : tout cela appartient aux paquets. Ce
module appelle, configure, et rend compte.

**Trois étapes publiques, et `run()` est leur composition.** C'est voulu : un
carnet qui a déjà téléchargé cent quarante mébioctets doit pouvoir rejouer la
normalisation sans les reprendre, et un fichier déjà sur le disque doit
pouvoir être traité sans acquisition du tout.

| Méthode | Pour qui |
|---|---|
| `acquire(request)` | télécharger, et rien d'autre ; **propage** |
| `normalise_granule(source)` | un fichier déjà là, d'où qu'il vienne |
| `normalise(acquisition)` | reprendre une acquisition sans retélécharger |
| `run(request)` | la chaîne entière, et un compte rendu **quoi qu'il arrive** |
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from x10_connectors import BaseConnector, ConnectorResult, grib2, netcdf_cf
from x10_connectors.contract import output_contract
from x10_models import Retrieval

from .config import Settings
from .credentials import Credentials
from .options import DEFAULT_OPTIONS, NormaliseOptions
from .report import (
    ErrorType,
    GranuleReport,
    PipelineReport,
    Verdict,
    contract_fingerprint,
)

#: Correspondance requête → connecteur, résolue **paresseusement**.
#: L'import d'`EcmwfIfsOpenDataConnector` tire le client officiel, qui est un
#: extra : le résoudre au chargement du module rendrait le client
#: ininstallable sans lui.
_CONNECTORS = {
    "MeteoFrancePntRequest": ("meteofrance_pnt", "MeteoFrancePntConnector"),
    "EcmwfIfsRequest": ("ecmwf_ifs", "EcmwfIfsOpenDataConnector"),
}

#: Exception d'un paquet → catégorie du compte rendu. Le classement est
#: **nominatif et fermé** : une exception inconnue tombe en `OTHER` plutôt que
#: d'être rangée par ressemblance, ce qui mentirait au premier renommage amont.
_ERROR_TYPES: tuple[tuple[str, ErrorType], ...] = (
    ("UnconvertibleUnitError", ErrorType.UNITS),
    ("UnknownStatisticalProcessingError", ErrorType.CELL_METHODS),
    ("UnrepresentableIntervalError", ErrorType.INTERVAL),
    ("NoOutputFileError", ErrorType.WRITE),
    ("GribUnavailableError", ErrorType.WRITE),
    ("DroppedFieldsError", ErrorType.DECODE),
)

#: Profondeur de remontée dans `__context__`. Une exception de la pile GRIB
#: est souvent enveloppée ; au-delà, on ne saurait plus de quoi on parle.
_CONTEXT_DEPTH = 5


class UnknownRequest(TypeError):
    """Aucun connecteur ne correspond à cette requête."""


#: Les deux connecteurs héritent de `BaseConnector` mais **ne partagent pas
#: de signature de construction** : la classe de base définit le comportement,
#: pas l'instanciation. `type[BaseConnector]` mentirait donc ; un appelable
#: rendant un connecteur dit exactement ce qu'on sait.
ConnectorFactory = Callable[..., BaseConnector]


def _connector_for(request: object) -> ConnectorFactory:
    name = type(request).__name__
    if name not in _CONNECTORS:
        known = ", ".join(sorted(_CONNECTORS))
        raise UnknownRequest(f"{name}: no known connector. Expected one of {known}.")
    import importlib

    module_name, class_name = _CONNECTORS[name]
    module = importlib.import_module(f"x10_connectors.{module_name}")
    factory: ConnectorFactory = getattr(module, class_name)
    return factory


def _classify(error: BaseException) -> ErrorType:
    """Range une exception de paquet dans le vocabulaire fermé du compte rendu."""
    names: set[str] = set()
    modules: set[str] = set()
    current: BaseException | None = error
    for _ in range(_CONTEXT_DEPTH):
        if current is None:
            break
        names.add(type(current).__name__)
        modules.add(type(current).__module__)
        current = current.__context__

    for name, category in _ERROR_TYPES:
        if name in names:
            return category
    # Un fichier que la pile GRIB refuse d'ouvrir ne porte aucune exception à
    # nous : la pile lève la sienne. Elle se range au décodage, qui est bien
    # l'étape en cause. Les trois modules sont nommés plutôt que devinés —
    # `UnsupportedEditionError` vient de `gribapi.errors`, pas d'`eccodes`,
    # et l'oublier rangeait un fichier illisible en « autre ».
    if any(m.startswith(("eccodes", "gribapi", "cfgrib")) for m in modules):
        return ErrorType.DECODE
    return ErrorType.OTHER


@dataclass(frozen=True)
class Session:
    """Une configuration résolue, et les opérations qu'elle permet."""

    settings: Settings
    #: Identifiants des sources authentifiees. **Separes des reglages** : la
    #: configuration s'affiche sans risque, et l'objet qui franchit le plus de
    #: frontieres est celui qui ne porte aucun secret.
    credentials: Credentials = field(default_factory=Credentials)

    @classmethod
    def from_env(cls, environment: dict[str, str] | None = None) -> Session:
        return cls(
            settings=Settings.from_env(environment),
            credentials=Credentials.from_env(environment),
        )

    # --- Acquisition ---------------------------------------------------------

    def _connector(self, request: object) -> BaseConnector:
        """Construit le connecteur **sans télécharger**.

        Séparé de `acquire` pour que `run` dispose de `source_name` même
        lorsque `fetch()` lève — sans quoi un échec d'acquisition ne saurait
        pas dire de quelle source il parle.
        """
        self.settings.destination.mkdir(parents=True, exist_ok=True)
        factory = _connector_for(request)
        extra = (
            {"max_bytes": self.settings.max_bytes} if self.settings.max_bytes is not None else {}
        )
        return factory(self.settings.destination, request, **extra)

    def acquire(self, request: object) -> ConnectorResult:
        """Télécharge, et rien de plus. Le compte rendu est celui du paquet.

        **Propage.** Qui appelle cette méthode directement veut l'exception du
        connecteur, avec sa trace ; c'est `run()` qui la convertit en compte
        rendu.
        """
        return self._connector(request).fetch()

    # --- Normalisation -------------------------------------------------------

    def normalise_granule(
        self,
        source: Path,
        *,
        retrieval: Retrieval | None = None,
        options: NormaliseOptions | None = None,
    ) -> GranuleReport:
        """Décode, normalise, écrit et contracte **un** granule.

        Publique, et utilisable sur un fichier qui ne vient d'aucune
        acquisition — un granule conservé hors dépôt, par exemple.

        **Le comportement en cas d'échec est une option, pas un câblage.**
        `options.errors` vaut `"raise"` par défaut, qui est le comportement
        d'une bibliothèque ; `run()` passe `"report"`. La divergence se lit au
        lieu de surprendre.

        Le lignage est **transmis à l'écriture** : une donnée qui quitte le
        système sans sa licence n'est pas exploitable, et c'est `netcdf_cf`
        qui sait l'inscrire dans le fichier.
        """
        options = options or DEFAULT_OPTIONS
        try:
            return self._normalise_granule(source, retrieval, options)
        except Exception as error:
            if options.errors == "raise":
                raise
            return GranuleReport(
                source=source,
                verdict=Verdict.FAILED,
                error_type=_classify(error),
                reason=f"{type(error).__name__}: {error}",
            )

    def _normalise_granule(
        self, source: Path, retrieval: Retrieval | None, options: NormaliseOptions
    ) -> GranuleReport:
        """Le traitement nu, qui lève. La politique est au-dessus."""
        incoming = grib2.file_triplets(source)
        dropped: tuple[str, ...] = ()
        verdict = Verdict.COMPLETE
        reason = ""

        try:
            datasets = grib2.open_granule(source)
        except grib2.DroppedFieldsError:
            if options.dropped_fields == "raise":
                raise
            # Le grain de l'arbitrage appartient à l'appelant : la bibliothèque
            # refuse une perte silencieuse, le client la **nomme** plutôt que
            # d'abandonner un granule dont le reste est bon.
            datasets = grib2.open_granule(source, errors="ignore")
            dropped = tuple(
                grib2.format_identity(code)
                for code in sorted(grib2.dropped_fields(source, datasets))
            )
            verdict = Verdict.PARTIAL
            reason = (
                f"{len(dropped)} parameter(s) present on input do not appear in "
                "the decoded output: two parameters share a short name there."
            )

        normalised = tuple(grib2.normalise(dataset) for dataset in datasets)
        # Le contrat prend **le même réglage que l'écriture** : bâti sans lui,
        # il levait sur une unité intraduisible trois lignes avant que
        # `strict_units` ne soit consulté, et la tolérance paraissait sans effet.
        reference = contract_fingerprint(
            output_contract(normalised, strict_units=options.strict_units).json_stable()
        )

        outputs: list[Path] = []
        if options.write:
            for index, dataset in enumerate(normalised):
                target = self.settings.destination / f"{source.stem}__{index:02d}.nc"
                outputs.append(
                    netcdf_cf.write_netcdf(
                        dataset,
                        target,
                        retrieval=retrieval,
                        strict_units=options.strict_units,
                        compress=options.compress,
                    )
                )

        return GranuleReport(
            source=source,
            outputs=tuple(outputs),
            parameters_in=len(incoming),
            fields_out=sum(len(d.data_vars) for d in normalised),
            dropped=dropped,
            contract=reference,
            verdict=verdict,
            reason=reason,
        )

    def normalise(
        self, acquisition: ConnectorResult, *, options: NormaliseOptions | None = None
    ) -> tuple[GranuleReport, ...]:
        """Traite tous les granules d'une acquisition, **sans retélécharger**.

        C'est l'étape qui manquait : un carnet garde son `ConnectorResult` et
        rejoue la normalisation autant de fois qu'il veut, en changeant les
        options, sans rien redemander au producteur.
        """
        retrieval = acquisition.retrieval
        artefacts = retrieval.artefacts if retrieval else ()
        return tuple(
            self.normalise_granule(Path(a), retrieval=retrieval, options=options) for a in artefacts
        )

    # --- L'enchaînement complet ----------------------------------------------

    def run(self, request: object, *, options: NormaliseOptions | None = None) -> PipelineReport:
        """Acquiert puis traite, et rend un compte rendu **quoi qu'il arrive**.

        **Ne lève pas** sur un échec d'acquisition ni sur un granule fautif :
        c'est la différence entre une bibliothèque et un client. Le compte
        rendu porte le verdict, et la ligne de commande le traduit en code de
        sortie.

        Le correctif date du 16/10/2026, sur un défaut mesuré : auparavant un
        échec de décodage faisait remonter l'exception **avant**
        l'accumulation, de sorte qu'un téléchargement réussi ne laissait
        aucune trace. La disponibilité sous-déclarait exactement dans le cas
        où la source allait bien et où c'était nous qui échouions.
        """
        options = (options or DEFAULT_OPTIONS).model_copy(update={"errors": "report"})
        started = datetime.now(UTC)
        start = time.perf_counter_ns()

        # **Hors du rattrapage, délibérément.** Une requête sans connecteur est
        # une erreur de l'appelant, pas une défaillance de la source. L'inscrire
        # à l'historique ferait chuter le taux de disponibilité d'un producteur
        # qui n'a même pas été contacté.
        connector = self._connector(request)

        try:
            acquisition = connector.fetch()
        except Exception as error:
            # Les connecteurs **lèvent** au lieu de rendre `outcome="failure"`,
            # ce qui est leur droit. Mais sans ce rattrapage aucune défaillance
            # n'entrerait jamais dans l'historique, et le taux de succès
            # vaudrait structurellement 1. Le compte rendu ci-dessous est
            # **composé par le client** ; rien n'y est inventé, tout y est
            # mesuré ou connu avant l'appel.
            acquisition = ConnectorResult(
                source=connector.source_name,
                outcome="failure",
                message=f"{type(error).__name__}: {error}",
                run_id=str(uuid.uuid4()),
                started_at=started,
                duration_ns=time.perf_counter_ns() - start,
            )

        granules: tuple[GranuleReport, ...] = ()
        try:
            granules = self.normalise(acquisition, options=options)
        finally:
            # Dans un `finally` : aucun chemin ne doit sauter l'accumulation,
            # sous peine de reproduire le défaut qu'on corrige.
            report = PipelineReport(
                source=acquisition.source,
                run_id=acquisition.run_id,
                started_at=started,
                acquisition=acquisition,
                granules=granules,
            )
            self._accumulate(report)
        return report

    # --- Constater, ne pas tester --------------------------------------------

    def _accumulate(self, report: PipelineReport) -> Path:
        """Ajoute le compte rendu à l'état, pour en déduire la disponibilité.

        **Aucune requête n'est émise ici.** La disponibilité se constate sur
        le trafic réel — une acquisition dit déjà si la source a répondu, en
        combien de temps et pour quel volume. Sonder pour vérifier qu'on peut
        sonder dépenserait un crédit fini auprès du producteur, et pour rien.

        Une ligne par exécution, ajoutée en fin de fichier : le format se
        relit, se coupe et s'analyse sans rien charger en mémoire.
        """
        self.settings.state.mkdir(parents=True, exist_ok=True)
        target = self.settings.state / "runs.jsonl"
        with target.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(json.loads(report.model_dump_json()), ensure_ascii=False))
            stream.write("\n")
        return target


__all__ = ["Session", "UnknownRequest"]
