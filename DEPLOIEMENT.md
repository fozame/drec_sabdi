# Déploiement de SABDI avec Docker

## Prérequis sur le serveur

- Linux 64 bits avec Docker Engine et le module Compose (`docker compose version`).
- Git, et un accès sortant à github.com (SSH port 22 ou HTTPS 443) pour le déploiement depuis GitHub.
- 16 Go de mémoire vive conseillés : une analyse utilise environ 0,35 Go par million de lignes
  (BDI de 16 millions de lignes ≈ 6 Go). Le conteneur est limité à 13 Go (`SABDI_MEMOIRE`).
- Espace disque : environ 1 Go pour l'image, plus les données (historique, extractions,
  fichiers téléversés conservés 3 jours).
- Pour la construction de l'image : accès à Docker Hub (image `python:3.11-slim-bookworm`)
  et à PyPI, directement ou par le proxy de l'Agence. Sans accès Internet, voir
  « Serveur sans accès Internet » plus bas.

Les commandes sont à lancer depuis le dossier de SABDI, avec `sudo` si l'utilisateur
n'est pas membre du groupe `docker`.

## Déploiement depuis GitHub (recommandé)

Principe : le code est déposé dans un dépôt GitHub **privé** ; le serveur le récupère
avec `git pull` puis reconstruit le conteneur. Le dépôt ne contient que le code :
`.gitignore` exclut `.env`, `donnees/`, `depots/`, `sauvegardes/`, les bases et tous les
fichiers d'opérateurs (`.csv`, `.txt`, `.xlsx`, `.zip`).

### Une seule fois : création du dépôt (sur votre poste)

```bash
cd sabdi
git init -b main
git add .
git commit -m "SABDI 5.1.0"
git tag v5.1.0
git remote add origin git@github.com:<compte>/sabdi.git      # dépôt PRIVÉ créé sur github.com
git push -u origin main --tags
```

### Une seule fois : accès du serveur au dépôt

Sur le serveur, créer une clé de déploiement (lecture seule) :
```bash
sudo ssh-keygen -t ed25519 -f /root/.ssh/sabdi_github -N ""
sudo cat /root/.ssh/sabdi_github.pub
```
Sur GitHub : dépôt → *Settings* → *Deploy keys* → *Add deploy key*, coller la clé,
**sans** cocher « Allow write access ». Puis sur le serveur :
```bash
sudo tee -a /root/.ssh/config >/dev/null <<'FIN'
Host github-sabdi
  HostName github.com
  User git
  IdentityFile /root/.ssh/sabdi_github
  IdentitiesOnly yes
FIN
sudo git clone git@github-sabdi:<compte>/sabdi.git /opt/sabdi
cd /opt/sabdi
cp /chemin/vers/logo_art.png .          # facultatif
sudo ./scripts/deployer.sh
```

Si le port SSH (22) est fermé par le pare-feu, utiliser HTTPS avec un jeton GitHub
en lecture seule (*fine-grained token*, droit « Contents: Read-only » sur ce seul dépôt) :
`sudo git clone https://github.com/<compte>/sabdi.git /opt/sabdi` (le jeton est demandé
comme mot de passe ; `git config credential.helper store` évite de le ressaisir).

### À chaque nouvelle version

Sur votre poste :
```bash
# modifier le fichier VERSION (ex. 5.2.0), puis :
git add . && git commit -m "Version 5.2.0 : <résumé>"
git tag v5.2.0
git push && git push --tags
```
Sur le serveur :
```bash
cd /opt/sabdi && sudo ./scripts/mettre_a_jour_depuis_git.sh          # dernière version
cd /opt/sabdi && sudo ./scripts/mettre_a_jour_depuis_git.sh v5.2.0   # ou une version précise
```
Le script récupère le code, sauvegarde les données, reconstruit l'image, remplace le
conteneur et vérifie le démarrage. Si la construction échoue, l'ancienne version reste en
service. Changer le numéro du fichier `VERSION` à chaque livraison permet de revenir en
arrière avec `retour_arriere.sh`.

