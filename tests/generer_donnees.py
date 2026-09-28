"""
Génère des jeux de données synthétiques reproduisant les schémas transmis par
Orange et MTN (noms de fichiers et de colonnes hétérogènes, anomalies
volontaires) afin de tester l'application sans données réelles.

    python tests/generer_donnees.py /chemin/sortie [facteur]
"""
import os
import sys
from datetime import date, timedelta

import numpy as np
import polars as pl

rng = np.random.default_rng(42)


def msisdns(n, debut):
    return np.arange(debut, debut + n).astype(str)


def dates(n, a0, a1, fmt="%Y-%m-%d"):
    j0 = (a0 - date(1970, 1, 1)).days
    j1 = (a1 - date(1970, 1, 1)).days
    jours = rng.integers(j0, j1, n)
    s = pl.Series(jours).cast(pl.Date)
    return s.dt.strftime(fmt).to_list()


def choix(valeurs, poids, n):
    p = np.array(poids, dtype=float)
    return rng.choice(valeurs, n, p=p / p.sum()).tolist()


def troue(lst, taux, valeur=""):
    m = rng.random(len(lst)) < taux
    return [valeur if x else v for v, x in zip(lst, m)]


def noms(n):
    a = ["MBARGA", "NGONO", "FOTSO", "TCHOUA", "ABENA", "ETOA", "NJOYA", "KAMGA", "BELLO", "ATANGANA"]
    b = ["Jean", "Marie", "Paul", "Aïcha", "Brice", "Chantal", "Hervé", "Nadège", "Ibrahim", "Sandrine"]
    return [f"{x} {y}" for x, y in zip(rng.choice(a, n), rng.choice(b, n))]


def pieces(n, prefixe="1"):
    """Mélange d'anciens numéros (lettres + chiffres) et de numéros à 9 chiffres."""
    anciens = [f"{prefixe}{v:010d}" for v in rng.integers(0, 10**10, n)]
    nouveaux = [f"{v:09d}" for v in rng.integers(10**8, 10**9, n)]
    m = rng.random(n) < 0.2
    return [b if x else a for a, b, x in zip(anciens, nouveaux, m)]


def ecrire(df, chemin, sep):
    df.write_csv(chemin, separator=sep)
    print(f"  {os.path.basename(chemin):45s} {df.height:>9,} lignes")


