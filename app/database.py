"""
database.py
───────────
Base SQLite : utilisateurs et historique complet des analyses (résultats
conservés au format JSON, ce qui permet de rouvrir, modifier les observations
et réexporter toute analyse passée).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from functools import wraps

from flask import flash, redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import config


def connexion():
    conn = sqlite3.connect(config.CHEMIN_BD, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connexion() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'admin1',
            nom TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS analyses_bdi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operateur TEXT,
            operateur_libelle TEXT,
            annee INTEGER,
            mois INTEGER,
            periode_libelle TEXT,
            dossier TEXT,
            date_analyse TEXT NOT NULL,
            utilisateur TEXT,
            nb_numeros INTEGER,
            duree_s REAL,
            resultats TEXT NOT NULL,
            modifie_le TEXT,
            modifie_par TEXT)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_analyses_periode ON analyses_bdi(operateur, annee, mois)")
        existantes = {r[1] for r in c.execute("PRAGMA table_info(analyses_bdi)").fetchall()}
        for col, typ in (("statut_validation", "TEXT DEFAULT 'brouillon'"), ("valide_par", "TEXT"),
                         ("valide_le", "TEXT")):
            if col not in existantes:
                c.execute(f"ALTER TABLE analyses_bdi ADD COLUMN {col} {typ}")
        c.execute("""CREATE TABLE IF NOT EXISTS notes_mensuelles (
            annee INTEGER NOT NULL,
            mois INTEGER NOT NULL,
            texte TEXT,
            modifie_par TEXT,
            modifie_le TEXT,
            PRIMARY KEY (annee, mois))""")
        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            c.execute("INSERT INTO users (username, password, role, nom) VALUES (?,?,?,?)",
                      ("admin", generate_password_hash(config.MOT_DE_PASSE_ADMIN_INITIAL), "admin0", "Administrateur"))


# ═════════════════════════════════════════════════════════════════════════════
# UTILISATEURS
# ═════════════════════════════════════════════════════════════════════════════

def verifier_login(username, password):
    with connexion() as c:
        u = c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not u:
            return None
        stocke = u["password"]
        # Compatibilité avec les mots de passe de l'ancienne version (SHA-256 sans sel)
        if len(stocke) == 64 and all(ch in "0123456789abcdef" for ch in stocke):
            if hashlib.sha256(password.encode()).hexdigest() != stocke:
                return None
            c.execute("UPDATE users SET password = ? WHERE id = ?", (generate_password_hash(password), u["id"]))
            return u
        return u if check_password_hash(stocke, password) else None


def get_all_users():
    with connexion() as c:
        return c.execute("SELECT id, username, role, nom FROM users ORDER BY id").fetchall()


def ajouter_user(username, password, role, nom):
    try:
        with connexion() as c:
            c.execute("INSERT INTO users (username, password, role, nom) VALUES (?,?,?,?)",
                      (username, generate_password_hash(password), role, nom))
        return True
    except sqlite3.IntegrityError:
        return False


def modifier_user(user_id, role, nom, password=None):
    with connexion() as c:
        if password:
            c.execute("UPDATE users SET role=?, nom=?, password=? WHERE id=?",
                      (role, nom, generate_password_hash(password), user_id))
        else:
            c.execute("UPDATE users SET role=?, nom=? WHERE id=?", (role, nom, user_id))


def changer_mot_de_passe(user_id, ancien, nouveau):
    with connexion() as c:
        u = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not u or not verifier_login(u["username"], ancien):
        return False
    with connexion() as c:
        c.execute("UPDATE users SET password=? WHERE id=?", (generate_password_hash(nouveau), user_id))
    return True


def supprimer_user(user_id):
    with connexion() as c:
        c.execute("DELETE FROM users WHERE id=?", (user_id,))


# ═════════════════════════════════════════════════════════════════════════════
# ANALYSES
# ═════════════════════════════════════════════════════════════════════════════

def enregistrer_analyse(res: dict, utilisateur: str) -> int:
    res["utilisateur"] = utilisateur
    nb = next((e["lignes"][0]["total"] for e in res.get("etat_des_lieux", []) if e["code"] == "numeros"), None)
    p = res.get("periode", {})
    with connexion() as c:
        cur = c.execute(
            """INSERT INTO analyses_bdi (operateur, operateur_libelle, annee, mois, periode_libelle, dossier,
               date_analyse, utilisateur, nb_numeros, duree_s, resultats) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (res.get("operateur"), res.get("operateur_libelle"), p.get("annee"), p.get("mois"), p.get("libelle"),
             res.get("dossier"), datetime.now().isoformat(timespec="seconds"), utilisateur, nb,
             res.get("duree_s"), json.dumps(res, ensure_ascii=False, default=str)))
        return cur.lastrowid


def lire_analyse(analyse_id: int):
    with connexion() as c:
        row = c.execute("SELECT * FROM analyses_bdi WHERE id=?", (analyse_id,)).fetchone()
    if not row:
        return None, None
    res = json.loads(row["resultats"])
    res["id"] = row["id"]
    return row, res


def maj_resultats(analyse_id: int, res: dict, utilisateur: str):
    res = {k: v for k, v in res.items() if k != "id"}
    with connexion() as c:
        c.execute("UPDATE analyses_bdi SET resultats=?, modifie_le=?, modifie_par=? WHERE id=?",
                  (json.dumps(res, ensure_ascii=False, default=str), datetime.now().isoformat(timespec="seconds"),
                   utilisateur, analyse_id))


