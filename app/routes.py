"""
routes.py
─────────
Pages et points d'accès de l'application.
"""
from __future__ import annotations

import io
import os
import re
import unicodedata

from flask import (abort, flash, jsonify, redirect, render_template, request, send_file, session,
                   url_for)

import config
from app import app, taches
from app.database import (STATUTS_VALIDATION, analyse_reference, devalider_analyse, enregistrer_note,
                          lire_note, operateurs_du_mois, periodes_disponibles, role_requis, valider_analyse,
                          admin0_requis, ajouter_user, changer_mot_de_passe, get_all_users,
                          lire_analyse, lister_analyses, login_requis, maj_resultats, modifier_user,
                          supprimer_analyse, supprimer_user, valeurs_filtres, verifier_login)
from exports import modele as M
from moteur import referentiel as R
from moteur.detection import examiner_dossier, libelle_operateur
from moteur.format import n as fn, pct as fp

ROLES_LIBELLES = {"admin0": "Administrateur", "admin1": "Chargé d'analyse", "direction": "Direction"}


# ═════════════════════════════════════════════════════════════════════════════
# FILTRES DE GABARITS
# ═════════════════════════════════════════════════════════════════════════════

app.jinja_env.filters["n"] = fn


@app.context_processor
def _identite():
    """Logo et nom de l'application, disponibles dans tous les gabarits."""
    chemin = config.chemin_logo()
    url = None
    if chemin:
        url = url_for("logo") + f"?v={int(os.path.getmtime(chemin))}"
    return {"logo_url": url, "NOM_APPLI": config.NOM_APPLICATION, "NOM_COMPLET": config.NOM_COMPLET,
            "ROLES_LIBELLES": ROLES_LIBELLES, "VERSION": config.VERSION}


@app.route("/logo")
def logo():
    """Logo de l'ART, où qu'il soit déposé (dossier des données ou app/static)."""
    chemin = config.chemin_logo()
    if not chemin:
        abort(404)
    return send_file(chemin, max_age=86400)


@app.route("/sante")
def sante():
    """Contrôle de fonctionnement (utilisé par Docker)."""
    return {"etat": "ok", "version": config.VERSION}
app.jinja_env.globals.update(pct=fp, R=R, config=config, MOIS=R.MOIS_NOMS)


@app.template_filter("date_fr")
def date_fr(iso):
    if not iso:
        return ""
    s = str(iso)
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?", s)
    if not m:
        return s
    a, mo, j, h, mi = m.groups()
    return f"{j}/{mo}/{a}" + (f" {h}:{mi}" if h else "")


def _nom_fichier(texte):
    t = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_")


# ═════════════════════════════════════════════════════════════════════════════
# AUTHENTIFICATION
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("index"))
    if request.method == "POST":
        user = verifier_login(request.form.get("username", "").strip(), request.form.get("password", ""))
        if user:
            session.update(user_id=user["id"], username=user["username"],
                           nom=user["nom"] or user["username"], role=user["role"])
            return redirect(request.args.get("suivant") or url_for("index"))
        flash("Identifiant ou mot de passe incorrect.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Vous êtes déconnecté.", "success")
    return redirect(url_for("login"))


@app.route("/compte", methods=["GET", "POST"])
@login_requis
def compte():
    if request.method == "POST":
        nouveau = request.form.get("nouveau", "")
        if len(nouveau) < 6:
            flash("Le nouveau mot de passe doit comporter au moins 6 caractères.", "danger")
        elif nouveau != request.form.get("confirmation", ""):
            flash("La confirmation ne correspond pas.", "danger")
        elif changer_mot_de_passe(session["user_id"], request.form.get("ancien", ""), nouveau):
            flash("Mot de passe modifié.", "success")
            return redirect(url_for("index"))
        else:
            flash("Mot de passe actuel incorrect.", "danger")
    return render_template("compte.html")


