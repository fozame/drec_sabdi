"""
lecture.py
──────────
Chargement d'un fichier en ne conservant que les colonnes utiles, renommées
selon les champs canoniques, avec normalisation des numéros, des dates, des
statuts et des types de pièce.
"""
from __future__ import annotations

import os

import polars as pl

from . import referentiel as R
from .detection import FichierDetecte, detecter_encodage, detecter_separateur, resoudre_colonnes
from .normalisation import (categoriser_statut, expr_date, expr_identifiant, expr_msisdn,
                            expr_vide, normaliser_type_piece)

CHAMPS_DATE = {"date_naissance", "date_expiration", "date_activation", "date_naissance_tuteur",
               "date_expiration_tuteur"}
_OUI = ["Y", "YES", "O", "OUI", "1", "TRUE", "VRAI", "T"]


def _lire_excel(chemin: str) -> pl.DataFrame:
    """Lecture d'un classeur (première feuille), toutes valeurs converties en texte."""
    try:
        return pl.read_excel(chemin, infer_schema_length=0)
    except Exception:
        pass
    if chemin.lower().endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(chemin, read_only=True, data_only=True)
        lignes = wb.worksheets[0].iter_rows(values_only=True)
        entete = [str(c) if c is not None else f"colonne_{i}" for i, c in enumerate(next(lignes))]
        colonnes = [[] for _ in entete]
        for l in lignes:
            for i in range(len(entete)):
                v = l[i] if i < len(l) else None
                if hasattr(v, "strftime"):
                    v = v.strftime("%Y-%m-%d")
                colonnes[i].append(None if v is None else str(v))
        wb.close()
        return pl.DataFrame({h: c for h, c in zip(entete, colonnes)}, schema={h: pl.String for h in entete})
    import pandas as pd
    pdf = pd.read_excel(chemin, dtype=object)
    return pl.DataFrame({str(c): [None if pd.isna(v) else str(v) for v in pdf[c]] for c in pdf.columns})


def _transcoder(chemin: str, encodage: str) -> str:
    """Copie UTF-8 temporaire d'un fichier Windows-1252 / Latin-1 (lecture par blocs)."""
    import tempfile
    dossier = os.path.join(tempfile.gettempdir(), "sgrna_conversion")
    os.makedirs(dossier, exist_ok=True)
    cible = os.path.join(dossier, f"{os.getpid()}_{abs(hash(chemin))}.csv")
    with open(chemin, "rb") as src, open(cible, "wb") as dst:
        while True:
            bloc = src.read(16 * 1024 * 1024)
            if not bloc:
                break
            dst.write(bloc.decode(encodage, errors="replace").encode("utf-8"))
    return cible


def scanner(fd: FichierDetecte) -> tuple[pl.LazyFrame, str | None]:
    """Retourne (LazyFrame tout en texte, fichier temporaire éventuel à supprimer après lecture)."""
    ext = os.path.splitext(fd.chemin)[1].lower()
    if ext in (".xlsx", ".xls"):
        df = _lire_excel(fd.chemin)
        if fd.saut:
            entete = [str(v) for v in df.row(fd.saut - 1)]
            df = df.slice(fd.saut).rename({a: b for a, b in zip(df.columns, entete) if b})
        return df.select([pl.col(c).cast(pl.String) for c in df.columns]).lazy(), None

    chemin, temporaire = fd.chemin, None
    enc = detecter_encodage(fd.chemin)
    if enc != "utf-8":
        temporaire = chemin = _transcoder(fd.chemin, enc)
    sep = fd.separateur
    if not sep:
        with open(chemin, "rb") as f:
            sep = detecter_separateur(f.read(65536).decode("utf-8", "replace").splitlines()[:6])
    options = dict(separator=sep, infer_schema_length=0, encoding="utf8-lossy", ignore_errors=True,
                   truncate_ragged_lines=True, quote_char='"', low_memory=False)
    if fd.sans_entete:
        options.update(has_header=False, new_columns=list(fd.colonnes))
    elif fd.saut:
        options.update(skip_rows=fd.saut)
    return pl.scan_csv(chemin, **options), temporaire


