"""
normalisation.py
────────────────
Expressions Polars et fonctions de normalisation des valeurs :
numéros de téléphone, dates, champs non renseignés, statuts, types de pièce.
"""
from __future__ import annotations

import re
from datetime import date

import polars as pl

from . import referentiel as R
from .detection import sans_accents

# ═════════════════════════════════════════════════════════════════════════════
# EXPRESSIONS
# ═════════════════════════════════════════════════════════════════════════════

_VIDES_MAJ = sorted({v.upper() for v in R.VALEURS_VIDES} | {sans_accents(v).upper() for v in R.VALEURS_VIDES})


def expr_vide(col: str) -> pl.Expr:
    """Vrai si la valeur est absente ou non significative (« - », « 0 », « N/A », « XXX »…)."""
    v = pl.col(col).cast(pl.String).str.strip_chars()
    return (v.is_null()
            | v.str.to_uppercase().is_in(_VIDES_MAJ)
            | v.str.contains(R.MOTIF_BOURRAGE)).fill_null(True)


def expr_msisdn(col: str) -> pl.Expr:
    """
    Numéro normalisé sur 9 chiffres : suppression des caractères non numériques,
    de « .0 » final (export tableur) et de l'indicatif 237 / 00237 / +237.
    """
    d = (pl.col(col).cast(pl.String).str.strip_chars()
         .str.replace(r"\.0+$", "")
         .str.replace_all(r"\D", ""))
    d = (pl.when(d.str.starts_with("00237")).then(d.str.slice(5))
         .when(d.str.starts_with("237") & (d.str.len_chars() >= 12)).then(d.str.slice(3))
         .otherwise(d))
    return pl.when(d.str.len_chars() > 0).then(d).otherwise(None)


_FORMATS_DATE = [
    ("%Y-%m-%d", 10), ("%d/%m/%Y", 10), ("%d-%m-%Y", 10), ("%Y/%m/%d", 10),
    ("%d.%m.%Y", 10), ("%Y%m%d", 8), ("%d-%b-%Y", 11), ("%d-%b-%y", 9),
    ("%d/%m/%y", 8), ("%m/%d/%Y", 10),
]


def expr_date(col: str) -> pl.Expr:
    """Conversion tolérante d'une date saisie sous des formats hétérogènes."""
    s = pl.col(col).cast(pl.String).str.strip_chars()
    essais = []
    for fmt, longueur in _FORMATS_DATE:
        d = s.str.slice(0, longueur).str.strip_chars().str.to_date(format=fmt, strict=False)
        essais.append(pl.when(d.dt.year().is_between(R.ANNEE_MIN_NAISSANCE, 2100)).then(d))
    return pl.coalesce(essais)


def expr_identifiant(col: str) -> pl.Expr:
    """Numéro de pièce normalisé pour le rapprochement (majuscules, sans séparateurs)."""
    return (pl.col(col).cast(pl.String).str.to_uppercase()
            .str.replace_all(r"[^0-9A-Z]", ""))


# ═════════════════════════════════════════════════════════════════════════════
# STATUTS
# ═════════════════════════════════════════════════════════════════════════════

def categoriser_statut(brut) -> str:
    """Classe une valeur de statut brute dans une catégorie normalisée."""
    if brut is None:
        return "NON_RENSEIGNE"
    s = sans_accents(str(brut)).strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    if not s or s.upper() in _VIDES_MAJ:
        return "NON_RENSEIGNE"
    if s in R.VRAI:
        return "ACTIF"
    if s in R.FAUX:
        return "SUSPENDU"
    m = R.STATUT_MOTS
    a = lambda cle: any(x in f"_{s}_" or x in s for x in m[cle])  # noqa: E731
    if a("eligible"):
        return "ELIGIBLE"
    if a("resilie"):
        return "RESILIE"
    if a("suspension"):
        emission, reception, total = a("emission"), a("reception"), a("total")
        if total or (emission and reception):
            return "SUSP_TOTAL"
        if emission:
            return "SUSP_EMISSION"
        if reception:
            return "SUSP_RECEPTION"
        return "SUSPENDU"
    if a("actif"):
        return "ACTIF"
    return "AUTRE"


def est_actif(cat: str) -> bool:
    return cat == "ACTIF"


# ═════════════════════════════════════════════════════════════════════════════
# TYPES DE PIÈCE
# ═════════════════════════════════════════════════════════════════════════════

def normaliser_type_piece(brut) -> str:
    """
    « 'ANCIENNE_CNI' » → ANCIENNE_CNI ; « Nationalid » / « nationalid3 » → NATIONALID ;
    « residentpermit2 » → RESIDENTPERMIT ; valeur vide → NON_RENSEIGNE.
    """
    if brut is None:
        return "NON_RENSEIGNE"
    s = sans_accents(str(brut)).strip().strip("'\"`").strip().upper()
    if not s or s in _VIDES_MAJ or re.fullmatch(R.MOTIF_BOURRAGE, s):
        return "NON_RENSEIGNE"
    s = re.sub(r"[^A-Z0-9]+", "_", s).strip("_")
    s2 = re.sub(r"_?\d+$", "", s)
    return s2 or s


def est_acte_naissance(type_norm: str) -> bool:
    t = (type_norm or "").upper()
    return t in R.TYPES_ACTE_NAISSANCE or ("NAISSANCE" in t) or ("BIRTH" in t)


def est_nouvelle_cni(type_norm: str) -> bool:
    t = (type_norm or "").upper()
    return t in R.TYPES_NOUVELLE_CNI or "BIO" in t


def age_limite(ref: date, annees: int) -> date:
    try:
        return ref.replace(year=ref.year - annees)
    except ValueError:  # 29 février
        return ref.replace(year=ref.year - annees, day=28)


def mois_decale(ref: date, mois: int) -> date:
    from dateutil.relativedelta import relativedelta
    return ref + relativedelta(months=mois)
