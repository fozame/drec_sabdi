"""
Jeux de test aux en-têtes EXACTS transmis par les opérateurs (septembre 2026) :

MTN (séparateur tabulation, M2M en « ; ») :
  DBI    : MSISDN NAME ID_NUMBER ID_EXPIRY_DATE BIRTH_DATE SUBSCRIPTION_DATE ADRESSE IMEI STATUT ID_TYPE
           PARENT_NAME IDTYPE_PARENT IDNUMBER_PARENT IDEXPIRYDATE_PARENT RED_LIST IS_MTN_RESERVED
  MAJOR  : MSISDN NAME ID_NUMBER ID_EXPIRY_DATE BIRTH_DATE SUBSCRIPTION_DATE ADRESSE IMEI STATUT ID_TYPE
           RED_LIST IS_MTN_RESERVED
  MINOR  : MSISDN NAME ID_NUMBER ID_EXPIRY_DATE BIRTH_DATE SUBSCRIPTION_DATE STATUT PARENT_NAME
           IDNUMBER_PARENT IDEXPIRYDATE_PARENT ADRESSE IMEI ID_TYPE_MINOR IDTYPE_PARENT RED_LIST IS_MTN_RESERVED
  POSTPAID / M2M : COMPANY TRADE_REGISTER_NUMBER PRIME_IDNUMBER ALTER_SUBSCRIPTION_DATE COMPANY_LOCATION
           ALTERNATE_MSISDN ALTER_FULLNAME ALTER_IDNUMBER ALTER_IMEI ALTER_ADRESSE STATUT SIM_TYPE RED_LIST
           IS_MTN_RESERVED
  HLR    : MSISDN,SUBSCRIBER_CAN_CALL
ORANGE :
  BDI / majeurs (tabulation / « | ») : numero_telephone nom_prenom date_naissance type_piece_identite
           numero_piece date_expiration date_souscription adresse imei statut
  flotte : numero_telephone|nom_prenom|numero_piece|imei|date_souscription|nom_structure|
           cni_representant_legal|adresse_structure|numero_registre_commerce|adresse|statut
  M2M    : nom_structure|numero_registre_commerce|cni_representant_legal|adresse_structure|numero_telephone
  mineurs: numero_telephone|type_piece_identite|numero_piece_mineur|nom_prenom_mineur|date_naissance_mineur|
           date_expiration_mineur|imei|adresse_mineur|type_piece_tuteur|numero_piece_tuteur|nom_prenom_tuteur|
           date_naissance_tuteur|date_expiration_tuteur|adresse_tuteur|date_activation|statut
  HLR    : msisdn|odbincomingcalls|odboutgoingcalls|statut

    python tests/generer_donnees_schemas.py /chemin/sortie
"""
import json
import os
import sys
from datetime import date

import numpy as np
import polars as pl

rng = np.random.default_rng(3)
NOMS = ["MBARGA", "NGONO", "FOTSO", "TCHOUA", "ABENA", "ETOA", "NJOYA", "KAMGA", "BELLO", "ATANGANA",
        "ESSOMBA", "MVONDO", "NANA", "DJOMO", "OWONA", "TAMBA", "YOUMBI", "ZE", "MOUSSA", "HAMADOU"]
PRENOMS = ["Jean", "Marie", "Paul", "Aicha", "Brice", "Chantal", "Herve", "Nadege", "Ibrahim", "Sandrine"]


def noms(n):
    return [f"{a} {b} {c}" for a, b, c in zip(rng.choice(NOMS, n), rng.choice(NOMS, n), rng.choice(PRENOMS, n))]


def dates(n, a, b, fmt):
    j = rng.integers((a - date(1970, 1, 1)).days, (b - date(1970, 1, 1)).days, n)
    s = pl.Series(j).cast(pl.Date)
    return (s.cast(pl.Datetime) if "%H" in fmt else s).dt.strftime(fmt).to_list()


def pieces(n):
    return [f"{v:09d}" if rng.random() < .4 else f"1{v:09d}" for v in rng.integers(10**8, 10**9, n)]


def ecrire(df, chemin, sep):
    df.write_csv(chemin, separator=sep)


