# execution/behaviour_shield.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Behaviour Shield (Anti-Inducement Final)
══════════════════════════════════════════════════════════════
Responsabilités :
  - Dernier filtre avant envoi d'ordre à MT5
  - Détecter les pièges de manipulation (stop hunt, fake BO)
  - Filtrer les setups périmés ou dupliqués
  - Bloquer les trades de revanche (revenge trading)
  - Détecter les liquidity grabs avant le vrai move
  - Valider la fraîcheur du setup (< MAX_SETUP_AGE_SEC)
  - Retourner un ShieldResult {approved, reason, filters}

8 Filtres du Behaviour Shield :
  BS1 — Stop Hunt       : spike + retour rapide sur niveau clé
  BS2 — Fake Breakout   : cassure sans confirmation HTF
  BS3 — Liquidity Grab  : purge equal highs/lows avant move
  BS4 — News Spike      : entrée < 3 min après mouvement news
  BS5 — Overextension   : price trop loin de l'OB/FVG entry
  BS6 — Revenge Trade   : N pertes consécutives même direction
  BS7 — Duplicate       : même setup < MAX_DUPLICATE_MIN
  BS8 — Staleness       : setup calculé il y a > MAX_AGE_SEC

Dépendances :
  - DataStore      → get_candles(), get_stats()
  - FVGDetector    → get_nearest_fvg()
  - OBDetector     → get_nearest_ob()
  - BiasDetector   → get_direction()
  - config.constants → Trading, Risk

Consommé par :
  - order_manager.py → validation finale avant envoi ordre
