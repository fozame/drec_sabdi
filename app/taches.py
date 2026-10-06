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


ETAPES_APRES_SIGNAUX = ("Signaux d'alerte", "Synthèse", "Extraction des lignes concernées")


def _executer(tache):
    from app.database import enregistrer_analyse

    def log(msg, niveau="info"):
        tache["logs"].append({"t": round(time.time() - tache["debut"], 1), "msg": str(msg), "niveau": niveau})

    parametres = dict(tache["parametres"])
    try:
        res = None
        for essai in range(3):
            res, etape_fin, code = _processus(tache, parametres, log)
            if res is not None:
                break
            if code is None:                      # erreur signalée par l'analyse elle-même
                return
            # processus arrêté par le système (mémoire insuffisante le plus souvent)
            msg = (f"L'analyse a été interrompue par le système pendant l'étape « {etape_fin} » "
                   f"(code {code}) : mémoire insuffisante.")
            if etape_fin in ETAPES_APRES_SIGNAUX and parametres.get("signaux", True):
                log(msg + " Nouvel essai sans les signaux d'alerte.", "alerte")
                parametres.update(signaux=False, motif_sans_signaux=(
                    "Signaux d'alerte non calculés : mémoire insuffisante pour ce volume de données "
                    "(augmenter SABDI_MEMOIRE)."))
                continue
            if etape_fin == "Extraction des lignes concernées" and parametres.get("dossier_extractions"):
                log(msg + " Nouvel essai sans les extractions de lignes.", "alerte")
                parametres["dossier_extractions"] = None
                continue
            raise RuntimeError(msg + " Augmenter la mémoire allouée (SABDI_MEMOIRE dans le fichier .env) "
                                     "ou contacter l'administrateur.")
        if res is None:
            raise RuntimeError("L'analyse n'a pas pu aboutir après plusieurs essais.")
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


def _processus(tache, parametres, log):
    """
    Lance l'analyse dans un processus enfant et relaie sa progression.
    Retourne (résultat | None, dernière étape, code de sortie si arrêt anormal).
    """
    import multiprocessing as mp
    import queue as _queue
    from moteur.execution import travail

    ctx = mp.get_context("spawn")
    file = ctx.Queue()
    p = ctx.Process(target=travail, args=(parametres, file), daemon=True)
    _demarrer_sans_script_principal(p)
    res, etape_fin = None, tache.get("etape", "")
    try:
        while True:
            try:
                msg = file.get(timeout=1)
            except _queue.Empty:
                if not p.is_alive():
                    break
                continue
            if msg[0] == "log":
                log(msg[1], msg[2])
            elif msg[0] == "etape":
                _, texte, pct, mem = msg
                tache["etape"], tache["pct"] = texte, pct
                etape_fin = texte
                log(texte + (f"  (mémoire utilisée : {mem:.1f} Go)" if mem else ""), "etape")
            elif msg[0] == "resultat":
                res = msg[1]
                break
            elif msg[0] == "erreur":
                tache["etat"], tache["erreur"] = "erreur", msg[1]
                log(f"Erreur : {msg[1]}", "erreur")
                log(msg[2], "trace")
                p.join(10)
                return None, etape_fin, None
    finally:
        p.join(30)
        if p.is_alive():
            p.kill()
    if res is not None:
        return res, etape_fin, 0
    return None, etape_fin, p.exitcode


_verrou_demarrage = threading.Lock()


def _demarrer_sans_script_principal(p):
    """
    Démarre le processus enfant sans lui faire réexécuter le script principal
    (serveur.py, run.py ou un script d'essai) : seul le moteur est chargé.
    """
    import sys
    principal = sys.modules.get("__main__")
    with _verrou_demarrage:
        fichier = getattr(principal, "__file__", None)
        try:
            if fichier is not None:
                del principal.__file__
            p.start()
        finally:
            if fichier is not None:
                principal.__file__ = fichier