# ═════════════════════════════════════════════════════════════════════════════
def orange(dossier, f=1.0):
    os.makedirs(dossier, exist_ok=True)
    print(f"Orange → {dossier}")
    n_hlr = int(200_000 * f)
    base = 690_000_000
    num = msisdns(n_hlr, base)
    statuts = choix(["ACTIF", "SUSPENDU_EMISSION", "SUSPENDU_EMISSION_RECEPTION", "ELIGIBLE_REATTRIBUTION"],
                    [0.90, 0.02, 0.005, 0.075], n_hlr)
    hlr = pl.DataFrame({"msisdn": ["237" + m for m in num], "statut": statuts})
    ecrire(hlr, f"{dossier}/DonneesHLR_OCM_Fev26.csv", ";")

    # Répartition des numéros HLR entre catégories (+ quelques non identifiés)
    idx = rng.permutation(n_hlr)
    n_maj, n_min, n_fl, n_m2m = int(n_hlr * .70), int(n_hlr * .002), int(n_hlr * .015), int(n_hlr * .25)
    i_maj = idx[:n_maj]
    i_min = idx[n_maj:n_maj + n_min]
    i_fl = idx[n_maj + n_min:n_maj + n_min + n_fl]
    i_m2m = idx[n_maj + n_min + n_fl:n_maj + n_min + n_fl + n_m2m]
    st = np.array(statuts)

    # Majeurs
    types = ["ACTE_NAISSANCE", "ANCIENNE_CNI", "AUTRE", "CARTE_CONSULAIRE", "CARTE_MILITAIRE", "CARTE_REFUGIE",
             "CARTE_SEJOUR", "CNI", "NOUVELLE_CNI", "PASSEPORT", "TITRE_IDENTITE_PROVISOIRE"]
    poids = [0.01, 0.39, 0.066, 0.0003, 0.00005, 0.004, 0.002, 0.36, 0.155, 0.0007, 0.012]
    n = len(i_maj)
    tp = choix(types, poids, n)
    tp = [f"'{t}'" if rng.random() < 0.5 else t for t in tp]  # guillemets parasites
    piece = pieces(n)
    # Identifiants réutilisés > 3 fois (dont format 9 chiffres nouvelle CNI)
    for k in range(int(300 * f)):
        pid = f"{rng.integers(10**8, 10**9)}" if k % 2 else f"1{rng.integers(0, 10**10):010d}"
        for j in rng.integers(0, n, int(rng.integers(4, 9))):
            piece[j] = pid
    maj = pl.DataFrame({
        "Numéro Téléphone": num[i_maj],
        "Nom Prénom": troue(noms(n), 0.0004),
        "Date Naissance": dates(n, date(1940, 1, 1), date(2007, 12, 1)),
        "Type Pièce Identité": troue(tp, 0.001),
        "Numéro Pièce": troue(piece, 0.0005, "-"),
        "Date Expiration": troue(dates(n, date(2019, 1, 1), date(2035, 1, 1)), 0.01),
        "Adresse": troue(["YAOUNDE"] * n, 0.02),
        "IMEI": troue([f"35{v:013d}" for v in rng.integers(0, 10**13, n)], 0.05),
        "Date Activation": dates(n, date(2010, 1, 1), date(2026, 2, 1)),
        "Statut": st[i_maj].tolist(),
    })
    ecrire(maj, f"{dossier}/Personnes_Majeurs_OCM_Fevrier.csv", ";")
    # BDI (= majeurs + 3 % de numéros supplémentaires), en-têtes « snake_case »
    bdi = maj.rename({"Numéro Téléphone": "numero_telephone", "Nom Prénom": "nom_prenom",
                      "Date Naissance": "date_naissance", "Type Pièce Identité": "type_piece_identite",
                      "Numéro Pièce": "numero_piece", "Date Expiration": "date_expiration", "Adresse": "adresse",
                      "IMEI": "imei", "Date Activation": "date_activation", "Statut": "statut"})
    ecrire(bdi, f"{dossier}/AbonneesBDI_OCM_FEV2026.csv", ";")

    # Mineurs
    n = len(i_min)
    mineurs = pl.DataFrame({
        "numero_telephone": num[i_min],
        "nom_prenom_mineur": noms(n),
        "date_naissance_mineur": dates(n, date(2006, 1, 1), date(2014, 1, 1), "%d/%m/%Y"),
        "adresse_mineur": ["DOUALA"] * n,
        "type_piece_identite": choix(["ACTE_NAISSANCE", "NOUVELLE_CNI", "ANCIENNE_CNI", "CNI"], [.3, .5, .15, .05], n),
        "numero_piece_mineur": pieces(n, "2"),
        "nom_prenom_tuteur": troue(noms(n), 0.02),
        "type_piece_tuteur": choix(["CNI", "NOUVELLE_CNI", "ACTE_NAISSANCE", "PASSEPORT"], [.5, .4, .05, .05], n),
        "numero_piece_tuteur": troue(pieces(n), 0.01, "N/A"),
        "adresse_tuteur": ["DOUALA"] * n,
        "date_activation": dates(n, date(2020, 1, 1), date(2026, 2, 1)),
        "imei": [f"35{v:013d}" for v in rng.integers(0, 10**13, n)],
        "statut": st[i_min].tolist(),
    })
    ecrire(mineurs, f"{dossier}/Personnes_Mineurs_OCM_Fev.csv", ";")

    # Flotte (avec 50 numéros hors HLR)
    n = len(i_fl)
    fl_num = np.concatenate([num[i_fl], msisdns(50, 677_000_000)])
    n2 = len(fl_num)
    flotte = pl.DataFrame({
        "numero_telephone": fl_num,
        "nom_prenom": noms(n2),
        "numero_piece": pieces(n2),
        "imei": [f"35{v:013d}" for v in rng.integers(0, 10**13, n2)],
        "date_souscription": dates(n2, date(2015, 1, 1), date(2026, 2, 1)),
        "nom_structure": troue(["SOCIETE ALPHA SA"] * n2, 0.03),
        "cni_representant_legal": troue(pieces(n2), 0.08, "-"),
        "adresse_structure": ["DOUALA AKWA"] * n2,
        "numero_registre_commerce": troue(["RC/DLA/2015/B/1234"] * n2, 0.05),
        "adresse": troue(["DOUALA"] * n2, 0.1),
        "statut": np.concatenate([st[i_fl], np.array(["ACTIF"] * 50)]).tolist(),
    })
    ecrire(flotte, f"{dossier}/LignesFlottes_OCM_Fev.csv", ";")

    # M2M sans colonne statut (statut repris du HLR)
    n = len(i_m2m)
    m2m = pl.DataFrame({
        "NOM_STRUCTURE": ["ENEO"] * n,
        "NUMERO_REGISTRE_COMMERCE": troue(["RC/YAO/2001/B/0001"] * n, 0.0001),
        "NUMERO_PIECE": troue(pieces(n), 0.001, "-"),
        "ADRESSE": ["YAOUNDE"] * n,
        "ADRESSE_STRUCTURE": ["YAOUNDE CENTRE"] * n,
        "MSISDN": ["237" + x for x in num[i_m2m]],
    })
    ecrire(m2m, f"{dossier}/LignesM2M_OCM_Fev.csv", ",")


