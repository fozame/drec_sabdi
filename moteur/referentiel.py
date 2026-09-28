"""
referentiel.py
──────────────
Référentiel modifiable du moteur d'analyse : rôles des fichiers, synonymes de
colonnes, mois, statuts, valeurs sentinelles et règles de contrôle.

Toute la tolérance aux variations d'écriture (noms de fichiers, en-têtes de
colonnes, libellés de statut) est paramétrée ici. Pour prendre en compte une
nouvelle écriture transmise par un opérateur, il suffit en général d'ajouter
un synonyme dans la liste correspondante (en minuscules, sans accents).
"""

# ═════════════════════════════════════════════════════════════════════════════
# PARAMÈTRES D'ANALYSE
# ═════════════════════════════════════════════════════════════════════════════

AGE_MAJORITE = 18          # années
DELAI_EXPIRATION_MOIS = 6  # pièce expirée depuis au moins N mois
DELAI_ECHEANCE_MOIS = 6    # pièce arrivant à expiration dans les N prochains mois
MAX_MODULES = 3            # seuil « plus de N modules (SIM) par personne »
ANNEE_MIN_NAISSANCE = 1900
IMEI_LONGUEURS_VALIDES = (14, 15, 16)


# ═════════════════════════════════════════════════════════════════════════════
# RÔLES DES FICHIERS
# ═════════════════════════════════════════════════════════════════════════════
# L'ordre compte : le premier rôle dont un mot-clé apparaît dans le nom du
# fichier est retenu (« POSTPAID_DB_M2M » doit être classé M2M avant FLOTTE).

ROLES = {
    "HLR": "HLR (parc des numéros)",
    "M2M": "Personnes morales – M2M",
    "MINEURS": "Personnes physiques mineures",
    "MAJEURS": "Personnes physiques majeures",
    "FLOTTE": "Personnes morales – Flotte",
    "BDI": "Base d'identification (personnes physiques)",
    "IGNORE": "Non utilisé",
}

MOTS_CLES_ROLES = [
    ("HLR", ["hlr", "hss", "parc", "donneeshlr"]),
    ("M2M", ["m2m", "iot", "machine"]),
    ("MINEURS", ["mineur", "mineurs", "minor", "minors", "minr", "enfant", "enfants"]),
    ("MAJEURS", ["majeur", "majeurs", "major", "majors", "adulte", "adultes", "adult"]),
    ("FLOTTE", ["flotte", "flottes", "flote", "fleet", "postpaid", "corporate",
                "entreprise", "entreprises", "morale", "morales", "b2b", "lignesflottes"]),
    ("BDI", ["bdi", "dbi", "abonne", "abonnes", "abonnees", "subscriber", "subscribers",
             "entire", "identification", "kyc", "prepaid", "physique", "physiques"]),
]

LIBELLES_OPERATEURS = {
    "ORANGE": "Orange Cameroun",
    "MTN": "MTN Cameroon",
    "CAMTEL": "CAMTEL",
    "NEXTTEL": "Nexttel",
}
MOTS_CLES_OPERATEURS = [
    ("ORANGE", ["ocm", "orange"]),
    ("MTN", ["mtn", "trb"]),
    ("CAMTEL", ["camtel", "blue"]),
    ("NEXTTEL", ["nexttel", "viettel"]),
]


# ═════════════════════════════════════════════════════════════════════════════
# COLONNES CANONIQUES ET SYNONYMES
# ═════════════════════════════════════════════════════════════════════════════
# Les en-têtes sont comparés après normalisation : minuscules, sans accents,
# tout caractère non alphanumérique remplacé par « _ ».
# Résolution : 1) correspondance exacte avec un synonyme (dans l'ordre),
#              2) règle « contient » (mots obligatoires / mots exclus),
#              3) rapprochement approximatif (difflib, seuil 0,86).

LIBELLES_CHAMPS = {
    "msisdn": "Numéro de téléphone",
    "statut": "Statut",
    "nom": "Nom et prénom",
    "type_piece": "Type de pièce",
    "numero_piece": "Numéro de pièce",
    "date_naissance": "Date de naissance",
    "date_expiration": "Date d'expiration de la pièce",
    "adresse": "Adresse",
    "imei": "IMEI",
    "date_activation": "Date d'activation / souscription",
    "nom_tuteur": "Nom du tuteur",
    "type_piece_tuteur": "Type de pièce du tuteur",
    "numero_piece_tuteur": "Numéro de pièce du tuteur",
    "adresse_tuteur": "Adresse du tuteur",
    "raison_sociale": "Raison sociale",
    "registre_commerce": "N° registre de commerce",
    "piece_representant": "Pièce du représentant légal",
    "sim_type": "Type de SIM",
    "date_naissance_tuteur": "Date de naissance du tuteur",
    "date_expiration_tuteur": "Date d'expiration de la pièce du tuteur",
    "liste_rouge": "Liste rouge (RED_LIST)",
    "reserve_operateur": "Numéro réservé à l'opérateur",
    "odb_entrant": "Blocage des appels entrants (ODB)",
    "odb_sortant": "Blocage des appels sortants (ODB)",
}

SYNONYMES = {
    "msisdn": ["msisdn", "numero_telephone", "num_telephone", "numero_tel", "num_tel",
               "telephone", "tel", "numero", "numero_abonne", "phone", "phone_number",
               "mobile", "msisdn_src", "numero_ligne", "ligne", "prime_idnumber",
               "alternate_msisdn"],
    "statut": ["statut", "status", "etat", "state", "statut_ligne", "statut_abonne",
               "line_status", "subscriber_status", "subscriber_can_call", "can_call",
               "statut_hlr", "hlr_status", "etat_ligne", "etat_abonne", "etat_de_la_ligne"],
    "nom": ["nom_prenom", "nom_prenoms", "noms_prenoms", "nom_et_prenom", "nom_complet",
            "name", "full_name", "fullname", "alter_fullname", "nom", "customer_name",
            "subscriber_name", "noms"],
    "type_piece": ["type_piece_identite", "type_piece", "type_de_piece", "typepiece",
                   "id_type", "type_id", "nature_piece", "document_type", "type_document",
                   "piece_type"],
    "numero_piece": ["numero_piece", "numero_piece_identite", "num_piece", "no_piece",
                     "id_number", "idnumber", "numero_id", "numero_cni", "num_cni",
                     "document_number", "alter_idnumber", "piece"],
    "date_naissance": ["date_naissance", "date_de_naissance", "birth_date", "birthdate",
                       "date_of_birth", "dob", "datenaissance", "date_naiss", "datenais", "date_nais",
                       "naissance", "birthday", "date_birth", "dt_naissance", "dte_naissance"],
    "date_expiration": ["date_expiration", "date_expiration_piece", "date_exp",
                        "id_expiry_date", "expiry_date", "expiration_date", "date_fin_validite",
                        "date_validite", "validite"],
    "adresse": ["adresse", "address", "adresse_abonne", "domicile", "localisation",
                "adresse_structure", "company_location", "alter_adresse", "ville", "quartier"],
    "imei": ["imei", "alter_imei", "imei_terminal", "code_imei"],
    "date_activation": ["date_activation", "date_souscription", "subscription_date",
                        "alter_subscription_date", "activation_date", "date_creation",
                        "date_identification"],
    "nom_tuteur": ["nom_prenom_tuteur", "nom_tuteur", "tuteur", "nom_parent", "parent_name",
                   "nom_prenom_parent", "guardian_name", "tutor_name"],
    "type_piece_tuteur": ["type_piece_tuteur", "type_piece_identite_tuteur", "idtype_parent", "id_type_parent",
                          "type_piece_parent", "guardian_id_type", "tutor_id_type"],
    "numero_piece_tuteur": ["numero_piece_tuteur", "num_piece_tuteur", "cni_tuteur", "idnumber_parent",
                            "id_number_parent", "numero_piece_parent", "guardian_id_number", "tutor_id_number"],
    "date_naissance_tuteur": ["date_naissance_tuteur", "date_naissance_parent", "birth_date_parent",
                              "parent_birth_date", "birthdate_parent"],
    "date_expiration_tuteur": ["date_expiration_tuteur", "date_expiration_parent", "idexpirydate_parent",
                               "id_expiry_date_parent", "expiry_date_parent"],
    "liste_rouge": ["red_list", "redlist", "liste_rouge", "blacklist", "black_list", "liste_noire"],
    "reserve_operateur": ["is_mtn_reserved", "is_reserved", "reserve", "numero_reserve", "is_orange_reserved",
                          "reserve_operateur"],
    "adresse_tuteur": ["adresse_tuteur", "guardian_address", "tutor_address"],
    "raison_sociale": ["nom_structure", "raison_sociale", "company", "company_name",
                       "entreprise", "structure", "denomination", "nom_entreprise", "societe"],
    "registre_commerce": ["numero_registre_commerce", "registre_commerce", "rccm",
                          "num_rccm", "trade_register_number", "trade_register", "numero_rc"],
    "piece_representant": ["cni_representant_legal", "piece_representant_legal",
                           "numero_piece_representant", "cni_representant", "representant_legal",
                           "prime_idnumber", "alter_idnumber", "legal_representative_id"],
    "sim_type": ["sim_type", "type_sim", "type_ligne", "line_type"],
    "odb_entrant": ["odbincomingcalls", "odb_incoming_calls", "odb_incoming", "odb_ic", "odbic",
                    "barring_incoming", "bar_incoming", "baic", "odb_entrant", "odb_in"],
    "odb_sortant": ["odboutgoingcalls", "odb_outgoing_calls", "odb_outgoing", "odb_oc", "odboc",
                    "barring_outgoing", "bar_outgoing", "baoc", "odb_sortant", "odb_out"],
}

# Surcharges par rôle : synonymes testés en priorité pour ce rôle.
SYNONYMES_PAR_ROLE = {
    "MINEURS": {
        "nom": ["nom_prenom_mineur", "nom_mineur", "nom_prenoms_mineur"],
        "type_piece": ["type_piece_mineur", "type_piece_identite_mineur", "id_type_minor", "idtype_minor"],
        "numero_piece": ["numero_piece_mineur", "num_piece_mineur", "id_number_minor"],
        "date_naissance": ["date_naissance_mineur", "date_de_naissance_mineur", "birth_date_minor"],
        "date_expiration": ["date_expiration_mineur", "id_expiry_date_minor", "id_expiry_date"],
        "adresse": ["adresse_mineur"],
    },
    "M2M": {
        "msisdn": ["msisdn", "numero_telephone", "prime_idnumber", "alternate_msisdn"],
        "adresse": ["adresse_structure", "company_location", "adresse", "alter_adresse"],
        "piece_representant": ["cni_representant_legal", "piece_representant_legal",
                               "alter_idnumber", "numero_piece"],
    },
    "FLOTTE": {
        "msisdn": ["msisdn", "numero_telephone", "prime_idnumber", "alternate_msisdn"],
        "adresse": ["adresse_structure", "company_location", "adresse", "alter_adresse"],
        "piece_representant": ["cni_representant_legal", "piece_representant_legal",
                               "alter_idnumber", "numero_piece"],
    },
}

# Règles « contient » : (tous ces fragments présents, aucun de ceux-ci présent)
REGLES_CONTIENT = {
    "msisdn": [(["msisdn"], []), (["tel"], ["tuteur"]), (["phone"], [])],
    "statut": [(["statut"], ["src_norm", "juridique"]), (["status"], []), (["can_call"], []),
               (["etat"], ["civil"])],
    "nom": [(["nom"], ["tuteur", "structure", "entreprise", "fichier", "parent"]),
            (["name"], ["company", "guardian", "file", "parent"])],
    "type_piece": [(["type", "piece"], ["tuteur", "parent"]), (["id", "type"], ["guardian", "tutor", "parent"])],
    "numero_piece": [(["num", "piece"], ["tuteur", "representant", "parent"]),
                     (["id", "number"], ["guardian", "tutor", "parent"])],
    "date_naissance": [(["nais"], ["tuteur", "lieu", "parent"]), (["birth"], ["place", "parent"]), (["dob"], [])],
    "date_expiration": [(["expir"], ["tuteur", "parent"]), (["expiry"], ["parent", "guardian"]), (["validite"], [])],
    "adresse": [(["adress"], ["tuteur", "mail", "ip"]), (["address"], ["guardian", "mail", "ip"])],
    "imei": [(["imei"], [])],
    "date_activation": [(["activation"], []), (["souscri"], []), (["subscri", "date"], [])],
    "nom_tuteur": [(["nom", "tuteur"], []), (["guardian", "name"], []), (["parent", "name"], [])],
    "type_piece_tuteur": [(["type", "tuteur"], []), (["type", "parent"], [])],
    "numero_piece_tuteur": [(["piece", "tuteur"], ["type"]), (["cni", "tuteur"], []), (["number", "parent"], [])],
    "adresse_tuteur": [(["adress", "tuteur"], []), (["adress", "parent"], [])],
    "date_naissance_tuteur": [(["nais", "tuteur"], []), (["birth", "parent"], [])],
    "date_expiration_tuteur": [(["expir", "tuteur"], []), (["expir", "parent"], [])],
    "liste_rouge": [(["red", "list"], []), (["liste", "rouge"], [])],
    "reserve_operateur": [(["reserv"], [])],
    "raison_sociale": [(["structure"], ["adresse", "adress"]), (["company"], ["location"]), (["raison"], [])],
    "registre_commerce": [(["registre"], []), (["rccm"], []), (["trade"], [])],
    "piece_representant": [(["representant"], []), (["legal"], [])],
    "sim_type": [(["sim", "type"], [])],
    "odb_entrant": [(["odb", "incom"], []), (["odb", "entr"], [])],
    "odb_sortant": [(["odb", "outgo"], []), (["odb", "sort"], [])],
}

# Champs recherchés selon le rôle du fichier
CHAMPS_PAR_ROLE = {
    "HLR": ["msisdn", "statut", "odb_entrant", "odb_sortant"],
    "BDI": ["msisdn", "statut", "nom", "type_piece", "numero_piece", "date_naissance",
            "date_expiration", "adresse", "imei", "date_activation",
            "nom_tuteur", "type_piece_tuteur", "numero_piece_tuteur", "date_naissance_tuteur",
            "date_expiration_tuteur", "liste_rouge", "reserve_operateur"],
    "MAJEURS": ["msisdn", "statut", "nom", "type_piece", "numero_piece", "date_naissance",
                "date_expiration", "adresse", "imei", "date_activation", "liste_rouge", "reserve_operateur"],
    "MINEURS": ["msisdn", "statut", "nom", "type_piece", "numero_piece", "date_naissance",
                "date_expiration", "adresse", "imei", "date_activation",
                "nom_tuteur", "type_piece_tuteur", "numero_piece_tuteur", "adresse_tuteur",
                "date_naissance_tuteur", "date_expiration_tuteur", "liste_rouge", "reserve_operateur"],
    "FLOTTE": ["msisdn", "statut", "raison_sociale", "registre_commerce", "piece_representant",
               "adresse", "nom", "numero_piece", "imei", "date_activation", "sim_type",
               "liste_rouge", "reserve_operateur"],
    "M2M": ["msisdn", "statut", "raison_sociale", "registre_commerce", "piece_representant",
            "adresse", "imei", "date_activation", "sim_type", "liste_rouge", "reserve_operateur"],
}

# Signatures de colonnes utilisées quand le nom du fichier ne permet pas de
# déterminer son rôle.
SIGNATURES_ROLES = {
    "MINEURS": ["tuteur", "mineur", "guardian", "minor"],
    "M2M": ["m2m"],
    "FLOTTE": ["structure", "registre", "rccm", "company", "trade_register"],
    "HLR": ["subscriber_can_call", "imsi", "hlr"],
}


# ═════════════════════════════════════════════════════════════════════════════
# PÉRIODE
# ═════════════════════════════════════════════════════════════════════════════

MOIS_NOMS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
             "août", "septembre", "octobre", "novembre", "décembre"]

# Jetons reconnus (sans accents, minuscules) → numéro du mois
MOIS_JETONS = {
    1: ["janvier", "janv", "jan", "january", "janu"],
    2: ["fevrier", "fev", "fevr", "feb", "february", "fevri"],
    3: ["mars", "mar", "march"],
    4: ["avril", "avr", "apr", "april", "avri"],
    5: ["mai", "may"],
    6: ["juin", "jun", "june"],
    7: ["juillet", "juil", "jul", "july", "juill"],
    8: ["aout", "aou", "aug", "august"],
    9: ["septembre", "sept", "sep", "september"],
    10: ["octobre", "oct", "october"],
    11: ["novembre", "nov", "november"],
    12: ["decembre", "dec", "december"],
}


# ═════════════════════════════════════════════════════════════════════════════
# STATUTS
# ═════════════════════════════════════════════════════════════════════════════
# Catégories normalisées, dans l'ordre d'affichage des colonnes « Résultats ».

CATEGORIES_STATUT = [
    ("ACTIF", "Actifs"),
    ("SUSP_EMISSION", "Suspendus en émission"),
    ("SUSP_RECEPTION", "Suspendus en réception"),
    ("SUSP_TOTAL", "Suspendus en émission et en réception"),
    ("SUSPENDU", "Suspendus"),
    ("ELIGIBLE", "Éligibles pour réattribution"),
    ("RESILIE", "Résiliés"),
    ("AUTRE", "Autres statuts"),
    ("NON_RENSEIGNE", "Statut non renseigné"),
]
LIBELLES_STATUT = dict(CATEGORIES_STATUT)
ORDRE_STATUT = [c for c, _ in CATEGORIES_STATUT]

# Libellés courts pour les en-têtes de tableau étroits
LIBELLES_STATUT_COURTS = {
    "ACTIF": "Actifs",
    "SUSP_EMISSION": "Suspendus en émission",
    "SUSP_RECEPTION": "Suspendus en réception",
    "SUSP_TOTAL": "Suspendus en émission et en réception",
    "SUSPENDU": "Suspendus",
    "ELIGIBLE": "Éligibles pour réattribution",
    "RESILIE": "Résiliés",
    "AUTRE": "Autres statuts",
    "NON_RENSEIGNE": "Non renseigné",
}

STATUT_MOTS = {
    "eligible": ["eligib", "reattrib", "recycl", "quarant"],
    "resilie": ["resili", "termin", "deactiv", "desactiv", "churn", "cancel", "annul", "ferme", "closed"],
    "suspension": ["susp", "barr", "bloq", "block", "bar_", "inactif", "inactive", "restrict", "coupe"],
    "emission": ["emission", "sortant", "outgoing", "_og", "og_", "oneway", "one_way", "sortie", "moc"],
    "reception": ["reception", "entrant", "incoming", "_ic", "ic_", "entree", "mtc"],
    "total": ["total", "twoway", "two_way", "bidirection", "complet", "emission_et_reception",
              "emission_reception"],
    "actif": ["actif", "active", "activ", "activated", "en_service", "ok", "live", "normal", "open"],
}
VRAI = {"true", "vrai", "1", "yes", "oui", "y", "o", "t"}
FAUX = {"false", "faux", "0", "no", "non", "n", "f"}


# ═════════════════════════════════════════════════════════════════════════════
# VALEURS CONSIDÉRÉES COMME NON RENSEIGNÉES
# ═════════════════════════════════════════════════════════════════════════════

VALEURS_VIDES = ["", "NA", "N/A", "N.A", "N.A.", "NAN", "NULL", "NONE", "NIL", "NEANT",
                 "NÉANT", "INCONNU", "UNKNOWN", "NR", "ND", "NON RENSEIGNE", "NON RENSEIGNÉ",
                 "RAS", "VIDE", "EMPTY", "UNDEFINED", "NIL", "#N/A", "?"]
# Chaînes composées uniquement de ces caractères (ex. « - », « 000 », « XXX »)
MOTIF_BOURRAGE = r"^[\s\-_.,;:/\\*?#0xX]*$"


# ═════════════════════════════════════════════════════════════════════════════
# TYPES DE PIÈCE
# ═════════════════════════════════════════════════════════════════════════════
# Un type de pièce est normalisé (majuscules, sans guillemets ni accents,
# séparateurs « _ », chiffres terminaux retirés : « nationalid3 » → NATIONALID).
# Les motifs ci-dessous servent aux contrôles (pièce recevable ou non).

TYPES_ACTE_NAISSANCE = ["ACTE_NAISSANCE", "ACTE_DE_NAISSANCE", "BIRTHCERTIFICATE",
                        "BIRTH_CERTIFICATE", "EXTRAIT_NAISSANCE", "ACTE"]
TYPES_NOUVELLE_CNI = ["NOUVELLE_CNI", "BIONATIONALID", "CNI_BIOMETRIQUE", "NEW_CNI"]


# ═════════════════════════════════════════════════════════════════════════════
# CRITÈRES DE MAUVAISE IDENTIFICATION
# ═════════════════════════════════════════════════════════════════════════════
# code: (libellé, type de contrôle, champ, actif par défaut)
# type « vide »  → champ non renseigné
# type « acte »  → pièce de type acte de naissance

CRITERES = {
    "MAJEURS": [
        ("nom_absent", "Nom et prénom non renseignés", "vide", "nom", True),
        ("type_piece_absent", "Type de pièce non renseigné", "vide", "type_piece", True),
        ("numero_piece_absent", "Numéro de pièce non renseigné", "vide", "numero_piece", True),
        ("acte_naissance", "Majeur identifié avec un acte de naissance", "acte", "type_piece", True),
        ("adresse_absente", "Adresse non renseignée", "vide", "adresse", False),
    ],
    "MINEURS": [
        ("nom_absent", "Nom du mineur non renseigné", "vide", "nom", True),
        ("nom_tuteur_absent", "Nom du tuteur non renseigné", "vide", "nom_tuteur", True),
        ("type_piece_tuteur_absent", "Type de pièce du tuteur non renseigné", "vide", "type_piece_tuteur", True),
        ("numero_piece_tuteur_absent", "Numéro de pièce du tuteur non renseigné", "vide", "numero_piece_tuteur", True),
        ("tuteur_acte_naissance", "Tuteur identifié avec un acte de naissance", "acte", "type_piece_tuteur", True),
        ("tuteur_mineur", "Tuteur lui-même âgé de moins de 18 ans", "tuteur_mineur", "date_naissance_tuteur", True),
        ("numero_piece_absent", "Numéro de pièce non renseigné", "vide", "numero_piece", True),
        ("date_naissance_absente", "Date de naissance non renseignée", "date_vide", "date_naissance", True),
    ],
    "FLOTTE": [
        ("nom_absent_morale", "Nom non renseigné", "vide", "nom", True),
        ("piece_absente_morale", "Numéro de pièce non renseigné", "vide", "numero_piece", True),
        ("raison_sociale_absente", "Raison sociale non renseignée", "vide", "raison_sociale", True),
        ("rccm_absent", "N° registre de commerce non renseigné", "vide", "registre_commerce", True),
        ("representant_absent", "Pièce du représentant légal non renseignée", "vide", "piece_representant", True),
        ("adresse_absente", "Adresse non renseignée", "vide", "adresse", True),
    ],
    "M2M": [
        ("nom_absent_morale", "Nom non renseigné", "vide", "nom", True),
        ("piece_absente_morale", "Numéro de pièce non renseigné", "vide", "numero_piece", True),
        ("raison_sociale_absente", "Raison sociale non renseignée", "vide", "raison_sociale", True),
        ("rccm_absent", "N° registre de commerce non renseigné", "vide", "registre_commerce", True),
        ("representant_absent", "Pièce du représentant légal non renseignée", "vide", "piece_representant", True),
        ("adresse_absente", "Adresse non renseignée", "vide", "adresse", True),
    ],
}

# Critères évalués seulement si la colonne existe (sans mention « non évalué » sinon)
CRITERES_FACULTATIFS = {"nom_absent_morale", "piece_absente_morale", "tuteur_mineur"}

