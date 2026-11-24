# Image de verification du deploiement X10 -- etape du conteneur dedie.
#
# Elle ne collecte rien. Elle prouve trois choses dans un orchestrateur :
# qu'une image a nous demarre, que la pile GRIB s'y importe avec les memes
# tables que l'integration continue, et que le sortant atteint les
# producteurs que les connecteurs declarent.
#
# Le point d'entree de collecte n'est volontairement pas ici : il depend
# d'une decision de depot encore ouverte -- aucun membre ne declare
# `[project.scripts]`, et promouvoir la ligne de commande en paquet publie
# est un arbitrage qui engage l'integrateur. Ce fichier ne le prejuge pas.

# L'image de base est epinglee par EMPREINTE, jamais par etiquette : une
# etiquette est mutable, et c'est exactement la doctrine qui fait epingler
# les actions GitHub par empreinte. Relevee le 23/11/2026 pour
# `python:3.12-slim` ; pour en relever une nouvelle, sans Docker :
#
#   T=$(curl -s "https://auth.docker.io/token?service=registry.docker.io\
#   &scope=repository:library/python:pull" | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')
#   curl -sI -H "Authorization: Bearer $T" \
#     -H "Accept: application/vnd.oci.image.index.v1+json" \
#     https://registry-1.docker.io/v2/library/python/manifests/3.12-slim \
#     | grep -i docker-content-digest
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

# `uv` est epingle a la version du poste et de l'integration continue : une
# resolution differente ici produirait un environnement different la.
RUN pip install --no-cache-dir uv==0.12.16

WORKDIR /src
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
COPY services/ services/

# `--frozen` installe EXACTEMENT ce que le verrou dit, sans reresoudre.
# Sans lui, deux constructions du meme commit embarqueraient deux versions
# d'ecCodes -- donc deux jeux de tables sous une meme empreinte d'image, et
# la tracabilite que l'empreinte est censee porter serait fausse.
RUN uv sync --frozen --no-dev --package x10-connectors --extra grib

COPY deploy/verifier.py /opt/verifier.py

# Utilisateur sans privilege, dont l'identifiant numerique est repris tel
# quel par `runAsUser` dans le manifeste : les deux doivent concorder.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin x10
USER 10001

ENTRYPOINT ["python", "/opt/verifier.py"]
