"""
note.py
───────
Note de synthèse mensuelle d'une page (A4 portrait), PDF et Word :
chiffres clés par opérateur, évolution sur un mois, constats principaux,
observations et actions proposées saisies par les chargés d'analyse.
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

import config
from . import pdf as X


def _sources(s) -> str:
    morceaux = []
    for c in s["colonnes"]:
        etat = "validée" if c["validee"] else "non validée"
        morceaux.append(f"{c['libelle']} : analyse n° {c['id']} ({etat})")
    return " ; ".join(morceaux)


# ═════════════════════════════════════════════════════════════════════════════
# PDF
# ═════════════════════════════════════════════════════════════════════════════

def generer_note_pdf(s: dict) -> bytes:
    buf = io.BytesIO()
    doc, C = X._document(buf, f"Note de synthèse – {s['libelle']}", f"Note de synthèse – {s['libelle']}", page=A4)
    largeur = A4[0] - X.MARGE_G - X.MARGE_D
    h = X._bloc_titre("Bases de données d'identification des opérateurs",
                      f"Mois de {s['libelle']} – note établie le {datetime.now().strftime('%d/%m/%Y')}",
                      mot="NOTE DE SYNTHÈSE")

    # 1. Chiffres clés
    h.append(X.P("1. Chiffres clés", "section"))
    k = len(s["colonnes"])
    w_lib = 5.6 * cm
    w_op = (largeur - w_lib) / max(k, 1)
    entete = [X.P("Indicateur", "th")] + [X.P(c["libelle"] + ("" if c["validee"] else " *"), "th")
                                          for c in s["colonnes"]]
    donnees, styles = [entete], []
    for i, l in enumerate(s["lignes"], 1):
        ligne = [X.P(l["libelle"], "td")]
        for c in l["cellules"]:
            txt = f"<b>{escape(c['txt'])}</b>"
            if c["taux"]:
                txt += f" <font size='6.5' color='#5B6472'>({escape(c['taux'])})</font>"
            if c["var_txt"] and c["var_txt"] != "=":
                txt += f"<br/><font size='6.3' color='#5B6472'>{escape(c['var_txt'])} vs {escape(s['libelle_precedent'])}</font>"
            ligne.append(Paragraph(txt, X.S["num"]))
        donnees.append(ligne)
        if not l["anomalie"]:
            styles.append(("BACKGROUND", (0, i), (-1, i), X.SOUS_TOTAL))
    t = Table(donnees, colWidths=[w_lib] + [w_op] * k, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), X.ENTETE), ("GRID", (0, 0), (-1, -1), 0.4, X.TRAIT),
                           ("BOX", (0, 0), (-1, -1), 0.8, X.ENCRE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)] + styles))
    h.append(t)
    if any(not c["validee"] for c in s["colonnes"]):
        h.append(X.P("* Analyse non encore validée.", "note"))

    # 2. Constats
    h.append(X.P("2. Constats principaux", "section"))
    if s["constats"]:
        for c in s["constats"]:
            h.append(Paragraph("• " + escape(c), X._st("constat", fontSize=8.5, leading=11.5, leftIndent=8,
                                                          firstLineIndent=-8, spaceAfter=2)))
    else:
        h.append(X.P("Aucune anomalie relevée.", "texte"))

    # 3. Observations et actions
    h.append(X.P("3. Observations et actions proposées", "section"))
    texte = (s.get("note") or "").strip() or "À compléter par les chargés d'analyse."
    for para in texte.split("\n"):
        if para.strip():
            h.append(X.P(para, "texte"))
    h += [Spacer(1, 8), X.P("Sources : " + _sources(s) + ". Le détail figure dans les annexes de chaque analyse.",
                           "note")]
    doc.build(h, canvasmaker=C)
    return buf.getvalue()


# ═════════════════════════════════════════════════════════════════════════════
# WORD
# ═════════════════════════════════════════════════════════════════════════════

def generer_note_docx(s: dict) -> bytes:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt
    from . import word as W

    doc = W._nouveau_document(f"Note de synthèse – {s['libelle']}", paysage=False)
    W._bloc_titre(doc, "Bases de données d'identification des opérateurs",
                  f"Mois de {s['libelle']} – note établie le {datetime.now().strftime('%d/%m/%Y')}",
                  mot="NOTE DE SYNTHÈSE")
    W._section(doc, "1. Chiffres clés")
    k = len(s["colonnes"])
    largeur = 21.0 - 2 * 1.8
    w_lib = 5.6
    lignes = []
    for l in s["lignes"]:
        ligne = [l["libelle"]]
        for c in l["cellules"]:
            txt = c["txt"] + (f" ({c['taux']})" if c["taux"] else "")
            if c["var_txt"] and c["var_txt"] != "=":
                txt += f"\n{c['var_txt']} vs {s['libelle_precedent']}"
            ligne.append(txt)
        lignes.append(ligne)
    W._tableau_simple(doc, ["Indicateur"] + [c["libelle"] + ("" if c["validee"] else " *") for c in s["colonnes"]],
                      lignes, [w_lib] + [(largeur - w_lib) / max(k, 1)] * k, droite=tuple(range(1, k + 1)))
    if any(not c["validee"] for c in s["colonnes"]):
        W._para(doc, "* Analyse non encore validée.", 7.5, couleur=W.GRIS, avant=2)
    W._section(doc, "2. Constats principaux")
    for c in s["constats"] or ["Aucune anomalie relevée."]:
        p = W._para(doc, "• " + c, 9, apres=2)
        p.paragraph_format.left_indent = Pt(8)
        p.paragraph_format.first_line_indent = Pt(-8)
    W._section(doc, "3. Observations et actions proposées")
    texte = (s.get("note") or "").strip() or "À compléter par les chargés d'analyse."
    for para in texte.split("\n"):
        if para.strip():
            W._para(doc, para, 9, apres=3)
    W._para(doc, "Sources : " + _sources(s) + ". Le détail figure dans les annexes de chaque analyse.", 7.5,
            couleur=W.GRIS, avant=8, align=WD_ALIGN_PARAGRAPH.LEFT)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


__all__ = ["generer_note_pdf", "generer_note_docx", "config"]
