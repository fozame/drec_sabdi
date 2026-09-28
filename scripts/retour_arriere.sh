#!/usr/bin/env bash
# Remet en service une version précédente (image déjà présente sur le serveur).
#   ./scripts/retour_arriere.sh 5.0.0
# Pour revenir aussi aux données d'avant la mise à jour : ./scripts/restaurer.sh <archive>
source "$(dirname "$0")/_commun.sh"
V="${1:-}"
if [ -z "$V" ]; then
  echo "Versions disponibles :"; docker images sabdi --format '  {{.Tag}}  ({{.CreatedSince}})'
  echo "Usage : $0 <version>"; exit 1
fi
docker image inspect "sabdi:$V" >/dev/null 2>&1 || { err "Image sabdi:$V introuvable."; exit 1; }
ecrire_env SABDI_VERSION "$V"
$DC up -d --no-build
attendre_demarrage && ok "Version $V remise en service." || { err "La version $V ne répond pas."; exit 1; }
