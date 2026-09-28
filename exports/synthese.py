"""
synthese.py
───────────
Synthèse d'un mois, tous opérateurs confondus : chiffres clés comparés,
évolution par rapport au mois précédent et constats principaux formulés de
manière factuelle à partir des résultats (aucune interprétation ajoutée).

Pour chaque opérateur, l'analyse retenue est celle qui a été validée ; à
défaut, la plus récente (signalée « non validée »).
"""
from __future__ import annotations

import math

from moteur import referentiel as R
from moteur.format import n as fn, pct as fp


# ═════════════════════════════════════════════════════════════════════════════
# LECTURE DES INDICATEURS DANS UN RÉSULTAT
# ═════════════════════════════════════════════════════════════════════════════

def _etat(res, code):
    return next((e for e in res.get("etat_des_lieux", []) if e["code"] == code), None)


def _total(res, code):
    e = _etat(res, code)
    if not e or e["type"] == "non_evaluable" or not e["lignes"]:
        return None
    return sum(l["total"] or 0 for l in e["lignes"])


def _signal(res, code):
    return next((x for x in res.get("signaux", []) if x["code"] == code), None)


def _controle(res, code):
    return next((c for c in res.get("controles", []) if c["code"] == code), None)


def _physiques(res):
    a, b = _total(res, "total_majeurs"), _total(res, "total_mineurs")
    return None if a is None and b is None else (a or 0) + (b or 0)


def _morales(res):
    a, b = _total(res, "flotte"), _total(res, "m2m")
    return None if a is None and b is None else (a or 0) + (b or 0)


def _mal(res):
    vals = [_total(res, f"mal_{s}") for s in ("majeurs", "mineurs", "flotte", "m2m")]
    if all(v is None for v in vals):
        return None, None
    base = sum(v or 0 for v in (_total(res, "total_majeurs"), _total(res, "total_mineurs"),
                                _total(res, "flotte"), _total(res, "m2m")))
    return sum(v or 0 for v in vals), base or None


def _sig(code):
    def f(res):
        x = _signal(res, code)
        if not x or x.get("code") == "statuts_non_comparables":
            return None, None, None
        return x["lignes"], x.get("base"), x.get("entites")
    return f


def _ctrl(code):
    def f(res):
        c = _controle(res, code)
        return (c["valeur"], c.get("base"), None) if c else (None, None, None)
    return f


# (code, libellé, fonction → (valeur, base, entités), anomalie ?, poids pour les constats)
INDICATEURS = [
    ("numeros", "Numéros d'abonnés (HLR)", lambda r: (_total(r, "numeros"), None, None), False, 0),
    ("physiques", "Personnes physiques", lambda r: (_physiques(r), None, None), False, 0),
    ("morales", "Personnes morales (flotte + M2M)", lambda r: (_morales(r), None, None), False, 0),
    ("hlr_non_identifies", "Numéros du HLR sans identification", _ctrl("hlr_non_identifies"), True, 3),
    ("mal", "Abonnés mal identifiés", lambda r: (*_mal(r), None), True, 2),
    ("mineurs_non_declares", "Mineurs non déclarés", _sig("mineurs_non_declares"), True, 4),
    ("pieces_partagees", "Pièces partagées entre personnes différentes", _sig("pieces_partagees"), True, 3),
    ("plus3_par_identite", f"Personnes détenant plus de {R.MAX_MODULES} numéros", _sig("plus3_par_identite"), True, 3),
    ("series_consecutives", "Numéros de pièce en séries consécutives", _sig("series_consecutives"), True, 2),
    ("expirees", f"Pièces expirées depuis au moins {R.DELAI_EXPIRATION_MOIS} mois",
     lambda r: (_total(r, "expirees"), _physiques(r), None), True, 1),
    ("statut_suspendu_bdi_actif_hlr", "Suspendus dans la BDI mais actifs au HLR",
     _sig("statut_suspendu_bdi_actif_hlr"), True, 5),
    ("hlr_eligible_non_bloque", "Numéros éligibles à la réattribution encore utilisables",
     _sig("hlr_eligible_non_bloque"), True, 4),
]

PHRASES = {
    "hlr_non_identifies": "{op} : {n} numéros du HLR ({t}) n'ont aucune identification dans les fichiers transmis.",
    "mal": "{op} : {n} abonnés mal identifiés, soit {t} des abonnés identifiés.",
    "mineurs_non_declares": "{op} : {n} mineurs figurent parmi les abonnés ordinaires sans être déclarés comme tels.",
    "pieces_partagees": "{op} : {e} numéros de pièce sont utilisés par des personnes différentes "
                        "({n} numéros de téléphone concernés).",
    "plus3_par_identite": "{op} : {e} personnes détiennent plus de " + str(R.MAX_MODULES) +
                          " numéros ({n} numéros de téléphone concernés).",
    "series_consecutives": "{op} : {e} séries de numéros de pièce consécutifs ({n} numéros de téléphone concernés).",
    "expirees": "{op} : {t} des personnes physiques ({n}) ont une pièce expirée depuis au moins "
                + str(R.DELAI_EXPIRATION_MOIS) + " mois.",
    "statut_suspendu_bdi_actif_hlr": "{op} : {n} lignes déclarées suspendues ou résiliées dans la BDI sont actives au HLR.",
    "hlr_eligible_non_bloque": "{op} : {n} numéros déclarés éligibles à la réattribution restent utilisables "
                               "(aucun blocage au HLR).",
}


