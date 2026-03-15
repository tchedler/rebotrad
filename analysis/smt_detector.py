# analysis/smt_detector.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Détecteur SMT Divergence Matrix
══════════════════════════════════════════════════════════════
Responsabilités :
  - Détecter les SMT Divergences entre paires corrélées
  - Classifier la force : WEAK / MODERATE / STRONG
  - Déduire la direction du signal institutionnel
  - Valider uniquement dans la fenêtre temporelle récente
  - Pousser résultats dans DataStore pour KB5Engine

SMT (Smart Money Technique) Divergence :
  Quand deux instruments corrélés sont censés faire un nouveau
  high/low ensemble, mais l'un d'eux échoue → signal que les
  institutions ont manipulé le prix d'un côté pour piéger les
  retail traders avant un mouvement dans la direction opposée.

Matrice de corrélations KB5 :
  EURUSD  ↔  GBPUSD   (corrélation positive forte)
  EURUSD  ↔  USDCHF   (corrélation négative forte)
  XAUUSD  ↔  USDX     (corrélation négative)
  US30    ↔  NAS100   (corrélation positive)
  USOIL   ↔  USDCAD   (corrélation négative)
  BTCUSD  ↔  NAS100   (corrélation positive)

Dépendances :
  - DataStore  → get_candles(), set_analysis()
  - config.constants → Trading

Consommé par :
  - bias_detector.py
  - kb5_engine.py
  - scoring_engine.py
