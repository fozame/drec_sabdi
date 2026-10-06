"""
execution.py
────────────
Exécution d'une analyse dans un processus séparé.

Si la mémoire vient à manquer, le système arrête ce processus (le plus gros)
et non l'application : l'utilisateur reçoit un message clair au lieu d'une
application redémarrée et d'une analyse disparue. Aucune dépendance à Flask :
le processus enfant n'importe que le moteur.
"""
from __future__ import annotations

import os
import traceback


def memoire_go() -> float | None:
    """Mémoire de travail du processus courant (Go)."""
    try:
        with open("/proc/self/status") as f:
            for ligne in f:
                if ligne.startswith("RssAnon"):
                    return int(ligne.split()[1]) / 2 ** 20
    except OSError:
        pass
    return None


def travail(parametres: dict, file) -> None:
    """Point d'entrée du processus enfant : messages ("log"|"etape"|"resultat"|"erreur", …)."""
    os.environ.setdefault("_RJEM_MALLOC_CONF", "background_thread:true,dirty_decay_ms:0,muzzy_decay_ms:0")
    try:
        from moteur.analyse import lancer_analyse

        def log(msg, niveau="info"):
            file.put(("log", str(msg), niveau))

        def etape(texte, pct):
            m = memoire_go()
            file.put(("etape", texte, pct, m))

        res = lancer_analyse(parametres, log=log, etape=etape)
        file.put(("resultat", res))
    except BaseException as e:                     # noqa: BLE001 (y compris les erreurs internes de Polars)
        file.put(("erreur", f"{type(e).__name__} : {e}", traceback.format_exc()))
