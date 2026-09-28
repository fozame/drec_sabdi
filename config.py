"""
Configuration générale de l'application.
Les valeurs peuvent être surchargées par variables d'environnement.
"""
import os
import secrets

RACINE = os.path.dirname(os.path.abspath(__file__))


def _env(nom: str, defaut: str = "") -> str:
    """Variable SABDI_<nom> (ou SGRNA_<nom>, nom de l'ancienne version)."""
    return os.environ.get(f"SABDI_{nom}", os.environ.get(f"SGRNA_{nom}", defaut))


DOSSIER_DONNEES = _env("DATA", os.path.join(RACINE, "data"))
os.makedirs(DOSSIER_DONNEES, exist_ok=True)

# Base SQLite (utilisateurs + historique des analyses) ; l'ancien nom de fichier reste reconnu
_ancienne_bd = os.path.join(DOSSIER_DONNEES, "sgrna.db")
CHEMIN_BD = _env("DB", _ancienne_bd if os.path.exists(_ancienne_bd) else os.path.join(DOSSIER_DONNEES, "sabdi.db"))

# Réseau
HOTE = _env("HOST", "0.0.0.0")
PORT = int(_env("PORT", "5600"))

# Dossier proposé par défaut dans le formulaire d'analyse (facultatif)
DOSSIER_PAR_DEFAUT = _env("DOSSIER", "")


def _cle_secrete() -> str:
    cle = _env("SECRET")
    if cle:
        return cle
    fichier = os.path.join(DOSSIER_DONNEES, ".cle_secrete")
    if os.path.exists(fichier):
        return open(fichier).read().strip()
    cle = secrets.token_hex(32)
    with open(fichier, "w") as f:
        f.write(cle)
    return cle


CLE_SECRETE = _cle_secrete()

# En-tête des documents exportés
ORGANISME = [
    "AGENCE DE RÉGULATION DES TÉLÉCOMMUNICATIONS",
    "Direction Technique",
    "Sous-direction de la Gestion des Ressources Techniques",
]
NOM_APPLICATION = "SABDI"
NOM_COMPLET = "Système d'analyse des bases de données d'identification des opérateurs"


def chemin_logo() -> str | None:
    """Logo de l'ART (app/static/logo_art.png) ; None s'il n'a pas encore été déposé."""
    for rel in ("app/static/logo_art.png", "app/static/images/logo_art.png", "static/logo_art.png"):
        p = os.path.join(RACINE, rel)
        if os.path.exists(p):
            return p
    return None
TITRE_ANNEXE = "État des lieux de la base des données d'identification"
