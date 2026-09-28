# SABDI – Système d'analyse des bases de données d'identification des opérateurs

Agence de Régulation des Télécommunications – Direction Technique –
Sous-direction de la Gestion des Ressources Techniques.

Application web (Flask) d'analyse des fichiers d'identification transmis par
les opérateurs (Orange, MTN, Camtel, Nexttel…). Elle produit l'**état des
lieux de la base des données d'identification** au format de l'annexe
habituelle, des contrôles complémentaires, et des exports PDF, Word et Excel
prêts à imprimer.

## Installation

```bash
pip install -r requirements.txt
python run.py
```

L'application s'ouvre sur http://127.0.0.1:5600. Les collègues du réseau
utilisent l'adresse IP du poste (http://192.168.x.x:5600).

Compte initial : `admin` / `admin123` (à modifier dès la première connexion,
menu « Mot de passe »).

**Logo** : déposer le fichier `logo_art.png` dans `app/static/`. Il apparaît
dans l'en-tête de l'application, sur la page de connexion, dans l'aperçu avant
impression et dans les documents PDF, Word et Excel. Sans ce fichier, tout
fonctionne sans logo.

## Profils

| Profil | Droits |
|--------|--------|
| Administrateur | tout, y compris la gestion des comptes et la suppression d'analyses |
| Chargé d'analyse | dépôt des fichiers, analyses, observations, note mensuelle, exports |
| Direction | consultation, validation des analyses, exports ; aucune modification. Arrive directement sur la synthèse du mois |

## Validation des analyses

Une analyse est d'abord en **brouillon** : les chargés d'analyse peuvent
modifier ses observations. La Direction (ou un administrateur) la **valide** :
elle fait alors foi pour cet opérateur et ce mois, ses observations sont
verrouillées, et une analyse validée antérieurement pour le même mois passe
en « remplacée ». La synthèse du mois, la note et l'évolution utilisent
l'analyse validée (à défaut, la plus récente, signalée « non validée »).

## Synthèse du mois et note de synthèse

La page « Synthèse du mois » compare tous les opérateurs d'un même mois :
chiffres clés, évolution par rapport au mois précédent, constats principaux
établis automatiquement à partir des chiffres (formulation factuelle), et un
champ « Observations et actions proposées » rédigé par les chargés d'analyse.
Elle produit :
- la **note de synthèse d'une page** (PDF ou Word, A4 portrait) destinée à la Direction ;
- l'**annexe regroupée** du mois (tous opérateurs).

## Déroulement d'une analyse

1. **Nouvelle analyse** : glisser les fichiers reçus (fichiers isolés, dossier
   complet ou archive .zip) ou utiliser les boutons « Choisir des fichiers ou
   un .zip » / « Choisir un dossier ». Aucun chemin à saisir. L'envoi se fait
   par blocs avec barre de progression (fichiers de plusieurs Go acceptés).
   La saisie d'un chemin reste possible en « option avancée ».
2. Vérifier ce qui a été reconnu :
   - opérateur et **mois de la base** (obligatoire, déduit des noms de fichiers
     ou, à défaut, de la date de souscription la plus récente) ;
   - rôle de chaque fichier et **colonne retenue pour chaque information**,
     avec le taux de valeurs exploitables et un aperçu des premières lignes :
     toute colonne peut être corrigée dans la liste ;
   - classement des **types de pièce** : les types désignant une personne
     morale (RCCM…) sont comptés en personnes morales ;
   - **numéros comptés** : numéros présents au HLR (par défaut) ou toutes les
     lignes.
3. « Lancer l'analyse » : suivi de l'étape en cours et du journal.
4. Résultats sur six onglets : Synthèse, État des lieux, Signaux d'alerte,
   Contrôles, Complétude des champs, Fichiers et méthode.
5. Exporter en PDF, Word ou Excel, imprimer, ou télécharger les lignes
   détaillées de chaque indicateur (CSV lisible dans Excel).

## Mois de référence

Tous les âges et délais sont calculés par rapport au **mois de la base**
(année et mois), jamais à la date du jour : une base de janvier analysée en
septembre donne les mêmes résultats.

- Mineur : moins de 18 ans au mois de la base (année et mois de naissance).
- Pièce expirée depuis au moins 6 mois : mois d'expiration antérieur ou égal
  au mois de la base moins 6.
- Âge à la souscription : mois de souscription moins mois de naissance.

## Signaux d'alerte

Informations que les chiffres déclarés ne montrent pas, chacune vérifiable
ligne par ligne (téléchargement des lignes concernées) :

