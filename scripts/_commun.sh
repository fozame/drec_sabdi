# Fonctions communes aux scripts de déploiement SABDI (ne pas lancer directement).
set -euo pipefail
cd "$(dirname "$0")/.."

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "Docker Compose est introuvable. Installer le paquet docker-compose-plugin." >&2
  exit 1
fi

VERSION_CODE="$(tr -d '[:space:]' < VERSION)"

info()  { printf '\033[1;34m[SABDI]\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m[SABDI]\033[0m %s\n' "$*"; }
err()   { printf '\033[1;31m[SABDI]\033[0m %s\n' "$*" >&2; }

# Lit une valeur du fichier .env
lire_env() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- ; }

# Écrit (ou remplace) une valeur dans le fichier .env
ecrire_env() {
  if grep -qE "^$1=" .env; then
    sed -i "s|^$1=.*|$1=$2|" .env
  else
    echo "$1=$2" >> .env
  fi
}

port_hote() { local p; p="$(lire_env SABDI_PORT_HOTE)"; echo "${p:-5600}"; }

# Attend que l'application réponde (contrôle /sante), 120 s au plus
attendre_demarrage() {
  local port; port="$(port_hote)"
  for _ in $(seq 1 60); do
    if docker exec sabdi python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5600/sante', timeout=3)" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

dossier_donnees() { local d; d="$(lire_env SABDI_DONNEES)"; echo "${d:-./donnees}"; }

# Crée le fichier .env s'il n'existe pas (modèle env.exemple, ou valeurs par défaut)
creer_env() {
  [ -f .env ] && return 0
  if [ -f env.exemple ]; then
    cp env.exemple .env
  elif [ -f .env.exemple ]; then
    cp .env.exemple .env
  else
    cat > .env <<'FIN'
SABDI_VERSION=latest
SABDI_SECRET=
SABDI_ADMIN_PASSWORD=admin123
SABDI_PORT_HOTE=5600
SABDI_DONNEES=./donnees
SABDI_DEPOTS=./depots
SABDI_MEMOIRE=13g
SABDI_THREADS=8
SABDI_POLARS_RUNTIME=
TZ=Africa/Douala
FIN
  fi
  ecrire_env SABDI_SECRET "$(head -c 48 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  info "Fichier .env créé (clé secrète générée)."
}

# Anciennes valeurs par défaut remplacées lors d'une mise à jour
migrer_env() {
  [ -f .env ] || return 0
  if [ "$(lire_env SABDI_MEMOIRE)" = "8g" ]; then
    ecrire_env SABDI_MEMOIRE 13g
    info "Mémoire maximale portée de 8 à 13 Go (SABDI_MEMOIRE dans .env)."
  fi
}
