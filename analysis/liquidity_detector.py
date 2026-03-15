# analysis/liquidity_detector.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Détecteur de Liquidité ICT
══════════════════════════════════════════════════════════════
Responsabilités :
  - Identifier les Liquidity Pools (aimants institutionnels) :
      · PDH / PDL   (Previous Day High / Low)
      · PWH / PWL   (Previous Week High / Low)
      · Asia Range High / Low (session d'Asie 21h-00h UTC)
      · Midnight Open  (00h00 UTC — pivot institutionnel)
      · Equal Highs / Equal Lows (faux support/résistance retail)
  - Détecter les Liquidity Sweeps (Turtle Soup) :
      · SWEEP_BULL : mèche sous un pool SSL → rejet haussier
      · SWEEP_BEAR : mèche au-dessus d'un pool BSL → rejet baissier
  - Déterminer le Draw on Liquidity (DOL) :
      · Quelle est la PROCHAINE cible institutionnelle ?
      · Basé sur le dernier sweep : inverse de la liquidité prise

Intégration dans la pyramide KB5 :
  - Consommé par : kb5_engine.py (_detect_confluences, _calculate_entry_model)
  - Bonus de score : CONFLUENCE_SWEEP (+12), CONFLUENCE_MIDNIGHT (+8)

Concept ICT fondamental :
  "Le prix doit TOUJOURS prendre la liquidité avant de se diriger
   vers sa cible réelle. Ne jamais entrer avant le Sweep."
  — Inner Circle Trader (ICT)

Dépendances :
  - DataStore  → get_candles()
  - config.constants → Trading

Consommé par :
  - kb5_engine.py
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
# CONSTANTES LOCALES
# ══════════════════════════════════════════════════════════════

# Fenêtre de fraîcheur d'un sweep (en bougies) — au-delà, il est "périmé"
SWEEP_FRESH_CANDLES  = 5

# Tolérance Equal Highs/Lows (en % de l'ATR, pas en pips absolus)
EQUAL_HL_TOLERANCE   = 0.15   # ≤ 15% de l'ATR → considéré "égal"

# Nombre de bougies minimum pour marquer un Equal High/Low
EQUAL_HL_MIN_CANDLES = 3      # Au moins 3 bougies entre les deux touches

# Mèche minimum pour valider un Sweep (en % de l'ATR)
SWEEP_WICK_MIN_ATR   = 0.25   # La mèche doit dépasser le pool d'au moins 25% ATR

# Heures UTC de la session d'Asie pour le calcul du Range
ASIA_RANGE_START_UTC = 21
ASIA_RANGE_END_UTC   = 0      # traverse minuit → jusqu'à 00h00 UTC

# Bonuses ICT (exportés pour kb5_engine.py)
CONFLUENCE_SWEEP        = 12
CONFLUENCE_MIDNIGHT     = 8
CONFLUENCE_ASIA_RANGE   = 6

# Statuts sweep
SWEEP_FRESH  = "FRESH"
SWEEP_USED   = "USED"   # Déjà exploité ou dépassé la fenêtre de fraîcheur


# ══════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════

class LiquidityDetector:
    """
    Radar ICT de liquidité pour Sentinel Pro KB5.

    Identifie les "aimants" institutionnels sur le marché :
      - Niveaux où les Retail traders ont leurs Stop-Loss
      - Zones où les algorithmes interbancaires viennent "faire le plein"
        avant d'initier le VRAI mouvement directionnel.

    Logique de base :
      1. Cartographier les pools de liquidité (PDH, PDL, Asia Range, etc.)
      2. Surveiller si le prix "sonde" ces zones (Turtle Soup / Sweep)
      3. Si Sweep confirmé → le bot peut entrer EN SENS INVERSE
         car la liquidité est "épuisée" à ce niveau.
    """

    def __init__(self, data_store: DataStore):
        self._ds   = data_store
        self._lock = threading.RLock()
        # Format : _cache[pair] = {pools, sweeps, dol, midnight_open}
        self._cache: dict[str, dict] = {}
        logger.info("LiquidityDetector initialisé — Radar ICT actif")

    # ══════════════════════════════════════════════════════════
    # MÉTHODE PRINCIPALE — SCAN COMPLET
    # ══════════════════════════════════════════════════════════

    def scan_pair(self, pair: str) -> dict:
        """
        Scan complet de la liquidité pour une paire.
        Calcule les pools, détecte les sweeps et détermine le DOL.

        Args:
            pair: ex. "EURUSD"

        Returns:
            dict {pools, sweeps, dol, midnight_open, asia_range}
        """
        df_h1 = self._ds.get_candles(pair, "H1")
        df_d1 = self._ds.get_candles(pair, "D1")
        df_w1 = self._ds.get_candles(pair, "W")
        df_m15 = self._ds.get_candles(pair, "M15")

        if df_h1 is None or len(df_h1) < 24:
            logger.debug(f"LiquidityDetector — {pair} | Données H1 insuffisantes")
            return self._empty_result(pair)

        atr = self._calculate_atr(df_h1)

        # ── Étape 1 : Calculer les Pools ──────────────────────
        pools = self._calculate_pools(pair, df_h1, df_d1, df_w1, atr)

        # ── Étape 2 : Calculer le Midnight Open ───────────────
        midnight_open = self._get_midnight_open(df_h1)

        # ── Étape 3 : Calculer l'Asia Range ───────────────────
        asia_range = self._get_asia_range(df_m15 if df_m15 is not None else df_h1)

        # ── Étape 4 : Détecter les Equal Highs / Equal Lows ──
        eq_highs, eq_lows = self._find_equal_levels(df_h1, atr)
        pools["equal_highs"] = eq_highs
        pools["equal_lows"]  = eq_lows

        # ── Étape 5 : Détecter les Sweeps ─────────────────────
        all_pools_flat = self._flatten_pools(pools)
        sweeps = self._detect_sweeps(pair, df_h1, all_pools_flat, atr)

        # ── Étape 6 : Calculer le Draw on Liquidity ───────────
        dol = self._calculate_dol(pair, sweeps, pools)

        result = {
            "pair":         pair,
            "timestamp":    datetime.now(timezone.utc).isoformat(),
            "atr_h1":       round(atr, 6),
            "pools":        pools,
            "midnight_open": midnight_open,
            "asia_range":   asia_range,
            "sweeps":       sweeps,
            "dol":          dol,
        }

        with self._lock:
            self._cache[pair] = result

        self._ds.set_analysis(pair, "liquidity", result)

        logger.info(
            f"LiquidityDetector — {pair} | "
            f"Pools: {len(all_pools_flat)} | "
            f"Sweeps frais: {sum(1 for s in sweeps if s['status'] == SWEEP_FRESH)} | "
            f"DOL: {dol.get('direction', 'N/A')} → {dol.get('target_level', 'N/A')}"
        )

        return result

    # ══════════════════════════════════════════════════════════
    # CALCUL DES LIQUIDITY POOLS (AIMANTS)
    # ══════════════════════════════════════════════════════════

    def _calculate_pools(self, pair: str, df_h1: pd.DataFrame,
                          df_d1: Optional[pd.DataFrame],
                          df_w1: Optional[pd.DataFrame],
                          atr: float) -> dict:
        """
        Identifie tous les Liquidity Pools actifs :
          - PDH / PDL  (Previous Day High / Low)
          - PWH / PWL  (Previous Week High / Low)
        """
        pools: dict = {
            "pdh": None, "pdl": None,   # Previous Day
            "pwh": None, "pwl": None,   # Previous Week
            "equal_highs": [],
            "equal_lows":  [],
        }

        # ── PDH / PDL ─────────────────────────────────────────
        if df_d1 is not None and len(df_d1) >= 2:
            # [−2] = la bougie journalière précédente (fermée)
            prev_day = df_d1.iloc[-2]
            pools["pdh"] = {
                "level":   round(float(prev_day["high"]), 6),
                "type":    "PDH",
                "pool":    "BSL",    # Buy Side Liquidity = stops au-dessus des hauts
                "pair":    pair,
                "tf":      "D1",
            }
            pools["pdl"] = {
                "level":   round(float(prev_day["low"]), 6),
                "type":    "PDL",
                "pool":    "SSL",    # Sell Side Liquidity = stops en-dessous des bas
                "pair":    pair,
                "tf":      "D1",
            }

        # ── PWH / PWL ─────────────────────────────────────────
        if df_w1 is not None and len(df_w1) >= 2:
            prev_week = df_w1.iloc[-2]
            pools["pwh"] = {
                "level":   round(float(prev_week["high"]), 6),
                "type":    "PWH",
                "pool":    "BSL",
                "pair":    pair,
                "tf":      "W1",
            }
            pools["pwl"] = {
                "level":   round(float(prev_week["low"]), 6),
                "type":    "PWL",
                "pool":    "SSL",
                "pair":    pair,
                "tf":      "W1",
            }

        return pools

    def _get_midnight_open(self, df_h1: pd.DataFrame) -> Optional[dict]:
        """
        Retourne le prix d'ouverture à 00h00 UTC (Midnight Open ICT).
        C'est le pivot institutionnel le plus puissant de la journée.
        En-dessous = Discount (favorable aux achats BULLISH).
        Au-dessus  = Premium  (favorable aux ventes BEARISH).

        Returns:
            dict {level, session_date} ou None si introuvable
        """
        try:
            # Chercher la bougie H1 dont l'heure est 00h00 UTC parmi les récentes
            times = df_h1.index if hasattr(df_h1.index, '__iter__') else df_h1["time"]
            opens = df_h1["open"].values

            for i in range(len(df_h1) - 1, max(len(df_h1) - 30, -1), -1):
                t = pd.to_datetime(times[i])
                # Bougie d'ouverture à exactement minuit UTC
                if t.hour == 0 and t.minute == 0:
                    return {
                        "level":        round(float(opens[i]), 6),
                        "type":         "MIDNIGHT_OPEN",
                        "pool":         "PIVOT",
                        "session_date": str(t.date()),
                        "candle_idx":   i,
                    }
        except Exception as e:
            logger.debug(f"Midnight Open introuvable : {e}")

        return None

    def _get_asia_range(self, df: pd.DataFrame) -> dict:
        """
        Calcule le Range de la session d'Asie (21h00–00h00 UTC).
        Le high et low de ce range sont des aimants massifs pour
        les sessions de Londres et New York.

        Returns:
            dict {high, low, mid, range_size} ou dict vide
        """
        try:
            times  = df.index if hasattr(df.index, '__iter__') else df["time"]
            highs  = df["high"].values
            lows   = df["low"].values

            asia_highs = []
            asia_lows  = []

            for i in range(len(df)):
                t = pd.to_datetime(times[i])
                # Session Asie : 21h00 UTC → 00h00 UTC (traversée minuit)
                if t.hour >= ASIA_RANGE_START_UTC or t.hour < ASIA_RANGE_END_UTC:
                    # Garder uniquement les bougies de la SESSION D'ASIE DU JOUR EN COURS
                    # (i.e. les 3–9 dernières bougies selon TF)
                    if i >= len(df) - 10:
                        asia_highs.append(float(highs[i]))
                        asia_lows.append(float(lows[i]))

            if not asia_highs:
                return {}

            ar_high = max(asia_highs)
            ar_low  = min(asia_lows)
            ar_mid  = (ar_high + ar_low) / 2.0

            return {
                "high":       round(ar_high, 6),
                "low":        round(ar_low,  6),
                "mid":        round(ar_mid,  6),
                "range_size": round(ar_high - ar_low, 6),
                "bsl_level":  round(ar_high, 6),   # BSL = stops au-dessus du High Asie
                "ssl_level":  round(ar_low,  6),   # SSL = stops en-dessous du Low Asie
            }

        except Exception as e:
            logger.debug(f"Asia Range introuvable : {e}")
            return {}

    def _find_equal_levels(self, df: pd.DataFrame,
                            atr: float) -> tuple[list, list]:
        """
        Détecte les Equal Highs (EQH) et Equal Lows (EQL).
        Ce sont des zones où le prix a touché deux fois le même niveau
        créant un "faux" support/résistance que les algos vont purger.

        Logique :
          - Comparer les hauts/bas locaux entre eux
          - Si deux hauts sont à ≤ EQUAL_HL_TOLERANCE × ATR = EQH
          - Au moins EQUAL_HL_MIN_CANDLES bougies de séparation minimale

        Returns:
            tuple (eq_highs_list, eq_lows_list)
        """
        tolerance = EQUAL_HL_TOLERANCE * atr
        highs = df["high"].values
        lows  = df["low"].values
        times = df.index if hasattr(df.index, '__iter__') else df["time"].values

        eq_highs = []
        eq_lows  = []

        # Regarder les 50 dernières bougies seulement
        window = min(50, len(df))
        h = highs[-window:]
        l = lows[-window:]
        t = list(times)[-window:]

        # ── Equal Highs ───────────────────────────────────────
        for i in range(len(h) - 1):
            for j in range(i + EQUAL_HL_MIN_CANDLES, len(h)):
                if abs(h[j] - h[i]) <= tolerance:
                    eq_level = round((h[i] + h[j]) / 2, 6)
                    # Éviter les doublons (même niveau)
                    if not any(abs(eq["level"] - eq_level) <= tolerance
                               for eq in eq_highs):
                        eq_highs.append({
                            "level":    eq_level,
                            "type":     "EQH",
                            "pool":     "BSL",
                            "touch_1":  str(t[i]),
                            "touch_2":  str(t[j]),
                            "strength": "STRONG" if abs(h[j] - h[i]) < tolerance * 0.5
                                        else "MODERATE",
                        })

        # ── Equal Lows ────────────────────────────────────────
        for i in range(len(l) - 1):
            for j in range(i + EQUAL_HL_MIN_CANDLES, len(l)):
                if abs(l[j] - l[i]) <= tolerance:
                    eq_level = round((l[i] + l[j]) / 2, 6)
                    if not any(abs(eq["level"] - eq_level) <= tolerance
                               for eq in eq_lows):
                        eq_lows.append({
                            "level":    eq_level,
                            "type":     "EQL",
                            "pool":     "SSL",
                            "touch_1":  str(t[i]),
                            "touch_2":  str(t[j]),
                            "strength": "STRONG" if abs(l[j] - l[i]) < tolerance * 0.5
                                        else "MODERATE",
                        })

        # Garder les 3 EQH/EQL les plus récents et les plus proches du prix actuel
        current_price = float(df["close"].iloc[-1])
        eq_highs.sort(key=lambda x: abs(x["level"] - current_price))
        eq_lows.sort(key=lambda x: abs(x["level"] - current_price))

        return eq_highs[:3], eq_lows[:3]

    # ══════════════════════════════════════════════════════════
    # DÉTECTION DES SWEEPS (TURTLE SOUP)
    # ══════════════════════════════════════════════════════════

    def _flatten_pools(self, pools: dict) -> list:
        """
        Aplatit le dict pools en une liste homogène de niveaux
        pour la détection de sweeps.

        Returns:
            liste de dicts {level, type, pool}
        """
        flat = []
        for key, val in pools.items():
            if isinstance(val, dict) and "level" in val:
                flat.append(val)
            elif isinstance(val, list):
                flat.extend(val)
        return flat

    def _detect_sweeps(self, pair: str, df: pd.DataFrame,
                        pools: list, atr: float) -> list:
        """
        Détecte les Sweeps (Turtle Soup / Purge de liquidité).

        Un Sweep est validé quand :
          1. Une mèche dépasse le pool d'au moins SWEEP_WICK_MIN_ATR × ATR
          2. Le CORPS de la bougie clôture DE L'AUTRE CÔTÉ du pool
             (la bougie "dégage" la zone sans s'y installer → c'est un piège)
          3. Détecté dans les SWEEP_FRESH_CANDLES dernières bougies

        Args:
            pair:  symbole paire
            df:    DataFrame H1
            pools: liste de pools (PDH, PDL, EQH, EQL, etc.)
            atr:   ATR H1

        Returns:
            liste de dicts Sweep avec statut FRESH / USED
        """
        sweeps = []
        min_wick = SWEEP_WICK_MIN_ATR * atr

        highs  = df["high"].values
        lows   = df["low"].values
        opens  = df["open"].values
        closes = df["close"].values
        times  = df.index if hasattr(df.index, '__iter__') else df["time"].values

        # Période de scan : SWEEP_FRESH_CANDLES × 3 pour pouvoir marquer USED
        lookback = min(SWEEP_FRESH_CANDLES * 3, len(df) - 1)
        start_i  = len(df) - lookback

        for pool in pools:
            if pool is None or "level" not in pool:
                continue

            level     = pool["level"]
            pool_type = pool.get("pool", "UNKNOWN")  # BSL ou SSL

            for i in range(start_i, len(df)):
                h = highs[i]
                l = lows[i]
                o = opens[i]
                c = closes[i]

                # ── SWEEP BEARISH (Turtle Soup Bear) ───────────
                # Mèche AU-DESSUS d'un Pool BSL (Equal High, PDH…) → rejet
                if pool_type == "BSL":
                    wick_above = h - level
                    body_below = c < level and o < level   # corps entier sous le niveau
                    body_close_below = c < level           # au min la clôture sous le niveau

                    if wick_above >= min_wick and body_close_below:
                        freshness = "FRESH" if i >= len(df) - SWEEP_FRESH_CANDLES \
                                    else "USED"
                        sweep_id = f"SWEEP_BEAR_{pair}_{pool['type']}_{str(times[i])}"
                        # Éviter doublons strict
                        if not any(s["id"] == sweep_id for s in sweeps):
                            sweeps.append({
                                "id":             sweep_id,
                                "pair":           pair,
                                "type":           "SWEEP_BEAR",
                                "direction":      "BEARISH",  # signal de rejet haussier
                                "signal_direction": "BEARISH",
                                "pool_type":      pool["type"],
                                "pool_level":     level,
                                "wick_size":      round(wick_above, 6),
                                "close":          round(c, 6),
                                "candle_idx":     i,
                                "detected_at":    str(times[i]),
                                "status":         freshness,
                                "atr_ratio":      round(wick_above / atr, 2) if atr else 0,
                            })

                # ── SWEEP BULLISH (Turtle Soup Bull) ──────────
                # Mèche EN-DESSOUS d'un Pool SSL (Equal Low, PDL…) → rejet
                elif pool_type == "SSL":
                    wick_below = level - l
                    body_above = c > level and o > level   # corps entier au-dessus
                    body_close_above = c > level           # au min la clôture au-dessus

                    if wick_below >= min_wick and body_close_above:
                        freshness = "FRESH" if i >= len(df) - SWEEP_FRESH_CANDLES \
                                    else "USED"
                        sweep_id = f"SWEEP_BULL_{pair}_{pool['type']}_{str(times[i])}"
                        if not any(s["id"] == sweep_id for s in sweeps):
                            sweeps.append({
                                "id":             sweep_id,
                                "pair":           pair,
                                "type":           "SWEEP_BULL",
                                "direction":      "BULLISH",
                                "signal_direction": "BULLISH",
                                "pool_type":      pool["type"],
                                "pool_level":     level,
                                "wick_size":      round(wick_below, 6),
                                "close":          round(c, 6),
                                "candle_idx":     i,
                                "detected_at":    str(times[i]),
                                "status":         freshness,
                                "atr_ratio":      round(wick_below / atr, 2) if atr else 0,
                            })

        # Tri par fraîcheur puis par taille de wick (priorité aux plus significatifs)
        sweeps.sort(key=lambda s: (
            0 if s["status"] == SWEEP_FRESH else 1,
            -s["atr_ratio"]
        ))

        if sweeps:
            fresh = [s for s in sweeps if s["status"] == SWEEP_FRESH]
            logger.info(
                f"Sweeps détectés — {pair} | "
                f"Total: {len(sweeps)} | FRESH: {len(fresh)}"
            )
            for s in fresh:
                logger.info(
                    f"  🎣 {s['type']} sur {s['pool_type']} ({s['pool_level']}) | "
                    f"Wick: {s['atr_ratio']}× ATR | Clôture: {s['close']}"
                )

        return sweeps

    # ══════════════════════════════════════════════════════════
    # DRAW ON LIQUIDITY (DOL)
    # ══════════════════════════════════════════════════════════

    def _calculate_dol(self, pair: str, sweeps: list, pools: dict) -> dict:
        """
        Détermine le Draw on Liquidity (DOL) :
        La prochaine cible institutionnelle vers laquelle le prix
        sera "attiré" après la liquidité actuelle.

        Logique ICT fondamentale :
          Si dernier sweep = BULL (SSL prise en dessous)
            → les institutions ont leur carburant BULLISH
            → DOL = le prochain pool BSL au-dessus (PDH, PWH, EQH)

          Si dernier sweep = BEAR (BSL prise au-dessus)
            → les institutions ont leur carburant BEARISH
            → DOL = le prochain pool SSL en-dessous (PDL, PWL, EQL)

        Returns:
            dict {direction, target_level, target_type, confidence}
        """
        fresh_sweeps = [s for s in sweeps if s["status"] == SWEEP_FRESH]

        if not fresh_sweeps:
            return {
                "direction":    "NEUTRAL",
                "target_level": None,
                "target_type":  None,
                "confidence":   "NONE",
                "reason":       "Aucun sweep frais détecté",
            }

        # Prendre le sweep le plus frais (premier dans la liste triée)
        last_sweep = fresh_sweeps[0]
        sweep_dir  = last_sweep["direction"]  # BULLISH ou BEARISH

        # ── Si dernier sweep BULLISH → DOL = prochain BSL (haut) ──
        if sweep_dir == "BULLISH":
            candidates = []
            if pools.get("pdh"):
                candidates.append(pools["pdh"])
            if pools.get("pwh"):
                candidates.append(pools["pwh"])
            for eqh in pools.get("equal_highs", []):
                candidates.append(eqh)

            # Filtrer : target doit être AU-DESSUS du niveau du sweep
            sweep_close = last_sweep["close"]
            above_candidates = [c for c in candidates
                                 if c["level"] > sweep_close]

            if above_candidates:
                # Cible la plus proche (première atteignable)
                target = min(above_candidates, key=lambda c: c["level"])
                return {
                    "direction":    "BULLISH",
                    "target_level": target["level"],
                    "target_type":  target["type"],
                    "confidence":   "HIGH" if last_sweep["atr_ratio"] >= 0.5 else "MODERATE",
                    "sweep_origin": last_sweep["pool_level"],
                    "sweep_type":   last_sweep["pool_type"],
                    "reason":       f"SSL purgée → DOL vers {target['type']} {target['level']}",
                }

        # ── Si dernier sweep BEARISH → DOL = prochain SSL (bas) ──
        elif sweep_dir == "BEARISH":
            candidates = []
            if pools.get("pdl"):
                candidates.append(pools["pdl"])
            if pools.get("pwl"):
                candidates.append(pools["pwl"])
            for eql in pools.get("equal_lows", []):
                candidates.append(eql)

            sweep_close = last_sweep["close"]
            below_candidates = [c for c in candidates
                                 if c["level"] < sweep_close]

            if below_candidates:
                target = max(below_candidates, key=lambda c: c["level"])
                return {
                    "direction":    "BEARISH",
                    "target_level": target["level"],
                    "target_type":  target["type"],
                    "confidence":   "HIGH" if last_sweep["atr_ratio"] >= 0.5 else "MODERATE",
                    "sweep_origin": last_sweep["pool_level"],
                    "sweep_type":   last_sweep["pool_type"],
                    "reason":       f"BSL purgée → DOL vers {target['type']} {target['level']}",
                }

        return {
            "direction":    "NEUTRAL",
            "target_level": None,
            "target_type":  None,
            "confidence":   "LOW",
            "reason":       "Cible DOL introuvable (pas de pool au-delà du sweep)",
        }

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

        return atr if atr > 0 else 0.0001

    # ══════════════════════════════════════════════════════════
    # API PUBLIQUE — ACCÈS RÉSULTATS
    # ══════════════════════════════════════════════════════════

    def get_pools(self, pair: str) -> dict:
        """
        Retourne les Liquidity Pools calculés pour une paire.

        Returns:
            dict {pdh, pdl, pwh, pwl, equal_highs, equal_lows}
        """
        with self._lock:
            return dict(self._cache.get(pair, {}).get("pools", {}))

    def get_sweeps(self, pair: str,
                   status: Optional[str] = None,
                   direction: Optional[str] = None) -> list:
        """
        Retourne les Sweeps détectés pour une paire.

        Args:
            pair:      ex. "EURUSD"
            status:    "FRESH", "USED", ou None (tous)
            direction: "BULLISH", "BEARISH", ou None

        Returns:
            liste de dicts Sweep
        """
        with self._lock:
            sweeps = list(self._cache.get(pair, {}).get("sweeps", []))

        if status:
            sweeps = [s for s in sweeps if s["status"] == status]
        if direction:
            sweeps = [s for s in sweeps if s["direction"] == direction]

        return sweeps

    def get_dol(self, pair: str) -> dict:
        """
        Retourne le Draw on Liquidity (DOL) actuel.
        C'est la cible institutionnelle probable pour le prochain mouvement.

        Returns:
            dict {direction, target_level, target_type, confidence}
        """
        with self._lock:
            return dict(self._cache.get(pair, {}).get("dol", {}))

    def get_midnight_open(self, pair: str) -> Optional[dict]:
        """
        Retourne le Midnight Open (pivot ICT 00h00 UTC).

        Returns:
            dict {level, session_date} ou None
        """
        with self._lock:
            return self._cache.get(pair, {}).get("midnight_open")

    def get_asia_range(self, pair: str) -> dict:
        """
        Retourne le Range de la session d'Asie.

        Returns:
            dict {high, low, mid, bsl_level, ssl_level}
        """
        with self._lock:
            return dict(self._cache.get(pair, {}).get("asia_range", {}))

    def has_fresh_sweep(self, pair: str,
                         direction: Optional[str] = None) -> bool:
        """
        Vérifie rapidement si un Sweep FRESH est présent.
        Utilisé par kb5_engine pour bonus de confluence.

        Args:
            pair:      ex. "EURUSD"
            direction: "BULLISH", "BEARISH", ou None

        Returns:
            True si au moins un Sweep FRESH dans la direction donnée
        """
        fresh = self.get_sweeps(pair, status=SWEEP_FRESH, direction=direction)
        return len(fresh) > 0

    def is_price_above_midnight(self, pair: str) -> Optional[bool]:
        """
        Vérifie si le prix actuel est au-dessus du Midnight Open.
        Au-dessus = zone PREMIUM (favorable BEARISH)
        En-dessous = zone DISCOUNT (favorable BULLISH)

        Returns:
            True = Premium, False = Discount, None = non disponible
        """
        with self._lock:
            data = self._cache.get(pair, {})

        midnight = data.get("midnight_open")
        df_h1    = self._ds.get_candles(pair, "H1")

        if midnight is None or df_h1 is None or df_h1.empty:
            return None

        current_price = float(df_h1["close"].iloc[-1])
        return current_price > midnight["level"]
    
    def get_lrlr(self, pair: str, direction: str) -> dict:
        """
        Détecte le LRLR (Lower Relative Low Reference) pour BULLISH
        ou HRLR (Higher Relative High Reference) pour BEARISH.

        Concept ICT :
        LRLR = dernier bas relatif sous le prix actuel non encore sweepé
        HRLR = dernier haut relatif au-dessus du prix actuel non encore sweepé

        Returns:
            dict {detected, level, type, distance, swept}
        """
        df = self._ds.get_candles(pair, "H4")
        if df is None or len(df) < 20:
            return {"detected": False, "reason": "H4 insuffisant"}

        highs        = df["high"].values[-20:]
        lows         = df["low"].values[-20:]
        current      = float(df["close"].iloc[-1])
        atr          = self._calculate_atr(df)

        if direction == "BULLISH":
            # LRLR = bas local sous le prix actuel
            candidates = [
                lows[i] for i in range(len(lows) - 1)
                if lows[i] < current
                and lows[i] < lows[i - 1]
                and lows[i] < lows[i + 1]
            ]
            if not candidates:
                return {"detected": False,
                        "reason": "Aucun LRLR trouvé"}
            level  = round(max(candidates), 6)  # le plus proche
            swept  = current < (level - (0.25 * atr))
            return {
                "detected" : True,
                "level"    : level,
                "type"     : "LRLR",
                "distance" : round(abs(current - level), 6),
                "swept"    : swept,
                "atr_ratio": round(abs(current - level) / atr, 2)
                             if atr else 0,
            }

        else:  # BEARISH — HRLR
            candidates = [
                highs[i] for i in range(len(highs) - 1)
                if highs[i] > current
                and highs[i] > highs[i - 1]
                and highs[i] > highs[i + 1]
            ]
            if not candidates:
                return {"detected": False,
                        "reason": "Aucun HRLR trouvé"}
            level  = round(min(candidates), 6)  # le plus proche
            swept  = current > (level + (0.25 * atr))
            return {
                "detected" : True,
                "level"    : level,
                "type"     : "HRLR",
                "distance" : round(abs(current - level), 6),
                "swept"    : swept,
                "atr_ratio": round(abs(current - level) / atr, 2)
                             if atr else 0,
            }

    def has_lrlr_swept(self, pair: str, direction: str) -> bool:
        """
        Vérifie rapidement si le LRLR/HRLR a été sweepé.
        Utilisé par kb5_engine pour bonus de confluence.
        """
        result = self.get_lrlr(pair, direction)
        return result.get("swept", False)


    def get_snapshot(self, pair: str) -> dict:
        """
        Snapshot compact pour Dashboard Patron.

        Returns:
            dict résumé liquidité
        """
        with self._lock:
            data = dict(self._cache.get(pair, {}))

        if not data:
            return {"pair": pair, "status": "non scanné"}

        dol    = data.get("dol", {})
        sweeps = data.get("sweeps", [])
        mn     = data.get("midnight_open")
        ar     = data.get("asia_range", {})

        return {
            "pair":           pair,
            "dol_direction":  dol.get("direction"),
            "dol_target":     dol.get("target_level"),
            "dol_confidence": dol.get("confidence"),
            "fresh_sweeps":   sum(1 for s in sweeps if s["status"] == SWEEP_FRESH),
            "total_sweeps":   len(sweeps),
            "midnight_open":  mn.get("level") if mn else None,
            "asia_high":      ar.get("high"),
            "asia_low":       ar.get("low"),
            "pdh":            data.get("pools", {}).get("pdh", {}).get("level"),
            "pdl":            data.get("pools", {}).get("pdl", {}).get("level"),
            "pwh":            data.get("pools", {}).get("pwh", {}).get("level"),
            "pwl":            data.get("pools", {}).get("pwl", {}).get("level"),
        }

    def clear_cache(self, pair: Optional[str] = None) -> None:
        """Vide le cache. Appelé par ReconnectManager."""
        with self._lock:
            if pair:
                self._cache.pop(pair, None)
                logger.info(f"LiquidityDetector cache vidé — {pair}")
            else:
                self._cache.clear()
                logger.info("LiquidityDetector cache vidé — toutes paires")

    # ==============================================================
    # D - INTERNAL vs EXTERNAL LIQUIDITY
    # ==============================================================

    def classify_pool_type(self, pool: dict, current_price: float,
                           atr: float) -> str:
        """
        Classifie un pool de liquidite en INTERNAL ou EXTERNAL.

        ICT Definition :
          EXTERNAL Liquidity = niveaux HORS de la structure de marche actuelle
            -> PDH, PDL, PWH, PWL = vraies cibles institutionnelles (Draw on Liquidity)

          INTERNAL Liquidity = niveaux DANS la structure actuelle
            -> EQH/EQL proches, Asia Range, Midnight Open = cibles intérimaires
        """
        if pool is None or "level" not in pool:
            return "UNKNOWN"

        pool_type_str = pool.get("type", "")
        level = pool.get("level", current_price)
        dist  = abs(level - current_price)

        # PDH, PDL, PWH, PWL : toujours External (cibles D1 / W1)
        if pool_type_str in ("PDH", "PDL", "PWH", "PWL"):
            return "EXTERNAL"

        # EQH/EQL : External si > 1.5 ATR du prix courant
        if pool_type_str in ("EQH", "EQL"):
            return "EXTERNAL" if dist > 1.5 * atr else "INTERNAL"

        # Midnight Open, Asia Range : contexte de session = Internal
        if pool_type_str in ("MIDNIGHT_OPEN", "ASIA_HIGH", "ASIA_LOW"):
            return "INTERNAL"

        # Defaut : External si loin, Internal si proche (1 ATR seuil)
        return "EXTERNAL" if dist > atr else "INTERNAL"

    def get_external_pools(self, pair: str) -> list:
        """
        Retourne uniquement les pools EXTERNES (vraies cibles DOL).
        Ce sont les niveaux prioritaires pour le calcul du Take Profit.
        """
        with self._lock:
            cached = dict(self._cache.get(pair, {}))

        if not cached:
            return []

        pools_raw = cached.get("pools", {})
        atr       = cached.get("atr_h1", 0.0001)
        df_h1     = self._ds.get_candles(pair, "H1")
        if df_h1 is None or df_h1.empty:
            return []

        current_price = float(df_h1["close"].iloc[-1])
        external = []

        for key, pool in pools_raw.items():
            if isinstance(pool, dict) and "level" in pool:
                if self.classify_pool_type(pool, current_price, atr) == "EXTERNAL":
                    external.append({**pool, "liquidity_class": "EXTERNAL"})
            elif isinstance(pool, list):
                for p in pool:
                    if isinstance(p, dict) and "level" in p:
                        if self.classify_pool_type(p, current_price, atr) == "EXTERNAL":
                            external.append({**p, "liquidity_class": "EXTERNAL"})

        external.sort(key=lambda p: abs(p["level"] - current_price))
        return external

    def get_internal_pools(self, pair: str) -> list:
        """
        Retourne uniquement les pools INTERNES (cibles de reequilibrage).
        """
        with self._lock:
            cached = dict(self._cache.get(pair, {}))

        if not cached:
            return []

        pools_raw = cached.get("pools", {})
        atr       = cached.get("atr_h1", 0.0001)
        df_h1     = self._ds.get_candles(pair, "H1")
        if df_h1 is None or df_h1.empty:
            return []

        current_price = float(df_h1["close"].iloc[-1])
        internal = []

        for key, pool in pools_raw.items():
            if isinstance(pool, dict) and "level" in pool:
                if self.classify_pool_type(pool, current_price, atr) == "INTERNAL":
                    internal.append({**pool, "liquidity_class": "INTERNAL"})
            elif isinstance(pool, list):
                for p in pool:
                    if isinstance(p, dict) and "level" in p:
                        if self.classify_pool_type(p, current_price, atr) == "INTERNAL":
                            internal.append({**p, "liquidity_class": "INTERNAL"})

        internal.sort(key=lambda p: abs(p["level"] - current_price))
        return internal

    def _empty_result(self, pair: str) -> dict:

        """Résultat vide standardisé en cas de données insuffisantes."""
        return {
            "pair":          pair,
            "timestamp":     datetime.now(timezone.utc).isoformat(),
            "atr_h1":        0.0,
            "pools":         {},
            "midnight_open": None,
            "asia_range":    {},
            "sweeps":        [],
            "dol":           {"direction": "NEUTRAL", "target_level": None,
                               "confidence": "NONE"},
        }

    def __repr__(self) -> str:
        pairs = list(self._cache.keys())
        return f"LiquidityDetector(pairs={pairs})"