def noms_colonnes(lf: pl.LazyFrame) -> list[str]:
    try:
        return list(lf.collect_schema().names())
    except AttributeError:  # Polars < 1.0
        return list(lf.columns)


STATUT = pl.Enum(R.ORDRE_STATUT)
CHAMPS_TYPE = ("type_piece", "type_piece_tuteur")
_ODB_LIBRE = {"", "0", "FALSE", "FAUX", "NO", "NON", "N", "F", "NONE", "NULL", "NA", "-", "00", "0.0"}


def _odb_actif(v) -> bool:
    """Valeur d'un indicateur de blocage (ODB) : 1 / TRUE / code de blocage = bloqué."""
    if v is None:
        return False
    return str(v).strip().upper() not in _ODB_LIBRE


def statut_hlr(statut, entrant, sortant, a_statut: bool, a_odb: bool) -> str:
    """Statut HLR combinant la colonne de statut et les indicateurs de blocage ODB."""
    base = categoriser_statut(statut) if a_statut else ("ACTIF" if a_odb else "NON_RENSEIGNE")
    if not a_odb or base in ("ELIGIBLE", "RESILIE", "SUSP_TOTAL"):
        return base
    bi, bo = _odb_actif(entrant), _odb_actif(sortant)
    if bi and bo:
        return "SUSP_TOTAL"
    if bo:
        return "SUSP_EMISSION"
    if bi:
        return "SUSP_RECEPTION"
    return base


def _collecter(lf: pl.LazyFrame) -> pl.DataFrame:
    """Collecte en flux quand la version de Polars le permet (mémoire réduite)."""
    for kw in ({"engine": "streaming"}, {"streaming": True}, {}):
        try:
            return lf.collect(**kw)
        except TypeError:
            continue
    return lf.collect()


def _nom_normalise(col: str) -> pl.Expr:
    """Nom en majuscules sans accents ni ponctuation, mots triés (« Marie NGONO » = « NGONO MARIE »)."""
    e = pl.col(col).cast(pl.String).str.to_uppercase()
    for motif, lettre in (("[ÀÁÂÄÃÅ]", "A"), ("[ÈÉÊË]", "E"), ("[ÌÍÎÏ]", "I"), ("[ÒÓÔÖÕ]", "O"),
                          ("[ÙÚÛÜ]", "U"), ("Ç", "C"), ("Ñ", "N"), ("Ÿ", "Y")):
        e = e.str.replace_all(motif, lettre)
    return e.str.replace_all(r"[^A-Z]+", " ").str.strip_chars().str.split(" ")


def correspondances_effectives(fd: FichierDetecte, reels: list[str]) -> dict:
    """Correspondances retenues à l'examen (y compris déduites du contenu), vérifiées sur les colonnes lues."""
    corresp = {k: v for k, v in (fd.correspondances or {}).items() if v in reels}
    complement = resoudre_colonnes(reels, fd.role, {**{k: v for k, v in corresp.items()}, **(fd.forcees or {})})
    for k, v in complement.items():
        corresp.setdefault(k, v)
    for k, v in (fd.forcees or {}).items():
        if not v:
            corresp.pop(k, None)
    return corresp


def charger(fd: FichierDetecte, log=print, champs: set | None = None) -> tuple[pl.DataFrame, dict]:
    """
    Lit un fichier et retourne (DataFrame compact, informations).

    Pour limiter la mémoire sur des fichiers de plusieurs millions de lignes, les
    textes libres (noms, adresses, IMEI…) ne sont pas conservés : seuls des
    indicateurs le sont (non renseigné, nom générique…) et une clé d'identité
    calculée à partir du nom (pour rapprocher les lignes d'une même personne).

    Colonnes produites selon disponibilité :
      msisdn (Int64), msisdn_nc, statut_fichier (Enum), type_piece, type_piece_tuteur,
      piece_id, date_naissance, date_expiration, date_activation (Date), <champ>_vide,
      date_expiration_invalide, imei_invalide, sim_type, nom_cle, nom_generique, nom_un_mot,
      nom_chiffres.
    `champs` limite la lecture à certains champs (ex. {"msisdn"}).
    """
    lf, temporaire = scanner(fd)
    try:
        return _charger(fd, lf, log, champs)
    finally:
        if temporaire:
            try:
                os.remove(temporaire)
            except OSError:
                pass


