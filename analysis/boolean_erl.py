"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Boolean ERL Gate (§0 Absolu)
══════════════════════════════════════════════════════════════
Règle ICT fondamentale :
Si le marché n'a PAS encore purgé un External Range Liquidity
dans la direction du trade → score plafonné à 44/100
→ trade IMPOSSIBLE peu importe le reste du scoring.

ERL = niveau de liquidité externe non encore sweepé :
  BULLISH → ERL = Equal Lows / PDL / Weekly Low non purgés
  BEARISH → ERL = Equal Highs / PDH / Weekly High non purgés
══════════════════════════════════════════════════════════════
"""

import logging
from datetime import datetime, timezone
from datastore.data_store import DataStore

logger = logging.getLogger(__name__)

# Gate absolu : si ERL non sweepé → score plafonné à cette valeur
ERL_GATE_CAP   = 44
ERL_SWEEP_PIPS = 0.0002  # distance minimale pour confirmer un sweep (2 pips)


class BooleanERL:
    """
    Gate §0 — Vérifie si un ERL a été purgé dans la direction du trade.
    Consommé par scoring_engine AVANT tout calcul de score final.
    """

    def __init__(self, datastore: DataStore, liquidity_detector=None):
        self._ds  = datastore
        self._liq = liquidity_detector
        logger.info("BooleanERL initialisé — Gate §0 prêt")

    # ══════════════════════════════════════════════════════════
    # MÉTHODE PRINCIPALE
    # ══════════════════════════════════════════════════════════

    def check(self, pair: str, direction: str) -> dict:
        """
        Vérifie si un ERL a été sweepé dans la direction du trade.

        Returns:
            dict {
                swept      : bool,   # True = ERL purgé → trade autorisé
                erl_level  : float,  # niveau ERL détecté
                erl_type   : str,    # PDH/PDL/EQH/EQL/WeeklyH/WeeklyL
                score_cap  : int,    # 44 si non sweepé, 100 si sweepé
                reason     : str     # explication lisible
            }
        """
        try:
            swept, erl_level, erl_type = self._detect_sweep(pair, direction)
        except Exception as e:
            logger.error(f"BooleanERL — erreur détection {pair} : {e}")
            # Fail-open : ne pas bloquer si erreur technique
            return self._result(True, 0.0, "UNKNOWN",
                                "Fail-open — erreur détection ERL")

        if swept:
            logger.debug(f"BooleanERL {pair} — ERL {erl_type} "
                         f"sweepé à {erl_level} ✅")
            return self._result(True, erl_level, erl_type,
                                f"ERL {erl_type} purgé — trade autorisé")
        else:
            logger.info(f"BooleanERL {pair} — ERL {erl_type} "
                        f"NON sweepé → score plafonné à {ERL_GATE_CAP}")
            return self._result(False, erl_level, erl_type,
                                f"ERL {erl_type} non purgé — "
                                f"score plafonné à {ERL_GATE_CAP}")

    # ══════════════════════════════════════════════════════════
    # DÉTECTION DU SWEEP
    # ══════════════════════════════════════════════════════════

    def _detect_sweep(self, pair: str,
                      direction: str) -> tuple:
        """
        Détecte si un ERL a été sweepé dans la direction du trade.

        Priorité de détection :
        1. LiquidityDetector (si disponible)
        2. PDH/PDL depuis les bougies D1
        3. Equal Highs/Lows depuis H4

        Returns:
            tuple (swept: bool, level: float, erl_type: str)
        """
        # ── Priorité 1 : LiquidityDetector ──────────────────
        if self._liq is not None:
            try:
                sweeps = self._liq.get_sweeps(
                    pair, status="FRESH", direction=direction
                )
                if sweeps:
                    best = sweeps[0]
                    return True, best.get("pool_level", 0.0), \
                           best.get("pool_type", "ERL")
            except Exception as e:
                logger.warning(f"BooleanERL — LiquidityDetector {pair} : {e}")

        # ── Priorité 2 : PDH/PDL depuis D1 ──────────────────
        df_d1 = self._ds.get_candles(pair, "D1")
        if df_d1 is not None and len(df_d1) >= 3:
            current_price = float(df_d1["close"].iloc[-1])

            if direction == "BULLISH":
                # ERL BULLISH = PDL non sweepé sous le prix actuel
                pdl = float(df_d1["low"].iloc[-3:-1].min())
                swept = current_price < (pdl - ERL_SWEEP_PIPS)
                return swept, pdl, "PDL_D1"

            else:  # BEARISH
                # ERL BEARISH = PDH non sweepé au-dessus du prix actuel
                pdh = float(df_d1["high"].iloc[-3:-1].max())
                swept = current_price > (pdh + ERL_SWEEP_PIPS)
                return swept, pdh, "PDH_D1"

        # ── Priorité 3 : Equal H/L depuis H4 ────────────────
        df_h4 = self._ds.get_candles(pair, "H4")
        if df_h4 is not None and len(df_h4) >= 10:
            current_price = float(df_h4["close"].iloc[-1])

            if direction == "BULLISH":
                eql = float(df_h4["low"].iloc[-10:-1].min())
                swept = current_price < (eql - ERL_SWEEP_PIPS)
                return swept, eql, "EQL_H4"
            else:
                eqh = float(df_h4["high"].iloc[-10:-1].max())
                swept = current_price > (eqh + ERL_SWEEP_PIPS)
                return swept, eqh, "EQH_H4"

        # Fail-open si aucune donnée disponible
        return True, 0.0, "NO_DATA"

    # ══════════════════════════════════════════════════════════
    # UTILITAIRES
    # ══════════════════════════════════════════════════════════

    def _result(self, swept: bool, level: float,
                erl_type: str, reason: str) -> dict:
        return {
            "swept"     : swept,
            "erl_level" : round(level, 6),
            "erl_type"  : erl_type,
            "score_cap" : 100 if swept else ERL_GATE_CAP,
            "reason"    : reason,
            "timestamp" : datetime.now(timezone.utc).isoformat(),
        }

    def apply_gate(self, score: int, erl_result: dict) -> int:
        """
        Applique le plafond ERL sur le score final.
        Appelé par scoring_engine après calcul du score brut.

        Returns:
            int score plafonné si ERL non sweepé
        """
        if not erl_result.get("swept", True):
            capped = min(score, ERL_GATE_CAP)
            if capped < score:
                logger.info(f"BooleanERL Gate appliqué — "
                            f"score {score} → {capped}")
            return capped
        return score

    def __repr__(self) -> str:
        return "BooleanERL(gate=§0, cap=44)"
