# gateway/tick_receiver.py
# Sentinel Pro KB5 — Réception Ticks Temps Réel
#
# Responsabilités :
# - 1 thread par paire active
# - Behaviour Shield : max 1 tick/sec/paire
# - Spread calculé correctement par instrument (FOREX/JPY/GOLD/INDEX)
# - Multi-callbacks : DataStore, AnomalyDetector, Media
# - Statistiques par paire pour Supervisor
# - Détection paire silencieuse (pas de tick > 30 sec)
# - Stop propre avec join du thread
# - symbolselect avant écoute
# - Freeze / Unfreeze pendant déconnexion

import MetaTrader5 as mt5
import threading
import time
import logging
from datetime import datetime, timezone
from collections import deque
from config.constants import Gateway, BehaviourShield

logger = logging.getLogger(__name__)

# Seuil silence paire : alerte si aucun tick reçu depuis X sec
SILENT_PAIR_THRESHOLD_SEC = 30

# Statuts possibles par paire
class PairStatus:
    ACTIVE   = "ACTIVE"
    FROZEN   = "FROZEN"
    SILENT   = "SILENT"
    STOPPED  = "STOPPED"
    ERROR    = "ERROR"


class TickReceiver:
    """
    Reçoit les ticks en temps réel pour toutes les paires actives.
    Thread-safe. Multi-callbacks. Spread corrigé par instrument.

    Séquence démarrage paire :
      1. symbolselect  — active la paire dans MT5
      2. Thread tick_loop lancé
      3. Callbacks notifiés à chaque tick

    Séquence arrêt paire :
      1. stop_event.set()
      2. thread.join(timeout)  — arrêt propre
      3. Statut → STOPPED
    """

    def __init__(self):
        self._threads    = {}   # pair → Thread
        self._stopevents = {}   # pair → Event
        self._stats      = {}   # pair → dict stats
        self._status     = {}   # pair → PairStatus
        self._ticks      = {}   # pair → deque(maxlen=100) buffer récent
        self._callbacks  = []   # multi-callbacks abonnés
        self._lock       = threading.RLock()

    # ─────────────────────────────────────────────
    # ABONNEMENTS MULTI-CALLBACKS
    # ─────────────────────────────────────────────

    def subscribe(self, callback):
        """
        Abonne un module aux ticks.
        Usage :
            tick_receiver.subscribe(datastore.add_tick)
            tick_receiver.subscribe(anomaly_detector.on_tick)
            tick_receiver.subscribe(media_service.on_tick)
        """
        if callback not in self._callbacks:
            self._callbacks.append(callback)
            logger.debug(f"Abonné ticks : {callback.__self__.__class__.__name__}")

    def _notify(self, tick_data: dict):
        """Notifie tous les abonnés. Chaque erreur est isolée."""
        for cb in self._callbacks:
            try:
                cb(tick_data)
            except Exception as e:
                logger.error(f"Callback tick échoué [{cb.__self__.__class__.__name__}] : {e}")

    # ─────────────────────────────────────────────
    # GESTION DES PAIRES
    # ─────────────────────────────────────────────

    def start_pair(self, pair: str):
        """Démarre l'écoute tick pour une paire. Idempotent."""
        with self._lock:
            if pair in self._threads:
                logger.debug(f"Tick receiver déjà actif pour {pair}.")
                return

            # Activation symbole MT5 obligatoire
            if not self._ensure_symbol_active(pair):
                self._status[pair] = PairStatus.ERROR
                logger.error(f"Impossible d'activer le symbole {pair} — tick receiver non démarré.")
                return

            stop_event = threading.Event()
            self._stopevents[pair] = stop_event
            self._stats[pair] = {
                "tick_count": 0,
                "last_tick_at": None,
                "last_spread": 0.0,
                "last_bid": 0.0,
                "last_ask": 0.0,
                "silent_alerts": 0,
            }
            self._status[pair] = PairStatus.ACTIVE
            self._ticks[pair] = deque(maxlen=100)

            t = threading.Thread(
                target=self._tick_loop,
                args=(pair, stop_event),
                daemon=True,
                name=f"Tick-{pair}"
            )
            self._threads[pair] = t
            t.start()
            logger.info(f"Tick receiver démarré pour {pair}.")

    def stop_pair(self, pair: str):
        """Arrête proprement le thread tick d'une paire avec join."""
        with self._lock:
            if pair not in self._stopevents:
                return
            self._stopevents[pair].set()
            thread = self._threads.get(pair)

        # Join hors du lock pour éviter deadlock
        if thread and thread.is_alive():
            thread.join(timeout=3)

        with self._lock:
            self._stopevents.pop(pair, None)
            self._threads.pop(pair, None)
            self._status[pair] = PairStatus.STOPPED
            logger.info(f"Tick receiver arrêté pour {pair}.")

    def stop_all(self):
        """Arrête tous les threads tick. Appelé par ReconnectManager.freeze()."""
        pairs = list(self._stopevents.keys())
        for pair in pairs:
            self.stop_pair(pair)
        logger.info(f"Tick receiver — tous arrêtés ({len(pairs)} paires).")

    def freeze(self):
        """
        Alias stop_all() utilisé par ReconnectManager lors d'une déconnexion.
        Stoppe tous les threads, marque statut FROZEN.
        """
        pairs = list(self._stopevents.keys())
        self.stop_all()
        with self._lock:
            for pair in pairs:
                self._status[pair] = PairStatus.FROZEN
        logger.info("TickReceiver gelé pendant déconnexion.")

    def unfreeze(self, active_pairs: list):
        """
        Redémarre les ticks après reconnexion.
        Appelé par ReconnectManager.restart_tick_receiver().
        """
        for pair in active_pairs:
            self.start_pair(pair)
        logger.info(f"TickReceiver redémarré pour {active_pairs}.")

    # ─────────────────────────────────────────────
    # BOUCLE TICK
    # ─────────────────────────────────────────────

    def _tick_loop(self, pair: str, stop_event: threading.Event):
        """
        Boucle principale tick pour une paire.
        Behaviour Shield : max 1 update/sec/paire.
        Détecte paire silencieuse > SILENT_PAIR_THRESHOLD_SEC.
        """
        last_tick_time = None

        while not stop_event.is_set():
            stop_event.wait(Gateway.TICK_UPDATE_INTERVAL_SEC)  # Behaviour Shield 1 sec
            if stop_event.is_set():
                break

            try:
                tick = mt5.symbol_info_tick(pair)
                if tick is None:
                    self._check_silence(pair)
                    continue

                # Éviter doublons
                if last_tick_time == tick.time:
                    self._check_silence(pair)
                    continue

                last_tick_time = tick.time

                # Spread corrigé par instrument
                spread = self._calc_spread(pair, tick)

                tick_data = {
                    "pair":        pair,
                    "timestamp":   datetime.fromtimestamp(tick.time, tz=timezone.utc),
                    "bid":         tick.bid,
                    "ask":         tick.ask,
                    "spread":      spread,        # en pips, correct pour tous instruments
                    "last":        tick.last,
                    "volume":      tick.volume,
                    "volume_real": tick.volume_real,  # volume réel Exness
                    "flags":       tick.flags,         # type de tick pour AnomalyDetector
                }

                # Mise à jour stats et buffer
                with self._lock:
                    s = self._stats.get(pair, {})
                    s["tick_count"]    += 1
                    s["last_tick_at"]   = datetime.utcnow()
                    s["last_spread"]    = spread
                    s["last_bid"]       = tick.bid
                    s["last_ask"]       = tick.ask
                    self._stats[pair]   = s
                    self._status[pair]  = PairStatus.ACTIVE
                    self._ticks[pair].append(tick_data)

                # Notifier tous les abonnés
                self._notify(tick_data)

            except Exception as e:
                logger.error(f"Erreur tick_loop {pair} : {e}")

    # ─────────────────────────────────────────────
    # SPREAD CORRIGÉ PAR INSTRUMENT
    # ─────────────────────────────────────────────

    def _calc_spread(self, pair: str, tick) -> float:
        """
        Calcule le spread en pips, correct pour chaque type d'instrument.

        Problème version initiale : spread = round((ask - bid) * 10000, 1)
        → USDJPY : 151.502 - 151.498 = 0.004 * 10000 = 40 pips  ❌ (devrait être 0.4)
        → XAUUSD : 2345.50 - 2345.20 = 0.30 * 10000 = 3000 pips ❌

        Solution : utiliser symbol_info().point pour la normalisation.
        """
        try:
            info = mt5.symbol_info(pair)
            if info is None or info.point == 0:
                return round((tick.ask - tick.bid) * 10000, 1)
            # spread en pips = (ask - bid) / point / 10
            spread_pips = (tick.ask - tick.bid) / info.point / 10
            return round(spread_pips, 1)
        except Exception:
            return round((tick.ask - tick.bid) * 10000, 1)

    # ─────────────────────────────────────────────
    # DÉTECTION PAIRE SILENCIEUSE
    # ─────────────────────────────────────────────

    def _check_silence(self, pair: str):
        """
        Détecte si une paire est silencieuse (aucun tick depuis X sec).
        Marque le statut SILENT et log une alerte.
        """
        with self._lock:
            s = self._stats.get(pair, {})
            last = s.get("last_tick_at")
            if last is None:
                return
            age = (datetime.utcnow() - last).total_seconds()
            if age > SILENT_PAIR_THRESHOLD_SEC:
                if self._status.get(pair) != PairStatus.SILENT:
                    self._status[pair] = PairStatus.SILENT
                    s["silent_alerts"] = s.get("silent_alerts", 0) + 1
                    logger.warning(
                        f"PAIRE SILENCIEUSE : {pair} — "
                        f"aucun tick depuis {age:.0f} sec. "
                        f"Problème réseau partiel ?"
                    )

    # ─────────────────────────────────────────────
    # ACTIVATION SYMBOLE
    # ─────────────────────────────────────────────

    def _ensure_symbol_active(self, pair: str) -> bool:
        """
        Active la paire dans MT5 si elle ne l'est pas.
        Sans ça, symbol_info_tick() retourne None silencieusement.
        """
        info = mt5.symbol_info(pair)
        if info is None:
            logger.error(f"Symbole inconnu sur ce compte : {pair}")
            return False
        if not info.visible:
            if not mt5.symbol_select(pair, True):
                logger.error(f"Impossible d'activer {pair} : {mt5.last_error()}")
                return False
            logger.debug(f"Symbole {pair} activé dans MT5.")
        return True

    # ─────────────────────────────────────────────
    # ACCÈS DONNÉES — utilisés par DataStore / Supervisor
    # ─────────────────────────────────────────────

    def get_latest_tick(self, pair: str) -> dict:
        """Dernier tick reçu pour cette paire."""
        with self._lock:
            ticks = self._ticks.get(pair)
            return dict(ticks[-1]) if ticks else {}

    def get_recent_ticks(self, pair: str, n: int = 10) -> list:
        """N derniers ticks. Utilisé par AnomalyDetector (spike, flash crash)."""
        with self._lock:
            ticks = self._ticks.get(pair, deque())
            return [dict(t) for t in list(ticks)[-n:]]

    def get_current_spread(self, pair: str) -> float:
        """Spread actuel en pips — utilisé pour vérification KS4 en temps réel."""
        return self.get_latest_tick(pair).get("spread", 0.0)

    def get_current_bid(self, pair: str) -> float:
        return self.get_latest_tick(pair).get("bid", 0.0)

    def get_current_ask(self, pair: str) -> float:
        return self.get_latest_tick(pair).get("ask", 0.0)

    def get_pair_status(self, pair: str) -> str:
        """Statut ACTIVE / FROZEN / SILENT / STOPPED / ERROR."""
        with self._lock:
            return self._status.get(pair, PairStatus.STOPPED)

    # ─────────────────────────────────────────────
    # STATISTIQUES SUPERVISOR
    # ─────────────────────────────────────────────

    def get_stats(self, pair: str) -> dict:
        """Stats complètes d'une paire pour le Supervisor."""
        with self._lock:
            return dict(self._stats.get(pair, {}))

    def get_all_stats(self) -> dict:
        """Stats de toutes les paires actives."""
        with self._lock:
            return {pair: dict(s) for pair, s in self._stats.items()}

    def is_pair_silent(self, pair: str) -> bool:
        """True si la paire est en statut SILENT."""
        return self.get_pair_status(pair) == PairStatus.SILENT

    # ─────────────────────────────────────────────
    # PROPRIÉTÉS
    # ─────────────────────────────────────────────

    @property
    def active_pairs(self) -> list:
        """Liste des paires avec thread actif."""
        with self._lock:
            return list(self._threads.keys())

    def __repr__(self):
        return (
            f"TickReceiver("
            f"pairs={self.active_pairs}, "
            f"callbacks={len(self._callbacks)})"
        )
