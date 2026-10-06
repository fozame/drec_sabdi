"""
analyse.py
──────────
Calcul de l'état des lieux de la base des données d'identification d'un
opérateur pour une période, à partir des fichiers qu'il a transmis.

Principes
─────────
· Les chiffres présentés sont ceux des fichiers reçus : chaque ligne est
  ventilée selon le statut déclaré dans son propre fichier. Si un fichier ne
  comporte pas de colonne de statut, le statut du HLR est utilisé (et indiqué
  en observation).
· Les personnes physiques proviennent des fichiers « majeurs » / « mineurs »
  lorsqu'ils existent ; à défaut, la BDI est ventilée selon la date de
  naissance. Âges et expirations sont évalués au MOIS DE LA BASE (année et
  mois), jamais à la date de l'analyse.
· Périmètre : par défaut, seuls les numéros présents au HLR sont comptés
  (les lignes absentes du HLR sont dénombrées à part).
· Les lignes de la BDI dont le type de pièce désigne une personne morale
  (RCCM…) sont comptées en personnes morales.
· Les contrôles complémentaires (couverture HLR, doublons, âges, statuts
  divergents, échéances) sont calculés séparément et n'altèrent pas le tableau.
"""
from __future__ import annotations

import time
from datetime import datetime

import polars as pl

from . import referentiel as R
from .detection import (FichierDetecte, analyser_fichier, categorie_type_defaut, date_reference,
                        libelle_operateur, libelle_periode, lister_fichiers)
from .extraction import extraire
from .signaux import Signaux, idx_mois
from .format import n as fn, pct as fp, taux
from .lecture import STATUT, charger
from .normalisation import est_acte_naissance, est_nouvelle_cni

VERSION_RESULTATS = 3
SEGMENTS = ["MAJEURS", "MINEURS", "FLOTTE", "M2M"]
LIBELLE_SEGMENT = {"MAJEURS": "personnes physiques majeures", "MINEURS": "personnes physiques mineures",
                   "FLOTTE": "personnes morales (flotte)", "M2M": "personnes morales (M2M)"}


# ═════════════════════════════════════════════════════════════════════════════
# OUTILS
# ═════════════════════════════════════════════════════════════════════════════

COLONNES_SIGNAUX = ("msisdn", "date_naissance", "date_activation", "date_expiration", "date_naissance_tuteur",
                    "date_expiration_tuteur", "piece_id", "numero_piece_vide", "nom_cle", "nom_generique",
                    "nom_un_mot", "nom_chiffres", "type_piece", "type_piece_tuteur")


def _concat(dfs: list[pl.DataFrame]) -> pl.DataFrame:
    dfs = [d for d in dfs if d is not None and d.width > 0]
    if not dfs:
        return pl.DataFrame()
    if len(dfs) == 1:
        return dfs[0]
    try:
        return pl.concat(dfs, how="diagonal_relaxed")
    except Exception:
        return pl.concat(dfs, how="diagonal")


def _vide(df: pl.DataFrame) -> bool:
    return df is None or df.height == 0


def compter_statuts(df: pl.DataFrame, col: str = "statut") -> dict:
    if _vide(df):
        return {}
    res = df.group_by(col).agg(pl.len().alias("n"))
    return {k if k is not None else "NON_RENSEIGNE": int(v)
            for k, v in zip(res[col].to_list(), res["n"].to_list())}


def ligne_resultat(specification: str, valeurs: dict, variantes=None) -> dict:
    return {"specification": specification, "variantes": variantes or [],
            "valeurs": valeurs, "total": int(sum(valeurs.values()))}


def entree(code, statistique, lignes, observation="", type_="simple"):
    if type_ == "non_evaluable":
        for l in lignes:
            l["total"] = None
    return {"code": code, "statistique": statistique, "type": type_, "lignes": lignes,
            "observation_auto": observation.strip(), "observation": observation.strip()}


def _somme_valeurs(lignes: list[dict]) -> dict:
    total = {}
    for l in lignes:
        for k, v in l["valeurs"].items():
            total[k] = total.get(k, 0) + v
    return total


def _libelle_type(t: str) -> str:
    return "Non renseigné" if t == "NON_RENSEIGNE" else t


def _lib_mois(idx: int) -> str:
    return f"{R.MOIS_NOMS[idx % 12]} {idx // 12}"


FORMATS_PIECE = [
    ("Numéro à 9 chiffres", r"^\d{9}$"),
    ("Numérique, autre longueur", r"^\d+$"),
    ("Alphanumérique", r"^[0-9A-Z]+$"),
]


# ═════════════════════════════════════════════════════════════════════════════
# ANALYSE
# ═════════════════════════════════════════════════════════════════════════════