# ═════════════════════════════════════════════════════════════════════════════
# NOUVELLE ANALYSE
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/")
@login_requis
def index():
    if session.get("role") == "direction":
        return redirect(url_for("mois"))
    return render_template("index.html", recentes=lister_analyses(limite=6),
                           tache=taches.en_cours(), roles=R.ROLES, operateurs=R.LIBELLES_OPERATEURS,
                           dossier_defaut=config.DOSSIER_PAR_DEFAUT)


@app.route("/examiner", methods=["POST"])
@role_requis("admin0", "admin1")
def examiner():
    chemin = (request.get_json(silent=True) or {}).get("chemin", "") or request.form.get("chemin", "")
    if not chemin.strip():
        return jsonify({"ok": False, "erreur": "Veuillez indiquer le chemin du dossier."})
    try:
        return jsonify(examiner_dossier(chemin))
    except Exception as e:
        return jsonify({"ok": False, "erreur": f"Examen impossible : {e}"})


@app.route("/examiner/fichier", methods=["POST"])
@role_requis("admin0", "admin1")
def examiner_fichier():
    """Réexamen d'un fichier après changement de rôle ou de colonnes."""
    from moteur.detection import analyser_fichier
    d = request.get_json(silent=True) or {}
    try:
        fd = analyser_fichier(d["chemin"], d.get("role"), d.get("colonnes"), apercu=True)
        return jsonify({"ok": True, "fichier": fd.to_dict()})
    except Exception as e:
        return jsonify({"ok": False, "erreur": str(e)})


# ── Téléversement (fichiers, dossier ou archive .zip) ─────────────────────────

@app.route("/televersement/nouveau", methods=["POST"])
@role_requis("admin0", "admin1")
def televersement_nouveau():
    from app import televersement as T
    return jsonify({"ok": True, "id": T.nouveau()})


@app.route("/televersement/<tid>/bloc", methods=["POST"])
@role_requis("admin0", "admin1")
def televersement_bloc(tid):
    from urllib.parse import unquote
    from app import televersement as T
    try:
        taille = T.ecrire_bloc(tid, unquote(request.headers.get("X-Nom", "")),
                               int(request.headers.get("X-Position", "0")), request.stream)
        return jsonify({"ok": True, "taille": taille})
    except Exception as e:
        return jsonify({"ok": False, "erreur": str(e)}), 400


@app.route("/televersement/<tid>/terminer", methods=["POST"])
@role_requis("admin0", "admin1")
def televersement_terminer(tid):
    from app import televersement as T
    try:
        dossier = T.finaliser(tid)
        res = examiner_dossier(dossier)
        res["televersement"] = tid
        return jsonify(res)
    except Exception as e:
        return jsonify({"ok": False, "erreur": f"Traitement des fichiers reçus impossible : {e}"})


@app.route("/lancer", methods=["POST"])
@role_requis("admin0", "admin1")
def lancer():
    import uuid
    d = request.get_json(silent=True) or {}
    if taches.en_cours():
        return jsonify({"ok": False, "erreur": "Une analyse est déjà en cours. Veuillez patienter."})
    fichiers = [f for f in d.get("fichiers", []) if f.get("role") and f["role"] != "IGNORE"]
    if not fichiers:
        return jsonify({"ok": False, "erreur": "Aucun fichier retenu pour l'analyse."})
    code = (d.get("operateur") or "").strip().upper() or None
    libelle = (d.get("operateur_libelle") or "").strip() or libelle_operateur(code)
    if code == "AUTRE":
        code = _nom_fichier(libelle).upper() or "AUTRE"
    try:
        annee = int(d.get("annee")) if d.get("annee") else None
        mois = int(d.get("mois")) if d.get("mois") else None
    except ValueError:
        return jsonify({"ok": False, "erreur": "Période invalide."})
    if not (annee and mois):
        return jsonify({"ok": False, "erreur": "Le mois et l'année de la base sont obligatoires : ils servent "
                                               "de référence pour les âges et les expirations."})
    extraction_id = uuid.uuid4().hex[:16]
    parametres = {"dossier": d.get("dossier"), "fichiers": fichiers, "operateur": code,
                  "operateur_libelle": libelle, "annee": annee, "mois": mois,
                  "source_physiques": d.get("source_physiques", "auto"),
                  "perimetre": d.get("perimetre", "hlr"),
                  "classement_types": d.get("classement_types") or {},
                  "extractions_id": extraction_id,
                  "dossier_extractions": os.path.join(config.DOSSIER_DONNEES, "extractions", extraction_id),
                  "supprimer_apres": bool(d.get("supprimer_apres")) and bool(d.get("televersement"))}
    job = taches.lancer(parametres, session.get("nom") or session.get("username"))
    return jsonify({"ok": True, "url": url_for("suivi", job_id=job)})