def mtn(d, n=40_000):
    os.makedirs(d, exist_ok=True)
    v = {}
    msisdn = np.arange(677_000_000, 677_000_000 + n).astype(str)
    nmaj = int(n * .97)
    nmin = n - nmaj
    statut = rng.choice(["ACTIF", "SUSPENDU"], n, p=[.95, .05])
    base = {
        "MSISDN": msisdn, "NAME": noms(n), "ID_NUMBER": pieces(n),
        "ID_EXPIRY_DATE": dates(n, date(2019, 1, 1), date(2034, 1, 1), "%d/%m/%Y"),
        "BIRTH_DATE": dates(nmaj, date(1950, 1, 1), date(2006, 1, 1), "%d/%m/%Y")
        + dates(nmin, date(2010, 3, 1), date(2014, 1, 1), "%d/%m/%Y"),
        "SUBSCRIPTION_DATE": dates(n, date(2015, 1, 1), date(2026, 3, 1), "%d/%m/%Y %H:%M:%S"),
        "ADRESSE": ["DOUALA"] * n, "IMEI": [f"86{x:013d}" for x in rng.integers(0, 10**13, n)],
        "STATUT": statut.tolist(),
    }
    typ = rng.choice(["nationalid", "bionationalid", "passport", "tempid"], n, p=[.55, .3, .05, .1]).tolist()
    parent_nom = [""] * nmaj + noms(nmin)
    parent_type = [""] * nmaj + rng.choice(["nationalid", "birthcertificate"], nmin, p=[.9, .1]).tolist()
    parent_num = [""] * nmaj + pieces(nmin)
    parent_exp = [""] * nmaj + dates(nmin, date(2020, 1, 1), date(2032, 1, 1), "%d/%m/%Y")
    # anomalies : tuteurs manquants, pièces du tuteur expirées, listes rouges, numéros réservés
    for i in range(nmaj, nmaj + 30):
        parent_nom[i] = ""
    red = rng.choice(["N", "Y"], n, p=[.99, .01]).tolist()
    res = rng.choice(["N", "Y"], n, p=[.995, .005]).tolist()
    v.update({"mineurs": nmin, "red_list": red.count("Y"), "reserves": res.count("Y"),
              "parents_absents": 30})

    dbi = pl.DataFrame({**base, "ID_TYPE": typ, "PARENT_NAME": parent_nom, "IDTYPE_PARENT": parent_type,
                        "IDNUMBER_PARENT": parent_num, "IDEXPIRYDATE_PARENT": parent_exp,
                        "RED_LIST": red, "IS_MTN_RESERVED": res})
    ecrire(dbi, f"{d}/TRB_DUMP_ENTIRE_DBI_2026MAR.txt", "\t")
    maj = dbi.head(nmaj).select(["MSISDN", "NAME", "ID_NUMBER", "ID_EXPIRY_DATE", "BIRTH_DATE", "SUBSCRIPTION_DATE",
                                 "ADRESSE", "IMEI", "STATUT", "ID_TYPE", "RED_LIST", "IS_MTN_RESERVED"])
    ecrire(maj, f"{d}/TRB_DUMP_MAJEUR2026MAR.txt", "\t")
    mino = dbi.tail(nmin).rename({"ID_TYPE": "ID_TYPE_MINOR"}).select(
        ["MSISDN", "NAME", "ID_NUMBER", "ID_EXPIRY_DATE", "BIRTH_DATE", "SUBSCRIPTION_DATE", "STATUT", "PARENT_NAME",
         "IDNUMBER_PARENT", "IDEXPIRYDATE_PARENT", "ADRESSE", "IMEI", "ID_TYPE_MINOR", "IDTYPE_PARENT", "RED_LIST",
         "IS_MTN_RESERVED"])
    ecrire(mino, f"{d}/TRB_DUMP_MINOR_2026MAR.txt", "\t")

    def morale(m, debut, sim):
        num = np.arange(debut, debut + m).astype(str)
        return num, pl.DataFrame({
            "COMPANY": ["BRASSERIES"] * m, "TRADE_REGISTER_NUMBER": ["RC/DLA/1948/B/12"] * m, "PRIME_IDNUMBER": num,
            "ALTER_SUBSCRIPTION_DATE": dates(m, date(2016, 1, 1), date(2026, 3, 1), "%d/%m/%Y"),
            "COMPANY_LOCATION": ["DOUALA"] * m, "ALTERNATE_MSISDN": [""] * m, "ALTER_FULLNAME": noms(m),
            "ALTER_IDNUMBER": pieces(m), "ALTER_IMEI": [f"86{x:013d}" for x in rng.integers(0, 10**13, m)],
            "ALTER_ADRESSE": ["DOUALA"] * m, "STATUT": rng.choice(["ACTIF", "SUSPENDU"], m, p=[.95, .05]).tolist(),
            "SIM_TYPE": rng.choice(sim, m).tolist(), "RED_LIST": ["N"] * m, "IS_MTN_RESERVED": ["N"] * m})
    n_post, post = morale(800, 678_000_000, ["VOICE", "DATA"])
    n_m2m, m2m = morale(300, 679_000_000, ["M2M"])
    ecrire(post, f"{d}/TRB_POSTPAID_DATABASE_2026MAR.txt", "\t")
    ecrire(m2m, f"{d}/TRB_POSTPAID_DB_M2M_2026MAR.csv", ";")

    # HLR : statut cohérent sauf 150 lignes suspendues dans la BDI mais actives au réseau
    tous = np.concatenate([msisdn, n_post, n_m2m])
    st_bdi = np.concatenate([statut, post["STATUT"].to_numpy(), m2m["STATUT"].to_numpy()])
    can = np.where(st_bdi == "ACTIF", "True", "False")
    idx_susp = np.where(st_bdi[:n] == "SUSPENDU")[0][:150]
    can[idx_susp] = "True"
    v["suspendu_bdi_actif_hlr"] = len(idx_susp)
    ecrire(pl.DataFrame({"MSISDN": ["237" + x for x in tous], "SUBSCRIBER_CAN_CALL": can}),
           f"{d}/TRB_DUMP_HLR_2026MAR.csv", ",")
    json.dump(v, open(f"{d}/_verite.json", "w"), indent=1)
    print("MTN", v)


