"""
Jeux de test reproduisant les schémas réellement reçus (BDI + HLR uniquement) :

  MTN    BDI : MSISDN, NAME, ID_NUMBER, ID_EXPIRY_DATE, BIRTH_DATE, SUBSCRIPTION_DATE, ADRESSE
         HLR : MSISDN, SUBSCRIBER_CAN_CALL
  Orange BDI : numero_telephone, nom_prenom, date_naissance, type_piece_identite, numero_piece,
               date_expiration, date_souscription, adresse
         HLR : msisdn|odbincomingcalls|odboutgoingcalls|statut

Anomalies injectées (connues, pour vérifier les signaux d'alerte) :
  mineurs non déclarés, souscriptions par des mineurs, pièces partagées entre personnes,
  même personne sous plusieurs numéros de pièce proches, séries de numéros consécutifs,
  numéros triviaux, pièce = numéro de téléphone, pièce expirée à la souscription,
  dates de naissance par défaut, noms génériques, lignes BDI hors HLR, HLR non identifiés.

    python tests/generer_donnees_reelles.py /chemin/sortie [facteur]
"""
import json
import os
import sys
from datetime import date

import numpy as np
import polars as pl

rng = np.random.default_rng(7)
NOMS = ["MBARGA", "NGONO", "FOTSO", "TCHOUA", "ABENA", "ETOA", "NJOYA", "KAMGA", "BELLO", "ATANGANA",
        "ESSOMBA", "MVONDO", "NANA", "DJOMO", "OWONA", "TAMBA", "YOUMBI", "ZE", "MOUSSA", "HAMADOU"]
PRENOMS = ["Jean", "Marie", "Paul", "Aicha", "Brice", "Chantal", "Herve", "Nadege", "Ibrahim", "Sandrine",
           "Serge", "Carine", "Alain", "Grace", "Fadimatou", "Boris", "Linda", "Yves", "Rose", "Oumarou"]


def jours(d):
    return (d - date(1970, 1, 1)).days


def dates_aleatoires(n, a, b):
    return rng.integers(jours(a), jours(b), n)


def fmt(j, style):
    s = pl.Series(j).cast(pl.Date)
    if "%H" in style:
        s = s.cast(pl.Datetime)
    return s.dt.strftime(style).to_list()