# ═════════════════════════════════════════════════════════════════════════════
def mtn(dossier, f=1.0):
    os.makedirs(dossier, exist_ok=True)
    print(f"MTN → {dossier}")
    n_hlr = int(150_000 * f)
    num = msisdns(n_hlr, 670_000_000)
    can = choix(["True", "False"], [0.967, 0.033], n_hlr)
    ecrire(pl.DataFrame({"MSISDN": num, "SUBSCRIBER_CAN_CALL": can}), f"{dossier}/TRB_DUMP_HLR_2026AVR.csv", ",")
    st = np.array(["ACTIF" if c == "True" else "SUSPENDU" for c in can])
    # Statut du fichier légèrement divergent du HLR
    bascule = rng.random(n_hlr) < 0.004
    st = np.where(bascule, np.where(st == "ACTIF", "SUSPENDU", "ACTIF"), st)

    idx = rng.permutation(n_hlr)
    n_phys, n_post, n_m2m = int(n_hlr * .96), int(n_hlr * .0065), int(n_hlr * .0027)
    i_phys = idx[:n_phys]
    i_post = idx[n_phys:n_phys + n_post]
    i_m2m = idx[n_phys + n_post:n_phys + n_post + n_m2m]

    n = len(i_phys)
    types = ["birthcertificate", "nationalid", "Nationalid", "nationalid3", "passport", "Passport",
             "bionationalid", "cemac", "refugeeid", "residentpermit", "residentpermit2", "tempid",
             "tempresidentpermit", ""]
    poids = [0.0002, 0.40, 0.14, 0.10, 0.003, 0.001, 0.245, 0.00001, 0.014, 0.003, 0.0004, 0.092, 0.00001, 0.0013]
    naiss = dates(n, date(1945, 1, 1), date(2007, 6, 1), "%d/%m/%Y")
    # 0,1 % de mineurs
    for j in rng.integers(0, n, int(n * 0.001)):
        naiss[j] = dates(1, date(2009, 1, 1), date(2013, 1, 1), "%d/%m/%Y")[0]
    idn = pieces(n)
    for k in range(int(120 * f)):
        pid = f"{rng.integers(10**8, 10**9)}" if k % 3 else f"1{rng.integers(0, 10**10):010d}"
        for j in rng.integers(0, n, int(rng.integers(4, 7))):
            idn[j] = pid
    phys = pl.DataFrame({
        "MSISDN": num[i_phys],
        "NAME": troue(noms(n), 0.0003),
        "ID_NUMBER": idn,
        "ID_TYPE": choix(types, poids, n),
        "ID_EXPIRY_DATE": dates(n, date(2018, 1, 1), date(2034, 1, 1), "%d/%m/%Y"),
        "BIRTH_DATE": troue(naiss, 0.0005),
        "SUBSCRIPTION_DATE": dates(n, date(2012, 1, 1), date(2026, 4, 1), "%d/%m/%Y"),
        "ADRESSE": ["DOUALA"] * n,
        "STATUT": st[i_phys].tolist(),
        "IMEI": troue([f"86{v:013d}" for v in rng.integers(0, 10**13, n)], 0.1),
    })
    ecrire(phys, f"{dossier}/TRB_DUMP_ENTIRE_DBI_2026AVR.csv", ",")
    dn = phys.with_columns(pl.col("BIRTH_DATE").str.to_date("%d/%m/%Y", strict=False).alias("_d"))
    lim = date(2026, 4, 30).replace(year=2008)
    majeurs = dn.filter(pl.col("_d") <= lim).drop("_d")
    mineurs = dn.filter(pl.col("_d") > lim).drop("_d")
    # Anomalie : 20 majeurs placés dans le fichier des mineurs, identifiés par acte de naissance
    intrus = majeurs.head(20).with_columns(pl.lit("birthcertificate").alias("ID_TYPE"))
    mineurs = pl.concat([mineurs, intrus])
    ecrire(majeurs, f"{dossier}/TRB_DUMP_MAJEUR2026AVR.csv", ",")
    ecrire(mineurs, f"{dossier}/TRB_DUMP_MINOR_2026AVR.csv", ",")

    def morale(ii, sim):
        n = len(ii)
        return pl.DataFrame({
            "COMPANY": troue(["BRASSERIES DU CAMEROUN"] * n, 0.004),
            "TRADE_REGISTER_NUMBER": troue(["RC/DLA/1948/B/0012"] * n, 0.004),
            "PRIME_IDNUMBER": num[ii],
            "ALTER_SUBSCRIPTION_DATE": dates(n, date(2016, 1, 1), date(2026, 4, 1), "%d/%m/%Y"),
            "COMPANY_LOCATION": troue(["DOUALA BASSA"] * n, 0.003),
            "ALTERNATE_MSISDN": [""] * n,
            "ALTER_FULLNAME": noms(n),
            "ALTER_IDNUMBER": troue(pieces(n), 0.003),
            "ALTER_IMEI": [f"86{v:013d}" for v in rng.integers(0, 10**13, n)],
            "ALTER_ADRESSE": ["DOUALA"] * n,
            "STATUT": st[ii].tolist(),
            "SIM_TYPE": choix(sim, [0.9, 0.1], n),
            "RED_LIST": ["N"] * n,
            "IS_MTN_RESERVED": ["N"] * n,
        })
    ecrire(morale(i_post, ["VOICE", "M2M"]), f"{dossier}/TRB_POSTPAID_DATABASE_2026AVR.csv", ",")
    ecrire(morale(i_m2m, ["M2M", "DATA"]), f"{dossier}/TRB_POSTPAID_DB_M2M_2026AVR.csv", ",")


if __name__ == "__main__":
    sortie = sys.argv[1] if len(sys.argv) > 1 else "donnees_test"
    facteur = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    orange(os.path.join(sortie, "OCM_FEVRIER_2026"), facteur)
    mtn(os.path.join(sortie, "MTN_AVRIL_2026"), facteur)
