"""Les noms CF commités sont-ils cohérents avec leurs unités ?

CF exige que l'unité d'une variable portant un `standard_name` soit
physiquement équivalente à l'unité canonique de ce nom. ERDDAP l'applique, CMOR
le refuse par erreur critique, et **rien ici ne le vérifiait** : jusqu'au
22/10/2026 le dépôt a commité treize couples que CF déclare incompatibles — un
nom de débit posé sur un champ cumulé, qui traverse ecCodes, cfgrib, xarray et
netCDF4 sans un mot.

**Pourquoi ce contrôle est transverse et non dans un paquet.** Les noms
concernés vivent dans deux membres — les contrats de référence de
`x10-connectors` et les données de `x10-catalog` — et onze des treize fautes
étaient dans le second. Le placer dans l'un ferait dépendre sa suite des
sources de l'autre ; c'est la raison même d'être de ce dossier.

Il **n'importe aucun module du dépôt** : il lit des fichiers de données, et
tourne donc sans installation.

**Portée à ne pas surestimer.** Un test vert dit que nos noms et nos unités
sont *dimensionnellement compatibles*, pas que nos noms sont justes : la
convertibilité ne voit ni le signe ni la convention de référence. Un flux
compté vers le haut nommé comme un flux vers le bas passerait au vert.
"""

from __future__ import annotations

import json
import os
import pathlib

import pytest

RACINE = pathlib.Path(__file__).resolve().parents[1]
REFERENCE = pathlib.Path(__file__).parent / "cf-canonical-units.json"

#: Les fichiers commités qui portent des couples nom / unité. Énumérés plutôt
#: que découverts : un dossier nouveau doit être inscrit à la main, ce qui
#: produit une ligne de `git diff` qu'un relecteur lit.
SOURCES = (
    RACINE / "packages" / "x10-connectors" / "tests" / "references",
    RACINE / "packages" / "x10-catalog" / "src" / "x10_catalog" / "data",
)

#: Le tableau des noms standards, forme XML. Source normative de CF, et la
#: seule façon de vérifier une unité canonique autrement qu'en l'affirmant.
CF_TABLE_URL = (
    "https://cfconventions.org/Data/cf-standard-names/current/src/cf-standard-name-table.xml"
)


def couples_commites() -> dict[str, set[tuple[str, str]]]:
    """Les couples (nom standard, unité) de chaque fichier commité.

    Un nom sans unité, ou une unité sans nom, n'est pas un couple : seule leur
    coexistence sur une même fiche est vérifiable.
    """
    releve: dict[str, set[tuple[str, str]]] = {}
    for dossier in SOURCES:
        for chemin in sorted(dossier.glob("*.json")):
            if chemin == REFERENCE:
                continue
            trouves: set[tuple[str, str]] = set()
            pile: list[object] = [json.loads(chemin.read_text(encoding="utf-8"))]
            while pile:
                noeud = pile.pop()
                if isinstance(noeud, dict):
                    nom, unite = noeud.get("standard_name"), noeud.get("units")
                    if isinstance(nom, str) and isinstance(unite, str):
                        trouves.add((nom, unite))
                    pile.extend(noeud.values())
                elif isinstance(noeud, list):
                    pile.extend(noeud)
            if trouves:
                releve[chemin.name] = trouves
    return releve


def unites_canoniques() -> dict[str, str]:
    return dict(json.loads(REFERENCE.read_text(encoding="utf-8"))["units"])


def test_chaque_couple_nom_unite_est_dimensionnellement_coherent():
    """L'invariant que la sonde `X10-DIV-0008` annonçait sans l'outiller."""
    cf_units = pytest.importorskip("cf_units")
    canoniques = unites_canoniques()
    releve = couples_commites()
    assert releve, "aucun couple relevé : les fichiers commités sont-ils encore là ?"

    fautifs = []
    for fichier, couples in sorted(releve.items()):
        for nom, unite in sorted(couples):
            attendue = canoniques.get(nom)
            if attendue is None:
                fautifs.append(f"{fichier} — {nom} : absent de {REFERENCE.name}")
            elif not cf_units.Unit(unite).is_convertible(cf_units.Unit(attendue)):
                fautifs.append(f"{fichier} — {nom} : émis en {unite!r}, canonique {attendue!r}")
    assert fautifs == [], "Couple(s) nom/unité que CF déclare incompatibles :\n  " + "\n  ".join(
        fautifs
    )


def test_le_releve_couvre_les_deux_membres_concernes():
    """Un relevé amputé ferait passer le contrôle en ne vérifiant plus rien.

    Onze des treize fautes initiales étaient dans le catalogue : une version
    de ce contrôle qui ne balaierait que les contrats de `x10-connectors`
    serait passée à côté de l'essentiel.
    """
    fichiers = set(couples_commites())
    assert any(f.startswith("meteofrance-arome") for f in fichiers), (
        "les contrats de référence de x10-connectors ne sont plus balayés"
    )
    assert "meteofrance.json" in fichiers, "les données de x10-catalog ne sont plus balayées"


@pytest.mark.network
def test_les_unites_canoniques_suivent_le_tableau_officiel():
    """Engendre le relevé des unités canoniques, et échoue s'il a bougé.

    Même mécanique que `lexique-public.txt` : la référence est **commitée**, de
    sorte qu'une évolution du tableau CF produit une ligne de `git diff` qu'un
    relecteur lit, au lieu de se glisser dans la sortie.

    Régénérer par
    `X10_REGENERATE_REFERENCES=1 uv run pytest -m network -k unites_canoniques`.
    """
    import urllib.request
    from xml.etree import ElementTree

    with urllib.request.urlopen(CF_TABLE_URL, timeout=120) as reponse:
        racine = ElementTree.parse(reponse).getroot()

    officielles = {
        e.get("id"): (e.findtext("canonical_units") or "").strip() for e in racine.iter("entry")
    }
    assert len(officielles) > 4000, "tableau CF inattendu : trop peu d'entrées"

    voulus = {nom for couples in couples_commites().values() for nom, _ in couples}
    absents = sorted(nom for nom in voulus if nom not in officielles)
    assert absents == [], (
        f"Nom(s) commis absent(s) du tableau CF : {absents}. Un nom qui "
        "n'existe pas rend le fichier non conforme en silence."
    )

    releve = {
        "version": racine.findtext("version_number"),
        "units": {nom: officielles[nom] for nom in sorted(voulus)},
    }
    rendu = json.dumps(releve, ensure_ascii=False, indent=2) + "\n"

    if os.environ.get("X10_REGENERATE_REFERENCES"):
        REFERENCE.write_text(rendu, encoding="utf-8")
        pytest.skip(f"référence régénérée : {REFERENCE.name}")

    assert REFERENCE.read_text(encoding="utf-8") == rendu, (
        f"{REFERENCE.name} diffère du tableau CF {releve['version']}. Relire "
        "l'écart avant de régénérer : une unité canonique qui change est un "
        "signal, pas un détail."
    )
