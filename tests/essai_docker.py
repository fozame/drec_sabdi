"""
Essai du conteneur en service (HTTP réel) : connexion, téléversement d'une archive,
analyse d'un dossier déposé dans /depots, exports.
    python tests/essai_docker.py http://127.0.0.1:5600 <dossier_a_televerser> <nom_dossier_dans_depots> [mot_de_passe]
"""
import io, os, sys, time, zipfile
import requests

URL, DOSSIER, DEPOT = sys.argv[1:4]
MDP = sys.argv[4] if len(sys.argv) > 4 else "admin123"
s = requests.Session()
r = s.post(f"{URL}/login", data={"username": "admin", "password": MDP})
assert "Nouvelle analyse" in r.text, "connexion"


def lancer(ex, tid=None):
    corps = {"dossier": ex["dossier"], "operateur": ex["operateur"] or "AUTRE",
             "operateur_libelle": ex["operateur_libelle"], "mois": ex["periode"]["mois"],
             "annee": ex["periode"]["annee"], "source_physiques": "auto", "perimetre": "hlr",
             "classement_types": {t["type"]: t["categorie"] for t in ex.get("types_piece", [])},
             "fichiers": [{"chemin": f["chemin"], "role": f["role"], "colonnes": f["correspondances"]}
                          for f in ex["fichiers"]]}
    if tid:
        corps.update(televersement=tid, supprimer_apres=True)
    r = s.post(f"{URL}/lancer", json=corps).json()
    assert r["ok"], r
    job = r["url"].rsplit("/", 1)[1]
    while True:
        e = s.get(f"{URL}/suivi/{job}/etat").json()
        if e["etat"] != "en_cours":
            break
        time.sleep(1)
    assert e["etat"] == "termine", e
    aid = int(e["url"].rsplit("/", 1)[1])
    for fmt in ("pdf", "docx", "xlsx"):
        rr = s.get(f"{URL}/analyse/{aid}/export/{fmt}")
        assert rr.status_code == 200 and len(rr.content) > 5000, fmt
    assert s.get(f"{URL}/analyse/{aid}/extractions.zip").status_code == 200
    return aid


# 1. Archive .zip téléversée par blocs
tid = s.post(f"{URL}/televersement/nouveau").json()["id"]
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(os.listdir(DOSSIER)):
        if not f.startswith(("_", ".")):
            z.write(os.path.join(DOSSIER, f), os.path.join(os.path.basename(DOSSIER), f))
data, BLOC = buf.getvalue(), 3 << 20
for pos in range(0, len(data), BLOC):
    r = s.post(f"{URL}/televersement/{tid}/bloc", data=data[pos:pos + BLOC],
               headers={"X-Nom": os.path.basename(DOSSIER) + ".zip", "X-Position": str(pos)}).json()
    assert r["ok"], r
ex = s.post(f"{URL}/televersement/{tid}/terminer").json()
while ex.get("en_cours"):
    time.sleep(1)
    ex = s.get(f"{URL}/televersement/{tid}/etat").json()
assert ex["ok"], ex
a1 = lancer(ex, tid)
print("téléversement zip : analyse", a1, ex["operateur_libelle"], ex["periode"])

# 2. Dossier déposé sur le serveur
ex = s.post(f"{URL}/examiner", json={"chemin": f"/depots/{DEPOT}"}).json()
assert ex["ok"], ex
a2 = lancer(ex)
print("dossier /depots : analyse", a2, ex["operateur_libelle"], ex["periode"])
assert s.get(f"{URL}/mois").status_code == 200
print("ESSAI DOCKER OK", a1, a2)
