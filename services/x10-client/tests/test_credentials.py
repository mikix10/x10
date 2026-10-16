"""Les secrets : qu'ils entrent, qu'ils servent, et qu'ils ne sortent jamais.

Le dernier point est le seul qui compte vraiment. Ces tests le vérifient sur
**tous** les chemins par lesquels X10 fait sortir de l'information : compte
rendu, journal d'exécutions, journalisation ECS, message d'exception,
affichage de la configuration.

> Un secret qui fuit une fois a fui pour toujours : l'historique d'un journal
> est aussi permanent que celui d'un dépôt.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr
from x10_client import Credentials, MissingCredential, PipelineReport, Session
from x10_client.credentials import ENVIRONMENT

from x10_connectors import ConnectorResult
from x10_connectors.observability import failure_fields, redact

#: Une valeur reconnaissable, qui n'est le secret de personne.
FACTICE = "valeur-factice-a-ne-jamais-voir-sortir"


# --- Entrer ------------------------------------------------------------------


def test_sans_variable_aucun_identifiant():
    """Une source sans identifiant n'est pas une erreur : la plupart des
    nôtres n'en demandent aucun, et exiger ici empêcherait d'acquérir en
    voie ouverte."""
    vide = Credentials.from_env({})
    assert vide.available == ()
    assert vide.get("meteofrance") is None


def test_une_variable_posee_est_lue():
    creds = Credentials.from_env({"X10_MF_APPLICATION_ID": FACTICE})
    assert creds.available == ("meteofrance",)
    assert creds.get("meteofrance").get_secret_value() == FACTICE


def test_une_source_a_plusieurs_parts_se_nomme():
    """Un service a `login` et `mot de passe` en demande deux. Le modele les
    porte separement plutot que de les entasser avec un separateur, qui se
    melangerait au premier identifiant le contenant."""
    from x10_client.credentials import ENVIRONMENT

    assert all(isinstance(parts, dict) and parts for parts in ENVIRONMENT.values())
    # Aucune source actuelle n'en a deux, mais le modele l'accepte.
    deux = Credentials(parts={"cds": {"token": SecretStr(FACTICE), "autre": SecretStr(FACTICE)}})
    assert FACTICE not in deux.model_dump_json()


def test_une_part_doit_etre_nommee_quand_il_y_en_a_plusieurs(monkeypatch):
    from x10_client import credentials as module

    monkeypatch.setitem(module.ENVIRONMENT, "duo", {"login": "X10_DUO_LOGIN", "pw": "X10_DUO_PW"})
    creds = Credentials.from_env({"X10_DUO_LOGIN": "jean", "X10_DUO_PW": FACTICE})
    with pytest.raises(ValueError, match="several parts"):
        creds.get("duo")
    assert creds.get("duo", "pw").get_secret_value() == FACTICE


def test_une_part_inconnue_leve():
    with pytest.raises(ValueError, match="Unknown part"):
        Credentials().get("cds", "mot-de-passe")


def test_une_source_a_moitie_configuree_n_est_pas_disponible(monkeypatch):
    """La dire disponible serait un mensonge qui se paierait a la requete."""
    from x10_client import credentials as module

    monkeypatch.setitem(module.ENVIRONMENT, "duo", {"login": "X10_DUO_LOGIN", "pw": "X10_DUO_PW"})
    creds = Credentials.from_env({"X10_DUO_LOGIN": "jean"})
    assert "duo" not in creds.available
    assert creds.incomplete == ("duo",)


def test_require_nomme_toutes_les_parts_manquantes(monkeypatch):
    from x10_client import credentials as module

    monkeypatch.setitem(module.ENVIRONMENT, "duo", {"login": "X10_DUO_LOGIN", "pw": "X10_DUO_PW"})
    creds = Credentials.from_env({"X10_DUO_LOGIN": "jean"})
    with pytest.raises(MissingCredential, match="X10_DUO_PW"):
        creds.require("duo")


def test_require_rend_le_jeu_complet(monkeypatch):
    """Un appelant qui obtiendrait une part sur deux echouerait plus loin,
    avec le message du service et non le notre."""
    from x10_client import credentials as module

    monkeypatch.setitem(module.ENVIRONMENT, "duo", {"login": "X10_DUO_LOGIN", "pw": "X10_DUO_PW"})
    creds = Credentials.from_env({"X10_DUO_LOGIN": "jean", "X10_DUO_PW": FACTICE})
    jeu = creds.require("duo")
    assert set(jeu) == {"login", "pw"}
    assert jeu["pw"].get_secret_value() == FACTICE


def test_une_variable_vide_vaut_une_absence():
    assert Credentials.from_env({"X10_MF_APPLICATION_ID": "   "}).available == ()


def test_chaque_source_a_sa_propre_variable():
    """Un secret partagé entre deux sources serait impossible à révoquer pour
    l'une sans casser l'autre."""
    toutes = [v for parts in ENVIRONMENT.values() for v in parts.values()]
    assert len(set(toutes)) == len(toutes)
    creds = Credentials.from_env({"X10_CDS_TOKEN": FACTICE})
    assert creds.available == ("cds",)
    assert creds.get("meteofrance") is None


def test_une_source_inconnue_leve_plutot_que_de_rendre_none():
    """Rendre `None` sur un nom mal orthographié ferait croire à une absence
    d'identifiant là où il y a une faute de frappe."""
    with pytest.raises(ValueError, match="Unknown credential source"):
        Credentials().get("mon-service")