def supprimer_analyse(analyse_id: int):
    with connexion() as c:
        c.execute("DELETE FROM analyses_bdi WHERE id=?", (analyse_id,))


STATUTS_VALIDATION = {"brouillon": "Brouillon", "validee": "Validée", "remplacee": "Remplacée"}


def valider_analyse(analyse_id: int, utilisateur: str):
    """Valide une analyse ; une éventuelle analyse validée du même opérateur et du même mois est remplacée."""
    with connexion() as c:
        row = c.execute("SELECT operateur, annee, mois FROM analyses_bdi WHERE id=?", (analyse_id,)).fetchone()
        if not row:
            return
        c.execute("""UPDATE analyses_bdi SET statut_validation='remplacee'
                     WHERE statut_validation='validee' AND id<>? AND operateur IS ? AND annee IS ? AND mois IS ?""",
                  (analyse_id, row["operateur"], row["annee"], row["mois"]))
        c.execute("UPDATE analyses_bdi SET statut_validation='validee', valide_par=?, valide_le=? WHERE id=?",
                  (utilisateur, datetime.now().isoformat(timespec="seconds"), analyse_id))


def devalider_analyse(analyse_id: int):
    with connexion() as c:
        c.execute("UPDATE analyses_bdi SET statut_validation='brouillon', valide_par=NULL, valide_le=NULL WHERE id=?",
                  (analyse_id,))


def analyse_reference(operateur: str, annee: int, mois: int):
    """Analyse qui fait foi pour un opérateur et un mois : la validée, sinon la plus récente."""
    with connexion() as c:
        return c.execute("""SELECT id, statut_validation FROM analyses_bdi
                            WHERE operateur=? AND annee=? AND mois=?
                            ORDER BY (statut_validation='validee') DESC, id DESC LIMIT 1""",
                         (operateur, annee, mois)).fetchone()


def periodes_disponibles():
    with connexion() as c:
        return c.execute("""SELECT DISTINCT annee, mois FROM analyses_bdi
                            WHERE annee IS NOT NULL AND mois IS NOT NULL ORDER BY annee DESC, mois DESC""").fetchall()


def operateurs_du_mois(annee: int, mois: int):
    with connexion() as c:
        return [r[0] for r in c.execute("""SELECT DISTINCT operateur FROM analyses_bdi WHERE annee=? AND mois=?
                                            AND operateur IS NOT NULL ORDER BY operateur""", (annee, mois)).fetchall()]


def lire_note(annee: int, mois: int):
    with connexion() as c:
        return c.execute("SELECT * FROM notes_mensuelles WHERE annee=? AND mois=?", (annee, mois)).fetchone()


def enregistrer_note(annee: int, mois: int, texte: str, utilisateur: str):
    with connexion() as c:
        c.execute("""INSERT INTO notes_mensuelles (annee, mois, texte, modifie_par, modifie_le) VALUES (?,?,?,?,?)
                     ON CONFLICT(annee, mois) DO UPDATE SET texte=excluded.texte, modifie_par=excluded.modifie_par,
                     modifie_le=excluded.modifie_le""",
                  (annee, mois, texte, utilisateur, datetime.now().isoformat(timespec="seconds")))


def lister_analyses(operateur=None, annee=None, limite=None, statut=None):
    req = ("SELECT id, operateur, operateur_libelle, annee, mois, periode_libelle, dossier, date_analyse, "
           "utilisateur, nb_numeros, duree_s, modifie_le, statut_validation, valide_par, valide_le "
           "FROM analyses_bdi WHERE 1=1")
    params = []
    if statut:
        req += " AND COALESCE(statut_validation, 'brouillon') = ?"
        params.append(statut)
    if operateur:
        req += " AND operateur = ?"
        params.append(operateur)
    if annee:
        req += " AND annee = ?"
        params.append(int(annee))
    req += " ORDER BY COALESCE(annee,0) DESC, COALESCE(mois,0) DESC, id DESC"
    if limite:
        req += f" LIMIT {int(limite)}"
    with connexion() as c:
        return c.execute(req, params).fetchall()


def valeurs_filtres():
    with connexion() as c:
        ops = c.execute("SELECT DISTINCT operateur, operateur_libelle FROM analyses_bdi "
                        "WHERE operateur IS NOT NULL ORDER BY operateur_libelle").fetchall()
        annees = [r[0] for r in c.execute("SELECT DISTINCT annee FROM analyses_bdi WHERE annee IS NOT NULL "
                                          "ORDER BY annee DESC").fetchall()]
    return ops, annees


# ═════════════════════════════════════════════════════════════════════════════
# DÉCORATEURS
# ═════════════════════════════════════════════════════════════════════════════

def login_requis(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Veuillez vous connecter.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def role_requis(*roles):
    """Accès réservé à certains profils (admin0 = administrateur, admin1 = chargé d'analyse, direction)."""
    def deco(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                flash("Veuillez vous connecter.", "warning")
                return redirect(url_for("login"))
            if session.get("role") not in roles:
                flash("Cette action n'est pas ouverte à votre profil.", "danger")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return decorated
    return deco


def admin0_requis(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if session.get("role") != "admin0":
            flash("Accès réservé aux administrateurs de niveau 0.", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated
