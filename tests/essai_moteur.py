"""Analyse un dossier en ligne de commande et affiche le tableau :  python tests/essai_moteur.py /chemin/dossier"""
import json, sys, time
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from moteur.detection import examiner_dossier
from moteur.analyse import lancer_analyse
from moteur.format import n
d = sys.argv[1]
ex = examiner_dossier(d)
t=time.time()
res = lancer_analyse({"dossier": d, "operateur": ex["operateur"], "annee": ex["periode"]["annee"], "mois": ex["periode"]["mois"],
                      "fichiers": [{"chemin": f["chemin"], "role": f["role"]} for f in ex["fichiers"]],
                      "dossier_extractions": os.environ.get("EXTRACTIONS")}, log=lambda m: None)
print("durée", round(time.time()-t,1), "s")
cols = res["colonnes_statut"]
print("colonnes:", cols)
for e in res["etat_des_lieux"]:
    for i,l in enumerate(e["lignes"]):
        print(f"{e['n'] if i==0 else '':>3} {(e['statistique'] if i==0 else '')[:60]:60s} {l['specification'][:22]:22s}", " ".join(f"{n(l['valeurs'].get(c,0)):>10}" for c in cols), f"{n(l['total']):>11}")
    if e["observation"]: print("      obs:", e["observation"].replace("\n"," | "))
print("\nCONTROLES")
for c in res["controles"]:
    print(f"  [{c['famille']}] {c['libelle']}: {n(c['valeur'])} / {n(c['base']) if c['base'] else '-'} {c['taux']} {c['detail']}")
print("\nSIGNAUX")
for x in res.get("signaux", []):
    print(f"  [{x['famille']}] {x['libelle']}: {n(x['lignes'])} lignes, {x['entites']} {x['lib_entites'] or ''} {x['detail'][:6]}")
print("\nTRACE")
for t in res.get("trace", []):
    print("  ", t["titre"], [(a, b) for a, b in t["etapes"]], "=>", t["final"])
print("EXTRACTIONS", [(e["code"], e["lignes"]) for e in res.get("extractions", [])])
print("\nALERTES", res["alertes"])
print("\nSYNTHESE", json.dumps(res["synthese"]["kpis"], ensure_ascii=False, indent=0)[:1500])