Ne pas modifier les fichiers directement sur le serveur : toute modification passe par le
dépôt (le script refuse de se lancer si des fichiers suivis ont été modifiés localement).
Seuls `.env`, `donnees/`, `depots/` et `sauvegardes/` sont propres au serveur.

## Première installation (sans GitHub, par copie du zip)

```bash
unzip sabdi_v5.1.zip -d /opt/        # le dossier /opt/sabdi est créé
cd /opt/sabdi
cp /chemin/vers/logo_art.png .        # facultatif : logo de l'ART
sudo ./scripts/deployer.sh
```

Le script :
1. crée le fichier `.env` à partir de `env.exemple` et génère la clé secrète ;
2. crée les dossiers `donnees/` (base, historique, extractions, logo),
   `depots/` et `sauvegardes/` ;
3. construit l'image `sabdi:<version>` et démarre le conteneur `sabdi` ;
4. vérifie que l'application répond et affiche son adresse.

Accès : `http://<adresse-du-serveur>:5600`, compte `admin` / `admin123` (ou la valeur de
`SABDI_ADMIN_PASSWORD` dans `.env` avant le premier démarrage). Changer ce mot de passe
dès la première connexion, puis créer les comptes des chargés d'analyse et de la Direction
(menu « Utilisateurs »).

Le conteneur redémarre automatiquement avec le serveur (`restart: unless-stopped`).

## Mise à jour (sans GitHub, par copie du zip)

1. Copier la nouvelle version **par-dessus** le dossier existant :
   ```bash
   unzip -o sabdi_v5.2.zip -d /opt/
   ```
   Le zip ne contient ni `.env`, ni `donnees/`, ni `sauvegardes/` : la configuration, les
   comptes et l'historique ne sont pas touchés.
2. Lancer :
   ```bash
   cd /opt/sabdi && sudo ./scripts/mettre_a_jour.sh
   ```
   Le script sauvegarde les données, construit la nouvelle image, remplace le conteneur
   (coupure de quelques secondes) et vérifie le démarrage. En cas d'échec de construction,
   l'ancienne version reste en service.

Éviter de mettre à jour pendant une analyse : elle serait interrompue et devrait être relancée.

La version en service est affichée sur la page de connexion et en bas de chaque page, et
renvoyée par `http://<serveur>:5600/sante`.

**Retour à la version précédente** (les anciennes images sont conservées) :
```bash
sudo ./scripts/retour_arriere.sh            # liste les versions disponibles
sudo ./scripts/retour_arriere.sh 5.1.0
```

## Sauvegarde et restauration

```bash
sudo ./scripts/sauvegarder.sh                                   # → sauvegardes/sabdi_AAAAMMJJ_HHMM.tar.gz
sudo ./scripts/restaurer.sh sauvegardes/sabdi_20260927_1015.tar.gz
```

La sauvegarde contient la base (comptes, historique des analyses, validations, notes du
mois), les extractions, le logo et la clé. Elle peut être faite application en service
(copie cohérente de la base). Les 15 dernières sont conservées. Pour une sauvegarde
quotidienne automatique, ajouter au `crontab` de root :

```
30 19 * * * cd /opt/sabdi && ./scripts/sauvegarder.sh >> sauvegardes/journal.log 2>&1
```

Copier régulièrement le dossier `sauvegardes/` sur un autre support.

## Fichiers des opérateurs

Deux façons de fournir les fichiers :
- **par le navigateur** (cas normal) : glisser le dossier ou l'archive .zip dans la page
  « Nouvelle analyse » ;
- **par le serveur**, pour les très gros envois : copier le dossier dans `depots/`
  (ex. `depots/MTN_MARS_2026/`), puis dans « Nouvelle analyse », option avancée, saisir
  `/depots/MTN_MARS_2026`. Ce dossier est monté en lecture seule : l'application ne
  modifie jamais les fichiers d'origine.

## Réglages (`.env`)

