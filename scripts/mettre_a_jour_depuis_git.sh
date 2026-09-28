#!/usr/bin/env bash
# Récupère la dernière version depuis le dépôt Git (GitHub) puis met à jour le conteneur.
#   sudo ./scripts/mettre_a_jour_depuis_git.sh            (branche en cours)
#   sudo ./scripts/mettre_a_jour_depuis_git.sh v5.2.0     (version étiquetée précise)
# Le bloc entre accolades est lu en entier avant exécution : le script peut donc
# être lui-même modifié par la mise à jour sans incident.
{
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .git ] || { echo "Ce dossier n'est pas un clone Git." >&2; exit 1; }
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "Des fichiers suivis ont été modifiés sur le serveur :" >&2
  git status --short --untracked-files=no >&2
  echo "Annuler ces modifications (git checkout -- .) ou les reporter dans le dépôt, puis relancer." >&2
  exit 1
fi
AVANT="$(git rev-parse --short HEAD)"
git fetch --tags --prune
if [ -n "${1:-}" ]; then
  git checkout --quiet "$1"
else
  git pull --ff-only
fi
APRES="$(git rev-parse --short HEAD)"
if [ "$AVANT" = "$APRES" ]; then
  echo "[SABDI] Déjà à jour ($APRES, version $(cat VERSION))."
  exit 0
fi
echo "[SABDI] Code mis à jour : $AVANT → $APRES"
git log --oneline "$AVANT..$APRES" 2>/dev/null | head -20 || true
exec ./scripts/mettre_a_jour.sh
}
