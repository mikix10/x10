"""Les secrets dont une source authentifiée a besoin — et rien d'autre.

**X10 ne porte aucun secret, et cette décision ne change pas.** Elle disait
que les *paquets* n'en détiennent aucun, pas qu'aucune source authentifiée ne
serait jamais atteinte. Un client qui lit l'environnement est l'endroit où un
identifiant a sa place : il résout, le connecteur reçoit.

Vérifié le 16/10/2026 : **aucun paquet ne lit l'environnement** — zéro
occurrence de `os.environ` dans `packages/*/src` —, et un test l'exige
désormais. La règle tient donc par construction plutôt que par discipline.

**Un identifiant a plusieurs parts, et il faut le prévoir.** Un premier jet
posait un champ par source, ce qui supposait qu'une source demande *une*
valeur. C'est faux en général : un service à `login` et `mot de passe` en
demande deux, et l'ancienne forme du CDS attendait `UID:clé`. Le modèle porte
donc **des parts nommées par source**, ce qui évite le piège qui guettait —
entasser deux valeurs dans une variable avec un séparateur, et les voir se
mélanger au premier identifiant contenant ce séparateur.

> Relevé le 16/10/2026 : le CDS actuel attend **un** jeton d'accès personnel,
> la forme `UID:clé` étant obsolète. Mais son URL de base diffère de celle de
> l'ADS, et une source à deux parts reste la règle ailleurs. Le modèle ne
> coûte rien de plus et n'oblige à aucun changement de schéma à la prochaine
> source.

**Ce qui rend la chose sûre est mesuré, pas supposé.** `SecretStr` rédige sur
tous les chemins que X10 emprunte — `repr`, `str`, f-string, `model_dump`,
`model_dump_json` — **y compris imbriqué dans un dictionnaire**, et seul
`get_secret_value()` expose. Un secret ne peut donc fuir ni dans
`runs.jsonl`, ni dans un compte rendu, ni dans un message d'exception composé
par interpolation.

**Le seul chemin qui restait ouvert** était l'URL : une bibliothèque HTTP met
volontiers l'adresse complète dans son message d'exception, et
`observability.failure_fields` la recopiait dans le journal ECS. Deux
réponses, toutes deux nécessaires — la chaîne de requête est retirée du
journal côté `x10-connectors`, et **un secret ne voyage jamais en paramètre
d'URL quand un en-tête existe**.

**Les secrets ne sont pas dans `Settings`**, délibérément : afficher la
configuration reste ainsi sans risque, et l'objet qui franchit le plus de
frontières est celui qui n'en porte aucun.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, SecretStr, field_serializer

from x10_connectors.observability import SecretRedactor

#: Par source, les **parts** attendues et la variable d'environnement de
#: chacune. Vocabulaire **fermé** : une source inconnue lève plutôt que de
#: rendre une absence, un nom mal orthographié étant sinon indiscernable d'un
#: identifiant non posé.
#:
#: Une variable **par part et par source** : un secret partagé entre deux
#: sources serait impossible à révoquer pour l'une sans casser l'autre, et
#: deux parts dans une même variable se mélangeraient au premier identifiant
#: contenant le séparateur.
#:
#: Ce sont des identifiants **de longue durée**. Le jeton éphémère qu'ils
#: permettent d'obtenir n'a pas sa place ici — voir `Credentials`.
ENVIRONMENT: dict[str, dict[str, str]] = {
    # Identifiant d'application, qui sert a obtenir un jeton d'une heure.
    "meteofrance": {"application_id": "X10_MF_APPLICATION_ID"},
    # Jeton d'acces personnel. La forme `UID:cle` est obsolete depuis 2025.
    "cds": {"token": "X10_CDS_TOKEN"},
    "ads": {"token": "X10_ADS_TOKEN"},
}


class MissingCredential(RuntimeError):
    """Une source authentifiée a été demandée sans son identifiant complet."""


class Credentials(BaseModel):
    """Les identifiants de longue durée, lus de l'environnement.

    **Un identifiant de longue durée, jamais un jeton.** Mesuré sur
    Météo-France : l'identifiant d'application permet d'obtenir un jeton
    valable **une heure**. Mettre ce jeton en variable d'environnement
    condamnerait toute exécution de plus d'une heure, et toute exécution
    lancée une heure après l'avoir posé. C'est donc au connecteur — seul à
    connaître le protocole de sa source — de faire l'échange.

    Jamais lus d'un fichier que nous analyserions : un `.env` est déjà refusé
    au niveau du compte, et le lire ici contournerait ce garde-fou.
    """

    #: `hide_input_in_errors` est **indispensable, pas une précaution**.
    #: Mesuré le 16/10/2026 : sans lui, une valeur mal formée ressort en
    #: clair dans le `ValidationError` — « input_value={'x': 'le-secret'} » —,
    #: et c'est justement une entrée mal formée qui finit journalisée.
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    #: Les parts posées, par source. Absente de ce dictionnaire, une source
    #: n'a simplement aucun identifiant configuré.
    parts: dict[str, dict[str, SecretStr]] = {}

    # --- La rédaction tient au conteneur, pas seulement à la feuille --------
    #
    # Mesuré le 16/10/2026 : un modèle **gelé** interdit de réaffecter le
    # champ, mais **pas de muter le dictionnaire** qu'il contient. Une seule
    # ligne — `creds.parts[source][part] = "en-clair"` — suffisait à faire
    # fuir cinq chemins de rendu, parce que la protection reposait alors sur
    # le seul type de la feuille.
    #
    # Les trois membres ci-dessous rendent la fuite impossible **quel que
    # soit le contenu** : ils ne lisent jamais une valeur. Le type `SecretStr`
    # reste déclaré, en défense supplémentaire et non en défense unique.

    @field_serializer("parts", when_used="always")
    def _jamais_de_valeur_serialisee(
        self, parts: dict[str, dict[str, SecretStr]]
    ) -> dict[str, dict[str, str]]:
        """Sérialise la **forme**, jamais le contenu."""
        return {source: dict.fromkeys(p, "**********") for source, p in parts.items()}

    def __repr__(self) -> str:
        """Dit quelles sources et quelles parts sont posées, jamais leur valeur.

        Utile et sûr : `Credentials(parts={'cds': ['token']})` suffit à
        diagnostiquer une configuration sans rien révéler.
        """
        detail = {source: sorted(p) for source, p in sorted(self.parts.items())}
        return f"{type(self).__name__}(parts={detail})"

    __str__ = __repr__

    def __reduce__(self) -> str | tuple[object, ...]:
        """Interdit la sérialisation binaire.

        Mesuré : les octets d'un `pickle.dumps` contiennent le secret **en
        clair**, `SecretStr` n'y changeant rien. Un objet d'identifiants n'a
        aucune raison d'être pickle — ni cache, ni file de travail, ni
        multiprocessing — et l'interdire vaut mieux que de compter sur le
        fait que personne n'essaiera.
        """
        raise TypeError(
            f"{type(self).__name__} must not be pickled: the bytes would carry the "
            "secret in clear. Pass the resolved value to the connector instead."
        )

    @classmethod
    def from_env(cls, environment: dict[str, str] | None = None) -> Credentials:
        """Résout les parts présentes. Aucune n'est obligatoire ici.

        Une source sans identifiant n'est pas une erreur : la plupart des
        nôtres n'en demandent aucun, et exiger à la construction empêcherait
        d'acquérir en voie ouverte. L'erreur survient au moment où une source
        authentifiée est **demandée** — voir `require`.

        Une source dont **une seule part sur deux** est posée est conservée
        telle quelle : c'est `require` qui dira laquelle manque, en la
        nommant.
        """
        env = os.environ if environment is None else environment
        trouvees: dict[str, dict[str, SecretStr]] = {}
        for source, variables in ENVIRONMENT.items():
            posees = {
                part: SecretStr(brut)
                for part, variable in variables.items()
                if (brut := env.get(variable, "").strip())
            }
            if posees:
                trouvees[source] = posees
        return cls(parts=trouvees)

    def _connue(self, source: str) -> dict[str, str]:
        if source not in ENVIRONMENT:
            connues = ", ".join(sorted(ENVIRONMENT))
            raise ValueError(f"Unknown credential source {source!r}. Expected one of {connues}.")
        return ENVIRONMENT[source]

    def get(self, source: str, part: str | None = None) -> SecretStr | None:
        """Une part d'un identifiant, ou `None`.

        `part` est facultatif quand la source n'en attend qu'une — le cas le
        plus courant, et celui où l'imposer serait une cérémonie inutile.
        """
        attendues = self._connue(source)
        if part is None:
            if len(attendues) != 1:
                noms = ", ".join(sorted(attendues))
                raise ValueError(
                    f"Source {source!r} has several parts ({noms}); name the one you want."
                )
            part = next(iter(attendues))
        if part not in attendues:
            noms = ", ".join(sorted(attendues))
            raise ValueError(f"Unknown part {part!r} for {source!r}. Expected one of {noms}.")
        return self.parts.get(source, {}).get(part)

    def require(self, source: str) -> dict[str, SecretStr]:
        """**Toutes** les parts d'une source, ou une erreur qui dit quoi poser.

        Rend le jeu complet plutôt qu'une part : un appelant qui en obtient
        une sur deux échouerait plus loin, au moment de la requête, avec un
        message du service et non le nôtre.

        Le message nomme les variables d'environnement manquantes — une
        erreur qui dit seulement « identifiant manquant » oblige à lire le
        code pour savoir quoi faire.
        """
        attendues = self._connue(source)
        posees = self.parts.get(source, {})
        manquantes = sorted(variable for part, variable in attendues.items() if part not in posees)
        if manquantes:
            raise MissingCredential(
                f"Source {source!r} requires {len(attendues)} credential part(s). "
                f"Set {', '.join(manquantes)} in the environment."
            )
        return dict(posees)

    @property
    def available(self) -> tuple[str, ...]:
        """Les sources dont **toutes** les parts sont posées.

        Rend les **noms de sources**, jamais les valeurs — de quoi afficher
        ce qui est utilisable sans rien révéler. Une source à moitié
        configurée n'y figure pas : elle n'est pas utilisable, et la dire
        disponible serait un mensonge qui se paierait à la requête.
        """
        return tuple(
            sorted(
                source
                for source, attendues in ENVIRONMENT.items()
                if set(self.parts.get(source, {})) >= set(attendues)
            )
        )

    @property
    def incomplete(self) -> tuple[str, ...]:
        """Les sources partiellement configurées — presque toujours un oubli."""
        return tuple(
            sorted(
                source
                for source, attendues in ENVIRONMENT.items()
                if self.parts.get(source) and set(self.parts[source]) < set(attendues)
            )
        )

    def redactor(self) -> SecretRedactor:
        """Le filtre de journalisation qui rédige nos valeurs, et rien d'autre.

        **C'est ici que le partage se joue.** `x10-connectors` fournit le
        mécanisme et ne détient aucun secret ; le client détient les valeurs
        et les lui remet. Un connecteur reçoit déjà un identifiant résolu en
        paramètre : c'est le même régime, appliqué à la journalisation.

        **À installer par l'application, jamais par la bibliothèque.** Le
        dépôt a posé que `x10-connectors` n'impose ni destination ni rendu de
        journal ; il n'imposera pas davantage un filtre. L'appelant écrit :

            handler.addFilter(session.credentials.redactor())

        Mesuré le 19/10/2026 : sans ce filtre, `observability.redact` ne
        couvre qu'**un** des quatre chemins par lesquels un identifiant
        atteint le journal — elle laisse passer un jeton dans le chemin d'une
        URL, un en-tête recopié, et un identifiant cité en clair.
        """
        valeurs = {
            part.get_secret_value() for parts in self.parts.values() for part in parts.values()
        }
        return SecretRedactor(valeurs)


__all__ = ["ENVIRONMENT", "Credentials", "MissingCredential"]
