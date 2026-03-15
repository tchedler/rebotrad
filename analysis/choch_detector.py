# analysis/choch_detector.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Détecteur CHoCH (Change of Character)
══════════════════════════════════════════════════════════════
Responsabilités :
  - Détecter les premiers signes faibles de retournement (CHoCH)
    sur les timeframes courts (M15, H1)
  - Servir d'alerte PRÉCOCE avant que le MSS complet soit confirmé
  - Filtrer les entrées contre-tendance trop prématurées

Concept ICT :
  Un CHoCH intervient AVANT le MSS. C'est le premier symptôme
  que la tendance perd de sa force. Il se manifeste par la
  cassure d'un Swing High ou Low INTERNE à la structure (pas
  le dernier swing extrême).

  Exemple (Bearish → Bullish CHoCH) :
    - Le marché fait des LL (Lower Lows) et LH (Lower Highs)
    - Soudain, le prix casse AU-DESSUS du dernier LH
    - C'est un CHoCH → première preuve de faiblesse BEARISH
    - Elle ne confirme pas un retournement, mais prépare l'entrée

Différence MSS vs CHoCH :
  - CHoCH = signal INTERNE, "early warning", peut-être faux
  - MSS   = confirmation FINALE, fort momentum, structure cassée

Consommé par :
  - kb5_engine.py (bonus léger + filtre sur les setups LTF)
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

# Nombre de bougies pour définir la structure locale
CHOCH_STRUCTURE_LEN    = 10    # Fenêtre pour identifier HH / HL / LH / LL
CHOCH_LOOKBACK_CANDLES = 15    # Bougies à scanner pour un CHoCH récent
CHOCH_FRESH_CANDLES    = 4     # Fraîcheur : 4 bougies pour être "actif"

# Corps minimum d'une bougie pour valider le CHoCH (plus souple que MSS)
CHOCH_BODY_MIN_ATR     = 0.25  # Corps > 25% ATR (moins strict que MSS)

# Timeframes pour le CHoCH (LTF seulement — c'est un signal faible)
CHOCH_TIMEFRAMES       = ["H1", "M15"]


# ══════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════

