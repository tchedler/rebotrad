"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — CISD Detector
(Change In State of Delivery)
══════════════════════════════════════════════════════════════
Concept ICT :
Le CISD est un signal de confirmation M5/M1 qui précède
un MSS (Market Structure Shift) sur H1.
C'est la bougie qui "change" la livraison du prix :
- BULLISH CISD : bougie baissière suivie d'une bougie
                 haussière qui clôture AU-DESSUS du high
                 de la bougie baissière
- BEARISH CISD : bougie haussière suivie d'une bougie
                 baissière qui clôture EN-DESSOUS du low
                 de la bougie haussière

Utilisation KB5 :
Le CISD sur M5 ou M1 est le trigger d'entrée précis
APRÈS confirmation du setup H1/H4.
══════════════════════════════════════════════════════════════
"""

import logging
import pandas as pd
from datetime import datetime, timezone
from datastore.data_store import DataStore

logger = logging.getLogger(__name__)

# Paramètres CISD
CISD_MIN_BODY_RATIO = 0.4   # corps bougie min 40% de la range
CISD_LOOKBACK       = 10    # bougies à analyser en arrière


class CISDDetector:
    """
    Détecte le CISD sur M5 et M1 comme trigger d'entrée précis.
    Consommé par kb5_engine pour la confirmation LTF finale.
    """

    def __init__(self, datastore: DataStore):
        self._ds = datastore
        logger.info("CISDDetector initialisé — trigger M5/M1 prêt")

    # ══════════════════════════════════════════════════════════
    # MÉTHODE PRINCIPALE
    # ══════════════════════════════════════════════════════════

    def check(self, pair: str, direction: str) -> dict:
        """
        Détecte un CISD récent sur M5 puis M1 en fallback.

        Returns:
            dict {
                detected   : bool,
                tf         : str,     # M5 ou M1
                cisd_high  : float,   # high de la bougie signal
                cisd_low   : float,   # low de la bougie signal
                cisd_close : float,   # clôture de confirmation
                strength   : str,     # STRONG / MODERATE / WEAK
                bars_ago   : int,     # il y a combien de bougies
                reason     : str,
            }
        """
        # M5 d'abord, M1 en fallback
        for tf in ["M5", "M1"]:
            result = self._check_tf(pair, direction, tf)
            if result["detected"]:
                return result

        return self._empty_result("Aucun CISD détecté sur M5/M1")

    # ══════════════════════════════════════════════════════════
    # DÉTECTION PAR TF
    # ══════════════════════════════════════════════════════════

    def _check_tf(self, pair: str, direction: str, tf: str) -> dict:
        """Cherche un CISD sur les dernières bougies du TF."""
        df = self._ds.get_candles(pair, tf)
        if df is None or len(df) < CISD_LOOKBACK + 2:
            return self._empty_result(f"{tf} insuffisant")

        candles = df.tail(CISD_LOOKBACK + 1).reset_index(drop=True)

        # Analyser les paires de bougies (n-1, n)
        for i in range(len(candles) - 1, 0, -1):
            prev = candles.iloc[i - 1]  # bougie signal
            curr = candles.iloc[i]      # bougie confirmation

            result = self._detect_cisd_pair(
                prev, curr, direction, tf,
                bars_ago=len(candles) - 1 - i
            )
            if result["detected"]:
                return result

        return self._empty_result(f"Pas de CISD sur {tf}")

    def _detect_cisd_pair(self, prev: pd.Series, curr: pd.Series,
                          direction: str, tf: str,
                          bars_ago: int) -> dict:
        """
        Analyse une paire de bougies pour détecter un CISD.

        BULLISH CISD :
          - prev = bougie baissière (close < open)
          - curr = bougie haussière qui clôture > high de prev

        BEARISH CISD :
          - prev = bougie haussière (close > open)
          - curr = bougie baissière qui clôture < low de prev
        """
        prev_open  = float(prev["open"])
        prev_close = float(prev["close"])
        prev_high  = float(prev["high"])
        prev_low   = float(prev["low"])
        prev_range = prev_high - prev_low

        curr_open  = float(curr["open"])
        curr_close = float(curr["close"])
        curr_high  = float(curr["high"])
        curr_low   = float(curr["low"])
        curr_range = curr_high - curr_low

        if prev_range <= 0 or curr_range <= 0:
            return self._empty_result("Range nulle")

        # Corps minimum
        prev_body = abs(prev_close - prev_open)
        curr_body = abs(curr_close - curr_open)
        prev_body_ratio = prev_body / prev_range
        curr_body_ratio = curr_body / curr_range

        if (prev_body_ratio < CISD_MIN_BODY_RATIO or
                curr_body_ratio < CISD_MIN_BODY_RATIO):
            return self._empty_result("Corps insuffisant")

        if direction == "BULLISH":
            # prev baissière + curr haussière au-dessus du high prev
            is_prev_bearish = prev_close < prev_open
            is_curr_bullish = curr_close > curr_open
            is_cisd = (is_prev_bearish and
                       is_curr_bullish and
                       curr_close > prev_high)

        else:  # BEARISH
            # prev haussière + curr baissière en-dessous du low prev
            is_prev_bullish = prev_close > prev_open
            is_curr_bearish = curr_close < curr_open
            is_cisd = (is_prev_bullish and
                       is_curr_bearish and
                       curr_close < prev_low)

        if not is_cisd:
            return self._empty_result("Pattern CISD absent")

        # Force du signal
        if curr_body_ratio >= 0.7:
            strength = "STRONG"
        elif curr_body_ratio >= 0.5:
            strength = "MODERATE"
        else:
            strength = "WEAK"

        logger.debug(f"CISD {direction} détecté sur {tf} "
                     f"il y a {bars_ago} bougies — {strength}")

        return {
            "detected"   : True,
            "tf"         : tf,
            "cisd_high"  : round(prev_high, 6),
            "cisd_low"   : round(prev_low, 6),
            "cisd_close" : round(curr_close, 6),
            "strength"   : strength,
            "bars_ago"   : bars_ago,
            "body_ratio" : round(curr_body_ratio, 3),
            "reason"     : f"CISD {direction} {strength} sur {tf}",
            "timestamp"  : datetime.now(timezone.utc).isoformat(),
        }

    # ══════════════════════════════════════════════════════════
    # BONUS SCORING
    # ══════════════════════════════════════════════════════════

    def get_score_bonus(self, pair: str, direction: str) -> int:
        """
        Retourne le bonus de score CISD.
        STRONG   → +10 pts
        MODERATE → +7  pts
        WEAK     → +3  pts
        """
        result = self.check(pair, direction)
        if not result["detected"]:
            return 0
        bonuses = {"STRONG": 10, "MODERATE": 7, "WEAK": 3}
        return bonuses.get(result["strength"], 0)

    # ══════════════════════════════════════════════════════════
    # UTILITAIRES
    # ══════════════════════════════════════════════════════════

    def _empty_result(self, reason: str) -> dict:
        return {
            "detected"   : False,
            "tf"         : None,
            "cisd_high"  : 0.0,
            "cisd_low"   : 0.0,
            "cisd_close" : 0.0,
            "strength"   : None,
            "bars_ago"   : 0,
            "body_ratio" : 0.0,
            "reason"     : reason,
            "timestamp"  : datetime.now(timezone.utc).isoformat(),
        }

    def __repr__(self) -> str:
        return f"CISDDetector(tf=M5/M1, min_body={CISD_MIN_BODY_RATIO})"
