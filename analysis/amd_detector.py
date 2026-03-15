# analysis/amd_detector.py
"""
==============================================================
Sentinel Pro KB5 - Detecteur AMD (Power of 3 / Cycle ICT)
==============================================================
Responsabilites :
  - Detecter les 3 phases du cycle ICT journalier :
      A - Accumulation  : Range de consolidation (Asie / Pre-session)
      M - Manipulation  : Judas Swing contre le biais (boulot des algos)
      D - Distribution  : Expansion directionnelle vers le DOL

  APPROCHE STRUCTURELLE (Pas horaire rigide) :
    - La detection est basee sur la STRUCTURE DU PRIX (sweep + MSS),
      pas sur des horaires fixes.
    - Cela rend le module valide pour le Forex, l'Or, et les Cryptos
      (qui ne respectent pas les sessions classiques).
    - La fractalite est integree : on peut detecter l'AMD sur D1, H4, H1.

  Cascade de detection :
    1. Calculer le "Consolidation Range" depuis l'ouverture de la periode.
    2. Si le prix sort du range CONTRE le biais HTF = Manipulation detectee.
    3. Si le prix retourne dans le range + Market Structure Shift = Distribution.

Consomme par :
  - kb5_engine.py  (bonus CONFLUENCE_AMD, filtre anti-piegeage)
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
# CONSTANTES AMD
# ==============================================================

# Nombre de bougies H1 pour construire le range d'Accumulation
# par defaut (utilise comme fallback si la session Asie n'est pas dispo)
ACCUM_CANDLES_DEFAULT    = 4     # 4h depuis l'ouverture -> range de consolidation

# Taille max du range d'Accumulation en % de l'ATR pour etre "valide"
# Si le range est trop grand, c'est deja une tendance, pas une Accumulation
ACCUM_MAX_RANGE_ATR_MULT  = 2.0  # range H < 2.0 x ATR => vraie accumulation

# Mèche minimum pour valider la Manipulation (en % ATR)
MANIP_MIN_WICK_ATR        = 0.30  # la sortie du range doit faire >= 30% ATR

# Distance minimum de la cassure de structure pour valider la Distribution
MSS_MIN_DISTANCE_ATR      = 0.15  # le MSS doit etre > 15% ATR au-dela du range

# Nombre de bougies pour considerer la manipulation comme "ACTIVE" (recente)
MANIP_FRESH_CANDLES       = 8

# Score AMD : combien de bougies H1 a scruter dans l'historique
LOOKBACK_H1               = 48   # 2 jours glissants

# Phases AMD
PHASE_ACCUM   = "ACCUMULATION"
PHASE_MANIP   = "MANIPULATION"
PHASE_DISTRIB = "DISTRIBUTION"
PHASE_UNKNOWN = "UNKNOWN"

# Profils journaliers
PROFILE_AMD_BULL    = "AMD_BULLISH"    # Manipulation baisiere -> Distribution haussiere
PROFILE_AMD_BEAR    = "AMD_BEARISH"    # Manipulation haussiere -> Distribution baisiere
PROFILE_TRENDING    = "TRENDING"       # Pas de Judas Swing : tendance pure
PROFILE_UNKNOWN     = "UNKNOWN"

# Bonus de score pour kb5_engine
CONFLUENCE_AMD_DISTRIB  = 15   # On est en Distribution -> signal fort
CONFLUENCE_AMD_SETUP    = 10   # On est en fin de Manipulation -> setup imminent


# ==============================================================
# CLASSE PRINCIPALE
# ==============================================================

class AMDDetector:
    """
    Detecteur du cycle ICT Power of 3 (AMD).

    Il repond a des questions cles comme :
      "Est-ce que le mouvement actuel est un PIEGE (Manipulation)
       ou le VRAI mouvement institutionnel (Distribution) ?"

    La detection est STRUCTURELLE :
      - On identifie la zone d'Accumulation (range de consolidation)
      - On detecte si le prix a fait un faux mouvement contre le biais
      - On confirme la Distribution par un Market Structure Shift (MSS)

    Compatible Forex, Or, Crypto sans modification des heures.
    """

    def __init__(self,
                 data_store: DataStore,
                 bias_detector=None,
                 liquidity_detector=None):
        self._ds   = data_store
        self._bias = bias_detector           # BiasDetector pour le biais HTF
        self._liq  = liquidity_detector      # LiquidityDetector pour Asia Range + Sweeps
        self._lock = threading.RLock()
        self._cache: dict[str, dict] = {}
        logger.info("AMDDetector initialise - Power of 3 ICT actif")

    # ==============================================================
    # METHODE PRINCIPALE - ANALYSE AMD
    # ==============================================================

    def analyze(self, pair: str, tf: str = "H1") -> dict:
        """
        Analyse complete du cycle AMD pour une paire sur un timeframe.

        Args:
            pair: ex. "EURUSD", "XAUUSD", "BTCUSD"
            tf:   Timeframe d'analyse ("H1" par defaut, "H4" ou "D1" possibles)

        Returns:
            dict {phase, profile, accum_range, manip, distrib, confidence}
        """
        df = self._ds.get_candles(pair, tf)
        if df is None or len(df) < LOOKBACK_H1:
            logger.debug(f"AMDDetector - {pair}/{tf} | Donnees insuffisantes")
            return self._empty_result(pair, tf)

        atr = self._calculate_atr(df)

        # Biais directional HTF (demande au BiasDetector)
        htf_bias = self._get_htf_bias(pair)

        # ---- Etape 1 : Identifier le Range d'Accumulation ----
        accum = self._detect_accumulation(pair, df, atr)

        # ---- Etape 2 : Detecter la Manipulation (Judas Swing) ----
        manip = self._detect_manipulation(pair, df, atr, accum, htf_bias)

        # ---- Etape 3 : Detecter la Distribution (Expansion / MSS) ----
        distrib = self._detect_distribution(pair, df, atr, accum, manip, htf_bias)

        # ---- Etape 4 : Classifier la phase courante ----
        phase   = self._classify_phase(accum, manip, distrib)
        profile = self._classify_profile(manip, distrib, htf_bias)

        # ---- Confiance globale ----
        confidence = self._calculate_confidence(accum, manip, distrib, htf_bias)

        result = {
            "pair":        pair,
            "tf":          tf,
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "htf_bias":    htf_bias,
            "phase":       phase,
            "profile":     profile,
            "confidence":  confidence,
            "accum":       accum,
            "manip":       manip,
            "distrib":     distrib,
            "atr":         round(atr, 6),
        }

        with self._lock:
            self._cache[f"{pair}_{tf}"] = result

        logger.info(
            f"AMD - {pair}/{tf} | Phase: {phase} | Profile: {profile} | "
            f"Bias: {htf_bias} | Conf: {confidence}"
        )
        if manip.get("detected"):
            logger.info(
                f"  Judas Swing {manip['direction']} detecte ! "
                f"Range breake: {manip['break_level']} | Wick: {manip['wick_size_atr']:.2f}x ATR"
            )

        return result

    # ==============================================================
    # ETAPE 1 : ACCUMULATION (CONSOLIDATION RANGE)
    # ==============================================================

    def _detect_accumulation(self, pair: str, df: pd.DataFrame,
                              atr: float) -> dict:
        """
        Identifie le range de consolidation (phase A).

        Strategie :
          1. Utilise le Range d'Asie depuis LiquidityDetector si disponible.
          2. Sinon, prend le High/Low des N premieres bougies depuis l'ouverture
             de la session la plus recente (approche structurelle).
          3. Valide que le range est "serré" (< ACCUM_MAX_RANGE_ATR_MULT x ATR).

        Returns:
            dict {detected, high, low, mid, range_size, open_price, candles_count}
        """
        # Priorite 1 : Asia Range depuis LiquidityDetector
        if self._liq is not None:
            ar = self._liq.get_asia_range(pair)
            if ar and ar.get("high") and ar.get("low"):
                ar_range = ar["high"] - ar["low"]
                is_compressed = ar_range < (ACCUM_MAX_RANGE_ATR_MULT * atr)
                return {
                    "detected":     True,
                    "source":       "ASIA_RANGE",
                    "high":         ar["high"],
                    "low":          ar["low"],
                    "mid":          ar["mid"],
                    "range_size":   round(ar_range, 6),
                    "compressed":   is_compressed,
                    "open_price":   ar.get("mid"),
                    "candles_count": None,
                }

        # Priorite 2 : Calcul structurel depuis l'ouverture
        # Prendre les N premieres bougies de la session du jour
        n = self._get_accum_candle_count(pair)
        lookback = min(n, len(df))
        df_accum = df.iloc[-LOOKBACK_H1:]   # 2 jours glissants

        # Chercher la bougie d'ouverture de session (proche de minuit UTC)
        open_idx = self._find_session_open(df_accum)
        if open_idx is None:
            # Fallback absolu : prendre les N dernieres bougies comme accum
            accum_slice = df.iloc[-n:]
        else:
            # Prendre les N bougies depuis l'ouverture
            end_idx = min(open_idx + n, len(df_accum))
            accum_slice = df_accum.iloc[open_idx:end_idx]

        if len(accum_slice) < 2:
            return {"detected": False, "source": "NONE"}

        h = float(accum_slice["high"].max())
        l = float(accum_slice["low"].min())
        o = float(accum_slice["open"].iloc[0])
        mid = (h + l) / 2.0
        range_size = h - l
        is_compressed = range_size < (ACCUM_MAX_RANGE_ATR_MULT * atr)

        return {
            "detected":      is_compressed,    # Un range trop large n'est pas une Accum
            "source":        "STRUCTURAL",
            "high":          round(h, 6),
            "low":           round(l, 6),
            "mid":           round(mid, 6),
            "range_size":    round(range_size, 6),
            "compressed":    is_compressed,
            "open_price":    round(o, 6),
            "candles_count": len(accum_slice),
        }

    def _get_accum_candle_count(self, pair: str) -> int:
        """
        Nombre de bougies H1 pour l'accumulation selon le type d'actif.
        Crypto/Or = accumulation plus longue possible.
        """
        market_type = PAIR_MARKET_TYPE.get(pair, MarketType.FOREX)
        if market_type == MarketType.CRYPTO:
            return 6    # Crypto : accum peut durer jusqu'a 6h (pas de session fixe)
        elif market_type == MarketType.GOLD:
            return 5    # Or : sensible a 2 sessions, accum courte avant Londres
        else:
            return ACCUM_CANDLES_DEFAULT  # Forex/Indices : 4h suffisent

    def _find_session_open(self, df: pd.DataFrame) -> Optional[int]:
        """
        Cherche l'index de la bougie d'ouverture de session (minuit UTC ou 00h00).
        Retourne l'index dans le DataFrame ou None si introuvable.
        """
        try:
            times = df.index if hasattr(df.index, '__iter__') else df["time"]
            for i in range(len(df) - 1, max(len(df) - 30, -1), -1):
                t = pd.to_datetime(times[i])
                if t.hour == 0 and t.minute == 0:
                    return i
        except Exception as e:
            logger.debug(f"Session open introuvable : {e}")
        return None

    # ==============================================================
    # ETAPE 2 : MANIPULATION (JUDAS SWING)
    # ==============================================================

    def _detect_manipulation(self, pair: str, df: pd.DataFrame,
                              atr: float, accum: dict,
                              htf_bias: str) -> dict:
        """
        Detecte la phase de Manipulation (Judas Swing / Faux Breakout).

        Un Judas Swing est valide si :
          1. Le prix sort du range d'Accumulation.
          2. Ce mouvement est CONTRE le biais HTF (c'est le piege).
          3. Le prix revient ensuite a l'interieur du range (c'est le rejet).
          OU
          4. Un Liquidity Sweep FRESH est detecte contre le biais
             (delegation au LiquidityDetector).

        La detection est STRUCTURELLE, pas horaire.

        Returns:
            dict {detected, direction, break_level, reentry, wick_size_atr,
                  sweep_confirmed, fresh, candle_idx}
        """
        if not accum.get("detected"):
            # Pas de range d'accum = pas de manipulation detectee
            return {"detected": False, "reason": "Pas d'Accumulation definie"}

        accum_high = accum.get("high", 0)
        accum_low  = accum.get("low", 0)
        min_wick   = MANIP_MIN_WICK_ATR * atr

        highs  = df["high"].values
        lows   = df["low"].values
        closes = df["close"].values
        opens  = df["open"].values
        times  = df.index if hasattr(df.index, '__iter__') else df["time"].values

        # Scanner les MANIP_FRESH_CANDLES dernieres bougies
        scan_start = max(0, len(df) - MANIP_FRESH_CANDLES)

        manips_detected = []

        for i in range(scan_start, len(df)):
            h = highs[i]
            l = lows[i]
            c = closes[i]

            # JUDAS SWING BEARISH :
            # Prix monte AU-DESSUS du range d'Accum mais CLOTURE dedans ou en-dessous
            # ET le biais HTF est BULLISH (c'est un piege pour pousser a la vente)
            if htf_bias in ("BULLISH", "NEUTRAL") or htf_bias is None:
                wick_above = h - accum_high
                reentry    = c <= accum_high   # corps cloture sous le haut du range

                if wick_above >= min_wick and reentry:
                    is_fresh = i >= len(df) - (MANIP_FRESH_CANDLES // 2)
                    manips_detected.append({
                        "detected":       True,
                        "direction":      "BEARISH_MANIP",   # faux mouvement haussier
                        "intended_bias":  "BULLISH",          # la vraie intention est haussiere
                        "break_level":    round(accum_high, 6),
                        "break_price":    round(h, 6),
                        "reentry":        reentry,
                        "wick_size_atr":  round(wick_above / atr, 2) if atr else 0,
                        "close":          round(c, 6),
                        "candle_idx":     i,
                        "detected_at":    str(times[i]),
                        "fresh":          is_fresh,
                        "sweep_confirmed": False,   # sera mis a True via LiquidityDetector
                    })

            # JUDAS SWING BULLISH :
            # Prix s'effondre EN-DESSOUS du range d'Accum mais CLOTURE dedans ou au-dessus
            # ET le biais HTF est BEARISH (c'est un piege pour pousser a l'achat)
            if htf_bias in ("BEARISH", "NEUTRAL") or htf_bias is None:
                wick_below = accum_low - l
                reentry    = c >= accum_low    # corps cloture au-dessus du bas du range

                if wick_below >= min_wick and reentry:
                    is_fresh = i >= len(df) - (MANIP_FRESH_CANDLES // 2)
                    manips_detected.append({
                        "detected":       True,
                        "direction":      "BULLISH_MANIP",   # faux mouvement baissier
                        "intended_bias":  "BEARISH",          # la vraie intention est baisiere
                        "break_level":    round(accum_low, 6),
                        "break_price":    round(l, 6),
                        "reentry":        reentry,
                        "wick_size_atr":  round(wick_below / atr, 2) if atr else 0,
                        "close":          round(c, 6),
                        "candle_idx":     i,
                        "detected_at":    str(times[i]),
                        "fresh":          is_fresh,
                        "sweep_confirmed": False,
                    })

        if not manips_detected:
            # Fallback : verifier via LiquidityDetector si un Sweep existe
            if self._liq is not None:
                sweep_bull = self._liq.has_fresh_sweep(pair, direction="BULLISH")
                sweep_bear = self._liq.has_fresh_sweep(pair, direction="BEARISH")

                if sweep_bull and htf_bias == "BEARISH":
                    return {
                        "detected":       True,
                        "direction":      "BULLISH_MANIP",
                        "intended_bias":  "BEARISH",
                        "break_level":    accum_low,
                        "wick_size_atr":  None,
                        "fresh":          True,
                        "sweep_confirmed": True,
                        "source":         "LIQUIDITY_SWEEP",
                    }
                if sweep_bear and htf_bias == "BULLISH":
                    return {
                        "detected":       True,
                        "direction":      "BEARISH_MANIP",
                        "intended_bias":  "BULLISH",
                        "break_level":    accum_high,
                        "wick_size_atr":  None,
                        "fresh":          True,
                        "sweep_confirmed": True,
                        "source":         "LIQUIDITY_SWEEP",
                    }

            return {"detected": False, "reason": "Aucun Judas Swing detecte"}

        # Retourner la Manipulation la plus recente et la plus significative
        manips_detected.sort(key=lambda m: (
            0 if m["fresh"] else 1,
            -(m["wick_size_atr"] or 0)
        ))

        best = manips_detected[0]
        # Enrichissement via LiquidityDetector
        if self._liq is not None:
            liq_dir = "BEARISH" if "BULLISH_MANIP" in best["direction"] else "BULLISH"
            best["sweep_confirmed"] = self._liq.has_fresh_sweep(pair, direction=liq_dir)

        return best

    # ==============================================================
    # ETAPE 3 : DISTRIBUTION (MARKET STRUCTURE SHIFT)
    # ==============================================================

    def _detect_distribution(self, pair: str, df: pd.DataFrame,
                              atr: float, accum: dict,
                              manip: dict, htf_bias: str) -> dict:
        """
        Detecte la phase de Distribution (Expansion / MSS).

        La Distribution est validee par :
          1. Un Market Structure Shift (MSS) dans la direction du biais HTF.
          2. Ce MSS intervient APRES une Manipulation (Judas Swing).
          3. Le prix casse un High (BULL) ou un Low (BEAR) significatif
             de la structure H1 post-manipulation.

        Returns:
            dict {detected, direction, mss_level, expansion_started,
                  strength, candle_idx}
        """
        accum_high = accum.get("high")
        accum_low  = accum.get("low")

        # La Distribution ne peut pas etre confirmee sans range d'accum
        if accum_high is None or accum_low is None:
            return {"detected": False, "reason": "Range d'Accumulation non defini"}

        highs  = df["high"].values
        lows   = df["low"].values
        closes = df["close"].values
        times  = df.index if hasattr(df.index, '__iter__') else df["time"].values

        min_mss = MSS_MIN_DISTANCE_ATR * atr

        # On scanne les dernieres bougies (depuis la potentielle manipulation)
        manip_idx  = manip.get("candle_idx", max(0, len(df) - MANIP_FRESH_CANDLES))
        scan_start = manip_idx if manip.get("detected") else max(0, len(df) - LOOKBACK_H1)

        distributions = []

        # DISTRIBUTION BULLISH : MSS haussier (clôture au-dessus du range Accum HIGH)
        # ET biais = BULLISH
        if htf_bias in ("BULLISH", "NEUTRAL") or htf_bias is None:
            for i in range(scan_start, len(df)):
                c = closes[i]
                if c > accum_high + min_mss:
                    # MSS haussier confirme - le Distribution a commence
                    body_size = abs(c - float(df["open"].values[i]))
                    strength  = "STRONG" if body_size > (0.5 * atr) else "MODERATE"
                    distributions.append({
                        "detected":          True,
                        "direction":         "BULLISH",
                        "mss_level":         round(accum_high + min_mss, 6),
                        "close":             round(c, 6),
                        "expansion_started": True,
                        "strength":          strength,
                        "candle_idx":        i,
                        "detected_at":       str(times[i]),
                    })
                    break   # premier MSS suffit

        # DISTRIBUTION BEARISH : MSS baissier (clôture en-dessous du range Accum LOW)
        if htf_bias in ("BEARISH", "NEUTRAL") or htf_bias is None:
            for i in range(scan_start, len(df)):
                c = closes[i]
                if c < accum_low - min_mss:
                    body_size = abs(c - float(df["open"].values[i]))
                    strength  = "STRONG" if body_size > (0.5 * atr) else "MODERATE"
                    distributions.append({
                        "detected":          True,
                        "direction":         "BEARISH",
                        "mss_level":         round(accum_low - min_mss, 6),
                        "close":             round(c, 6),
                        "expansion_started": True,
                        "strength":          strength,
                        "candle_idx":        i,
                        "detected_at":       str(times[i]),
                    })
                    break

        if not distributions:
            return {
                "detected": False,
                "reason":   "Pas de MSS confirme (Distribution non active)",
            }

        # Retourner la Distribution la plus significative
        distributions.sort(key=lambda d: 0 if d["strength"] == "STRONG" else 1)
        return distributions[0]

    # ==============================================================
    # CLASSIFICATION DES PHASES ET PROFILS
    # ==============================================================

    def _classify_phase(self, accum: dict, manip: dict,
                         distrib: dict) -> str:
        """
        Determine la phase courante du cycle AMD.
        Logique sequentielle : A -> M -> D.
        """
        if distrib.get("detected"):
            return PHASE_DISTRIB
        if manip.get("detected") and manip.get("fresh"):
            return PHASE_MANIP
        if accum.get("detected"):
            return PHASE_ACCUM
        return PHASE_UNKNOWN

    def _classify_profile(self, manip: dict, distrib: dict,
                           htf_bias: str) -> str:
        """
        Determine le profil journalier (AMD_BULLISH, AMD_BEARISH, ...).
        """
        if distrib.get("detected"):
            if distrib["direction"] == "BULLISH":
                return PROFILE_AMD_BULL
            else:
                return PROFILE_AMD_BEAR

        if manip.get("detected"):
            # Si manipulation baisiere -> biais reel = BULLISH
            if manip["direction"] == "BEARISH_MANIP":
                return PROFILE_AMD_BULL
            else:
                return PROFILE_AMD_BEAR

        if htf_bias == "BULLISH":
            return PROFILE_AMD_BULL
        elif htf_bias == "BEARISH":
            return PROFILE_AMD_BEAR

        return PROFILE_UNKNOWN

    def _calculate_confidence(self, accum: dict, manip: dict,
                               distrib: dict, htf_bias: str) -> str:
        """
        Niveau de confiance du setup AMD.
        HIGH   = Accum + Manip + Distrib alignes avec Biais HTF
        MODERATE = 2 elements sur 3
        LOW    = 1 seul element
        NONE   = aucun
        """
        score = 0
        if accum.get("detected"):       score += 1
        if manip.get("detected"):       score += 1
        if distrib.get("detected"):     score += 2   # Distrib = confirmation finale
        if manip.get("sweep_confirmed"): score += 1  # Bonus si Sweep confirme la Manip

        if score >= 4:
            return "HIGH"
        elif score >= 2:
            return "MODERATE"
        elif score >= 1:
            return "LOW"
        return "NONE"

    # ==============================================================
    # BIAIS HTF
    # ==============================================================

    def _get_htf_bias(self, pair: str) -> str:
        """
        Recupere le biais HTF depuis BiasDetector.
        Fallback sur 'NEUTRAL' en cas d'indisponibilite.
        """
        if self._bias is None:
            return "NEUTRAL"
        try:
            bias_result = self._bias.get_bias(pair)
            if isinstance(bias_result, dict):
                return bias_result.get("direction", "NEUTRAL")
            return str(bias_result) if bias_result else "NEUTRAL"
        except Exception as e:
            logger.debug(f"BiasDetector indisponible pour {pair} : {e}")
            return "NEUTRAL"

    # ==============================================================
    # CALCUL ATR
    # ==============================================================

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

        return atr if atr > 0 else 0.0001

    # ==============================================================
    # RESULTATS VIDES
    # ==============================================================

    def _empty_result(self, pair: str, tf: str) -> dict:
        return {
            "pair":       pair,
            "tf":         tf,
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "htf_bias":   "NEUTRAL",
            "phase":      PHASE_UNKNOWN,
            "profile":    PROFILE_UNKNOWN,
            "confidence": "NONE",
            "accum":      {"detected": False},
            "manip":      {"detected": False},
            "distrib":    {"detected": False},
            "atr":        0.0,
        }

    # ==============================================================
    # API PUBLIQUE
    # ==============================================================

    def get_current_phase(self, pair: str, tf: str = "H1") -> str:
        """
        Retourne la phase AMD courante pour une paire.

        Returns:
            'ACCUMULATION', 'MANIPULATION', 'DISTRIBUTION', ou 'UNKNOWN'
        """
        with self._lock:
            result = self._cache.get(f"{pair}_{tf}", {})
        return result.get("phase", PHASE_UNKNOWN)

    def get_daily_profile(self, pair: str, tf: str = "H1") -> str:
        """
        Retourne le profil journalier AMD.

        Returns:
            'AMD_BULLISH', 'AMD_BEARISH', 'TRENDING', ou 'UNKNOWN'
        """
        with self._lock:
            result = self._cache.get(f"{pair}_{tf}", {})
        return result.get("profile", PROFILE_UNKNOWN)

    def is_manipulation_active(self, pair: str, tf: str = "H1") -> bool:
        """
        Verifie si une Manipulation (Judas Swing) est en cours.
        Utilise par kb5_engine pour eviter d'entrer sur un faux signal.

        Returns:
            True si une Manipulation FRESH est detectee
        """
        with self._lock:
            result = self._cache.get(f"{pair}_{tf}", {})
        manip = result.get("manip", {})
        return manip.get("detected", False) and manip.get("fresh", False)

    def is_distribution_active(self, pair: str, tf: str = "H1") -> bool:
        """
        Verifie si la phase de Distribution (Expansion) est active.
        C'est la fenetre optimale d'entree en trade.

        Returns:
            True si un Market Structure Shift confirme la Distribution
        """
        with self._lock:
            result = self._cache.get(f"{pair}_{tf}", {})
        distrib = result.get("distrib", {})
        return distrib.get("detected", False)

    def get_amd_state(self, pair: str, tf: str = "H1") -> dict:
        """
        Retourne l'etat AMD complet (pour kb5_engine et le Dashboard).

        Returns:
            dict complet {phase, profile, confidence, bias, accum, manip, distrib}
        """
        with self._lock:
            return dict(self._cache.get(f"{pair}_{tf}", {}))

    def get_snapshot(self, pair: str, tf: str = "H1") -> dict:
        """
        Snapshot compact pour le Dashboard Patron.

        Returns:
            dict resume AMD
        """
        with self._lock:
            data = dict(self._cache.get(f"{pair}_{tf}", {}))

        if not data:
            return {"pair": pair, "tf": tf, "status": "non analyse"}

        manip   = data.get("manip",   {})
        distrib = data.get("distrib", {})
        accum   = data.get("accum",   {})

        return {
            "pair":              pair,
            "tf":                tf,
            "phase":             data.get("phase"),
            "profile":           data.get("profile"),
            "confidence":        data.get("confidence"),
            "htf_bias":          data.get("htf_bias"),
            "accum_high":        accum.get("high"),
            "accum_low":         accum.get("low"),
            "accum_compressed":  accum.get("compressed"),
            "manip_detected":    manip.get("detected"),
            "manip_fresh":       manip.get("fresh"),
            "manip_direction":   manip.get("direction"),
            "manip_wick_atr":    manip.get("wick_size_atr"),
            "sweep_confirmed":   manip.get("sweep_confirmed"),
            "distrib_detected":  distrib.get("detected"),
            "distrib_direction": distrib.get("direction"),
            "distrib_strength":  distrib.get("strength"),
        }

    def clear_cache(self, pair: Optional[str] = None) -> None:
        """Vide le cache (appele par ReconnectManager)."""
        with self._lock:
            if pair:
                keys_to_delete = [k for k in self._cache if k.startswith(pair)]
                for k in keys_to_delete:
                    del self._cache[k]
            else:
                self._cache.clear()
