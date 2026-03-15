# analysis/bias_detector.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Détecteur de Biais Directionnel
══════════════════════════════════════════════════════════════
Responsabilités :
  - Calculer le biais Weekly (W1/D1)
  - Calculer le biais Daily (D1/H4)
  - Calculer le biais SOD par session (Asia/London/NY)
  - Détecter l'alignement HTF (Weekly + Daily + SOD)
  - Identifier Premium / Discount par rapport au range HTF
  - Détecter les Killzones ICT actives
  - Signaler les Bias Shifts (CHoCH / MSS intraday)
  - Pousser résultats dans DataStore pour KB5Engine

Logique ICT de biais :
  BULLISH  → prix cherche à purger les BSL (Buy Side Liquidity)
             = anciens highs, equal highs, stops au-dessus du marché
  BEARISH  → prix cherche à purger les SSL (Sell Side Liquidity)
             = anciens lows, equal lows, stops en-dessous du marché

Dépendances :
  - DataStore    → get_candles(), set_analysis()
  - FVGDetector  → FVG HTF pour confirmation biais
  - OBDetector   → OB HTF pour confluence
  - config.constants → Trading, Sessions

Consommé par :
  - kb5_engine.py
  - scoring_engine.py
  - killswitch_engine.py (SOD alignment check)