class Analyse:
    def __init__(self, parametres: dict, log=print, etape=None):
        self.p = parametres
        self.log = log
        self.etape = etape or (lambda texte, pct: log(f"── {texte}"))
        self.alertes: list[str] = []
        self.fichiers_info: list[dict] = []
        self.statuts_bruts: list[dict] = []
        self.variantes: dict[str, dict] = {}              # rôle → type normalisé → écritures reçues
        self.hlr: pl.DataFrame | None = None
        self.hlr_unique: pl.DataFrame | None = None
        self.bruts: dict[str, pl.DataFrame] = {}       # rôle → données cumulées
        self.sources: dict[str, list[str]] = {}        # rôle → fichiers
        self.source_statut: dict[str, str] = {}        # rôle → « fichier » / « HLR » / « mixte »
        self.seg: dict[str, pl.DataFrame] = {}         # segment → données
        self.seg_origine: dict[str, str] = {}          # segment → description de la source

        self.trace: list[dict] = []                     # du fichier au tableau
        self.marques: dict[str, dict] = {}              # indicateur → numéros (extractions)
        self.signaux: list[dict] = []

        annee, mois = parametres.get("annee"), parametres.get("mois")
        self.annee, self.mois = annee, mois
        self.ref = date_reference(annee, mois)
        if not (annee and mois):
            self.alertes.append("Mois de la base non renseigné : le mois de l'analyse a été utilisé comme "
                                "référence ; âges et expirations peuvent être faussés.")
        # Référence au mois : âges et délais sont calculés à l'année et au mois près
        self.ref_idx = self.ref.year * 12 + self.ref.month - 1
        self.ref_lib = _lib_mois(self.ref_idx)
        self.lim_exp_idx = self.ref_idx - R.DELAI_EXPIRATION_MOIS
        self.lim_ech_idx = self.ref_idx + R.DELAI_ECHEANCE_MOIS
        self.perimetre = parametres.get("perimetre") or "hlr"
        self.classement = {k.upper(): v for k, v in (parametres.get("classement_types") or {}).items()}

    # ─────────────────────────────────────────────────────────────────────────
    def executer(self) -> dict:
        t0 = time.time()
        self.etape("Lecture des fichiers", 5)
        self._charger()
        self.etape("Constitution des segments", 45)
        self._segments()
        self.etape("Calcul de l'état des lieux", 55)
        etat = self._etat_des_lieux()
        self.etape("Contrôles complémentaires", 75)
        controles = self._controles()
        self.etape("Complétude des champs", 88)
        completude = self._completude()
        if self.p.get("signaux", True):
            self.etape("Signaux d'alerte", 90)
            self._signaux()
        else:
            self.signaux = self._signaux_statuts()
            for code, df in self._marques_statuts.items():
                self.marques[f"sig_{code}"] = {"libelle": code, "msisdn": df, "roles": self._roles_statuts[code]}
            self.alertes.append(self.p.get("motif_sans_signaux") or "Signaux d'alerte non calculés.")
        self.etape("Synthèse", 94)
        synthese = self._synthese(etat, controles)
        for e in etat:
            code = "mineurs" if e["code"] == "total_mineurs" else e["code"]
            if code in self.marques:
                e["extraction"] = code
        for c in controles:
            if c["code"] in self.marques:
                c["extraction"] = c["code"]
        extractions = []
        if self.p.get("dossier_extractions"):
            self.etape("Extraction des lignes concernées", 96)
            extractions = extraire(self.fichiers_lus, self.marques, self.p["dossier_extractions"], self.log)

        colonnes = self._colonnes_statut(etat)
        return {
            "version": VERSION_RESULTATS,
            "operateur": (self.p.get("operateur") or "").upper() or None,
            "operateur_libelle": self.p.get("operateur_libelle") or libelle_operateur(self.p.get("operateur")),
            "periode": {"annee": self.annee, "mois": self.mois,
                        "libelle": libelle_periode(self.annee, self.mois),
                        "date_reference": self.ref.isoformat(), "mois_reference": self.ref_lib},
            "parametres": {
                "age_majorite": R.AGE_MAJORITE, "delai_expiration_mois": R.DELAI_EXPIRATION_MOIS,
                "delai_echeance_mois": R.DELAI_ECHEANCE_MOIS, "max_modules": R.MAX_MODULES,
                "source_physiques": self.p.get("source_physiques", "auto"),
                "perimetre": self.perimetre,
                "mois_limite_expiration": _lib_mois(self.lim_exp_idx),
                "classement_types": self.classement_applique,
            },
            "dossier": self.p.get("dossier"),
            "date_analyse": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "duree_s": round(time.time() - t0, 1),
            "fichiers": self.fichiers_info,
            "origine_segments": self.seg_origine,
            "colonnes_statut": colonnes,
            "etat_des_lieux": etat,
            "controles": controles,
            "completude": completude,
            "statuts_bruts": self.statuts_bruts,
            "signaux": self.signaux,
            "trace": self.trace,
            "extractions": extractions,
            "extractions_id": self.p.get("extractions_id"),
            "synthese": synthese,
            "alertes": self.alertes,
        }

    # ═════════════════════════════════════════════════════════════════════════
    # 1. CHARGEMENT
    # ═════════════════════════════════════════════════════════════════════════
    def _fichiers(self) -> list[FichierDetecte]:
        demandes = self.p.get("fichiers")
        if demandes:
            return [analyser_fichier(f["chemin"], f.get("role"), f.get("colonnes")) for f in demandes]
        return [analyser_fichier(c) for c in lister_fichiers(self.p["dossier"])]

    def _charger(self):
        fichiers = [f for f in self._fichiers() if f.role != "IGNORE"]
        # Ordre : HLR (statuts de référence), fichiers dédiés, puis BDI en dernier : on sait
        # alors si des fichiers majeurs / mineurs ont effectivement pu être lus.
        ordre = {"HLR": 0, "BDI": 2}
        fichiers.sort(key=lambda f: ordre.get(f.role, 1))
        self.fichiers_lus = []
        par_role: dict[str, list] = {}
        total = len(fichiers)
        for i, fd in enumerate(fichiers):
            self.etape(f"Lecture : {fd.nom}", 5 + int(38 * i / max(total, 1)))
            champs = None
            if fd.role == "BDI":
                physiques_lus = bool(set(par_role) & {"MAJEURS", "MINEURS"})
                if physiques_lus and self.p.get("source_physiques", "auto") in ("auto", "fichiers"):
                    champs = {"msisdn"}      # BDI utilisée seulement pour le rapprochement
            try:
                df, info = charger(fd, self.log, champs)
            except Exception as e:
                self.alertes.append(f"{fd.nom} : lecture impossible ({e}).")
                self.log(f"[ERREUR] {fd.nom} : {e}")
                continue
            if "msisdn" not in df.columns:
                self.alertes.append(f"{fd.nom} : colonne du numéro de téléphone introuvable, fichier ignoré.")
                continue
            self.fichiers_lus.append(fd)

            source_statut = "fichier"
            if fd.role == "HLR":
                df = df.with_columns(
                    (pl.col("statut_fichier") if "statut_fichier" in df.columns
                     else pl.lit("NON_RENSEIGNE").cast(STATUT)).alias("statut"))
                if "statut_fichier" not in df.columns:
                    self.alertes.append(f"{fd.nom} : colonne de statut non reconnue dans le HLR.")
            else:
                df = self._joindre_hlr(df)
                utile = ("statut_fichier" in df.columns and
                         df.filter(pl.col("statut_fichier") != "NON_RENSEIGNE").height > 0)
                if utile:
                    df = df.with_columns(pl.col("statut_fichier").alias("statut"))
                elif "statut_hlr" in df.columns:
                    df = df.with_columns(pl.col("statut_hlr").fill_null("NON_RENSEIGNE").alias("statut"))
                    source_statut = "HLR"
                else:
                    df = df.with_columns(pl.lit("NON_RENSEIGNE").cast(STATUT).alias("statut"))
                    source_statut = "aucune"
            df = df.drop([c for c in ("statut_fichier",) if c in df.columns])
            for t, v in info.get("variantes", {}).items():
                self.variantes.setdefault(fd.role, {}).setdefault(t, set()).update(v)

            for s_ in info["statuts_bruts"]:
                self.statuts_bruts.append({"fichier": fd.nom, "role": fd.role, **s_})
            self.fichiers_info.append({
                "nom": fd.nom, "chemin": fd.chemin, "role": fd.role,
                "role_libelle": R.ROLES.get(fd.role, fd.role),
                "lignes": info["lignes"], "colonnes_total": info.get("colonnes_total", 0),
                "correspondances": info["correspondances"],
                "champs_manquants": info["champs_manquants"],
                "source_statut": source_statut,
                "lecture_partielle": champs is not None,
            })

            if fd.role == "HLR":
                cols_hlr = ["msisdn", "statut"] + [c for c in ("statut_declare", "odb") if c in df.columns]
                self.hlr = _concat([self.hlr, df.select(cols_hlr)]) if self.hlr is not None \
                    else df.select(cols_hlr)
                self.hlr_unique = (self.hlr.filter(pl.col("msisdn").is_not_null())
                                   .unique(subset="msisdn", keep="first")
                                   .select(["msisdn", pl.col("statut").alias("statut_hlr")])
                                   .with_columns(pl.lit(True).alias("dans_hlr")))
                del df
                par_role.setdefault("HLR", [])
                continue
            par_role.setdefault(fd.role, []).append((df, source_statut, fd.nom))

        for role, lst in par_role.items():
            if role == "HLR":
                continue
            self.bruts[role] = _concat([d for d, _, _ in lst])
            self.sources[role] = [nm for _, _, nm in lst]
            srcs = {s_ for _, s_, _ in lst}
            self.source_statut[role] = srcs.pop() if len(srcs) == 1 else "mixte"

        if self.hlr is None:
            self.alertes.append("Aucun fichier HLR exploitable : le nombre de numéros est établi à partir "
                                "des fichiers d'identification ; les contrôles de couverture ne sont pas réalisés.")
            self.perimetre = "tous"

    def _joindre_hlr(self, df: pl.DataFrame) -> pl.DataFrame:
        if self.hlr_unique is None:
            return df
        return df.join(self.hlr_unique, on="msisdn", how="left").with_columns(
            pl.col("dans_hlr").fill_null(False))

    # ═════════════════════════════════════════════════════════════════════════
    # 2. SEGMENTS
    # ═════════════════════════════════════════════════════════════════════════
    def _avec_age(self, df: pl.DataFrame) -> pl.DataFrame:
        """Âge au mois de la base : (année, mois) de la base − (année, mois) de naissance."""
        if "date_naissance" not in df.columns:
            return df.with_columns(pl.lit("INCONNU").alias("age_cat"))
        age = pl.lit(self.ref_idx) - idx_mois("date_naissance")
        return df.with_columns(
            pl.when(pl.col("date_naissance").is_null() | (age < 0)).then(pl.lit("INCONNU"))
            .when(age >= R.AGE_MAJORITE * 12).then(pl.lit("MAJEUR"))
            .otherwise(pl.lit("MINEUR")).alias("age_cat"))

    def _classer_types(self, df: pl.DataFrame, source: str, etapes: list) -> tuple[pl.DataFrame, dict]:
        """Sépare les lignes dont le type de pièce désigne une personne morale."""
        autres = {}
        if "type_piece" not in df.columns:
            return df, autres
        types = [t for t in df["type_piece"].unique().to_list() if t]
        cat = {t: self.classement.get(t, categorie_type_defaut(t)) for t in types}
        for c in ("FLOTTE", "M2M", "IGNORE"):
            ts = [t for t, v in cat.items() if v == c]
            if ts:
                part = df.filter(pl.col("type_piece").is_in(ts))
                if part.height:
                    autres[c] = part
                    lib = {"FLOTTE": "classées personnes morales (flotte)", "M2M": "classées M2M",
                           "IGNORE": "non comptées (type de pièce exclu)"}[c]
                    etapes.append((f"Lignes {lib} d'après le type de pièce ({', '.join(ts)})", -part.height))
        self.classement_applique.update({t: v for t, v in cat.items() if v != "PHYSIQUE"})
        exclus = [t for t, v in cat.items() if v != "PHYSIQUE"]
        return (df.filter(~pl.col("type_piece").is_in(exclus)) if exclus else df), autres

    def _perimetre(self, df: pl.DataFrame, etapes: list) -> pl.DataFrame:
        if self.perimetre != "hlr" or "dans_hlr" not in df.columns:
            return df
        hors = df.filter(~pl.col("dans_hlr"))
        if hors.height:
            etapes.append(("Lignes dont le numéro est absent du HLR (hors périmètre)", -hors.height))
        return df.filter(pl.col("dans_hlr"))

    def _segments(self):
        self.classement_applique = {}
        mode = self.p.get("source_physiques") or "auto"
        a_maj, a_min, a_bdi = ("MAJEURS" in self.bruts, "MINEURS" in self.bruts, "BDI" in self.bruts)
        if mode == "auto":
            mode = "fichiers" if (a_maj or a_min) else "bdi"
        if mode == "bdi" and not a_bdi:
            mode = "fichiers"
        if mode == "fichiers" and not (a_maj or a_min) and a_bdi:
            mode = "bdi"
        self.mode_physiques = mode
        self.seg_tous: dict[str, pl.DataFrame] = {}
        morales: dict[str, list] = {"FLOTTE": [], "M2M": []}

        def ajouter_trace(titre, etapes, final_lib, final):
            self.trace.append({"titre": titre, "etapes": etapes, "final_lib": final_lib, "final": final})

        # ── Personnes physiques ─────────────────────────────────────────────
        if mode == "bdi" and a_bdi:
            bdi = self.bruts["BDI"]
            noms = ", ".join(self.sources.get("BDI", []))
            etapes = [(f"Lignes lues ({noms})", bdi.height)]
            bdi, autres = self._classer_types(bdi, "BDI", etapes)
            for c, part in autres.items():
                if c in morales:
                    morales[c].append(part)
            bdi = self._avec_age(bdi)
            self.bruts["BDI"] = bdi
            self.seg_tous["_PHYSIQUES"] = bdi
            bdi_p = self._perimetre(bdi, etapes)
            sans_date = "date_naissance" not in bdi.columns
            if sans_date:
                self.alertes.append("Aucune colonne de date de naissance n'a été reconnue dans la BDI : "
                                    "la répartition majeurs / mineurs est impossible. Choisir la colonne lors "
                                    "de l'examen du dossier.")
                maj, mino = bdi_p, bdi_p.head(0)
                etapes.append(("Pas de date de naissance : toutes les lignes comptées en majeurs", 0))
            else:
                inconnus = bdi_p.filter(pl.col("age_cat") == "INCONNU").height
                if inconnus:
                    etapes.append(("Date de naissance absente, illisible ou postérieure au mois de la base "
                                   "(non classées)", -inconnus))
                maj = bdi_p.filter(pl.col("age_cat") == "MAJEUR")
                mino = bdi_p.filter(pl.col("age_cat") == "MINEUR")
                etapes.append((f"dont mineurs (moins de {R.AGE_MAJORITE} ans en {self.ref_lib})", mino.height))
            self.seg["MAJEURS"], self.seg["MINEURS"] = maj, mino
            self.seg_tous["MAJEURS"], self.seg_tous["MINEURS"] = bdi, bdi.head(0)
            base = f"BDI ({noms})"
            self.seg_origine["MAJEURS"] = f"{base} – {R.AGE_MAJORITE} ans ou plus en {self.ref_lib}"
            self.seg_origine["MINEURS"] = f"{base} – moins de {R.AGE_MAJORITE} ans en {self.ref_lib}"
            ajouter_trace("Personnes physiques (BDI)", etapes, "Personnes physiques majeures", maj.height)
        else:
            for seg in ("MAJEURS", "MINEURS"):
                if seg not in self.bruts:
                    continue
                df = self.bruts[seg]
                etapes = [(f"Lignes lues ({', '.join(self.sources[seg])})", df.height)]
                df, autres = self._classer_types(df, seg, etapes)
                for c, part in autres.items():
                    if c in morales:
                        morales[c].append(part)
                df = self._avec_age(df)
                self.seg_tous[seg] = df
                df = self._perimetre(df, etapes)
                self.seg[seg] = df
                self.seg_origine[seg] = f"Fichier transmis : {', '.join(self.sources[seg])}"
                ajouter_trace(LIBELLE_SEGMENT[seg].capitalize(), etapes, LIBELLE_SEGMENT[seg].capitalize(), df.height)

        # ── Personnes morales ───────────────────────────────────────────────
        for seg in ("FLOTTE", "M2M"):
            parts, etapes, sources = [], [], []
            if seg in self.bruts:
                parts.append(self.bruts[seg])
                etapes.append((f"Lignes lues ({', '.join(self.sources[seg])})", self.bruts[seg].height))
                sources.append(f"fichier transmis ({', '.join(self.sources[seg])})")
            for part in morales[seg]:
                parts.append(part)
                etapes.append(("Lignes de la base des personnes classées ici d'après le type de pièce", part.height))
                sources.append("lignes de la BDI classées d'après le type de pièce")
            if not parts:
                continue
            df = _concat(parts)
            self.seg_tous[seg] = df
            df = self._perimetre(df, etapes)
            self.seg[seg] = df
            self.seg_origine[seg] = "Source : " + " + ".join(sources)
            ajouter_trace(LIBELLE_SEGMENT[seg].capitalize(), etapes, LIBELLE_SEGMENT[seg].capitalize(), df.height)

        for seg in SEGMENTS:
            if seg not in self.seg:
                self.alertes.append(f"Aucune donnée pour les {LIBELLE_SEGMENT[seg]}.")
        if self.hlr is not None:
            etapes = [("Lignes du HLR", self.hlr.height)]
            dup = self.hlr.height - self.hlr_unique.height
            if dup:
                etapes.append(("Numéros en double", -dup))
            self.trace.insert(0, {"titre": "Numéros d'abonnés (HLR)", "etapes": etapes,
                                  "final_lib": "Nombre de numéros d'abonnés", "final": self.hlr.height})
        self.log(f"Personnes physiques : source « {mode} » ; périmètre « {self.perimetre} ».")

    def _src_statut_seg(self, seg: str) -> str:
        if seg in ("FLOTTE", "M2M"):
            return self.source_statut.get(seg, self.source_statut.get("BDI", "fichier"))
        role = seg if (self.mode_physiques == "fichiers" and seg in self.bruts) else "BDI"
        return self.source_statut.get(role, "fichier")

    def _note_statut(self, seg: str) -> str:
        s_ = self._src_statut_seg(seg)
        note = ""
        if s_ == "HLR":
            note = " Statuts issus du HLR (pas de colonne de statut dans le fichier)."
        elif s_ == "aucune":
            note = " Statut non disponible (ni dans le fichier, ni via le HLR)."
        if self.perimetre == "hlr" and self.hlr is not None:
            hors = self.seg_tous.get(seg)
            if hors is not None and "dans_hlr" in hors.columns:
                k = hors.filter(~pl.col("dans_hlr")).height
                if seg in ("MAJEURS", "MINEURS") and self.mode_physiques == "bdi":
                    k = 0
                if k:
                    note += f" {fn(k)} lignes absentes du HLR non comptées."
        return note

    def _marquer(self, code: str, libelle: str, df: pl.DataFrame | None, roles):
        if df is None or df.height == 0 or "msisdn" not in df.columns:
            return
        self.marques[code] = {"libelle": libelle, "roles": set(roles),
                              "msisdn": df.select("msisdn").drop_nulls().head(R.EXTRACTION_MAX_LIGNES)}

    def _roles_seg(self, seg):
        if seg in ("FLOTTE", "M2M"):
            return {seg, "BDI", "MAJEURS", "MINEURS"}
        return {"BDI", "MAJEURS", "MINEURS"}

    # ═════════════════════════════════════════════════════════════════════════
    # 3. ÉTAT DES LIEUX (tableau principal)
    # ═════════════════════════════════════════════════════════════════════════
    def _ventilation_types(self, df: pl.DataFrame, seg: str = "") -> list[dict]:
        if _vide(df):
            return []
        if "type_piece" not in df.columns:
            if "piece_id" not in df.columns:
                return [ligne_resultat("Type de pièce non transmis", compter_statuts(df))]
            # Type de pièce non transmis : ventilation selon la forme du numéro de pièce
            cas = pl.when(pl.col("numero_piece_vide") | pl.col("piece_id").is_null()).then(pl.lit("Non renseigné"))
            for lib, motif in FORMATS_PIECE:
                cas = cas.when(pl.col("piece_id").str.contains(motif)).then(pl.lit(lib))
            g = (df.with_columns(cas.otherwise(pl.lit("Autre format")).alias("_f"))
                 .group_by(["_f", "statut"]).agg(pl.len().alias("n")))
            par = {}
            for f_, s_, k in zip(g["_f"].to_list(), g["statut"].to_list(), g["n"].to_list()):
                par.setdefault(f_, {})[s_ or "NON_RENSEIGNE"] = int(k)
            ordre = [l for l, _ in FORMATS_PIECE] + ["Autre format", "Non renseigné"]
            return [ligne_resultat(f"Format : {f_.lower()}" if f_ != "Non renseigné" else "N° de pièce non renseigné",
                                   par[f_]) for f_ in ordre if f_ in par]
        g = df.group_by(["type_piece", "statut"]).agg(pl.len().alias("n"))
        role = seg if seg in self.variantes and self.mode_physiques == "fichiers" else "BDI"
        variantes = {t: sorted(v)[:6] for t, v in self.variantes.get(role, self.variantes.get(seg, {})).items()}
        par_type: dict[str, dict] = {}
        for t, s, k in zip(g["type_piece"].to_list(), g["statut"].to_list(), g["n"].to_list()):
            par_type.setdefault(t or "NON_RENSEIGNE", {})[s or "NON_RENSEIGNE"] = int(k)
        types = sorted([t for t in par_type if t != "NON_RENSEIGNE"])
        if "NON_RENSEIGNE" in par_type:
            types.append("NON_RENSEIGNE")
        return [ligne_resultat(_libelle_type(t), par_type[t],
                               variantes.get(t) if t != "NON_RENSEIGNE" else []) for t in types]

    def _criteres(self, seg: str, df: pl.DataFrame) -> tuple[pl.Expr | None, list[dict]]:
        """Construit le masque « mal identifié » et le détail par critère."""
        details, masque = [], None
        for code, libelle, type_ctrl, champ, actif in R.CRITERES.get(seg, []):
            if not actif:
                continue
            expr = None
            tuteur_absent = (seg == "MINEURS" and not any(f"{c}_vide" in df.columns or c in df.columns
                                                          for c in ("nom_tuteur", "type_piece_tuteur",
                                                                    "numero_piece_tuteur")))
            if tuteur_absent and champ.endswith("_tuteur"):
                if code == "nom_tuteur_absent":
                    details.append({"code": "tuteur_absent", "n": df.height,
                                    "libelle": "Aucune information sur le tuteur dans le fichier"})
                    masque = pl.lit(True) if masque is None else (masque | pl.lit(True))
                continue
            if type_ctrl == "vide":
                if champ in ("type_piece", "type_piece_tuteur") and champ in df.columns:
                    expr = pl.col(champ) == "NON_RENSEIGNE"
                elif f"{champ}_vide" in df.columns:
                    expr = pl.col(f"{champ}_vide")
            elif type_ctrl == "acte" and champ in df.columns:
                actes = [t for t in df[champ].unique().to_list() if t and est_acte_naissance(t)]
                expr = pl.col(champ).is_in(actes) if actes else pl.lit(False)
            elif type_ctrl == "tuteur_mineur" and champ in df.columns:
                age_t = pl.lit(self.ref_idx) - idx_mois(champ)
                expr = age_t.is_between(0, R.AGE_MAJORITE * 12 - 1).fill_null(False)
            elif type_ctrl == "date_vide":
                if "date_naissance" in df.columns:
                    expr = pl.col("date_naissance").is_null()
                    libelle = "Date de naissance non renseignée ou invalide"
            if expr is None and code in R.CRITERES_FACULTATIFS:
                continue
            if expr is None:
                details.append({"code": code, "libelle": libelle, "n": None,
                                "note": "colonne absente du fichier – critère non évalué"})
                continue
            nb = df.filter(expr).height
            details.append({"code": code, "libelle": libelle, "n": nb})
            masque = expr if masque is None else (masque | expr)
        return masque, details

    def _plus_de_n_modules(self, df: pl.DataFrame):
        if _vide(df) or "piece_id" not in df.columns:
            return None
        base = (df.select([c for c in ("msisdn", "piece_id", "numero_piece_vide", "statut") if c in df.columns])
                .filter(~pl.col("numero_piece_vide") & (pl.col("piece_id").str.len_chars() >= 4)))
        ids = (base.group_by("piece_id").agg(pl.len().alias("nb"))
               .filter(pl.col("nb") > R.MAX_MODULES))
        lignes = base.join(ids.select("piece_id"), on="piece_id", how="semi")
        neuf = ids.filter(pl.col("piece_id").str.contains(r"^\d{9}$"))
        return {
            "valeurs": compter_statuts(lignes),
            "lignes": lignes,
            "identifiants": ids.height,
            "identifiants_9": neuf.height,
            "lignes_9": int(neuf["nb"].sum() or 0) if neuf.height else 0,
            "max": int(ids["nb"].max() or 0) if ids.height else 0,
        }

    def _etat_des_lieux(self) -> list[dict]:
        E: list[dict] = []

        # 1. Numéros d'abonnés
        if self.hlr is not None:
            vals = compter_statuts(self.hlr)
            dup = self.hlr.height - self.hlr_unique.height
            obs = f"Source : HLR ({', '.join(f['nom'] for f in self.fichiers_info if f['role'] == 'HLR')})."
            if dup:
                obs += f" {fn(dup)} numéros en double dans le HLR."
        else:
            union = _concat([d.select(["msisdn", "statut"]) for d in self.seg.values() if not _vide(d)])
            union = union.filter(pl.col("msisdn").is_not_null()).unique(subset="msisdn", keep="first") \
                if not _vide(union) else union
            vals = compter_statuts(union)
            obs = "HLR non transmis : numéros distincts des fichiers d'identification."
        E.append(entree("numeros", "Nombre de numéros d'abonnés", [ligne_resultat("/", vals)], obs))

        # 2-3. Personnes morales
        for seg, stat in (("FLOTTE", "Nombre de personnes morales (flotte)"),
                          ("M2M", "Nombre de personnes morales (M2M)")):
            if seg in self.seg:
                E.append(entree(seg.lower(), stat, [ligne_resultat("/", compter_statuts(self.seg[seg]))],
                                self._note_statut(seg)))
            else:
                E.append(entree(seg.lower(), stat, [ligne_resultat("/", {})],
                                "Fichier non transmis.", "non_evaluable"))

        # 4-7. Personnes physiques ventilées par type de pièce
        for seg, stat, st in (("MAJEURS", "Nombre de personnes physiques majeures",
                               "Nombre total de personnes majeures"),
                              ("MINEURS", "Nombre de personnes physiques mineures",
                               "Nombre total de personnes mineures")):
            df = self.seg.get(seg)
            if _vide(df):
                E.append(entree(seg.lower(), stat, [ligne_resultat("/", {})],
                                "Aucune donnée transmise." if df is None else "Aucun enregistrement.",
                                "non_evaluable"))
                continue
            lignes = self._ventilation_types(df, seg)
            obs = self.seg_origine.get(seg, "") + "." + self._note_statut(seg)
            E.append(entree(seg.lower(), stat, lignes, obs, "ventile"))
            obs_st = ""
            if "age_cat" in df.columns and self.mode_physiques == "fichiers" and seg in self.bruts:
                hors = df.filter(pl.col("age_cat") == ("MINEUR" if seg == "MAJEURS" else "MAJEUR")).height
                if hors:
                    obs_st = (f"Dont {fn(hors)} enregistrements dont la date de naissance correspond à un "
                              f"{'mineur' if seg == 'MAJEURS' else 'majeur'} en {self.ref_lib}.")
            if self.mode_physiques == "bdi" and seg == "MAJEURS" and "BDI" in self.bruts:
                b = self.bruts["BDI"]
                if self.perimetre == "hlr" and "dans_hlr" in b.columns:
                    b = b.filter(pl.col("dans_hlr"))
                inconnus = b.filter(pl.col("age_cat") == "INCONNU").height if "age_cat" in b.columns else 0
                if inconnus and "date_naissance" in b.columns:
                    obs_st = (f"{fn(inconnus)} lignes de la BDI sans date de naissance exploitable "
                              f"ne sont classées ni en majeurs ni en mineurs.")
            if seg == "MINEURS" and self.mode_physiques == "bdi":
                obs_st = ("Mineurs présents dans la BDI (âge calculé au mois de la base) ; aucun fichier de "
                          "mineurs déclarés n'a été transmis. " + obs_st).strip()
            E.append(entree(f"total_{seg.lower()}", st,
                            [ligne_resultat("/", _somme_valeurs(lignes))], obs_st, "sous_total"))
            if seg == "MINEURS":
                self._marquer("mineurs", "Personnes physiques mineures", df, {"BDI", "MINEURS", "MAJEURS"})

        # 8-11. Mal identifiés
        for seg, stat in (("MAJEURS", "Nombre de personnes physiques adultes mal identifiées"),
                          ("MINEURS", "Nombre de personnes physiques mineures mal identifiées"),
                          ("FLOTTE", "Nombre de personnes morales (flotte) mal identifiées"),
                          ("M2M", "Nombre de personnes morales (M2M) mal identifiées")):
            df = self.seg.get(seg)
            if _vide(df):
                E.append(entree(f"mal_{seg.lower()}", stat, [ligne_resultat("/", {})],
                                "Aucune donnée.", "non_evaluable"))
                continue
            masque, details = self._criteres(seg, df)
            if masque is None:
                E.append(entree(f"mal_{seg.lower()}", stat, [ligne_resultat("/", {})],
                                "Colonnes nécessaires absentes : critères non évaluables.", "non_evaluable"))
                continue
            mal = df.filter(masque)
            morceaux = [f"{d['libelle']} : {fn(d['n'])}" for d in details if d["n"]]
            non_eval = [d["libelle"] for d in details if d["n"] is None]
            obs = (f"{fp(mal.height, df.height)} de l'effectif." if mal.height
                   else "Aucune anomalie sur les critères évalués.")
            if morceaux:
                obs += " " + "\n".join(morceaux)
            if non_eval:
                obs += ("\nNon évalué (colonnes absentes du fichier) : "
                        + " ; ".join(x[0].lower() + x[1:] for x in non_eval) + ".")
            e = entree(f"mal_{seg.lower()}", stat, [ligne_resultat("/", compter_statuts(mal))], obs)
            self._marquer(f"mal_{seg.lower()}", stat, mal, self._roles_seg(seg))
            e["criteres"] = details
            e["base"] = df.height
            E.append(e)

        # 12-13. Plus de N modules
        for seg, stat in (("MAJEURS", f"Nombre de personnes physiques majeures détenant plus de "
                                      f"trois ({R.MAX_MODULES:02d}) modules d'identité d'abonné"),
                          ("MINEURS", f"Nombre de personnes physiques mineures détenant plus de "
                                      f"trois ({R.MAX_MODULES:02d}) modules d'identité d'abonné")):
            res = self._plus_de_n_modules(self.seg.get(seg))
            if res is None:
                E.append(entree(f"plus3_{seg.lower()}", stat, [ligne_resultat("/", {})],
                                "Numéro de pièce non disponible.", "non_evaluable"))
                continue
            if res["identifiants"]:
                obs = (f"{fn(res['identifiants'])} identifiants de pièce concernés "
                       f"(jusqu'à {fn(res['max'])} numéros pour un même identifiant). "
                       f"Les résultats indiquent le nombre de numéros.")
            else:
                obs = f"Aucun identifiant de pièce rattaché à plus de {R.MAX_MODULES} numéros."
            if res["identifiants_9"]:
                obs += (f"\nDont {fn(res['identifiants_9'])} identifiants à 9 chiffres ({fn(res['lignes_9'])} numéros) : "
                        f"décompte susceptible d'être biaisé par l'identifiant à 9 chiffres des nouvelles CNI.")
            e = entree(f"plus3_{seg.lower()}", stat, [ligne_resultat("/", res["valeurs"])], obs)
            self._marquer(f"plus3_{seg.lower()}", stat, res.get("lignes"), self._roles_seg(seg))
            e["identifiants"] = res["identifiants"]
            E.append(e)

        # 14. Pièces expirées depuis au moins N mois
        E.append(self._ligne_expirees())

        # 15. Pièces mutilées ou illisibles
        E.append(entree("mutilees", "Admission de pièces d'identité mutilées ou illisibles pour l'identification",
                        [ligne_resultat("/", {})],
                        "Non évaluable à partir des fichiers transmis (pièces numérisées non fournies).",
                        "non_evaluable"))

        for i, e in enumerate(E, 1):
            e["n"] = i
        return E

    def _ligne_expirees(self) -> dict:
        stat = (f"Nombre de numéros dont la pièce d'identité est expirée depuis "
                f"{R.DELAI_EXPIRATION_MOIS:02d} mois au moins")
        parts, detail = [], []
        sans_date = 0
        colonne = False
        for seg, lib in (("MAJEURS", "majeurs"), ("MINEURS", "mineurs")):
            df = self.seg.get(seg)
            if _vide(df) or "date_expiration" not in df.columns:
                continue
            colonne = True
            exp = df.filter(idx_mois("date_expiration") <= self.lim_exp_idx)
            parts.append(exp.select(["msisdn", "statut"]))
            detail.append(f"{fn(exp.height)} {lib}")
            sans_date += df.filter(pl.col("date_expiration").is_null()).height
        if not colonne:
            return entree("expirees", stat, [ligne_resultat("/", {})],
                          "Date d'expiration des pièces absente des fichiers.", "non_evaluable")
        tout = _concat(parts)
        self._marquer("expirees", stat, tout, {"BDI", "MAJEURS", "MINEURS"})
        obs = (f"Pièces expirées en {_lib_mois(self.lim_exp_idx)} ou avant ({R.DELAI_EXPIRATION_MOIS} mois "
               f"avant le mois de la base, {self.ref_lib}). Dont {' et '.join(detail)}.")
        if sans_date:
            obs += f"\n{fn(sans_date)} numéros sans date d'expiration exploitable."
        obs += "\nFlotte et M2M : pas de date d'expiration."
        return entree("expirees", stat, [ligne_resultat("/", compter_statuts(tout))], obs)

    def _colonnes_statut(self, etat: list[dict]) -> list[str]:
        presentes = set()
        for e in etat:
            for l in e["lignes"]:
                presentes |= {k for k, v in l["valeurs"].items() if v}
        cols = [c for c in R.ORDRE_STATUT if c in presentes]
        if "ACTIF" not in cols:
            cols.insert(0, "ACTIF")
        return cols

    # ═════════════════════════════════════════════════════════════════════════
    # 4. CONTRÔLES COMPLÉMENTAIRES
    # ═════════════════════════════════════════════════════════════════════════
    def _controles(self) -> list[dict]:
        C: list[dict] = []

        def ajouter(famille, code, libelle, valeur, base=None, detail=None, commentaire="", niveau=None):
            if niveau is None:
                niveau = "info" if not valeur else "alerte"
            C.append({"famille": famille, "code": code, "libelle": libelle,
                      "valeur": valeur, "base": base,
                      "taux": taux(valeur, base) if (valeur is not None and base) else None,
                      "detail": detail or [], "commentaire": commentaire, "niveau": niveau})

        segs = {k: v for k, v in self.seg.items() if not _vide(v)}
        tous = {k: v for k, v in self.seg_tous.items() if not _vide(v) and not k.startswith("_")}

        # ── Couverture HLR ──────────────────────────────────────────────────
        if self.hlr_unique is not None:
            ident = _concat([d.select("msisdn") for d in list(tous.values()) +
                             [self.bruts.get("BDI")] + [self.bruts.get(r) for r in ("MAJEURS", "MINEURS",
                                                                                   "FLOTTE", "M2M")]
                             if d is not None and not _vide(d)])
            ident = ident.filter(pl.col("msisdn").is_not_null()).unique() if not _vide(ident) else ident
            if not _vide(ident):
                non_id = self.hlr_unique.join(ident, on="msisdn", how="anti")
                vals = compter_statuts(non_id, "statut_hlr")
                self._marquer("hlr_non_identifies", "Numéros du HLR absents des fichiers d'identification",
                              non_id, {"HLR"})
                ajouter("Couverture HLR", "hlr_non_identifies",
                        "Numéros du HLR absents de tous les fichiers d'identification",
                        non_id.height, self.hlr_unique.height,
                        [(R.LIBELLES_STATUT.get(k, k), v) for k, v in _tri_statuts(vals)],
                        "Numéros en service sans identification correspondante dans les fichiers transmis.")
            base_phys = self.seg_tous.get("_PHYSIQUES")
            sources = ([("personnes physiques (BDI)", base_phys, "physiques")] if base_phys is not None else
                       [(LIBELLE_SEGMENT[s_], tous[s_], s_.lower()) for s_ in ("MAJEURS", "MINEURS") if s_ in tous])
            sources += [(LIBELLE_SEGMENT[s_], tous[s_], s_.lower()) for s_ in ("FLOTTE", "M2M") if s_ in tous]
            for lib, df, code in sources:
                if "dans_hlr" in df.columns:
                    absents = df.filter(~pl.col("dans_hlr") & pl.col("msisdn").is_not_null())
                    ajouter("Couverture HLR", f"absents_hlr_{code}",
                            f"Numéros des {lib} absents du HLR"
                            + (" (non comptés dans l'état des lieux)" if self.perimetre == "hlr" else ""),
                            absents.height, df.height)
                    self._marquer(f"absents_hlr_{code}", f"Numéros des {lib} absents du HLR", absents,
                                  {"BDI", "MAJEURS", "MINEURS", "FLOTTE", "M2M"})

        # ── Numéros non exploitables et doublons ────────────────────────────
        for seg, df in segs.items():
            sans = df.filter(pl.col("msisdn_nc")).height
            if sans:
                ajouter("Numéros", f"msisdn_invalide_{seg.lower()}",
                        f"Numéros absents ou non conformes (≠ 9 chiffres) – {LIBELLE_SEGMENT[seg]}", sans, df.height)
            g = (df.filter(pl.col("msisdn").is_not_null()).group_by("msisdn").agg(pl.len().alias("k"))
                 .filter(pl.col("k") > 1))
            ajouter("Numéros", f"doublons_{seg.lower()}",
                    f"Numéros enregistrés plusieurs fois – {LIBELLE_SEGMENT[seg]}",
                    g.height, df.height,
                    [("Enregistrements concernés", int(g["k"].sum() or 0))] if g.height else [])
        if len(segs) > 1:
            croise = _concat([d.select("msisdn").filter(pl.col("msisdn").is_not_null()).unique()
                              .with_columns(pl.lit(s).alias("seg")) for s, d in segs.items()])
            multi = croise.group_by("msisdn").agg(pl.col("seg").n_unique().alias("k")).filter(pl.col("k") > 1)
            detail = []
            if multi.height:
                paires = (croise.join(multi.select("msisdn"), on="msisdn", how="semi")
                          .group_by("msisdn").agg(pl.col("seg").sort().str.join(" + ").alias("p"))
                          .group_by("p").agg(pl.len().alias("n")).sort("n", descending=True))
                detail = [(" / ".join(_lib_court(x) for x in p.split(" + ")), int(k))
                          for p, k in zip(paires["p"].to_list(), paires["n"].to_list())]
            ajouter("Numéros", "doublons_inter", "Numéros présents dans plusieurs catégories d'abonnés",
                    multi.height, None, detail)

        # ── Cohérence des âges ──────────────────────────────────────────────
        ref = self.ref_lib
        for seg in ("MAJEURS", "MINEURS"):
            df = segs.get(seg)
            if df is None or "date_naissance" not in df.columns:
                continue
            sans = df.filter(pl.col("date_naissance").is_null()).height
            futur = df.filter(idx_mois("date_naissance") > self.ref_idx).height
            ajouter("Âges", f"naissance_invalide_{seg.lower()}",
                    f"Date de naissance absente, invalide ou postérieure au mois de la base – {LIBELLE_SEGMENT[seg]}",
                    sans + futur, df.height,
                    [("Absente ou non interprétable", sans), ("Postérieure à la date de référence", futur)]
                    if futur else [])
            if self.mode_physiques == "fichiers" and seg in self.bruts and "age_cat" in df.columns:
                cible = "MINEUR" if seg == "MAJEURS" else "MAJEUR"
                hors = df.filter(pl.col("age_cat") == cible)
                ajouter("Âges", f"age_incoherent_{seg.lower()}",
                        (f"Personnes de moins de {R.AGE_MAJORITE} ans en {ref} dans le fichier des majeurs"
                         if seg == "MAJEURS" else
                         f"Personnes de {R.AGE_MAJORITE} ans ou plus en {ref} dans le fichier des mineurs"),
                        hors.height, df.height,
                        [(R.LIBELLES_STATUT.get(k, k), v) for k, v in _tri_statuts(compter_statuts(hors))])
        df = segs.get("MAJEURS")
        if df is not None and "type_piece" in df.columns:
            actes = [t for t in df["type_piece"].unique().to_list() if t and est_acte_naissance(t)]
            k = df.filter(pl.col("type_piece").is_in(actes)).height if actes else 0
            ajouter("Pièces", "majeurs_acte", "Majeurs identifiés avec un acte de naissance", k, df.height)

        # ── Pièces d'identité ───────────────────────────────────────────────
        for seg in ("MAJEURS", "MINEURS"):
            df = segs.get(seg)
            if df is None or "date_expiration" not in df.columns:
                continue
            ie = idx_mois("date_expiration")
            ech = df.filter((ie > self.ref_idx) & (ie <= self.lim_ech_idx)).height
            exp = df.filter(ie < self.ref_idx).height
            ajouter("Pièces", f"expirees_{seg.lower()}",
                    f"Pièces expirées avant {ref} (toutes anciennetés) – {LIBELLE_SEGMENT[seg]}", exp, df.height)
            ajouter("Pièces", f"echeance_{seg.lower()}",
                    f"Pièces arrivant à expiration dans les {R.DELAI_ECHEANCE_MOIS} mois suivant le mois de la base "
                    f"(jusqu'à {_lib_mois(self.lim_ech_idx)}) – {LIBELLE_SEGMENT[seg]}",
                    ech, df.height, niveau="info")
        df = segs.get("MAJEURS")
        if df is not None and "piece_id" in df.columns:
            neuf = df.filter(pl.col("piece_id").str.contains(r"^\d{9}$"))
            if "type_piece" in df.columns and neuf.height:
                g = neuf.group_by("type_piece").agg(pl.len().alias("n")).sort("n", descending=True).head(6)
                det = [(_libelle_type(t), int(k)) for t, k in zip(g["type_piece"].to_list(), g["n"].to_list())]
            else:
                det = []
            ajouter("Pièces", "identifiants_9", "Numéros de pièce à 9 chiffres (format des nouvelles CNI) – majeurs",
                    neuf.height, df.height, det,
                    "Ces identifiants peuvent fausser le décompte des personnes détenant plus de trois modules.",
                    niveau="info")
            nc = [t for t in df["type_piece"].unique().to_list() if t and est_nouvelle_cni(t)] \
                if "type_piece" in df.columns else []
            if nc:
                k = df.filter(pl.col("type_piece").is_in(nc)).height
                ajouter("Pièces", "nouvelles_cni", "Abonnés identifiés avec une nouvelle CNI / CNI biométrique – majeurs",
                        k, df.height, niveau="info")

        # ── Types de SIM ────────────────────────────────────────────────────
        for seg, attendu_m2m in (("FLOTTE", False), ("M2M", True)):
            df = segs.get(seg)
            if df is None or "sim_type" not in df.columns:
                continue
            st = pl.col("sim_type").cast(pl.String).str.to_uppercase()
            if attendu_m2m:
                k = df.filter(pl.col("sim_type").is_not_null() & (st != "") & ~st.str.contains("M2M")).height
                lib = "Lignes du fichier M2M dont le type de SIM n'est pas M2M"
            else:
                k = df.filter(st.str.contains("M2M")).height
                lib = "Lignes du fichier flotte déclarées de type M2M"
            g = df.group_by("sim_type").agg(pl.len().alias("n")).sort("n", descending=True).head(8)
            ajouter("Catégories", f"sim_type_{seg.lower()}", lib, k, df.height,
                    [(str(t) if t is not None else "(vide)", int(v))
                     for t, v in zip(g["sim_type"].to_list(), g["n"].to_list())])

        # ── Particularités déclarées par l'opérateur (liste rouge, numéros réservés) ──
        for champ, lib in (("liste_rouge", "Lignes marquées en liste rouge (RED_LIST)"),
                           ("reserve_operateur", "Numéros déclarés réservés à l'opérateur")):
            for seg, df in tous.items():
                if champ not in df.columns:
                    continue
                marques = df.filter(pl.col(champ))
                code = f"{champ}_{seg.lower()}"
                ajouter("Particularités opérateur", code, f"{lib} – {LIBELLE_SEGMENT[seg]}", marques.height, df.height,
                        [(R.LIBELLES_STATUT.get(k, k), v) for k, v in _tri_statuts(compter_statuts(marques))],
                        "Information transmise par l'opérateur ; ces lignes restent comptées dans l'état des lieux.",
                        niveau="info")
                self._marquer(code, f"{lib} – {LIBELLE_SEGMENT[seg]}", marques, self._roles_seg(seg))

        # ── BDI et fichiers majeurs / mineurs ───────────────────────────────
        bdi = self.bruts.get("BDI")
        if bdi is not None and self.mode_physiques == "fichiers" and ("MAJEURS" in self.bruts or "MINEURS" in self.bruts):
            nb_f = sum(self.bruts[s].height for s in ("MAJEURS", "MINEURS") if s in self.bruts)
            ident_f = _concat([self.bruts[s].select("msisdn") for s in ("MAJEURS", "MINEURS") if s in self.bruts])
            hors_f = bdi.join(ident_f, on="msisdn", how="anti").height
            hors_b = ident_f.join(bdi.select("msisdn"), on="msisdn", how="anti").height
            ajouter("Cohérence des fichiers", "bdi_vs_fichiers",
                    "Écart entre la BDI et les fichiers majeurs + mineurs (nombre d'enregistrements)",
                    abs(bdi.height - nb_f), bdi.height,
                    [("BDI", bdi.height), ("Majeurs + mineurs", nb_f),
                     ("Numéros de la BDI absents des fichiers majeurs / mineurs", hors_f),
                     ("Numéros des fichiers majeurs / mineurs absents de la BDI", hors_b)])
        return C

    # ═════════════════════════════════════════════════════════════════════════
    # 4 bis. SIGNAUX D'ALERTE
    # ═════════════════════════════════════════════════════════════════════════
    def _signaux_statuts(self) -> list[dict]:
        """Comparaison des statuts déclarés dans les fichiers avec le HLR, et cohérence interne du HLR."""
        self._marques_statuts, self._roles_statuts = {}, {}
        sortie = []
        if self.hlr is None:
            return sortie

        def grossier(col):
            c = pl.col(col).cast(pl.String)
            return (pl.when(c == "ACTIF").then(pl.lit("Actif"))
                    .when(c.is_in(["SUSP_EMISSION", "SUSP_RECEPTION", "SUSP_TOTAL", "SUSPENDU"])).then(pl.lit("Suspendu"))
                    .when(c.is_in(["ELIGIBLE", "RESILIE"])).then(pl.lit("Résilié / éligible"))
                    .otherwise(pl.lit("Autre / non renseigné")))

        def signal(code, libelle, df, base, commentaire, niveau="alerte", detail=None, exemples=None, roles=None):
            n = df.height if df is not None else 0
            if n:
                self._marques_statuts[code] = df.select("msisdn").drop_nulls().head(R.EXTRACTION_MAX_LIGNES)
                self._roles_statuts[code] = roles or {"BDI", "MAJEURS", "MINEURS", "FLOTTE", "M2M"}
            sortie.append({"code": code, "famille": "Statuts", "libelle": libelle, "lignes": n, "entites": None,
                           "lib_entites": None, "base": base, "taux": round(n / base * 100, 2) if base else None,
                           "detail": detail or [], "commentaire": commentaire,
                           "exemples": exemples or {"colonnes": [], "lignes": []},
                           "niveau": niveau if n else "info"})

        # ── Fichiers d'identification portant leur propre statut ────────────
        sources = []
        if self.mode_physiques == "bdi" and "_PHYSIQUES" in self.seg_tous:
            if self.source_statut.get("BDI") == "fichier":
                sources.append(("BDI", self.seg_tous["_PHYSIQUES"]))
        else:
            for seg in ("MAJEURS", "MINEURS"):
                if seg in self.seg_tous and self.source_statut.get(seg) == "fichier":
                    sources.append((LIBELLE_SEGMENT[seg], self.seg_tous[seg]))
        for seg in ("FLOTTE", "M2M"):
            if seg in self.seg_tous and self._src_statut_seg(seg) == "fichier":
                sources.append((LIBELLE_SEGMENT[seg], self.seg_tous[seg]))
        if not sources:
            sortie.append({"code": "statuts_non_comparables", "famille": "Statuts",
                           "libelle": "Comparaison des statuts de la BDI avec le HLR", "lignes": 0, "entites": None,
                           "lib_entites": None, "base": None, "taux": None, "detail": [],
                           "commentaire": "Non réalisable : les fichiers d'identification transmis ne comportent pas de "
                                          "colonne de statut. Les statuts présentés proviennent du HLR. Demander aux "
                                          "opérateurs d'inclure le statut de chaque ligne dans la BDI.",
                           "exemples": {"colonnes": [], "lignes": []}, "niveau": "info"})
        else:
            D = _concat([d.select(["msisdn", "statut", "statut_hlr", "dans_hlr"]) for _, d in sources
                         if "statut_hlr" in d.columns])
            if not _vide(D):
                D = D.with_columns(grossier("statut").alias("f"),
                                   pl.when(pl.col("dans_hlr")).then(grossier("statut_hlr"))
                                   .otherwise(pl.lit("Absent du HLR")).alias("h"))
                base = D.height
                cols = ["Actif", "Suspendu", "Résilié / éligible", "Autre / non renseigné", "Absent du HLR"]
                m = D.group_by(["f", "h"]).agg(pl.len().alias("n"))
                mat = {(a, b): int(k) for a, b, k in zip(m["f"].to_list(), m["h"].to_list(), m["n"].to_list())}
                lignes_f = [l for l in cols[:4] if any(mat.get((l, c)) for c in cols)]
                exemples = {"titre": "Tableau croisé des statuts (fichier / HLR)", "ouvert": True,
                            "colonnes": ["Statut dans le fichier (lignes) / au HLR (colonnes)"] + cols,
                            "lignes": [[l] + [fn(mat.get((l, c), 0)) for c in cols] for l in lignes_f]}
                sources_txt = ", ".join(n for n, _ in sources)
                grave = D.filter(pl.col("f").is_in(["Suspendu", "Résilié / éligible"]) & (pl.col("h") == "Actif"))
                signal("statut_suspendu_bdi_actif_hlr",
                       "Lignes suspendues ou résiliées dans la BDI mais actives au HLR", grave, base,
                       "La ligne est déclarée suspendue ou résiliée par l'opérateur mais fonctionne sur le réseau : "
                       "suspension non exécutée.",
                       detail=[("Suspendues dans la BDI", mat.get(("Suspendu", "Actif"), 0)),
                               ("Résiliées / éligibles dans la BDI", mat.get(("Résilié / éligible", "Actif"), 0))],
                       exemples=exemples)
                a_na = D.filter((pl.col("f") == "Actif") & pl.col("h").is_in(["Suspendu", "Résilié / éligible"]))
                signal("statut_actif_bdi_non_actif_hlr", "Lignes actives dans la BDI mais suspendues ou résiliées au HLR",
                       a_na, base, "Le statut déclaré dans la BDI ne reflète pas l'état du réseau.",
                       detail=[("Suspendues au HLR", mat.get(("Actif", "Suspendu"), 0)),
                               ("Résiliées / éligibles au HLR", mat.get(("Actif", "Résilié / éligible"), 0))])
                absent = D.filter((pl.col("f") == "Actif") & (pl.col("h") == "Absent du HLR"))
                signal("statut_actif_bdi_absent_hlr", "Lignes actives dans la BDI mais absentes du HLR", absent, base,
                       f"Numéro déclaré actif ({sources_txt}) mais inconnu du HLR transmis.")

        # ── Cohérence interne du HLR (statut déclaré / blocages ODB) ────────
        H = self.hlr
        if "statut_declare" in H.columns and "odb" in H.columns:
            base = H.height
            libre = H.filter(pl.col("statut_declare").cast(pl.String).is_in(["ELIGIBLE", "RESILIE"]) & (pl.col("odb") == 0))
            signal("hlr_eligible_non_bloque",
                   "Numéros déclarés éligibles pour réattribution ou résiliés, sans aucun blocage au HLR", libre, base,
                   "Numéros censés être retirés mais encore utilisables en émission et en réception.",
                   roles={"HLR"})
            bloque = H.filter((pl.col("statut_declare").cast(pl.String) == "ACTIF") & (pl.col("odb") > 0))
            det = [("Bloqués en émission seulement", int((bloque["odb"] == 2).sum())),
                   ("Bloqués en réception seulement", int((bloque["odb"] == 1).sum())),
                   ("Bloqués en émission et en réception", int((bloque["odb"] == 3).sum()))]
            signal("hlr_actif_bloque", "Numéros déclarés actifs au HLR mais bloqués (ODB)", bloque, base,
                   "Statut « actif » contredit par les blocages : ces numéros sont comptés comme suspendus dans "
                   "l'état des lieux.", niveau="info", detail=det, roles={"HLR"})
        return sortie

    def _signaux(self):
        self._marques_statuts, self._roles_statuts = {}, {}
        parts = []

        def utiles(df):
            # seules les colonnes exploitées par les signaux (mémoire)
            return df.select([c for c in COLONNES_SIGNAUX if c in df.columns])

        if self.mode_physiques == "bdi" and "_PHYSIQUES" in self.seg_tous:
            b = self.seg_tous["_PHYSIQUES"]
            if self.perimetre == "hlr" and "dans_hlr" in b.columns:
                b = b.filter(pl.col("dans_hlr"))
            parts.append(utiles(b).with_columns(pl.lit("BDI").alias("source")))
        else:
            for seg in ("MAJEURS", "MINEURS"):
                if seg in self.seg:
                    parts.append(utiles(self.seg[seg]).with_columns(
                        pl.lit("MINEURS_DECLARES" if seg == "MINEURS" else seg).alias("source")))
        P = _concat(parts)
        del parts
        if _vide(P):
            self.signaux = self._signaux_statuts()
            for code, df in self._marques_statuts.items():
                self.marques[f"sig_{code}"] = {"libelle": code, "msisdn": df, "roles": self._roles_statuts[code]}
            return
        try:
            liste, marques = Signaux(P, self.ref_idx, self.ref_lib, "MINEURS" in self.bruts).calculer()
        except Exception as e:
            import traceback
            self.log(f"[ERREUR] signaux : {e}\n{traceback.format_exc()}")
            self.alertes.append(f"Signaux d'alerte partiellement calculés ({e}).")
            return
        self.signaux = liste + self._signaux_statuts()
        ordre = ["Mineurs", "Statuts", "Identités", "Pièces d'identité", "Dates"]
        self.signaux.sort(key=lambda x: ordre.index(x["famille"]) if x["famille"] in ordre else 9)
        lib = {x["code"]: x["libelle"] for x in self.signaux}
        marques.update(self._marques_statuts)
        for code, df in marques.items():
            self.marques[f"sig_{code}"] = {"libelle": lib.get(code, code), "msisdn": df,
                                           "roles": self._roles_statuts.get(code, {"BDI", "MAJEURS", "MINEURS"})}
            for x in self.signaux:
                if x["code"] == code:
                    x["extraction"] = f"sig_{code}"

    # ═════════════════════════════════════════════════════════════════════════
    # 5. COMPLÉTUDE DES CHAMPS
    # ═════════════════════════════════════════════════════════════════════════
    def _completude(self) -> list[dict]:
        sortie = []
        for seg in SEGMENTS:
            df = self.seg.get(seg)
            if _vide(df):
                continue
            champs, exprs = [], {}
            for champ in R.CHAMPS_COMPLETUDE[seg]:
                if champ == "msisdn":
                    exprs[champ] = (pl.col("msisdn").is_null(), pl.col("msisdn").is_not_null() & pl.col("msisdn_nc"))
                elif champ in ("type_piece", "type_piece_tuteur") and champ in df.columns:
                    exprs[champ] = (pl.col(champ) == "NON_RENSEIGNE", None)
                elif champ in ("date_naissance", "date_expiration", "date_activation") and f"{champ}_vide" in df.columns:
                    exprs[champ] = (pl.col(f"{champ}_vide"), ~pl.col(f"{champ}_vide") & pl.col(champ).is_null())
                elif champ == "imei" and "imei_vide" in df.columns:
                    exprs[champ] = (pl.col("imei_vide"), pl.col("imei_invalide"))
                elif f"{champ}_vide" in df.columns:
                    exprs[champ] = (pl.col(f"{champ}_vide"), None)
            sel = []
            for champ, (ev, ei) in exprs.items():
                sel.append(ev.sum().alias(f"{champ}|v"))
                if ei is not None:
                    sel.append(ei.sum().alias(f"{champ}|i"))
            sommes = df.select(sel).row(0, named=True) if sel else {}
            for champ in R.CHAMPS_COMPLETUDE[seg]:
                lib = R.LIBELLES_CHAMPS.get(champ, champ)
                if champ not in exprs:
                    champs.append({"champ": champ, "libelle": lib, "present": False})
                    continue
                k_vide = int(sommes.get(f"{champ}|v") or 0)
                k_inv = int(sommes.get(f"{champ}|i") or 0)
                champs.append({"champ": champ, "libelle": lib, "present": True,
                               "vides": k_vide, "invalides": k_inv, "taux": taux(k_vide + k_inv, df.height)})
            sortie.append({"segment": seg, "libelle": LIBELLE_SEGMENT[seg].capitalize(),
                           "effectif": df.height, "champs": champs})
        return sortie

    # ═════════════════════════════════════════════════════════════════════════
    # 6. SYNTHÈSE
    # ═════════════════════════════════════════════════════════════════════════
    def _synthese(self, etat: list[dict], controles: list[dict]) -> dict:
        par_code = {e["code"]: e for e in etat}

        def tot(code):
            e = par_code.get(code)
            return e["lignes"][0]["total"] if e and e["type"] != "non_evaluable" and e["lignes"] else None

        def val(code, cat):
            e = par_code.get(code)
            return e["lignes"][0]["valeurs"].get(cat, 0) if e and e["lignes"] else 0

        numeros = tot("numeros")
        maj, mino = tot("total_majeurs"), tot("total_mineurs")
        flotte, m2m = tot("flotte"), tot("m2m")
        mal = {s: tot(f"mal_{s.lower()}") for s in SEGMENTS}
        bases = {"MAJEURS": maj, "MINEURS": mino, "FLOTTE": flotte, "M2M": m2m}
        mal_total = sum(v for v in mal.values() if v)
        base_total = sum(v for v in bases.values() if v)
        ctrl = {c["code"]: c for c in controles}
        non_id = ctrl.get("hlr_non_identifies")
        exp = tot("expirees")
        plus3 = par_code.get("plus3_majeurs")

        kpis = [
            {"code": "numeros", "libelle": "Numéros d'abonnés", "valeur": numeros,
             "detail": f"dont {fn(val('numeros', 'ACTIF'))} actifs ({fp(val('numeros', 'ACTIF'), numeros)})"
             if numeros else ""},
            {"code": "physiques", "libelle": "Personnes physiques",
             "valeur": (maj or 0) + (mino or 0) if (maj or mino) else None,
             "detail": f"{fn(maj or 0)} majeures · {fn(mino or 0)} mineures"},
            {"code": "morales", "libelle": "Personnes morales",
             "valeur": (flotte or 0) + (m2m or 0) if (flotte or m2m) else None,
             "detail": f"{fn(flotte or 0)} flotte · {fn(m2m or 0)} M2M"},
            {"code": "mal", "libelle": "Abonnés mal identifiés", "valeur": mal_total,
             "detail": f"{fp(mal_total, base_total)} des abonnés identifiés", "alerte": bool(mal_total)},
        ]
        if non_id:
            kpis.append({"code": "non_identifies", "libelle": "Numéros du HLR sans identification",
                         "valeur": non_id["valeur"], "detail": f"{fp(non_id['valeur'], non_id['base'])} du HLR",
                         "alerte": bool(non_id["valeur"])})
        if exp is not None:
            kpis.append({"code": "expirees", "libelle": f"Pièces expirées depuis ≥ {R.DELAI_EXPIRATION_MOIS} mois",
                         "valeur": exp, "detail": f"{fp(exp, (maj or 0) + (mino or 0))} des personnes physiques",
                         "alerte": bool(exp)})
        if plus3 and plus3["type"] != "non_evaluable":
            kpis.append({"code": "plus3", "libelle": f"Numéros rattachés à > {R.MAX_MODULES} SIM par pièce",
                         "valeur": plus3["lignes"][0]["total"],
                         "detail": f"{fn(plus3.get('identifiants', 0))} identifiants de pièce (majeurs)"})

        sig = {x["code"]: x for x in self.signaux}
        for code, lib in (("mineurs_non_declares", "Mineurs non déclarés"),
                          ("pieces_partagees", "Pièces partagées entre personnes différentes"),
                          ("plus3_par_identite", f"Personnes à plus de {R.MAX_MODULES} numéros (nom + date de naissance)")):
            x = sig.get(code)
            if x:
                det = (f"{fn(x['entites'])} {x['lib_entites']}" if x.get("entites") is not None
                       else f"{fp(x['lignes'], x['base'])} des personnes physiques")
                kpis.append({"code": f"sig_{code}", "libelle": lib, "valeur": x["lignes"],
                             "detail": det + " · numéros concernés", "alerte": bool(x["lignes"])})

        taux_mal = [{"segment": s, "libelle": LIBELLE_SEGMENT[s].capitalize(), "mal": mal[s], "base": bases[s],
                     "taux": taux(mal[s], bases[s]) if mal[s] is not None and bases[s] else None}
                    for s in SEGMENTS]
        types = []
        e = par_code.get("majeurs")
        if e and e["type"] == "ventile":
            types = sorted([{"type": l["specification"], "total": l["total"]} for l in e["lignes"]],
                           key=lambda d: -d["total"])
        statuts = []
        e = par_code.get("numeros")
        if e and e["lignes"]:
            statuts = [{"categorie": k, "libelle": R.LIBELLES_STATUT.get(k, k), "n": v}
                       for k, v in _tri_statuts(e["lignes"][0]["valeurs"]) if v]
        return {"kpis": kpis, "taux_mal": taux_mal, "types_majeurs": types, "statuts_numeros": statuts,
                "mode_physiques": self.mode_physiques}


# ═════════════════════════════════════════════════════════════════════════════

def _tri_statuts(vals: dict):
    return sorted(vals.items(), key=lambda kv: R.ORDRE_STATUT.index(kv[0]) if kv[0] in R.ORDRE_STATUT else 99)


def _lib_court(seg: str) -> str:
    return {"MAJEURS": "Majeurs", "MINEURS": "Mineurs", "FLOTTE": "Flotte", "M2M": "M2M"}.get(seg, seg)


def lancer_analyse(parametres: dict, log=print, etape=None) -> dict:
    return Analyse(parametres, log=log, etape=etape).executer()
