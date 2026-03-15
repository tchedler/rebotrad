# analysis/mss_detector.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Détecteur MSS (Market Structure Shift)
══════════════════════════════════════════════════════════════
Responsabilités :
  - Détecter les cassures MAJEURES de structure du marché (MSS)
  - Distinguer un vrai MSS (fort momentum institutionnel) d'un
    "fakeout" retail (faible volume, petite mèche)
  - Valider le changement de direction DOMINANT sur HTF

Concept ICT :
  Un MSS est confirmé quand :
  1. Le prix casse VIOLEMMENT (avec fort corps de bougie) un
     Swing High (pour BULLISH) ou Swing Low (pour BEARISH)
  2. Cette cassure s'effectue avec un déplacement "impulsif"
     (grande bougie dont le corps dépasse > 50% de l'ATR)
  3. Le niveau cassé devient désormais la zone de retour optimal
     pour rechercher des entrées dans la direction du MSS

Différence MSS vs CHoCH :
  - MSS   = cassure FINALE, FORTE, confirme l'inversion totale
  - CHoCH = PREMIER signe faible de retournement interne

Consommé par :
  - kb5_engine.py (bonus de confluence + validation structure)
══════════════════════════════════════════════════════════════
"""

import logging
import threading
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Optional

from datastore.data_store import DataStore

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# CONSTANTES
# ══════════════════════════════════════════════════════════════

# Nombre de bougies pour identifier un Swing High / Low significatif
SWING_LOOKBACK         = 5     # N bougies de chaque côté pour valider un swing

# Mimimum de corps de bougie pour valider le MSS (en x ATR)
MSS_BODY_MIN_ATR       = 0.50  # Corps > 50% ATR = impulsion institutionelle

# Nombre de bougies à scanner pour le MSS
MSS_LOOKBACK_CANDLES   = 20    # Scanner les 20 dernières bougies max

# Fraîcheur du MSS : combien de bougies avant qu'il soit "périmé"
MSS_FRESH_CANDLES      = 6     # Valide pendant 6 bougies après détection

# Timeframes à analyser pour le MSS (du plus HTF au plus LTF)
MSS_TIMEFRAMES         = ["H4", "H1", "M15"]


# ══════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════

class MSSDetector:
    """
    Détecteur de Market Structure Shift pour Sentinel Pro KB5.

    Un MSS valide indique que le marché a OFFICIELLEMENT changé
    de direction — pas une simple correction, mais une vraie
    inversion de la structure des prix confirmée par le momentum.

    Réponses aux questions clé :
      "Est-ce que le prix a CASSÉ avec conviction un niveau clé ?"
      "La structure haussière est-elle officiellement invalidée ?"
    """

    def __init__(self, data_store: DataStore):
        self._ds   = data_store
        self._lock = threading.RLock()
        self._cache: dict[str, dict] = {}
        logger.info("MSSDetector initialisé — Veille des structures de marché active")

    # ══════════════════════════════════════════════════════════
    # MÉTHODE PRINCIPALE
    # ══════════════════════════════════════════════════════════

    def analyze(self, pair: str) -> dict:
        """
        Analyse complète du MSS pour une paire sur tous les TF pertinents.

        Args:
            pair: ex. "EURUSD"

        Returns:
            dict {bullish_mss, bearish_mss, dominant_mss, timeframes}
        """
        results_per_tf = {}

        for tf in MSS_TIMEFRAMES:
            df = self._ds.get_candles(pair, tf)
            if df is None or len(df) < (SWING_LOOKBACK * 2 + MSS_LOOKBACK_CANDLES):
                results_per_tf[tf] = {"bullish": None, "bearish": None}
                continue

            atr = self._calculate_atr(df)
            swings = self._identify_swings(df)
            mss_bull = self._detect_mss_bullish(df, swings, atr)
            mss_bear = self._detect_mss_bearish(df, swings, atr)

            results_per_tf[tf] = {
                "bullish": mss_bull,
                "bearish": mss_bear,
            }

        # Déterminer le MSS dominant (HTF en priorité)
        dominant = self._find_dominant_mss(results_per_tf)

        result = {
            "pair":       pair,
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "timeframes": results_per_tf,
            "dominant":   dominant,
        }

        with self._lock:
            self._cache[pair] = result

        self._ds.set_analysis(pair, "mss", result)

        if dominant.get("detected"):
            logger.info(
                f"MSS — {pair} | Direction: {dominant['direction']} | "
                f"TF: {dominant['tf']} | Niveau: {dominant['break_level']} | "
                f"Fraîcheur: {'FRESH' if dominant.get('fresh') else 'USED'}"
            )

        return result

    # ══════════════════════════════════════════════════════════
    # IDENTIFICATION DES SWINGS
    # ══════════════════════════════════════════════════════════

    def _identify_swings(self, df: pd.DataFrame) -> dict:
        """
        Identifie les Swing Highs et Swing Lows significatifs.

        Un Swing High = bougie dont le high est plus haut que
        SWING_LOOKBACK bougies de chaque côté.
        Un Swing Low  = bougie dont le low est plus bas que
        SWING_LOOKBACK bougies de chaque côté.

        Returns:
            dict {highs: [list of (idx, level)], lows: [list of (idx, level)]}
        """
        highs = df["high"].values
        lows  = df["low"].values
        n     = len(df)
        lb    = SWING_LOOKBACK

        swing_highs = []
        swing_lows  = []

        # Scanner uniquement la fenêtre de détection
        start = max(lb, n - MSS_LOOKBACK_CANDLES - lb)
        end   = n - lb

        for i in range(start, end):
            # Swing High : max local
            if highs[i] == max(highs[max(0, i - lb): i + lb + 1]):
                swing_highs.append((i, float(highs[i])))

            # Swing Low : min local
            if lows[i] == min(lows[max(0, i - lb): i + lb + 1]):
                swing_lows.append((i, float(lows[i])))

        return {"highs": swing_highs, "lows": swing_lows}

    # ══════════════════════════════════════════════════════════
    # DÉTECTION MSS BULLISH
    # ══════════════════════════════════════════════════════════

    def _detect_mss_bullish(self, df: pd.DataFrame,
                             swings: dict, atr: float) -> Optional[dict]:
        """
        Détecte un MSS Haussier :
        Le prix casse AVEC CONVICTION un Swing High précédent.

        Conditions :
          1. Il existe un Swing High précédent
          2. Une bougie CLÔTURE au-dessus de ce Swing High
          3. Le corps de cette bougie > MSS_BODY_MIN_ATR × ATR
             (confirmation de momentum institutionnel)

        Returns:
            dict MSS ou None
        """
        if not swings["highs"]:
            return None

        closes = df["close"].values
        opens  = df["open"].values
        n      = len(df)

        # Scanner les bougies récentes pour trouver une cassure d'un Swing High
        scan_start = max(0, n - MSS_LOOKBACK_CANDLES)

        for i in range(scan_start, n):
            c    = float(closes[i])
            o    = float(opens[i])
            body = abs(c - o)

            # Corps impulsif requis (filtre les fakeouts)
            if body < MSS_BODY_MIN_ATR * atr:
                continue

            # Chercher si cette clôture casse un Swing High antérieur
            for swing_idx, swing_level in swings["highs"]:
                if swing_idx >= i:
                    continue  # Le swing doit être ANTÉRIEUR à la cassure

                if c > swing_level:
                    # MSS Bullish confirmé !
                    is_fresh = i >= n - MSS_FRESH_CANDLES
                    return {
                        "detected":     True,
                        "direction":    "BULLISH",
                        "break_level":  round(swing_level, 6),
                        "break_close":  round(c, 6),
                        "body_size_atr": round(body / atr, 2),
                        "candle_idx":   i,
                        "swing_idx":    swing_idx,
                        "fresh":        is_fresh,
                        "strength":     "STRONG" if body > atr else "MODERATE",
                    }

        return None

    # ══════════════════════════════════════════════════════════
    # DÉTECTION MSS BEARISH
    # ══════════════════════════════════════════════════════════

    def _detect_mss_bearish(self, df: pd.DataFrame,
                             swings: dict, atr: float) -> Optional[dict]:
        """
        Détecte un MSS Baissier :
        Le prix casse AVEC CONVICTION un Swing Low précédent.

        Returns:
            dict MSS ou None
        """
        if not swings["lows"]:
            return None

        closes = df["close"].values
        opens  = df["open"].values
        n      = len(df)

        scan_start = max(0, n - MSS_LOOKBACK_CANDLES)

        for i in range(scan_start, n):
            c    = float(closes[i])
            o    = float(opens[i])
            body = abs(c - o)

            if body < MSS_BODY_MIN_ATR * atr:
                continue

            for swing_idx, swing_level in swings["lows"]:
                if swing_idx >= i:
                    continue

                if c < swing_level:
                    is_fresh = i >= n - MSS_FRESH_CANDLES
                    return {
                        "detected":     True,
                        "direction":    "BEARISH",
                        "break_level":  round(swing_level, 6),
                        "break_close":  round(c, 6),
                        "body_size_atr": round(body / atr, 2),
                        "candle_idx":   i,
                        "swing_idx":    swing_idx,
                        "fresh":        is_fresh,
                        "strength":     "STRONG" if body > atr else "MODERATE",
                    }

        return None

    # ══════════════════════════════════════════════════════════
    # DOMINANT MSS
    # ══════════════════════════════════════════════════════════

    def _find_dominant_mss(self, results_per_tf: dict) -> dict:
        """
        Détermine le MSS le plus significatif parmi tous les TF.
        Priorité : H4 > H1 > M15, puis fraicheur > strength.

        Returns:
            dict MSS dominant ou {detected: False}
        """
        for tf in MSS_TIMEFRAMES:  # H4 en premier = plus haute priorité
            tf_data = results_per_tf.get(tf, {})
            bull    = tf_data.get("bullish")
            bear    = tf_data.get("bearish")

            # Préférer le MSS le plus frais
            candidates = []
            if bull and bull.get("detected"):
                bull["tf"] = tf
                candidates.append(bull)
            if bear and bear.get("detected"):
                bear["tf"] = tf
                candidates.append(bear)

            if candidates:
                # Parmi les candidats de ce TF, le plus frais et le plus fort
                candidates.sort(key=lambda m: (
                    0 if m.get("fresh") else 1,
                    0 if m.get("strength") == "STRONG" else 1
                ))
                return candidates[0]

        return {"detected": False, "reason": "Aucun MSS détecté sur tous les TF"}

    # ══════════════════════════════════════════════════════════
    # CALCUL ATR
    # ══════════════════════════════════════════════════════════

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """ATR Wilder standard. Fallback 0.0001."""
        if len(df) < period + 1:
            return 0.0001

        high  = df["high"].values
        low   = df["low"].values
        close = df["close"].values

        tr_list = [
            max(high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i]  - close[i - 1]))
            for i in range(1, len(df))
        ]

        atr = float(np.mean(tr_list[:period]))
        for tr in tr_list[period:]:
            atr = (atr * (period - 1) + tr) / period

        return max(atr, 0.0001)

    # ══════════════════════════════════════════════════════════
    # API PUBLIQUE
    # ══════════════════════════════════════════════════════════

    def get_dominant_mss(self, pair: str) -> dict:
        """
        Retourne le MSS dominant en cache pour une paire.

        Returns:
            dict MSS ou {detected: False}
        """
        with self._lock:
            data = self._cache.get(pair, {})
        return data.get("dominant", {"detected": False})

    def has_bullish_mss(self, pair: str, tf: str = None) -> bool:
        """
        Vérifie si un MSS Haussier FRESH est actif.

        Args:
            pair: ex. "EURUSD"
            tf:   Timeframe spécifique, ou None pour le dominant

        Returns:
            True si MSS Bullish FRESH détecté
        """
        with self._lock:
            data = self._cache.get(pair, {})

        if tf:
            mss = data.get("timeframes", {}).get(tf, {}).get("bullish")
        else:
            mss = data.get("dominant", {})

        if not mss or not mss.get("detected"):
            return False
        return (
            mss.get("direction") == "BULLISH"
            and mss.get("fresh", False)
        )

    def has_bearish_mss(self, pair: str, tf: str = None) -> bool:
        """
        Vérifie si un MSS Baissier FRESH est actif.

        Returns:
            True si MSS Bearish FRESH détecté
        """
        with self._lock:
            data = self._cache.get(pair, {})

        if tf:
            mss = data.get("timeframes", {}).get(tf, {}).get("bearish")
        else:
            mss = data.get("dominant", {})

        if not mss or not mss.get("detected"):
            return False
        return (
            mss.get("direction") == "BEARISH"
            and mss.get("fresh", False)
        )

    def get_mss_level(self, pair: str, direction: str) -> Optional[float]:
        """
        Retourne le niveau de cassure du MSS (utilisé comme SL ou OTE).

        Returns:
            float niveau ou None
        """
        mss = self.get_dominant_mss(pair)
        if mss.get("detected") and mss.get("direction") == direction:
            return mss.get("break_level")
        return None

    def get_snapshot(self, pair: str) -> dict:
        """Snapshot compact pour le dashboard."""
        with self._lock:
            data = dict(self._cache.get(pair, {}))
        if not data:
            return {"pair": pair, "status": "non analysé"}
        dom = data.get("dominant", {})
        return {
            "pair":          pair,
            "detected":      dom.get("detected", False),
            "direction":     dom.get("direction"),
            "break_level":   dom.get("break_level"),
            "fresh":         dom.get("fresh"),
            "strength":      dom.get("strength"),
            "tf":            dom.get("tf"),
        }

    def clear_cache(self, pair: Optional[str] = None) -> None:
        """Vide le cache (appelé par ReconnectManager)."""
        with self._lock:
            if pair:
                self._cache.pop(pair, None)
            else:
                self._cache.clear()