| Variable | Rôle | Défaut |
|----------|------|--------|
| `SABDI_PORT_HOTE` | port d'accès sur le serveur | `5600` |
| `SABDI_SECRET` | clé de session (générée ; ne plus la modifier) | – |
| `SABDI_ADMIN_PASSWORD` | mot de passe du compte `admin` au premier démarrage | `admin123` |
| `SABDI_DONNEES` | dossier des données sur le serveur | `./donnees` |
| `SABDI_DEPOTS` | dossier des fichiers déposés sur le serveur | `./depots` |
| `SABDI_MEMOIRE` | mémoire maximale du conteneur | `13g` |
| `SABDI_THREADS` | fils d'exécution du serveur web | `8` |
| `SABDI_POLARS_RUNTIME` | `rtcompat` pour un processeur ancien (voir plus bas) | vide |
| `TZ` | fuseau horaire | `Africa/Douala` |

Après modification : `sudo docker compose up -d` (ou `mettre_a_jour.sh` si
`SABDI_POLARS_RUNTIME` a changé, car l'image doit être reconstruite).

## Serveur sans accès Internet

Sur un poste Linux disposant de Docker et d'Internet :
```bash
./scripts/exporter_image.sh              # → sabdi_image_<version>.tar.gz (environ 200 Mo)
```
Copier le dossier SABDI et ce fichier sur le serveur, puis :
```bash
sudo ./scripts/charger_image.sh sabdi_image_<version>.tar.gz
```
Le même script sert aux mises à jour ultérieures (il sauvegarde les données avant).

## Proxy

Si le serveur passe par un proxy, Docker doit le connaître pour télécharger l'image de
base (`/etc/systemd/system/docker.service.d/proxy.conf`), et la construction doit le
recevoir :
```bash
export HTTP_PROXY=http://proxy.art.cm:8080 HTTPS_PROXY=http://proxy.art.cm:8080
sudo -E ./scripts/mettre_a_jour.sh
```
(adresse du proxy à adapter.)

## Dépannage

| Situation | Commande / solution |
|-----------|---------------------|
| Voir le journal | `sudo docker compose logs --tail 200 sabdi` |
| État du conteneur | `sudo docker compose ps` (colonne *healthy*) |
| Redémarrer | `sudo docker compose restart sabdi` |
| Arrêter | `sudo docker compose down` (les données sont conservées) |
| « Illegal instruction » au démarrage | processeur sans jeu d'instructions récent : mettre `SABDI_POLARS_RUNTIME=rtcompat` dans `.env` puis `sudo ./scripts/mettre_a_jour.sh` |
| Analyse interrompue, application redémarrée (mémoire) | `sudo dmesg \| grep -i "out of memory"` le confirme ; augmenter `SABDI_MEMOIRE` dans `.env` (sans dépasser la mémoire du serveur moins 2 Go) puis `sudo docker compose up -d` |
| « L'envoi a échoué » | l'envoi reprend seul après une coupure (6 essais par bloc) ; si l'échec persiste, vérifier l'espace disque (`df -h`) et que l'application tourne (`sudo docker compose ps`) |
| Mot de passe admin perdu | `sudo docker exec -it sabdi python -c "import sqlite3, config; from werkzeug.security import generate_password_hash as h; c=sqlite3.connect(config.CHEMIN_BD); c.execute('UPDATE users SET password=? WHERE username=?', (h('NouveauMotDePasse'), 'admin')); c.commit()"` |
| Logo absent | déposer `logo_art.png` dans `donnees/` (pris en compte sans redémarrage) |

## Contenu du dossier

```
Dockerfile, docker-compose.yml, env.exemple   construction et lancement
docker/entrypoint.py                           démarrage du conteneur (droits, utilisateur non root)
serveur.py                                     serveur de production (waitress)
scripts/                                       deployer, mettre_a_jour, mettre_a_jour_depuis_git, retour_arriere,
                                               sauvegarder, restaurer, exporter_image, charger_image
donnees/        (créé)                         données persistantes – à sauvegarder
depots/         (créé)                         fichiers des opérateurs déposés sur le serveur
sauvegardes/    (créé)                         archives de sauvegarde
```