class CHoCHDetector:
    """
    Détecteur de Change of Character pour Sentinel Pro KB5.

    Répond à la question :
      "Le marché montre-t-il ses PREMIERS signes de faiblesse
       dans la direction dominante ?"

    Utilisation typique :
      CHoCH détecté sur H1 → la structure LTF est en train de
      se retourner → renforce un setup pris sur un OB ou FVG
      dans la nouvelle direction.
    """

    def __init__(self, data_store: DataStore):
        self._ds   = data_store
        self._lock = threading.RLock()
        self._cache: dict[str, dict] = {}
        logger.info("CHoCHDetector initialisé — Surveillance des changements de caractère")

    # ══════════════════════════════════════════════════════════
    # MÉTHODE PRINCIPALE
    # ══════════════════════════════════════════════════════════

    def analyze(self, pair: str) -> dict:
        """
        Analyse le CHoCH sur les timeframes H1 et M15.

        Args:
            pair: ex. "EURUSD"

        Returns:
            dict {bullish_choch, bearish_choch, dominant, timeframes}
        """
        results_per_tf = {}

        for tf in CHOCH_TIMEFRAMES:
            df = self._ds.get_candles(pair, tf)
            if df is None or len(df) < CHOCH_STRUCTURE_LEN + CHOCH_LOOKBACK_CANDLES:
                results_per_tf[tf] = {"bullish": None, "bearish": None}
                continue

            atr    = self._calculate_atr(df)
            struct = self._classify_structure(df)
            bull   = self._detect_bullish_choch(df, struct, atr)
            bear   = self._detect_bearish_choch(df, struct, atr)

            results_per_tf[tf] = {
                "structure": struct,
                "bullish":   bull,
                "bearish":   bear,
            }

        dominant = self._find_dominant_choch(results_per_tf)

        result = {
            "pair":       pair,
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "timeframes": results_per_tf,
            "dominant":   dominant,
        }

        with self._lock:
            self._cache[pair] = result

        self._ds.set_analysis(pair, "choch", result)

        if dominant.get("detected"):
            logger.info(
                f"CHoCH — {pair} | Direction: {dominant['direction']} | "
                f"TF: {dominant['tf']} | Structure: {dominant.get('from_structure')} → "
                f"{'BULLISH' if dominant['direction'] == 'BULLISH' else 'BEARISH'}"
            )

        return result

    # ══════════════════════════════════════════════════════════
    # CLASSIFICATION DE LA STRUCTURE
    # ══════════════════════════════════════════════════════════

    def _classify_structure(self, df: pd.DataFrame) -> str:
        """
        Détermine si le marché est en tendance haussière (HH/HL)
        ou baissière (LH/LL) sur la fenêtre récente.

        Returns:
            "BULLISH_TREND" | "BEARISH_TREND" | "RANGING"
        """
        n      = len(df)
        window = min(CHOCH_STRUCTURE_LEN, n)
        highs  = df["high"].values[-window:]
        lows   = df["low"].values[-window:]

        # Comparer le mid de la fenêtre avec le début et la fin
        mid = window // 2

        hh = highs[-1] > highs[mid]    # Higher High
        hl = lows[-1]  > lows[mid]     # Higher Low
        lh = highs[-1] < highs[mid]    # Lower High
        ll = lows[-1]  < lows[mid]     # Lower Low

        if hh and hl:
            return "BULLISH_TREND"
        elif lh and ll:
            return "BEARISH_TREND"
        else:
            return "RANGING"

    # ══════════════════════════════════════════════════════════
    # DÉTECTION CHOCH BULLISH
    # ══════════════════════════════════════════════════════════

    def _detect_bullish_choch(self, df: pd.DataFrame,
                               structure: str, atr: float) -> Optional[dict]:
        """
        Détecte un CHoCH Haussier (BEARISH → BULLISH).
        Le marché était en tendance BAISSIÈRE (LH/LL) et le prix
        vient de casser au-dessus d'un Lower High précédent.

        Returns:
            dict CHoCH ou None
        """
        # CHoCH Bullish pertinent seulement si structure précédente était BEARISH
        if structure not in ("BEARISH_TREND", "RANGING"):
            return None

        n      = len(df)
        highs  = df["high"].values
        closes = df["close"].values
        opens  = df["open"].values

        # Identifier les Lower Highs dans la fenêtre de structure
        struct_start = max(0, n - CHOCH_STRUCTURE_LEN - CHOCH_LOOKBACK_CANDLES)
        struct_end   = max(0, n - CHOCH_LOOKBACK_CANDLES)

        if struct_end <= struct_start:
            return None

        # Chercher les Lower Highs dans la structure récente
        local_highs = []
        for i in range(struct_start, struct_end):
            lb = 2
            if i >= lb and i < n - lb:
                if highs[i] >= max(highs[max(0, i - lb): i]) and \
                   highs[i] >= max(highs[i + 1: min(n, i + lb + 1)]):
                    local_highs.append((i, float(highs[i])))

        if not local_highs:
            return None

        # Y'a-t-il une bougie récente qui clôture AU-DESSUS d'un de ces highs ?
        scan_start = max(0, n - CHOCH_LOOKBACK_CANDLES)

        for i in range(scan_start, n):
            c    = float(closes[i])
            o    = float(opens[i])
            body = abs(c - o)

            if body < CHOCH_BODY_MIN_ATR * atr:
                continue

            # Clôture haussière (c > o pour confirmation)
            if c <= o:
                continue

            for hx_idx, hx_level in local_highs:
                if hx_idx >= i:
                    continue
                if c > hx_level:
                    is_fresh = i >= n - CHOCH_FRESH_CANDLES
                    return {
                        "detected":       True,
                        "direction":      "BULLISH",
                        "from_structure": structure,
                        "break_level":    round(hx_level, 6),
                        "break_close":    round(c, 6),
                        "body_atr":       round(body / atr, 2),
                        "candle_idx":     i,
                        "swing_idx":      hx_idx,
                        "fresh":          is_fresh,
                    }

        return None

    # ══════════════════════════════════════════════════════════
    # DÉTECTION CHOCH BEARISH
    # ══════════════════════════════════════════════════════════

    def _detect_bearish_choch(self, df: pd.DataFrame,
                               structure: str, atr: float) -> Optional[dict]:
        """
        Détecte un CHoCH Baissier (BULLISH → BEARISH).
        Le marché était en tendance HAUSSIÈRE et le prix vient
        de casser sous un Higher Low précédent.

        Returns:
            dict CHoCH ou None
        """
        if structure not in ("BULLISH_TREND", "RANGING"):
            return None

        n      = len(df)
        lows   = df["low"].values
        closes = df["close"].values
        opens  = df["open"].values

        struct_start = max(0, n - CHOCH_STRUCTURE_LEN - CHOCH_LOOKBACK_CANDLES)
        struct_end   = max(0, n - CHOCH_LOOKBACK_CANDLES)

        if struct_end <= struct_start:
            return None

        local_lows = []
        for i in range(struct_start, struct_end):
            lb = 2
            if i >= lb and i < n - lb:
                if lows[i] <= min(lows[max(0, i - lb): i]) and \
                   lows[i] <= min(lows[i + 1: min(n, i + lb + 1)]):
                    local_lows.append((i, float(lows[i])))

        if not local_lows:
            return None

        scan_start = max(0, n - CHOCH_LOOKBACK_CANDLES)

        for i in range(scan_start, n):
            c    = float(closes[i])
            o    = float(opens[i])
            body = abs(c - o)

            if body < CHOCH_BODY_MIN_ATR * atr:
                continue

            # Clôture baissière (c < o pour confirmation)
            if c >= o:
                continue

            for lx_idx, lx_level in local_lows:
                if lx_idx >= i:
                    continue
                if c < lx_level:
                    is_fresh = i >= n - CHOCH_FRESH_CANDLES
                    return {
                        "detected":       True,
                        "direction":      "BEARISH",
                        "from_structure": structure,
                        "break_level":    round(lx_level, 6),
                        "break_close":    round(c, 6),
                        "body_atr":       round(body / atr, 2),
                        "candle_idx":     i,
                        "swing_idx":      lx_idx,
                        "fresh":          is_fresh,
                    }

        return None

    # ══════════════════════════════════════════════════════════
    # DOMINANT CHoCH
    # ══════════════════════════════════════════════════════════

    def _find_dominant_choch(self, results_per_tf: dict) -> dict:
        """
        Retourne le CHoCH dominant (H1 prioritaire sur M15).

        Returns:
            dict CHoCH ou {detected: False}
        """
        for tf in CHOCH_TIMEFRAMES:
            tf_data = results_per_tf.get(tf, {})
            bull    = tf_data.get("bullish")
            bear    = tf_data.get("bearish")

            candidates = []
            if bull and bull.get("detected"):
                bull["tf"] = tf
                candidates.append(bull)
            if bear and bear.get("detected"):
                bear["tf"] = tf
                candidates.append(bear)

            if candidates:
                candidates.sort(key=lambda m: 0 if m.get("fresh") else 1)
                return candidates[0]

        return {"detected": False, "reason": "Aucun CHoCH détecté"}

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

    def get_dominant_choch(self, pair: str) -> dict:
        """Retourne le CHoCH dominant pour une paire."""
        with self._lock:
            data = self._cache.get(pair, {})
        return data.get("dominant", {"detected": False})

    def has_choch(self, pair: str, direction: str) -> bool:
        """
        Vérifie si un CHoCH FRESH est actif dans la direction donnée.

        Args:
            pair:      ex. "EURUSD"
            direction: "BULLISH" ou "BEARISH"

        Returns:
            True si CHoCH FRESH dans la direction demandée
        """
        choch = self.get_dominant_choch(pair)
        return (
            choch.get("detected", False)
            and choch.get("direction") == direction
            and choch.get("fresh", False)
        )

    def get_choch_level(self, pair: str, direction: str) -> Optional[float]:
        """
        Retourne le niveau de cassure du CHoCH.
        Utile pour définir des zones d'OTE.

        Returns:
            float niveau ou None
        """
        choch = self.get_dominant_choch(pair)
        if choch.get("detected") and choch.get("direction") == direction:
            return choch.get("break_level")
        return None

    def get_snapshot(self, pair: str) -> dict:
        """Snapshot compact pour le dashboard."""
        with self._lock:
            data = dict(self._cache.get(pair, {}))
        if not data:
            return {"pair": pair, "status": "non analysé"}
        dom = data.get("dominant", {})
        return {
            "pair":           pair,
            "detected":       dom.get("detected", False),
            "direction":      dom.get("direction"),
            "break_level":    dom.get("break_level"),
            "fresh":          dom.get("fresh"),
            "from_structure": dom.get("from_structure"),
            "tf":             dom.get("tf"),
        }

    def clear_cache(self, pair: Optional[str] = None) -> None:
        """Vide le cache."""
        with self._lock:
            if pair:
                self._cache.pop(pair, None)
            else:
                self._cache.clear()
