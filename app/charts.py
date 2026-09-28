"""
charts.py
Génère les 6 graphiques les plus pertinents pour l'analyse BDI.
Retourne des images base64 pour affichage direct dans le HTML.
Focus : quantifier et localiser précisément les problèmes d'identification.
"""
import io
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── Palette ──────────────────────────────────────────────────────────────────
C = {
    "vert"    : "#27AE60",
    "rouge"   : "#E74C3C",
    "orange"  : "#E67E22",
    "bleu"    : "#2980B9",
    "violet"  : "#8E44AD",
    "gris"    : "#95A5A6",
    "fond"    : "#F8FAFC",
    "texte"   : "#2C3E50",
    "bordure" : "#D5DDE5",
}

def _style():
    plt.rcParams.update({
        "font.family"      : "DejaVu Sans",
        "font.size"        : 11,
        "axes.titlesize"   : 13,
        "axes.titleweight" : "bold",
        "axes.spines.top"  : False,
        "axes.spines.right": False,
        "axes.grid"        : True,
        "grid.color"       : C["bordure"],
        "grid.linestyle"   : "--",
        "grid.linewidth"   : 0.6,
        "figure.facecolor" : C["fond"],
        "axes.facecolor"   : "#FFFFFF",
        "text.color"       : C["texte"],
    })


def _to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight',
                facecolor=C["fond"], dpi=150)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode()
    plt.close(fig)
    return b64


def _get_row(tableau, keyword):
    for row in tableau:
        if keyword.lower() in str(row.get("Indicateur", "")).lower():
            return row
    return None


def _val(row, col, fallback=0):
    if row is None:
        return fallback
    for c in [col, col.lower(), col.upper()]:
        if c in row:
            try:
                return int(row[c])
            except:
                pass
    return fallback


# ── Graphique 1 : Donut HLR — Actifs / Suspendus ────────────────────────────
def chart_hlr_donut(tableau, operateur) -> str:
    _style()
    row = _get_row(tableau, "total") or _get_row(tableau, "numéro")
    if not row:
        return ""

    actifs    = _val(row, "Actifs")
    suspendus = _val(row, "Suspendus") or _val(row, "Susp. Sortant")
    total     = actifs + suspendus
    if total == 0:
        return ""

    fig, ax = plt.subplots(figsize=(7, 5))
    fig.patch.set_facecolor(C["fond"])

    vals   = [actifs, suspendus]
    colors = [C["vert"], C["rouge"]]
    labels = [
        f"Actifs\n{actifs:,} ({actifs/total:.1%})",
        f"Suspendus\n{suspendus:,} ({suspendus/total:.1%})"
    ]

    wedges, _, autotexts = ax.pie(
        vals, colors=colors, autopct='%1.1f%%',
        startangle=90, explode=(0.04, 0.04),
        pctdistance=0.75, wedgeprops=dict(linewidth=2, edgecolor='white')
    )
    for at in autotexts:
        at.set_fontsize(12)
        at.set_fontweight('bold')
        at.set_color('white')

    # Cercle central
    centre = plt.Circle((0, 0), 0.55, fc='white')
    ax.add_artist(centre)
    ax.text(0, 0.08, f"{total:,}", ha='center', va='center',
            fontsize=14, fontweight='bold', color=C["texte"])
    ax.text(0, -0.18, "Total HLR", ha='center', va='center',
            fontsize=10, color=C["gris"])

    ax.legend(wedges, labels, loc='lower center',
              bbox_to_anchor=(0.5, -0.12), ncol=2, frameon=False, fontsize=10)
    ax.set_title(f"[{operateur}] Répartition du parc abonnés — HLR", pad=16)
    fig.tight_layout()
    return _to_b64(fig)


