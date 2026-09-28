#!/usr/bin/env python3
"""
Point d'entrée du conteneur SABDI.

- crée le dossier des données (/data) et lui donne le bon propriétaire ;
- abandonne les droits root et lance le serveur sous l'utilisateur « sabdi ».

Écrit en Python pour ne dépendre d'aucun outil système (gosu, setpriv…).
"""
import os
import pwd
import sys

DONNEES = os.environ.get("SABDI_DATA", "/data")
UTILISATEUR = "sabdi"


def main():
    os.makedirs(DONNEES, exist_ok=True)
    # fichiers temporaires (conversion d'encodage, Excel) sur le volume et non dans le conteneur
    tmp = os.environ.get("TMPDIR")
    if tmp:
        os.makedirs(tmp, exist_ok=True)
    if os.getuid() == 0:
        u = pwd.getpwnam(UTILISATEUR)
        for racine, dossiers, fichiers in os.walk(DONNEES):
            for nom in [racine] + [os.path.join(racine, x) for x in dossiers + fichiers]:
                try:
                    st = os.lstat(nom)
                    if st.st_uid != u.pw_uid:
                        os.lchown(nom, u.pw_uid, u.pw_gid)
                except OSError:
                    pass
        os.setgroups([])
        os.setgid(u.pw_gid)
        os.setuid(u.pw_uid)
        os.environ["HOME"] = u.pw_dir
    tz = os.environ.get("TZ")
    if tz and not os.path.exists(f"/usr/share/zoneinfo/{tz}"):
        print(f"[SABDI] Fuseau horaire {tz} introuvable : heure UTC utilisée.", file=sys.stderr)
    os.execvp(sys.executable, [sys.executable, "/app/serveur.py"])


if __name__ == "__main__":
    main()
