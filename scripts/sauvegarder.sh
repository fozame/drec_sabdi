#!/usr/bin/env bash
# Sauvegarde des données SABDI (base, extractions, logo, clé) dans sauvegardes/.
#   ./scripts/sauvegarder.sh
# Les fichiers téléversés et temporaires ne sont pas sauvegardés (purgés au bout de 3 jours).
# Les 15 dernières sauvegardes sont conservées.
source "$(dirname "$0")/_commun.sh"
DONNEES="$(dossier_donnees)"
[ -d "$DONNEES" ] || { err "Dossier des données introuvable : $DONNEES"; exit 1; }
mkdir -p sauvegardes
HORO="$(date +%Y%m%d_%H%M)"

# Copie cohérente de la base SQLite, même si l'application est en service
EN_SERVICE=0
if docker ps --format '{{.Names}}' | grep -qx sabdi; then
  EN_SERVICE=1
  docker exec -u sabdi sabdi python -c "
import sqlite3, config
src = sqlite3.connect(config.CHEMIN_BD); dst = sqlite3.connect(config.DOSSIER_DONNEES + '/sauvegarde_en_cours.db')
src.backup(dst); dst.close(); src.close()"
fi

ARCHIVE="sauvegardes/sabdi_${HORO}.tar.gz"
tar -czf "$ARCHIVE" -C "$DONNEES" --exclude=./televersements --exclude=./tmp .
[ "$EN_SERVICE" = 1 ] && docker exec -u sabdi sabdi rm -f /data/sauvegarde_en_cours.db
ok "Sauvegarde : $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
ls -1t sauvegardes/sabdi_*.tar.gz 2>/dev/null | tail -n +16 | xargs -r rm -f