# ── Graphique 2 : Mal-identifiés par catégorie — Nb + % ─────────────────────
def chart_mal_identifies(tableau, operateur) -> str:
    _style()

    recherches = [
        ("Adultes mal id.", "adultes mal"),
        ("Mineurs mal id.", "mineurs mal"),
        ("Flotte mal id.",  "flotte mal"),
        ("M2M mal id.",     "m2m"),
    ]

    # Total de référence
    row_total = _get_row(tableau, "total") or _get_row(tableau, "numéro")
    total_ref = _val(row_total, "Total") or 1

    cats, vals_mal, refs, pcts = [], [], [], []
    for label, key in recherches:
        row = _get_row(tableau, key)
        if row:
            total_cat = _val(row, "Total")
            # Chercher la ligne "population totale" correspondante
            if "adulte" in key or "mineur" in key:
                ref_key = "majeures" if "adulte" in key else "mineures"
                row_ref = _get_row(tableau, ref_key)
                ref = _val(row_ref, "Total") if row_ref else total_cat
            else:
                ref = total_cat * 5  # approximation si pas de ref
            cats.append(label)
            vals_mal.append(total_cat)
            refs.append(ref)
            pcts.append(total_cat / ref * 100 if ref > 0 else 0)

    if not cats:
        return ""

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    fig.patch.set_facecolor(C["fond"])
    x = np.arange(len(cats))

    # Subplot gauche : volumes absolus
    bars1 = ax1.bar(x, vals_mal, color=C["orange"], edgecolor='white',
                    linewidth=1.5, zorder=3)
    ax1.set_xticks(x)
    ax1.set_xticklabels(cats, rotation=15, ha='right')
    ax1.set_title("Nombre absolu de mal-identifiés", pad=12)
    ax1.set_ylabel("Nombre d'abonnés")
    ax1.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda v, _: f"{int(v):,}"))
    for bar, val in zip(bars1, vals_mal):
        if val > 0:
            ax1.text(bar.get_x() + bar.get_width()/2,
                     bar.get_height() + max(vals_mal)*0.01,
                     f"{val:,}", ha='center', va='bottom',
                     fontsize=10, fontweight='bold')

    # Subplot droit : taux (%)
    colors_pct = [C["rouge"] if p > 10 else C["orange"] if p > 5 else C["vert"]
                  for p in pcts]
    bars2 = ax2.bar(x, pcts, color=colors_pct, edgecolor='white',
                    linewidth=1.5, zorder=3)
    ax2.set_xticks(x)
    ax2.set_xticklabels(cats, rotation=15, ha='right')
    ax2.set_title("Taux de mal-identification (%)", pad=12)
    ax2.set_ylabel("Taux (%)")
    ax2.axhline(5,  color=C["orange"], linestyle='--', linewidth=1,
                label="Seuil 5%", alpha=0.7)
    ax2.axhline(10, color=C["rouge"],  linestyle='--', linewidth=1,
                label="Seuil 10%", alpha=0.7)
    ax2.legend(fontsize=9)
    for bar, pct in zip(bars2, pcts):
        ax2.text(bar.get_x() + bar.get_width()/2,
                 bar.get_height() + 0.3,
                 f"{pct:.1f}%", ha='center', va='bottom',
                 fontsize=10, fontweight='bold')

    fig.suptitle(f"[{operateur}] Localisation et quantification des problèmes d'identification",
                 fontsize=13, fontweight='bold', y=1.02)
    fig.tight_layout()
    return _to_b64(fig)


# ── Graphique 3 : Détail champs manquants par catégorie ─────────────────────
def chart_champs_manquants(tableau, operateur) -> str:
    """
    Analyse par segment quels champs obligatoires posent problème.
    Utilise les observations du tableau de synthèse.
    """
    _style()

    segments = []
    for row in tableau:
        obs = str(row.get("Observations", ""))
        ind = str(row.get("Indicateur", ""))
        total = _val(row, "Total")
        if total > 0 and ("champ" in obs.lower() or "manquant" in obs.lower()
                           or "mal" in ind.lower()):
            segments.append({
                "label": ind[:35] + "..." if len(ind) > 35 else ind,
                "total": total,
                "obs"  : obs,
            })

    if not segments:
        # Fallback : affiche tous les indicateurs triés par total décroissant
        segments = sorted(tableau, key=lambda r: _val(r, "Total"), reverse=True)[:8]
        for s in segments:
            s["label"] = str(s.get("Indicateur", ""))[:35]

    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor(C["fond"])

    labels = [s.get("label", str(s.get("Indicateur", "")))[:35] for s in segments]
    vals   = [s.get("total", _val(s, "Total")) for s in segments]

    colors = []
    for v in vals:
        if v > 100000:  colors.append(C["rouge"])
        elif v > 10000: colors.append(C["orange"])
        else:           colors.append(C["bleu"])

    y = np.arange(len(labels))
    bars = ax.barh(y, vals, color=colors, edgecolor='white',
                   linewidth=1.2, height=0.6)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xlabel("Nombre d'abonnés concernés")
    ax.set_title(f"[{operateur}] Volume des anomalies par indicateur", pad=14)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))

    for bar, val in zip(bars, vals):
        ax.text(bar.get_width() + max(vals)*0.005,
                bar.get_y() + bar.get_height()/2,
                f"{val:,}", va='center', fontsize=9, fontweight='bold')

    legende = [
        mpatches.Patch(color=C["rouge"],  label="> 100 000  — Critique"),
        mpatches.Patch(color=C["orange"], label="10 000 – 100 000  — Élevé"),
        mpatches.Patch(color=C["bleu"],   label="< 10 000  — Modéré"),
    ]
    ax.legend(handles=legende, loc='lower right', fontsize=9)
    ax.invert_yaxis()
    fig.tight_layout()
    return _to_b64(fig)


