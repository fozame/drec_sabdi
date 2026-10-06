"""
detection.py
────────────
Examen d'un dossier de données avant analyse :
  · inventaire des fichiers exploitables (CSV, TXT, TSV, Excel) ;
  · lecture des en-têtes et détection du séparateur ;
  · détermination du rôle de chaque fichier (HLR, BDI, majeurs, mineurs,
    flotte, M2M) à partir du nom puis, à défaut, des colonnes ;
  · détection de l'opérateur et de la période (mois / année) à partir des noms
    de fichiers et du dossier, quelle que soit l'écriture (JANV26, 2026JAN,
    Février_2026, 202602, 02-2026, …) ;
  · correspondance entre les colonnes réelles et les champs attendus.
"""
from __future__ import annotations

import calendar
import difflib
import os
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import date

from . import referentiel as R

EXTENSIONS = (".csv", ".txt", ".tsv", ".dat", ".xlsx", ".xls")
SEPARATEURS = [";", ",", "\t", "|"]


# ═════════════════════════════════════════════════════════════════════════════
# NORMALISATION DE TEXTE
# ═════════════════════════════════════════════════════════════════════════════

def sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c))


def normaliser_entete(nom: str) -> str:
    """« Numéro Téléphone » → « numero_telephone »."""
    s = sans_accents(str(nom)).lower().replace("﻿", "")
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def jetons(nom: str) -> list[str]:
    """
    Découpe un nom de fichier en jetons, en séparant lettres et chiffres :
    « TRB_DUMP_MAJEUR2026JAN » → [trb, dump, majeur, 2026, jan]
    « AbonneesBDI_OCM_Janvier » → [abonnees, bdi, ocm, janvier]
    """
    s = sans_accents(nom)
    # CamelCase → mots séparés (AbonneesBDI → Abonnees BDI)
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)
    s = s.lower()
    s = re.sub(r"([a-z])([0-9])", r"\1 \2", s)
    s = re.sub(r"([0-9])([a-z])", r"\1 \2", s)
    return [t for t in re.split(r"[^a-z0-9]+", s) if t]


# ═════════════════════════════════════════════════════════════════════════════
# PÉRIODE
# ═════════════════════════════════════════════════════════════════════════════

_JETON_VERS_MOIS = {j: m for m, liste in R.MOIS_JETONS.items() for j in liste}


def _annee(jeton: str) -> int | None:
    if re.fullmatch(r"20\d{2}", jeton):
        return int(jeton)
    if re.fullmatch(r"\d{2}", jeton) and 15 <= int(jeton) <= 60:
        return 2000 + int(jeton)
    return None


def periode_depuis_nom(nom: str) -> tuple[int | None, int | None]:
    """Retourne (année, mois) déduits d'un nom, chacun pouvant être None."""
    tk = jetons(nom)
    mois = annee = None

    # 1) Mois écrit en toutes lettres ou abrégé
    for i, t in enumerate(tk):
        if t in _JETON_VERS_MOIS:
            mois = _JETON_VERS_MOIS[t]
            voisins = [tk[j] for j in (i - 1, i + 1) if 0 <= j < len(tk)]
            for v in voisins:
                a = _annee(v)
                if a:
                    annee = a
                    break
            break

    # 2) Formes numériques : 202602, 022026, 20260228, 2026 02, 02 2026
    for i, t in enumerate(tk):
        if mois is None and re.fullmatch(r"20\d{2}(0[1-9]|1[0-2])", t):
            return int(t[:4]), int(t[4:])
        if mois is None and re.fullmatch(r"(0[1-9]|1[0-2])20\d{2}", t):
            return int(t[2:]), int(t[:2])
        if mois is None and re.fullmatch(r"20\d{2}(0[1-9]|1[0-2])([0-2]\d|3[01])", t):
            return int(t[:4]), int(t[4:6])
        if mois is None and re.fullmatch(r"20\d{2}", t):
            suivant = tk[i + 1] if i + 1 < len(tk) else ""
            precedent = tk[i - 1] if i > 0 else ""
            for v in (suivant, precedent):
                if re.fullmatch(r"0?[1-9]|1[0-2]", v):
                    return int(t), int(v)

    if annee is None:
        for t in tk:
            if re.fullmatch(r"20\d{2}", t):
                annee = int(t)
                break
    return annee, mois