def _charger(fd, lf, log, champs):
    reels = noms_colonnes(lf)
    corresp = correspondances_effectives(fd, reels)
    fd.correspondances = corresp
    fd.champs_manquants = [c for c in R.CHAMPS_PAR_ROLE.get(fd.role, []) if c not in corresp
                           and c not in R.CHAMPS_FACULTATIFS.get(fd.role, set())]
    utiles = {k: v for k, v in corresp.items() if champs is None or k in champs}
    vide_info = {"lignes": 0, "correspondances": corresp, "champs_manquants": fd.champs_manquants,
                 "statuts_bruts": [], "variantes": {}, "colonnes_total": len(reels)}
    if "msisdn" not in utiles:
        return pl.DataFrame(), vide_info

    # ── Passe 1 : valeurs distinctes des statuts (et blocages) et des types de pièce ──
    statuts_bruts, tables, variantes = [], {}, {}
    cols_statut = [c for c in ("statut", "odb_entrant", "odb_sortant") if c in utiles]
    if cols_statut:
        a_statut, a_odb = "statut" in utiles, ("odb_entrant" in utiles or "odb_sortant" in utiles)
        vc = _collecter(lf.group_by([pl.col(utiles[c]).cast(pl.String).str.strip_chars().alias(f"_{c}")
                                     for c in cols_statut]).agg(pl.len().alias("n")))
        combos = vc.to_dicts()
        cats = [statut_hlr(d.get("_statut"), d.get("_odb_entrant"), d.get("_odb_sortant"), a_statut, a_odb)
                for d in combos]
        declares = [categoriser_statut(d.get("_statut")) if a_statut else None for d in combos]
        blocages = [(1 if _odb_actif(d.get("_odb_entrant")) else 0) + (2 if _odb_actif(d.get("_odb_sortant")) else 0)
                    if a_odb else None for d in combos]
        tables["statut"] = vc.drop("n").with_columns(
            pl.Series("statut_fichier", cats).cast(STATUT),
            pl.Series("statut_declare", declares, dtype=pl.String).cast(STATUT),
            pl.Series("odb", blocages, dtype=pl.Int8))
        if not a_odb:
            tables["statut"] = tables["statut"].drop(["statut_declare", "odb"])
        for d, cat in zip(combos, cats):
            morceaux = [str(d.get("_statut")) if a_statut else ""]
            if "_odb_entrant" in d:
                morceaux.append(f"entrants bloqués : {d['_odb_entrant']}")
            if "_odb_sortant" in d:
                morceaux.append(f"sortants bloqués : {d['_odb_sortant']}")
            valeur = " · ".join(m for m in morceaux if m) or "(vide)"
            statuts_bruts.append({"valeur": valeur, "categorie": cat, "n": d["n"]})
        statuts_bruts.sort(key=lambda d: -d["n"])
    for champ in CHAMPS_TYPE:
        if champ in utiles:
            vc = _collecter(lf.select(pl.col(utiles[champ]).cast(pl.String).str.strip_chars().alias("v")).unique())
            valeurs = vc["v"].to_list()
            normes = [normaliser_type_piece(v) for v in valeurs]
            tables[champ] = pl.DataFrame({f"_{champ}": valeurs, champ: normes},
                                         schema={f"_{champ}": pl.String, champ: pl.String})
            if champ == "type_piece":
                for v, t in zip(valeurs, normes):
                    if v and t != "NON_RENSEIGNE" and v.strip().strip("'\"") != t:
                        variantes.setdefault(t, set()).add(v.strip())

    # ── Passe 2 : colonnes compactes ─────────────────────────────────────────
    exprs = [expr_msisdn(utiles["msisdn"]).alias("_m")]
    generiques = [g.upper() for g in R.NOMS_GENERIQUES]
    for champ, reel in utiles.items():
        if champ == "msisdn":
            continue
        if champ in ("statut", "odb_entrant", "odb_sortant") + CHAMPS_TYPE:
            exprs.append(pl.col(reel).cast(pl.String).str.strip_chars().alias(f"_{champ}"))
        elif champ in CHAMPS_DATE:
            exprs += [expr_date(reel).alias(champ), expr_vide(reel).alias(f"{champ}_vide")]
        elif champ == "numero_piece":
            exprs += [expr_identifiant(reel).alias("piece_id"), expr_vide(reel).alias("numero_piece_vide")]
        elif champ == "imei":
            lg = pl.col(reel).cast(pl.String).str.replace_all(r"\D", "").str.len_chars()
            exprs += [expr_vide(reel).alias("imei_vide"),
                      (~expr_vide(reel) & ~lg.is_in(list(R.IMEI_LONGUEURS_VALIDES))).alias("imei_invalide")]
        elif champ in ("liste_rouge", "reserve_operateur"):
            exprs.append(pl.col(reel).cast(pl.String).str.strip_chars().str.to_uppercase().is_in(_OUI)
                         .fill_null(False).alias(champ))
        elif champ == "sim_type":
            exprs.append(pl.col(reel).cast(pl.String).str.strip_chars().str.to_uppercase().alias("sim_type"))
        elif champ == "nom":
            mots = _nom_normalise(reel).list.eval(pl.element().filter(pl.element() != ""))
            exprs += [
                expr_vide(reel).alias("nom_vide"),
                pl.when(mots.list.len() > 0).then(mots.list.sort().list.join(" ").hash()).alias("nom_cle"),
                ((mots.list.len() > 0) & mots.list.eval(pl.element().is_in(generiques)).list.all())
                .alias("nom_generique"),
                (mots.list.len() == 1).alias("nom_un_mot"),
                pl.col(reel).cast(pl.String).str.contains(r"[0-9]").fill_null(False).alias("nom_chiffres"),
            ]
        else:
            exprs.append(expr_vide(reel).alias(f"{champ}_vide"))
    q = lf.select(exprs)
    for champ, table in tables.items():
        cles = [c for c in table.columns if c.startswith("_")]
        q = q.join(table.lazy(), on=cles, how="left", **_join_nulls())
    q = q.with_columns(
        pl.col("_m").cast(pl.Int64, strict=False).alias("msisdn"),
        (pl.col("_m").is_null() | (pl.col("_m").str.len_chars() != 9)).alias("msisdn_nc"),
    )
    noms_q = q.collect_schema().names()
    q = q.drop([c for c in noms_q if c.startswith("_")])
    df = _collecter(q)
    for champ in CHAMPS_TYPE:
        if champ in df.columns:
            df = df.with_columns(pl.col(champ).fill_null("NON_RENSEIGNE"))
    if "statut_fichier" in df.columns:
        df = df.with_columns(pl.col("statut_fichier").fill_null("NON_RENSEIGNE"))
    if "date_expiration" in df.columns:
        df = df.with_columns((~pl.col("date_expiration_vide") & pl.col("date_expiration").is_null())
                             .alias("date_expiration_invalide"))

    n = df.height
    log(f"{fd.nom} : {n:,} lignes chargées ({len(corresp)} colonnes reconnues)".replace(",", " "))
    info = {**vide_info, "lignes": n, "statuts_bruts": statuts_bruts,
            "variantes": {k: sorted(v)[:6] for k, v in variantes.items()}}
    return df, info


def _join_nulls() -> dict:
    """Jointure sur valeurs nulles (paramètre renommé selon la version de Polars)."""
    import inspect
    params = inspect.signature(pl.DataFrame.join).parameters
    if "nulls_equal" in params:
        return {"nulls_equal": True}
    if "join_nulls" in params:
        return {"join_nulls": True}
    return {}
