"""
excel.py
────────
Classeur Excel mis en forme : une feuille « État des lieux » au format de
référence (valeurs numériques exploitables), puis Contrôles, Complétude,
Fichiers et Statuts. Mise en page prête à l'impression (A4 paysage,
ajusté en largeur, lignes d'en-tête répétées).
"""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import config
from moteur import referentiel as R
from . import modele as M

POLICE = "Arial"
F_ENTETE = PatternFill("solid", fgColor="DCE3EC")
F_SOUS_TOTAL = PatternFill("solid", fgColor="EEF1F5")
FIN = Side(style="thin", color="9AA3AF")
EPAIS = Side(style="medium", color="1B2433")
BORD = Border(left=FIN, right=FIN, top=FIN, bottom=FIN)
FMT_N = '#,##0;-#,##0;0'


def _f(bold=False, taille=9, italique=False, couleur="1B2433"):
    return Font(name=POLICE, size=taille, bold=bold, italic=italique, color=couleur)


def _mise_en_page(ws, lignes_titre=None):
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = ws.page_margins.right = 0.5
    ws.page_margins.top, ws.page_margins.bottom = 0.7, 0.6
    ws.print_options.horizontalCentered = True
    ws.oddHeader.left.text = config.ORGANISME[0]
    ws.oddHeader.left.size = 8
    ws.oddFooter.right.text = "Page &P / &N"
    ws.oddFooter.right.size = 8
    ws.oddFooter.left.text = f"{config.NOM_APPLICATION} – {config.NOM_COMPLET}"
    ws.oddFooter.left.size = 8
    if lignes_titre:
        ws.print_title_rows = lignes_titre


def _titre(ws, ligne, texte, taille=12, nb_col=8):
    ws.cell(ligne, 1, texte).font = _f(True, taille, couleur="1F3A5F")
    ws.merge_cells(start_row=ligne, start_column=1, end_row=ligne, end_column=nb_col)


def _nombre(v):
    if v is None:
        return "/"
    return int(v)