# Champs dont la complétude est mesurée (annexe « Complétude des champs »)
CHAMPS_COMPLETUDE = {
    "MAJEURS": ["msisdn", "nom", "type_piece", "numero_piece", "date_naissance",
                "date_expiration", "adresse", "imei", "date_activation"],
    "MINEURS": ["msisdn", "nom", "type_piece", "numero_piece", "date_naissance", "adresse",
                "imei", "date_activation", "nom_tuteur", "type_piece_tuteur",
                "numero_piece_tuteur", "adresse_tuteur", "date_naissance_tuteur", "date_expiration_tuteur"],
    "FLOTTE": ["msisdn", "raison_sociale", "registre_commerce", "piece_representant",
               "adresse", "nom", "numero_piece", "imei", "date_activation"],
    "M2M": ["msisdn", "raison_sociale", "registre_commerce", "piece_representant",
            "adresse", "imei", "date_activation"],
}

# Champs recherchés mais dont l'absence n'est pas signalée comme anomalie
_OPTIONNELS = {"liste_rouge", "reserve_operateur"}
CHAMPS_FACULTATIFS = {
    "HLR": {"odb_entrant", "odb_sortant"},
    "BDI": {"nom_tuteur", "type_piece_tuteur", "numero_piece_tuteur", "date_naissance_tuteur",
            "date_expiration_tuteur"} | _OPTIONNELS,
    "MAJEURS": set(_OPTIONNELS),
    "MINEURS": {"date_naissance_tuteur", "date_expiration_tuteur"} | _OPTIONNELS,
    "FLOTTE": {"sim_type", "nom", "numero_piece"} | _OPTIONNELS,
    "M2M": {"sim_type"} | _OPTIONNELS,
}


# ═════════════════════════════════════════════════════════════════════════════
# CLASSEMENT DES TYPES DE PIÈCE (personnes morales présentes dans la BDI)
# ═════════════════════════════════════════════════════════════════════════════
# Types de pièce qui désignent une personne morale : les lignes correspondantes
# de la BDI sont comptées en « personnes morales » et non en personnes physiques.
# Modifiable lors de l'examen du dossier.
TYPES_PERSONNE_MORALE = ["RCCM", "REGISTRE_COMMERCE", "REGISTRE_DE_COMMERCE", "RC", "NIU",
                         "PERSONNE_MORALE", "ENTREPRISE", "PATENTE", "STATUTS", "SOCIETE",
                         "CARTE_CONTRIBUABLE", "ATTESTATION_IMMATRICULATION", "FLOTTE", "CORPORATE"]
TYPES_M2M = ["M2M", "IOT", "MACHINE"]
CATEGORIES_TYPES = {"PHYSIQUE": "Personne physique", "FLOTTE": "Personne morale (flotte)",
                    "M2M": "Personne morale (M2M)", "IGNORE": "Ne pas compter"}

# ═════════════════════════════════════════════════════════════════════════════
# SIGNAUX D'ALERTE
# ═════════════════════════════════════════════════════════════════════════════
SERIE_LONGUEUR_MIN = 10       # nombre minimal de numéros de pièce consécutifs pour une « série »
SERIE_ECART_MAX = 3           # écart maximal entre deux numéros successifs d'une série
DISTANCE_PIECES_PROCHES = 2   # caractères différents au plus entre deux numéros « proches »
AGE_MAX_PLAUSIBLE = 100
VALIDITE_MAX_ANNEES = 15      # pièce valable plus de N ans après le mois de la BD : suspect
NOMS_GENERIQUES = ["CLIENT", "CLIENTS", "XXX", "XX", "X", "TEST", "INCONNU", "ABONNE", "ABONNEE",
                   "NEANT", "NA", "AUCUN", "SANS NOM", "NOM", "PRENOM", "ORANGE", "MTN", "NEXTTEL",
                   "CAMTEL", "USER", "UTILISATEUR", "DEFAULT", "DEFAUT", "PROVISOIRE", "A COMPLETER"]
EXTRACTION_MAX_LIGNES = 200_000