══════════════════════════════════════════════════════════════
"""

import logging
import threading
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Optional

from datastore.data_store import DataStore
from config.constants import Trading

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# CONSTANTES — SESSIONS ICT (heures UTC réelles)
# Source : CME Group + ICT Mentorships (UTC = EST+5)
# ══════════════════════════════════════════════════════════════

SESSIONS = {
    "ASIA":         {"start_utc": 21, "end_utc": 7,  "label": "21h00-07h00 UTC"},
    "LONDON":       {"start_utc":  7, "end_utc": 16, "label": "07h00-16h00 UTC"},
    "OVERLAP":      {"start_utc": 12, "end_utc": 16, "label": "12h00-16h00 UTC (LDN+NY max liquidité)"},
    "NEW_YORK":     {"start_utc": 12, "end_utc": 21, "label": "12h00-21h00 UTC"},
}

# Killzones ICT — fenêtres précises de manipulation / entrée
# Toutes les heures sont en UTC. Source : ICT 2022 Mentorship.
KILLZONES = {
    "ASIA_RANGE":   {"start_utc": 21, "end_utc": 0},   # 21h00-00h00 UTC
    "LONDON_OPEN":  {"start_utc":  7, "end_utc": 10},  # 07h00-10h00 UTC (= 02h-05h EST)
    "NY_OPEN":      {"start_utc": 12, "end_utc": 16},  # 12h00-16h00 UTC (= 07h-11h EST)
    "LONDON_CLOSE": {"start_utc": 15, "end_utc": 16},  # 15h00-16h00 UTC (= 10h-11h EST)
}

# Seuils biais
BIAS_STRONG_THRESHOLD  = 0.65  # > 65% du range → biais fort
BIAS_NEUTRAL_THRESHOLD = 0.45  # 45-65% → neutre
PREMIUM_LEVEL          = 0.50  # au-dessus de 50% = premium (vendre)
DISCOUNT_LEVEL         = 0.50  # en-dessous de 50% = discount (acheter)

# Timeframes utilisés par niveau
TF_WEEKLY  = "W"
TF_DAILY   = "D1"
TF_H4      = "H4"
TF_H1      = "H1"
TF_M15     = "M15"

# ══════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════

class BiasDetector:
    """
    Calcule le biais directionnel multi-niveau selon la méthode ICT.
    Produit un BiasResult complet utilisé par KB5Engine pour
    pondérer les scores de chaque timeframe de la pyramide.
    """

    def __init__(self, data_store: DataStore,
                 fvg_detector=None,
                 ob_detector=None):
        self._ds   = data_store
        self._fvg  = fvg_detector
        self._ob   = ob_detector
        self._lock = threading.RLock()
        self._cache: dict[str, dict] = {}
        logger.info("BiasDetector initialisé")

    # ══════════════════════════════════════════════════════════
    # MÉTHODE PRINCIPALE
    # ══════════════════════════════════════════════════════════

    def analyze_pair(self, pair: str) -> dict:
        """
        Analyse complète du biais pour une paire.
        Calcule weekly, daily, SOD, alignment, premium/discount.

        Args:
            pair: ex. "EURUSD"

        Returns:
            dict BiasResult complet
        """
        now_utc = datetime.now(timezone.utc)

        weekly_bias  = self._get_weekly_bias(pair)
        daily_bias   = self._get_daily_bias(pair)
        sod_bias     = self._get_sod_bias(pair, now_utc)
        alignment    = self._check_alignment(weekly_bias, daily_bias, sod_bias)
        pd_zone      = self._get_premium_discount(pair)
        killzone     = self._get_active_killzone(now_utc)
        session      = self._get_active_session(now_utc)
        bias_shift   = self._detect_bias_shift(pair)

        result = {
            "pair":         pair,
            "timestamp":    now_utc.isoformat(),

            # Biais par niveau
            "weekly_bias":  weekly_bias,
            "daily_bias":   daily_bias,
            "sod_bias":     sod_bias,

            # Confluence
            "aligned":      alignment["aligned"],
            "alignment":    alignment,

            # Premium / Discount
            "pd_zone":      pd_zone,

            # Session ICT
            "session":      session,
            "killzone":     killzone,
            "in_killzone":  killzone is not None,

            # Bias Shift
            "bias_shift":   bias_shift,

            # Score de biais (0→100, utilisé par KB5Engine)
            "bias_score":   self._calculate_bias_score(
                                weekly_bias, daily_bias,
                                sod_bias, alignment, pd_zone
                            ),
        }

        with self._lock:
            self._cache[pair] = result

        self._ds.set_analysis(pair, "bias", result)

        logger.info(
            f"Biais analysé — {pair} | "
            f"W:{weekly_bias['direction']} "
            f"D:{daily_bias['direction']} "
            f"SOD:{sod_bias['direction']} | "
            f"Aligné:{alignment['aligned']} | "
            f"Zone:{pd_zone['zone']} | "
            f"Score:{result['bias_score']}"
        )

        return result

    # ══════════════════════════════════════════════════════════
    # BIAIS WEEKLY
    # ══════════════════════════════════════════════════════════

    def _get_weekly_bias(self, pair: str) -> dict:
        """
        Calcule le biais de la semaine en analysant la structure (HH/HL ou LH/LL)
        des dernières semaines, pas juste mathématiquement (ICT rule).

        Returns:
            dict {direction, strength, range_pct, details}
        """
        df_w = self._ds.get_candles(pair, TF_WEEKLY)
        df_d = self._ds.get_candles(pair, TF_DAILY)

        if df_w is None or len(df_w) < 4:
            return self._neutral_bias("WEEKLY", "données W1 insuffisantes")

        # Regarder les 3 dernières bougies complètes + la bougie en cours
        highs = df_w["high"].values[-4:]
        lows  = df_w["low"].values[-4:]
        closes = df_w["close"].values[-4:]
        opens = df_w["open"].values[-4:]

        # Structure W1: HH/HL vs LH/LL sur les 3 dernières semaines
        hh = highs[-1] > highs[-2]
        hl = lows[-1]  > lows[-2]
        lh = highs[-1] < highs[-2]
        ll = lows[-1]  < lows[-2]

        direction = "NEUTRAL"
        strength  = "WEAK"

        if hh and hl:
            direction = "BULLISH"
            strength  = "STRONG"
        elif lh and ll:
            direction = "BEARISH"
            strength  = "STRONG"
        elif hh:
            direction = "BULLISH"
            strength  = "MODERATE"
        elif ll:
            direction = "BEARISH"
            strength  = "MODERATE"

        # Position dans le range pour nuancer (Premium/Discount de la bougie hebdo)
        week_range = highs[-1] - lows[-1] if highs[-1] != lows[-1] else 0.0001
        range_pct  = (closes[-1] - lows[-1]) / week_range

        # Confirmation D1 : trend sur les 3 derniers jours pour valider la direction weekly
        d1_confirms = False
        if df_d is not None and len(df_d) >= 3:
            last_3 = df_d.iloc[-3:]
            d1_trend = last_3["close"].iloc[-1] - last_3["open"].iloc[0]
            d1_confirms = (
                (direction == "BULLISH" and d1_trend > 0) or
                (direction == "BEARISH" and d1_trend < 0)
            )

        if not d1_confirms and strength == "STRONG":
            strength = "MODERATE" # rétrograder si D1 ne suit pas le W1

        return {
            "direction":   direction,
            "strength":    strength,
            "range_pct":   round(range_pct, 3),
            "week_high":   round(highs[-1],  6),
            "week_low":    round(lows[-1],   6),
            "week_open":   round(opens[-1],  6),
            "week_close":  round(closes[-1], 6),
            "d1_confirms": d1_confirms,
            "level":       "WEEKLY",
        }

    # ══════════════════════════════════════════════════════════
    # BIAIS DAILY
    # ══════════════════════════════════════════════════════════

    def _get_daily_bias(self, pair: str) -> dict:
        """
        Calcule le biais du jour en cours via D1 et H4.

        Logique :
          - Bougie D1 en cours : position relative dans le range
          - Confirmation H4 : 2 dernières bougies H4 dans le même sens
          - FVG H4 frais dans la direction → +1 confirmation

        Returns:
            dict {direction, strength, range_pct, h4_confirms, details}
        """
        df_d  = self._ds.get_candles(pair, TF_DAILY)
        df_h4 = self._ds.get_candles(pair, TF_H4)

        if df_d is None or len(df_d) < 2:
            return self._neutral_bias("DAILY", "données D1 insuffisantes")

        # Bougie D1 en cours
        day_open  = df_d["open"].iloc[-1]
        day_high  = df_d["high"].iloc[-1]
        day_low   = df_d["low"].iloc[-1]
        day_close = df_d["close"].iloc[-1]
        day_range = day_high - day_low if day_high != day_low else 0.0001

        range_pct = (day_close - day_low) / day_range

        # Direction D1
        if day_close > day_open:
            d1_direction = "BULLISH"
        elif day_close < day_open:
            d1_direction = "BEARISH"
        else:
            d1_direction = "NEUTRAL"

        # Force basée sur position dans le range
        if range_pct > BIAS_STRONG_THRESHOLD or range_pct < (1 - BIAS_STRONG_THRESHOLD):
            strength = "STRONG"
        else:
            strength = "MODERATE"

        # Confirmation H4
        h4_confirms = False
        h4_direction = "NEUTRAL"
        if df_h4 is not None and len(df_h4) >= 3:
            last_h4 = df_h4.iloc[-3:]
            h4_trend = last_h4["close"].iloc[-1] - last_h4["open"].iloc[0]
            h4_direction = "BULLISH" if h4_trend > 0 else "BEARISH"
            h4_confirms  = h4_direction == d1_direction

        # Confirmation FVG H4 frais
        fvg_confirms = False
        if self._fvg:
            fresh_fvg = self._fvg.get_fresh_fvg(pair, TF_H4, d1_direction)
            fvg_confirms = len(fresh_fvg) > 0

        # Direction finale avec confirmations
        direction = d1_direction
        if not h4_confirms and not fvg_confirms:
            strength = "WEAK"

        return {
            "direction":    direction,
            "strength":     strength,
            "range_pct":    round(range_pct,   3),
            "day_high":     round(day_high,    6),
            "day_low":      round(day_low,     6),
            "day_open":     round(day_open,    6),
            "day_close":    round(day_close,   6),
            "h4_confirms":  h4_confirms,
            "h4_direction": h4_direction,
            "fvg_confirms": fvg_confirms,
            "level":        "DAILY",
        }

    # ══════════════════════════════════════════════════════════
    # BIAIS SOD (START OF DAY / SESSION)
    # ══════════════════════════════════════════════════════════

    def _get_sod_bias(self, pair: str, now_utc: datetime) -> dict:
        """
        Calcule le biais SOD pour la session en cours.
        Basé sur les 3 premières bougies H1 de la session active.

        Logique ICT SOD :
          - Identifier la session active (Asia/London/NY)
          - Prendre les 2-3 premières bougies H1 de la session
          - Analyser la structure : HH/HL = BULLISH, LH/LL = BEARISH
          - Cross-check avec OB H1 frais dans la direction

        Returns:
            dict {direction, strength, session, details}
        """
        df_h1 = self._ds.get_candles(pair, TF_H1)
        session = self._get_active_session(now_utc)

        if df_h1 is None or len(df_h1) < 6:
            return self._neutral_bias("SOD", "données H1 insuffisantes")

        # Prendre les 4 dernières bougies H1 fermées
        recent = df_h1.iloc[-5:-1]  # exclure la bougie en cours

        highs  = recent["high"].values
        lows   = recent["low"].values
        closes = recent["close"].values

        # Structure H1 : HH/HL ou LH/LL
        hh = highs[-1] > highs[-2]   # Higher High
        hl = lows[-1]  > lows[-2]    # Higher Low
        lh = highs[-1] < highs[-2]   # Lower High
        ll = lows[-1]  < lows[-2]    # Lower Low

        if hh and hl:
            direction = "BULLISH"
            strength  = "STRONG"
        elif lh and ll:
            direction = "BEARISH"
            strength  = "STRONG"
        elif hh or hl:
            direction = "BULLISH"
            strength  = "MODERATE"
        elif lh or ll:
            direction = "BEARISH"
            strength  = "MODERATE"
        else:
            direction = "NEUTRAL"
            strength  = "WEAK"

        # Confirmation OB H1
        ob_confirms = False
        if self._ob and direction != "NEUTRAL":
            valid_ob = self._ob.get_valid_ob(pair, TF_H1, direction)
            ob_confirms = len(valid_ob) > 0

        return {
            "direction":   direction,
            "strength":    strength,
            "session":     session,
            "hh": hh, "hl": hl, "lh": lh, "ll": ll,
            "ob_confirms": ob_confirms,
            "recent_high": round(float(highs.max()),  6),
            "recent_low":  round(float(lows.min()),   6),
            "level":       "SOD",
        }

    # ══════════════════════════════════════════════════════════
    # ALIGNMENT CHECK
    # ══════════════════════════════════════════════════════════

    def _check_alignment(self, weekly: dict,
                          daily: dict, sod: dict) -> dict:
        """
        Vérifie l'alignement des 3 niveaux de biais.
        L'alignement complet = confluence maximale ICT.

        Niveaux d'alignement :
          FULL    : Weekly + Daily + SOD identiques → score max
          PARTIAL : 2 sur 3 alignés → score modéré
          NONE    : aucun alignement → NO-TRADE probable

        Returns:
            dict {aligned, level, direction, details}
        """
        w_dir = weekly["direction"]
        d_dir = daily["direction"]
        s_dir = sod["direction"]

        # Ignorer NEUTRAL pour l'alignement
        directions = [d for d in (w_dir, d_dir, s_dir) if d != "NEUTRAL"]

        if not directions:
            return {"aligned": False, "level": "NONE",
                    "direction": "NEUTRAL", "score": 0}

        # Compter les votes par direction
        bull_count = sum(1 for d in directions if d == "BULLISH")
        bear_count = sum(1 for d in directions if d == "BEARISH")

        if bull_count == 3:
            return {
                "aligned":   True,
                "level":     "FULL",
                "direction": "BULLISH",
                "score":     100,
                "details":   f"W:{w_dir} D:{d_dir} SOD:{s_dir}",
            }
        elif bear_count == 3:
            return {
                "aligned":   True,
                "level":     "FULL",
                "direction": "BEARISH",
                "score":     100,
                "details":   f"W:{w_dir} D:{d_dir} SOD:{s_dir}",
            }
        elif bull_count == 2:
            return {
                "aligned":   True,
                "level":     "PARTIAL",
                "direction": "BULLISH",
                "score":     65,
                "details":   f"W:{w_dir} D:{d_dir} SOD:{s_dir}",
            }
        elif bear_count == 2:
            return {
                "aligned":   True,
                "level":     "PARTIAL",
                "direction": "BEARISH",
                "score":     65,
                "details":   f"W:{w_dir} D:{d_dir} SOD:{s_dir}",
            }
        else:
            return {
                "aligned":   False,
                "level":     "NONE",
                "direction": "NEUTRAL",
                "score":     0,
                "details":   f"W:{w_dir} D:{d_dir} SOD:{s_dir}",
            }

    # ══════════════════════════════════════════════════════════
    # PREMIUM / DISCOUNT
    # ══════════════════════════════════════════════════════════

    def _get_premium_discount(self, pair: str) -> dict:
        """
        Détermine si le prix actuel est en zone Premium ou Discount
        par rapport au range D1 (règle ICT fondamentale).

        Premium  (> 50% du range D1) → zone de vente optimale
        Discount (< 50% du range D1) → zone d'achat optimale
        Equilibrium (= 50%)          → zone neutre, éviter

        Returns:
            dict {zone, pct, optimal_for, day_range}
        """
        df_d = self._ds.get_candles(pair, TF_DAILY)
        if df_d is None or len(df_d) < 2:
            return {"zone": "UNKNOWN", "pct": 0.5,
                    "optimal_for": "NEUTRAL"}

        day_high  = df_d["high"].iloc[-1]
        day_low   = df_d["low"].iloc[-1]
        day_range = day_high - day_low if day_high != day_low else 0.0001
        current   = df_d["close"].iloc[-1]

        pct = (current - day_low) / day_range

        if pct > PREMIUM_LEVEL + 0.05:
            zone = "PREMIUM"
            optimal_for = "BEARISH"
        elif pct < DISCOUNT_LEVEL - 0.05:
            zone = "DISCOUNT"
            optimal_for = "BULLISH"
        else:
            zone = "EQUILIBRIUM"
            optimal_for = "NEUTRAL"

        return {
            "zone":        zone,
            "pct":         round(pct,      3),
            "current":     round(current,  6),
            "day_high":    round(day_high, 6),
            "day_low":     round(day_low,  6),
            "optimal_for": optimal_for,
        }

    # ══════════════════════════════════════════════════════════
    # SESSIONS ET KILLZONES
    # ══════════════════════════════════════════════════════════

    def _get_active_session(self, now_utc: datetime) -> str:
        """
        Retourne le nom de la session ICT active en UTC.
        Basé sur les vraies heures de marché (UTC) :
          ASIA     : 21h00 - 07h00 UTC (traverse minuit)
          LONDON   : 07h00 - 16h00 UTC
          OVERLAP  : 12h00 - 16h00 UTC (chevauchement London+NY)
          NEW_YORK : 12h00 - 21h00 UTC
          OFF_HOURS: Hors sessions actives

        Returns:
            str session name
        """
        hour = now_utc.hour

        # Chevauchement London / NY (liquidité maximale)
        if 12 <= hour < 16:
            return "OVERLAP_LDN_NY"

        # Session New York AM  (après overlap)
        if 16 <= hour < 21:
            return "NEW_YORK"

        # Session Londres (avant overlap)
        if 7 <= hour < 12:
            return "LONDON"

        # Session Asie (traverse minuit : 21h → 07h)
        if hour >= 21 or hour < 7:
            return "ASIA"

        return "OFF_HOURS"

    def _get_active_killzone(self, now_utc: datetime) -> Optional[str]:
        """
        Retourne la Killzone ICT active ou None.

        Returns:
            str nom killzone ou None
        """
        hour = now_utc.hour
        for kz_name, kz in KILLZONES.items():
            start = kz["start_utc"]
            end   = kz["end_utc"]
            if start <= end:
                if start <= hour < end:
                    return kz_name
            else:  # passage minuit (ex: ASIA 20h→23h)
                if hour >= start or hour < end:
                    return kz_name
        return None

    # ══════════════════════════════════════════════════════════
    # BIAS SHIFT (CHoCH / MSS)
    # ══════════════════════════════════════════════════════════

    def _detect_bias_shift(self, pair: str) -> dict:
        """
        Détecte un changement de biais intraday via H1/M15.

        CHoCH (Change of Character) : premier signe de retournement
        MSS  (Market Structure Shift) : confirmation du retournement

        Un Bias Shift est détecté quand :
          - Tendance H1 était BULLISH
          - Price casse le dernier Higher Low sur H1
          → Potentiel retournement BEARISH

        Returns:
            dict {detected, type, direction, strength}
        """
        df_h1 = self._ds.get_candles(pair, TF_H1)
        if df_h1 is None or len(df_h1) < 10:
            return {"detected": False, "type": None,
                    "direction": None, "strength": None}

        closes = df_h1["close"].values[-10:]
        highs  = df_h1["high"].values[-10:]
        lows   = df_h1["low"].values[-10:]

        # Détecter la tendance sur les 10 dernières bougies
        trend_slope = np.polyfit(range(len(closes)), closes, 1)[0]
        prior_trend = "BULLISH" if trend_slope > 0 else "BEARISH"

        # Vérifier rupture de structure
        recent_high = highs[-4:-1].max()
        recent_low  = lows[-4:-1].min()
        last_close  = closes[-1]
        last_high   = highs[-1]
        last_low    = lows[-1]

        choch_detected = False
        shift_direction = None

        if prior_trend == "BULLISH" and last_low < recent_low:
            choch_detected  = True
            shift_direction = "BEARISH"
        elif prior_trend == "BEARISH" and last_high > recent_high:
            choch_detected  = True
            shift_direction = "BULLISH"

        if choch_detected:
            logger.warning(
                f"Bias Shift détecté — {pair} | "
                f"Ancien biais : {prior_trend} | "
                f"Nouveau : {shift_direction}"
            )

        return {
            "detected":     choch_detected,
            "type":         "CHoCH" if choch_detected else None,
            "prior_trend":  prior_trend,
            "direction":    shift_direction,
            "strength":     "MODERATE" if choch_detected else None,
        }

    # ══════════════════════════════════════════════════════════
    # CALCUL SCORE BIAIS
    # ══════════════════════════════════════════════════════════

    def _calculate_bias_score(self, weekly: dict, daily: dict,
                               sod: dict, alignment: dict,
                               pd_zone: dict) -> int:
        """
        Calcule un score de biais 0→100 basé sur :
          - Alignement HTF (40 pts max)
          - Force des biais individuels (30 pts max)
          - Position Premium/Discount cohérente (20 pts max)
          - Confirmation par structure (10 pts max)

        Returns:
            int score 0→100
        """
        score = 0

        # Alignement HTF (40 pts)
        score += alignment.get("score", 0) * 0.40

        # Force biais individuel (30 pts)
        strength_map = {"STRONG": 10, "MODERATE": 6, "WEAK": 2}
        score += strength_map.get(weekly["strength"], 0)
        score += strength_map.get(daily["strength"],  0)
        score += strength_map.get(sod["strength"],    0)

        # Premium/Discount cohérent avec biais (20 pts)
        aligned_dir = alignment.get("direction", "NEUTRAL")
        pd_optimal  = pd_zone.get("optimal_for", "NEUTRAL")
        if aligned_dir == pd_optimal and aligned_dir != "NEUTRAL":
            score += 20
        elif pd_zone.get("zone") == "EQUILIBRIUM":
            score += 5   # zone neutre → pénalité partielle

        return min(int(score), 100)

    # ══════════════════════════════════════════════════════════
    # UTILITAIRES
    # ══════════════════════════════════════════════════════════

    def _neutral_bias(self, level: str, reason: str) -> dict:
        """Retourne un biais neutre standardisé avec raison."""
        logger.debug(f"Biais neutre — {level} | Raison : {reason}")
        return {
            "direction": "NEUTRAL",
            "strength":  "WEAK",
            "level":     level,
            "reason":    reason,
        }

    # ══════════════════════════════════════════════════════════
    # API PUBLIQUE
    # ══════════════════════════════════════════════════════════

    def get_bias(self, pair: str) -> Optional[dict]:
        """
        Retourne le dernier BiasResult calculé pour une paire.

        Returns:
            dict BiasResult ou None si jamais calculé
        """
        with self._lock:
            return dict(self._cache.get(pair, {})) or None

    def get_direction(self, pair: str) -> str:
        """
        Retourne uniquement la direction alignée.
        Raccourci pour scoring_engine et kb5_engine.

        Returns:
            "BULLISH", "BEARISH", ou "NEUTRAL"
        """
        with self._lock:
            result = self._cache.get(pair, {})
        return result.get("alignment", {}).get("direction", "NEUTRAL")

    def is_aligned(self, pair: str) -> bool:
        """
        Vérifie si les 3 niveaux sont alignés.
        Utilisé par killswitch_engine (KS6 — contre-tendance HTF).

        Returns:
            True si alignement FULL ou PARTIAL
        """
        with self._lock:
            result = self._cache.get(pair, {})
        return result.get("aligned", False)

    def is_in_killzone(self) -> bool:
        """
        Vérifie si on est actuellement dans une Killzone ICT.
        Utilisé par scoring_engine pour bonus de timing.

        Returns:
            True si dans une Killzone
        """
        now = datetime.now(timezone.utc)
        return self._get_active_killzone(now) is not None

    def get_pd_zone(self, pair: str) -> str:
        """
        Retourne la zone Premium/Discount actuelle.
        Utilisé par kb5_engine pour validation entrée.

        Returns:
            "PREMIUM", "DISCOUNT", "EQUILIBRIUM", ou "UNKNOWN"
        """
        with self._lock:
            result = self._cache.get(pair, {})
        return result.get("pd_zone", {}).get("zone", "UNKNOWN")

    def get_bias_score(self, pair: str) -> int:
        """
        Retourne le score de biais 0→100.
        Consommé directement par scoring_engine.

        Returns:
            int 0→100
        """
        with self._lock:
            result = self._cache.get(pair, {})
        return result.get("bias_score", 0)

    def get_snapshot(self, pair: str) -> dict:
        """
        Snapshot complet pour Dashboard Patron.

        Returns:
            dict résumé biais
        """
        with self._lock:
            result = dict(self._cache.get(pair, {}))

        if not result:
            return {"pair": pair, "status": "non calculé"}

        return {
            "pair":        pair,
            "weekly":      result.get("weekly_bias", {}).get("direction"),
            "daily":       result.get("daily_bias",  {}).get("direction"),
            "sod":         result.get("sod_bias",    {}).get("direction"),
            "aligned":     result.get("aligned"),
            "direction":   result.get("alignment", {}).get("direction"),
            "pd_zone":     result.get("pd_zone",   {}).get("zone"),
            "session":     result.get("session"),
            "killzone":    result.get("killzone"),
            "bias_score":  result.get("bias_score"),
            "bias_shift":  result.get("bias_shift", {}).get("detected"),
        }

    def clear_cache(self, pair: str = None) -> None:
        """
        Vide le cache biais. Appelé au début de chaque nouvelle session.
        """
        with self._lock:
            if pair:
                self._cache.pop(pair, None)
                logger.info(f"Bias cache vidé — Paire : {pair}")
            else:
                self._cache.clear()
                logger.info("Bias cache vidé — toutes les paires")

    def __repr__(self) -> str:
        pairs = list(self._cache.keys())
        return f"BiasDetector(pairs={pairs})"
