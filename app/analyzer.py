"""
analyzer.py v2
- Exécute l'analyse dans un thread séparé
- Stream les logs via SSE en temps réel
- Libère la mémoire après chaque étape
- N'appelle chaque fonction qu'une seule fois
"""
import sys, os, gc, io, csv, json, threading, queue
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ── File de messages SSE ──────────────────────────────────────────────────────
_analyse_queue   : queue.Queue = queue.Queue()
_analyse_resultats : dict       = {}
_analyse_en_cours  : bool       = False


def get_queue():
    return _analyse_queue


def get_resultats():
    return _analyse_resultats


def est_en_cours():
    return _analyse_en_cours


# ── Logger qui écrit dans la queue SSE ───────────────────────────────────────
class QueueLogger:
    """Redirige stdout vers la queue SSE."""
    def __init__(self, q: queue.Queue, original):
        self.q        = q
        self.original = original
        self.buf      = ""

    def write(self, text):
        self.original.write(text)
        self.original.flush()
        self.buf += text
        # Envoie ligne par ligne
        while '\n' in self.buf:
            line, self.buf = self.buf.split('\n', 1)
            line = line.strip()
            if line:
                self.q.put({"type": "log", "msg": line})

    def flush(self):
        self.original.flush()


# ── Analyse dans un thread ────────────────────────────────────────────────────
def lancer_analyse_thread(chemin: str, operateur: str):
    global _analyse_en_cours, _analyse_resultats

    _analyse_en_cours = True
    _analyse_resultats = {}

    # Vide la queue
    while not _analyse_queue.empty():
        try: _analyse_queue.get_nowait()
        except: pass

    t = threading.Thread(
        target=_run_analyse,
        args=(chemin, operateur),
        daemon=True
    )
    t.start()


def _emit(msg: str, niveau: str = "info"):
    _analyse_queue.put({"type": "log", "msg": msg, "niveau": niveau})


def _etape(texte: str):
    _analyse_queue.put({"type": "etape", "msg": texte})


def _run_analyse(chemin: str, operateur: str):
    global _analyse_en_cours, _analyse_resultats

    orig_stdout = sys.stdout
    sys.stdout  = QueueLogger(_analyse_queue, orig_stdout)

    try:
        resultats = {
            "operateur"     : operateur.upper(),
            "chemin"        : chemin,
            "date_analyse"  : datetime.now().strftime("%d/%m/%Y %H:%M"),
            "fichiers"      : [],
            "tableau"       : [],
            "ventilation_majeur": [],
            "ventilation_mineur": [],
            "ventilation_tous"  : [],
            "total_abonnes" : 0,
            "total_actifs"  : 0,
            "total_suspendus": 0,
            "erreur"        : None,
        }

        # ── ÉTAPE 1 : Chargement ─────────────────────────────────────────────
        _etape("Chargement des fichiers…")
        from loader import DataLoader
        loader = DataLoader(chemin)
        data   = loader.load_data()

        if not data:
            _analyse_queue.put({"type": "erreur", "msg": "Aucun fichier chargé."})
            return

        resultats["fichiers"] = list(data.keys())
        _emit(f"{len(data)} fichier(s) chargé(s) : {', '.join(data.keys())}", "ok")

        # ── ÉTAPE 2 : Analyse ────────────────────────────────────────────────
        _etape("Analyse en cours…")

        if operateur.lower() == "orange":
            _emit("Opérateur : ORANGE")
            from functions import StatisticFunction
            sf = StatisticFunction(data)

            _etape("Génération du tableau de synthèse…")
            df_synthese = sf.func_generate_tableau_synthese()
            resultats["tableau"] = df_synthese.to_dicts() if df_synthese.height > 0 else []
            del df_synthese; gc.collect()

            _etape("Ventilation par type de pièce…")
            try:
                df_maj = sf.func_nb_physique_par_type_piece(age_filtre="majeur")
                df_min = sf.func_nb_physique_par_type_piece(age_filtre="mineur")
                df_all = sf.func_nb_physique_par_type_piece(age_filtre="tous")
                resultats["ventilation_majeur"] = df_maj.to_dicts()
                resultats["ventilation_mineur"] = df_min.to_dicts()
                resultats["ventilation_tous"]   = df_all.to_dicts()
                del df_maj, df_min, df_all; gc.collect()
            except Exception as e:
                _emit(f"Ventilation ignorée : {e}", "warn")

            del sf; gc.collect()

        elif operateur.lower() == "mtn":
            _emit("Opérateur : MTN")
            from functions_MTN import StatisticFunction_MTN
            mois = _detecter_mois(list(data.keys()))
            _emit(f"Période détectée : {mois}")
            sf = StatisticFunction_MTN(data, mois=mois, hlr_prefix_len=0)

            _etape("Génération du tableau de synthèse…")
            df_synthese = sf.func_generate_tableau_synthese()
            resultats["tableau"] = df_synthese.to_dicts() if df_synthese.height > 0 else []
            resultats["mois"]    = mois
            del df_synthese; gc.collect()

            _etape("Ventilation par type de pièce…")
            try:
                df_maj = sf.func_nb_physique_par_type_piece(age_filtre="majeur")
                df_min = sf.func_nb_physique_par_type_piece(age_filtre="mineur")
                df_all = sf.func_nb_physique_par_type_piece(age_filtre="tous")
                resultats["ventilation_majeur"] = df_maj.to_dicts()
                resultats["ventilation_mineur"] = df_min.to_dicts()
                resultats["ventilation_tous"]   = df_all.to_dicts()
                del df_maj, df_min, df_all; gc.collect()
            except Exception as e:
                _emit(f"Ventilation ignorée : {e}", "warn")

            del sf; gc.collect()

        # Libère les données brutes
        del data; gc.collect()

        # ── ÉTAPE 3 : Extraction des KPI ─────────────────────────────────────
        _etape("Extraction des KPI…")
        for row in resultats["tableau"]:
            ind = str(row.get("Indicateur", "")).lower()
            if "total" in ind or "numéro" in ind or "numero" in ind:
                resultats["total_abonnes"]   = int(row.get("Total", 0) or 0)
                resultats["total_actifs"]    = int(row.get("Actifs", 0) or 0)
                resultats["total_suspendus"] = int(
                    row.get("Suspendus") or row.get("Susp. Sortant") or 0
                )
                break

        _analyse_resultats = resultats
        _analyse_queue.put({"type": "termine", "msg": "Analyse terminée avec succès."})

    except Exception as e:
        import traceback
        msg = f"{e}\n{traceback.format_exc()}"
        _analyse_queue.put({"type": "erreur", "msg": msg})

    finally:
        sys.stdout      = orig_stdout
        _analyse_en_cours = False


def _detecter_mois(noms: list) -> str:
    import re
    for n in noms:
        m = re.search(r'(20\d{2}[A-Z]{3})', n.upper())
        if m: return m.group(1)
    return "2026JAN"


# ── Export CSV ────────────────────────────────────────────────────────────────
def resultats_vers_csv(resultats: dict) -> str:
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow(["Date analyse", "Opérateur", "Indicateur",
                     "Actifs", "Suspendus", "Total", "Observations"])
    date_a = resultats.get("date_analyse", "")
    op     = resultats.get("operateur", "")
    for row in resultats.get("tableau", []):
        writer.writerow([
            date_a, op,
            row.get("Indicateur", ""),
            row.get("Actifs", ""),
            row.get("Suspendus") or row.get("Susp. Sortant", ""),
            row.get("Total", ""),
            str(row.get("Observations", "")).replace("\n", " | "),
        ])
    output.seek(0)
    return '\ufeff' + output.getvalue()
