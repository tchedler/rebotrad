# analysis/irl_detector.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Détecteur IRL (Internal Range Liquidity)
══════════════════════════════════════════════════════════════
Responsabilités :
  - Cartographier la "liquidité interne" au mouvement actuel :
      · Anciens Fair Value Gaps (FVG) non remplis situés
        DANS le range de prix courant
      · Anciens petits sommets / creux INTERNES (Swing H/L internes)
        qui n'ont pas encore été sweepés
  - Calculer des cibles de Take Profit précises (IRL comme DOL)
  - Distinguer l'IRL (cible intermédiaire) de l'ERL (cible finale)

Concept ICT :
  Dans tout mouvement directionnel, le prix ne va PAS DIRECTEMENT
  à sa cible finale (ERL). Il va d'abord "régler ses affaires"
  en interne : remplir ses FVG, purger ses pools de liquidité
  internes. Ces points internes = "IRL" (Internal Range Liquidity).

  Exemple (mouvement BULLISH) :
    - ERL = le prochain PDH (cible finale)
    - IRL = l'ancien FVG Bearish de H4 encore ouvert
            + les EQL (Equal Lows) internes
    - Le prix va vers l'IRL D'ABORD, puis vers l'ERL.
    - Utiliser l'IRL comme PREMIER TP partiel, l'ERL comme TP final.

Consommé par :
  - kb5_engine.py (précision des Take Profit + bonus confluence)
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

# Timeframes pour l'analyse IRL (du LTF vers HTF)
IRL_TIMEFRAMES         = ["H1", "H4"]

# Bougies pour chercher les FVG internes
IRL_FVG_LOOKBACK       = 30     # Scanner les 30 dernières bougies pour FVG

# Taille minimale d'un FVG pour être considéré comme IRL cible (en % ATR)
IRL_FVG_MIN_ATR        = 0.20   # FVG > 20% ATR = significatif

# Nombre de niveaux IRL à retourner (TP1, TP2, TP3)
IRL_MAX_TARGETS        = 3

# Fenêtre pour les Swing Highs / Lows internes
IRL_SWING_LOOKBACK     = 4    # Swings plus "faibles" que MSS (moins de bougies de chaque côté)


# ══════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════