def feuille_etat(ws, res, ligne=1, numero_depart=1, indice=0):
    """Écrit le tableau d'une analyse à partir de `ligne`. Retourne (ligne suivante, numéro suivant)."""
    cols = M.colonnes(res)
    k = len(cols)
    nb = 5 + k
    _titre(ws, ligne, M.titre_section(res, indice), 11, nb)
    ligne += 2
    h1, h2 = ligne, ligne + 1
    entetes = [(1, "N°"), (2, "Statistiques"), (3, "Spécifications"), (nb, "Observations")]
    for c, t in entetes:
        ws.cell(h1, c, t)
        ws.merge_cells(start_row=h1, start_column=c, end_row=h2, end_column=c)
    ws.cell(h1, 4, "Résultats")
    ws.merge_cells(start_row=h1, start_column=4, end_row=h1, end_column=4 + k)
    for j, (_, lib) in enumerate(cols):
        ws.cell(h2, 4 + j, lib)
    ws.cell(h2, 4 + k, "Total")
    for r in (h1, h2):
        for c in range(1, nb + 1):
            cel = ws.cell(r, c)
            cel.font = _f(True, 8.5)
            cel.fill = F_ENTETE
            cel.border = BORD
            cel.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[h2].height = 36
    ligne = h2 + 1

    num = numero_depart
    for e in res.get("etat_des_lieux", []):
        obs = e.get("observation") if e.get("observation") is not None else e.get("observation_auto", "")
        style = e["type"]
        debut = ligne
        for l in e["lignes"]:
            ws.cell(ligne, 3, l["specification"] + (f"\n({' | '.join(l['variantes'])})" if l.get("variantes") else ""))
            for j, (code, _) in enumerate(cols):
                ws.cell(ligne, 4 + j, "/" if style == "non_evaluable" else _nombre(l["valeurs"].get(code, 0)))
            ws.cell(ligne, 4 + k, "/" if style == "non_evaluable" else _nombre(l["total"]))
            for c in range(1, nb + 1):
                cel = ws.cell(ligne, c)
                cel.border = BORD
                cel.font = _f(style == "sous_total" or c == 4 + k, 8.5,
                              italique=style == "non_evaluable", couleur="5B6472" if style == "non_evaluable" else "1B2433")
                if 4 <= c <= 4 + k:
                    cel.number_format = FMT_N
                    cel.alignment = Alignment(horizontal="right", vertical="center")
                else:
                    cel.alignment = Alignment(vertical="center", wrap_text=True,
                                              horizontal="center" if c == 1 else "left")
                if style == "sous_total":
                    cel.fill = F_SOUS_TOTAL
            ligne += 1
        fin = ligne - 1
        ws.cell(debut, 1, num)
        ws.cell(debut, 2, e["statistique"])
        ws.cell(debut, nb, obs or "/")
        ws.cell(debut, nb).font = _f(False, 8)
        if fin > debut:
            for c in (1, 2, nb):
                ws.merge_cells(start_row=debut, start_column=c, end_row=fin, end_column=c)
        for c in range(1, nb + 1):
            ws.cell(debut, c).border = Border(left=FIN, right=FIN, top=EPAIS, bottom=FIN)
        # hauteur approximative selon la longueur des observations
        lignes_obs = sum(max(1, len(x) // 55 + 1) for x in (obs or "").split("\n"))
        if fin == debut:
            ws.row_dimensions[debut].height = max(15, min(11 * lignes_obs, 110),
                                                  11 * (len(e["statistique"]) // 38 + 1))
        num += 1

    largeurs = [5, 38, 24] + [13] * k + [13, 58]
    for j, w in enumerate(largeurs, 1):
        ws.column_dimensions[get_column_letter(j)].width = max(ws.column_dimensions[get_column_letter(j)].width or 0, w)
    return ligne + 1, num, (h1, h2)


def _tableau(ws, entetes, lignes, largeurs, droite=(), nombres=()):
    for j, e in enumerate(entetes, 1):
        c = ws.cell(1, j, e)
        c.font, c.fill, c.border = _f(True, 8.5), F_ENTETE, BORD
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for i, l in enumerate(lignes, 2):
        for j, v in enumerate(l, 1):
            c = ws.cell(i, j, v)
            c.font, c.border = _f(False, 8.5), BORD
            c.alignment = Alignment(vertical="center", wrap_text=True,
                                    horizontal="right" if (j - 1) in droite else "left")
            if (j - 1) in nombres and isinstance(v, (int, float)):
                c.number_format = FMT_N
    for j, w in enumerate(largeurs, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(entetes))}{max(2, len(lignes) + 1)}"
    _mise_en_page(ws, "1:1")


def _feuilles_annexes(wb, res, suffixe=""):
    ws = wb.create_sheet(f"Signaux{suffixe}"[:31])
    lignes = []
    for x in res.get("signaux", []):
        lignes.append([x["famille"], x["libelle"], x["lignes"], x.get("entites"), x.get("lib_entites") or "",
                       x.get("base"), (x["taux"] / 100) if x.get("taux") is not None else None,
                       "; ".join(f"{a} : {b}" for a, b in x.get("detail", []) if b is not None),
                       x.get("commentaire", "")])
    _tableau(ws, ["Famille", "Signal", "Numéros", "Entités", "Nature", "Base", "Taux", "Détail", "Commentaire"],
             lignes, [16, 55, 12, 10, 16, 12, 9, 70, 60], droite=(2, 3, 5, 6), nombres=(2, 3, 5))
    for r in range(2, len(lignes) + 2):
        ws.cell(r, 7).number_format = "0.0%"

    ws = wb.create_sheet(f"Traçabilité{suffixe}"[:31])
    lignes = []
    for t in res.get("trace", []):
        for a, b in t["etapes"]:
            lignes.append([t["titre"], a, b])
        lignes.append([t["titre"], "= " + t["final_lib"], t["final"]])
    _tableau(ws, ["Catégorie", "Étape", "Lignes"], lignes, [34, 90, 14], droite=(2,), nombres=(2,))

    ws = wb.create_sheet(f"Contrôles{suffixe}"[:31])
    lignes = []
    for c in res.get("controles", []):
        lignes.append([c["famille"], c["libelle"], c["valeur"], c["base"],
                       (c["taux"] / 100) if c.get("taux") is not None else None,
                       "; ".join(f"{a} : {b}" for a, b in c.get("detail", []))])
    _tableau(ws, ["Famille", "Contrôle", "Nombre", "Base", "Taux", "Détail"], lignes,
             [20, 70, 12, 12, 9, 70], droite=(2, 3, 4), nombres=(2, 3))
    for r in range(2, len(lignes) + 2):
        ws.cell(r, 5).number_format = "0.0%"

    ws = wb.create_sheet(f"Complétude{suffixe}"[:31])
    lignes = []
    for bloc in res.get("completude", []):
        for c in bloc["champs"]:
            if c["present"]:
                lignes.append([bloc["libelle"], bloc["effectif"], R.LIBELLES_CHAMPS.get(c["champ"], c["champ"]),
                               c["vides"], c["invalides"], (c["taux"] or 0) / 100])
            else:
                lignes.append([bloc["libelle"], bloc["effectif"], R.LIBELLES_CHAMPS.get(c["champ"], c["champ"]),
                               "colonne absente", None, None])
    _tableau(ws, ["Catégorie", "Effectif", "Champ", "Non renseignés", "Invalides", "Taux"], lignes,
             [34, 12, 34, 16, 12, 9], droite=(1, 3, 4, 5), nombres=(1, 3, 4))
    for r in range(2, len(lignes) + 2):
        ws.cell(r, 6).number_format = "0.0%"

    ws = wb.create_sheet(f"Fichiers{suffixe}"[:31])
    lignes = [[f["nom"], f["role_libelle"], f["lignes"], f"{len(f['correspondances'])} / {f.get('colonnes_total', 0)}",
               f.get("source_statut", ""),
               "; ".join(f"{R.LIBELLES_CHAMPS.get(a, a)} ← {b}" for a, b in f["correspondances"].items()),
               ", ".join(R.LIBELLES_CHAMPS.get(a, a) for a in f["champs_manquants"])]
              for f in res.get("fichiers", [])]
    _tableau(ws, ["Fichier", "Rôle", "Lignes", "Colonnes reconnues", "Statuts", "Correspondances", "Non trouvés"],
             lignes, [36, 30, 12, 12, 10, 80, 40], droite=(2,), nombres=(2,))

    ws = wb.create_sheet(f"Statuts{suffixe}"[:31])
    lignes = [[s["fichier"], s["valeur"], R.LIBELLES_STATUT.get(s["categorie"], s["categorie"]), s["n"]]
              for s in res.get("statuts_bruts", [])]
    _tableau(ws, ["Fichier", "Valeur transmise", "Catégorie retenue", "Nombre"], lignes,
             [36, 36, 36, 14], droite=(3,), nombres=(3,))


def _logo(ws, colonne="H"):
    logo = config.chemin_logo()
    if not logo:
        return
    try:
        from openpyxl.drawing.image import Image as XLImage
        img = XLImage(logo)
        ratio = 55 / img.height
        img.height, img.width = 55, int(img.width * ratio)
        ws.add_image(img, f"{colonne}1")
    except Exception:
        pass


def _entete_classeur(ws, sous_titre):
    ws.row_dimensions[1].height = 22
    ws.row_dimensions[2].height = 20
    ws.cell(1, 1, config.ORGANISME[0]).font = _f(True, 10)
    ws.cell(2, 1, "ANNEXE – " + config.TITRE_ANNEXE).font = _f(True, 12, couleur="1F3A5F")
    ws.cell(3, 1, sous_titre).font = _f(False, 9, couleur="5B6472")
    return 5


def generer_xlsx(res: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "État des lieux"
    l = _entete_classeur(ws, f"{res.get('operateur_libelle', '')} – mois de {res['periode']['libelle']} – "
                             f"analyse du {res.get('date_analyse', '')}")
    _, _, (h1, h2) = feuille_etat(ws, res, l)
    _logo(ws, get_column_letter(5 + len(M.colonnes(res))))
    ws.freeze_panes = ws.cell(h2 + 1, 4)
    _mise_en_page(ws, f"{h1}:{h2}")
    _feuilles_annexes(wb, res)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def generer_xlsx_groupe(resultats: list[dict], numerotation_continue=True) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "État des lieux"
    l = _entete_classeur(ws, " – ".join(f"{r.get('operateur_libelle', '')} ({r['periode']['libelle']})"
                                         for r in resultats))
    _logo(ws, get_column_letter(5 + max(len(M.colonnes(r)) for r in resultats)))
    num = 1
    for i, res in enumerate(resultats):
        l, suivant, _ = feuille_etat(ws, res, l, num if numerotation_continue else 1, i)
        num = suivant
        l += 1
    _mise_en_page(ws)
    for i, res in enumerate(resultats):
        _feuilles_annexes(wb, res, f" {M.ROMAINS[i]}")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