def orange(d, n=40_000):
    os.makedirs(d, exist_ok=True)
    v = {}
    msisdn = np.arange(655_500_000, 655_500_000 + n).astype(str)
    statut = rng.choice(["ACTIF", "SUSPENDU", "RESILIE"], n, p=[.93, .05, .02])
    cols = {
        "numero_telephone": msisdn, "nom_prenom": noms(n),
        "date_naissance": dates(n, date(1950, 1, 1), date(2006, 1, 1), "%Y-%m-%d"),
        "type_piece_identite": rng.choice(["CNI", "NOUVELLE_CNI", "ANCIENNE_CNI", "PASSEPORT"], n).tolist(),
        "numero_piece": pieces(n), "date_expiration": dates(n, date(2019, 1, 1), date(2034, 1, 1), "%Y-%m-%d"),
        "date_souscription": dates(n, date(2015, 1, 1), date(2026, 3, 1), "%Y-%m-%d %H:%M:%S"),
        "adresse": ["YAOUNDE"] * n, "imei": [f"35{x:013d}" for x in rng.integers(0, 10**13, n)],
        "statut": statut.tolist(),
    }
    bdi = pl.DataFrame(cols)
    ecrire(bdi, f"{d}/AbonneesBDI_OCM_Mars2026.txt", "\t")
    ecrire(bdi, f"{d}/Personnes_Majeurs_OCM_Mars2026.txt", "|")
    # mineurs : 30 tuteurs eux-mêmes mineurs, 40 pièces de tuteur expirées
    m = 600
    num_min = np.arange(656_000_000, 656_000_000 + m).astype(str)
    naiss_tut = dates(m, date(1965, 1, 1), date(1995, 1, 1), "%Y-%m-%d")
    for i in range(30):
        naiss_tut[i] = "2011-05-10"
    exp_tut = dates(m, date(2027, 1, 1), date(2033, 1, 1), "%Y-%m-%d")
    for i in range(30, 70):
        exp_tut[i] = "2024-01-15"
    mineurs = pl.DataFrame({
        "numero_telephone": num_min, "type_piece_identite": rng.choice(["ACTE_NAISSANCE", "CNI"], m).tolist(),
        "numero_piece_mineur": pieces(m), "nom_prenom_mineur": noms(m),
        "date_naissance_mineur": dates(m, date(2009, 6, 1), date(2014, 1, 1), "%Y-%m-%d"),
        "date_expiration_mineur": dates(m, date(2025, 1, 1), date(2032, 1, 1), "%Y-%m-%d"),
        "imei": [f"35{x:013d}" for x in rng.integers(0, 10**13, m)], "adresse_mineur": ["DOUALA"] * m,
        "type_piece_tuteur": ["CNI"] * m, "numero_piece_tuteur": pieces(m), "nom_prenom_tuteur": noms(m),
        "date_naissance_tuteur": naiss_tut, "date_expiration_tuteur": exp_tut, "adresse_tuteur": ["DOUALA"] * m,
        "date_activation": dates(m, date(2022, 1, 1), date(2026, 3, 1), "%Y-%m-%d"),
        "statut": ["ACTIF"] * m})
    ecrire(mineurs, f"{d}/Personnes_Mineurs_OCM_Mars2026.txt", "|")
    v.update({"tuteurs_mineurs": 30, "pieces_tuteur_expirees": 40})
    f = 1500
    num_f = np.arange(657_000_000, 657_000_000 + f).astype(str)
    flotte = pl.DataFrame({
        "numero_telephone": num_f, "nom_prenom": noms(f), "numero_piece": pieces(f),
        "imei": [f"35{x:013d}" for x in rng.integers(0, 10**13, f)],
        "date_souscription": dates(f, date(2016, 1, 1), date(2026, 3, 1), "%Y-%m-%d"),
        "nom_structure": ["SOCIETE ALPHA"] * f, "cni_representant_legal": pieces(f),
        "adresse_structure": ["AKWA"] * f, "numero_registre_commerce": ["RC/DLA/2015/B/1"] * f,
        "adresse": ["DOUALA"] * f, "statut": ["ACTIF"] * f})
    ecrire(flotte, f"{d}/LignesFlottes_OCM_Mars2026.txt", "|")
    k = 2000
    num_k = np.arange(658_000_000, 658_000_000 + k).astype(str)
    ecrire(pl.DataFrame({"nom_structure": ["ENEO"] * k, "numero_registre_commerce": ["RC/YAO/1"] * k,
                         "cni_representant_legal": pieces(k), "adresse_structure": ["YAOUNDE"] * k,
                         "numero_telephone": num_k}), f"{d}/LignesM2M_OCM_Mars2026.txt", "|")
    # HLR : 120 lignes suspendues/résiliées dans la BDI mais actives au réseau
    tous = np.concatenate([msisdn, num_min, num_f, num_k])
    st = np.concatenate([statut, np.array(["ACTIF"] * (m + f + k))])
    odb_in = np.where(st == "ACTIF", "0", "1")
    odb_out = np.where(st == "ACTIF", "0", "1")
    hs = np.where(st == "RESILIE", "ELIGIBLE_REATTRIBUTION", "ACTIF")
    idx = np.where(st[:n] != "ACTIF")[0][:120]
    odb_in[idx], odb_out[idx], hs[idx] = "0", "0", "ACTIF"
    v["suspendu_bdi_actif_hlr"] = len(idx)
    lignes = ["msisdn|odbincomingcalls|odboutgoingcalls|statut"] + [
        f"237{a}|{b}|{c}|{e}" for a, b, c, e in zip(tous, odb_in, odb_out, hs)]
    open(f"{d}/DonneesHLR_OCM_Mars2026.txt", "w").write("\n".join(lignes))
    json.dump(v, open(f"{d}/_verite.json", "w"), indent=1)
    print("ORANGE", v)


if __name__ == "__main__":
    sortie = sys.argv[1] if len(sys.argv) > 1 else "donnees_schemas"
    mtn(os.path.join(sortie, "MTN_MARS_2026"))
    orange(os.path.join(sortie, "OCM_MARS_2026"))
