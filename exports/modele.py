"""
modele.py
─────────
Mise en forme commune des résultats pour tous les supports (écran, PDF, Word,
Excel, impression). Chaque export s'appuie sur ce modèle afin que les chiffres,
libellés et numérotations soient strictement identiques partout.
"""
from __future__ import annotations

from moteur import referentiel as R
from moteur.format import n as fn, pct as fp

ROMAINS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


def titre_section(res: dict, indice: int | None = None) -> str:
    p = res.get("periode", {})
    periode = p.get("libelle") or "période non précisée"
    prefixe = f"{ROMAINS[indice]}. " if indice is not None and indice < len(ROMAINS) else ""
    return (f"{prefixe}{res.get('operateur_libelle', 'Opérateur')} (mois de {periode}) – "
            f"État des lieux de la base des données d'identification")


def colonnes(res: dict) -> list[tuple[str, str]]:
    return [(c, R.LIBELLES_STATUT_COURTS.get(c, c)) for c in res.get("colonnes_statut", ["ACTIF"])]


def tableau_etat(res: dict, numero_depart: int = 1) -> dict:
    """
    Retourne :
      colonnes : [(code, libellé)]
      lignes   : liste de lignes affichables ; chaque ligne porte
                 n, statistique, specification, variantes, valeurs (textes), total,
                 observation, style, debut_groupe, taille_groupe
    """
    cols = colonnes(res)
    lignes = []
    num = numero_depart
    for e in res.get("etat_des_lieux", []):
        obs = e.get("observation") if e.get("observation") is not None else e.get("observation_auto", "")
        k = len(e["lignes"]) or 1
        style = {"sous_total": "sous_total", "non_evaluable": "non_evaluable"}.get(e["type"], "normal")
        for i, l in enumerate(e["lignes"] or [{"specification": "/", "valeurs": {}, "total": None}]):
            if style == "non_evaluable":
                vals, total = ["/"] * len(cols), "/"
            else:
                vals = [fn(l["valeurs"].get(c, 0)) for c, _ in cols]
                total = fn(l["total"])
            lignes.append({
                "n": num, "code": e["code"],
                "statistique": e["statistique"],
                "specification": l["specification"],
                "variantes": l.get("variantes", []),
                "valeurs": vals, "total": total,
                "observation": obs or "/",
                "style": style,
                "debut_groupe": i == 0, "taille_groupe": k,
            })
        num += 1
    return {"colonnes": cols, "lignes": lignes, "numero_suivant": num}


def controles(res: dict) -> list[dict]:
    sortie = []
    for c in res.get("controles", []):
        detail = "; ".join(f"{a} : {fn(b)}" for a, b in c.get("detail", []) if b is not None)
        sortie.append({
            "famille": c["famille"], "libelle": c["libelle"],
            "valeur": fn(c["valeur"]), "base": fn(c["base"]) if c.get("base") else "–",
            "taux": fp(c["valeur"], c["base"]) if c.get("base") else "–",
            "detail": detail, "commentaire": c.get("commentaire", ""),
            "niveau": c.get("niveau", "info"), "brut": c,
        })
    return sortie


def completude(res: dict) -> list[dict]:
    corresp = {}
    for f in res.get("fichiers", []):
        for champ, col in f.get("correspondances", {}).items():
            corresp.setdefault((f["role"], champ), col)
    sortie = []
    for bloc in res.get("completude", []):
        seg = bloc["segment"]
        lignes = []
        for c in bloc["champs"]:
            col = corresp.get((seg, c["champ"])) or corresp.get(("BDI", c["champ"])) or ""
            if not c["present"]:
                lignes.append({"libelle": c["libelle"], "colonne": "absente", "vides": "–",
                               "invalides": "–", "taux": "–", "absent": True, "taux_num": None})
            else:
                lignes.append({"libelle": c["libelle"], "colonne": col, "vides": fn(c["vides"]),
                               "invalides": fn(c["invalides"]) if c["invalides"] else "–",
                               "taux": fp(c["vides"] + c["invalides"], bloc["effectif"]),
                               "absent": False, "taux_num": c.get("taux")})
        sortie.append({"segment": seg, "libelle": bloc["libelle"], "effectif": fn(bloc["effectif"]),
                       "lignes": lignes})
    return sortie


