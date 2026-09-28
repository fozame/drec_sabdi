"""
pdf.py
──────
Annexe PDF (A4 paysage) : en-tête institutionnel, tableau « État des lieux »
au format de référence, contrôles complémentaires, complétude, fichiers et
notes de méthode. Pagination « Page x / y » sur chaque page.
"""
from __future__ import annotations

import io
import os
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, KeepTogether, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

import config
from . import modele as M

# ── Polices ─────────────────────────────────────────────────────────────────
_POLICES = os.path.join(os.path.dirname(__file__), "polices")
try:
    pdfmetrics.registerFont(TTFont("Sans", os.path.join(_POLICES, "LiberationSans-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Sans-Bold", os.path.join(_POLICES, "LiberationSans-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("Sans-Italic", os.path.join(_POLICES, "LiberationSans-Italic.ttf")))
    pdfmetrics.registerFont(TTFont("Sans-BoldItalic", os.path.join(_POLICES, "LiberationSans-BoldItalic.ttf")))
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    registerFontFamily("Sans", normal="Sans", bold="Sans-Bold", italic="Sans-Italic", boldItalic="Sans-BoldItalic")
    F, FB, FI = "Sans", "Sans-Bold", "Sans-Italic"
except Exception:  # repli sur les polices standard
    F, FB, FI = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"

# ── Couleurs (sobres, adaptées à l'impression) ──────────────────────────────
ENCRE = colors.HexColor("#1B2433")
GRIS = colors.HexColor("#5B6472")
TRAIT = colors.HexColor("#9AA3AF")
TRAIT_CLAIR = colors.HexColor("#C9CED6")
ENTETE = colors.HexColor("#DCE3EC")
SOUS_TOTAL = colors.HexColor("#EEF1F5")
ACCENT = colors.HexColor("#1F3A5F")
ALERTE = colors.HexColor("#8A1C1C")

PAGE = landscape(A4)
MARGE_G = MARGE_D = 1.4 * cm
MARGE_H, MARGE_B = 2.0 * cm, 1.6 * cm
LARGEUR = PAGE[0] - MARGE_G - MARGE_D


def _st(nom, **kw):
    base = dict(fontName=F, fontSize=8, leading=10, textColor=ENCRE)
    base.update(kw)
    return ParagraphStyle(nom, **base)


S = {
    "org": _st("org", fontName=FB, fontSize=9, leading=12, alignment=TA_CENTER),
    "org2": _st("org2", fontSize=8.5, leading=11, alignment=TA_CENTER, textColor=GRIS),
    "annexe": _st("annexe", fontName=FB, fontSize=13, leading=16, alignment=TA_CENTER,
                  textColor=ACCENT, spaceBefore=10),
    "titre": _st("titre", fontName=FB, fontSize=11.5, leading=15, alignment=TA_CENTER, spaceAfter=4),
    "section": _st("section", fontName=FB, fontSize=10.5, leading=14, spaceBefore=10, spaceAfter=6,
                   textColor=ACCENT),
    "sous_section": _st("sous_section", fontName=FB, fontSize=9, leading=12, spaceBefore=8, spaceAfter=4),
    "texte": _st("texte", fontSize=8.5, leading=11.5),
    "note": _st("note", fontSize=7.5, leading=10, textColor=GRIS),
    "th": _st("th", fontName=FB, fontSize=7.5, leading=9, alignment=TA_CENTER),
    "td": _st("td", fontSize=7.5, leading=9.2),
    "td_b": _st("td_b", fontName=FB, fontSize=7.5, leading=9.2),
    "td_i": _st("td_i", fontName=FI, fontSize=7.5, leading=9.2, textColor=GRIS),
    "td_c": _st("td_c", fontSize=7.5, leading=9.2, alignment=TA_CENTER),
    "num": _st("num", fontSize=7.5, leading=9.2, alignment=TA_RIGHT),
    "num_b": _st("num_b", fontName=FB, fontSize=7.5, leading=9.2, alignment=TA_RIGHT),
    "obs": _st("obs", fontSize=6.8, leading=8.4, textColor=colors.HexColor("#303846")),
    "meta_k": _st("meta_k", fontName=FB, fontSize=8.5, leading=11, textColor=GRIS),
    "meta_v": _st("meta_v", fontSize=8.5, leading=11),
}


def P(texte, style="td"):
    t = escape(str(texte if texte is not None else "")).replace("\n", "<br/>")
    return Paragraph(t, S[style])


# ═════════════════════════════════════════════════════════════════════════════
# PAGINATION
# ═════════════════════════════════════════════════════════════════════════════

class _CanvasNumerote(rl_canvas.Canvas):
    """Canvas en deux passes pour afficher « Page x / y »."""
    entete_droite = ""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._pages = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for etat in self._pages:
            self.__dict__.update(etat)
            self._decor(total)
            super().showPage()
        super().save()

    def _decor(self, total):
        w, h = self._pagesize
        self.saveState()
        self.setStrokeColor(TRAIT)
        self.setLineWidth(0.5)
        # En-tête (logo + organisme)
        x = MARGE_G
        logo = config.chemin_logo()
        if logo:
            try:
                from reportlab.lib.utils import ImageReader
                img = ImageReader(logo)
                iw, ih = img.getSize()
                hauteur = 0.75 * cm
                largeur = hauteur * iw / ih
                self.drawImage(img, MARGE_G, h - 1.22 * cm, largeur, hauteur, mask="auto")
                x = MARGE_G + largeur + 0.2 * cm
            except Exception:
                pass
        self.setFont(FB, 7.5)
        self.setFillColor(GRIS)
        self.drawString(x, h - 1.0 * cm, config.ORGANISME[0])
        self.setFont(F, 6.5)
        self.drawString(x, h - 1.3 * cm + 0.02 * cm, config.ORGANISME[2])
        self.setFont(F, 7.5)
        self.drawRightString(w - MARGE_D, h - 1.15 * cm, self.entete_droite)
        self.line(MARGE_G, h - 1.45 * cm, w - MARGE_D, h - 1.45 * cm)
        # Pied de page
        self.line(MARGE_G, 1.15 * cm, w - MARGE_D, 1.15 * cm)
        self.setFont(F, 7)
        self.drawString(MARGE_G, 0.75 * cm,
                        f"{config.NOM_APPLICATION} – {config.NOM_COMPLET} – document généré le "
                        f"{datetime.now().strftime('%d/%m/%Y à %H:%M')}")
        self.drawRightString(w - MARGE_D, 0.75 * cm, f"Page {self._pageNumber} / {total}")
        self.restoreState()


def _document(buf, titre, entete_droite, page=PAGE):
    doc = BaseDocTemplate(buf, pagesize=page, leftMargin=MARGE_G, rightMargin=MARGE_D,
                          topMargin=MARGE_H, bottomMargin=MARGE_B, title=titre,
                          author=config.ORGANISME[0], creator=config.NOM_APPLICATION)
    cadre = Frame(MARGE_G, MARGE_B, page[0] - MARGE_G - MARGE_D, page[1] - MARGE_H - MARGE_B, id="corps",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="page", frames=[cadre])])

    class C(_CanvasNumerote):
        pass
    C.entete_droite = entete_droite
    return doc, C


# ═════════════════════════════════════════════════════════════════════════════
# BLOCS
# ═════════════════════════════════════════════════════════════════════════════

def logo_flowable(hauteur_cm: float = 2.0):
    logo = config.chemin_logo()
    if not logo:
        return None
    try:
        from reportlab.lib.utils import ImageReader
        from reportlab.platypus import Image
        iw, ih = ImageReader(logo).getSize()
        return Image(logo, width=hauteur_cm * cm * iw / ih, height=hauteur_cm * cm)
    except Exception:
        return None


def _bloc_titre(titre, sous_titre=None, mot="ANNEXE"):
    elts = []
    lg = logo_flowable()
    if lg:
        elts += [lg, Spacer(1, 4)]
    elts += [P(config.ORGANISME[0], "org")]
    for l in config.ORGANISME[1:]:
        elts.append(P(l, "org2"))
    elts += [Spacer(1, 4), P(mot, "annexe"), P(titre, "titre")]
    if sous_titre:
        elts.append(P(sous_titre, "org2"))
    elts.append(Spacer(1, 8))
    return elts


def _meta(res):
    p = res.get("periode", {})
    lignes = [
        ("Opérateur", res.get("operateur_libelle", "")),
        ("Période analysée", p.get("libelle", "")),
        ("Date de référence", M._date_fr(p.get("date_reference"))),
        ("Analyse réalisée le", f"{res.get('date_analyse', '')}" +
         (f" par {res['utilisateur']}" if res.get("utilisateur") else "")),
        ("Fichiers analysés", str(len(res.get("fichiers", [])))),
    ]
    t = Table([[P(k, "meta_k"), P(v, "meta_v")] for k, v in lignes], colWidths=[4.2 * cm, 12 * cm], hAlign="LEFT")
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, TRAIT_CLAIR),
                           ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
    return t


def tableau_etat_pdf(res, numero_depart=1):
    mod = M.tableau_etat(res, numero_depart)
    cols = mod["colonnes"]
    k = len(cols)
    w_n, w_stat, w_spec, w_tot = 0.9 * cm, 5.0 * cm, 3.3 * cm, 2.0 * cm
    w_s = (2.0 if k <= 4 else 1.75) * cm
    w_obs = LARGEUR - (w_n + w_stat + w_spec + w_tot + k * w_s)
    if w_obs < 4.5 * cm:
        w_stat -= (4.5 * cm - w_obs)
        w_obs = 4.5 * cm
    elif w_obs > 9.5 * cm:  # peu de colonnes de statut : on élargit les colonnes de gauche
        surplus = w_obs - 9.5 * cm
        w_stat += surplus * 0.45
        w_spec += surplus * 0.25
        w_s += surplus * 0.30 / k
        w_obs = 9.5 * cm
    largeurs = [w_n, w_stat, w_spec] + [w_s] * k + [w_tot, w_obs]

    h1 = [P("N°", "th"), P("Statistiques", "th"), P("Spécifications", "th"), P("Résultats", "th")] + \
         [""] * k + [P("Observations", "th")]
    h2 = ["", "", ""] + [P(lib, "th") for _, lib in cols] + [P("Total", "th"), ""]
    donnees = [h1, h2]
    styles = [
        ("FONT", (0, 0), (-1, -1), F, 7.5),
        ("BACKGROUND", (0, 0), (-1, 1), ENTETE),
        ("SPAN", (0, 0), (0, 1)), ("SPAN", (1, 0), (1, 1)), ("SPAN", (2, 0), (2, 1)),
        ("SPAN", (3, 0), (3 + k, 0)), ("SPAN", (4 + k, 0), (4 + k, 1)),
        ("VALIGN", (0, 0), (-1, 1), "MIDDLE"),
        ("VALIGN", (0, 2), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, TRAIT),
        ("BOX", (0, 0), (-1, -1), 0.8, ENCRE),
        ("LINEBELOW", (0, 1), (-1, 1), 0.8, ENCRE),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    r = 2
    for l in mod["lignes"]:
        st = l["style"]
        spec = escape(l["specification"])
        if l["variantes"]:
            spec += f'<br/><font size="6" color="#5B6472">{escape(" | ".join(l["variantes"]))}</font>'
        cellule_spec = Paragraph(spec, S["td_b" if st == "sous_total" else "td"])
        num = "num_b" if st == "sous_total" else "num"
        ligne = [
            P(l["n"], "td_c") if l["debut_groupe"] else "",
            P(l["statistique"], "td_b" if st == "sous_total" else ("td_i" if st == "non_evaluable" else "td"))
            if l["debut_groupe"] else "",
            cellule_spec,
        ] + [P(v, num) for v in l["valeurs"]] + [P(l["total"], "num_b"),
                                                   P(l["observation"], "obs") if l["debut_groupe"] else ""]
        donnees.append(ligne)
        if l["debut_groupe"] and l["taille_groupe"] > 1:
            fin = r + l["taille_groupe"] - 1
            styles += [("SPAN", (0, r), (0, fin)), ("SPAN", (1, r), (1, fin)), ("SPAN", (4 + k, r), (4 + k, fin))]
        if st == "sous_total":
            styles.append(("BACKGROUND", (0, r), (-1, r), SOUS_TOTAL))
        if l["debut_groupe"]:
            styles.append(("LINEABOVE", (0, r), (-1, r), 0.7, ENCRE))
        r += 1
    t = Table(donnees, colWidths=largeurs, repeatRows=2)
    t.setStyle(TableStyle(styles))
    return t, mod["numero_suivant"]


def _tableau_simple(entetes, lignes, largeurs, alignements=None, style_lignes=None):
    alignements = alignements or ["L"] * len(entetes)
    donnees = [[P(e, "th") for e in entetes]]
    for i, l in enumerate(lignes):
        donnees.append([P(v, "num" if a == "R" else ("td_c" if a == "C" else "td"))
                        for v, a in zip(l, alignements)])
    t = Table(donnees, colWidths=largeurs, repeatRows=1, hAlign="LEFT")
    st = [("BACKGROUND", (0, 0), (-1, 0), ENTETE), ("GRID", (0, 0), (-1, -1), 0.4, TRAIT),
          ("BOX", (0, 0), (-1, -1), 0.8, ENCRE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
          ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    if style_lignes:
        st += style_lignes
    t.setStyle(TableStyle(st))
    return t


def _controles(res):
    ctrl = M.controles(res)
    lignes, st, famille = [], [], None
    r = 1
    for c in ctrl:
        lignes.append([c["famille"] if c["famille"] != famille else "", c["libelle"], c["valeur"],
                       c["base"], c["taux"], c["detail"] or "–"])
        if c["famille"] != famille:
            st.append(("LINEABOVE", (0, r), (-1, r), 0.7, ENCRE))
        famille = c["famille"]
        r += 1
    return _tableau_simple(["Famille", "Contrôle", "Nombre", "Base", "Taux", "Détail"], lignes,
                           [3.0 * cm, 9.2 * cm, 2.0 * cm, 2.0 * cm, 1.6 * cm, LARGEUR - 17.8 * cm],
                           ["L", "L", "R", "R", "R", "L"], st)


def _completude(res):
    elts = []
    for bloc in M.completude(res):
        lignes = [[l["libelle"], l["colonne"], l["vides"], l["invalides"], l["taux"]] for l in bloc["lignes"]]
        st = [("TEXTCOLOR", (0, i + 1), (-1, i + 1), GRIS) for i, l in enumerate(bloc["lignes"]) if l["absent"]]
        t = _tableau_simple(["Champ", "Colonne du fichier", "Non renseignés", "Invalides", "Taux"],
                            lignes, [6 * cm, 6 * cm, 3 * cm, 3 * cm, 2.4 * cm], ["L", "L", "R", "R", "R"], st)
        elts.append(KeepTogether([P(f"{bloc['libelle']} – effectif : {bloc['effectif']}", "sous_section"), t]))
    return elts


def _fichiers(res):
    lignes = [[f["nom"], f["role"], f["lignes"], f["reconnues"], f["statut"], f["manquants"]]
              for f in M.fichiers(res)]
    return _tableau_simple(["Fichier", "Rôle retenu", "Lignes", "Colonnes reconnues", "Statuts", "Champs non trouvés"],
                           lignes, [6.8 * cm, 5.2 * cm, 2.2 * cm, 2.5 * cm, 2.0 * cm, LARGEUR - 18.7 * cm],
                           ["L", "L", "R", "C", "C", "L"])


def _statuts(res):
    lignes = [[s["fichier"], s["valeur"], s["categorie"], s["n"]] for s in M.statuts(res)]
    if not lignes:
        return None
    return _tableau_simple(["Fichier", "Valeur transmise", "Catégorie retenue", "Nombre"], lignes,
                           [7 * cm, 6.5 * cm, 6.5 * cm, 3 * cm], ["L", "L", "L", "R"])


def _signaux(res):
    """Tableau des signaux d'alerte : un signal par ligne, détail condensé."""
    lignes, st, famille, r = [], [], None, 1
    for x in M.signaux(res):
        det = "; ".join(f"{a} : {b}" for a, b in x["detail_txt"] if b is not None and b not in ("0",))
        lignes.append([x["famille"] if x["famille"] != famille else "", x["libelle"] +
                       (f"\n{x['commentaire']}" if x["commentaire"] else ""),
                       x["lignes_txt"], x["entites_txt"] or "–", x["taux_txt"], det or "–"])
        if x["famille"] != famille:
            st.append(("LINEABOVE", (0, r), (-1, r), 0.7, ENCRE))
        famille = x["famille"]
        r += 1
    if not lignes:
        return None
    return _tableau_simple(["Famille", "Signal", "Numéros", "Entités", "Taux", "Détail"], lignes,
                           [2.6 * cm, 8.2 * cm, 2.0 * cm, 3.2 * cm, 1.6 * cm, LARGEUR - 17.6 * cm],
                           ["L", "L", "R", "R", "R", "L"], st)


def _trace(res):
    elts = []
    for t in M.trace(res):
        lignes = [[a, b] for a, b in t["etapes"]] + [[t["final_lib"], t["final"]]]
        n = len(lignes)
        elts.append(KeepTogether([P(t["titre"], "sous_section"), _tableau_simple(
            ["Étape", "Lignes"], lignes, [13 * cm, 3 * cm], ["L", "R"],
            [("FONTNAME", (0, n), (-1, n), FB), ("LINEABOVE", (0, n), (-1, n), 0.8, ENCRE)])]))
    return elts


def _notes(res):
    return [P("Notes de méthode", "sous_section")] + [P(f"• {n}", "note") for n in M.notes_methode(res)]


# ═════════════════════════════════════════════════════════════════════════════
# POINTS D'ENTRÉE
# ═════════════════════════════════════════════════════════════════════════════

def generer_pdf(res: dict, contenu: str = "complet") -> bytes:
    """Annexe d'une analyse. contenu : « tableau » ou « complet »."""
    buf = io.BytesIO()
    titre = M.titre_section(res)
    doc, C = _document(buf, titre, f"Annexe – {res.get('operateur_libelle', '')} – {res['periode']['libelle']}")
    h = []
    h += _bloc_titre(config.TITRE_ANNEXE,
                     f"{res.get('operateur_libelle', '')} – mois de {res['periode']['libelle']}")
    h += [_meta(res), Spacer(1, 10)]
    h.append(P(M.titre_section(res, 0), "section"))
    t, _ = tableau_etat_pdf(res)
    h.append(t)
    if contenu == "complet":
        sig = _signaux(res)
        if sig:
            h += [PageBreak(), P("II. Signaux d'alerte", "section"),
                  P(f"Informations non visibles dans les chiffres déclarés. Âges et délais calculés au mois de la "
                    f"base ({res['periode'].get('mois_reference') or res['periode']['libelle']}). Une même personne "
                    f"est reconnue par son nom et sa date de naissance. Les lignes concernées sont disponibles en "
                    f"extraction depuis l'application.", "note"), Spacer(1, 4), sig]
        h += [PageBreak(), P("III. Contrôles complémentaires", "section"),
              P("Contrôles réalisés sur les fichiers transmis, en complément de l'état des lieux. "
                "Ils n'entrent pas dans les chiffres du tableau principal.", "note"), Spacer(1, 4),
              _controles(res)]
        h += [CondPageBreak(6 * cm), P("IV. Complétude des champs d'identification", "section")] + _completude(res)
        h += [PageBreak(), P("V. Fichiers analysés et passage du fichier au tableau", "section"), _fichiers(res)]
        h += _trace(res)
        st = _statuts(res)
        if st:
            h += [CondPageBreak(5 * cm), P("Valeurs de statut rencontrées et catégories retenues", "sous_section"), st]
        h += [Spacer(1, 6)] + _notes(res)
    else:
        h += [Spacer(1, 6)] + _notes(res)
    doc.build(h, canvasmaker=C)
    return buf.getvalue()


def generer_pdf_groupe(resultats: list[dict], contenu: str = "tableau", numerotation_continue: bool = True) -> bytes:
    """Annexe regroupant plusieurs opérateurs / périodes (sections I, II, …)."""
    buf = io.BytesIO()
    doc, C = _document(buf, config.TITRE_ANNEXE, f"Annexe – {config.TITRE_ANNEXE}")
    h = _bloc_titre(config.TITRE_ANNEXE, " – ".join(
        f"{r.get('operateur_libelle', '')} ({r['periode']['libelle']})" for r in resultats))
    num = 1
    for i, res in enumerate(resultats):
        if i:
            h.append(PageBreak())
        h.append(P(M.titre_section(res, i), "section"))
        t, suivant = tableau_etat_pdf(res, num if numerotation_continue else 1)
        num = suivant
        h.append(t)
        if contenu == "complet":
            sig = _signaux(res)
            if sig:
                h += [CondPageBreak(6 * cm), P(f"Signaux d'alerte – {res.get('operateur_libelle', '')}",
                                               "sous_section"), sig]
            h += [CondPageBreak(6 * cm), P(f"Contrôles complémentaires – {res.get('operateur_libelle', '')}",
                                           "sous_section"), _controles(res)]
    h += [Spacer(1, 8)] + _notes(resultats[0])
    doc.build(h, canvasmaker=C)
    return buf.getvalue()
