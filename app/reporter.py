"""
reporter.py
Génère un PDF complet : tableau de synthèse + graphiques.
Utilise reportlab (pip install reportlab).
"""
import io
import base64
from datetime import datetime

def generer_pdf(resultats: dict, charts: dict) -> bytes:
    """Génère le PDF et retourne les bytes."""
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                        Table, TableStyle, Image, PageBreak,
                                        HRFlowable)
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from PIL import Image as PILImage
    except ImportError:
        return b"[ERREUR] Installez reportlab et Pillow : pip install reportlab Pillow"

    buf    = io.BytesIO()
    doc    = SimpleDocTemplate(buf, pagesize=A4,
                               leftMargin=2*cm, rightMargin=2*cm,
                               topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story  = []

    # ── Styles personnalisés ─────────────────────────────────────────────────
    titre_style = ParagraphStyle('titre',
        fontSize=18, fontName='Helvetica-Bold',
        textColor=colors.HexColor('#1a1a2e'),
        alignment=TA_CENTER, spaceAfter=6)

    sous_titre_style = ParagraphStyle('sous_titre',
        fontSize=11, fontName='Helvetica',
        textColor=colors.HexColor('#555555'),
        alignment=TA_CENTER, spaceAfter=4)

    section_style = ParagraphStyle('section',
        fontSize=13, fontName='Helvetica-Bold',
        textColor=colors.HexColor('#1a1a2e'),
        spaceBefore=16, spaceAfter=8,
        borderPad=4)

    cell_style = ParagraphStyle('cell',
        fontSize=8, fontName='Helvetica',
        wordWrap='CJK')

    # ── Page de garde ────────────────────────────────────────────────────────
    story.append(Spacer(1, 2*cm))
    story.append(Paragraph("AGENCE DE RÉGULATION DES TÉLÉCOMMUNICATIONS", sous_titre_style))
    story.append(Paragraph("Direction Technique", sous_titre_style))
    story.append(Paragraph("Sous-direction Gestion et Régulation des Numéros", sous_titre_style))
    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width="100%", thickness=2,
                             color=colors.HexColor('#1a1a2e')))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("RAPPORT D'ANALYSE", titre_style))
    story.append(Paragraph("Qualité des données abonnés — BDI", titre_style))
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=2,
                             color=colors.HexColor('#1a1a2e')))
    story.append(Spacer(1, 1.5*cm))

    op   = resultats.get("operateur", "—")
    date = resultats.get("date_analyse", datetime.now().strftime("%d/%m/%Y %H:%M"))

    meta = [
        ["Opérateur",       op],
        ["Date d'analyse",  date],
        ["Total abonnés",   f"{resultats.get('total_abonnes', 0):,}"],
        ["Total actifs",    f"{resultats.get('total_actifs',  0):,}"],
        ["Total suspendus", f"{resultats.get('total_suspendus', 0):,}"],
    ]
    t_meta = Table(meta, colWidths=[5*cm, 10*cm])
    t_meta.setStyle(TableStyle([
        ('FONTNAME',    (0,0), (-1,-1), 'Helvetica'),
        ('FONTNAME',    (0,0), (0,-1),  'Helvetica-Bold'),
        ('FONTSIZE',    (0,0), (-1,-1), 11),
        ('TEXTCOLOR',   (0,0), (0,-1),  colors.HexColor('#1a1a2e')),
        ('ROWBACKGROUNDS', (0,0), (-1,-1),
         [colors.HexColor('#F0F4F8'), colors.white]),
        ('GRID',        (0,0), (-1,-1), 0.5, colors.HexColor('#D5DDE5')),
        ('PADDING',     (0,0), (-1,-1), 8),
    ]))
    story.append(t_meta)
    story.append(PageBreak())

    # ── Tableau de synthèse ──────────────────────────────────────────────────
    story.append(Paragraph("1. Tableau de synthèse", section_style))

    tableau = resultats.get("tableau", [])
    if tableau:
        cols_affich = ["N°", "Indicateur", "Actifs", "Suspendus", "Total"]
        # Détecte les colonnes disponibles
        first = tableau[0]
        if "Susp. Sortant" in first:
            cols_affich = ["N°", "Indicateur", "Actifs",
                           "Susp. Sortant", "Susp. Entrant", "Suspendus", "Total"]

        header = [Paragraph(f"<b>{c}</b>", cell_style) for c in cols_affich]
        rows_pdf = [header]

        for i, row in enumerate(tableau):
            r = []
            for c in cols_affich:
                val = row.get(c, "")
                if isinstance(val, int) and val > 0:
                    val = f"{val:,}"
                r.append(Paragraph(str(val), cell_style))
            rows_pdf.append(r)

        col_w = [1*cm, 6.5*cm] + [2*cm] * (len(cols_affich) - 2)
        t = Table(rows_pdf, colWidths=col_w, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND',  (0,0), (-1,0),  colors.HexColor('#1a1a2e')),
            ('TEXTCOLOR',   (0,0), (-1,0),  colors.white),
            ('FONTNAME',    (0,0), (-1,0),  'Helvetica-Bold'),
            ('FONTSIZE',    (0,0), (-1,-1), 8),
            ('ROWBACKGROUNDS', (0,1), (-1,-1),
             [colors.white, colors.HexColor('#F8FAFC')]),
            ('GRID',        (0,0), (-1,-1), 0.3, colors.HexColor('#D5DDE5')),
            ('PADDING',     (0,0), (-1,-1), 5),
            ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN',       (2,1), (-1,-1), 'RIGHT'),
        ]))
        story.append(t)

    story.append(PageBreak())

    # ── Graphiques ───────────────────────────────────────────────────────────
    titres_charts = {
        "hlr_donut"        : "2. Répartition du parc abonnés (HLR)",
        "mal_identifies"   : "3. Localisation et quantification des problèmes d'identification",
        "champs_manquants" : "4. Volume des anomalies par indicateur",
        "age_distribution" : "5. Répartition Majeurs / Mineurs",
        "risques"          : "6. Indicateurs de risque — Conformité & Fraude",
        "coherence"        : "7. Taux de cohérence HLR ↔ Source",
    }

    for key, titre in titres_charts.items():
        b64 = charts.get(key, "")
        if not b64:
            continue
        story.append(Paragraph(titre, section_style))
        img_bytes = base64.b64decode(b64)
        img_buf   = io.BytesIO(img_bytes)
        img       = Image(img_buf, width=16*cm, height=9*cm)
        story.append(img)
        story.append(Spacer(1, 0.5*cm))

        # PageBreak sauf après le dernier
        if key != list(titres_charts.keys())[-1]:
            story.append(PageBreak())

    # ── Pied de page final ───────────────────────────────────────────────────
    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width="100%", thickness=1,
                             color=colors.HexColor('#D5DDE5')))
    story.append(Paragraph(
        f"Rapport généré le {date} — ART Cameroun / Direction Technique",
        ParagraphStyle('footer', fontSize=8, textColor=colors.grey,
                       alignment=TA_CENTER, spaceBefore=6)
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()
