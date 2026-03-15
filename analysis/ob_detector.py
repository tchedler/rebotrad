# analysis/ob_detector.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Détecteur Order Blocks (OB)
══════════════════════════════════════════════════════════════
Responsabilités :
  - Détecter Order Blocks Bullish/Bearish sur tous les TF
  - Identifier Breaker Blocks (OB invalidé → polarité inversée)
  - Calculer BPR (Balanced Price Range) FVG vs FVG opposé
  - Classifier statut : VALID / TESTED / BROKEN
  - Valider OB par impulsion suivante ≥ seuil ATR
  - Pousser résultats dans DataStore pour KB5Engine

Dépendances :
  - DataStore       → get_candles(), set_analysis()
  - FVGDetector     → BPR (chevauchement FVG opposés)
  - config.constants → Trading

Consommé par :
  - bias_detector.py
  - kb5_engine.py
  - smt_detector.py
  - scoring_engine.py
══════════════════════════════════════════════════════════════
"""

import logging
import threading
import numpy as np
import pandas as pd
from typing import Optional

from datastore.data_store import DataStore
from config.constants import Trading

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# CONSTANTES LOCALES
# ══════════════════════════════════════════════════════════════

OB_VALID   = "VALID"     # OB intact, non testé
OB_TESTED  = "TESTED"    # prix revenu dans l'OB (zone d'entrée)
OB_BROKEN  = "BROKEN"    # prix a traversé → devient Breaker Block

BB_VALID   = "VALID"     # Breaker Block actif
BB_INVALID = "INVALID"   # Breaker Block comblé

ATR_PERIOD         = 14
ATR_IMPULSE_FACTOR = 1.5   # impulsion suivante ≥ 1.5× ATR pour valider force OB
ATR_MIN_OB_SIZE    = 0.10  # corps OB ≥ 10% ATR (filtre micro-OB)
MAX_OB_LOOKBACK    = 60    # profondeur scan ICT (les vieux OB n'intéressent plus)

# ══════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════

class OBDetector:
    """
    Détecte les Order Blocks ICT, Breaker Blocks et BPR
    sur tous les timeframes actifs.

    Order Block Bullish :
        Dernière bougie BEARISH avant une impulsion haussière ≥ 2× ATR.
        Zone d'entrée = corps de la bougie bearish (open → close).

    Order Block Bearish :
        Dernière bougie BULLISH avant une impulsion baissière ≥ 2× ATR.
        Zone d'entrée = corps de la bougie bullish (open → close).

    Breaker Block :
        OB dont le prix a traversé le corps. Ancienne demande → offre,
        ancienne offre → demande. Utilisé comme résistance/support retourné.

    BPR (Balanced Price Range) :
        Chevauchement d'un FVG bullish et d'un FVG bearish consécutifs.
        Zone de consolidation premium pour entrée institutionnelle.
    """

    def __init__(self, data_store: DataStore, fvg_detector=None):
        self._ds          = data_store
        self._fvg         = fvg_detector   # optionnel pour BPR
        self._lock        = threading.RLock()
        self._cache: dict[str, dict[str, dict]] = {}
        # Format : _cache[pair][tf] = {ob_list, breaker_list, bpr_list}
        logger.info("OBDetector initialisé")

    # ══════════════════════════════════════════════════════════
    # MÉTHODE PRINCIPALE — SCAN COMPLET
    # ══════════════════════════════════════════════════════════

    def scan_pair(self, pair: str) -> dict:
        """
        Scan tous les TF actifs pour une paire.
        Détecte OB, Breakers et BPR, met à jour les statuts.

        Args:
            pair: ex. "EURUSD"

        Returns:
            dict {tf: {ob_list, breaker_list, bpr_list}}
        """
        results: dict[str, dict] = {}

        for tf in Trading.TIMEFRAMES:
            df = self._ds.get_candles(pair, tf)
            if df is None or len(df) < ATR_PERIOD + 5:
                logger.debug(f"OB scan ignoré — {pair} {tf} | bougies insuffisantes")
                continue

            atr       = self._calculate_atr(df)
            ob_list   = self._detect_ob(pair, tf, df, atr)
            ob_list   = self._update_ob_statuses(ob_list, df)

            breakers  = self._extract_breakers(ob_list)
            bpr_list  = self._detect_bpr(pair, tf, df, atr)

            results[tf] = {
                "ob_list":      ob_list,
                "breaker_list": breakers,
                "bpr_list":     bpr_list,
            }

            logger.debug(
                f"OB scan — {pair} {tf} | "
                f"ob={len(ob_list)} | "
                f"breakers={len(breakers)} | "
                f"bpr={len(bpr_list)} | "
                f"atr={round(atr, 6)}"
            )

        with self._lock:
            if pair not in self._cache:
                self._cache[pair] = {}

            # Fusionner avec les résultats existants
            for tf, new_data in results.items():
                existing = self._cache[pair].get(tf, {"ob_list": [], "breaker_list": [], "bpr_list": []})
                
                # Master dict pour les OBs (indexer par ID timestamp)
                ob_master = {ob["id"]: ob for ob in existing["ob_list"]}
                for ob in new_data["ob_list"]:
                    if ob["id"] not in ob_master:
                        ob_master[ob["id"]] = ob

                # Mettre à jour les statuts sur TOUS les OBs de la master list
                df = self._ds.get_candles(pair, tf)
                final_ob_list = self._update_ob_statuses(list(ob_master.values()), df)

                # Extraire breakers à partir des OBs BROKEN
                # Note: On garde aussi les breakers de façon persistante ?
                # Pour l'instant, on regenere la liste breaker_list à partir des OBs BROKEN
                # mais on peut aussi merger bpr_list
                new_breakers = self._extract_breakers(final_ob_list)
                
                # Update cache
                self._cache[pair][tf] = {
                    "ob_list":      [ob for ob in final_ob_list if ob["status"] != OB_BROKEN],
                    "breaker_list": new_breakers,
                    "bpr_list":     new_data["bpr_list"], # BPR reste calculé sur fenêtre actuelle
                }

        with self._lock:
            self._ds.set_analysis(pair, "ob", self._cache[pair])
        return self._cache[pair]

    # ══════════════════════════════════════════════════════════
    # DÉTECTION ORDER BLOCKS
    # ══════════════════════════════════════════════════════════

    def _detect_ob(self, pair: str, tf: str,
                   df: pd.DataFrame, atr: float) -> list:
        """
        Parcourt les bougies pour identifier les Order Blocks valides.

        Règle de validation ICT stricte :
          - Bougie = manipulation avant l'impulsion
          - Impulsion suivante ≥ ATR_IMPULSE_FACTOR × ATR
          - L'impulsion doit casser le High (pour Bull) ou le Low (pour Bear) de la zone
          - Corps bougie candidate ≥ ATR_MIN_OB_SIZE × ATR

        Returns:
            liste de dicts OB
        """
        ob_list   = []
        opens     = df["open"].values
        highs     = df["high"].values
        lows      = df["low"].values
        closes    = df["close"].values
        times     = df.index if hasattr(df.index, '__iter__') else df["time"].values

        min_body  = ATR_MIN_OB_SIZE * atr
        min_move  = ATR_IMPULSE_FACTOR * atr
        lookback  = min(MAX_OB_LOOKBACK, len(df) - 3)

        for i in range(len(df) - lookback, len(df) - 2):
            if i < 0:
                continue

            body_size = abs(closes[i] - opens[i])
            if body_size < min_body:
                continue

            is_bearish_candle = closes[i] < opens[i]
            is_bullish_candle = closes[i] > opens[i]

            # ── OB Bullish : manipulation bearish suivie d'impulsion cassant structure
            if is_bearish_candle:
                impulse_high = max(highs[i+1:i+6]) if i + 6 <= len(df) else max(highs[i+1:])
                impulse = impulse_high - lows[i]

                # Validation ICT stricte: le mouvement doit casser le High de l'OB et avoir de la force (ATR)
                bos_achieved = impulse_high > highs[i]
                
                if impulse >= min_move and bos_achieved:
                    ob_list.append({
                        "id":          f"OB_BULL_{pair}_{tf}_{str(times[i])}",
                        "pair":        pair,
                        "tf":          tf,
                        "type":        "BULL_OB",
                        "direction":   "BULLISH",
                        "top":         round(max(opens[i], closes[i]), 6),
                        "bottom":      round(min(opens[i], closes[i]), 6),
                        "high":        round(highs[i], 6),
                        "low":         round(lows[i],  6),
                        "body_size":   round(body_size, 6),
                        "impulse":     round(impulse,   6),
                        "atr_ratio":   round(impulse / atr, 2) if atr > 0 else 0,
                        "formed_at":   str(times[i]),
                        "candle_idx":  i,
                        "status":      OB_VALID,
                        "tested_at":   None,
                        "broken_at":   None,
                        "touch_count": 0,
                    })

            # ── OB Bearish : manipulation bullish suivie d'impulsion cassant structure
            elif is_bullish_candle:
                impulse_low = min(lows[i+1:i+6]) if i + 6 <= len(df) else min(lows[i+1:])
                impulse = highs[i] - impulse_low
                
                # Validation ICT stricte: le mouvement doit casser le Low de l'OB et avoir de la force
                bos_achieved = impulse_low < lows[i]

                if impulse >= min_move and bos_achieved:
                    ob_list.append({
                        "id":          f"OB_BEAR_{pair}_{tf}_{str(times[i])}",
                        "pair":        pair,
                        "tf":          tf,
                        "type":        "BEAR_OB",
                        "direction":   "BEARISH",
                        "top":         round(max(opens[i], closes[i]), 6),
                        "bottom":      round(min(opens[i], closes[i]), 6),
                        "high":        round(highs[i], 6),
                        "low":         round(lows[i],  6),
                        "body_size":   round(body_size, 6),
                        "impulse":     round(impulse,   6),
                        "atr_ratio":   round(impulse / atr, 2) if atr > 0 else 0,
                        "formed_at":   str(times[i]),
                        "candle_idx":  i,
                        "status":      OB_VALID,
                        "tested_at":   None,
                        "broken_at":   None,
                        "touch_count": 0,
                    })

        return ob_list

    # ══════════════════════════════════════════════════════════
    # MISE À JOUR STATUTS OB
    # ══════════════════════════════════════════════════════════

    def _update_ob_statuses(self, ob_list: list,
                             df: pd.DataFrame) -> list:
        """
        Met à jour le statut de chaque OB selon les prix post-formation :
          - VALID  : prix n'est pas revenu dans l'OB
          - TESTED : prix a touché le corps de l'OB (zone d'entrée active)
          - BROKEN : prix a traversé l'intégralité de l'OB → Breaker potentiel

        Un OB TESTED reste exploitable (entrée ICT classique).
        Un OB BROKEN devient Breaker Block (polarité inversée).
        """
        highs = df["high"].values
        lows  = df["low"].values
        times = df.index if hasattr(df.index, '__iter__') else df["time"].values

        for ob in ob_list:
            idx = ob.get("candle_idx", 0) + 1
            top = ob["top"]
            bot = ob["bottom"]

            # Si l'OB est ancien et n'a plus cet index dans le DF actuel, on scan tout le DF
            start_j = max(0, idx)
            if start_j >= len(df):
                start_j = 0

            for j in range(start_j, len(df)):
                h = highs[j]
                l = lows[j]

                if ob["direction"] == "BULLISH":
                    if l <= bot:
                        ob["status"]    = OB_BROKEN
                        ob["broken_at"] = str(times[j])
                        break
                    elif l <= top and ob["status"] in (OB_VALID, OB_TESTED):
                        # On compte le nombre de fois où c'est mitigé.
                        # ICT rule: Plus d'1 ou 2 fois = invalidé car les algos interbancaires ne le défendent plus.
                        if ob["touch_count"] >= 2:
                            ob["status"] = OB_BROKEN
                            ob["broken_at"] = str(times[j])
                            break
                        ob["status"]   = OB_TESTED
                        ob["tested_at"] = str(times[j])
                        ob["touch_count"] += 1

                else:  # BEARISH
                    if h >= top:
                        ob["status"]    = OB_BROKEN
                        ob["broken_at"] = str(times[j])
                        break
                    elif h >= bot and ob["status"] in (OB_VALID, OB_TESTED):
                        if ob["touch_count"] >= 2:
                            ob["status"] = OB_BROKEN
                            ob["broken_at"] = str(times[j])
                            break
                        ob["status"]   = OB_TESTED
                        ob["tested_at"] = str(times[j])
                        ob["touch_count"] += 1

        return ob_list

    # ══════════════════════════════════════════════════════════
    # EXTRACTION BREAKER BLOCKS
    # ══════════════════════════════════════════════════════════

    def _extract_breakers(self, ob_list: list) -> list:
        """
        Extrait les Breaker Blocks depuis les OB avec statut BROKEN.
        Un Breaker Block est un OB dont la polarité est inversée :
          - Ancien BULL_OB brisé → résistance baissière
          - Ancien BEAR_OB brisé → support haussier

        Returns:
            liste de dicts Breaker Block
        """
        breakers = []
        for ob in ob_list:
            if ob["status"] != OB_BROKEN:
                continue

            breakers.append({
                "id":           f"BB_{ob['id']}",
                "pair":         ob["pair"],
                "tf":           ob["tf"],
                "type":         "BULL_BREAKER" if ob["direction"] == "BEARISH" else "BEAR_BREAKER",
                "direction":    "BULLISH" if ob["direction"] == "BEARISH" else "BEARISH",
                "top":          ob["top"],
                "bottom":       ob["bottom"],
                "origin_ob_id": ob["id"],
                "broken_at":    ob["broken_at"],
                "status":       BB_VALID,
            })

        return breakers

    # ══════════════════════════════════════════════════════════
    # DÉTECTION BPR (BALANCED PRICE RANGE)
    # ══════════════════════════════════════════════════════════

    def _detect_bpr(self, pair: str, tf: str,
                    df: pd.DataFrame, atr: float) -> list:
        """
        Détecte les BPR : chevauchement d'un FVG Bullish et d'un FVG Bearish
        consécutifs sur le même TF. La zone de chevauchement = BPR.

        Si FVGDetector n'est pas injecté, retourne liste vide.

        Returns:
            liste de dicts BPR
        """
        if self._fvg is None:
            return []

        bpr_list  = []
        bull_fvgs = self._fvg.get_all_fvg(pair, tf, status="FRESH")
        bear_fvgs = [f for f in bull_fvgs if f["direction"] == "BEARISH"]
        bull_fvgs = [f for f in bull_fvgs if f["direction"] == "BULLISH"]

        for bf in bull_fvgs:
            for sf in bear_fvgs:
                overlap_top = min(bf["top"],    sf["top"])
                overlap_bot = max(bf["bottom"], sf["bottom"])

                if overlap_top > overlap_bot:
                    size = overlap_top - overlap_bot
                    if size >= ATR_MIN_OB_SIZE * atr:
                        bpr_list.append({
                            "id":          f"BPR_{pair}_{tf}_{bf['candle_idx']}",
                            "pair":        pair,
                            "tf":          tf,
                            "type":        "BPR",
                            "top":         round(overlap_top, 6),
                            "bottom":      round(overlap_bot, 6),
                            "midpoint":    round((overlap_top + overlap_bot) / 2, 6),
                            "size":        round(size, 6),
                            "bull_fvg_id": bf["id"],
                            "bear_fvg_id": sf["id"],
                            "formed_at":   bf["formed_at"],
                        })

        return bpr_list

    # ══════════════════════════════════════════════════════════
    # CALCUL ATR
    # ══════════════════════════════════════════════════════════

    def _calculate_atr(self, df: pd.DataFrame,
                       period: int = ATR_PERIOD) -> float:
        """
        ATR Wilder (RMA) sur `period` bougies.
        Fallback 0.0001 si données insuffisantes.
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
    # API PUBLIQUE — ACCÈS RÉSULTATS
    # ══════════════════════════════════════════════════════════

    def get_valid_ob(self, pair: str, tf: str,
                     direction: str = None) -> list:
        """
        Retourne les OB avec statut VALID ou TESTED (exploitables).

        Args:
            pair:      ex. "EURUSD"
            tf:        ex. "H4"
            direction: "BULLISH", "BEARISH", ou None

        Returns:
            liste OB exploitables
        """
        with self._lock:
            data = self._cache.get(pair, {}).get(tf, {})

        ob_list = data.get("ob_list", [])
        active  = [o for o in ob_list
                   if o["status"] in (OB_VALID, OB_TESTED)]

        if direction:
            active = [o for o in active if o["direction"] == direction]

        return active

    def get_nearest_ob(self, pair: str, tf: str,
                       current_price: float,
                       direction: str = None) -> Optional[dict]:
        """
        Retourne l'OB exploitable le plus proche du prix actuel.
        Utilisé par KB5Engine pour point d'entrée / invalidation.

        Returns:
            dict OB le plus proche, ou None
        """
        active = self.get_valid_ob(pair, tf, direction)
        if not active:
            return None

        midpoints = [(abs((o["top"] + o["bottom"]) / 2 - current_price), o)
                     for o in active]
        return min(midpoints, key=lambda x: x[0])[1]

    def get_breakers(self, pair: str, tf: str,
                     direction: str = None) -> list:
        """
        Retourne les Breaker Blocks actifs.

        Returns:
            liste Breaker Block dicts
        """
        with self._lock:
            data = self._cache.get(pair, {}).get(tf, {})

        breakers = data.get("breaker_list", [])
        if direction:
            breakers = [b for b in breakers if b["direction"] == direction]

        return breakers

    def get_bpr(self, pair: str, tf: str) -> list:
        """
        Retourne les BPR détectés sur une paire/TF.

        Returns:
            liste BPR dicts
        """
        with self._lock:
            data = self._cache.get(pair, {}).get(tf, {})

        return data.get("bpr_list", [])

    def get_ob_count(self, pair: str, tf: str) -> dict:
        """
        Résumé des comptages OB par statut.
        Consommé par scoring_engine.

        Returns:
            dict {valid, tested, broken, breakers, bpr, total}
        """
        with self._lock:
            data = self._cache.get(pair, {}).get(tf, {})

        ob_list  = data.get("ob_list",      [])
        breakers = data.get("breaker_list", [])
        bpr      = data.get("bpr_list",     [])

        return {
            "valid":    sum(1 for o in ob_list if o["status"] == OB_VALID),
            "tested":   sum(1 for o in ob_list if o["status"] == OB_TESTED),
            "broken":   sum(1 for o in ob_list if o["status"] == OB_BROKEN),
            "breakers": len(breakers),
            "bpr":      len(bpr),
            "total":    len(ob_list),
        }

    def get_snapshot(self, pair: str) -> dict:
        """
        Snapshot complet pour Dashboard Patron.

        Returns:
            dict {tf: {counts, nearest_bull_ob, nearest_bear_ob}}
        """
        snapshot = {}
        with self._lock:
            pair_data = dict(self._cache.get(pair, {}))

        for tf, data in pair_data.items():
            ob_list = data.get("ob_list", [])
            snapshot[tf] = {
                "counts":   self.get_ob_count(pair, tf),
                "breakers": len(data.get("breaker_list", [])),
                "bpr":      len(data.get("bpr_list",     [])),
                "sample_ob": ob_list[-2:],
            }

        return snapshot

    def clear_cache(self, pair: str = None) -> None:
        """
        Vide le cache OB. Appelé par ReconnectManager
        après rechargement des bougies.
        """
        with self._lock:
            if pair:
                self._cache.pop(pair, None)
                logger.info(f"OB cache vidé — Paire : {pair}")
            else:
                self._cache.clear()
                logger.info("OB cache vidé — toutes les paires")

    def __repr__(self) -> str:
        pairs = list(self._cache.keys())
        return f"OBDetector(pairs={pairs})"
