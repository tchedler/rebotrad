# analysis/pa_detector.py
# encoding: utf-8
"""
==============================================================
Sentinel Pro KB5 - Price Action Pur Detector
==============================================================
Detecte les concepts fondamentaux du Price Action pur (PA) :

  E1. CHIFFRES RONDS (Round Numbers / Psychological Levels)
      - Niveaux a 00 et 50 pips (ex: 1.0800, 1.0850)
      - Niveaux a 00  sur indices (ex: 33000, 20000) et Or
      - Ce sont des niveaux "magiques" : beaucoup d'ordres SL/TP

  E2. LIGNES DE TENDANCE (Swing High/Low Connection)
      - Detection des Swing Highs / Swing Lows locaux (structure)
      - Calcul de la pente (slope) et de la validite (nb touches)
      - Coherence avec le biais HTF

  E3. ENGULFING (Bougie d'Absorption)
      - Bullish Engulfing : corps haussier avale le corps de la bougie precedente
      - Bearish Engulfing : corps baissier avale le corps de la bougie precedente
      - Confirmation ICT : on prefere un Engulfing sur un FVG/OB/Pool

Consomme par :
  - kb5_engine.py (bonus CONFLUENCE_PA_* dans _detect_confluences())
==============================================================
"""

import logging
import threading
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Optional

from datastore.data_store import DataStore
from config.constants import PAIR_MARKET_TYPE, MarketType

logger = logging.getLogger(__name__)

# ==============================================================
# CONSTANTES PA
# ==============================================================

# Tolerances Round Numbers (en pips absolus selon l'actif)
# Le prix doit etre a moins de ROUND_NUMBER_TOLERANCE pour etre "pres" du niveau
ROUND_NUMBER_TOLERANCE_FX     = 0.00050   # Forex : +-5 pips
ROUND_NUMBER_TOLERANCE_GOLD   = 0.50      # Or : +-50 cents
ROUND_NUMBER_TOLERANCE_CRYPTO = 100.0     # BTC : +-$100
ROUND_NUMBER_TOLERANCE_INDEX  = 25.0      # Indices : +-25 pts

# Taille minimum du corps Engulfing vs bougie precedente (en %)
ENGULF_BODY_RATIO_MIN         = 1.0      # Le corps doit couvrir >= 100% du corps precedent
# Un Engulfing de 150% est fort, 100% est modere
ENGULF_STRONG_RATIO           = 1.5

# Nombre de swings pour tracer la trendline
TRENDLINE_MIN_TOUCHES         = 2
# Fenetre de recherche des swings (en bougies H1)
TRENDLINE_LOOKBACK            = 50
# Nombre de bougies pour definir un "Swing High/Low" (sommet local)
SWING_ORDER                   = 3        # Swing si high[i] > high[i-3..i+3]

# Bonus scores PA (pour kb5_engine)
CONFLUENCE_ROUND_NUMBER       = 8    # Pres d'un chiffre rond = support/resistance psychologique
CONFLUENCE_TRENDLINE          = 10   # Setup sur ligne de tendance valide
CONFLUENCE_ENGULFING          = 12   # Bougie Engulfing confirme la direction


# ==============================================================
# CLASSE PRINCIPALE
# ==============================================================