def construire(n, ref: date, operateur):
    """Population commune ; retourne un DataFrame + le registre des anomalies injectées."""
    verite = {}
    noms = [f"{a} {b} {c}" for a, b, c in zip(rng.choice(NOMS, n), rng.choice(NOMS, n), rng.choice(PRENOMS, n))]
    naiss = dates_aleatoires(n, date(1945, 1, 1), date(2005, 1, 1))
    souscr = dates_aleatoires(n, date(2012, 1, 1), jours_vers_date(jours(ref) - 5))
    expir = dates_aleatoires(n, date(2019, 1, 1), date(2034, 1, 1))
    pieces = [f"{v:09d}" if rng.random() < .35 else f"{v:010d}" for v in rng.integers(10**8, 10**9, n)]
    idx = rng.permutation(n)
    k = 0

    def prendre(m):
        nonlocal k
        sel = idx[k:k + m]
        k += m
        return sel

    # 1. Mineurs non déclarés (moins de 18 ans au mois de la BD)
    sel = prendre(int(n * .006))
    for i in sel:
        naiss[i] = jours(date(ref.year - 17, 1, 1)) + int(rng.integers(0, 3 * 365))
        souscr[i] = max(souscr[i], naiss[i] + 12 * 365)
    verite["mineurs_non_declares"] = len(sel)
    # 2. Souscription étant mineur, désormais majeur
    sel = prendre(int(n * .008))
    for i in sel:
        naiss[i] = jours(date(ref.year - 20, 6, 1)) + int(rng.integers(0, 365))
        souscr[i] = naiss[i] + 16 * 365
    verite["souscrit_mineur"] = len(sel)
    # 3. Pièce partagée par plusieurs personnes différentes (4 à 7 noms)
    sel = prendre(int(n * .01))
    groupes = np.array_split(sel, max(1, len(sel) // 5))
    for g in groupes:
        for i in g:
            pieces[i] = pieces[g[0]]
    verite["pieces_partagees_groupes"] = len(groupes)
    # 4. Même personne, numéros de pièce proches (1 chiffre modifié) pour dépasser 3 SIM
    sel = prendre(int(n * .006))
    groupes_var = np.array_split(sel, max(1, len(sel) // 6))
    for g in groupes_var:
        base = pieces[g[0]]
        for j, i in enumerate(g):
            noms[i], naiss[i] = noms[g[0]], naiss[g[0]]
            p = list(base)
            p[-1 - (j % 3)] = str((int(p[-1 - (j % 3)]) + j // 3 + (1 if j else 0)) % 10)
            pieces[i] = "".join(p) if j % 2 else base
    verite["meme_personne_plusieurs_pieces"] = len(groupes_var)
    # 5. Séries de numéros consécutifs (fabrication en série)
    sel = prendre(int(n * .004))
    series = np.array_split(sel, max(1, len(sel) // 25))
    for s in series:
        depart = int(rng.integers(10**8, 9 * 10**8))
        for j, i in enumerate(s):
            pieces[i] = str(depart + j)
    verite["series"] = len(series)
    # 6. Numéros triviaux et pièce = téléphone
    sel = prendre(60)
    for j, i in enumerate(sel):
        pieces[i] = ["111111111", "123456789", "000000001", "999999999", "12345678"][j % 5]
    verite["triviaux"] = 60
    sel_tel = prendre(40)
    verite["piece_egale_tel"] = 40
    # 7. Pièce expirée à la date de souscription
    sel = prendre(int(n * .01))
    for i in sel:
        expir[i] = souscr[i] - int(rng.integers(30, 900))
    verite["expiree_a_souscription"] = len(sel)
    # 8. Dates de naissance par défaut
    sel = prendre(int(n * .003))
    for j, i in enumerate(sel):
        naiss[i] = jours(date(1900, 1, 1)) if j % 2 else jours(date(1970, 1, 1))
    verite["naissance_defaut"] = len(sel)
    # 9. Noms génériques
    sel = prendre(80)
    for j, i in enumerate(sel):
        noms[i] = ["CLIENT", "XXX", "TEST TEST", "INCONNU", "ABONNE"][j % 5]
    verite["noms_generiques"] = 80

    df = pl.DataFrame({"nom": noms, "piece": pieces, "naiss": naiss, "souscr": souscr, "expir": expir})
    return df, verite, sel_tel


def jours_vers_date(j):
    return date(1970, 1, 1).fromordinal(date(1970, 1, 1).toordinal() + j)


def mtn(dossier, f=1.0):
    os.makedirs(dossier, exist_ok=True)
    ref = date(2026, 1, 31)
    n = int(120_000 * f)
    df, verite, sel_tel = construire(n, ref, "MTN")
    msisdn = np.arange(670_000_000, 670_000_000 + n).astype(str)
    pieces = df["piece"].to_list()
    for i in sel_tel:
        pieces[i] = msisdn[i]
    bdi = pl.DataFrame({
        "MSISDN": msisdn,
        "NAME": df["nom"],
        "ID_NUMBER": pieces,
        "ID_EXPIRY_DATE": fmt(df["expir"], "%d/%m/%Y"),
        "BIRTH_DATE": fmt(df["naiss"], "%d/%m/%Y"),
        "SUBSCRIPTION_DATE": fmt(df["souscr"], "%d/%m/%Y %H:%M:%S"),
        "ADRESSE": ["DOUALA"] * n,
    })
    hors = int(n * .02)                           # lignes BDI absentes du HLR
    num_hlr = np.concatenate([msisdn[hors:], np.arange(690_000_000, 690_000_000 + int(n * .05)).astype(str)])
    can = rng.choice(["True", "False"], len(num_hlr), p=[.96, .04])
    bdi.write_csv(f"{dossier}/BDI_MTN_JANV26.csv", separator=",")
    pl.DataFrame({"MSISDN": ["237" + m for m in num_hlr], "SUBSCRIBER_CAN_CALL": can}).write_csv(
        f"{dossier}/HLR_MTN_JANV26.csv", separator=",")
    verite.update({"bdi": n, "hlr": len(num_hlr), "bdi_hors_hlr": hors, "hlr_non_identifies": int(n * .05)})
    json.dump(verite, open(f"{dossier}/_verite.json", "w"), indent=1)
    print("MTN", verite)


def orange(dossier, f=1.0):
    os.makedirs(dossier, exist_ok=True)
    ref = date(2026, 2, 28)
    n = int(150_000 * f)
    df, verite, sel_tel = construire(n, ref, "ORANGE")
    msisdn = np.arange(655_000_000, 655_000_000 + n).astype(str)
    types = rng.choice(["CNI", "ANCIENNE_CNI", "NOUVELLE_CNI", "PASSEPORT", "CARTE_SEJOUR", "AUTRE",
                        "RCCM", "ACTE_NAISSANCE"], n, p=[.35, .3, .2, .01, .01, .07, .04, .02]).tolist()
    pieces = df["piece"].to_list()
    for i in sel_tel:
        pieces[i] = msisdn[i]
    bdi = pl.DataFrame({
        "numero_telephone": msisdn,
        "nom_prenom": df["nom"],
        "date_naissance": fmt(df["naiss"], "%Y-%m-%d"),
        "type_piece_identite": [f"'{t}'" for t in types],
        "numero_piece": pieces,
        "date_expiration": fmt(df["expir"], "%Y-%m-%d"),
        "date_souscription": fmt(df["souscr"], "%Y-%m-%d %H:%M:%S"),
        "adresse": ["YAOUNDE"] * n,
    })
    bdi.write_csv(f"{dossier}/bdi_orange_202602.txt", separator=";")
    hors = int(n * .02)
    num_hlr = np.concatenate([msisdn[hors:], np.arange(699_000_000, 699_000_000 + int(n * .05)).astype(str)])
    m = len(num_hlr)
    odb_in = rng.choice(["0", "1"], m, p=[.985, .015])
    odb_out = np.where(odb_in == "1", "1", rng.choice(["0", "1"], m, p=[.97, .03]))
    statut = rng.choice(["ACTIF", "ELIGIBLE_REATTRIBUTION"], m, p=[.93, .07])
    lignes = ["msisdn|odbincomingcalls|odboutgoingcalls|statut"] + [
        f"237{a}|{b}|{c}|{d}" for a, b, c, d in zip(num_hlr, odb_in, odb_out, statut)]
    open(f"{dossier}/hlr_orange_202602.txt", "w").write("\n".join(lignes))
    verite.update({"bdi": n, "hlr": m, "bdi_hors_hlr": hors, "hlr_non_identifies": int(n * .05),
                   "rccm": types.count("RCCM")})
    json.dump(verite, open(f"{dossier}/_verite.json", "w"), indent=1)
    print("ORANGE", verite)


if __name__ == "__main__":
    sortie = sys.argv[1] if len(sys.argv) > 1 else "donnees_reelles_test"
    fac = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    mtn(os.path.join(sortie, "MTN_JANVIER_2026"), fac)
    orange(os.path.join(sortie, "ORANGE_FEVRIER_2026"), fac)