def detecter_periode(noms: list[str]) -> dict:
    """Vote majoritaire sur l'ensemble des noms (fichiers + dossier)."""
    votes_mois, votes_annee = Counter(), Counter()
    for n in noms:
        a, m = periode_depuis_nom(n)
        if m:
            votes_mois[m] += 1
        if a:
            votes_annee[a] += 1
    mois = votes_mois.most_common(1)[0][0] if votes_mois else None
    annee = votes_annee.most_common(1)[0][0] if votes_annee else None
    return {"mois": mois, "annee": annee,
            "certitude": "complete" if (mois and annee) else ("partielle" if (mois or annee) else "aucune")}


def libelle_periode(annee: int | None, mois: int | None) -> str:
    if mois and annee:
        return f"{R.MOIS_NOMS[mois - 1]} {annee}"
    if mois:
        return R.MOIS_NOMS[mois - 1]
    if annee:
        return str(annee)
    return "période non précisée"


def date_reference(annee: int | None, mois: int | None) -> date:
    """Dernier jour du mois analysé (date à laquelle âges et expirations sont évalués)."""
    if annee and mois:
        return date(annee, mois, calendar.monthrange(annee, mois)[1])
    return date.today()


# ═════════════════════════════════════════════════════════════════════════════
# OPÉRATEUR
# ═════════════════════════════════════════════════════════════════════════════

def detecter_operateur(noms: list[str], colonnes: list[str] | None = None) -> str | None:
    votes = Counter()
    for n in noms:
        tk = set(jetons(n))
        brut = sans_accents(n).lower()
        for code, mots in R.MOTS_CLES_OPERATEURS:
            if any(m in tk or (len(m) > 3 and m in brut) for m in mots):
                votes[code] += 1
    if not votes and colonnes:
        cols = {normaliser_entete(c) for c in colonnes}
        if "subscriber_can_call" in cols or "trade_register_number" in cols:
            votes["MTN"] += 1
        elif "odbincomingcalls" in cols or "odboutgoingcalls" in cols:
            votes["ORANGE"] += 1
        elif False:
            votes["MTN"] += 1
        elif any("tuteur" in c for c in cols) or "numero_telephone" in cols:
            votes["ORANGE"] += 1
    return votes.most_common(1)[0][0] if votes else None


def libelle_operateur(code: str | None) -> str:
    if not code:
        return "Opérateur non précisé"
    return R.LIBELLES_OPERATEURS.get(code.upper(), code)


# ═════════════════════════════════════════════════════════════════════════════
# LECTURE DES EN-TÊTES
# ═════════════════════════════════════════════════════════════════════════════

_TOUS_SYNONYMES = {s for lst in R.SYNONYMES.values() for s in lst} | \
    {s for d in R.SYNONYMES_PAR_ROLE.values() for lst in d.values() for s in lst} | \
    {"odbincomingcalls", "odboutgoingcalls"}


def detecter_separateur(lignes: list[str]) -> str:
    meilleur, score_max = ",", -1
    for sep in SEPARATEURS:
        comptes = [l.count(sep) for l in lignes if l.strip()]
        if not comptes:
            continue
        # séparateur présent et régulier sur les premières lignes
        score = min(comptes) * 10 + (5 if len(set(comptes)) == 1 else 0)
        if comptes[0] > 0 and score > score_max:
            meilleur, score_max = sep, score
    return meilleur


