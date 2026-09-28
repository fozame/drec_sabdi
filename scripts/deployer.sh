#!/usr/bin/env bash
# Première installation de SABDI sur le serveur.
#   ./scripts/deployer.sh
source "$(dirname "$0")/_commun.sh"

command -v docker >/dev/null || { err "Docker n'est pas installé."; exit 1; }

# 1. Fichier de configuration
creer_env
[ -n "$(lire_env SABDI_SECRET)" ] || { err "SABDI_SECRET est vide dans .env."; exit 1; }
ecrire_env SABDI_VERSION "$VERSION_CODE"

# 2. Dossiers persistants
DONNEES="$(dossier_donnees)"
mkdir -p "$DONNEES" "$(lire_env SABDI_DEPOTS || echo ./depots)" sauvegardes
if [ -f logo_art.png ] && [ ! -f "$DONNEES/logo_art.png" ]; then
  cp logo_art.png "$DONNEES/logo_art.png"
  info "Logo copié dans $DONNEES/logo_art.png."
fi
[ -f "$DONNEES/logo_art.png" ] || [ -f app/static/logo_art.png ] || \
  info "Logo absent : déposer logo_art.png dans $DONNEES/ (pris en compte sans redémarrage)."

# 3. Construction et démarrage
info "Construction de l'image sabdi:$VERSION_CODE…"
$DC build
$DC up -d
info "Démarrage…"
if attendre_demarrage; then
  ok "SABDI $VERSION_CODE est en service : http://$(hostname -I 2>/dev/null | awk '{print $1}'):$(port_hote)"
  if [ ! -f "$DONNEES/.installe" ]; then
    touch "$DONNEES/.installe"
    info "Compte initial : admin / (mot de passe SABDI_ADMIN_PASSWORD du fichier .env). À changer à la première connexion."
  fi
else
  err "L'application ne répond pas. Journal : $DC logs --tail 100 sabdi"
  exit 1
fi
