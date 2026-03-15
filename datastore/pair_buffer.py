# datastore/pair_buffer.py
# Sentinel Pro KB5 — Buffer Circulaire par Paire
#
# Responsabilités :
# - Buffer ticks circulaire O(1) par paire  (deque)
# - Buffer bougies par paire/TF             (deque)
# - Accès thread-safe lecture/écriture
# - Fenêtre glissante pour Anomaly Detector
# - Statistiques freshness par paire
# - Purge propre par paire ou TF
# - Séparé du DataStore central : léger, rapide, dédié au buffer

import threading
import logging
from collections import deque
from datetime import datetime

logger = logging.getLogger(__name__)

# Taille des buffers par défaut
DEFAULT_TICK_BUFFER    = 1000   # 1000 derniers ticks par paire
DEFAULT_CANDLE_BUFFER  = 500    # 500 dernières bougies par paire/TF


class PairBuffer:
    """
    Buffer circulaire dédié à une seule paire.

    Deux buffers séparés :
      1. Ticks    → deque(maxlen=N)  O(1) natif
      2. Bougies  → dict{TF: deque(maxlen=N)}

    Pourquoi séparé du DataStore ?
    - DataStore = source de vérité (copies protégées, analyse, KS/CB)
    - PairBuffer = buffer brut haute fréquence (ticks, bougies récentes)
    - PairBuffer est écrit 1x/sec par TickReceiver
    - DataStore est écrit moins souvent par CandleFetcher
    """

    def __init__(
        self,
        pair: str,
        max_ticks: int   = DEFAULT_TICK_BUFFER,
        max_candles: int = DEFAULT_CANDLE_BUFFER,
    ):
        self.pair        = pair
        self.max_ticks   = max_ticks
        self.max_candles = max_candles
        self._lock       = threading.RLock()

        # Buffer ticks : deque O(1)
        self._ticks: deque = deque(maxlen=max_ticks)

        # Buffer bougies : {tf: deque(maxlen=max_candles)}
        self._candles: dict = {}

        # Métadonnées freshness
        self._last_tick_at:   datetime | None = None
        self._last_candle_at: dict            = {}   # {tf: datetime}
        self._tick_count:     int             = 0

        logger.debug(
            f"PairBuffer créé pour {pair} "
            f"[ticks={max_ticks}, candles={max_candles}]"
        )

    # ─────────────────────────────────────────────
    # SECTION 1 — TICKS
    # ─────────────────────────────────────────────

    def add_tick(self, tick_data: dict):
        """
        Ajoute un tick au buffer circulaire.
        O(1) natif deque — pas de recopie mémoire.
        Appelé par TickReceiver à chaque tick reçu.
        """
        with self._lock:
            self._ticks.append(tick_data)
            self._last_tick_at = datetime.utcnow()
            self._tick_count  += 1

    def get_latest_tick(self) -> dict:
        """Dernier tick reçu."""
        with self._lock:
            return dict(self._ticks[-1]) if self._ticks else {}

    def get_recent_ticks(self, n: int = 10) -> list:
        """
        N derniers ticks.
        Utilisé par :
        - AnomalyDetector : détection spike volume, flash crash
        - KS4 : vérification spread sur fenêtre glissante
        """
        with self._lock:
            return [dict(t) for t in list(self._ticks)[-n:]]

    def get_all_ticks(self) -> list:
        """Tous les ticks du buffer. Copie protégée."""
        with self._lock:
            return [dict(t) for t in list(self._ticks)]

    def get_current_spread(self) -> float:
        """
        Spread actuel en pips depuis le dernier tick.
        Utilisé pour vérification KS4 (spread > 3 pips).
        """
        tick = self.get_latest_tick()
        return tick.get("spread", 0.0)

    def get_current_bid(self) -> float:
        return self.get_latest_tick().get("bid", 0.0)

    def get_current_ask(self) -> float:
        return self.get_latest_tick().get("ask", 0.0)

    def is_spread_above(self, threshold_pips: float = 3.0) -> bool:
        """
        True si le spread actuel dépasse le seuil KS4.
        Appelé directement par KillswitchEngine.
        """
        return self.get_current_spread() > threshold_pips

    def tick_count(self) -> int:
        """Nombre total de ticks reçus depuis le démarrage."""
        with self._lock:
            return self._tick_count

    def clear_ticks(self):
        """Vide le buffer ticks. Utilisé lors d'un reset complet."""
        with self._lock:
            self._ticks.clear()
            self._tick_count   = 0
            self._last_tick_at = None
            logger.debug(f"PairBuffer {self.pair} — ticks vidés.")

    # ─────────────────────────────────────────────
    # SECTION 2 — BOUGIES
    # ─────────────────────────────────────────────

    def add_candle(self, timeframe: str, candle: dict):
        """
        Ajoute une bougie au buffer pour un TF donné.
        Crée le deque si le TF n'existe pas encore.
        Appelé par CandleFetcher après chaque fetch.
        """
        with self._lock:
            if timeframe not in self._candles:
                self._candles[timeframe] = deque(maxlen=self.max_candles)
            self._candles[timeframe].append(candle)
            self._last_candle_at[timeframe] = datetime.utcnow()

    def add_candles_bulk(self, timeframe: str, candles: list):
        """
        Ajoute une liste de bougies d'un coup.
        Utilisé lors du chargement initial ou post-reconnexion.
        Plus rapide que N appels add_candle().
        """
        with self._lock:
            if timeframe not in self._candles:
                self._candles[timeframe] = deque(maxlen=self.max_candles)
            self._candles[timeframe].extend(candles)
            self._last_candle_at[timeframe] = datetime.utcnow()
            logger.debug(
                f"PairBuffer {self.pair}/{timeframe} — "
                f"{len(candles)} bougies ajoutées."
            )

    def get_latest_candle(self, timeframe: str) -> dict:
        """
        Dernière bougie du buffer pour ce TF.
        ⚠️ Peut être la bougie EN COURS (non fermée).
        Pour l'analyse KB5 → utiliser get_closed_candle().
        """
        with self._lock:
            buf = self._candles.get(timeframe)
            return dict(buf[-1]) if buf else {}

    def get_closed_candle(self, timeframe: str) -> dict:
        """
        Avant-dernière bougie = dernière bougie FERMÉE.
        iloc[-2] équivalent.
        Utilisé par le Service Analyse KB5.
        """
        with self._lock:
            buf = self._candles.get(timeframe)
            if not buf or len(buf) < 2:
                return {}
            return dict(list(buf)[-2])

    def get_recent_candles(self, timeframe: str, n: int = 50) -> list:
        """
        N dernières bougies pour un TF.
        Utilisé par KB5Engine pour FVG, OB, MSS, scoring.
        """
        with self._lock:
            buf = self._candles.get(timeframe)
            if not buf:
                return []
            return [dict(c) for c in list(buf)[-n:]]

    def get_all_candles(self, timeframe: str) -> list:
        """Toutes les bougies du buffer pour ce TF. Copie protégée."""
        with self._lock:
            buf = self._candles.get(timeframe)
            return [dict(c) for c in list(buf)] if buf else []

    def has_candles(self, timeframe: str) -> bool:
        """True si le buffer contient des bougies pour ce TF."""
        with self._lock:
            buf = self._candles.get(timeframe)
            return bool(buf)

    def candle_count(self, timeframe: str) -> int:
        """Nombre de bougies en buffer pour ce TF."""
        with self._lock:
            buf = self._candles.get(timeframe)
            return len(buf) if buf else 0

    def get_available_timeframes(self) -> list:
        """Liste des TF chargés dans ce buffer."""
        with self._lock:
            return list(self._candles.keys())

    def clear_candles(self, timeframe: str = None):
        """
        Vide les bougies d'un TF précis, ou tous les TF si None.
        Utilisé lors d'un reset ou retrait de paire.
        """
        with self._lock:
            if timeframe:
                self._candles.pop(timeframe, None)
                self._last_candle_at.pop(timeframe, None)
                logger.debug(f"PairBuffer {self.pair}/{timeframe} — bougies vidées.")
            else:
                self._candles.clear()
                self._last_candle_at.clear()
                logger.debug(f"PairBuffer {self.pair} — tous les TF vidés.")

    # ─────────────────────────────────────────────
    # SECTION 3 — FRESHNESS
    # ─────────────────────────────────────────────

    def tick_age_sec(self) -> float:
        """Secondes depuis le dernier tick reçu."""
        with self._lock:
            if self._last_tick_at is None:
                return float("inf")
            return (datetime.utcnow() - self._last_tick_at).total_seconds()

    def candle_age_sec(self, timeframe: str) -> float:
        """Secondes depuis la dernière mise à jour des bougies pour ce TF."""
        with self._lock:
            last = self._last_candle_at.get(timeframe)
            if last is None:
                return float("inf")
            return (datetime.utcnow() - last).total_seconds()

    def is_tick_fresh(self, max_age_sec: int = 5) -> bool:
        """True si un tick a été reçu dans les N dernières secondes."""
        return self.tick_age_sec() <= max_age_sec

    def is_candle_fresh(self, timeframe: str, max_age_sec: int = 120) -> bool:
        """True si les bougies ont été mises à jour dans les N dernières secondes."""
        return self.candle_age_sec(timeframe) <= max_age_sec

    # ─────────────────────────────────────────────
    # SECTION 4 — STATISTIQUES SUPERVISOR
    # ─────────────────────────────────────────────

    def get_stats(self) -> dict:
        """
        Stats complètes de ce buffer pour le Supervisor/Dashboard.
        Inclut freshness, taille buffer, spread actuel.
        """
        with self._lock:
            return {
                "pair":              self.pair,
                "tick_count":        self._tick_count,
                "tick_buffer_size":  len(self._ticks),
                "last_tick_at":      self._last_tick_at,
                "tick_age_sec":      round(self.tick_age_sec(), 1),
                "tick_fresh":        self.is_tick_fresh(),
                "current_spread":    self.get_current_spread(),
                "spread_ks4_alert":  self.is_spread_above(3.0),
                "timeframes_loaded": list(self._candles.keys()),
                "candles_per_tf": {
                    tf: len(buf)
                    for tf, buf in self._candles.items()
                },
                "candle_age_sec": {
                    tf: round(self.candle_age_sec(tf), 1)
                    for tf in self._candles.keys()
                },
            }

    # ─────────────────────────────────────────────
    # RESET COMPLET
    # ─────────────────────────────────────────────

    def reset(self):
        """
        Reset complet du buffer.
        Utilisé lors du retrait d'une paire active
        ou au redémarrage du bot.
        """
        with self._lock:
            self._ticks.clear()
            self._candles.clear()
            self._last_tick_at   = None
            self._last_candle_at = {}
            self._tick_count     = 0
            logger.info(f"PairBuffer {self.pair} — reset complet.")

    def __repr__(self):
        return (
            f"PairBuffer({self.pair} | "
            f"ticks={len(self._ticks)}/{self.max_ticks} | "
            f"TF={list(self._candles.keys())})"
        )
