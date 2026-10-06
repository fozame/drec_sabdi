"""
signaux.py
──────────
Signaux d'alerte : informations que les chiffres déclarés ne montrent pas.

Tous les âges et délais sont évalués au MOIS DE LA BASE (mois de réception),
jamais à la date de l'analyse, pour qu'une base de janvier analysée en
septembre donne les mêmes résultats.

Chaque signal indique : nombre de lignes (numéros) concernées, nombre
d'entités (personnes, identifiants, séries), base de calcul, détail, et une
table d'exemples. Les numéros concernés sont conservés pour l'extraction des
lignes complètes (fichier CSV téléchargeable).

Une « identité » est rapprochée par le nom (mots triés, sans accents ni
ponctuation) ET la date de naissance.
"""
from __future__ import annotations

import polars as pl

from . import referentiel as R
from .format import n as fn
from .normalisation import est_acte_naissance

MOIS_MAJORITE = R.AGE_MAJORITE * 12


def idx_mois(col: str) -> pl.Expr:
    """Numéro de mois absolu (année × 12 + mois) : les âges se calculent à l'année et au mois près."""
    return pl.col(col).dt.year().cast(pl.Int32) * 12 + pl.col(col).dt.month().cast(pl.Int32) - 1


def _distance(a: str, b: str, maxi: int) -> int:
    """Distance d'édition (arrêt anticipé au-delà de `maxi`)."""
    if abs(len(a) - len(b)) > maxi:
        return maxi + 1
    prec = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cour = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cour[j] = min(prec[j] + 1, cour[j - 1] + 1, prec[j - 1] + (ca != cb))
        if min(cour) > maxi:
            return maxi + 1
        prec = cour
    return prec[-1]


def _suites_triviales() -> list[str]:
    s = set()
    for base in ("0123456789" * 2, "9876543210" * 2):
        for k in range(6, 13):
            for i in range(10):
                s.add(base[i:i + k])
    return sorted(s)