# ── Graphique 4 : Répartition Majeurs / Mineurs ──────────────────────────────
def chart_age_distribution(tableau, operateur) -> str:
    _style()
    row_maj = _get_row(tableau, "majeur") or _get_row(tableau, "physiques majeures")
    row_min = _get_row(tableau, "mineur") or _get_row(tableau, "physiques mineures")
    maj = _val(row_maj, "Total")
    min_ = _val(row_min, "Total")
    if maj + min_ == 0:
        return ""

    fig, ax = plt.subplots(figsize=(7, 5))
    fig.patch.set_facecolor(C["fond"])
    total = maj + min_

    vals   = [maj, min_]
    colors = [C["bleu"], C["violet"]]
    labels = [
        f"Majeurs\n{maj:,}  ({maj/total:.1%})",
        f"Mineurs\n{min_:,}  ({min_/total:.1%})"
    ]

    wedges, _, autotexts = ax.pie(
        vals, colors=colors, autopct='%1.1f%%',
        startangle=90, explode=(0.03, 0.06),
        pctdistance=0.78, wedgeprops=dict(linewidth=2, edgecolor='white')
    )
    for at in autotexts:
        at.set_fontsize(12)
        at.set_fontweight('bold')
        at.set_color('white')

    centre = plt.Circle((0, 0), 0.55, fc='white')
    ax.add_artist(centre)
    ax.text(0, 0, f"{total:,}\nPhysiques", ha='center', va='center',
            fontsize=12, fontweight='bold', color=C["texte"])

    ax.legend(wedges, labels, loc='lower center',
              bbox_to_anchor=(0.5, -0.1), ncol=2, frameon=False, fontsize=10)
    ax.set_title(f"[{operateur}] Répartition Majeurs / Mineurs", pad=14)
    fig.tight_layout()
    return _to_b64(fig)


# ── Graphique 5 : Pièces expirées + Multi-utilisation ────────────────────────
def chart_risques(tableau, operateur) -> str:
    _style()

    row_exp  = _get_row(tableau, "expir")
    row_maj3 = _get_row(tableau, "pièce") or _get_row(tableau, "id_number")
    row_min3 = _get_row(tableau, "mineurs — id") or _get_row(tableau, "mineur") 

    exp   = _val(row_exp,  "Total")
    maj3  = _val(row_maj3, "Total")
    min3  = _val(row_min3, "Total")

    if exp + maj3 + min3 == 0:
        return ""

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.patch.set_facecolor(C["fond"])

    # Gauche : pièces expirées
    ax1 = axes[0]
    ax1.bar(["Pièces expirées\n≥ 6 mois"], [exp],
            color=C["rouge"], edgecolor='white', linewidth=1.5, width=0.5)
    ax1.text(0, exp + max(exp, 1)*0.03, f"{exp:,}",
             ha='center', fontsize=13, fontweight='bold', color=C["texte"])
    ax1.set_title("Pièces d'identité expirées", pad=12)
    ax1.set_ylabel("Nombre d'abonnés")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax1.set_ylim(0, max(exp, 1) * 1.2)

    # Droite : ID utilisé > 3 fois (risque fraude)
    ax2 = axes[1]
    labels = ["Majeurs\n(ID > 3×)", "Mineurs\n(ID > 3×)"]
    vals   = [maj3, min3]
    colors = [C["orange"], C["violet"]]
    bars2  = ax2.bar(labels, vals, color=colors, edgecolor='white',
                     linewidth=1.5, width=0.4)
    ax2.set_title("Pièces utilisées > 3 fois\n(Risque fraude)", pad=12)
    ax2.set_ylabel("Nombre d'abonnés")
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax2.set_ylim(0, max(max(vals), 1) * 1.25)
    for bar, val in zip(bars2, vals):
        ax2.text(bar.get_x() + bar.get_width()/2,
                 bar.get_height() + max(vals)*0.02,
                 f"{val:,}", ha='center', fontsize=12, fontweight='bold')

    fig.suptitle(f"[{operateur}] Indicateurs de risque — Conformité & Fraude",
                 fontsize=13, fontweight='bold')
    fig.tight_layout()
    return _to_b64(fig)