class PADetector:
    """
    Detecteur de Price Action Pur pour Sentinel Pro KB5.

    Cette couche complementaire au pipeline ICT capte les signaux
    que les institutions et les traders PA utilisent independamment :
      - Les chiffres ronds (Round Numbers) = zones de clusters d'ordres SL/TP
      - Les trendlines = dynamique structurelle du marche
      - Les engulfings = "coup de pied" d'absorption institutionnelle
    """

    def __init__(self, data_store: DataStore):
        self._ds   = data_store
        self._lock = threading.RLock()
        self._cache: dict[str, dict] = {}
        logger.info("PADetector initialise - Price Action pur actif")

    # ==============================================================
    # METHODE PRINCIPALE
    # ==============================================================

    def analyze(self, pair: str) -> dict:
        """
        Analyse complete PA pour une paire.

        Returns:
            dict {round_numbers, engulfing, trendlines, timestamp}
        """
        df_h1  = self._ds.get_candles(pair, "H1")
        df_m15 = self._ds.get_candles(pair, "M15")

        if df_h1 is None or len(df_h1) < 20:
            return self._empty_result(pair)

        market_type = PAIR_MARKET_TYPE.get(pair, MarketType.FOREX)
        current_price = float(df_h1["close"].iloc[-1])

        # ---- E1 : Round Numbers ----
        round_levels = self._detect_round_numbers(current_price, market_type)

        # ---- E2 : Trendlines (Swing High/Low) ----
        trendlines = self._detect_trendlines(df_h1)

        # ---- E3 : Engulfing (H1 + M15) ----
        engulf_h1  = self._detect_engulfing(df_h1,  lookback=5,  label="H1")
        engulf_m15 = self._detect_engulfing(df_m15 if df_m15 is not None else df_h1,
                                             lookback=10, label="M15")

        result = {
            "pair":          pair,
            "timestamp":     datetime.now(timezone.utc).isoformat(),
            "price":         current_price,
            "round_numbers": round_levels,
            "trendlines":    trendlines,
            "engulfing":     {
                "H1":  engulf_h1,
                "M15": engulf_m15,
            },
        }

        with self._lock:
            self._cache[pair] = result

        logger.info(
            f"PADetector - {pair} | "
            f"Rounds: {len(round_levels)} | "
            f"Trendlines: {len(trendlines)} | "
            f"Engulf H1: {engulf_h1.get('type', 'NONE')} | "
            f"Engulf M15: {engulf_m15.get('type', 'NONE')}"
        )
        return result

    # ==============================================================
    # E1 : CHIFFRES RONDS (ROUND NUMBERS)
    # ==============================================================

    def _detect_round_numbers(self, price: float,
                               market_type: MarketType) -> list:
        """
        Identifie les niveaux de chiffres ronds proches du prix actuel.

        Logique adaptee par type de marche :
          - Forex : niveaux a 0.XX00 et 0.XX50 (pas de 50 pips)
          - Or    : niveaux a X00 (ex: 2300, 2350)
          - Crypto: niveaux a X000 (ex: 85000, 90000)
          - Index : niveaux a X000 ou X500

        On retourne les 3 niveaux Round Numbers les plus proches
        (un au-dessus, un en-dessous, un au prix actuel si tres proche).
        """
        if market_type == MarketType.FOREX:
            tolerance = ROUND_NUMBER_TOLERANCE_FX
            # Arrondir a la centaine de pips : 1.0800, 1.0850
            step   = 0.0050
            levels = self._get_round_levels_float(price, step, n_above=3, n_below=3)

        elif market_type == MarketType.GOLD:
            tolerance = ROUND_NUMBER_TOLERANCE_GOLD
            step      = 50.0     # 2300, 2350, 2400
            levels    = self._get_round_levels_float(price, step, n_above=3, n_below=3)

        elif market_type == MarketType.CRYPTO:
            tolerance = ROUND_NUMBER_TOLERANCE_CRYPTO
            step      = 1000.0   # 85000, 86000
            levels    = self._get_round_levels_float(price, step, n_above=3, n_below=3)

        elif market_type == MarketType.INDEX:
            tolerance = ROUND_NUMBER_TOLERANCE_INDEX
            step      = 500.0    # 20000, 20500
            levels    = self._get_round_levels_float(price, step, n_above=3, n_below=3)

        else:
            tolerance = ROUND_NUMBER_TOLERANCE_FX
            step      = 0.0050
            levels    = self._get_round_levels_float(price, step, n_above=3, n_below=3)

        # Enrichir chaque niveau avec sa distance et sa proximite
        result = []
        for lv in levels:
            dist  = abs(price - lv)
            prox  = dist <= tolerance
            side  = "ABOVE" if lv > price else "BELOW" if lv < price else "AT"
            # Detecter les niveaux "gros" (XX00) vs "mi-niveau" (XX50)
            strength = self._round_number_strength(lv, step)
            result.append({
                "level":    round(lv, 6),
                "distance": round(dist, 6),
                "near":     prox,
                "side":     side,
                "strength": strength,   # "MAJOR" (00) ou "MINOR" (50)
            })

        # Trier par distance
        result.sort(key=lambda x: x["distance"])
        return result

    def _get_round_levels_float(self, price: float, step: float,
                                 n_above: int, n_below: int) -> list:
        """
        Genere des niveaux arrondis au step le plus proche.
        """
        base = round(price / step) * step
        levels = []
        for i in range(-n_below, n_above + 1):
            levels.append(round(base + i * step, 6))
        return levels

    def _round_number_strength(self, level: float, step: float) -> str:
        """
        Determine si c'est un niveau MAJOR (XX00 / double-zero)
        ou MINOR (XX50 / mid-level).
        """
        # Pour Forex : si le niveau est divisible par 2*step c'est un MAJOR
        if step < 1:
            # Forex : 0.0050 step -> MAJOR si divisible par 0.0100
            is_major = abs(round(level / (step * 2), 0) * step * 2 - level) < 1e-7
        else:
            # Indices, Or, Crypto : MAJOR si divisible par 2*step
            is_major = abs(level % (step * 2)) < 0.01

        return "MAJOR" if is_major else "MINOR"

    # ==============================================================
    # E2 : LIGNES DE TENDANCE (SWING HIGH/LOW)
    # ==============================================================

    def _detect_trendlines(self, df: pd.DataFrame) -> list:
        """
        Detecte les lignes de tendance actives depuis les pivots H1.

        Methode :
          1. Identifier les Swing Highs/Lows locaux (avec un ordre de N bougies)
          2. Connecter les 2-3 derniers pivots de meme type
          3. Calculer la pente (slope) et valider la coherence
          4. Verifier si le prix actuel est pres de la trendline (test de la ligne)

        Returns:
            list de dicts {type, slope, points, current_value, price_distance, valid}
        """
        lookback = min(TRENDLINE_LOOKBACK, len(df))
        df_w     = df.iloc[-lookback:]

        highs  = df_w["high"].values
        lows   = df_w["low"].values
        closes = df_w["close"].values
        n      = len(df_w)
        current_price = float(closes[-1])

        order = min(SWING_ORDER, n // 4)
        if order < 1:
            return []

        # ---- Detecter les pivots ----
        swing_highs = []
        swing_lows  = []

        for i in range(order, n - order):
            # Swing High : max local
            if highs[i] == max(highs[max(0, i-order):i+order+1]):
                swing_highs.append((i, highs[i]))
            # Swing Low : min local
            if lows[i] == min(lows[max(0, i-order):i+order+1]):
                swing_lows.append((i, lows[i]))

        trendlines = []

        # ---- Trendline Baissiere : connexion des 2-3 derniers Swing Highs ----
        if len(swing_highs) >= 2:
            p1, p2 = swing_highs[-2], swing_highs[-1]
            slope  = (p2[1] - p1[1]) / max(p2[0] - p1[0], 1)
            # Valeur courante de la trendline (extrapolee au dernier index)
            current_tl  = p2[1] + slope * (n - 1 - p2[0])
            distance    = abs(current_price - current_tl)

            # Trendline baissiere valide si slope < 0
            is_valid = slope < 0 and abs(slope) > 0.00001
            trendlines.append({
                "type":           "BEARISH_TL",
                "slope":          round(slope, 8),
                "anchors":        [{"idx": p1[0], "price": round(p1[1], 6)},
                                   {"idx": p2[0], "price": round(p2[1], 6)}],
                "current_value":  round(current_tl, 6),
                "price_distance": round(distance, 6),
                "near":           distance < 2 * abs(slope) * n if slope != 0 else False,
                "valid":          is_valid,
            })

        # ---- Trendline Haussiere : connexion des 2-3 derniers Swing Lows ----
        if len(swing_lows) >= 2:
            p1, p2 = swing_lows[-2], swing_lows[-1]
            slope  = (p2[1] - p1[1]) / max(p2[0] - p1[0], 1)
            current_tl  = p2[1] + slope * (n - 1 - p2[0])
            distance    = abs(current_price - current_tl)

            is_valid = slope > 0 and abs(slope) > 0.00001
            trendlines.append({
                "type":           "BULLISH_TL",
                "slope":          round(slope, 8),
                "anchors":        [{"idx": p1[0], "price": round(p1[1], 6)},
                                   {"idx": p2[0], "price": round(p2[1], 6)}],
                "current_value":  round(current_tl, 6),
                "price_distance": round(distance, 6),
                "near":           distance < 2 * abs(slope) * n if slope != 0 else False,
                "valid":          is_valid,
            })

        return [tl for tl in trendlines if tl["valid"]]

    # ==============================================================
    # E3 : ENGULFING (ABSORPTION INSTITUTIONNELLE)
    # ==============================================================

    def _detect_engulfing(self, df: pd.DataFrame, lookback: int = 5,
                           label: str = "H1") -> dict:
        """
        Detecte un pattern Engulfing (absorption) sur les N dernieres bougies.

        Un Engulfing est valide si :
          1. Le corps de la bougie courante est >= ENGULF_BODY_RATIO_MIN * corps precedent
          2. La direction est inversee par rapport a la bougie precedente
          3. (Optionnel) Le corps englobe toute la range (High-Low) precedent = Full Engulfing

        Priorite : on prend le plus recent et le plus fort.

        Returns:
            dict {type, strength, candle_idx, body_ratio} ou dict vide
        """
        if df is None or len(df) < 3:
            return {"type": "NONE"}

        scan_n = min(lookback, len(df) - 1)
        results = []

        opens  = df["open"].values
        closes = df["close"].values
        highs  = df["high"].values
        lows   = df["low"].values

        for i in range(len(df) - scan_n, len(df)):
            if i < 1:
                continue

            # Bougie courante
            curr_open  = opens[i]
            curr_close = closes[i]
            curr_body  = abs(curr_close - curr_open)

            # Bougie precedente
            prev_open  = opens[i - 1]
            prev_close = closes[i - 1]
            prev_body  = abs(prev_close - prev_open)

            if prev_body < 1e-8:
                continue   # Doji - ignorer

            ratio = curr_body / prev_body

            if ratio < ENGULF_BODY_RATIO_MIN:
                continue

            # Direction
            curr_bull = curr_close > curr_open
            prev_bull = prev_close > prev_open

            # Engulfing = directions opposees
            if curr_bull == prev_bull:
                continue

            # Full engulfing = corps courant contient tout le range precedent ?
            full_engulf = (
                curr_close >= max(prev_open, prev_close) and
                curr_open  <= min(prev_open, prev_close)
                if curr_bull else
                curr_close <= min(prev_open, prev_close) and
                curr_open  >= max(prev_open, prev_close)
            )

            strength = "STRONG" if ratio >= ENGULF_STRONG_RATIO or full_engulf else "MODERATE"
            engulf_type = "BULLISH_ENGULFING" if curr_bull else "BEARISH_ENGULFING"

            results.append({
                "type":       engulf_type,
                "strength":   strength,
                "candle_idx": i,
                "body_ratio": round(ratio, 2),
                "full":       full_engulf,
                "tf":         label,
                "close":      round(float(curr_close), 6),
            })

        if not results:
            return {"type": "NONE"}

        # Retourner le plus recent et le plus fort
        results.sort(key=lambda x: (
            -(len(df) - x["candle_idx"]),    # recence
            0 if x["strength"] == "STRONG" else 1,
        ))
        return results[0]

    # ==============================================================
    # CALCUL ATR (helper)
    # ==============================================================

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
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
        return atr if atr > 0 else 0.0001

    # ==============================================================
    # RESULTATS VIDES
    # ==============================================================

    def _empty_result(self, pair: str) -> dict:
        return {
            "pair":          pair,
            "timestamp":     datetime.now(timezone.utc).isoformat(),
            "price":         None,
            "round_numbers": [],
            "trendlines":    [],
            "engulfing":     {"H1": {"type": "NONE"}, "M15": {"type": "NONE"}},
        }

    # ==============================================================
    # API PUBLIQUE
    # ==============================================================

    def get_near_round_numbers(self, pair: str) -> list:
        """Retourne les chiffres ronds proches du prix actuel."""
        with self._lock:
            return [rn for rn in self._cache.get(pair, {}).get("round_numbers", [])
                    if rn.get("near")]

    def get_engulfing(self, pair: str,
                      tf: str = "H1",
                      direction: Optional[str] = None) -> dict:
        """
        Retourne le dernier Engulfing detecte.

        Args:
            direction: "BULLISH" ou "BEARISH" pour filtrer
        """
        with self._lock:
            eng = self._cache.get(pair, {}).get("engulfing", {}).get(tf, {"type": "NONE"})

        if direction:
            expected = f"{direction}_ENGULFING"
            if eng.get("type") != expected:
                return {"type": "NONE"}
        return eng

    def has_engulfing(self, pair: str,
                      direction: str,
                      tf: str = "H1") -> bool:
        """Booleen rapide pour kb5_engine."""
        eng = self.get_engulfing(pair, tf=tf, direction=direction)
        return eng.get("type") != "NONE"

    def get_active_trendlines(self, pair: str) -> list:
        """Retourne les trendlines actives (pres du prix)."""
        with self._lock:
            return [tl for tl in self._cache.get(pair, {}).get("trendlines", [])
                    if tl.get("valid")]

    def get_snapshot(self, pair: str) -> dict:
        """Snapshot compact pour le Dashboard."""
        with self._lock:
            data = dict(self._cache.get(pair, {}))
        if not data:
            return {"pair": pair, "status": "non analyse"}

        near_rounds  = [rn for rn in data.get("round_numbers", []) if rn.get("near")]
        eng_h1  = data.get("engulfing", {}).get("H1",  {})
        eng_m15 = data.get("engulfing", {}).get("M15", {})
        tls     = [tl for tl in data.get("trendlines", []) if tl.get("valid")]

        return {
            "pair":              pair,
            "price":             data.get("price"),
            "near_round_count":  len(near_rounds),
            "nearest_round":     near_rounds[0]["level"] if near_rounds else None,
            "engulf_h1":         eng_h1.get("type"),
            "engulf_h1_str":     eng_h1.get("strength"),
            "engulf_m15":        eng_m15.get("type"),
            "engulf_m15_str":    eng_m15.get("strength"),
            "trendlines":        len(tls),
            "tl_types":          [tl["type"] for tl in tls],
        }

    def clear_cache(self, pair: Optional[str] = None) -> None:
        with self._lock:
            if pair:
                self._cache.pop(pair, None)
            else:
                self._cache.clear()
