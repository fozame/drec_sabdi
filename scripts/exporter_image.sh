#!/usr/bin/env bash
# Pour un serveur SANS accès Internet : construire l'image sur un poste connecté,
# l'exporter dans un fichier, puis la charger sur le serveur avec charger_image.sh.
#   ./scripts/exporter_image.sh      → sabdi_image_<version>.tar.gz
source "$(dirname "$0")/_commun.sh"
[ -f .env ] || { cp .env.exemple .env; ecrire_env SABDI_SECRET "a-remplacer-sur-le-serveur"; }
ecrire_env SABDI_VERSION "$VERSION_CODE"
$DC build
F="sabdi_image_${VERSION_CODE}.tar.gz"
docker save "sabdi:$VERSION_CODE" | gzip > "$F"
ok "Image exportée : $F ($(du -h "$F" | cut -f1)). Copier ce fichier avec le dossier SABDI sur le serveur."
