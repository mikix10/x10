"""Accès HTTP partagé par le catalogue — bibliothèque standard seulement.

**Une sonde ne justifie jamais à elle seule une dépendance nouvelle.** Elle
se limite au nécessaire et suffisant avec ce que le dépôt a déjà ; le jour
où une bibliothèque arrive pour une raison produit, une sonde peut s'en
servir et se renforcer. Les connecteurs n'utilisant que `urllib.request`,
c'est ce que l'on emploie ici.

**Convergence prévue, et c'est une dette assumée.** L'échange identifiant →
jeton revient au connecteur, « seul à connaître le protocole de sa source ».
Quand les connecteurs CDS et API ciblée existeront, ces fonctions
disparaîtront au profit d'appels à eux. Les écrire ici maintenant évite
d'attendre, et les trois lignes qu'elles feront alors les éprouveront.

Le nom commence par `_` : le chargeur de catalogue ignore ces modules.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from x10_client.credentials import Credentials, MissingCredential

#: Délai maximal, explicite. Le skill `security` l'exige : jamais de requête
#: sans borne, et les clients officiels d'ECMWF se sont tous deux fait
#: prendre à des reprises de seize heures par défaut.
TIMEOUT = 120

MF_TOKEN = "https://portail-api.meteofrance.fr/token"
MF_GATEWAY = "https://public-api.meteofrance.fr"
CDS = "https://cds.climate.copernicus.eu/api"


def _open(requete: urllib.request.Request) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(requete, timeout=TIMEOUT) as reponse:
            return int(reponse.status), reponse.read()
    except urllib.error.HTTPError as erreur:
        return int(erreur.code), erreur.read()


def fetch(
    url: str, *, entetes: dict[str, str] | None = None, params: dict[str, Any] | None = None
) -> tuple[int, bytes]:
    """Un GET borné, qui rend le code et le corps sans lever sur un 4xx.

    Un code d'erreur est une **donnée** pour une sonde : c'est souvent lui
    qui porte le constat, comme le `403` qui nomme une politique manquante.
    """
    if params:
        url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
    return _open(urllib.request.Request(url, headers=entetes or {}))


def meteofrance_token(credentials: Credentials) -> str:
    """Échange l'identifiant d'application contre un jeton d'une heure.

    Mesuré le 20/10/2026 : `expires_in` vaut exactement 3 600 s, et le jeton
    voyage ensuite en en-tête `Bearer`, jamais en paramètre d'URL.
    """
    part = credentials.get("meteofrance")
    if part is None:
        raise MissingCredential("Set X10_MF_APPLICATION_ID to replay the Meteo-France probes.")
    url = f"{MF_TOKEN}?{urllib.parse.urlencode({'grant_type': 'client_credentials'})}"
    requete = urllib.request.Request(
        url, data=b"", headers={"Authorization": f"Basic {part.get_secret_value()}"}
    )
    code, corps = _open(requete)
    if code != 200:
        raise MissingCredential(f"Meteo-France token endpoint answered HTTP {code}.")
    jeton = json.loads(corps)["access_token"]
    return str(jeton)


def meteofrance_headers(credentials: Credentials) -> dict[str, str]:
    return {"Authorization": f"Bearer {meteofrance_token(credentials)}", "Accept": "*/*"}


def cds_headers(credentials: Credentials) -> dict[str, str]:
    """L'en-tête `PRIVATE-TOKEN` du moteur `ecmwf-datastores-client`.

    Un seul jeton d'accès personnel ouvre CDS, ADS et EWDS — mesuré le
    19/10/2026, les trois rendant la même identité.
    """
    part = credentials.get("ecmwf_datastores")
    if part is None:
        raise MissingCredential("Set X10_ECMWF_DATASTORES_TOKEN to replay the Copernicus probes.")
    return {"PRIVATE-TOKEN": part.get_secret_value(), "Accept": "application/json"}


def redact(credentials: Credentials, texte: str) -> str:
    """Rédige toute valeur connue avant qu'un détail ne parte au rapport.

    Le compte rendu d'une sonde est écrit, lu et parfois transmis : il tombe
    exactement sous le cas que `SecretRedactor` traite.
    """
    return str(credentials.redactor().scrub(texte))


def subsetting(racine: str, entetes: dict[str, str], couverture: str) -> list[str]:
    """Le `subset` d'une couverture, **lu** dans `DescribeCoverage`.

    Le service exige un découpage sur tous les axes sauf deux, et refuse une
    valeur qui n'est pas dans ceux qu'il déclare. Supposer le premier instant
    égal au réseau est faux : sur MFWAM la première échéance vaut
    réseau + 3 600 s. On lit donc les coefficients plutôt que de les deviner.

    Les deux axes laissés libres sont la géographie, bornée à une petite
    emprise — une sonde constate, elle ne rapatrie pas de la donnée.
    """
    import datetime as _dt
    import re as _re

    code, corps = fetch(
        f"{racine}/DescribeCoverage",
        entetes=entetes,
        params={"service": "WCS", "version": "2.0.1", "coverageid": couverture},
    )
    if code != 200:
        raise RuntimeError(f"DescribeCoverage answered HTTP {code}.")
    texte = corps.decode("utf-8", "replace")
    etiquettes = _re.findall(r'axisLabels="([^"]+)"', texte)
    axes = etiquettes[0].split() if etiquettes else []
    coefficients = [
        c.split()
        for c in _re.findall(r"<gmlrgrid:coefficients>([^<]*)</gmlrgrid:coefficients>", texte)
    ]
    reseau = couverture.rsplit("___", 1)[1].partition("_")[0].replace(".", ":")

    subset = ["lat(43,45)", "long(2,5)"]
    irreguliers = [a for a in axes if a not in {"lat", "long"}]
    for rang, axe in enumerate(irreguliers):
        valeurs = coefficients[rang] if rang < len(coefficients) else []
        if axe == "time":
            debut = _dt.datetime.fromisoformat(reseau.replace("Z", "+00:00"))
            quand = debut + _dt.timedelta(seconds=int(valeurs[0]) if valeurs else 0)
            subset.append(f"time({quand.strftime('%Y-%m-%dT%H:%M:%SZ')})")
        elif valeurs:
            subset.append(f"{axe}({valeurs[0]})")
    return subset


def instant_of(subset: list[str]) -> str:
    """Extrait la valeur temporelle d'un découpage, sans guillemets."""
    for expression in subset:
        if expression.startswith("time("):
            return expression[len("time(") : -1]
    raise RuntimeError("No temporal axis in the subset.")