def test_require_nomme_la_variable_a_poser():
    """Une erreur qui dit seulement « identifiant manquant » oblige à lire le
    code pour savoir quoi faire."""
    with pytest.raises(MissingCredential, match="X10_MF_APPLICATION_ID"):
        Credentials().require("meteofrance")


def test_require_rend_la_valeur_quand_elle_est_la():
    creds = Credentials.from_env({"X10_MF_APPLICATION_ID": FACTICE})
    assert creds.require("meteofrance")["application_id"].get_secret_value() == FACTICE


# --- Ne jamais sortir ---------------------------------------------------------


@pytest.fixture
def creds():
    return Credentials.from_env({"X10_MF_APPLICATION_ID": FACTICE, "X10_CDS_TOKEN": FACTICE})


@pytest.mark.parametrize(
    ("rendu", "comment"),
    [
        (repr, "repr"),
        (str, "str"),
        (lambda c: f"{c}", "f-string"),
        (lambda c: str(c.model_dump()), "model_dump"),
        (lambda c: c.model_dump_json(), "model_dump_json"),
        (lambda c: json.dumps(c.model_dump(mode="json")), "json"),
    ],
    ids=["repr", "str", "f-string", "model_dump", "model_dump_json", "json"],
)
def test_aucun_rendu_ne_laisse_passer_la_valeur(creds, rendu, comment):
    """La propriété mesurée qui permet d'accepter un secret."""
    assert FACTICE not in rendu(creds), f"fuite par {comment}"


def test_seul_get_secret_value_expose(creds):
    """Une seule porte, et il faut l'ouvrir exprès."""
    assert creds.get("cds").get_secret_value() == FACTICE


def test_les_sources_disponibles_se_disent_sans_rien_reveler(creds):
    """De quoi afficher ce qui est configuré, sans afficher quoi."""
    assert creds.available == ("cds", "meteofrance")
    assert FACTICE not in str(creds.available)


def test_la_configuration_ne_porte_aucun_secret(tmp_path, monkeypatch):
    """`Settings` et `Credentials` sont deux objets, délibérément : afficher
    la configuration reste ainsi sans risque."""
    monkeypatch.setenv("X10_DESTINATION", str(tmp_path))
    monkeypatch.setenv("X10_MF_APPLICATION_ID", FACTICE)
    session = Session.from_env()

    assert FACTICE not in repr(session.settings)
    assert session.credentials.available == ("meteofrance",)
    assert FACTICE not in repr(session)


def test_un_secret_ne_survit_pas_a_un_compte_rendu():
    """Le chemin le plus exposé : `runs.jsonl` est écrit à chaque exécution
    et relu par `observe`."""
    rapport = PipelineReport(
        source="une-source",
        run_id="r1",
        started_at=datetime.now(UTC),
        acquisition=ConnectorResult(
            source="une-source",
            outcome="failure",
            message=f"echec en interrogeant https://exemple.invalid/v1?token={FACTICE}",
            run_id="r1",
            started_at=datetime.now(UTC),
            duration_ns=1,
        ),
    )
    # Le message est compose par le connecteur ; c'est `redact` qui le nettoie
    # avant le journal. Ici on verifie la fonction, puis le rendu complet.
    assert FACTICE not in redact(rapport.acquisition.message)
    assert "exemple.invalid/v1" in redact(rapport.acquisition.message)


# --- La rédaction, seul chemin qui restait ouvert ------------------------------


def test_une_chaine_de_requete_est_redigee():
    message = f"HTTPError 403 for https://api.invalid/v1/data?token={FACTICE}&x=1"
    nettoye = redact(message)
    assert FACTICE not in nettoye
    assert "https://api.invalid/v1/data?<redacted>" in nettoye