class Signaux:
    def __init__(self, P: pl.DataFrame, ref_idx: int, periode: str, mineurs_declares: bool):
        """
        P : personnes physiques du périmètre, colonnes compactes (voir lecture.py) +
            « source » (« MINEURS_DECLARES » pour le fichier des mineurs transmis).
        """
        self.P = P
        self.ref_idx = ref_idx
        self.periode = periode
        self.mineurs_declares = mineurs_declares
        self.liste: list[dict] = []
        self.marques: dict[str, pl.DataFrame] = {}     # code → msisdn concernés
        c = set(P.columns)
        self.a_naiss = "date_naissance" in c
        self.a_souscr = "date_activation" in c
        self.a_exp = "date_expiration" in c
        self.a_piece = "piece_id" in c
        self.a_nom = "nom_cle" in c
        self.a_type = "type_piece" in c

    # ─────────────────────────────────────────────────────────────────────────
    def _ajouter(self, code, famille, libelle, lignes: pl.DataFrame | int, entites=None, lib_entites=None,
                 base=None, detail=None, commentaire="", exemples=None, niveau="alerte"):
        n = lignes if isinstance(lignes, int) else lignes.height
        if isinstance(lignes, pl.DataFrame) and n:
            self.marques[code] = lignes.select("msisdn").drop_nulls().head(R.EXTRACTION_MAX_LIGNES)
        self.liste.append({
            "code": code, "famille": famille, "libelle": libelle, "lignes": n,
            "entites": entites, "lib_entites": lib_entites, "base": base,
            "taux": round(n / base * 100, 2) if base else None,
            "detail": detail or [], "commentaire": commentaire,
            "exemples": exemples or {"colonnes": [], "lignes": []},
            "niveau": niveau if n else "info",
        })

    def _par_type(self, df: pl.DataFrame, k: int = 8) -> list:
        if not self.a_type or df.height == 0:
            return []
        g = df.group_by("type_piece").agg(pl.len().alias("n")).sort("n", descending=True).head(k)
        return [("Non renseigné" if t == "NON_RENSEIGNE" else t, int(v))
                for t, v in zip(g["type_piece"].to_list(), g["n"].to_list())]

    def _cols(self, *noms) -> pl.DataFrame:
        """Sous-ensemble de colonnes (évite de copier toutes les colonnes à chaque filtre)."""
        return self.P.select([c for c in dict.fromkeys(("msisdn",) + noms) if c in self.P.columns])

    def _pieces_valides(self, *cols) -> pl.DataFrame:
        return (self._cols("piece_id", "numero_piece_vide", *cols)
                .filter(~pl.col("numero_piece_vide") & (pl.col("piece_id").str.len_chars() >= 4)))

    # ─────────────────────────────────────────────────────────────────────────
    def calculer(self) -> tuple[list[dict], dict]:
        P = self.P
        if P.height == 0:
            return [], {}
        base = P.height
        if self.a_naiss:
            P = P.with_columns((pl.lit(self.ref_idx) - idx_mois("date_naissance")).alias("_age_m"))
            if self.a_souscr:
                P = P.with_columns((idx_mois("date_activation") - idx_mois("date_naissance")).alias("_age_s"))
            self.P = P
            self._mineurs(base)
            self._tuteurs()
        self._pieces(base)
        self._identites(base)
        self._series(base)
        self._formes(base)
        self._dates(base)
        self._noms(base)
        ordre = ["Mineurs", "Identités", "Pièces d'identité", "Dates"]
        self.liste.sort(key=lambda x: ordre.index(x["famille"]) if x["famille"] in ordre else 9)
        return self.liste, self.marques

    # ── Mineurs ──────────────────────────────────────────────────────────────
    def _mineurs(self, base):
        P = self.P
        mineurs = P.filter(pl.col("_age_m").is_between(0, MOIS_MAJORITE - 1))
        caches = mineurs.filter(pl.col("source") != "MINEURS_DECLARES")
        tranches = []
        if caches.height:
            ages = (caches["_age_m"] // 12)
            for lib, a, b in (("moins de 10 ans", 0, 9), ("10 à 13 ans", 10, 13), ("14 à 15 ans", 14, 15),
                              ("16 à 17 ans", 16, 17)):
                tranches.append((lib, int(((ages >= a) & (ages <= b)).sum())))
        comm = (f"Personnes de moins de {R.AGE_MAJORITE} ans en {self.periode} (âge calculé à l'année et au mois "
                f"de naissance), enregistrées comme abonnés ordinaires")
        comm += " et non dans le fichier des mineurs transmis." if self.mineurs_declares else \
            " (aucun fichier de mineurs transmis : aucun n'est déclaré comme tel)."
        self._ajouter("mineurs_non_declares", "Mineurs", "Mineurs non déclarés comme tels",
                      caches, base=base, detail=tranches + [("— par type de pièce", None)] + self._par_type(caches),
                      commentaire=comm)

        if self.a_type:
            adultes = [t for t in mineurs["type_piece"].unique().to_list()
                       if t and t != "NON_RENSEIGNE" and not est_acte_naissance(t)]
            piece_adulte = mineurs.filter(pl.col("type_piece").is_in(adultes)) if adultes else mineurs.head(0)
            self._ajouter("mineurs_piece_adulte", "Mineurs",
                          "Mineurs identifiés avec une pièce d'adulte (CNI, passeport…)", piece_adulte,
                          base=mineurs.height or None, detail=self._par_type(piece_adulte),
                          commentaire="Une pièce d'adulte au nom d'un mineur laisse supposer l'usage de la pièce "
                                      "d'un tiers ou une date de naissance erronée.")

        if self.a_souscr:
            s = P.filter(pl.col("_age_s").is_between(0, MOIS_MAJORITE - 1))
            encore = s.filter(pl.col("_age_m") < MOIS_MAJORITE).height
            self._ajouter("souscrit_mineur", "Mineurs", "Lignes souscrites alors que l'abonné était mineur",
                          s, base=base,
                          detail=[("Encore mineurs aujourd'hui", encore), ("Devenus majeurs depuis", s.height - encore)]
                          + [("— par type de pièce", None)] + self._par_type(s),
                          commentaire="Âge à la date de souscription inférieur à 18 ans (année et mois).")

    # ── Tuteurs ──────────────────────────────────────────────────────────────
    def _tuteurs(self):
        P = self.P
        mineurs = P.filter(pl.col("_age_m").is_between(0, MOIS_MAJORITE - 1) | (pl.col("source") == "MINEURS_DECLARES"))
        if mineurs.height == 0:
            return
        if "date_naissance_tuteur" in P.columns:
            age_t = pl.lit(self.ref_idx) - idx_mois("date_naissance_tuteur")
            t = mineurs.filter(age_t.is_between(0, MOIS_MAJORITE - 1))
            self._ajouter("tuteur_mineur", "Mineurs", "Tuteurs eux-mêmes âgés de moins de 18 ans", t,
                          base=mineurs.height,
                          commentaire=f"Âge du tuteur calculé en {self.periode} à partir de sa date de naissance.")
        if "date_expiration_tuteur" in P.columns:
            e = mineurs.filter(idx_mois("date_expiration_tuteur") < self.ref_idx)
            self._ajouter("tuteur_piece_expiree", "Mineurs", "Pièce du tuteur expirée au mois de la base", e,
                          base=mineurs.height, niveau="info",
                          commentaire="Mineurs dont la pièce d'identité du tuteur est expirée.")

    # ── Pièces partagées et réutilisées ──────────────────────────────────────
    def _pieces(self, base):
        if not self.a_piece:
            return
        V = self._pieces_valides("nom_cle", "date_naissance")
        if self.a_nom:
            aggs = [pl.len().alias("lignes"), pl.col("nom_cle").n_unique().alias("noms")]
            if self.a_naiss:
                aggs.append(pl.col("date_naissance").n_unique().alias("naiss"))
            g = V.filter(pl.col("nom_cle").is_not_null()).group_by("piece_id").agg(aggs)
            partage = g.filter(pl.col("noms") >= 2)
            lignes = V.join(partage.select("piece_id"), on="piece_id", how="semi")
            det = [("2 personnes", int((partage["noms"] == 2).sum())),
                   ("3 à 5 personnes", int(partage["noms"].is_between(3, 5).sum())),
                   ("plus de 5 personnes", int((partage["noms"] > 5).sum()))]
            if self.a_naiss:
                det.append(("dont avec des dates de naissance différentes", int((partage["naiss"] >= 2).sum())))
            top = partage.sort(["noms", "lignes"], descending=True).head(15)
            ex = {"colonnes": ["Numéro de pièce", "Numéros", "Noms différents"] +
                              (["Dates de naissance différentes"] if self.a_naiss else []),
                  "lignes": [[r["piece_id"], fn(r["lignes"]), fn(r["noms"])] +
                             ([fn(r["naiss"])] if self.a_naiss else []) for r in top.to_dicts()]}
            self._ajouter("pieces_partagees", "Pièces d'identité",
                          "Même numéro de pièce utilisé par des personnes différentes", lignes,
                          entites=partage.height, lib_entites="numéros de pièce", base=base, detail=det,
                          exemples=ex, commentaire="Noms différents (après normalisation) sur un même numéro de pièce.")

        g = V.group_by("piece_id").agg(pl.len().alias("n"))
        g2 = g.filter(pl.col("n") >= 2)
        det = [("utilisés 2 fois", int((g2["n"] == 2).sum())), ("3 fois", int((g2["n"] == 3).sum())),
               ("4 à 5 fois", int(g2["n"].is_between(4, 5).sum())), ("6 à 10 fois", int(g2["n"].is_between(6, 10).sum())),
               ("plus de 10 fois", int((g2["n"] > 10).sum()))]
        top = g2.sort("n", descending=True).head(15)
        self._ajouter("pieces_reutilisees", "Pièces d'identité", "Numéros de pièce apparaissant plusieurs fois",
                      V.join(g2.select("piece_id"), on="piece_id", how="semi"),
                      entites=g2.height, lib_entites="numéros de pièce", base=base, detail=det,
                      exemples={"colonnes": ["Numéro de pièce", "Occurrences"],
                                "lignes": [[r["piece_id"], fn(r["n"])] for r in top.to_dicts()]},
                      niveau="info")

    # ── Même personne, plusieurs pièces / plus de 3 lignes ───────────────────
    def _identites(self, base):
        if not (self.a_nom and self.a_naiss):
            return
        I = (self._cols("nom_cle", "date_naissance", "nom_generique", "numero_piece_vide", "piece_id")
             .filter(pl.col("nom_cle").is_not_null() & pl.col("date_naissance").is_not_null()
                     & ~pl.col("nom_generique")))
        if self.a_piece:
            V = I.filter(~pl.col("numero_piece_vide") & (pl.col("piece_id").str.len_chars() >= 4))
            g = (V.group_by(["nom_cle", "date_naissance"])
                 .agg(pl.col("piece_id").unique().alias("pieces"), pl.len().alias("lignes"))
                 .filter(pl.col("pieces").list.len() >= 2))
            proches, exemples = 0, []
            for r in g.head(300_000).iter_rows(named=True):
                p = sorted(r["pieces"])[:20]
                trouve = any(_distance(a, b, R.DISTANCE_PIECES_PROCHES) <= R.DISTANCE_PIECES_PROCHES
                             for i, a in enumerate(p) for b in p[i + 1:])
                if trouve:
                    proches += 1
                    if len(exemples) < 15:
                        exemples.append([", ".join(p[:5]) + (" …" if len(p) > 5 else ""),
                                         r["date_naissance"].strftime("%d/%m/%Y"), fn(r["lignes"])])
            lignes = V.join(g.select(["nom_cle", "date_naissance"]), on=["nom_cle", "date_naissance"], how="semi")
            self._ajouter("meme_personne_plusieurs_pieces", "Identités",
                          "Même personne (nom et date de naissance) sous plusieurs numéros de pièce", lignes,
                          entites=g.height, lib_entites="personnes", base=base,
                          detail=[("dont numéros de pièce très proches (≤ "
                                   f"{R.DISTANCE_PIECES_PROCHES} caractères de différence)", proches),
                                  (f"dont plus de {R.MAX_MODULES} numéros au total",
                                   int((g["lignes"] > R.MAX_MODULES).sum()))],
                          exemples={"colonnes": ["Numéros de pièce", "Date de naissance", "Numéros"],
                                    "lignes": exemples},
                          commentaire="Des numéros de pièce proches pour une même personne suggèrent une variation "
                                      "volontaire pour contourner la limite de trois modules.")
        g = I.group_by(["nom_cle", "date_naissance"]).agg(pl.len().alias("n")).filter(pl.col("n") > R.MAX_MODULES)
        self._ajouter("plus3_par_identite", "Identités",
                      f"Personnes (nom et date de naissance) détenant plus de {R.MAX_MODULES} numéros",
                      I.join(g.select(["nom_cle", "date_naissance"]), on=["nom_cle", "date_naissance"], how="semi"),
                      entites=g.height, lib_entites="personnes", base=base,
                      detail=[("4 à 5 numéros", int(g["n"].is_between(4, 5).sum())),
                              ("6 à 10 numéros", int(g["n"].is_between(6, 10).sum())),
                              ("plus de 10 numéros", int((g["n"] > 10).sum()))],
                      commentaire="Décompte par identité, indépendant du numéro de pièce : non biaisé par "
                                  "l'identifiant à 9 chiffres des nouvelles CNI ni par les variations de numéro.")

    # ── Séries de numéros consécutifs ────────────────────────────────────────
    def _series(self, base):
        if not self.a_piece:
            return
        V = self._pieces_valides("date_activation").filter(pl.col("piece_id").str.contains(r"^\d{6,12}$"))
        if V.height == 0:
            return
        ids = (V.select(pl.col("piece_id").cast(pl.Int64).alias("v")).unique().sort("v")
               .with_columns((pl.col("v").diff().fill_null(10**12) > R.SERIE_ECART_MAX).cum_sum().alias("serie")))
        series = (ids.group_by("serie").agg(pl.len().alias("taille"), pl.col("v").min().alias("debut"),
                                            pl.col("v").max().alias("fin"))
                  .filter(pl.col("taille") >= R.SERIE_LONGUEUR_MIN))
        membres = ids.join(series.select("serie"), on="serie", how="semi")
        lignes = V.with_columns(pl.col("piece_id").cast(pl.Int64).alias("v")).join(membres, on="v", how="inner")
        meme_jour = 0
        if self.a_souscr and lignes.height:
            j = lignes.group_by("serie").agg(pl.col("date_activation").n_unique().alias("jours"))
            meme_jour = int((j["jours"] <= 1).sum())
        top = series.sort("taille", descending=True).head(15)
        self._ajouter("series_consecutives", "Pièces d'identité",
                      f"Séries d'au moins {R.SERIE_LONGUEUR_MIN} numéros de pièce consécutifs", lignes,
                      entites=series.height, lib_entites="séries", base=base,
                      detail=[("Numéros de pièce concernés", membres.height),
                              ("dont séries souscrites en totalité le même jour", meme_jour)],
                      exemples={"colonnes": ["Du numéro", "Au numéro", "Numéros de pièce"],
                                "lignes": [[str(r["debut"]), str(r["fin"]), fn(r["taille"])] for r in top.to_dicts()]},
                      commentaire=(f"Numéros successifs (écart ≤ {R.SERIE_ECART_MAX}) : les pièces réelles "
                                   "d'abonnés différents sont rarement consécutives. À vérifier en priorité "
                                   "lorsque la série est souscrite le même jour."))

    # ── Numéros de pièce de forme suspecte ───────────────────────────────────
    def _formes(self, base):
        if not self.a_piece:
            return
        V = (self._cols("piece_id", "numero_piece_vide")
             .filter(~pl.col("numero_piece_vide") & pl.col("piece_id").is_not_null() & (pl.col("piece_id") != "")))
        p = pl.col("piece_id")
        regles = [
            ("Un seul chiffre ou caractère répété (111111111…)",
             (p.str.len_chars() >= 4) & (p.str.strip_chars(p.str.slice(0, 1)).str.len_chars() == 0)),
            ("Suite croissante ou décroissante (123456789…)", p.is_in(_suites_triviales())),
            ("Trop court (moins de 6 caractères)", p.str.len_chars() < 6),
            ("Identique au numéro de téléphone", p.str.contains(r"^\d+$") &
             (p.str.replace(r"^0+", "") == pl.col("msisdn").cast(pl.String))),
            ("Lettres uniquement", p.str.contains(r"^[A-Z]+$")),
        ]
        masque, det = None, []
        for lib, e in regles:
            det.append((lib, V.filter(e).height))
            masque = e if masque is None else masque | e
        self._ajouter("pieces_forme_suspecte", "Pièces d'identité", "Numéros de pièce de forme suspecte",
                      V.filter(masque), base=base, detail=det)

    # ── Dates incohérentes ───────────────────────────────────────────────────
    def _dates(self, base):
        P = self.P
        if self.a_exp and self.a_souscr:
            e = P.filter(idx_mois("date_expiration") < idx_mois("date_activation"))
            self._ajouter("expiree_a_souscription", "Dates", "Pièce déjà expirée à la date de souscription",
                          e, base=base, detail=self._par_type(e),
                          commentaire="Mois d'expiration antérieur au mois de souscription : la pièce "
                                      "n'aurait pas dû être acceptée.")
        regles = []
        if self.a_naiss:
            regles += [(f"Âge supérieur à {R.AGE_MAX_PLAUSIBLE} ans", pl.col("_age_m") > R.AGE_MAX_PLAUSIBLE * 12),
                       ("Naissance postérieure au mois de la base", pl.col("_age_m") < 0)]
            if self.a_souscr:
                regles.append(("Souscription antérieure à la naissance", pl.col("_age_s") < 0))
        if self.a_souscr:
            regles.append(("Souscription postérieure au mois de la base",
                           idx_mois("date_activation") > self.ref_idx))
        if self.a_exp:
            regles.append((f"Pièce valable plus de {R.VALIDITE_MAX_ANNEES} ans après le mois de la base",
                           idx_mois("date_expiration") > self.ref_idx + R.VALIDITE_MAX_ANNEES * 12))
        if regles:
            masque, det = None, []
            for lib, e in regles:
                det.append((lib, P.filter(e).height))
                masque = e if masque is None else masque | e
            self._ajouter("dates_incoherentes", "Dates", "Dates incohérentes ou invraisemblables",
                          P.filter(masque), base=base, detail=det)
        if self.a_naiss:
            d = P.filter(pl.col("date_naissance").is_not_null())
            g = d.group_by("date_naissance").agg(pl.len().alias("n"))
            if g.height:
                mediane = float(g["n"].median() or 1)
                seuil = max(50, mediane * 20)
                sur = g.filter(pl.col("n") > seuil).sort("n", descending=True)
                janv = d.filter((pl.col("date_naissance").dt.month() == 1) & (pl.col("date_naissance").dt.day() == 1))
                attendu = d.height / 365.25
                self._ajouter("naissances_par_defaut", "Dates",
                              "Dates de naissance sur-représentées (valeurs par défaut probables)",
                              d.join(sur.select("date_naissance"), on="date_naissance", how="semi"),
                              entites=sur.height, lib_entites="dates", base=base,
                              detail=[("Nés un 1er janvier", janv.height),
                                      ("attendu sans valeur par défaut (environ)", int(attendu))],
                              exemples={"colonnes": ["Date de naissance", "Numéros"],
                                        "lignes": [[r["date_naissance"].strftime("%d/%m/%Y"), fn(r["n"])]
                                                   for r in sur.head(12).to_dicts()]},
                              commentaire=f"Dates portées par plus de {fn(int(seuil))} abonnés "
                                          f"(20 fois la fréquence médiane).")

    # ── Noms ─────────────────────────────────────────────────────────────────
    def _noms(self, base):
        if "nom_generique" not in self.P.columns:
            return
        P = self.P
        regles = [("Nom générique (CLIENT, XXX, TEST, INCONNU…)", pl.col("nom_generique")),
                  ("Un seul mot", pl.col("nom_un_mot") & ~pl.col("nom_generique")),
                  ("Contient des chiffres", pl.col("nom_chiffres"))]
        masque, det = None, []
        for lib, e in regles:
            det.append((lib, P.filter(e).height))
            masque = e if masque is None else masque | e
        self._ajouter("noms_suspects", "Identités", "Noms génériques ou incomplets", P.filter(masque),
                      base=base, detail=det)