def detecter_encodage(chemin: str) -> str:
    """« utf-8 » si le début et le milieu du fichier sont en UTF-8 valide, sinon « cp1252 »."""
    taille = os.path.getsize(chemin)
    with open(chemin, "rb") as f:
        echantillons = [f.read(1 << 20)]
        if taille > 2 << 20:
            f.seek(taille // 2)
            echantillons.append(f.read(1 << 20))
    for i, b in enumerate(echantillons):
        try:
            b.decode("utf-8")
        except UnicodeDecodeError as e:
            # caractère coupé en début / fin d'échantillon : sans conséquence
            if e.start < len(b) - 4 and not (i == 1 and e.start < 4):
                return "cp1252"
    return "utf-8"


def _decouper(ligne: str, sep: str) -> list[str]:
    import csv
    try:
        return [c.strip().strip("'") for c in next(csv.reader([ligne], delimiter=sep))]
    except Exception:
        return [c.strip().strip('"').strip("'") for c in ligne.split(sep)]


def _score_entete(cellules: list[str]) -> int:
    return sum(1 for c in cellules if normaliser_entete(c) in _TOUS_SYNONYMES)


def lire_echantillon(chemin: str, n_lignes: int = 400) -> dict:
    """
    Lit le début d'un fichier : séparateur, ligne d'en-tête (qui n'est pas
    toujours la première), colonnes et lignes d'exemple.
    Retourne {colonnes, separateur, saut, sans_entete, lignes}.
    """
    ext = os.path.splitext(chemin)[1].lower()
    if ext in (".xlsx", ".xls"):
        brutes = _lignes_excel(chemin, n_lignes + 20)
        sep = None
    else:
        with open(chemin, "rb") as f:
            brut = f.read(512 * 1024)
        texte = brut.decode(detecter_encodage(chemin), errors="replace").lstrip("﻿")
        lignes_txt = texte.splitlines()
        if len(brut) == 512 * 1024 and lignes_txt:
            lignes_txt = lignes_txt[:-1]           # dernière ligne possiblement tronquée
        lignes_txt = [l for l in lignes_txt if l.strip()]
        if not lignes_txt:
            return {"colonnes": [], "separateur": ",", "saut": 0, "sans_entete": False, "lignes": []}
        sep = detecter_separateur(lignes_txt[:25])
        brutes = [_decouper(l, sep) for l in lignes_txt[:n_lignes + 20]]
    if not brutes:
        return {"colonnes": [], "separateur": sep, "saut": 0, "sans_entete": False, "lignes": []}

    # Ligne d'en-tête : celle, parmi les 20 premières, qui contient le plus de noms connus
    scores = [_score_entete(l) for l in brutes[:20]]
    saut = max(range(len(scores)), key=lambda i: (scores[i], -i)) if scores else 0
    if scores and scores[saut] <= scores[0]:
        saut = 0
    sans_entete = False
    if scores and max(scores) == 0:
        premiere = brutes[0]
        # première ligne composée de valeurs (numéro de téléphone, dates…) : pas d'en-tête
        if any(re.fullmatch(r"\+?(237)?\s?6\d{8}", c.replace(" ", "")) for c in premiere):
            sans_entete = True
    if sans_entete:
        colonnes = [f"colonne_{i + 1}" for i in range(len(brutes[0]))]
        donnees = brutes[:n_lignes]
    else:
        colonnes = [c if c else f"colonne_{i + 1}" for i, c in enumerate(brutes[saut])]
        donnees = brutes[saut + 1:saut + 1 + n_lignes]
    return {"colonnes": colonnes, "separateur": sep, "saut": saut, "sans_entete": sans_entete, "lignes": donnees}


def _lignes_excel(chemin: str, n: int) -> list[list[str]]:
    try:
        import openpyxl
        wb = openpyxl.load_workbook(chemin, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        sortie = []
        for l in ws.iter_rows(max_row=n, values_only=True):
            sortie.append(["" if v is None else (v.strftime("%Y-%m-%d") if hasattr(v, "strftime") else str(v))
                           for v in l])
        wb.close()
        return sortie
    except Exception:
        import pandas as pd
        df = pd.read_excel(chemin, nrows=n, header=None, dtype=str)
        return df.fillna("").values.tolist()


def lire_entete(chemin: str) -> tuple[list[str], str | None]:
    """Compatibilité : (colonnes, séparateur)."""
    e = lire_echantillon(chemin, 5)
    return e["colonnes"], e["separateur"]


# ═════════════════════════════════════════════════════════════════════════════
# RÔLE DES FICHIERS
# ═════════════════════════════════════════════════════════════════════════════

def role_depuis_nom(nom: str) -> str | None:
    tk = jetons(nom)
    brut = normaliser_entete(sans_accents(nom))
    for role, mots in R.MOTS_CLES_ROLES:
        for m in mots:
            if m in tk:
                return role
            # mots longs (ou alphanumériques comme « m2m ») recherchés aussi à
            # l'intérieur des jetons : « lignesflottes », « LignesM2M »
            if (len(m) >= 5 or any(ch.isdigit() for ch in m)) and m in brut:
                return role
    return None


def role_depuis_colonnes(colonnes: list[str]) -> str | None:
    cols = [normaliser_entete(c) for c in colonnes]
    joint = " ".join(cols)
    for role, fragments in R.SIGNATURES_ROLES.items():
        if any(f in joint for f in fragments):
            return role
    # Peu de colonnes (numéro + statut) → HLR
    if len(cols) <= 5 and any("msisdn" in c or "tel" in c for c in cols) and \
            not any("nais" in c or "birth" in c or "nom" in c or "name" in c for c in cols):
        return "HLR"
    if any("nais" in c or "birth" in c for c in cols):
        return "BDI"
    return None


# ═════════════════════════════════════════════════════════════════════════════
# CORRESPONDANCE DES COLONNES
# ═════════════════════════════════════════════════════════════════════════════

def resoudre_colonnes(colonnes: list[str], role: str, forcees: dict | None = None) -> dict[str, str]:
    """
    Associe chaque champ attendu pour le rôle à une colonne réelle.
    Une colonne réelle n'est attribuée qu'à un seul champ.
    `forcees` : correspondances imposées par l'utilisateur ({champ: colonne} ;
    une colonne vide « » signifie « aucune colonne pour ce champ »).
    Retourne {champ_canonique: nom_de_colonne_réel}.
    """
    normes = {normaliser_entete(c): c for c in colonnes if str(c).strip()}
    utilisees: set[str] = set()
    resultat: dict[str, str] = {}
    exclus: set[str] = set()
    champs = R.CHAMPS_PAR_ROLE.get(role, R.CHAMPS_PAR_ROLE["BDI"])
    surcharges = R.SYNONYMES_PAR_ROLE.get(role, {})

    for champ, col in (forcees or {}).items():
        if not col:
            exclus.add(champ)
        elif col in colonnes:
            resultat[champ] = col
            utilisees.add(normaliser_entete(col))

    # Passe 1 : correspondances exactes (tous champs), pour que les règles
    # approximatives ne « volent » pas une colonne évidente d'un autre champ.
    for champ in champs:
        if champ in resultat or champ in exclus:
            continue
        for syn in surcharges.get(champ, []) + R.SYNONYMES.get(champ, []):
            if syn in normes and syn not in utilisees:
                resultat[champ] = normes[syn]
                utilisees.add(syn)
                break

    # Passe 2 : règles « contient »
    for champ in champs:
        if champ in resultat or champ in exclus:
            continue
        for obligatoires, exclus_mots in R.REGLES_CONTIENT.get(champ, []):
            candidats = [n for n in normes if n not in utilisees
                         and all(o in n for o in obligatoires)
                         and not any(e in n for e in exclus_mots)]
            if candidats:
                choisi = min(candidats, key=len)
                resultat[champ] = normes[choisi]
                utilisees.add(choisi)
                break

    # Passe 3 : rapprochement approximatif
    for champ in champs:
        if champ in resultat or champ in exclus:
            continue
        restants = [n for n in normes if n not in utilisees]
        for syn in surcharges.get(champ, []) + R.SYNONYMES.get(champ, []):
            proches = difflib.get_close_matches(syn, restants, n=1, cutoff=0.86)
            if proches:
                resultat[champ] = normes[proches[0]]
                utilisees.add(proches[0])
                break
    return resultat


def _analyse_colonnes_echantillon(colonnes: list[str], lignes: list[list[str]]):
    """Statistiques par colonne sur l'échantillon : taux de numéros, taux de dates, années."""
    import polars as pl
    from .normalisation import expr_date, expr_msisdn
    if not lignes:
        return {}
    k = len(colonnes)
    data = {c: [(l[i] if i < len(l) else None) or None for l in lignes] for i, c in enumerate(colonnes)}
    df = pl.DataFrame(data, schema={c: pl.String for c in colonnes})
    stats = {}
    for c in colonnes:
        remplis = df.filter(pl.col(c).is_not_null() & (pl.col(c).str.strip_chars() != ""))
        n = remplis.height
        if n == 0:
            stats[c] = {"remplis": 0}
            continue
        m = remplis.select(expr_msisdn(c).alias("m"))["m"]
        taux_tel = m.drop_nulls().str.len_chars().eq(9).sum() / n
        d = remplis.select(expr_date(c).alias("d"))["d"].drop_nulls()
        annees = d.dt.year() if d.len() else None
        stats[c] = {"remplis": n, "taux_tel": taux_tel, "taux_date": d.len() / n,
                    "annee_med": float(annees.median()) if annees is not None else None,
                    "annee_max": int(annees.max()) if annees is not None else None,
                    "exemple": remplis[c][0]}
    del k
    return stats


def deduire_par_contenu(colonnes, lignes, corresp: dict, role: str) -> list[str]:
    """
    Complète les champs essentiels non reconnus par leur nom en examinant les
    valeurs : numéro de téléphone (9 chiffres), dates de naissance, d'expiration
    et de souscription (selon la plage des années). Retourne les champs déduits.
    """
    if role in ("IGNORE", None):
        return []
    stats = _analyse_colonnes_echantillon(colonnes, lignes)
    prises = set(corresp.values())
    libres = [c for c in colonnes if c not in prises and stats.get(c, {}).get("remplis")]
    deduits = []
    annee_courante = date.today().year
    if "msisdn" not in corresp:
        cands = [c for c in libres if stats[c].get("taux_tel", 0) >= .8 and stats[c].get("taux_date", 0) < .5]
        if cands:
            corresp["msisdn"] = cands[0]
            libres.remove(cands[0])
            deduits.append("msisdn")
    if role == "HLR":
        return deduits
    dates = [c for c in libres if stats[c].get("taux_date", 0) >= .7]
    regles = [
        ("date_naissance", lambda s: s["annee_med"] and s["annee_med"] < annee_courante - 12),
        ("date_expiration", lambda s: s["annee_max"] and s["annee_max"] > annee_courante and s["annee_med"] >= 2010),
        ("date_activation", lambda s: s["annee_med"] and 2000 <= s["annee_med"] <= annee_courante
         and (s["annee_max"] or 0) <= annee_courante),
    ]
    for champ, test in regles:
        if champ in corresp or champ not in R.CHAMPS_PAR_ROLE.get(role, []):
            continue
        cands = [c for c in dates if test(stats[c])]
        if cands:
            corresp[champ] = cands[0]
            dates.remove(cands[0])
            deduits.append(champ)
    return deduits


def qualite_colonnes(colonnes, lignes, corresp: dict) -> dict:
    """Pour chaque champ reconnu : taux de valeurs exploitables sur l'échantillon et exemple."""
    stats = _analyse_colonnes_echantillon(colonnes, lignes)
    q = {}
    for champ, col in corresp.items():
        s = stats.get(col, {})
        if not s.get("remplis"):
            q[champ] = {"taux": None, "remplis": 0, "exemple": ""}
            continue
        if champ == "msisdn":
            t = s["taux_tel"]
        elif champ.startswith("date_"):
            t = s["taux_date"]
        else:
            t = None
        q[champ] = {"taux": round(t * 100) if t is not None else None,
                    "remplis": round(s["remplis"] / max(len(lignes), 1) * 100), "exemple": s.get("exemple", "")}
    return q


# ═════════════════════════════════════════════════════════════════════════════
# EXAMEN D'UN DOSSIER
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class FichierDetecte:
    chemin: str
    nom: str
    taille_octets: int
    colonnes: list[str]
    separateur: str | None
    role: str
    role_source: str                     # "nom", "colonnes", "manuel", "défaut"
    correspondances: dict = field(default_factory=dict)
    champs_manquants: list = field(default_factory=list)
    saut: int = 0                        # lignes à ignorer avant l'en-tête
    sans_entete: bool = False
    forcees: dict = field(default_factory=dict)
    deduits: list = field(default_factory=list)
    apercu: list = field(default_factory=list)
    qualite: dict = field(default_factory=dict)

    def to_dict(self):
        d = asdict(self)
        d["role_libelle"] = R.ROLES.get(self.role, self.role)
        d["taille_lisible"] = taille_lisible(self.taille_octets)
        return d


def taille_lisible(n: int) -> str:
    for unite in ("o", "Ko", "Mo", "Go"):
        if n < 1024:
            return f"{n:.0f} {unite}" if unite == "o" else f"{n:.1f} {unite}".replace(".", ",")
        n /= 1024
    return f"{n:.1f} To".replace(".", ",")


def lister_fichiers(dossier: str) -> list[str]:
    """Fichiers exploitables du dossier et de ses sous-dossiers (archives décompressées)."""
    if os.path.isfile(dossier):
        return [dossier]
    trouves = []
    for racine, sous, noms in os.walk(dossier):
        sous[:] = [d for d in sous if not d.startswith((".", "__MACOSX"))]
        for nm in noms:
            if nm.startswith(("~$", ".", "._")):
                continue
            if os.path.splitext(nm)[1].lower() in EXTENSIONS:
                trouves.append(os.path.join(racine, nm))
    return sorted(trouves)


def analyser_fichier(chemin: str, role_force: str | None = None, forcees: dict | None = None,
                     apercu: bool = False) -> FichierDetecte:
    nom = os.path.splitext(os.path.basename(chemin))[0]
    try:
        e = lire_echantillon(chemin)
    except Exception:
        e = {"colonnes": [], "separateur": ",", "saut": 0, "sans_entete": False, "lignes": []}
    colonnes = e["colonnes"]
    if role_force:
        role, source = role_force, "manuel"
    else:
        role, source = role_depuis_nom(nom), "nom"
        if role is None:
            role, source = role_depuis_colonnes(colonnes), "colonnes"
        if role is None:
            role, source = "IGNORE", "défaut"
    fd = FichierDetecte(chemin=chemin, nom=nom, taille_octets=os.path.getsize(chemin),
                        colonnes=colonnes, separateur=e["separateur"], role=role, role_source=source,
                        saut=e["saut"], sans_entete=e["sans_entete"], forcees=dict(forcees or {}))
    completer_correspondances(fd, e["lignes"])
    if apercu:
        fd.apercu = [l[:len(colonnes)] for l in e["lignes"][:5]]
        fd.qualite = qualite_colonnes(colonnes, e["lignes"], fd.correspondances)
    return fd


def completer_correspondances(fd: FichierDetecte, lignes=None) -> None:
    if fd.role in ("IGNORE", None):
        fd.correspondances, fd.champs_manquants = {}, []
        return
    fd.correspondances = resoudre_colonnes(fd.colonnes, fd.role, fd.forcees)
    if lignes:
        exclus = {k for k, v in fd.forcees.items() if not v}
        avant = dict(fd.correspondances)
        fd.deduits = [c for c in deduire_par_contenu(fd.colonnes, lignes, fd.correspondances, fd.role)
                      if c not in exclus]
        for c in exclus:
            if c in fd.correspondances and c not in avant:
                del fd.correspondances[c]
    attendus = R.CHAMPS_PAR_ROLE.get(fd.role, [])
    fd.champs_manquants = [c for c in attendus if c not in fd.correspondances
                           and c not in R.CHAMPS_FACULTATIFS.get(fd.role, set())]


def types_de_piece(fichiers: list[FichierDetecte], limite: int = 300_000) -> list[dict]:
    """Types de pièce présents (sur un échantillon) avec la catégorie proposée par défaut."""
    from .lecture import scanner
    from .normalisation import normaliser_type_piece
    import polars as pl
    compte = Counter()
    for fd in fichiers:
        if fd.role not in ("BDI", "MAJEURS", "MINEURS") or "type_piece" not in fd.correspondances:
            continue
        try:
            lf, tmp = scanner(fd)
            col = fd.correspondances["type_piece"]
            vc = lf.head(limite).group_by(pl.col(col).cast(pl.String).alias("v")).agg(pl.len().alias("n")).collect()
            for v, n in zip(vc["v"].to_list(), vc["n"].to_list()):
                compte[normaliser_type_piece(v)] += n
            if tmp:
                os.remove(tmp)
        except Exception:
            continue
    return [{"type": t, "n": n, "categorie": categorie_type_defaut(t)} for t, n in compte.most_common()]


def categorie_type_defaut(t: str) -> str:
    t = (t or "").upper()
    if any(m == t or t.startswith(m) for m in R.TYPES_M2M):
        return "M2M"
    if any(m == t or t.startswith(m) for m in R.TYPES_PERSONNE_MORALE):
        return "FLOTTE"
    return "PHYSIQUE"


def estimer_periode_donnees(fichiers: list[FichierDetecte]) -> dict | None:
    """Mois de la date de souscription la plus récente (hors dates futures) dans la BDI."""
    from .lecture import lots
    from .normalisation import expr_date
    import polars as pl
    aujourd_hui = date.today()
    meilleur = None
    for fd in fichiers:
        if fd.role not in ("BDI", "MAJEURS", "MINEURS", "FLOTTE", "M2M") or "date_activation" not in fd.correspondances:
            continue
        try:
            col = fd.correspondances["date_activation"]
            for x in lots(fd, colonnes=[col]):
                d = x.lazy().select(expr_date(col).alias("d")).filter(pl.col("d") <= pl.lit(aujourd_hui)) \
                    .select(pl.col("d").max()).collect().item()
                if d and (meilleur is None or d > meilleur):
                    meilleur = d
        except Exception:
            continue
    if not meilleur:
        return None
    return {"annee": meilleur.year, "mois": meilleur.month, "date_max": meilleur.isoformat()}


def examiner_dossier(dossier: str) -> dict:
    """Examen complet : fichiers, rôles, colonnes, opérateur, période, alertes."""
    dossier = os.path.expanduser(dossier.strip().strip('"').strip("'"))
    if not os.path.exists(dossier):
        return {"ok": False, "erreur": f"Chemin introuvable : {dossier}"}
    chemins = lister_fichiers(dossier)
    if not chemins:
        return {"ok": False, "erreur": "Aucun fichier CSV, TXT ou Excel trouvé."}

    fichiers = [analyser_fichier(c, apercu=True) for c in chemins]
    noms = [f.nom for f in fichiers] + [os.path.basename(os.path.normpath(dossier))]
    periode = detecter_periode(noms)
    periode["source"] = "noms de fichiers" if periode["certitude"] != "aucune" else None
    estimation = None
    if periode["certitude"] != "complete":
        estimation = estimer_periode_donnees(fichiers)
        if estimation:
            if not periode["mois"] or not periode["annee"]:
                periode["mois"] = periode["mois"] or estimation["mois"]
                periode["annee"] = periode["annee"] or estimation["annee"]
                periode["source"] = "date de souscription la plus récente"
    toutes_colonnes = [c for f in fichiers for c in f.colonnes]
    operateur = detecter_operateur(noms, toutes_colonnes)

    return {
        "ok": True,
        "dossier": dossier,
        "fichiers": [f.to_dict() for f in fichiers],
        "operateur": operateur,
        "operateur_libelle": libelle_operateur(operateur),
        "periode": {**periode, "libelle": libelle_periode(periode["annee"], periode["mois"])},
        "estimation_periode": estimation,
        "types_piece": types_de_piece(fichiers),
        "a_hlr": any(f.role == "HLR" for f in fichiers),
        "champs": {r: R.CHAMPS_PAR_ROLE.get(r, []) for r in R.ROLES if r != "IGNORE"},
        "alertes": alertes_examen(fichiers, periode),
    }


def alertes_examen(fichiers: list[FichierDetecte], periode: dict) -> list[str]:
    alertes = []
    roles = Counter(f.role for f in fichiers)
    if not roles.get("HLR"):
        alertes.append("Aucun fichier HLR identifié : le nombre de numéros sera établi à partir "
                       "des fichiers d'identification et les contrôles de couverture ne pourront pas être réalisés.")
    if not (roles.get("BDI") or roles.get("MAJEURS")):
        alertes.append("Aucun fichier de personnes physiques (BDI ou majeurs) identifié.")
    for role, n in roles.items():
        if role not in ("IGNORE", "BDI") and n > 1:
            alertes.append(f"{n} fichiers classés « {R.ROLES[role]} » : ils seront cumulés.")
    for f in fichiers:
        if f.role == "IGNORE":
            alertes.append(f"{f.nom} : rôle non déterminé, fichier ignoré (modifiable).")
            continue
        if "msisdn" in f.champs_manquants:
            alertes.append(f"{f.nom} : colonne du numéro de téléphone non reconnue (à choisir dans la liste).")
        if f.role in ("BDI", "MAJEURS", "MINEURS") and "date_naissance" not in f.correspondances:
            alertes.append(f"{f.nom} : colonne de date de naissance non reconnue : la répartition "
                           f"majeurs / mineurs sera impossible (à choisir dans la liste).")
        for champ, q in f.qualite.items():
            if champ.startswith("date_") and q.get("taux") is not None and q["taux"] < 60 and q["remplis"] > 10:
                alertes.append(f"{f.nom} : {R.LIBELLES_CHAMPS.get(champ, champ).lower()} interprétée pour "
                               f"{q['taux']} % des valeurs seulement (ex. « {q['exemple']} »).")
        if f.saut:
            alertes.append(f"{f.nom} : en-tête trouvé à la ligne {f.saut + 1} ; les lignes précédentes sont ignorées.")
        if f.sans_entete:
            alertes.append(f"{f.nom} : pas de ligne d'en-tête ; colonnes identifiées d'après leur contenu.")
        if f.deduits:
            alertes.append(f"{f.nom} : colonnes identifiées d'après leur contenu : "
                           + ", ".join(R.LIBELLES_CHAMPS.get(c, c).lower() for c in f.deduits) + ".")
    if periode.get("certitude") != "complete":
        alertes.append("Mois de la base non trouvé dans les noms de fichiers"
                       + (" : estimé d'après la date de souscription la plus récente." if periode.get("source") ==
                          "date de souscription la plus récente" else ".")
                       + " À vérifier : il sert de référence pour les âges et les expirations.")
    return alertes