@app.route("/suivi/<job_id>")
@login_requis
def suivi(job_id):
    t = taches.lire(job_id)
    if not t:
        flash("Cette analyse n'est plus suivie. Consultez l'historique.", "warning")
        return redirect(url_for("historique"))
    return render_template("suivi.html", tache=t)


@app.route("/suivi/<job_id>/etat")
@login_requis
def suivi_etat(job_id):
    t = taches.lire(job_id)
    if not t:
        return jsonify({"etat": "inconnu"})
    depuis = request.args.get("depuis", 0, type=int)
    return jsonify({"etat": t["etat"], "pct": t["pct"], "etape": t["etape"], "logs": t["logs"][depuis:],
                    "total_logs": len(t["logs"]), "erreur": t["erreur"],
                    "url": url_for("analyse", analyse_id=t["analyse_id"]) if t["analyse_id"] else None})


# ═════════════════════════════════════════════════════════════════════════════
# CONSULTATION D'UNE ANALYSE
# ═════════════════════════════════════════════════════════════════════════════

def _charger(analyse_id):
    row, res = lire_analyse(analyse_id)
    if not res:
        abort(404)
    return row, res


def _points_attention(res, limite=8):
    pts = [{"libelle": c["libelle"], "famille": c["famille"], "valeur": c["valeur"], "base": c.get("base"),
            "taux": c.get("taux") or 0}
           for c in res.get("controles", []) if c.get("niveau") == "alerte" and c.get("valeur")]
    pts += [{"libelle": x["libelle"], "famille": "Signal d'alerte – " + x["famille"], "valeur": x["lignes"],
             "base": x.get("base"), "taux": (x.get("taux") or 0) + 100}      # signaux affichés en premier
            for x in res.get("signaux", []) if x.get("niveau") == "alerte" and x.get("lignes")]
    pts.sort(key=lambda c: -c["taux"])
    return pts[:limite]


@app.route("/analyse/<int:analyse_id>")
@login_requis
def analyse(analyse_id):
    row, res = _charger(analyse_id)
    ext = M.extractions(res)

    def lien_extraction(code):
        return url_for("extraction", analyse_id=analyse_id, code=code) if code in ext else None
    return render_template("analyse.html", row=row, res=res, lien_extraction=lien_extraction,
                           tableau=M.tableau_etat(res), controles=M.controles(res),
                           completude=M.completude(res), fichiers=M.fichiers(res), statuts=M.statuts(res),
                           notes=M.notes_methode(res), points=_points_attention(res),
                           signaux=M.signaux(res), trace=M.trace(res), ext=M.extractions(res),
                           titre=M.titre_section(res), onglet=request.args.get("onglet", "synthese"),
                           statut=row["statut_validation"] or "brouillon", statuts_validation=STATUTS_VALIDATION)


@app.route("/analyse/<int:analyse_id>/observations", methods=["POST"])
@role_requis("admin0", "admin1")
def observations(analyse_id):
    row, res = _charger(analyse_id)
    if (row["statut_validation"] or "brouillon") == "validee":
        flash("Analyse validée : repasser en brouillon pour modifier les observations.", "warning")
        return redirect(url_for("analyse", analyse_id=analyse_id, onglet="etat"))
    for e in res.get("etat_des_lieux", []):
        cle = f"obs_{e['code']}"
        if cle in request.form:
            e["observation"] = request.form[cle].strip()
        if request.form.get("reinitialiser") == "1":
            e["observation"] = e.get("observation_auto", "")
    maj_resultats(analyse_id, res, session.get("nom"))
    flash("Observations enregistrées." if request.form.get("reinitialiser") != "1"
          else "Observations automatiques rétablies.", "success")
    return redirect(url_for("analyse", analyse_id=analyse_id, onglet="etat"))


