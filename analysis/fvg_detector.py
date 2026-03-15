# analysis/fvg_detector.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Détecteur FVG (Fair Value Gap)
══════════════════════════════════════════════════════════════
Responsabilités :
  - Détecter FVG Bullish (BISI) et Bearish (SIBI) sur tous les TF
  - Classifier chaque FVG : FRESH / MITIGATED / INVALID
  - Filtrer les micro-gaps via seuil ATR
  - Pousser les résultats dans DataStore pour KB5Engine
  - Exposer get_fresh_fvg() pour bias_detector et kb5_engine

Dépendances :
  - DataStore  → get_candles(), set_analysis()
  - config.constants → Trading, Gateway

Consommé par :
  - bias_detector.py
  - kb5_engine.py
  - scoring_engine.py
══════════════════════════════════════════════════════════════
"""

import logging
import threading
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional

from datastore.data_store import DataStore
from config.constants import Trading, Gateway

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# CONSTANTES LOCALES
# ══════════════════════════════════════════════════════════════

FVG_FRESH      = "FRESH"
FVG_INVALID    = "INVALID"     # price a comblé 50%+ du gap (CE)

ATR_MIN_FACTOR = 0.30          # FVG < 30% ATR ignoré (bruit)
ATR_PERIOD     = 14            # période ATR standard

# ══════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════

class FVGDetector:
    """
    Détecte et classe les Fair Value Gaps (FVG) ICT sur tous les
    timeframes actifs. Un FVG est un déséquilibre de prix créé par
    une bougie impulsive entre 3 bougies consécutives.

    FVG Bullish (BISI — Buy Side Imbalance, Sell Side Inefficiency) :
        gap entre high[i] et low[i+2], bougie i+1 ne comble pas.

    FVG Bearish (SIBI — Sell Side Imbalance, Buy Side Inefficiency) :
        gap entre low[i] et high[i+2], bougie i+1 ne comble pas.
    """

    def __init__(self, data_store: DataStore):
        self._ds        = data_store
        self._lock      = threading.RLock()
        self._cache: dict[str, dict[str, list]] = {}
        # Format : _cache[pair][tf] = [list of FVG dicts]
        logger.info("FVGDetector initialisé")

    # ══════════════════════════════════════════════════════════
    # MÉTHODE PRINCIPALE — SCAN COMPLET
    # ══════════════════════════════════════════════════════════

    def scan_pair(self, pair: str) -> dict:
        """
        Scan tous les timeframes actifs pour une paire.
        Retourne un dict {tf: [fvg_list]} avec statuts à jour.

        Args:
            pair: ex. "EURUSD"

        Returns:
            dict avec clés = TF, valeurs = liste de FVG dicts
        """
        results: dict[str, list] = {}

        for tf in Trading.TIMEFRAMES:
            df = self._ds.get_candles(pair, tf)
            if df is None or len(df) < ATR_PERIOD + 3:
                logger.debug(f"FVG scan ignoré — {pair} {tf} | bougies insuffisantes")
                continue

            fvg_list = self._detect_fvg(pair, tf, df)

            # Si Timeframe H1 ou inférieur, on détecte aussi les True Gaps (NWOG/NDOG)
            # car ils nécessitent une granularité horaire/m15 pour être précis
            if tf in [Trading.TF_H1, Trading.TF_M15]:
                atr = self._calculate_atr(df)
                true_gaps = self._detect_true_gaps(pair, tf, df, atr)
                fvg_list.extend(true_gaps)

            fvg_list = self._update_statuses(fvg_list, df)
            results[tf] = fvg_list

            logger.debug(
                f"FVG scan — {pair} {tf} | "
                f"total={len(fvg_list)} | "
                f"fresh={sum(1 for f in fvg_list if f['status'] == FVG_FRESH)}"
            )

        with self._lock:
            if pair not in self._cache:
                self._cache[pair] = {}

            # Fusionner avec les FVGs existants dans le cache
            for tf, new_fvg_list in results.items():
                existing_list = self._cache[pair].get(tf, [])
                
                # Indexer par ID pour éviter les doublons
                master_dict = {f["id"]: f for f in existing_list}
                for f in new_fvg_list:
                    if f["id"] not in master_dict:
                        master_dict[f["id"]] = f
                
                # Mettre à jour les statuts sur TOUS les FVGs (anciens et nouveaux)
                # Note: df est différent pour chaque TF, donc on le gère dans la boucle TF
                df = self._ds.get_candles(pair, tf)
                final_list = self._update_statuses(list(master_dict.values()), df)
                
                # Pour KB5, on ne garde que les FRESH
                self._cache[pair][tf] = [
                    f for f in final_list 
                    if f["status"] == FVG_FRESH
                ]

        # Pousser le cache complet (fusionné) dans DataStore
        with self._lock:
            self._ds.set_analysis(pair, "fvg", self._cache[pair])

        return self._cache[pair]

    # ══════════════════════════════════════════════════════════
    # DÉTECTION FVG BRUTE
    # ══════════════════════════════════════════════════════════

    def _detect_fvg(self, pair: str, tf: str, df: pd.DataFrame) -> list:
        """
        Parcourt les bougies et détecte tous les FVG valides.
        Filtre les micro-gaps < ATR_MIN_FACTOR * ATR.

        Args:
            pair: symbole
            tf:   timeframe string
            df:   DataFrame avec colonnes [open, high, low, close]

        Returns:
            liste de dicts FVG
        """
        fvg_list = []
        atr = self._calculate_atr(df) if "atr" not in locals() else atr
        min_gap_size = ATR_MIN_FACTOR * atr

        highs  = df["high"].values
        lows   = df["low"].values
        closes = df["close"].values
        times  = df.index if hasattr(df.index, '__iter__') else df["time"].values

        # Scan de i=0 à len-3 (on a besoin de i, i+1, i+2)
        for i in range(len(df) - 2):
            # ── FVG Bullish (BISI) ──────────────────────────
            # Condition : low[i+2] > high[i]
            gap_low  = highs[i]
            gap_high = lows[i + 2]

            if gap_high > gap_low:
                gap_size = gap_high - gap_low
                if gap_size >= min_gap_size:
                    fvg_list.append({
                        "id":        f"FVG_BULL_{pair}_{tf}_{str(times[i+1])}",
                        "pair":      pair,
                        "tf":        tf,
                        "type":      "BISI",
                        "direction": "BULLISH",
                        "top":       round(gap_high, 6),
                        "bottom":    round(gap_low,  6),
                        "midpoint":  round((gap_high + gap_low) / 2, 6),
                        "size":      round(gap_size, 6),
                        "atr_ratio": round(gap_size / atr, 2) if atr > 0 else 0,
                        "formed_at": str(times[i + 1]),
                        "candle_idx": i,
                        "status":    FVG_FRESH,
                        "mitigated_at": None,
                        "invalid_at":   None,
                    })

            # ── FVG Bearish (SIBI) ──────────────────────────
            # Condition : high[i+2] < low[i]
            gap_high2 = lows[i]
            gap_low2  = highs[i + 2]

            if gap_high2 > gap_low2:
                gap_size = gap_high2 - gap_low2
                if gap_size >= min_gap_size:
                    fvg_list.append({
                        "id":        f"FVG_BEAR_{pair}_{tf}_{str(times[i+1])}",
                        "pair":      pair,
                        "tf":        tf,
                        "type":      "SIBI",
                        "direction": "BEARISH",
                        "top":       round(gap_high2, 6),
                        "bottom":    round(gap_low2,  6),
                        "midpoint":  round((gap_high2 + gap_low2) / 2, 6),
                        "size":      round(gap_size, 6),
                        "atr_ratio": round(gap_size / atr, 2) if atr > 0 else 0,
                        "formed_at": str(times[i + 1]),
                        "candle_idx": i,
                        "status":    FVG_FRESH,
                        "mitigated_at": None,
                        "invalid_at":   None,
                    })

        return fvg_list

    # ══════════════════════════════════════════════════════════
    # DÉTECTION TRUE GAPS (NWOG / NDOG)
    # ══════════════════════════════════════════════════════════

    def _detect_true_gaps(self, pair: str, tf: str, df: pd.DataFrame, atr: float) -> list:
        """
        Détecte les NWOG (New Week Opening Gap) et NDOG (New Day Opening Gap).
        Contrairement aux FVG classiques, un True Gap est l'espace entre le
        Close de la veille/semaine précédente et le Open du jour/semaine actuel.
        Ces gaps attirent très fortement le prix.
        """
        gaps = []
        min_gap_size = ATR_MIN_FACTOR * atr

        opens  = df["open"].values
        closes = df["close"].values
        times  = df.index if hasattr(df.index, '__iter__') else df["time"].values

        for i in range(1, len(df)):
            try:
                # Convertir time en datetime pandas
                t_prev = pd.to_datetime(times[i - 1])
                t_curr = pd.to_datetime(times[i])
            except Exception:
                continue

            # Détection de changement de jour / semaine
            is_new_day  = t_curr.date() > t_prev.date()
            # La première bougie de la semaine en Forex ouvre souvent
            # le dimanche soir ou lundi de très bonne heure (selon fuseau)
            # Différence de jour >= 2 indique un week-end passé
            is_new_week = (t_curr.date() - t_prev.date()).days >= 2

            if not is_new_day:
                continue

            gap_type = "NWOG" if is_new_week else "NDOG"
            c_prev   = closes[i - 1]
            o_curr   = opens[i]

            # Si le prix d'ouverture est différent du prix de clôture précédent
            gap_size = abs(o_curr - c_prev)

            if gap_size >= min_gap_size:
                direction = "BULLISH" if o_curr > c_prev else "BEARISH"
                top = max(o_curr, c_prev)
                bot = min(o_curr, c_prev)

                gaps.append({
                    "id":         f"GAP_{gap_type}_{pair}_{tf}_{str(t_curr)}",
                    "pair":       pair,
                    "tf":         tf,
                    "type":       gap_type,
                    "direction":  direction,
                    "top":        round(top, 6),
                    "bottom":     round(bot, 6),
                    "midpoint":   round((top + bot) / 2, 6),
                    "size":       round(gap_size, 6),
                    "atr_ratio":  round(gap_size / atr, 2) if atr > 0 else 0,
                    "formed_at":  str(t_curr),
                    "candle_idx": i,
                    "status":     FVG_FRESH,
                    "mitigated_at": None,
                    "invalid_at":   None,
                })

        return gaps

    # ══════════════════════════════════════════════════════════
    # MISE À JOUR DES STATUTS
    # ══════════════════════════════════════════════════════════

    def _update_statuses(self, fvg_list: list, df: pd.DataFrame) -> list:
        """
        Met à jour le statut de chaque FVG selon le prix actuel :
          - FRESH      : prix n'a pas atteint le midpoint
          - MITIGATED  : prix a touché ≥ 50% du gap
          - INVALID    : prix a comblé 100% du gap

        Args:
            fvg_list: liste de FVG détectés
            df:       DataFrame bougie (prix récents en fin)

        Returns:
            liste mise à jour
        """
        if df.empty or not fvg_list:
            return fvg_list

        # Prix récents (bougies après formation du FVG)
        recent_highs = df["high"].values
        recent_lows  = df["low"].values
        times        = df.index if hasattr(df.index, '__iter__') else df["time"].values

        for fvg in fvg_list:
            idx   = fvg.get("candle_idx", 0) + 2  # bougies après le FVG
            top   = fvg["top"]
            bot   = fvg["bottom"]
            mid   = fvg["midpoint"]

            # Si le FVG est trop ancien et n'a plus de candle_idx valide dans ce DF,
            # on commence le scan au début du DF actuel
            start_j = max(0, idx)
            if start_j >= len(df):
                start_j = 0

            # Parcourir les bougies POST-formation
            for j in range(start_j, len(df)):
                h = recent_highs[j]
                l = recent_lows[j]

                if fvg["direction"] == "BULLISH":
                    # Invalidation à 50% (Consequent Encroachment)
                    if l <= mid:
                        fvg["status"]     = FVG_INVALID
                        fvg["invalid_at"] = str(times[j])
                        break

                else:  # BEARISH
                    # Invalidation à 50% (Consequent Encroachment)
                    if h >= mid:
                        fvg["status"]     = FVG_INVALID
                        fvg["invalid_at"] = str(times[j])
                        break

        return fvg_list

    # ══════════════════════════════════════════════════════════
    # CALCUL ATR
    # ══════════════════════════════════════════════════════════

    def _calculate_atr(self, df: pd.DataFrame, period: int = ATR_PERIOD) -> float:
        """
        Calcule l'ATR Wilder (RMA) sur `period` bougies.
        Utilisé pour filtrer les micro-FVG non significatifs.

        Returns:
            float ATR, ou 0.0001 si calcul impossible (fallback sûr)
        """
        if len(df) < period + 1:
            return 0.0001

        high  = df["high"].values
        low   = df["low"].values
        close = df["close"].values

        tr_list = []
        for i in range(1, len(df)):
            tr = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i]  - close[i - 1])
            )
            tr_list.append(tr)

        # Wilder's RMA : seed avec SMA(period), puis lissage exponentiel
        atr = float(np.mean(tr_list[:period]))
        for tr in tr_list[period:]:
            atr = (atr * (period - 1) + tr) / period

        return atr if atr > 0 else 0.0001

    # ══════════════════════════════════════════════════════════
    # API PUBLIQUE — ACCÈS RÉSULTATS
    # ══════════════════════════════════════════════════════════

    def get_fresh_fvg(self, pair: str, tf: str,
                      direction: Optional[str] = None) -> list:
        """
        Retourne les FVG FRESH pour une paire/TF.
        Optionnellement filtré par direction ('BULLISH' ou 'BEARISH').

        Args:
            pair:      ex. "EURUSD"
            tf:        ex. "H1"
            direction: "BULLISH", "BEARISH", ou None (tous)

        Returns:
            liste de FVG dicts avec status=FRESH
        """
        with self._lock:
            tf_data = self._cache.get(pair, {}).get(tf, [])

        fresh = [f for f in tf_data if f["status"] == FVG_FRESH]

        if direction:
            fresh = [f for f in fresh if f["direction"] == direction]

        return fresh

    def get_nearest_fvg(self, pair: str, tf: str,
                        current_price: float,
                        direction: Optional[str] = None) -> Optional[dict]:
        """
        Retourne le FVG FRESH le plus proche du prix actuel.
        Utilisé par KB5Engine pour trouver le point d'entrée optimal.

        Args:
            pair:          ex. "EURUSD"
            tf:            ex. "H1"
            current_price: prix bid actuel
            direction:     filtre directionnel optionnel

        Returns:
            dict FVG le plus proche, ou None
        """
        fresh = self.get_fresh_fvg(pair, tf, direction)
        if not fresh:
            return None

        nearest = min(
            fresh,
            key=lambda f: abs(f["midpoint"] - current_price)
        )
        return nearest

    def get_all_fvg(self, pair: str, tf: str,
                    status: Optional[str] = None) -> list:
        """
        Retourne tous les FVG d'une paire/TF, optionnellement
        filtré par statut (FRESH / MITIGATED / INVALID).

        Args:
            pair:   ex. "EURUSD"
            tf:     ex. "H4"
            status: filtre statut optionnel

        Returns:
            liste complète de FVG dicts
        """
        with self._lock:
            tf_data = list(self._cache.get(pair, {}).get(tf, []))

        if status:
            tf_data = [f for f in tf_data if f["status"] == status]

        return tf_data

    def get_fvg_count(self, pair: str, tf: str) -> dict:
        """
        Retourne un résumé des comptages par statut.
        Utilisé par scoring_engine pour évaluer la densité FVG.

        Returns:
            dict {fresh: N, mitigated: N, invalid: N, total: N}
        """
        all_fvg = self.get_all_fvg(pair, tf)
        return {
            "fresh":     sum(1 for f in all_fvg if f["status"] == FVG_FRESH),
            "invalid":   sum(1 for f in all_fvg if f["status"] == FVG_INVALID),
            "total":     len(all_fvg),
        }

    def get_snapshot(self, pair: str) -> dict:
        """
        Snapshot complet pour Dashboard Patron.
        Retourne un résumé par TF avec comptes et FVG frais.

        Returns:
            dict {tf: {count, fresh_list}}
        """
        snapshot = {}
        with self._lock:
            pair_data = dict(self._cache.get(pair, {}))

        for tf, fvg_list in pair_data.items():
            fresh = [f for f in fvg_list if f["status"] == FVG_FRESH]
            snapshot[tf] = {
                "total":    len(fvg_list),
                "fresh":    len(fresh),
                "fresh_fvg": fresh[-3:],  # derniers 3 FVG frais max
            }

        return snapshot

    # ══════════════════════════════════════════════════════════
    # UTILITAIRES
    # ══════════════════════════════════════════════════════════

    def clear_cache(self, pair: Optional[str] = None) -> None:
        """
        Vide le cache FVG pour une paire ou toutes les paires.
        Appelé par ReconnectManager après rechargement des bougies.
        """
        with self._lock:
            if pair:
                self._cache.pop(pair, None)
                logger.info(f"FVG cache vidé — Paire : {pair}")
            else:
                self._cache.clear()
                logger.info("FVG cache vidé — toutes les paires")

    def __repr__(self) -> str:
        pairs = list(self._cache.keys())
        return f"FVGDetector(pairs={pairs}, timeframes={Trading.TIMEFRAMES})"
