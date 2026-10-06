"""
televersement.py
────────────────
Réception des fichiers envoyés depuis le navigateur (fichiers isolés, dossier
complet ou archive .zip), par blocs de quelques Mo pour supporter des fichiers
de plusieurs gigaoctets et afficher la progression.
"""
from __future__ import annotations

import os
import re
import shutil
import time
import uuid
import zipfile

import config

RACINE = os.path.join(config.DOSSIER_DONNEES, "televersements")
DUREE_CONSERVATION_S = 3 * 24 * 3600


def _dossier(tid: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{16}", tid or ""):
        raise ValueError("Identifiant de téléversement invalide.")
    return os.path.join(RACINE, tid)


def nouveau() -> str:
    purger()
    tid = uuid.uuid4().hex[:16]
    os.makedirs(_dossier(tid), exist_ok=True)
    return tid


def _chemin_sur(tid: str, nom_relatif: str) -> str:
    """Chemin de destination sans remontée de répertoire."""
    base = _dossier(tid)
    parties = [p for p in re.split(r"[\\/]+", nom_relatif or "") if p not in ("", ".", "..")]
    if not parties:
        raise ValueError("Nom de fichier vide.")
    parties = [re.sub(r'[<>:"|?*\x00-\x1f]', "_", p) for p in parties]
    chemin = os.path.abspath(os.path.join(base, *parties))
    if not chemin.startswith(os.path.abspath(base) + os.sep):
        raise ValueError("Nom de fichier invalide.")
    return chemin


def ecrire_bloc(tid: str, nom_relatif: str, position: int, flux, taille_bloc: int = 1 << 20) -> int:
    chemin = _chemin_sur(tid, nom_relatif)
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    if position == 0 and os.path.exists(chemin):
        os.remove(chemin)
    actuelle = os.path.getsize(chemin) if os.path.exists(chemin) else 0
    if position > actuelle:
        raise ValueError(f"Bloc hors séquence ({position} > {actuelle}).")
    if position < actuelle:
        # bloc renvoyé après une coupure : on reprend à sa position
        with open(chemin, "r+b") as f:
            f.truncate(position)
    with open(chemin, "ab") as f:
        while True:
            morceau = flux.read(taille_bloc)
            if not morceau:
                break
            f.write(morceau)
    return os.path.getsize(chemin)


def finaliser(tid: str) -> str:
    """Décompresse les archives .zip reçues et retourne le dossier à examiner."""
    base = _dossier(tid)
    for racine, _, noms in os.walk(base):
        for nm in noms:
            if nm.lower().endswith(".zip"):
                archive = os.path.join(racine, nm)
                cible = os.path.join(racine, os.path.splitext(nm)[0])
                _extraire_zip(archive, cible)
                os.remove(archive)
    return base


def _extraire_zip(archive: str, cible: str):
    cible_abs = os.path.abspath(cible)
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            nom = info.filename
            if info.is_dir() or "__MACOSX" in nom or os.path.basename(nom).startswith("._"):
                continue
            dest = os.path.abspath(os.path.join(cible, nom))
            if not dest.startswith(cible_abs + os.sep):
                continue                                   # protection contre les chemins sortants
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with z.open(info) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
            if nom.lower().endswith(".zip"):              # archive dans l'archive
                _extraire_zip(dest, os.path.splitext(dest)[0])
                os.remove(dest)


def est_televersement(chemin: str) -> bool:
    return os.path.abspath(chemin or "").startswith(os.path.abspath(RACINE) + os.sep)


def supprimer(chemin: str):
    if est_televersement(chemin):
        shutil.rmtree(chemin, ignore_errors=True)


def purger():
    """Supprime les téléversements de plus de trois jours."""
    if not os.path.isdir(RACINE):
        return
    limite = time.time() - DUREE_CONSERVATION_S
    for nm in os.listdir(RACINE):
        d = os.path.join(RACINE, nm)
        try:
            if os.path.isdir(d) and os.path.getmtime(d) < limite:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


# ── Finalisation en arrière-plan (décompression et examen peuvent durer) ─────
import threading as _threading

_finalisations: dict[str, dict] = {}


def finaliser_en_arriere_plan(tid: str, examiner) -> None:
    """Lance décompression + examen sans bloquer la requête du navigateur."""
    _dossier(tid)                                   # contrôle de l'identifiant
    if _finalisations.get(tid, {}).get("etat") == "en_cours":
        return
    _finalisations[tid] = {"etat": "en_cours", "debut": time.time()}

    def tache():
        try:
            dossier = finaliser(tid)
            res = examiner(dossier)
            res["televersement"] = tid
            _finalisations[tid] = {"etat": "termine", "resultat": res}
        except Exception as e:                      # noqa: BLE001
            _finalisations[tid] = {"etat": "erreur",
                                   "erreur": f"Traitement des fichiers reçus impossible : {e}"}

    _threading.Thread(target=tache, daemon=True).start()


def etat_finalisation(tid: str) -> dict:
    return _finalisations.get(tid, {"etat": "inconnu"})
