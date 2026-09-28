"""Parcours complet de l'application avec le client de test Flask."""
import os, sys, time, json
import tempfile
os.environ.setdefault("SGRNA_DATA", tempfile.mkdtemp(prefix="sgrna_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app

DOSSIERS = sys.argv[1:]
c = app.test_client()
r = c.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
assert r.status_code == 200 and "Nouvelle analyse" in r.get_data(as_text=True), "login"
ids = []
import io, zipfile
BLOC = 3 * 1024 * 1024
for d in DOSSIERS:
    # Envoi comme depuis le navigateur : un dossier sur deux sous forme d'archive .zip
    tid = c.post("/televersement/nouveau").get_json()["id"]
    fichiers = [f for f in sorted(os.listdir(d)) if not f.startswith(("_", "."))]
    if len(ids) % 2:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for f in fichiers:
                z.write(os.path.join(d, f), os.path.join(os.path.basename(d), f))
        envois = [(os.path.basename(d) + ".zip", buf.getvalue())]
    else:
        envois = [(os.path.basename(d) + "/" + f, open(os.path.join(d, f), "rb").read()) for f in fichiers]
    for nom, contenu in envois:
        for pos in range(0, max(len(contenu), 1), BLOC):
            r = c.post(f"/televersement/{tid}/bloc", data=contenu[pos:pos + BLOC],
                       headers={"X-Nom": nom, "X-Position": str(pos)})
            assert r.get_json()["ok"], r.get_json()
    ex = c.post(f"/televersement/{tid}/terminer").get_json()
    assert ex["ok"], ex
    assert ex["periode"]["mois"] and ex["periode"]["annee"], ex["periode"]
    f0 = ex["fichiers"][0]
    rr = c.post("/examiner/fichier", json={"chemin": f0["chemin"], "role": f0["role"], "colonnes": f0["correspondances"]}).get_json()
    assert rr["ok"], rr
    r = c.post("/lancer", json={"dossier": ex["dossier"], "operateur": ex["operateur"] or "AUTRE",
                                "operateur_libelle": ex["operateur_libelle"], "mois": ex["periode"]["mois"],
                                "annee": ex["periode"]["annee"], "source_physiques": "auto", "perimetre": "hlr",
                                "televersement": tid, "supprimer_apres": True,
                                "classement_types": {t["type"]: t["categorie"] for t in ex.get("types_piece", [])},
                                "fichiers": [{"chemin": f["chemin"], "role": f["role"], "colonnes": f["correspondances"]}
                                             for f in ex["fichiers"]]}).get_json()
    assert r["ok"], r
    job = r["url"].rsplit("/", 1)[1]
    assert c.get(r["url"]).status_code == 200
    while True:
        e = c.get(f"/suivi/{job}/etat").get_json()
        if e["etat"] != "en_cours": break
        time.sleep(0.5)
    assert e["etat"] == "termine", e
    aid = int(e["url"].rsplit("/", 1)[1]); ids.append(aid)
    for o in ("synthese", "etat", "signaux", "controles", "completude", "fichiers"):
        rr = c.get(f"/analyse/{aid}?onglet={o}"); assert rr.status_code == 200, (o, rr.status_code)
    for fmt in ("pdf", "docx", "xlsx"):
        rr = c.get(f"/analyse/{aid}/export/{fmt}"); assert rr.status_code == 200 and len(rr.data) > 5000, fmt
        open(os.path.join(os.environ["SGRNA_DATA"], f"export_{aid}.{fmt}"), "wb").write(rr.data)
    assert c.get(f"/analyse/{aid}/imprimer").status_code == 200
    rr = c.get(f"/analyse/{aid}/extractions.zip"); assert rr.status_code == 200 and len(rr.data) > 100
    page = c.get(f"/analyse/{aid}?onglet=signaux").get_data(as_text=True)
    import re as _re
    liens = _re.findall(r'href="(/analyse/\d+/extraction/[a-z_0-9]+)"', page)
    assert liens, "aucun lien d'extraction"
    assert c.get(liens[0]).status_code == 200
    assert not os.path.exists(ex["dossier"]), "téléversement non supprimé"
    print("analyse", aid, "ok")

# Validation, profil Direction, synthèse du mois et note
from app.database import ajouter_user
for aid in ids:
    assert c.post(f"/analyse/{aid}/valider", data={"action": "valider"}, follow_redirects=True).status_code == 200
r = c.post(f"/analyse/{ids[0]}/observations", data={"obs_mutilees": "x"}, follow_redirects=True)
assert "verrouill" in r.get_data(as_text=True) or "brouillon" in r.get_data(as_text=True)
c.post(f"/analyse/{ids[0]}/valider", data={"action": "brouillon"})
page = c.get("/mois").get_data(as_text=True)
assert "Chiffres clés comparés" in page, "page mois"
c.post("/mois", data={"annee": "2026", "mois": "2", "texte": "Convoquer l'opérateur.\nDemander la BDI avec statut."})
for fmt in ("pdf", "docx"):
    rr = c.get(f"/mois/note.{fmt}?annee=2026&mois=2"); assert rr.status_code == 200 and len(rr.data) > 3000, fmt
    open(os.path.join(os.environ["SGRNA_DATA"], f"note_fevrier.{fmt}"), "wb").write(rr.data)
    rr = c.get(f"/mois/annexe.{fmt}?annee=2026&mois=2"); assert rr.status_code == 200, fmt
ajouter_user("directeur", "direction123", "direction", "Le Directeur")
d = app.test_client()
d.post("/login", data={"username": "directeur", "password": "direction123"})
assert d.get("/").status_code == 302 and "/mois" in d.get("/").headers["Location"]
assert d.post("/lancer", json={}).status_code == 302, "direction ne doit pas lancer"
assert d.post(f"/analyse/{ids[0]}/observations", data={"obs_mutilees": "x"}).status_code == 302
page = d.get(f"/analyse/{ids[0]}").get_data(as_text=True)
assert "Valider l" in page and "Nouvelle analyse" not in page
assert d.post(f"/analyse/{ids[0]}/valider", data={"action": "valider"}, follow_redirects=True).status_code == 200
assert d.get("/mois?annee=2026&mois=2").status_code == 200

# Observations modifiées puis réexport
c.post(f"/analyse/{ids[0]}/valider", data={"action": "brouillon"})
r = c.post(f"/analyse/{ids[0]}/observations", data={"obs_mutilees": "Pas de CNI scannés"}, follow_redirects=True)
assert "Observations enregistrées" in r.get_data(as_text=True)
assert "Pas de CNI scann" in c.get(f"/analyse/{ids[0]}?onglet=etat").get_data(as_text=True)
# Historique, annexe groupée, évolution, utilisateurs
assert c.get("/historique").status_code == 200
for fmt in ("pdf", "docx", "xlsx", "imprimer"):
    rr = c.post("/historique/annexe", data={"ids": [str(i) for i in ids], "format": fmt, "contenu": "tableau",
                                            "numerotation": "continue", "ordre": "selection"})
    assert rr.status_code == 200, fmt
    if fmt != "imprimer":
        open(os.path.join(os.environ["SGRNA_DATA"], f"annexe_groupee.{fmt}"), "wb").write(rr.data)
assert c.get("/evolution").status_code == 200
assert c.get("/evolution?operateur=ORANGE").status_code == 200
assert c.get("/users").status_code == 200
assert c.get("/compte").status_code == 200
assert c.get("/analyse/9999").status_code == 404
print("TOUT OK", ids)
