"""
Lancement de SABDI – Système d’analyse des bases de données d’identification des opérateurs.

    python run.py

Ouvre http://127.0.0.1:5600 ; les collègues du réseau utilisent l'adresse IP
du poste (http://192.168.x.x:5600).
"""
import os
import threading
import webbrowser

# Restitution rapide au système de la mémoire libérée par le moteur de calcul
# (doit être défini avant le premier chargement de Polars).
os.environ.setdefault("_RJEM_MALLOC_CONF", "background_thread:true,dirty_decay_ms:0,muzzy_decay_ms:0")

import config
from app import app


def ouvrir_navigateur():
    webbrowser.open(f"http://127.0.0.1:{config.PORT}")


if __name__ == "__main__":
    threading.Timer(1.2, ouvrir_navigateur).start()
    app.run(host=config.HOTE, port=config.PORT, debug=False, threaded=True)