class IRLDetector:
    """
    Détecteur de Internal Range Liquidity pour Sentinel Pro KB5.

    Répond à la question :
      "Quelles sont les cibles intermédiaires RÉALISTES
       entre le prix actuel et l'objectif final (ERL) ?"

    Les IRL servent typiquement de :
      - TP1 partiel (clôturer 50% de la position)
      - Points de décision (continuer ou sortir ?)
      - Niveaux d'OTE pour re-entrer après un retour de prix
    """

    def __init__(self, data_store: DataStore, fvg_detector=None):
        self._ds   = data_store
        self._fvg  = fvg_detector    # FVGDetector optionnel pour les FVG existants
        self._lock = threading.RLock()
        self._cache: dict[str, dict] = {}
        logger.info("IRLDetector initialisé — Cartographie des liquidités internes")

    # ══════════════════════════════════════════════════════════
    # MÉTHODE PRINCIPALE
    # ══════════════════════════════════════════════════════════

    def analyze(self, pair: str, direction: str) -> dict:
        """
        Analyse l'IRL pour une paire dans une direction donnée.

        Args:
            pair:      ex. "EURUSD"
            direction: "BULLISH" ou "BEARISH"

        Returns:
            dict {targets, count, best_target, direction}
        """
        all_irl_targets = []

        for tf in IRL_TIMEFRAMES:
            df = self._ds.get_candles(pair, tf)
            if df is None or len(df) < 20:
                continue

            atr          = self._calculate_atr(df)
            current      = float(df["close"].iloc[-1])

            # ── Source 1 : FVG internes ─────────────────────
            fvg_targets  = self._find_fvg_irl(pair, tf, df, direction, current, atr)
            all_irl_targets.extend(fvg_targets)

            # ── Source 2 : Swing Highs / Lows internes ──────
            swing_targets = self._find_swing_irl(df, direction, current, atr, tf)
            all_irl_targets.extend(swing_targets)

        # Trier par proximité du prix actuel (cibles les plus proches = TP1, TP2...)
        current_price = self._get_current_price(pair)
        if current_price is not None:
            if direction == "BULLISH":
                # Targets au-dessus du prix, triées du plus proche au plus loin
                all_irl_targets = [t for t in all_irl_targets
                                   if t["level"] > current_price]
                all_irl_targets.sort(key=lambda t: t["level"])
            else:
                # Targets en-dessous du prix, triées du plus proche au plus loin
                all_irl_targets = [t for t in all_irl_targets
                                   if t["level"] < current_price]
                all_irl_targets.sort(key=lambda t: t["level"], reverse=True)

        # Dédupliquer (arrondi à 5 décimales pour comparer)
        seen    = set()
        unique  = []
        for t in all_irl_targets:
            key = round(t["level"], 4)
            if key not in seen:
                seen.add(key)
                unique.append(t)

        targets    = unique[:IRL_MAX_TARGETS]
        best       = targets[0] if targets else None

        result = {
            "pair":        pair,
            "direction":   direction,
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "targets":     targets,
            "count":       len(targets),
            "best_target": best,
        }

        with self._lock:
            self._cache[f"{pair}_{direction}"] = result

        self._ds.set_analysis(pair, f"irl_{direction.lower()}", result)

        if targets:
            logger.info(
                f"IRL — {pair} {direction} | {len(targets)} cibles internes | "
                f"TP1: {best.get('level')} ({best.get('type')}) | "
                f"Source: {best.get('tf')}"
            )

        return result

    # ══════════════════════════════════════════════════════════
    # SOURCE 1 : FVG INTERNES
    # ══════════════════════════════════════════════════════════

    def _find_fvg_irl(self, pair: str, tf: str, df: pd.DataFrame,
                       direction: str, current: float, atr: float) -> list:
        """
        Identifie les anciens FVG (Fair Value Gaps) qui n'ont pas encore
        été remplis et qui se situent entre le prix actuel et la cible finale.

        Un FVG Interne (IRL FVG) = zone de déséquilibre que le prix
        va probablement "visiter" avant d'aller plus loin.

        Returns:
            list de dicts {level, type, tf, source, priority}
        """
        targets = []
        highs   = df["high"].values
        lows    = df["low"].values
        closes  = df["close"].values
        n       = len(df)

        min_fvg_size = IRL_FVG_MIN_ATR * atr

        # Scanner les bougies récentes pour FVG
        scan_start = max(0, n - IRL_FVG_LOOKBACK)

        # BULLISH IRL → chercher des FVG Bearish non remplis EN-DESSOUS
        # (zones de déséquilibre haussier que le prix pourrait toucher)
        if direction == "BULLISH":
            for i in range(scan_start + 1, n - 1):
                # FVG Bullish (BISI) : high[i-1] < low[i+1]
                # (trou entre deux bougies → zone non remplie)
                gap_low  = float(highs[i - 1])
                gap_high = float(lows[i + 1])

                if gap_high < gap_low:  # pas de FVG ici
                    continue
                gap_size = gap_high - gap_low

                if gap_size < min_fvg_size:
                    continue

                mid = (gap_low + gap_high) / 2.0

                # Vérifier que ce FVG est ENCORE OUVERT (pas rempli)
                # → le prix n'est pas passé dans cette zone depuis
                recent_lows = lows[i + 1:]
                still_open  = all(float(l) > gap_low for l in recent_lows)

                if still_open and mid < current:
                    targets.append({
                        "level":    round(mid, 6),
                        "top":      round(gap_high, 6),
                        "bottom":   round(gap_low, 6),
                        "size_atr": round(gap_size / atr, 2),
                        "type":     "IRL_FVG_BULLISH",
                        "tf":       tf,
                        "source":   "FVG",
                        "priority": "HIGH" if gap_size > atr else "MODERATE",
                        "candle_idx": i,
                    })

        # BEARISH IRL → chercher des FVG Bullish non remplis AU-DESSUS
        else:  # "BEARISH"
            for i in range(scan_start + 1, n - 1):
                # FVG Bearish (SIBI) : low[i-1] > high[i+1]
                gap_high = float(lows[i - 1])
                gap_low  = float(highs[i + 1])

                if gap_low > gap_high:  # pas de FVG ici
                    continue
                gap_size = gap_high - gap_low

                if gap_size < min_fvg_size:
                    continue

                mid = (gap_low + gap_high) / 2.0

                # Vérifier que ce FVG est encore ouvert
                recent_highs = highs[i + 1:]
                still_open   = all(float(h) < gap_high for h in recent_highs)

                if still_open and mid > current:
                    targets.append({
                        "level":    round(mid, 6),
                        "top":      round(gap_high, 6),
                        "bottom":   round(gap_low, 6),
                        "size_atr": round(gap_size / atr, 2),
                        "type":     "IRL_FVG_BEARISH",
                        "tf":       tf,
                        "source":   "FVG",
                        "priority": "HIGH" if gap_size > atr else "MODERATE",
                        "candle_idx": i,
                    })

        return targets

    # ══════════════════════════════════════════════════════════
    # SOURCE 2 : SWING HIGHS / LOWS INTERNES
    # ══════════════════════════════════════════════════════════

    def _find_swing_irl(self, df: pd.DataFrame, direction: str,
                         current: float, atr: float, tf: str) -> list:
        """
        Identifie les Swing Highs / Lows internes non encore sweepés.
        Ces niveaux agissent comme de petits aimants de liquidité
        sur le chemin vers la cible finale (ERL).

        Returns:
            list de dicts {level, type, tf, source}
        """
        targets = []
        highs   = df["high"].values
        lows    = df["low"].values
        n       = len(df)
        lb      = IRL_SWING_LOOKBACK

        scan_start = max(lb, n - IRL_FVG_LOOKBACK)
        scan_end   = n - lb

        if direction == "BULLISH":
            # Les Equal Highs et Swing Highs internes sont des cibles BULLISH
            for i in range(scan_start, scan_end):
                h = float(highs[i])
                # Swing High local
                if h == max(highs[max(0, i - lb): min(n, i + lb + 1)]):
                    if h > current:  # Ce swing est AU-DESSUS du prix → cible
                        targets.append({
                            "level":    round(h, 6),
                            "type":     "IRL_SWING_HIGH",
                            "tf":       tf,
                            "source":   "SWING",
                            "priority": "MODERATE",
                            "candle_idx": i,
                        })
        else:  # BEARISH
            # Les Swing Lows internes sont des cibles BEARISH
            for i in range(scan_start, scan_end):
                l = float(lows[i])
                # Swing Low local
                if l == min(lows[max(0, i - lb): min(n, i + lb + 1)]):
                    if l < current:  # Ce swing est EN-DESSOUS du prix → cible
                        targets.append({
                            "level":    round(l, 6),
                            "type":     "IRL_SWING_LOW",
                            "tf":       tf,
                            "source":   "SWING",
                            "priority": "MODERATE",
                            "candle_idx": i,
                        })

        return targets

    # ══════════════════════════════════════════════════════════
    # UTILITAIRES
    # ══════════════════════════════════════════════════════════

    def _get_current_price(self, pair: str) -> Optional[float]:
        """Retourne le dernier prix connu pour une paire."""
        df = self._ds.get_candles(pair, "H1")
        if df is None or df.empty:
            df = self._ds.get_candles(pair, "M15")
        if df is None or df.empty:
            return None
        return float(df["close"].iloc[-1])

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

    def get_irl_targets(self, pair: str, direction: str) -> list:
        """
        Retourne les cibles IRL ordonnées pour une paire.

        Args:
            pair:      ex. "EURUSD"
            direction: "BULLISH" ou "BEARISH"

        Returns:
            liste de dicts cible IRL (TP1 = index 0, TP2 = index 1...)
        """
        with self._lock:
            data = self._cache.get(f"{pair}_{direction}", {})
        return data.get("targets", [])

    def get_best_target(self, pair: str, direction: str) -> Optional[dict]:
        """
        Retourne la meilleure cible IRL (TP1 le plus proche).

        Returns:
            dict cible ou None
        """
        targets = self.get_irl_targets(pair, direction)
        return targets[0] if targets else None

    def get_tp1_level(self, pair: str, direction: str) -> Optional[float]:
        """
        Retourne le niveau de prix du premier TP (IRL le plus proche).

        Returns:
            float niveau ou None
        """
        best = self.get_best_target(pair, direction)
        return best.get("level") if best else None

    def has_irl_target(self, pair: str, direction: str) -> bool:
        """
        Vérifie si au moins une cible IRL existe dans la direction donnée.

        Returns:
            True si au moins un IRL cible disponible
        """
        return len(self.get_irl_targets(pair, direction)) > 0

    def get_snapshot(self, pair: str, direction: str) -> dict:
        """Snapshot compact pour le dashboard."""
        with self._lock:
            data = dict(self._cache.get(f"{pair}_{direction}", {}))
        if not data:
            return {"pair": pair, "direction": direction, "count": 0}
        return {
            "pair":        pair,
            "direction":   direction,
            "count":       data.get("count", 0),
            "tp1":         data.get("best_target", {}).get("level"),
            "tp1_type":    data.get("best_target", {}).get("type"),
            "tp1_tf":      data.get("best_target", {}).get("tf"),
        }

    def clear_cache(self, pair: Optional[str] = None) -> None:
        """Vide le cache."""
        with self._lock:
            if pair:
                keys = [k for k in self._cache if k.startswith(pair)]
                for k in keys:
                    del self._cache[k]
            else:
                self._cache.clear()