@app.route("/analyse/<int:analyse_id>/valider", methods=["POST"])
@role_requis("admin0", "direction")
def valider(analyse_id):
    _charger(analyse_id)
    if request.form.get("action") == "brouillon":
        devalider_analyse(analyse_id)
        flash("Analyse repassée en brouillon : les observations sont de nouveau modifiables.", "success")
    else:
        valider_analyse(analyse_id, session.get("nom") or session.get("username"))
        flash("Analyse validée : elle fait foi pour cet opérateur et ce mois.", "success")
    return redirect(url_for("analyse", analyse_id=analyse_id))


def _dossier_extractions(res):
    eid = res.get("extractions_id")
    if not eid or not re.fullmatch(r"[0-9a-f]{16}", eid):
        return None
    return os.path.join(config.DOSSIER_DONNEES, "extractions", eid)


@app.route("/analyse/<int:analyse_id>/extraction/<code>")
@login_requis
def extraction(analyse_id, code):
    _, res = _charger(analyse_id)
    d = _dossier_extractions(res)
    ext = next((e for e in res.get("extractions", []) if e["code"] == code), None)
    if not d or not ext:
        abort(404)
    chemin = os.path.join(d, f"{code}.csv")
    if not os.path.exists(chemin):
        flash("Fichier d'extraction introuvable (supprimé du poste).", "warning")
        return redirect(url_for("analyse", analyse_id=analyse_id, onglet="signaux"))
    nom = _nom_fichier(f"{res.get('operateur') or ''}_{res['periode']['libelle']}_{code}") + ".csv"
    return send_file(chemin, as_attachment=True, download_name=nom, mimetype="text/csv")


@app.route("/analyse/<int:analyse_id>/extractions.zip")
@login_requis
def extractions_zip(analyse_id):
    import zipfile
    _, res = _charger(analyse_id)
    d = _dossier_extractions(res)
    if not d or not os.path.isdir(d):
        abort(404)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for e in res.get("extractions", []):
            chemin = os.path.join(d, f"{e['code']}.csv")
            if os.path.exists(chemin):
                z.write(chemin, f"{e['code']}.csv")
    buf.seek(0)
    nom = _nom_fichier(f"Extractions_{res.get('operateur') or ''}_{res['periode']['libelle']}")
    return send_file(buf, as_attachment=True, download_name=f"{nom}.zip", mimetype="application/zip")


@app.route("/analyse/<int:analyse_id>/supprimer", methods=["POST"])
@admin0_requis
def supprimer(analyse_id):
    import shutil
    _, res = lire_analyse(analyse_id)
    d = _dossier_extractions(res or {})
    if d:
        shutil.rmtree(d, ignore_errors=True)
    supprimer_analyse(analyse_id)
    flash("Analyse supprimée de l'historique.", "success")
    return redirect(url_for("historique"))


@app.route("/analyse/<int:analyse_id>/imprimer")
@login_requis
def imprimer(analyse_id):
    _, res = _charger(analyse_id)
    contenu = request.args.get("contenu", "complet")
    return render_template("impression.html", sections=[{"res": res, "tableau": M.tableau_etat(res),
                                                          "titre": M.titre_section(res, 0),
                                                          "controles": M.controles(res),
                                                          "completude": M.completude(res)}],
                           contenu=contenu, notes=M.notes_methode(res),
                           sous_titre=f"{res.get('operateur_libelle', '')} – mois de {res['periode']['libelle']}")