def fichiers(res: dict) -> list[dict]:
    sortie = []
    for f in res.get("fichiers", []):
        sortie.append({
            "nom": f["nom"], "role": f["role_libelle"], "lignes": fn(f["lignes"]),
            "reconnues": f"{len(f.get('correspondances', {}))} / {f.get('colonnes_total', 0)}",
            "correspondances": "; ".join(f"{R.LIBELLES_CHAMPS.get(k, k)} ← {v}"
                                         for k, v in f.get("correspondances", {}).items()),
            "manquants": ", ".join(R.LIBELLES_CHAMPS.get(k, k) for k in f.get("champs_manquants", [])) or "–",
            "statut": {"fichier": "Fichier", "HLR": "HLR", "aucune": "Non disponible",
                       "mixte": "Mixte"}.get(f.get("source_statut"), f.get("source_statut", "")),
        })
    return sortie


def statuts(res: dict) -> list[dict]:
    return [{"fichier": s["fichier"], "valeur": s["valeur"],
             "categorie": R.LIBELLES_STATUT.get(s["categorie"], s["categorie"]), "n": fn(s["n"])}
            for s in res.get("statuts_bruts", [])]


def notes_methode(res: dict) -> list[str]:
    p = res.get("parametres", {})
    mode = {"fichiers": "fichiers « majeurs » et « mineurs » transmis par l'opérateur",
            "bdi": "BDI ventilée selon la date de naissance"}.get(
        res.get("synthese", {}).get("mode_physiques"), "fichiers transmis")
    mois_ref = res.get("periode", {}).get("mois_reference") or res.get("periode", {}).get("libelle", "")
    perim = {"hlr": "numéros présents au HLR (les lignes absentes du HLR sont dénombrées dans les contrôles)",
             "tous": "toutes les lignes des fichiers transmis"}.get(p.get("perimetre"), "toutes les lignes")
    classes = p.get("classement_types") or {}
    lignes = [
        f"Mois de référence : {mois_ref} (mois de la base). Âges, expirations et échéances sont calculés à l'année "
        f"et au mois près par rapport à ce mois, et non à la date de l'analyse.",
        f"Périmètre : {perim}.",
    ]
    if classes:
        lignes.append("Types de pièce comptés en personnes morales ou exclus : "
                      + ", ".join(f"{t} ({ {'FLOTTE': 'flotte', 'M2M': 'M2M', 'IGNORE': 'exclu'}.get(c, c) })"
                                  for t, c in classes.items()) + ".")
    return lignes + [
        f"Personnes physiques : {mode}.",
        "Les résultats sont ventilés selon le statut déclaré dans chaque fichier ; "
        "à défaut de colonne de statut, le statut du HLR est retenu.",
        "Valeurs considérées comme non renseignées : cellule vide, « - », « 0 », « N/A », « NULL », « XXX » et équivalents.",
        f"Plus de {p.get('max_modules', 3)} modules : nombre de numéros rattachés à un même numéro de pièce "
        f"utilisé plus de {p.get('max_modules', 3)} fois.",
        f"Pièce expirée depuis au moins {p.get('delai_expiration_mois', 6)} mois : mois d'expiration "
        f"{p.get('mois_limite_expiration') or _date_fr(p.get('date_limite_expiration'))} ou antérieur.",
    ]


def _date_fr(iso):
    from datetime import date
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except Exception:
        return iso or ""


def signaux(res: dict) -> list[dict]:
    sortie = []
    for x in res.get("signaux", []):
        detail = [(a, fn(b) if b is not None else None) for a, b in x.get("detail", [])]
        sortie.append({**x, "lignes_txt": fn(x["lignes"]),
                       "entites_txt": f"{fn(x['entites'])} {x['lib_entites']}" if x.get("entites") is not None else "",
                       "taux_txt": fp(x["lignes"], x["base"]) if x.get("base") else "–",
                       "detail_txt": detail})
    return sortie


def trace(res: dict) -> list[dict]:
    sortie = []
    for t in res.get("trace", []):
        etapes = []
        for lib, v in t["etapes"]:
            if v is None:
                continue
            txt = fn(abs(v))
            if lib.startswith("dont"):
                txt = fn(v)
            elif v < 0:
                txt = "− " + fn(-v)
            etapes.append((lib, txt))
        sortie.append({"titre": t["titre"], "etapes": etapes, "final_lib": t["final_lib"], "final": fn(t["final"])})
    return sortie


def extractions(res: dict) -> dict:
    return {e["code"]: e for e in res.get("extractions", [])}