# ── Graphique 6 : Cohérence HLR ↔ Source (taux par catégorie) ───────────────
def chart_coherence(tableau, operateur) -> str:
    _style()

    cibles = [
        ("Actifs",    "actifs",    C["vert"]),
        ("Suspendus", "suspendus", C["rouge"]),
        ("Flotte",    "flotte",    C["bleu"]),
        ("M2M",       "m2m",       C["violet"]),
    ]

    cats, taux_ok, taux_ko = [], [], []
    for label, key, _ in cibles:
        row = _get_row(tableau, key)
        if not row:
            continue
        total = _val(row, "Total")
        mal   = 0
        obs   = str(row.get("Observations", ""))
        # Tente d'extraire le nb d'incohérents depuis Observations
        import re
        m = re.search(r'(\d[\d\s,]+)\s*/\s*[\d\s,]+', obs.replace(' ', ''))
        if m:
            try:
                mal = int(m.group(1).replace(',', ''))
            except:
                pass
        if total > 0:
            taux_ko.append(mal / total * 100)
            taux_ok.append((total - mal) / total * 100)
            cats.append(label)

    if not cats:
        return ""

    fig, ax = plt.subplots(figsize=(9, 5))
    fig.patch.set_facecolor(C["fond"])
    x = np.arange(len(cats))
    w = 0.35

    b1 = ax.bar(x - w/2, taux_ok, w, label="Cohérents (%)",
                color=C["vert"], edgecolor='white', linewidth=1.2)
    b2 = ax.bar(x + w/2, taux_ko, w, label="Incohérents (%)",
                color=C["rouge"], edgecolor='white', linewidth=1.2)

    ax.set_xticks(x)
    ax.set_xticklabels(cats)
    ax.set_ylabel("Taux (%)")
    ax.set_ylim(0, 110)
    ax.axhline(95, color=C["bleu"], linestyle='--', linewidth=1,
               alpha=0.6, label="Seuil qualité 95%")
    ax.set_title(f"[{operateur}] Taux de cohérence HLR ↔ Source par catégorie", pad=14)
    ax.legend(fontsize=10)

    for bar, val in zip(list(b1) + list(b2), taux_ok + taux_ko):
        if val > 1:
            ax.text(bar.get_x() + bar.get_width()/2,
                    bar.get_height() + 1,
                    f"{val:.1f}%", ha='center', va='bottom', fontsize=9)

    fig.tight_layout()
    return _to_b64(fig)


# ── Fonction principale : génère tous les graphiques ─────────────────────────
def generer_tous_graphiques(resultats: dict) -> dict:
    """
    Reçoit le dict de résultats de analyzer.py.
    Retourne un dict {nom_chart: base64_string}.
    """
    tableau   = resultats.get("tableau", [])
    operateur = resultats.get("operateur", "")

    if not tableau:
        return {}

    charts = {}
    try:
        charts["hlr_donut"]       = chart_hlr_donut(tableau, operateur)
        charts["mal_identifies"]  = chart_mal_identifies(tableau, operateur)
        charts["champs_manquants"]= chart_champs_manquants(tableau, operateur)
        charts["age_distribution"]= chart_age_distribution(tableau, operateur)
        charts["risques"]         = chart_risques(tableau, operateur)
        charts["coherence"]       = chart_coherence(tableau, operateur)
    except Exception as e:
        charts["erreur"] = str(e)

    return charts
