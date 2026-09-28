"""
taches.py
─────────
Exécution des analyses en arrière-plan. L'interface interroge l'état de la
tâche (étape, progression, journal) ; une seule analyse s'exécute à la fois
pour préserver la mémoire du poste.
"""
from __future__ import annotations

import gc
import threading
import time
import traceback
import uuid

_taches: dict[str, dict] = {}
_verrou = threading.Lock()


def en_cours() -> dict | None:
    with _verrou:
        for t in _taches.values():
            if t["etat"] == "en_cours":
                return t
    return None


def lire(job_id: str) -> dict | None:
    return _taches.get(job_id)


def lancer(parametres: dict, utilisateur: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    tache = {"id": job_id, "etat": "en_cours", "pct": 0, "etape": "Initialisation", "logs": [],
             "analyse_id": None, "erreur": None, "debut": time.time(), "parametres": parametres,
             "utilisateur": utilisateur}
    with _verrou:
        # purge des tâches terminées depuis plus d'une heure
        for k in [k for k, t in _taches.items() if t["etat"] != "en_cours" and time.time() - t["debut"] > 3600]:
            del _taches[k]
        _taches[job_id] = tache
    threading.Thread(target=_executer, args=(tache,), daemon=True).start()
    return job_id


def _executer(tache):
    from moteur.analyse import lancer_analyse
    from app.database import enregistrer_analyse

    def log(msg, niveau="info"):
        tache["logs"].append({"t": round(time.time() - tache["debut"], 1), "msg": str(msg), "niveau": niveau})

    def etape(texte, pct):
        tache["etape"], tache["pct"] = texte, pct
        log(texte, "etape")

    try:
        res = lancer_analyse(tache["parametres"], log=log, etape=etape)
        for a in res.get("alertes", []):
            log(a, "alerte")
        tache["analyse_id"] = enregistrer_analyse(res, tache["utilisateur"])
        tache["pct"], tache["etape"], tache["etat"] = 100, "Analyse terminée", "termine"
        log(f"Analyse terminée en {res.get('duree_s', 0)} s.", "ok")
        if tache["parametres"].get("supprimer_apres"):
            from app import televersement as T
            T.supprimer(tache["parametres"].get("dossier"))
            log("Fichiers téléversés supprimés du poste (résultats et extractions conservés).")
    except Exception as e:
        tache["etat"], tache["erreur"] = "erreur", str(e)
        log(f"Erreur : {e}", "erreur")
        log(traceback.format_exc(), "trace")
    finally:
        gc.collect()