══════════════════════════════════════════════════════════════
"""

import logging
import threading
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Optional

from datastore.data_store import DataStore
from config.constants import Trading

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# MATRICE DE CORRÉLATIONS KB5
# ══════════════════════════════════════════════════════════════

SMT_PAIRS_MATRIX = [
    # ── FOREX (Devise contrepartie USD) ──
    ("EURUSD", "GBPUSD",  "POSITIVE",  1.0),  # La paire SMT la plus surveillée
    ("AUDUSD", "NZDUSD",  "POSITIVE",  0.9),  # Océanie / Matières premières
    ("USDJPY", "USDCHF",  "POSITIVE",  0.8),  # Confirmation force intrinsèque USD
    
    # Dollar Index (Corrélation inverse)
    ("EURUSD", "DXYm",    "NEGATIVE",  1.0),  # SMT majeur : Actif vs Index
    ("GBPUSD", "DXYm",    "NEGATIVE",  0.9),  

    # ── INDICES BOURSIERS (Fortement corrélés) ──
    ("NAS100", "US500",   "POSITIVE",  1.0),  # NQ vs ES — Duo de base
    ("US30",   "US500",   "POSITIVE",  0.9),  # Dow vs S&P
    ("NAS100", "US30",    "POSITIVE",  0.8),  # Tech vs Industrie

    # ── MATIÈRES PREMIÈRES ──
    ("XAUUSD", "XAGUSD",  "POSITIVE",  0.9),  # Or vs Argent

    # ── CRYPTOMONNAIES ──
    ("BTCUSD", "ETHUSD",  "POSITIVE",  0.9),  # Bitcoin vs Ethereum (Leader vs Altcoins)
]

# Timeframes valides pour SMT (pas en dessous de H1 → trop de bruit)
SMT_VALID_TIMEFRAMES = ["H1", "H4", "D1", "W1"]

# Fenêtre de recherche (bougies récentes)
SMT_LOOKBACK        = 5    # cherche divergence sur 5 dernières bougies
ATR_PERIOD          = 14
SMT_WEAK_THRESHOLD  = 0.3  # divergence < 30% ATR → WEAK
SMT_STRONG_THRESHOLD= 1.0  # divergence ≥ 100% ATR → STRONG

# ══════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════

class SMTDetector:
    """
    Détecte les SMT Divergences entre paires corrélées.
    Chaque signal SMT identifie une manipulation institutionnelle
    et prédit la direction probable du mouvement réel.
    """

    def __init__(self, data_store: DataStore):
        self._ds   = data_store
        self._lock = threading.RLock()
        self._cache: dict[str, list] = {}
        # Format : _cache[pair] = [list of SMT signal dicts]
        logger.info("SMTDetector initialisé")

    # ══════════════════════════════════════════════════════════
    # MÉTHODE PRINCIPALE — SCAN COMPLET
    # ══════════════════════════════════════════════════════════

    def scan_pair(self, pair: str) -> list:
        """
        Scan toutes les corrélations impliquant `pair` sur tous
        les TF valides. Retourne la liste des SMT détectés.

        Args:
            pair: ex. "EURUSD"

        Returns:
            liste de dicts SMT signal
        """
        all_signals = []

        # Trouver toutes les paires corrélées à `pair`
        correlations = self._get_correlations_for(pair)

        for pair_a, pair_b, corr_type, weight in correlations:
            for tf in SMT_VALID_TIMEFRAMES:
                df_a = self._ds.get_candles(pair_a, tf)
                df_b = self._ds.get_candles(pair_b, tf)

                if df_a is None or df_b is None:
                    continue
                if len(df_a) < ATR_PERIOD + SMT_LOOKBACK:
                    continue
                if len(df_b) < ATR_PERIOD + SMT_LOOKBACK:
                    continue

                signal = self._detect_smt(
                    pair_a, pair_b, tf,
                    df_a, df_b,
                    corr_type, weight
                )

                if signal:
                    all_signals.append(signal)
                    logger.info(
                        f"SMT détecté — {pair_a}/{pair_b} {tf} | "
                        f"Direction : {signal['signal_direction']} | "
                        f"Force : {signal['strength']} | "
                        f"Divergence : {signal['divergence_pct']}%"
                    )

        with self._lock:
            self._cache[pair] = all_signals

        self._ds.set_analysis(pair, "smt", all_signals)
        return all_signals

    def scan_all(self) -> dict:
        """
        Scan global de toutes les paires actives.
        Évite les doublons : chaque paire scannée une seule fois.

        Returns:
            dict {pair: [smt_signals]}
        """
        results = {}
        scanned_pairs = set()

        for pair_a, pair_b, _, _ in SMT_PAIRS_MATRIX:
            for pair in (pair_a, pair_b):
                if pair not in scanned_pairs and pair in Trading.ACTIVE_PAIRS:
                    results[pair] = self.scan_pair(pair)
                    scanned_pairs.add(pair)

        return results

    # ══════════════════════════════════════════════════════════
    # DÉTECTION SMT DIVERGENCE
    # ══════════════════════════════════════════════════════════

    def _detect_smt(self, pair_a: str, pair_b: str, tf: str,
                    df_a: pd.DataFrame, df_b: pd.DataFrame,
                    corr_type: str, weight: float) -> Optional[dict]:
        """
        Compare les extremes récents de deux paires corrélées.
        Détecte si l'une confirme un nouveau high/low et l'autre échoue.

        Logique SMT :
          Corrélation POSITIVE  (EURUSD / GBPUSD) :
            - A fait new HIGH   → B échoue à faire new HIGH
              → Signal BEARISH sur A (manipulation haussière)
            - A fait new LOW    → B échoue à faire new LOW
              → Signal BULLISH sur A (manipulation baissière)

          Corrélation NEGATIVE (EURUSD / USDCHF) :
            - A fait new HIGH   → B échoue à faire new LOW
              → Signal BEARISH sur A
            - A fait new LOW    → B échoue à faire new HIGH
              → Signal BULLISH sur A

        Args:
            pair_a, pair_b : paires à comparer
            tf             : timeframe
            df_a, df_b     : DataFrames bougies
            corr_type      : "POSITIVE" ou "NEGATIVE"
            weight         : poids signal (0.0 → 1.0)

        Returns:
            dict signal SMT ou None si pas de divergence
        """
        atr_a = self._calculate_atr(df_a)

        # Fenêtre récente
        recent_a = df_a.iloc[-SMT_LOOKBACK:]
        recent_b = df_b.iloc[-SMT_LOOKBACK:]

        # Extremes sur la fenêtre récente
        high_a = recent_a["high"].max()
        low_a  = recent_a["low"].min()
        high_b = recent_b["high"].max()
        low_b  = recent_b["low"].min()

        # Extremes sur la fenêtre précédente (référence)
        prev_a = df_a.iloc[-(SMT_LOOKBACK * 2):-SMT_LOOKBACK]
        prev_b = df_b.iloc[-(SMT_LOOKBACK * 2):-SMT_LOOKBACK]

        prev_high_a = prev_a["high"].max()
        prev_low_a  = prev_a["low"].min()
        prev_high_b = prev_b["high"].max()
        prev_low_b  = prev_b["low"].min()

        signal = None

        if corr_type == "POSITIVE":
            # ── Cas 1 : A fait new HIGH, B échoue ──────────
            if high_a > prev_high_a and high_b <= prev_high_b:
                divergence = high_a - prev_high_a
                signal = self._build_signal(
                    pair_a, pair_b, tf,
                    signal_direction="BEARISH",
                    smt_type="BULL_FAKE_OUT",
                    divergence=divergence,
                    atr=atr_a,
                    weight=weight,
                    details={
                        "pair_a_new_high": round(high_a, 6),
                        "pair_b_failed":   round(high_b, 6),
                        "prev_high_a":     round(prev_high_a, 6),
                        "prev_high_b":     round(prev_high_b, 6),
                    }
                )

            # ── Cas 2 : A fait new LOW, B échoue ───────────
            elif low_a < prev_low_a and low_b >= prev_low_b:
                divergence = prev_low_a - low_a
                signal = self._build_signal(
                    pair_a, pair_b, tf,
                    signal_direction="BULLISH",
                    smt_type="BEAR_FAKE_OUT",
                    divergence=divergence,
                    atr=atr_a,
                    weight=weight,
                    details={
                        "pair_a_new_low":  round(low_a, 6),
                        "pair_b_failed":   round(low_b, 6),
                        "prev_low_a":      round(prev_low_a, 6),
                        "prev_low_b":      round(prev_low_b, 6),
                    }
                )

        else:  # NEGATIVE correlation
            # ── Cas 3 : A fait new HIGH, B échoue new LOW ──
            if high_a > prev_high_a and low_b >= prev_low_b:
                divergence = high_a - prev_high_a
                signal = self._build_signal(
                    pair_a, pair_b, tf,
                    signal_direction="BEARISH",
                    smt_type="NEG_BULL_FAKE_OUT",
                    divergence=divergence,
                    atr=atr_a,
                    weight=weight,
                    details={
                        "pair_a_new_high": round(high_a, 6),
                        "pair_b_no_low":   round(low_b,  6),
                    }
                )

            # ── Cas 4 : A fait new LOW, B échoue new HIGH ──
            elif low_a < prev_low_a and high_b <= prev_high_b:
                divergence = prev_low_a - low_a
                signal = self._build_signal(
                    pair_a, pair_b, tf,
                    signal_direction="BULLISH",
                    smt_type="NEG_BEAR_FAKE_OUT",
                    divergence=divergence,
                    atr=atr_a,
                    weight=weight,
                    details={
                        "pair_a_new_low":  round(low_a,  6),
                        "pair_b_no_high":  round(high_b, 6),
                    }
                )

        return signal

    # ══════════════════════════════════════════════════════════
    # CONSTRUCTION SIGNAL
    # ══════════════════════════════════════════════════════════

    def _build_signal(self, pair_a: str, pair_b: str, tf: str,
                      signal_direction: str, smt_type: str,
                      divergence: float, atr: float,
                      weight: float, details: dict) -> dict:
        """
        Construit un dict signal SMT complet avec classification
        de force et score de confiance.

        Force :
          WEAK     : divergence < 0.3 × ATR
          MODERATE : divergence 0.3→1.0 × ATR
          STRONG   : divergence ≥ 1.0 × ATR

        Returns:
            dict signal SMT complet
        """
        atr_ratio = divergence / atr if atr > 0 else 0

        if atr_ratio >= SMT_STRONG_THRESHOLD:
            strength = "STRONG"
            base_score = 85
        elif atr_ratio >= SMT_WEAK_THRESHOLD:
            strength = "MODERATE"
            base_score = 65
        else:
            strength = "WEAK"
            base_score = 40

        # Score pondéré par le poids de la corrélation
        confidence_score = round(base_score * weight, 1)

        return {
            "id":               f"SMT_{pair_a}_{pair_b}_{tf}_{smt_type}",
            "pair_a":           pair_a,
            "pair_b":           pair_b,
            "tf":               tf,
            "smt_type":         smt_type,
            "signal_direction": signal_direction,
            "strength":         strength,
            "divergence":       round(divergence, 6),
            "atr_ratio":        round(atr_ratio,  3),
            "divergence_pct":   round(atr_ratio * 100, 1),
            "confidence_score": confidence_score,
            "corr_weight":      weight,
            "details":          details,
            "detected_at":      datetime.utcnow().isoformat(),
            "tf_rank":          SMT_VALID_TIMEFRAMES.index(tf)
                                if tf in SMT_VALID_TIMEFRAMES else 99,
        }

    # ══════════════════════════════════════════════════════════
    # CALCUL ATR
    # ══════════════════════════════════════════════════════════

    def _calculate_atr(self, df: pd.DataFrame,
                       period: int = ATR_PERIOD) -> float:
        """
        ATR Wilder (RMA) sur `period` bougies.
        Fallback 0.0001 si insuffisant.
        """
        if len(df) < period + 1:
            return 0.0001

        high  = df["high"].values
        low   = df["low"].values
        close = df["close"].values

        tr_list = [
            max(high[i] - low[i],
                abs(high[i]  - close[i - 1]),
                abs(low[i]   - close[i - 1]))
            for i in range(1, len(df))
        ]

        # Wilder's RMA : seed=SMA(period), puis lissage exponentiel
        atr = float(np.mean(tr_list[:period]))
        for tr in tr_list[period:]:
            atr = (atr * (period - 1) + tr) / period

        return atr if atr > 0 else 0.0001

    # ══════════════════════════════════════════════════════════
    # UTILITAIRES INTERNES
    # ══════════════════════════════════════════════════════════

    def _get_correlations_for(self, pair: str) -> list:
        """
        Retourne toutes les entrées de la matrice impliquant `pair`.

        Returns:
            liste de tuples (pair_a, pair_b, corr_type, weight)
        """
        result = []
        for entry in SMT_PAIRS_MATRIX:
            pair_a, pair_b, corr_type, weight = entry
            if pair_a == pair or pair_b == pair:
                # Toujours mettre la paire demandée en pair_a
                if pair_b == pair:
                    corr_type_adj = corr_type  # symétrique
                    result.append((pair_b, pair_a, corr_type_adj, weight))
                else:
                    result.append(entry)
        return result

    # ══════════════════════════════════════════════════════════
    # API PUBLIQUE — ACCÈS RÉSULTATS
    # ══════════════════════════════════════════════════════════

    def get_signals(self, pair: str,
                    direction: str = None,
                    min_strength: str = None,
                    tf: str = None) -> list:
        """
        Retourne les signaux SMT filtrés pour une paire.

        Args:
            pair:         ex. "EURUSD"
            direction:    "BULLISH", "BEARISH", ou None
            min_strength: "WEAK", "MODERATE", "STRONG"
            tf:           filtre timeframe optionnel

        Returns:
            liste de signaux SMT filtrés
        """
        strength_order = {"WEAK": 0, "MODERATE": 1, "STRONG": 2}

        with self._lock:
            signals = list(self._cache.get(pair, []))

        if direction:
            signals = [s for s in signals
                       if s["signal_direction"] == direction]

        if min_strength:
            min_val = strength_order.get(min_strength, 0)
            signals = [s for s in signals
                       if strength_order.get(s["strength"], 0) >= min_val]

        if tf:
            signals = [s for s in signals if s["tf"] == tf]

        # Tri par force décroissante puis TF HTF en premier
        signals.sort(key=lambda s: (
            -strength_order.get(s["strength"], 0),
            s["tf_rank"]
        ))

        return signals

    def get_strongest_signal(self, pair: str,
                              direction: str = None) -> Optional[dict]:
        """
        Retourne le signal SMT le plus fort pour une paire.
        Utilisé par KB5Engine pour bonus de confluence.

        Returns:
            dict signal le plus fort, ou None
        """
        signals = self.get_signals(pair, direction, min_strength="MODERATE")
        return signals[0] if signals else None

    def has_smt_confirmation(self, pair: str,
                              direction: str,
                              tf: str = None) -> bool:
        """
        Vérifie rapidement si un signal SMT MODERATE+ confirme
        la direction donnée. Utilisé par scoring_engine.

        Args:
            pair:      ex. "EURUSD"
            direction: "BULLISH" ou "BEARISH"
            tf:        filtre TF optionnel

        Returns:
            True si confirmation SMT présente
        """
        signals = self.get_signals(
            pair,
            direction=direction,
            min_strength="MODERATE",
            tf=tf
        )
        return len(signals) > 0

    def get_smt_score(self, pair: str, direction: str) -> float:
        """
        Calcule un score SMT 0→100 pour une paire/direction.
        Agrège les confidence_scores de tous les signaux actifs.
        Utilisé directement par scoring_engine.

        Returns:
            float score 0→100
        """
        signals = self.get_signals(pair, direction=direction,
                                   min_strength="WEAK")
        if not signals:
            return 0.0

        # Prendre le meilleur signal par TF
        best_by_tf: dict[str, float] = {}
        for s in signals:
            tf = s["tf"]
            if tf not in best_by_tf or s["confidence_score"] > best_by_tf[tf]:
                best_by_tf[tf] = s["confidence_score"]

        # Score agrégé plafonné à 100
        raw_score = sum(best_by_tf.values())
        return min(raw_score, 100.0)

    def get_snapshot(self, pair: str) -> dict:
        """
        Snapshot complet pour Dashboard Patron.

        Returns:
            dict {total, strong, moderate, weak, by_tf}
        """
        with self._lock:
            signals = list(self._cache.get(pair, []))

        by_tf: dict[str, int] = {}
        for s in signals:
            by_tf[s["tf"]] = by_tf.get(s["tf"], 0) + 1

        return {
            "total":    len(signals),
            "strong":   sum(1 for s in signals if s["strength"] == "STRONG"),
            "moderate": sum(1 for s in signals if s["strength"] == "MODERATE"),
            "weak":     sum(1 for s in signals if s["strength"] == "WEAK"),
            "by_tf":    by_tf,
            "latest":   signals[:3] if signals else [],
        }

    def clear_cache(self, pair: str = None) -> None:
        """
        Vide le cache SMT. Appelé entre sessions ou après
        rechargement DataStore par ReconnectManager.
        """
        with self._lock:
            if pair:
                self._cache.pop(pair, None)
                logger.info(f"SMT cache vidé — Paire : {pair}")
            else:
                self._cache.clear()
                logger.info("SMT cache vidé — toutes les paires")

    def __repr__(self) -> str:
        pairs = list(self._cache.keys())
        total = sum(len(v) for v in self._cache.values())
        return f"SMTDetector(pairs={pairs}, total_signals={total})"
