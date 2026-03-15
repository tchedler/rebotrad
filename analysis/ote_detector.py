"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — OTE Detector (Optimal Trade Entry)
══════════════════════════════════════════════════════════════
Concept ICT :
L'OTE est la zone Fibonacci 62%-79% d'un swing HTF.
C'est la zone où les institutions placent leurs ordres
après un displacement / MSS confirmé.

Règles :
- BULLISH : swing Low → High, retrace 62-79% → zone d'achat
- BEARISH : swing High → Low, retrace 62-79% → zone de vente
- Statuts : WAITING (prix pas encore en zone)
            INSIDE  (prix dans la zone OTE)
            MISSED  (prix a dépassé la zone sans entrée)
══════════════════════════════════════════════════════════════
"""

import logging
import numpy as np
from datetime import datetime, timezone
from datastore.data_store import DataStore

logger = logging.getLogger(__name__)

# Niveaux Fibonacci OTE ICT
OTE_LOW  = 0.62   # 62% retracement
OTE_HIGH = 0.79   # 79% retracement
OTE_PREMIUM_ENTRY = 0.705  # niveau idéal (70.5%)

# Lookback pour détecter le swing HTF
SWING_LOOKBACK_H4  = 20   # bougies H4
SWING_LOOKBACK_H1  = 30   # bougies H1


class OTEDetector:
    """
    Détecte la zone OTE ICT (62-79% Fibonacci) sur H4 et H1.
    Produit un OTE_RESULT consommé par kb5_engine et scoring_engine.
    """

    def __init__(self, datastore: DataStore):
        self._ds = datastore
        logger.info("OTEDetector initialisé — zone 62-79% Fibo prêt")

    # ══════════════════════════════════════════════════════════
    # MÉTHODE PRINCIPALE
    # ══════════════════════════════════════════════════════════

    def check(self, pair: str, direction: str) -> dict:
        """
        Vérifie si le prix est dans la zone OTE pour la direction donnée.

        Returns:
            dict {
                status      : WAITING / INSIDE / MISSED / NO_SWING,
                ote_low     : float,  # bas de la zone OTE
                ote_high    : float,  # haut de la zone OTE
                ideal_entry : float,  # niveau 70.5%
                swing_high  : float,
                swing_low   : float,
                tf          : str,    # H4 ou H1
                in_zone     : bool,   # True si prix dans OTE
                distance    : float,  # distance au niveau idéal
            }
        """
        # Essayer H4 d'abord, puis H1 en fallback
        for tf, lookback in [("H4", SWING_LOOKBACK_H4),
                             ("H1", SWING_LOOKBACK_H1)]:
            result = self._check_tf(pair, direction, tf, lookback)
            if result["status"] != "NO_SWING":
                return result

        return self._empty_result("NO_SWING", "Aucun swing détecté")

    # ══════════════════════════════════════════════════════════
    # DÉTECTION PAR TF
    # ══════════════════════════════════════════════════════════

    def _check_tf(self, pair: str, direction: str,
                  tf: str, lookback: int) -> dict:
        """Calcule la zone OTE sur un TF donné."""
        df = self._ds.get_candles(pair, tf)
        if df is None or len(df) < lookback:
            return self._empty_result("NO_SWING", f"{tf} insuffisant")

        highs = df["high"].values[-lookback:]
        lows  = df["low"].values[-lookback:]
        current_price = float(df["close"].iloc[-1])

        if direction == "BULLISH":
            # Swing : Low → High (retrace vers le bas)
            swing_low  = float(np.min(lows))
            swing_high = float(np.max(highs[np.argmin(lows):]))

            if swing_high <= swing_low:
                return self._empty_result("NO_SWING", "Swing BULL invalide")

            swing_range = swing_high - swing_low
            ote_high = round(swing_high - (OTE_LOW  * swing_range), 6)
            ote_low  = round(swing_high - (OTE_HIGH * swing_range), 6)
            ideal    = round(swing_high - (OTE_PREMIUM_ENTRY * swing_range), 6)

        else:  # BEARISH
            # Swing : High → Low (retrace vers le haut)
            swing_high = float(np.max(highs))
            swing_low  = float(np.min(lows[np.argmax(highs):]))

            if swing_low >= swing_high:
                return self._empty_result("NO_SWING", "Swing BEAR invalide")

            swing_range = swing_high - swing_low
            ote_low  = round(swing_low + (OTE_LOW  * swing_range), 6)
            ote_high = round(swing_low + (OTE_HIGH * swing_range), 6)
            ideal    = round(swing_low + (OTE_PREMIUM_ENTRY * swing_range), 6)

        # Déterminer le statut
        in_zone = ote_low <= current_price <= ote_high

        if in_zone:
            status = "INSIDE"
        elif direction == "BULLISH" and current_price > ote_high:
            status = "MISSED"
        elif direction == "BEARISH" and current_price < ote_low:
            status = "MISSED"
        else:
            status = "WAITING"

        distance = round(abs(current_price - ideal), 6)

        logger.debug(f"OTE {pair} {tf} {direction} — "
                     f"Zone [{ote_low} → {ote_high}] "
                     f"Prix {current_price} → {status}")

        return {
            "status"      : status,
            "ote_low"     : ote_low,
            "ote_high"    : ote_high,
            "ideal_entry" : ideal,
            "swing_high"  : round(swing_high, 6),
            "swing_low"   : round(swing_low, 6),
            "tf"          : tf,
            "in_zone"     : in_zone,
            "distance"    : distance,
            "current"     : round(current_price, 6),
            "timestamp"   : datetime.now(timezone.utc).isoformat(),
        }

    # ══════════════════════════════════════════════════════════
    # BONUS SCORING
    # ══════════════════════════════════════════════════════════

    def get_score_bonus(self, pair: str, direction: str) -> int:
        """
        Retourne le bonus de score OTE pour kb5_engine.
        INSIDE  → +10 pts
        WAITING → +5  pts (zone proche)
        MISSED  →  0  pts
        """
        result = self.check(pair, direction)
        bonuses = {"INSIDE": 10, "WAITING": 5, "MISSED": 0, "NO_SWING": 0}
        return bonuses.get(result["status"], 0)

    # ══════════════════════════════════════════════════════════
    # UTILITAIRES
    # ══════════════════════════════════════════════════════════

    def _empty_result(self, status: str, reason: str) -> dict:
        return {
            "status"      : status,
            "ote_low"     : 0.0,
            "ote_high"    : 0.0,
            "ideal_entry" : 0.0,
            "swing_high"  : 0.0,
            "swing_low"   : 0.0,
            "tf"          : None,
            "in_zone"     : False,
            "distance"    : 0.0,
            "current"     : 0.0,
            "reason"      : reason,
            "timestamp"   : datetime.now(timezone.utc).isoformat(),
        }

    def __repr__(self) -> str:
        return f"OTEDetector(zone={OTE_LOW*100}%-{OTE_HIGH*100}%)"
