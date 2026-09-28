"""
Serveur de production de SABDI (utilisé par l'image Docker).

    python serveur.py

Un seul processus, plusieurs fils d'exécution : les analyses en cours sont
suivies en mémoire, l'application ne doit donc pas être lancée en plusieurs
processus (pas de gunicorn -w 4).
"""
import logging
import os

from waitress import serve

import config
from app import app

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    fils = int(os.environ.get("SABDI_THREADS", "8"))
    logging.info("SABDI %s – écoute sur %s:%s (%s fils)", config.VERSION, config.HOTE, config.PORT, fils)
    serve(app, host=config.HOTE, port=config.PORT, threads=fils,
          max_request_body_size=512 * 1024 * 1024,   # blocs de téléversement
          channel_timeout=600, connection_limit=200, ident="SABDI")