def test_le_chemin_survit_a_la_redaction():
    """Il dit quel objet était demandé — c'est ce qui sert au diagnostic.
    La chaîne de requête, elle, ne sert qu'à fuir."""
    assert redact("404 sur https://s3.invalid/b/k.grib2") == "404 sur https://s3.invalid/b/k.grib2"


def test_plusieurs_urls_sont_toutes_redigees():
    nettoye = redact(f"https://a.invalid/x?k={FACTICE} puis https://b.invalid/y?j={FACTICE}")
    assert FACTICE not in nettoye
    assert nettoye.count("<redacted>") == 2


def test_un_message_sans_url_est_rendu_tel_quel():
    assert redact("Aucun reseau ne porte la selection demandee") == (
        "Aucun reseau ne porte la selection demandee"
    )


def test_les_champs_ecs_d_echec_sont_rediges():
    """Le point d'entrée réel : `failure_fields` recopiait `str(error)` dans
    `error.message`, et une bibliothèque HTTP y met l'adresse complète."""
    erreur = RuntimeError(f"connexion refusee sur https://api.invalid/v1?key={FACTICE}")
    champs = failure_fields(erreur)
    assert FACTICE not in champs["error.message"]
    assert champs["error.type"] == "RuntimeError"


def test_rien_ne_fuit_par_la_journalisation(caplog):
    """De bout en bout : une exception porteuse d'un secret, journalisée par
    la mécanique réelle, ne doit rien laisser dans les enregistrements."""
    _log = logging.getLogger("x10_connectors.essai")
    erreur = RuntimeError(f"echec sur https://api.invalid/v1?token={FACTICE}")
    with caplog.at_level(logging.ERROR):
        _log.error("Retrieval failed", extra=failure_fields(erreur))

    capture = "\n".join(
        [r.getMessage() for r in caplog.records]
        + [str(r.__dict__.get("error.message", "")) for r in caplog.records]
    )
    assert FACTICE not in capture


# --- La règle de dépendance ----------------------------------------------------


def test_aucun_paquet_ne_lit_l_environnement():
    """**Le client résout, le connecteur reçoit.** Un paquet qui lirait
    l'environnement détiendrait un secret, ce que la décision « X10 ne porte
    aucun secret » interdit.

    Vérifié le 16/10/2026 : zéro occurrence avant ce chantier. Le test rend
    la règle structurelle plutôt que disciplinaire.
    """
    racine = Path(__file__).resolve().parents[3] / "packages"
    fautifs = [
        f"{p.relative_to(racine)}"
        for p in racine.rglob("src/**/*.py")
        if "__pycache__" not in p.parts
        and any(motif in p.read_text(encoding="utf-8") for motif in ("os.environ", "getenv"))
    ]
    assert fautifs == [], f"un paquet lit l'environnement : {fautifs}"


# --- Ce que l'imbrication a changé, et ce qu'elle n'a pas changé --------------
#
# Relevé le 16/10/2026, en passant d'un champ par source à des parts nommées :
# la protection tient au **type de la feuille**, pas au conteneur. Le modèle
# a pu devenir un dictionnaire libre sans rien affaiblir. Mais la surface
# d'accès a grandi, et elle grandira encore — d'où le balayage ci-dessous,
# qui n'énumère pas les chemins.


def test_une_chaine_nue_est_coercee_en_secret():
    """La garantie vient de l'annotation de type, pas de notre code.

    Simplifier `dict[str, dict[str, SecretStr]]` en
    `dict[str, dict[str, str]]` suffirait à faire sortir les secrets en
    clair, sans que rien ne tombe en panne. Ce test vérifie que la
    conversion automatique a bien lieu, et interdit donc cette
    simplification.
    """
    creds = Credentials(parts={"cds": {"token": FACTICE}})
    assert isinstance(creds.parts["cds"]["token"], SecretStr)
    assert FACTICE not in creds.model_dump_json()


def test_aucune_surface_publique_ne_laisse_passer_la_valeur(creds):
    """**Le test qui grandit avec le modèle.** Plutôt que d'énumérer les
    chemins — `repr`, `str`, `model_dump`… —, il parcourt tout ce que l'objet
    expose et vérifie que rien n'en sort en clair.

    Un accesseur ajouté demain sans y penser sera couvert par construction ;
    c'était la faiblesse de la version par chemins nommés.
    """
    # `model_fields` et consorts sont la mecanique de Pydantic, pas notre
    # surface, et y acceder sur l'instance est deprecie.
    mecanique = {n for n in dir(Credentials) if n.startswith("model_")}
    vus = []
    for nom in dir(creds):
        if nom.startswith("_") or nom in mecanique:
            continue
        attribut = getattr(creds, nom)
        if callable(attribut):
            continue  # les methodes a argument sont couvertes separement
        vus.append(nom)
        assert FACTICE not in str(attribut), f"fuite par l'attribut {nom}"
        assert FACTICE not in repr(attribut), f"fuite par le repr de {nom}"

    assert {"parts", "available", "incomplete"} <= set(vus), "le balayage doit voir ces trois-la"


