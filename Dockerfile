# ─────────────────────────────────────────────────────────────────────────────
# SABDI – Système d'analyse des bases de données d'identification des opérateurs
# Image de production : Python 3.11, serveur waitress, port 5600.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim-bookworm

# Processeurs anciens (message « Illegal instruction » au démarrage) :
#   docker compose build --build-arg POLARS_RUNTIME=rtcompat
ARG POLARS_RUNTIME=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Africa/Douala \
    SABDI_DATA=/data \
    TMPDIR=/data/tmp \
    SABDI_HOST=0.0.0.0 \
    SABDI_PORT=5600

WORKDIR /app

# Dépendances (couche mise en cache tant que requirements.txt ne change pas)
COPY requirements.txt .
RUN pip install -r requirements.txt \
 && if [ -n "$POLARS_RUNTIME" ]; then \
        pip install "polars[$POLARS_RUNTIME]==$(pip show polars | sed -n 's/^Version: //p')" \
        && pip uninstall -y polars-runtime-32; \
    fi

# Application
COPY . .
RUN useradd --system --home-dir /app --shell /usr/sbin/nologin sabdi \
 && mkdir -p /data /depots \
 && chown -R sabdi:sabdi /data \
 && python -m compileall -q app moteur exports config.py serveur.py

VOLUME ["/data"]
EXPOSE 5600

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5600/sante', timeout=4).status == 200 else 1)"

# Le point d'entrée démarre en root pour régler les droits de /data, puis passe sous « sabdi ».
ENTRYPOINT ["python", "/app/docker/entrypoint.py"]
