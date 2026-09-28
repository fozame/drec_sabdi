#!/usr/bin/env bash
# Serveur sans accès Internet : charge l'image exportée puis démarre (installation ou mise à jour).
#   ./scripts/charger_image.sh sabdi_image_5.1.0.tar.gz
source "$(dirname "$0")/_commun.sh"
F="${1:-sabdi_image_${VERSION_CODE}.tar.gz}"
[ -f "$F" ] || { err "Fichier introuvable : $F"; exit 1; }
gunzip -c "$F" | docker load
if [ ! -f .env ]; then
  creer_env
elif [ "$(lire_env SABDI_SECRET)" = "a-remplacer-sur-le-serveur" ]; then
  ecrire_env SABDI_SECRET "$(head -c 48 /dev/urandom | od -An -tx1 | tr -d ' \n')"
fi
DONNEES="$(dossier_donnees)"; mkdir -p "$DONNEES" ./depots sauvegardes
[ -f logo_art.png ] && [ ! -f "$DONNEES/logo_art.png" ] && cp logo_art.png "$DONNEES/"
[ -n "$(ls -A "$DONNEES" 2>/dev/null | grep -v logo_art.png)" ] && ./scripts/sauvegarder.sh || true
ecrire_env SABDI_VERSION "$VERSION_CODE"
$DC up -d --no-build
attendre_demarrage && ok "SABDI $VERSION_CODE est en service sur le port $(port_hote)." || { err "L'application ne répond pas."; exit 1; }