def _envoyer(donnees: bytes, nom: str, fmt: str):
    types = {"pdf": "application/pdf",
             "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    return send_file(io.BytesIO(donnees), as_attachment=True, download_name=f"{nom}.{fmt}", mimetype=types[fmt])


@app.route("/analyse/<int:analyse_id>/export/<fmt>")
@login_requis
def exporter(analyse_id, fmt):
    _, res = _charger(analyse_id)
    contenu = request.args.get("contenu", "complet")
    nom = _nom_fichier(f"Annexe_BDI_{res.get('operateur') or 'operateur'}_{res['periode']['libelle']}")
    if fmt == "pdf":
        from exports.pdf import generer_pdf
        return _envoyer(generer_pdf(res, contenu), nom, "pdf")
    if fmt == "docx":
        from exports.word import generer_docx
        return _envoyer(generer_docx(res, contenu), nom, "docx")
    if fmt == "xlsx":
        from exports.excel import generer_xlsx
        return _envoyer(generer_xlsx(res), nom, "xlsx")
    abort(404)


# ═════════════════════════════════════════════════════════════════════════════
# HISTORIQUE, ANNEXE GROUPÉE, ÉVOLUTION
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/historique")
@login_requis
def historique():
    op, annee = request.args.get("operateur") or None, request.args.get("annee") or None
    statut = request.args.get("statut") or None
    ops, annees = valeurs_filtres()
    return render_template("historique.html", analyses=lister_analyses(op, annee, statut=statut), operateurs=ops,
                           annees=annees, filtre_op=op, filtre_annee=annee, filtre_statut=statut,
                           statuts=STATUTS_VALIDATION)


def _resultats_selection(ids):
    res = []
    for i in ids:
        _, r = lire_analyse(int(i))
        if r:
            res.append(r)
    return res


@app.route("/historique/annexe", methods=["POST"])
@login_requis
def annexe_groupee():
    ids = request.form.getlist("ids")
    if not ids:
        flash("Sélectionnez au moins une analyse.", "warning")
        return redirect(url_for("historique"))
    resultats = _resultats_selection(ids)
    ordre = request.form.get("ordre", "selection")
    if ordre == "periode":
        resultats.sort(key=lambda r: (r["periode"].get("annee") or 0, r["periode"].get("mois") or 0,
                                      r.get("operateur_libelle", "")))
    fmt = request.form.get("format", "pdf")
    contenu = request.form.get("contenu", "tableau")
    continue_ = request.form.get("numerotation", "continue") == "continue"
    nom = "Annexe_BDI_" + "_".join(_nom_fichier(f"{r.get('operateur') or ''}_{r['periode']['libelle']}")
                                   for r in resultats)[:80]
    if fmt == "pdf":
        from exports.pdf import generer_pdf_groupe
        return _envoyer(generer_pdf_groupe(resultats, contenu, continue_), nom, "pdf")
    if fmt == "docx":
        from exports.word import generer_docx_groupe
        return _envoyer(generer_docx_groupe(resultats, contenu, continue_), nom, "docx")
    if fmt == "xlsx":
        from exports.excel import generer_xlsx_groupe
        return _envoyer(generer_xlsx_groupe(resultats, continue_), nom, "xlsx")
    if fmt == "imprimer":
        sections, num = [], 1
        for i, r in enumerate(resultats):
            tab = M.tableau_etat(r, num if continue_ else 1)
            num = tab["numero_suivant"]
            sections.append({"res": r, "tableau": tab, "titre": M.titre_section(r, i),
                             "controles": M.controles(r), "completude": M.completude(r)})
        return render_template("impression.html", sections=sections, contenu=contenu,
                               notes=M.notes_methode(resultats[0]),
                               sous_titre=" – ".join(f"{r.get('operateur_libelle', '')} ({r['periode']['libelle']})"
                                                     for r in resultats))
    abort(400)


INDICATEURS_EVOLUTION = [
    ("numeros", "Numéros d'abonnés", "total"),
    ("numeros", "dont actifs", "ACTIF"),
    ("flotte", "Personnes morales (flotte)", "total"),
    ("m2m", "Personnes morales (M2M)", "total"),
    ("total_majeurs", "Personnes physiques majeures", "total"),
    ("total_mineurs", "Personnes physiques mineures", "total"),
    ("mal_majeurs", "Adultes mal identifiés", "total"),
    ("mal_mineurs", "Mineurs mal identifiés", "total"),
    ("mal_flotte", "Flotte mal identifiée", "total"),
    ("mal_m2m", "M2M mal identifiés", "total"),
    ("plus3_majeurs", "Majeurs : numéros liés à > 3 SIM", "total"),
    ("expirees", "Pièces expirées depuis ≥ 6 mois", "total"),
    ("ctrl:hlr_non_identifies", "Numéros du HLR sans identification", "valeur"),
    ("sig:mineurs_non_declares", "Mineurs non déclarés", "lignes"),
    ("sig:souscrit_mineur", "Lignes souscrites par des mineurs", "lignes"),
    ("sig:pieces_partagees", "Pièces partagées entre personnes différentes", "lignes"),
    ("sig:meme_personne_plusieurs_pieces", "Même personne sous plusieurs pièces", "lignes"),
    ("sig:plus3_par_identite", "Personnes à plus de 3 numéros (identité)", "lignes"),
    ("sig:series_consecutives", "Séries de pièces consécutives", "lignes"),
    ("sig:expiree_a_souscription", "Pièce expirée à la souscription", "lignes"),
]


def _valeur_indicateur(res, code, champ):
    if code.startswith("sig:"):
        x = next((x for x in res.get("signaux", []) if x["code"] == code[4:]), None)
        return x["lignes"] if x else None
    if code.startswith("ctrl:"):
        c = next((c for c in res.get("controles", []) if c["code"] == code[5:]), None)
        return c["valeur"] if c else None
    e = next((e for e in res.get("etat_des_lieux", []) if e["code"] == code), None)
    if not e or e["type"] == "non_evaluable" or not e["lignes"]:
        return None
    if champ == "total":
        return sum(l["total"] or 0 for l in e["lignes"])
    return sum(l["valeurs"].get(champ, 0) for l in e["lignes"])


@app.route("/evolution")
@login_requis
def evolution():
    ops, _ = valeurs_filtres()
    op = request.args.get("operateur") or (ops[0]["operateur"] if ops else None)
    periodes = []
    if op:
        vues = {}
        for row in lister_analyses(op):
            if row["annee"] and row["mois"]:
                vues[(row["annee"], row["mois"])] = None
        for cle in sorted(vues):
            ref = analyse_reference(op, *cle)
            _, res = lire_analyse(ref["id"])
            periodes.append({"id": ref["id"], "libelle": res["periode"]["libelle"], "res": res,
                             "validee": ref["statut_validation"] == "validee"})
    lignes = []
    for code, libelle, champ in INDICATEURS_EVOLUTION:
        vals = [_valeur_indicateur(p["res"], code, champ) for p in periodes]
        if all(v is None for v in vals):
            continue
        cellules = []
        for i, v in enumerate(vals):
            prec = vals[i - 1] if i else None
            var = (v - prec) if (v is not None and prec is not None) else None
            cellules.append({"v": v, "var": var, "var_pct": fp(var, prec) if var is not None and prec else ""})
        lignes.append({"libelle": libelle, "cellules": cellules, "sous": libelle.startswith("dont"),
                       "anomalie": code.startswith(("mal_", "plus3", "expirees", "ctrl:", "sig:"))})
    return render_template("evolution.html", operateurs=ops, op=op, periodes=periodes, lignes=lignes)


# ═════════════════════════════════════════════════════════════════════════════
# SYNTHÈSE DU MOIS (comparatif des opérateurs, note d'une page)
# ═════════════════════════════════════════════════════════════════════════════

def _reference(op, annee, mois):
    r = analyse_reference(op, annee, mois)
    if not r:
        return None
    _, res = lire_analyse(r["id"])
    return (r["id"], r["statut_validation"] == "validee", res) if res else None


def _periode_demandee():
    periodes = periodes_disponibles()
    try:
        annee, mois = int(request.values.get("annee")), int(request.values.get("mois"))
    except (TypeError, ValueError):
        if not periodes:
            return None, None, periodes
        annee, mois = periodes[0]["annee"], periodes[0]["mois"]
    return annee, mois, periodes


def _synthese_mois(annee, mois):
    from exports.synthese import construire
    note = lire_note(annee, mois)
    return construire(annee, mois, _reference, operateurs_du_mois(annee, mois), note["texte"] if note else ""), note


@app.route("/mois", methods=["GET", "POST"])
@login_requis
def mois():
    annee, mois_, periodes = _periode_demandee()
    if request.method == "POST":
        if session.get("role") not in ("admin0", "admin1"):
            flash("Cette action n'est pas ouverte à votre profil.", "danger")
        else:
            enregistrer_note(annee, mois_, request.form.get("texte", "").strip(),
                             session.get("nom") or session.get("username"))
            flash("Observations et actions proposées enregistrées.", "success")
        return redirect(url_for("mois", annee=annee, mois=mois_))
    if annee is None:
        return render_template("mois.html", s=None, periodes=[], note=None)
    s, note = _synthese_mois(annee, mois_)
    return render_template("mois.html", s=s, periodes=periodes, note=note, annee=annee, mois=mois_)


@app.route("/mois/note.<fmt>")
@login_requis
def mois_note(fmt):
    annee, mois_, _ = _periode_demandee()
    if annee is None:
        abort(404)
    s, _ = _synthese_mois(annee, mois_)
    if not s["colonnes"]:
        abort(404)
    nom = _nom_fichier(f"Note_synthese_BDI_{s['libelle']}")
    from exports.note import generer_note_docx, generer_note_pdf
    if fmt == "pdf":
        return _envoyer(generer_note_pdf(s), nom, "pdf")
    if fmt == "docx":
        return _envoyer(generer_note_docx(s), nom, "docx")
    abort(404)


@app.route("/mois/annexe.<fmt>")
@login_requis
def mois_annexe(fmt):
    annee, mois_, _ = _periode_demandee()
    if annee is None:
        abort(404)
    s, _ = _synthese_mois(annee, mois_)
    resultats = [c["res"] for c in s["colonnes"]]
    if not resultats:
        abort(404)
    contenu = request.args.get("contenu", "tableau")
    nom = _nom_fichier(f"Annexe_BDI_{s['libelle']}")
    if fmt == "pdf":
        from exports.pdf import generer_pdf_groupe
        return _envoyer(generer_pdf_groupe(resultats, contenu), nom, "pdf")
    if fmt == "docx":
        from exports.word import generer_docx_groupe
        return _envoyer(generer_docx_groupe(resultats, contenu), nom, "docx")
    abort(404)


# ═════════════════════════════════════════════════════════════════════════════
# UTILISATEURS
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/users", methods=["GET", "POST"])
@admin0_requis
def gerer_users():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        mdp = request.form.get("password", "")
        if not u or len(mdp) < 6:
            flash("Identifiant requis et mot de passe d'au moins 6 caractères.", "danger")
        else:
            ok = ajouter_user(u, mdp, request.form.get("role", "admin1"), request.form.get("nom", "").strip())
            flash(f"Utilisateur « {u} » créé." if ok else f"L'identifiant « {u} » est déjà utilisé.",
                  "success" if ok else "danger")
    return render_template("users.html", users=get_all_users(), session_user_id=session.get("user_id"))


@app.route("/users/modifier/<int:id>", methods=["POST"])
@admin0_requis
def modifier_user_route(id):
    modifier_user(id, request.form.get("role", "admin1"), request.form.get("nom", "").strip(),
                  request.form.get("password") or None)
    flash("Utilisateur modifié.", "success")
    return redirect(url_for("gerer_users"))


@app.route("/users/supprimer/<int:id>", methods=["POST"])
@admin0_requis
def supprimer_user_route(id):
    if id == session.get("user_id"):
        flash("Vous ne pouvez pas supprimer votre propre compte.", "danger")
    else:
        supprimer_user(id)
        flash("Utilisateur supprimé.", "success")
    return redirect(url_for("gerer_users"))


@app.errorhandler(404)
def introuvable(e):
    return render_template("erreur.html", message="Page ou analyse introuvable."), 404
