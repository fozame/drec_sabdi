#!/usr/bin/env bash
# Mise à jour de SABDI après copie de la nouvelle version dans ce dossier.
#   ./scripts/mettre_a_jour.sh
# Les données (dossier donnees/) et le fichier .env sont conservés.
source "$(dirname "$0")/_commun.sh"

[ -f .env ] || { err "Fichier .env absent : utiliser ./scripts/deployer.sh pour une première installation."; exit 1; }
ANCIENNE="$(lire_env SABDI_VERSION)"
info "Version en service : ${ANCIENNE:-inconnue} → nouvelle version : $VERSION_CODE"

# 1. Sauvegarde préalable des données
./scripts/sauvegarder.sh

# 2. Construction de la nouvelle image (l'ancienne reste disponible pour un retour arrière)
ecrire_env SABDI_VERSION "$VERSION_CODE"
if ! $DC build; then
  ecrire_env SABDI_VERSION "$ANCIENNE"
  err "Échec de la construction : la version $ANCIENNE reste en service."
  exit 1
fi

# 3. Remplacement du conteneur (une analyse en cours serait interrompue)
$DC up -d
if attendre_demarrage; then
  ok "SABDI $VERSION_CODE est en service."
  docker image prune -f >/dev/null 2>&1 || true
else
  err "La nouvelle version ne répond pas. Journal : $DC logs --tail 100 sabdi"
  [ -n "$ANCIENNE" ] && err "Retour à la version précédente : ./scripts/retour_arriere.sh $ANCIENNE"
  exit 1
fi
