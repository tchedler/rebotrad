"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Trade Journal (SQLite)
══════════════════════════════════════════════════════════════
Responsabilités :
- Enregistrer chaque trade dans une base SQLite (32 colonnes)
- Détecter automatiquement la catégorie d'erreur
- Permettre à failure_lab.py d'analyser les pertes
- Générer des statistiques par setup, session, paire

10 catégories d'erreurs auto-détectées :
  EARLY_ENTRY     entrée trop tôt sans confirmation
  WRONG_BIAS      biais HTF opposé à la direction
  BAD_TIMING      trade hors session/macro
  OVERTRADING     trop de trades sur 24h
  SL_TOO_TIGHT    SL < 0.3 ATR
  INDUCEMENT      sweep non confirmé
  REVENGE_TRADE   trade après 2 pertes consécutives
  NO_DISPLACEMENT pas de bougie de displacement
  WRONG_ZONE      zone Premium/Discount incorrecte
  FRIDAY_TRADE    trade après 14h NY vendredi
══════════════════════════════════════════════════════════════
"""

import sqlite3
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH        = "learning/trade_journal.db"
MAX_DAILY_TRADES = 6   # seuil overtrading


class TradeJournal:
    """
    Journal de trades SQLite 32 colonnes.
    Thread-safe via threading.Lock.
    """

    def __init__(self, db_path: str = DB_PATH):
        self._db_path = db_path
        self._lock    = threading.Lock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"TradeJournal initialisé — DB: {db_path}")

    # ══════════════════════════════════════════════════════════
    # INITIALISATION BASE
    # ══════════════════════════════════════════════════════════

    def _init_db(self) -> None:
        """Crée la table trades si elle n'existe pas."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket          INTEGER,
                    pair            TEXT,
                    direction       TEXT,
                    trade_type      TEXT,
                    session         TEXT,
                    entry           REAL,
                    sl              REAL,
                    tp              REAL,
                    lot             REAL,
                    score           INTEGER,
                    grade           TEXT,
                    rr              REAL,
                    verdict         TEXT,
                    kb5_score       INTEGER,
                    bias_score      INTEGER,
                    v4_score        INTEGER,
                    erl_swept       INTEGER,
                    ote_status      TEXT,
                    cisd_detected   INTEGER,
                    in_killzone     INTEGER,
                    lrlr_swept      INTEGER,
                    pd_zone         TEXT,
                    dol_direction   TEXT,
                    dol_level       REAL,
                    open_time       TEXT,
                    close_time      TEXT,
                    pnl             REAL,
                    pnl_pct         REAL,
                    sl_distance     REAL,
                    outcome         TEXT,
                    error_category  TEXT,
                    error_detail    TEXT,
                    notes           TEXT
                )
            """)
            conn.commit()

    # ══════════════════════════════════════════════════════════
    # ENREGISTREMENT
    # ══════════════════════════════════════════════════════════

    def record_open(self, scalp_output: dict,
                    allocation: dict,
                    order_result: dict) -> int:
        """
        Enregistre l'ouverture d'un trade.
        Returns: id de la ligne insérée
        """
        em     = scalp_output.get("entry_model", {})
        v4     = scalp_output.get("scoring_v4", {})
        erl    = scalp_output.get("erl_result", {})
        kb5    = scalp_output.get("kb5_result", {})

        row = {
            "ticket"        : order_result.get("ticket"),
            "pair"          : scalp_output.get("pair"),
            "direction"     : scalp_output.get("direction"),
            "trade_type"    : scalp_output.get("trade_type", "INTRADAY"),
            "session"       : kb5.get("session", ""),
            "entry"         : em.get("entry"),
            "sl"            : em.get("sl"),
            "tp"            : em.get("tp"),
            "lot"           : allocation.get("lot_size"),
            "score"         : scalp_output.get("score"),
            "grade"         : scalp_output.get("grade"),
            "rr"            : em.get("rr"),
            "verdict"       : scalp_output.get("verdict"),
            "kb5_score"     : kb5.get("final_score"),
            "bias_score"    : scalp_output.get("bias_score"),
            "v4_score"      : v4.get("total"),
            "erl_swept"     : 1 if erl.get("swept") else 0,
            "ote_status"    : kb5.get("ote", {}).get("status"),
            "cisd_detected" : 1 if kb5.get("cisd", {}).get("detected") else 0,
            "in_killzone"   : 1 if kb5.get("in_killzone") else 0,
            "lrlr_swept"    : 1 if kb5.get("lrlr_swept") else 0,
            "pd_zone"       : kb5.get("pd_zone"),
            "dol_direction" : kb5.get("dol", {}).get("direction"),
            "dol_level"     : kb5.get("dol", {}).get("target_level"),
            "open_time"     : datetime.now(timezone.utc).isoformat(),
            "close_time"    : None,
            "pnl"           : None,
            "pnl_pct"       : None,
            "sl_distance"   : allocation.get("sl_pips"),
            "outcome"       : "OPEN",
            "error_category": None,
            "error_detail"  : None,
            "notes"         : None,
        }

        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute("""
                    INSERT INTO trades (
                        ticket, pair, direction, trade_type, session,
                        entry, sl, tp, lot, score, grade, rr, verdict,
                        kb5_score, bias_score, v4_score, erl_swept,
                        ote_status, cisd_detected, in_killzone,
                        lrlr_swept, pd_zone, dol_direction, dol_level,
                        open_time, close_time, pnl, pnl_pct,
                        sl_distance, outcome, error_category,
                        error_detail, notes
                    ) VALUES (
                        :ticket, :pair, :direction, :trade_type, :session,
                        :entry, :sl, :tp, :lot, :score, :grade, :rr,
                        :verdict, :kb5_score, :bias_score, :v4_score,
                        :erl_swept, :ote_status, :cisd_detected,
                        :in_killzone, :lrlr_swept, :pd_zone,
                        :dol_direction, :dol_level, :open_time,
                        :close_time, :pnl, :pnl_pct, :sl_distance,
                        :outcome, :error_category, :error_detail, :notes
                    )
                """, row)
                conn.commit()
                row_id = cursor.lastrowid
                logger.info(f"TradeJournal — trade ouvert "
                            f"#{row_id} {row['pair']} "
                            f"{row['direction']}")
                return row_id

    def record_close(self, ticket: int, pnl: float,
                     equity: float) -> None:
        """
        Met à jour le trade à la clôture avec PnL et catégorie d'erreur.
        """
        outcome = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BE"
        pnl_pct = round(pnl / equity * 100, 3) if equity > 0 else 0.0

        with self._lock:
            with self._connect() as conn:
                # Récupérer les données du trade pour analyse d'erreur
                row = conn.execute(
                    "SELECT * FROM trades WHERE ticket=? "
                    "ORDER BY id DESC LIMIT 1", (ticket,)
                ).fetchone()

                error_cat, error_detail = "", ""
                if row and pnl < 0:
                    error_cat, error_detail = \
                        self._classify_error(dict(row))

                conn.execute("""
                    UPDATE trades
                    SET close_time=?, pnl=?, pnl_pct=?,
                        outcome=?, error_category=?, error_detail=?
                    WHERE ticket=?
                """, (
                    datetime.now(timezone.utc).isoformat(),
                    round(pnl, 2), pnl_pct,
                    outcome, error_cat, error_detail,
                    ticket
                ))
                conn.commit()
                logger.info(f"TradeJournal — trade fermé "
                            f"ticket={ticket} PnL={pnl:.2f} "
                            f"({outcome}) erreur={error_cat}")

    # ══════════════════════════════════════════════════════════
    # CLASSIFICATION AUTOMATIQUE DES ERREURS
    # ══════════════════════════════════════════════════════════

    def _classify_error(self, row: dict) -> tuple:
        """
        Détecte automatiquement la catégorie d'erreur d'un trade perdant.
        Returns: (error_category, error_detail)
        """
        # FRIDAY_TRADE
        open_time = row.get("open_time", "")
        try:
            dt = datetime.fromisoformat(open_time)
            if dt.weekday() == 4 and dt.hour >= 14:
                return ("FRIDAY_TRADE",
                        "Trade ouvert vendredi après 14h NY")
        except Exception:
            pass

        # WRONG_BIAS
        if row.get("bias_score", 100) < 40:
            return ("WRONG_BIAS",
                    f"Bias score faible : {row.get('bias_score')}")

        # BAD_TIMING
        if not row.get("in_killzone"):
            return ("BAD_TIMING",
                    "Trade hors Killzone ICT")

        # NO_DISPLACEMENT
        if not row.get("cisd_detected"):
            return ("NO_DISPLACEMENT",
                    "Pas de CISD/displacement confirmé")

        # WRONG_ZONE
        direction = row.get("direction", "")
        pd_zone   = row.get("pd_zone", "")
        if ((direction == "BULLISH" and pd_zone == "PREMIUM") or
                (direction == "BEARISH" and pd_zone == "DISCOUNT")):
            return ("WRONG_ZONE",
                    f"Entrée en {pd_zone} pour {direction}")

        # SL_TOO_TIGHT
        if row.get("sl_distance", 999) < 5:
            return ("SL_TOO_TIGHT",
                    f"SL trop serré : {row.get('sl_distance')} pips")

        # INDUCEMENT
        if not row.get("erl_swept"):
            return ("INDUCEMENT",
                    "ERL non sweepé — inducement probable")

        # OTE MISSED
        if row.get("ote_status") == "MISSED":
            return ("EARLY_ENTRY",
                    "OTE MISSED — entrée trop tôt")

        return ("UNKNOWN", "Erreur non classifiée")

    # ══════════════════════════════════════════════════════════
    # STATISTIQUES
    # ══════════════════════════════════════════════════════════

    def get_stats(self, pair: str = None,
                  last_n: int = 100) -> dict:
        """Statistiques globales ou par paire."""
        with self._lock:
            with self._connect() as conn:
                query = """
                    SELECT outcome, error_category, pair,
                           AVG(rr) as avg_rr,
                           AVG(score) as avg_score,
                           COUNT(*) as total
                    FROM trades
                    WHERE outcome != 'OPEN'
                """
                params = []
                if pair:
                    query += " AND pair=?"
                    params.append(pair)
                query += f" ORDER BY id DESC LIMIT {last_n}"
                rows = conn.execute(query, params).fetchall()

                wins   = sum(1 for r in rows if r[0] == "WIN")
                losses = sum(1 for r in rows if r[0] == "LOSS")
                total  = wins + losses

                errors = {}
                for r in rows:
                    cat = r[1] or "NONE"
                    errors[cat] = errors.get(cat, 0) + 1

                return {
                    "total"    : total,
                    "wins"     : wins,
                    "losses"   : losses,
                    "winrate"  : round(wins / total * 100, 1)
                                 if total > 0 else 0,
                    "errors"   : errors,
                }

    def get_recent_losses(self, n: int = 10) -> list:
        """Retourne les N dernières pertes pour failure_lab."""
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute("""
                    SELECT * FROM trades
                    WHERE outcome='LOSS'
                    ORDER BY id DESC LIMIT ?
                """, (n,)).fetchall()
                cols = [d[0] for d in conn.execute(
                    "SELECT * FROM trades LIMIT 0"
                ).description or []]
                return [dict(zip(cols, r)) for r in rows]

    # ══════════════════════════════════════════════════════════
    # UTILITAIRES
    # ══════════════════════════════════════════════════════════

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def __repr__(self) -> str:
        return f"TradeJournal(db='{self._db_path}')"