| Famille | Signal |
|---------|--------|
| Mineurs | Mineurs non déclarés comme tels (présents parmi les abonnés ordinaires) |
| | Mineurs identifiés avec une pièce d'adulte (CNI, passeport…) |
| | Lignes souscrites alors que l'abonné était mineur |
| | Tuteurs eux-mêmes âgés de moins de 18 ans ; pièce du tuteur expirée au mois de la base |
| Identités | Même personne (nom + date de naissance) sous plusieurs numéros de pièce, dont numéros très proches (variation volontaire probable) |
| | Personnes détenant plus de 3 numéros, comptées par identité (non biaisé par l'identifiant à 9 chiffres) |
| | Noms génériques ou incomplets (CLIENT, XXX, TEST…) |
| Pièces d'identité | Même numéro de pièce utilisé par des personnes différentes |
| | Numéros de pièce apparaissant plusieurs fois (répartition) |
| | Séries de numéros de pièce consécutifs (dont séries souscrites le même jour) |
| | Numéros de forme suspecte (111111111, 123456789, identique au téléphone…) |
| Statuts | Lignes suspendues ou résiliées dans la BDI mais actives au HLR (suspension non exécutée) |
| | Lignes actives dans la BDI mais suspendues ou résiliées au HLR, ou absentes du HLR |
| | HLR : numéros éligibles à la réattribution sans aucun blocage ; numéros « actifs » mais bloqués (ODB) |
| Dates | Pièce déjà expirée à la date de souscription |
| | Dates incohérentes (âge > 100 ans, souscription avant la naissance…) |
| | Dates de naissance sur-représentées (valeurs par défaut) |

La comparaison des statuts BDI / HLR suppose que la BDI comporte une colonne
de statut ; à défaut, l'application l'indique.

Une même personne est reconnue par son nom (mots dans n'importe quel ordre,
sans accents ni ponctuation) et sa date de naissance. Les seuils (longueur des
séries, distance entre numéros proches…) sont dans `moteur/referentiel.py`.

## Traçabilité

L'onglet « Fichiers et méthode » montre, pour chaque catégorie, le passage du
nombre de lignes reçues au chiffre du tableau : lignes classées en personnes
morales, lignes hors HLR, dates de naissance inexploitables, etc. Les valeurs
de statut reçues (y compris les blocages ODB du HLR) et la catégorie retenue
sont listées.

## Tolérance aux écritures

- **Noms de fichiers** : la période et l'opérateur sont reconnus quelle que
  soit l'écriture (`JANV26`, `2026JAN`, `Janvier`, `Février_2026`, `202602`,
  `02-2026`, `sept-25`, `OCM`, `TRB`…).
- **Rôle des fichiers** : déduit du nom (`HLR`, `BDI`/`DBI`, `MAJEUR`/`MAJOR`,
  `MINEUR`/`MINOR`, `FLOTTE`/`POSTPAID`, `M2M`) puis, à défaut, des colonnes.
- **Colonnes** : rapprochement sans tenir compte des majuscules, accents,
  espaces et ponctuation (`Numéro Téléphone`, `numero_telephone`, `MSISDN`,
  `N° Tél` désignent le même champ), puis par règles de contenu et par
  similarité.
- **Ligne d'en-tête** : détectée même si elle n'est pas la première ligne ;
  fichier sans en-tête accepté (numéro et dates reconnus par leur contenu).
- **Statut HLR** : colonne de statut et/ou indicateurs de blocage
  (`odbincomingcalls`, `odboutgoingcalls`, `SUBSCRIBER_CAN_CALL`…).
- **Valeurs** : numéros avec ou sans indicatif 237, dates dans tous les
  formats courants (`03/05/2021`, `2021-05-03`, `03-MAY-21`…), statuts
  (`ACTIF`, `True`, `SUSPENDU_SORTANT`, `Barred OG`…), types de pièce
  (`'ANCIENNE_CNI'`, `nationalid3` → `NATIONALID`), fichiers en UTF-8 ou
  Windows-1252, séparateurs `;` `,` tabulation `|`, fichiers Excel.

### Schémas vérifiés

Les colonnes suivantes, transmises par les opérateurs, sont reconnues sans
réglage :

- **MTN** – DBI, MAJOR, MINOR (`ID_TYPE_MINOR`, `PARENT_NAME`,
  `IDTYPE_PARENT`, `IDNUMBER_PARENT`, `IDEXPIRYDATE_PARENT`), POSTPAID
  (`COMPANY`, `TRADE_REGISTER_NUMBER`, `PRIME_IDNUMBER`, `ALTER_*`,
  `SIM_TYPE`), M2M, HLR (`MSISDN`, `SUBSCRIBER_CAN_CALL`), ainsi que
  `RED_LIST` et `IS_MTN_RESERVED`.
