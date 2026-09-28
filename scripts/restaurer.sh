#!/usr/bin/env bash
# Restaure une sauvegarde des données.
#   ./scripts/restaurer.sh sauvegardes/sabdi_20260927_1015.tar.gz
# Le dossier des données actuel est conservé sous donnees.avant_restauration_<date>.
source "$(dirname "$0")/_commun.sh"
A="${1:-}"
[ -f "$A" ] || { echo "Usage : $0 <archive>"; ls -1t sauvegardes/*.tar.gz 2>/dev/null | head; exit 1; }
DONNEES="$(dossier_donnees)"
read -r -p "Restaurer $A ? Les données actuelles seront mises de côté. [o/N] " rep
[ "$rep" = "o" ] || [ "$rep" = "O" ] || exit 0
$DC stop sabdi
mv "$DONNEES" "${DONNEES%/}.avant_restauration_$(date +%Y%m%d_%H%M)"
mkdir -p "$DONNEES"
tar -xzf "$A" -C "$DONNEES"
# la copie cohérente de la base remplace la base éventuellement copiée en cours d'écriture
if [ -f "$DONNEES/sauvegarde_en_cours.db" ]; then
  BD="$(ls "$DONNEES"/*.db 2>/dev/null | grep -v sauvegarde_en_cours | head -1)"
  mv "$DONNEES/sauvegarde_en_cours.db" "${BD:-$DONNEES/sabdi.db}"
fi
$DC up -d --no-build
attendre_demarrage && ok "Restauration terminée." || err "L'application ne répond pas après restauration."