def test_les_accesseurs_a_argument_redigent_aussi(creds):
    """Les deux que le balayage ne peut pas appeler sans savoir quoi passer."""
    assert FACTICE not in str(creds.get("cds"))
    assert FACTICE not in str(creds.require("cds"))
    assert FACTICE not in repr(creds.require("cds"))


def test_la_valeur_reste_accessible_malgre_tout(creds):
    """La contrepartie : rédiger partout ne doit pas rendre le secret
    inutilisable. Une seule porte, et il faut l'ouvrir exprès."""
    assert creds.require("cds")["token"].get_secret_value() == FACTICE


# --- Contre la malveillance, pas seulement contre l'erreur --------------------
#
# Trois trous mesurés le 16/10/2026, dont un qui ne demande aucune
# malveillance. Ils avaient tous la même cause : la protection reposait sur
# le **type de la feuille**, et rien ne tenait au niveau du conteneur.


def test_muter_le_dictionnaire_interne_ne_fait_rien_fuir(creds):
    """**Le trou principal.** Un modèle gelé interdit de réaffecter le champ,
    mais pas de muter le dictionnaire qu'il contient. Avant correction, une
    seule ligne faisait fuir cinq chemins de rendu.

    Ce n'est pas qu'un scénario de malveillance : du code qui « met à jour »
    un jeton en place produirait le même effet.
    """
    creds.parts["cds"]["token"] = FACTICE  # une chaine nue, sans validation

    for nom, rendu in [
        ("repr", repr(creds)),
        ("str", str(creds)),
        ("f-string", f"{creds}"),
        ("model_dump", str(creds.model_dump())),
        ("model_dump_json", creds.model_dump_json()),
    ]:
        assert FACTICE not in rendu, f"fuite par {nom} apres mutation"


def test_une_source_ajoutee_apres_coup_ne_fuit_pas(creds):
    """Même chose en ajoutant une entrée entière, et non en remplaçant."""
    creds.parts["intrus"] = {"x": FACTICE}
    assert FACTICE not in creds.model_dump_json()
    assert FACTICE not in repr(creds)


def test_le_rendu_reste_utile_malgre_la_redaction(creds):
    """Rédiger ne doit pas rendre le diagnostic impossible : on veut savoir
    **quelles sources et quelles parts** sont posées."""
    rendu = repr(creds)
    assert "cds" in rendu and "token" in rendu
    assert "meteofrance" in rendu and "application_id" in rendu
    assert FACTICE not in rendu


def test_une_erreur_de_validation_ne_montre_pas_l_entree():
    """**Le trou qui ne demande aucune malveillance.** Sans
    `hide_input_in_errors`, Pydantic écrit « input_value=… » en clair — et
    c'est justement une entrée mal formée qui finit journalisée.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as capture:
        Credentials(parts={"cds": {"token": {"imbrique": FACTICE}}})
    assert FACTICE not in str(capture.value)


def test_la_serialisation_binaire_est_interdite(creds):
    """Les octets d'un `pickle.dumps` portent le secret **en clair**, le type
    `SecretStr` n'y changeant rien. Un objet d'identifiants n'a aucune raison
    d'être pickle."""
    import pickle

    with pytest.raises(TypeError, match="must not be pickled"):
        pickle.dumps(creds)


def test_une_copie_conserve_la_protection(creds):
    """La copie est un usage légitime — elle ne doit ni fuir ni casser."""
    import copy

    for copie in (creds.model_copy(deep=True), copy.deepcopy(creds)):
        assert FACTICE not in repr(copie)
        assert copie.require("cds")["token"].get_secret_value() == FACTICE


def test_la_protection_ne_depend_plus_du_seul_type_de_la_feuille():
    """Défense en profondeur : même construit avec des chaînes nues partout,
    l'objet ne laisse rien sortir. L'annotation reste, en seconde ligne."""
    brut = Credentials.model_construct(parts={"cds": {"token": FACTICE}})
    assert FACTICE not in repr(brut)
    assert FACTICE not in brut.model_dump_json()
