"""
extraction.py
─────────────
Extraction des lignes complètes (telles que reçues) correspondant à un
indicateur ou à un signal, pour vérification et investigation.

Les numéros marqués pendant l'analyse sont rapprochés des fichiers d'origine
(relecture en flux) ; un fichier CSV est produit par indicateur, lisible dans
Excel (séparateur « ; », UTF-8 avec BOM).
"""
from __future__ import annotations

import os

import polars as pl

from . import referentiel as R
from .detection import FichierDetecte
from .lecture import scanner, noms_colonnes, lots
from .normalisation import expr_msisdn


def extraire(fichiers: list[FichierDetecte], marques: dict[str, dict], dossier: str, log=print) -> list[dict]:
    """
    marques : {code: {"libelle", "msisdn": DataFrame[msisdn], "roles": set[str]}}
    Retourne la liste des extractions produites [{code, libelle, fichier, lignes, tronque}].
    """
    os.makedirs(dossier, exist_ok=True)
    tables = []
    for code, m in marques.items():
        df = m["msisdn"]
        if df is None or df.height == 0:
            continue
        tables.append(df.select(pl.col("msisdn").cast(pl.Int64)).unique()
                      .with_columns(pl.lit(code).alias("_indicateur")))
    if not tables:
        return []
    drapeaux = pl.concat(tables)
    sorties: dict[str, list[pl.DataFrame]] = {}
    for fd in fichiers:
        codes = [c for c, m in marques.items() if fd.role in m["roles"]]
        if not codes or "msisdn" not in fd.correspondances:
            continue
        try:
            lf, tmp = scanner(fd)
            cols = noms_colonnes(lf)
            if tmp:
                os.remove(tmp)
            col_m = fd.correspondances["msisdn"]
            if col_m not in cols:
                continue
            d = drapeaux.filter(pl.col("_indicateur").is_in(codes))
            # lecture par lots : seules les lignes concernées sont gardées en mémoire
            morceaux = []
            for x in lots(fd):
                morceaux.append(
                    x.lazy().with_columns(expr_msisdn(col_m).cast(pl.Int64, strict=False).alias("_m"))
                     .join(d.lazy(), left_on="_m", right_on="msisdn", how="inner")
                     .with_columns(pl.lit(fd.nom).alias("fichier_source"))
                     .drop("_m").collect())
            if not morceaux:
                continue
            res = pl.concat(morceaux, how="vertical")
        except Exception as e:
            log(f"Extraction impossible pour {fd.nom} : {e}")
            continue
        for (code,), part in res.partition_by("_indicateur", as_dict=True).items():
            sorties.setdefault(code, []).append(part.drop("_indicateur"))

    produits = []
    for code, parts in sorties.items():
        try:
            df = pl.concat(parts, how="diagonal")
        except Exception:
            df = parts[0]
        tronque = df.height >= R.EXTRACTION_MAX_LIGNES
        df = df.head(R.EXTRACTION_MAX_LIGNES)
        chemin = os.path.join(dossier, f"{code}.csv")
        try:
            df.write_csv(chemin, separator=";", include_bom=True)
        except TypeError:
            df.write_csv(chemin, separator=";")
        produits.append({"code": code, "libelle": marques[code]["libelle"], "fichier": chemin,
                         "lignes": df.height, "tronque": tronque})
    log(f"{len(produits)} extractions de lignes produites.")
    return produits