══════════════════════════════════════════════════════════════
"""

import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

from datastore.data_store import DataStore
from config.constants import Trading, Risk

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# CONSTANTES BEHAVIOUR SHIELD
# ══════════════════════════════════════════════════════════════

# BS1 — Stop Hunt
STOP_HUNT_REVERSAL_PCT   = 0.70   # retour ≥ 70% du spike = stop hunt
STOP_HUNT_LOOKBACK       = 3      # bougies M15 à analyser

# BS2 — Fake Breakout
FAKE_BO_CONFIRM_CLOSES   = 2      # besoin de 2 closes au-delà du niveau

# BS3 — Liquidity Grab
EQUAL_LEVEL_TOLERANCE    = 0.0002 # tolérance equal highs/lows (2 pips)
LIQ_GRAB_LOOKBACK        = 10     # bougies H1 pour equal levels

# BS4 — News Spike
NEWS_SPIKE_WAIT_SEC      = 180    # 3 min après spike news

# BS5 — Overextension
OVEREXT_ATR_FACTOR       = 3.0    # > 3× ATR depuis l'OB/FVG = trop loin

# BS6 — Revenge Trade
REVENGE_CONSEC_LOSSES    = 3      # blocage après 3 pertes consécutives
REVENGE_SAME_DIRECTION   = True   # uniquement dans la même direction

# BS7 — Duplicate
MAX_DUPLICATE_MIN        = 10     # même signal < 10 min = doublon

# BS8 — Staleness
MAX_SETUP_AGE_SEC        = 300    # setup > 5 min = périmé

# Filtres BLOQUANTS vs AVERTISSEMENT
BS_BLOCKING  = {1, 2, 3, 4, 5, 6, 7, 8}  # tous bloquants par défaut
BS_WARNING   = set()                        # aucun warning pour l'instant

# ══════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════

class BehaviourShield:
    """
    Dernier gardien avant l'envoi d'un ordre à MT5.
    Détecte les pièges de manipulation ICT et les
    comportements pathologiques du bot (revenge, doublon).

    Un seul filtre bloquant suffit à rejeter le setup,
    quelle que soit la qualité du SCALP_OUTPUT.
    """

    def __init__(self,
                 data_store: DataStore,
                 fvg_detector=None,
                 ob_detector=None,
                 bias_detector=None,
                 order_reader=None):
        self._ds     = data_store
        self._fvg    = fvg_detector
        self._ob     = ob_detector
        self._bias   = bias_detector
        self._orders = order_reader
        self._lock   = threading.Lock()

        # Historique des signaux envoyés (pour BS7 doublon)
        self._signal_history: list[dict] = []

        # Cache des derniers rejets par paire
        self._rejection_cache: dict[str, dict] = {}

        logger.info("BehaviourShield initialisé — 8 filtres actifs")

    # ══════════════════════════════════════════════════════════
    # MÉTHODE PRINCIPALE
    # ══════════════════════════════════════════════════════════

    def validate(self, pair: str,
                 scalp_output: dict,
                 allocation: dict) -> dict:
        """
        Validation finale du setup avant envoi ordre.
        Applique les 8 filtres dans l'ordre de priorité.

        Args:
            pair:         ex. "EURUSD"
            scalp_output: dict SCALP_OUTPUT de scoring_engine
            allocation:   dict AllocationResult de capital_allocator

        Returns:
            dict ShieldResult {
                approved, reason, filter_id,
                filters_passed, filters_failed
            }
        """
        now = datetime.now(timezone.utc)

        # Vérifications préalables
        if scalp_output.get("verdict") != "EXECUTE":
            return self._reject("PRE_CHECK",
                                "Verdict non-EXECUTE", 0)

        if not allocation.get("approved", False):
            return self._reject("PRE_CHECK",
                                f"Allocation rejetée : "
                                f"{allocation.get('reason')}", 0)

        entry     = scalp_output.get("entry", 0)
        direction = scalp_output.get("direction", "")
        timestamp = scalp_output.get("timestamp", "")

        filters_passed = []
        filters_failed = []

        # ── BS8 — Staleness (priorité max) ──────────────────
        bs8 = self._check_bs8_staleness(timestamp, now)
        if bs8["triggered"]:
            return self._reject("BS8_STALENESS", bs8["reason"], 8)
        filters_passed.append("BS8")

        # ── BS7 — Duplicate ─────────────────────────────────
        bs7 = self._check_bs7_duplicate(pair, direction, now)
        if bs7["triggered"]:
            return self._reject("BS7_DUPLICATE", bs7["reason"], 7)
        filters_passed.append("BS7")

        # ── BS6 — Revenge Trade ──────────────────────────────
        bs6 = self._check_bs6_revenge(pair, direction)
        if bs6["triggered"]:
            return self._reject("BS6_REVENGE", bs6["reason"], 6)
        filters_passed.append("BS6")

        # ── BS4 — News Spike ─────────────────────────────────
        bs4 = self._check_bs4_news_spike(pair, now)
        if bs4["triggered"]:
            return self._reject("BS4_NEWS_SPIKE", bs4["reason"], 4)
        filters_passed.append("BS4")

        # ── BS5 — Overextension ──────────────────────────────
        bs5 = self._check_bs5_overextension(pair, direction, entry)
        if bs5["triggered"]:
            return self._reject("BS5_OVEREXT", bs5["reason"], 5)
        filters_passed.append("BS5")

        # ── BS1 — Stop Hunt ──────────────────────────────────
        bs1 = self._check_bs1_stop_hunt(pair, direction, entry)
        if bs1["triggered"]:
            return self._reject("BS1_STOP_HUNT", bs1["reason"], 1)
        filters_passed.append("BS1")

        # ── BS3 — Liquidity Grab ─────────────────────────────
        bs3 = self._check_bs3_liquidity_grab(pair, direction)
        if bs3["triggered"]:
            return self._reject("BS3_LIQ_GRAB", bs3["reason"], 3)
        filters_passed.append("BS3")

        # ── BS2 — Fake Breakout ──────────────────────────────
        bs2 = self._check_bs2_fake_breakout(pair, direction, entry)
        if bs2["triggered"]:
            return self._reject("BS2_FAKE_BO", bs2["reason"], 2)
        filters_passed.append("BS2")

        # ── Tous filtres passés → APPROVED ──────────────────
        self._record_signal(pair, direction, now)

        result = {
            "approved":       True,
            "reason":         "Tous filtres BS validés",
            "filter_id":      None,
            "filters_passed": filters_passed,
            "filters_failed": [],
            "timestamp":      now.isoformat(),
        }

        logger.info(
            f"BehaviourShield APPROVED — {pair} | "
            f"Direction : {direction} | "
            f"Filtres : {len(filters_passed)}/8 OK"
        )

        return result

    # ══════════════════════════════════════════════════════════
    # BS8 — STALENESS (SETUP PÉRIMÉ)
    # ══════════════════════════════════════════════════════════

    def _check_bs8_staleness(self, timestamp: str,
                              now: datetime) -> dict:
        """
        BS8 — Vérifie que le SCALP_OUTPUT a été calculé
        il y a moins de MAX_SETUP_AGE_SEC secondes.

        Un setup périmé peut correspondre à des conditions
        de marché qui ont changé depuis le calcul.
        """
        if not timestamp:
            return {"triggered": True,
                    "reason": "Timestamp SCALP_OUTPUT absent"}

        try:
            setup_time = datetime.fromisoformat(
                timestamp.replace("Z", "+00:00")
            )
            age_sec = (now - setup_time).total_seconds()

            if age_sec > MAX_SETUP_AGE_SEC:
                return {
                    "triggered": True,
                    "reason":    (
                        f"Setup périmé : {int(age_sec)}s > "
                        f"max {MAX_SETUP_AGE_SEC}s"
                    ),
                    "age_sec":   int(age_sec),
                }

            return {"triggered": False, "age_sec": int(age_sec)}

        except Exception as e:
            return {"triggered": True,
                    "reason": f"Timestamp invalide : {e}"}

    # ══════════════════════════════════════════════════════════
    # BS7 — DUPLICATE SIGNAL
    # ══════════════════════════════════════════════════════════

    def _check_bs7_duplicate(self, pair: str,
                              direction: str,
                              now: datetime) -> dict:
        """
        BS7 — Vérifie qu'aucun signal identique (même paire +
        même direction) n'a été envoyé dans les dernières
        MAX_DUPLICATE_MIN minutes.

        Protège contre les boucles de soumission d'ordres
        en cas de bug ou de latence supervisor.
        """
        window = timedelta(minutes=MAX_DUPLICATE_MIN)

        with self._lock:
            recent = [
                s for s in self._signal_history
                if s["pair"]      == pair
                and s["direction"] == direction
                and (now - s["sent_at"]).total_seconds()
                    <= window.total_seconds()
            ]

        if recent:
            last = recent[-1]
            minutes_ago = round(
                (now - last["sent_at"]).total_seconds() / 60, 1
            )
            return {
                "triggered": True,
                "reason":    (
                    f"Signal dupliqué — {pair} {direction} "
                    f"déjà envoyé il y a {minutes_ago} min"
                ),
                "last_sent": last["sent_at"].isoformat(),
            }

        return {"triggered": False}

    # ══════════════════════════════════════════════════════════
    # BS6 — REVENGE TRADE
    # ══════════════════════════════════════════════════════════

    def _check_bs6_revenge(self, pair: str,
                            direction: str) -> dict:
        """
        BS6 — Bloque un trade si le bot a accumulé
        REVENGE_CONSEC_LOSSES pertes consécutives dans
        la même direction sur cette paire.

        Le revenge trading est l'une des causes principales
        de drawdown catastrophique en trading algorithmique.

        # TODO: Réactiver BS6 après la phase de test démo.
        # Nécessite l'ajout de get_closed_today() dans OrderReader.
        """
        # ── SUSPENDU EN PHASE DE TEST DÉMO ──────────────────
        # BS6 est temporairement désactivé car la méthode
        # get_closed_today() n'est pas encore disponible.
        # Le bot peut trader sans limite de pertes consécutives.
        return {"triggered": False, "reason": "BS6 suspendu — phase test démo"}

        if self._orders is None:
            return {"triggered": False,
                    "reason": "OrderReader absent — BS6 ignoré"}

        try:
            closed = self._orders.get_closed_today()
            if not closed:
                return {"triggered": False}

            # Filtrer par paire + direction
            bot_magic  = getattr(Trading, "BOT_MAGIC_NUMBER", 20260101)
            same_dir   = [
                o for o in closed
                if o.get("pair")      == pair
                and o.get("direction") == direction
                and o.get("magic")     == bot_magic
            ]

            if not same_dir:
                return {"triggered": False}

            # Compter les pertes consécutives récentes
            consec = 0
            for order in reversed(same_dir):
                if order.get("profit", 0) < 0:
                    consec += 1
                else:
                    break

            if consec >= REVENGE_CONSEC_LOSSES:
                return {
                    "triggered": True,
                    "reason":    (
                        f"Revenge trade bloqué — {pair} {direction} : "
                        f"{consec} pertes consécutives "
                        f"(max {REVENGE_CONSEC_LOSSES})"
                    ),
                    "consec": consec,
                }

            return {"triggered": False, "consec": consec}

        except Exception as e:
            logger.error(f"BehaviourShield BS6 erreur : {e}")
            return {"triggered": False}

    # ══════════════════════════════════════════════════════════
    # BS4 — NEWS SPIKE
    # ══════════════════════════════════════════════════════════

    def _check_bs4_news_spike(self, pair: str,
                               now: datetime) -> dict:
        """
        BS4 — Détecte un spike de volatilité récent sur M1/M5
        caractéristique d'une réaction news.

        Un spike news = bougie M5 dont le range > 3× ATR M5 moyen
        dans les 3 dernières minutes.
        Règle ICT : attendre le retour calme avant d'entrer.
        """
        df_m5 = self._ds.get_candles(pair, "M5")
        if df_m5 is None or len(df_m5) < 20:
            return {"triggered": False,
                    "reason": "M5 insuffisant — BS4 ignoré"}

        highs  = df_m5["high"].values
        lows   = df_m5["low"].values
        closes = df_m5["close"].values

        # ATR M5 moyen (20 dernières bougies hors la dernière)
        ranges = [highs[i] - lows[i] for i in range(len(df_m5) - 1)]
        atr_avg = sum(ranges[-20:]) / 20 if len(ranges) >= 20 else 0

        if atr_avg <= 0:
            return {"triggered": False}

        # Dernière bougie M5 fermée
        last_range = highs[-2] - lows[-2]
        spike_ratio = last_range / atr_avg

        if spike_ratio >= 3.0:
            return {
                "triggered": True,
                "reason":    (
                    f"Spike news détecté sur {pair} M5 — "
                    f"Range {spike_ratio:.1f}× ATR moyen | "
                    f"Attendre {NEWS_SPIKE_WAIT_SEC}s"
                ),
                "spike_ratio": round(spike_ratio, 2),
            }

        return {"triggered": False, "spike_ratio": round(spike_ratio, 2)}

    # ══════════════════════════════════════════════════════════
    # BS5 — OVEREXTENSION
    # ══════════════════════════════════════════════════════════

    def _check_bs5_overextension(self, pair: str,
                                  direction: str,
                                  entry: float) -> dict:
        """
        BS5 — Vérifie que le prix actuel n'est pas trop loin
        de la zone d'entrée (OB/FVG).

        Si price > OVEREXT_ATR_FACTOR × ATR depuis l'OB/FVG,
        le moment optimal est passé → attendre le prochain setup.

        Règle ICT : entrer sur la zone, pas après qu'elle soit dépassée.
        """
        df_h1 = self._ds.get_candles(pair, "H1")
        if df_h1 is None or len(df_h1) < 15:
            return {"triggered": False,
                    "reason": "H1 insuffisant — BS5 ignoré"}

        # ATR H1
        highs  = df_h1["high"].values
        lows   = df_h1["low"].values
        closes = df_h1["close"].values

        tr_list = [
            max(highs[i] - lows[i],
                abs(highs[i]  - closes[i - 1]),
                abs(lows[i]   - closes[i - 1]))
            for i in range(1, len(df_h1))
        ]
        atr_h1  = sum(tr_list[-14:]) / 14 if len(tr_list) >= 14 else 0

        current = float(df_h1["close"].iloc[-1])

        if atr_h1 <= 0 or entry is None or entry == 0:
            return {"triggered": False}

        # Distance prix actuel vs zone d'entrée
        distance    = abs(current - entry)
        dist_factor = distance / atr_h1

        if dist_factor > OVEREXT_ATR_FACTOR:
            return {
                "triggered": True,
                "reason":    (
                    f"Overextension {pair} — Price {current} "
                    f"trop loin de l'entrée {entry} | "
                    f"{dist_factor:.1f}× ATR > max {OVEREXT_ATR_FACTOR}×"
                ),
                "distance_atr": round(dist_factor, 2),
            }

        return {
            "triggered":    False,
            "distance_atr": round(dist_factor, 2),
        }

    # ══════════════════════════════════════════════════════════
    # BS1 — STOP HUNT
    # ══════════════════════════════════════════════════════════

    def _check_bs1_stop_hunt(self, pair: str,
                              direction: str,
                              entry: float) -> dict:
        """
        BS1 — Détecte un stop hunt récent sur M15.

        Stop hunt = price spike cassant un niveau clé
        puis retour rapide (≥ 70% du spike) dans la même bougie
        ou la suivante. Signe de manipulation institutionnelle
        pour purger les stops avant le vrai move.

        Règle ICT : après un stop hunt BULLISH, attendre la
        confirmation de la prise de direction avant d'entrer BULL.
        """
        df_m15 = self._ds.get_candles(pair, "M15")
        if df_m15 is None or len(df_m15) < STOP_HUNT_LOOKBACK + 2:
            return {"triggered": False,
                    "reason": "M15 insuffisant — BS1 ignoré"}

        recent = df_m15.iloc[-STOP_HUNT_LOOKBACK - 1:]
        highs  = recent["high"].values
        lows   = recent["low"].values
        opens  = recent["open"].values
        closes = recent["close"].values

        for i in range(len(recent) - 1):
            candle_range = highs[i] - lows[i]
            if candle_range <= 0:
                continue

            body      = abs(closes[i] - opens[i])
            wick_up   = highs[i]  - max(opens[i], closes[i])
            wick_down = min(opens[i], closes[i]) - lows[i]

            # Stop hunt BEARISH : longue mèche haute + retour
            if direction == "BULLISH":
                wick_ratio = wick_up / candle_range
                if wick_ratio >= STOP_HUNT_REVERSAL_PCT:
                    return {
                        "triggered": True,
                        "reason":    (
                            f"Stop hunt BEARISH détecté sur {pair} M15 — "
                            f"Mèche haute {wick_ratio:.0%} du range | "
                            f"Attendre confirmation haussière"
                        ),
                        "wick_ratio": round(wick_ratio, 3),
                    }

            # Stop hunt BULLISH : longue mèche basse + retour
            elif direction == "BEARISH":
                wick_ratio = wick_down / candle_range
                if wick_ratio >= STOP_HUNT_REVERSAL_PCT:
                    return {
                        "triggered": True,
                        "reason":    (
                            f"Stop hunt BULLISH détecté sur {pair} M15 — "
                            f"Mèche basse {wick_ratio:.0%} du range | "
                            f"Attendre confirmation baissière"
                        ),
                        "wick_ratio": round(wick_ratio, 3),
                    }

        return {"triggered": False}

    # ══════════════════════════════════════════════════════════
    # BS3 — LIQUIDITY GRAB
    # ══════════════════════════════════════════════════════════

    def _check_bs3_liquidity_grab(self, pair: str,
                                   direction: str) -> dict:
        """
        BS3 — Détecte un Liquidity Grab récent sur H1.

        Liquidity Grab = price vient de purger des equal highs
        ou equal lows évidents (stops regroupés des retail traders).
        Après un LG, le vrai move peut être dans la direction opposée.

        Equal highs/lows = niveaux à ±EQUAL_LEVEL_TOLERANCE près.
        """
        df_h1 = self._ds.get_candles(pair, "H1")
        if df_h1 is None or len(df_h1) < LIQ_GRAB_LOOKBACK + 3:
            return {"triggered": False,
                    "reason": "H1 insuffisant — BS3 ignoré"}

        highs = df_h1["high"].values[-(LIQ_GRAB_LOOKBACK + 3):]
        lows  = df_h1["low"].values[-(LIQ_GRAB_LOOKBACK + 3):]

        # Chercher des equal highs (stops au-dessus)
        equal_highs = []
        for i in range(len(highs) - 2):
            if abs(highs[i] - highs[i + 1]) <= EQUAL_LEVEL_TOLERANCE:
                equal_highs.append(highs[i])

        # Chercher des equal lows (stops en-dessous)
        equal_lows = []
        for i in range(len(lows) - 2):
            if abs(lows[i] - lows[i + 1]) <= EQUAL_LEVEL_TOLERANCE:
                equal_lows.append(lows[i])

        last_high = highs[-1]
        last_low  = lows[-1]

        # LG BEARISH : price vient de purger equal highs
        if direction == "BULLISH" and equal_highs:
            purged = [h for h in equal_highs
                      if last_high > h and
                      abs(last_high - h) < EQUAL_LEVEL_TOLERANCE * 3]
            if purged:
                return {
                    "triggered": True,
                    "reason":    (
                        f"Liquidity Grab BEARISH détecté {pair} H1 — "
                        f"Equal highs purgés à {round(purged[0], 5)} | "
                        f"Possible retournement baissier"
                    ),
                    "level": round(purged[0], 5),
                }

        # LG BULLISH : price vient de purger equal lows
        if direction == "BEARISH" and equal_lows:
            purged = [l for l in equal_lows
                      if last_low < l and
                      abs(last_low - l) < EQUAL_LEVEL_TOLERANCE * 3]
            if purged:
                return {
                    "triggered": True,
                    "reason":    (
                        f"Liquidity Grab BULLISH détecté {pair} H1 — "
                        f"Equal lows purgés à {round(purged[0], 5)} | "
                        f"Possible retournement haussier"
                    ),
                    "level": round(purged[0], 5),
                }

        return {"triggered": False}

    # ══════════════════════════════════════════════════════════
    # BS2 — FAKE BREAKOUT
    # ══════════════════════════════════════════════════════════

    def _check_bs2_fake_breakout(self, pair: str,
                                  direction: str,
                                  entry: float) -> dict:
        """
        BS2 — Détecte une fausse cassure de niveau H1.

        Fake Breakout = price ferme au-delà d'un niveau clé
        mais sans FAKE_BO_CONFIRM_CLOSES confirmations successives.
        Une seule bougie qui ferme au-delà = potentiellement faux.

        Règle ICT : une cassure valide nécessite 2 closes
        consécutifs au-delà du niveau.
        """
        df_h1 = self._ds.get_candles(pair, "H1")
        if df_h1 is None or len(df_h1) < 6:
            return {"triggered": False,
                    "reason": "H1 insuffisant — BS2 ignoré"}

        closes = df_h1["close"].values[-6:]
        highs  = df_h1["high"].values[-6:]
        lows   = df_h1["low"].values[-6:]

        # Niveau de référence = high/low des 5 bougies précédentes
        if direction == "BULLISH":
            ref_level = max(highs[-6:-1])
            # Cassure = close[-1] > ref_level
            if closes[-1] > ref_level:
                # Vérifier si la bougie précédente confirmait aussi
                prev_confirmed = closes[-2] > ref_level
                if not prev_confirmed:
                    return {
                        "triggered": True,
                        "reason":    (
                            f"Fake Breakout BULLISH {pair} H1 — "
                            f"Close {closes[-1]:.5f} > niveau "
                            f"{ref_level:.5f} sans confirmation "
                            f"bougie précédente"
                        ),
                        "ref_level": round(ref_level, 5),
                    }

        elif direction == "BEARISH":
            ref_level = min(lows[-6:-1])
            if closes[-1] < ref_level:
                prev_confirmed = closes[-2] < ref_level
                if not prev_confirmed:
                    return {
                        "triggered": True,
                        "reason":    (
                            f"Fake Breakout BEARISH {pair} H1 — "
                            f"Close {closes[-1]:.5f} < niveau "
                            f"{ref_level:.5f} sans confirmation "
                            f"bougie précédente"
                        ),
                        "ref_level": round(ref_level, 5),
                    }

        return {"triggered": False}

    # ══════════════════════════════════════════════════════════
    # UTILITAIRES INTERNES
    # ══════════════════════════════════════════════════════════

    def _reject(self, filter_id: str, reason: str,
                bs_num: int) -> dict:
        """Construit un ShieldResult de rejet standardisé."""
        logger.warning(
            f"BehaviourShield REJETÉ — "
            f"Filtre : {filter_id} | "
            f"Raison : {reason}"
        )
        return {
            "approved":       False,
            "reason":         reason,
            "filter_id":      filter_id,
            "bs_num":         bs_num,
            "filters_passed": [],
            "filters_failed": [filter_id],
            "timestamp":      datetime.now(timezone.utc).isoformat(),
        }

    def _record_signal(self, pair: str, direction: str,
                        now: datetime) -> None:
        """
        Enregistre un signal approuvé dans l'historique.
        Utilisé par BS7 pour détecter les doublons.
        """
        with self._lock:
            self._signal_history.append({
                "pair":      pair,
                "direction": direction,
                "sent_at":   now,
            })
            # Garder seulement les 200 derniers signaux
            if len(self._signal_history) > 200:
                self._signal_history = self._signal_history[-200:]

    # ══════════════════════════════════════════════════════════
    # API PUBLIQUE
    # ══════════════════════════════════════════════════════════

    def get_last_rejection(self, pair: str) -> Optional[dict]:
        """
        Retourne le dernier rejet pour une paire.
        Utilisé par Dashboard Patron pour afficher la raison.

        Returns:
            dict rejet ou None
        """
        with self._lock:
            return dict(self._rejection_cache.get(pair, {})) or None

    def get_signal_history(self, pair: str = None,
                            last_n: int = 20) -> list:
        """
        Retourne l'historique des signaux approuvés.
        Utilisé par Dashboard Patron section historique.

        Args:
            pair:   filtre par paire optionnel
            last_n: nombre d'entrées max

        Returns:
            liste de dicts {pair, direction, sent_at}
        """
        with self._lock:
            history = list(self._signal_history)

        if pair:
            history = [h for h in history if h["pair"] == pair]

        return history[-last_n:]

    def get_rejection_stats(self) -> dict:
        """
        Statistiques des rejets par filtre BS.
        Consommé par Dashboard Patron section audit.

        Returns:
            dict {BS1: count, BS2: count, ...}
        """
        with self._lock:
            cache = dict(self._rejection_cache)

        counts: dict[str, int] = {}
        for _, rejection in cache.items():
            fid = rejection.get("filter_id", "UNKNOWN")
            counts[fid] = counts.get(fid, 0) + 1

        return counts

    def get_snapshot(self, pair: str = None) -> dict:
        """
        Snapshot pour Dashboard Patron.

        Returns:
            dict {signals_sent, last_rejection, stats}
        """
        with self._lock:
            total_signals = len(self._signal_history)

        return {
            "total_signals_sent": total_signals,
            "last_rejection":     self.get_last_rejection(pair)
                                  if pair else None,
            "rejection_stats":    self.get_rejection_stats(),
            "filters_active":     8,
        }

    def clear_history(self) -> None:
        """
        Vide l'historique des signaux.
        Appelé par supervisor en début de session.
        """
        with self._lock:
            self._signal_history.clear()
            self._rejection_cache.clear()
        logger.info("BehaviourShield — historique vidé")

    def __repr__(self) -> str:
        with self._lock:
            total = len(self._signal_history)
        return (
            f"BehaviourShield("
            f"filters=8, "
            f"signals_sent={total})"
        )