def mois_precedent(annee, mois):
    return (annee - 1, 12) if mois == 1 else (annee, mois - 1)


def libelle_mois(annee, mois):
    return f"{R.MOIS_NOMS[mois - 1]} {annee}"


# ═════════════════════════════════════════════════════════════════════════════
# CONSTRUCTION
# ═════════════════════════════════════════════════════════════════════════════

def construire(annee: int, mois: int, charger_reference, operateurs: list[str], note=None) -> dict:
    """
    charger_reference(operateur, annee, mois) → (id, validée ?, résultats) ou None.
    """
    ap, mp = mois_precedent(annee, mois)
    colonnes = []
    for op in operateurs:
        ref = charger_reference(op, annee, mois)
        if not ref:
            continue
        aid, validee, res = ref
        prec = charger_reference(op, ap, mp)
        colonnes.append({"operateur": op, "libelle": res.get("operateur_libelle", op), "id": aid,
                         "validee": validee, "res": res, "prec": prec[2] if prec else None,
                         "prec_id": prec[0] if prec else None})

    lignes = []
    for code, lib, f, anomalie, _ in INDICATEURS:
        cellules, utile = [], False
        for c in colonnes:
            v, base, ent = f(c["res"])
            vp = f(c["prec"])[0] if c["prec"] else None
            if v is not None:
                utile = True
            var = (v - vp) if (v is not None and vp is not None) else None
            cellules.append({"v": v, "base": base, "entites": ent, "prec": vp, "var": var,
                             "txt": fn(v) if v is not None else "/",
                             "taux": fp(v, base) if (v is not None and base) else "",
                             "var_txt": _variation(v, vp)})
        if utile:
            lignes.append({"code": code, "libelle": lib, "anomalie": anomalie, "cellules": cellules})

    return {"annee": annee, "mois": mois, "libelle": libelle_mois(annee, mois),
            "libelle_precedent": libelle_mois(ap, mp), "colonnes": colonnes, "lignes": lignes,
            "constats": constats(colonnes, libelle_mois(ap, mp)),
            "note": note or ""}


def _variation(v, vp):
    if v is None or vp is None:
        return ""
    if vp == 0:
        return "nouveau" if v else "="
    d = (v - vp) / vp * 100
    if abs(d) < 0.05:
        return "="
    return f"{'+' if d > 0 else '−'}{abs(d):.1f}".replace(".", ",") + " %"


def constats(colonnes: list[dict], lib_prec: str, maximum: int = 7, max_variations: int = 2) -> list[str]:
    """
    Constats factuels : les anomalies les plus importantes en niveau, puis jusqu'à
    `max_variations` évolutions marquées (± 10 % sur au moins 100 numéros).
    """
    niveaux, variations = [], []
    for c in colonnes:
        for code, lib, f, anomalie, poids in INDICATEURS:
            if not anomalie or code not in PHRASES:
                continue
            v, base, ent = f(c["res"])
            if not v:
                continue
            texte = PHRASES[code].format(op=c["libelle"], n=fn(v), t=fp(v, base) if base else "",
                                         e=fn(ent) if ent is not None else fn(v))
            niveaux.append((poids * (1 + math.log10(v + 1)) * (1 + (v / base if base else 0)), c["operateur"], texte))
            if c["prec"]:
                vp = f(c["prec"])[0]
                if vp and max(v, vp) >= 100 and abs(v - vp) / vp >= 0.10:
                    sens = "en hausse" if v > vp else "en baisse"
                    variations.append((poids * min(abs(v - vp) / vp, 3) * (1.2 if v > vp else 1), c["operateur"],
                                       f"{c['libelle']} : {lib[0].lower() + lib[1:]} {sens} de "
                                       f"{_variation(v, vp).lstrip('+−')} par rapport à {lib_prec} "
                                       f"({fn(vp)} → {fn(v)})."))
    niveaux.sort(key=lambda x: -x[0])
    variations.sort(key=lambda x: -x[0])
    var_retenues = variations[:max_variations]
    choisis = niveaux[:maximum - len(var_retenues)]
    # au moins un constat par opérateur lorsque c'est possible
    for c in colonnes:
        if choisis and c["operateur"] not in {op for _, op, _ in choisis}:
            autre = next((x for x in niveaux if x[1] == c["operateur"]), None)
            if autre:
                # remplace le dernier constat d'un opérateur déjà représenté plusieurs fois
                for i in range(len(choisis) - 1, -1, -1):
                    if sum(1 for _, op, _ in choisis if op == choisis[i][1]) > 1:
                        choisis[i] = autre
                        break
    choisis.sort(key=lambda x: -x[0])
    sortie = []
    for _, _, t in choisis + var_retenues:
        if t not in sortie:
            sortie.append(t)
    return sortie