- **Orange** – BDI, majeurs, mineurs (champs `_mineur` et `_tuteur`, dont
  `date_naissance_tuteur` et `date_expiration_tuteur`), flotte, M2M, HLR
  (`msisdn`, `odbincomingcalls`, `odboutgoingcalls`, `statut`).

Colonnes lues mais non exploitées : `ALTERNATE_MSISDN`, `ALTER_ADRESSE`,
`adresse` du fichier flotte Orange. `RED_LIST` et `IS_MTN_RESERVED` sont
décomptés dans les contrôles (famille « Particularités opérateur ») sans
modifier les chiffres de l'état des lieux.

Pour une écriture nouvelle non reconnue, ajouter le synonyme dans
`moteur/referentiel.py` (listes `SYNONYMES`, `MOTS_CLES_ROLES`, `MOIS_JETONS`,
`STATUT_MOTS`).

## Indicateurs de l'état des lieux

| N° | Indicateur |
|----|------------|
| 1 | Nombre de numéros d'abonnés (HLR) |
| 2–3 | Personnes morales : flotte, M2M |
| 4–7 | Personnes physiques majeures et mineures par type de pièce, avec totaux |
| 8–11 | Mal identifiés : adultes, mineurs, flotte, M2M (détail des critères en observation) |
| 12–13 | Personnes détenant plus de trois modules d'identité d'abonné |
| 14 | Numéros dont la pièce est expirée depuis au moins 6 mois |
| 15 | Pièces mutilées ou illisibles (non évaluable sans pièces numérisées) |

Les colonnes de résultats reprennent les statuts effectivement présents dans
les données : Actifs, Suspendus en émission, en réception, en émission et en
réception, Suspendus, Éligibles pour réattribution, Résiliés.

Les **contrôles complémentaires** portent sur la couverture HLR (numéros sans
identification), les doublons, les statuts divergents fichier / HLR, la
cohérence des âges, les pièces (actes de naissance, échéances, identifiants à
9 chiffres), les types de SIM, les lignes en liste rouge ou réservées à l'opérateur et
l'écart BDI / fichiers majeurs + mineurs.

Les critères de mauvaise identification et les seuils (âge de la majorité,
délais, nombre de modules) sont paramétrés dans `moteur/referentiel.py`.

## Historique et annexes

- Chaque analyse est conservée intégralement : elle peut être rouverte,
  réexportée et ses observations modifiées (onglet « État des lieux »,
  bouton « Modifier les observations »).
- **Historique** : cocher plusieurs analyses pour produire une annexe
  regroupée (sections I, II…, numérotation continue ou non), en PDF, Word,
  Excel ou aperçu avant impression.
- **Évolution** : comparaison des principaux indicateurs d'un mois à l'autre
  pour un opérateur.

## Configuration

Variables d'environnement facultatives :

| Variable | Rôle | Défaut |
|----------|------|--------|
| `SABDI_DB` | chemin de la base SQLite | `data/sabdi.db` |
| `SABDI_DATA` | dossier des données de l'application | `data/` |
| `SABDI_PORT` | port d'écoute | `5600` |
| `SABDI_DOSSIER` | dossier proposé par défaut (option avancée) | – |

Les anciens noms (`SABDI_…`) et l'ancien fichier `data/sgrna.db` restent reconnus.
Pour conserver les comptes de la toute première version, pointer `SABDI_DB` vers
l'ancienne base (`sgrna_users.db`) : les mots de passe existants restent
valables et sont renforcés à la première connexion. L'en-tête des documents
(`ORGANISME`) se modifie dans `config.py`.

## Structure

```
run.py              lancement
config.py           configuration
moteur/             analyse (indépendante de l'interface)
  referentiel.py    synonymes, statuts, critères, seuils
  detection.py      examen du dossier, rôles, période, colonnes
  lecture.py        lecture compacte des fichiers
  normalisation.py  numéros, dates, statuts, types de pièce
  analyse.py        état des lieux, contrôles, complétude, synthèse
exports/            PDF, Word, Excel (modèle commun : modele.py)
app/                application web (routes, gabarits, style)
tests/              générateur de données fictives et essais
```

Essais sans données réelles :

```bash
python tests/generer_donnees.py /tmp/donnees_test            # fichiers séparés
python tests/generer_donnees_reelles.py /tmp/donnees_reelles  # BDI + HLR, anomalies connues
python tests/essai_moteur.py /tmp/donnees_test/OCM_FEVRIER_2026
python tests/essai_application.py /tmp/donnees_test/OCM_FEVRIER_2026 /tmp/donnees_test/MTN_AVRIL_2026
```

## Performances

Mesuré avec les signaux et extractions : 6 millions de lignes BDI + 6 millions
de lignes HLR en 80 secondes environ et 3,2 Go de mémoire. Pour une base de
12 millions de numéros, compter 3 minutes environ et 6 Go de mémoire.
