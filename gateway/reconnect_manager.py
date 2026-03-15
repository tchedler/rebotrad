"""
gateway/reconnect_manager.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sentinel Pro KB5 — Gestionnaire de reconnexion

Responsabilités :
- Abonné aux événements déconnexion de MT5Connector
- Timer annulable : urgence si déconnecté > 2 min
- Freeze TickReceiver pendant déconnexion
- Notification DataStore (KS activé/désactivé)
- Rechargement bougies manquantes après reconnexion
- Historique déconnexions pour Supervisor
- Actions post-reconnexion coordonnées
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import threading
import logging
from datetime import datetime
from config.constants import Gateway

logger = logging.getLogger(__name__)

# KS id utilisé pour signaler déconnexion dans DataStore
KS_DISCONNECT_ID = 99   # KS spécial Gateway — hors des 9 KB5


class ReconnectManager:
    """
    Coordonne toutes les actions liées à une déconnexion MT5.

    Séquence déconnexion :
    1. on_disconnect() appelé par MT5Connector
    2. TickReceiver freezé
    3. DataStore notifié (KS99 actif)
    4. Timer lancé (annulable)
    5. Si > 2 min → emergency_action()
    6. Si reconnexion → on_reconnected()

    Séquence reconnexion :
    1. on_reconnected() appelé par MT5Connector
    2. Timer annulé
    3. TickReceiver redémarré
    4. Bougies manquantes rechargées
    5. DataStore notifié (KS99 désactivé)
    """

    def __init__(
        self,
        connector,
        data_store=None,
        order_manager=None,
        tick_receiver=None,
        candle_fetcher=None,
        active_pairs: list = None,
    ):
        self._connector     = connector
        self._data_store    = data_store
        self._order_manager = order_manager
        self._tick_receiver = tick_receiver
        self._candle_fetcher= candle_fetcher
        self._active_pairs  = active_pairs or []

        # État déconnexion
        self._disconnected_at      = None
        self._emergency_triggered  = False
        self._emergency_timer: threading.Timer | None = None
        self._is_disconnected      = False

        # Historique déconnexions
        self._disconnect_history: list = []
        self._lock = threading.Lock()

        # S'abonner au MT5Connector
        if connector:
            connector.subscribe_disconnect(self.on_disconnect)
            logger.debug("ReconnectManager abonné aux événements MT5Connector.")

    # ══════════════════════════════════════
    # ÉVÉNEMENT DÉCONNEXION
    # ══════════════════════════════════════

    def on_disconnect(self):
        """
        Appelé par MT5Connector dès déconnexion détectée.
        Compatible avec subscribe_disconnect() (sans argument).
        """
        with self._lock:
            if self._is_disconnected:
                return  # Déjà en traitement — éviter double trigger
            self._is_disconnected     = True
            self._disconnected_at     = datetime.utcnow()
            self._emergency_triggered = False

        logger.warning(
            f"DÉCONNEXION MT5 détectée à "
            f"{self._disconnected_at.strftime('%H:%M:%S')} UTC. "
            f"Urgence dans {Gateway.RECONNECT_TIMEOUT_SEC} sec "
            f"si non rétabli."
        )

        # Étape 1 — Notifier DataStore (KS99 actif)
        self._notify_datastore_disconnect()

        # Étape 2 — Freezer TickReceiver
        self._freeze_tick_receiver()

        # Étape 3 — Lancer timer annulable
        self._start_emergency_timer()

    # ══════════════════════════════════════
    # ÉVÉNEMENT RECONNEXION
    # ══════════════════════════════════════

    def on_reconnected(self):
        """
        Appelé par MT5Connector après reconnexion réussie.
        Annule le timer d'urgence et relance les services.
        """
        with self._lock:
            if not self._is_disconnected:
                return  # Pas en déconnexion — ignorer
            disconnected_at = self._disconnected_at
            self._is_disconnected = False

        # Calculer durée de déconnexion
        duration_sec = (
            datetime.utcnow() - disconnected_at
        ).total_seconds() if disconnected_at else 0

        logger.info(
            f"RECONNEXION réussie après "
            f"{duration_sec:.0f} sec."
        )

        # Étape 1 — Annuler timer urgence
        self._cancel_emergency_timer()

        # Étape 2 — Enregistrer dans historique
        self._record_disconnect_event(disconnected_at, duration_sec)

        # Étape 3 — Notifier DataStore (KS99 désactivé)
        self._notify_datastore_reconnect()

        # Étape 4 — Redémarrer TickReceiver
        self._restart_tick_receiver()

        # Étape 5 — Recharger bougies manquantes
        self._reload_missing_candles(since=disconnected_at)

    # ══════════════════════════════════════
    # TIMER D'URGENCE
    # ══════════════════════════════════════

    def _start_emergency_timer(self):
        """Lance un timer annulable pour l'urgence."""
        self._cancel_emergency_timer()  # Annuler ancien si existe
        self._emergency_timer = threading.Timer(
            Gateway.RECONNECT_TIMEOUT_SEC,
            self._check_and_trigger_emergency
        )
        self._emergency_timer.daemon = True
        self._emergency_timer.start()
        logger.debug(
            f"Timer urgence lancé — "
            f"{Gateway.RECONNECT_TIMEOUT_SEC} sec."
        )

    def _cancel_emergency_timer(self):
        """Annule le timer si encore en cours."""
        if self._emergency_timer is not None:
            self._emergency_timer.cancel()
            self._emergency_timer = None
            logger.debug("Timer urgence annulé.")

    def _check_and_trigger_emergency(self):
        """
        Appelé par le timer après RECONNECT_TIMEOUT_SEC.
        Vérifie si toujours déconnecté avant de déclencher.
        """
        if self._connector and self._connector.is_connected:
            logger.info(
                "Timer urgence expiré mais connexion rétablie — "
                "annulation urgence."
            )
            return

        duration_sec = 0
        if self._disconnected_at:
            duration_sec = (
                datetime.utcnow() - self._disconnected_at
            ).total_seconds()

        logger.error(
            f"URGENCE — Toujours déconnecté après "
            f"{duration_sec:.0f} sec. "
            f"Déclenchement annulation ordres."
        )
        self._trigger_emergency(duration_sec)

    # ══════════════════════════════════════
    # ACTION D'URGENCE
    # ══════════════════════════════════════

    def _trigger_emergency(self, duration_sec: float = 0):
        """
        Déclenche l'annulation urgence.
        Idempotent — ne se déclenche qu'une fois par déconnexion.
        """
        with self._lock:
            if self._emergency_triggered:
                return
            self._emergency_triggered = True

        logger.critical(
            f"URGENCE DÉCLENCHÉE — "
            f"Durée déconnexion : {duration_sec:.0f} sec | "
            f"Timestamp : {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

        if self._order_manager:
            try:
                self._order_manager.cancel_all_orders(
                    reason="GATEWAY_DISCONNECT"
                )
                logger.info(
                    "Urgence — Tous les ordres annulés via OrderManager."
                )
            except Exception as e:
                logger.critical(
                    f"Urgence — Échec annulation ordres : {e}. "
                    f"INTERVENTION MANUELLE REQUISE."
                )
        else:
            logger.critical(
                "URGENCE — OrderManager non disponible. "
                "INTERVENTION MANUELLE IMMÉDIATE REQUISE. "
                "Connectez-vous à Exness et fermez les positions manuellement."
            )

    # ══════════════════════════════════════
    # ACTIONS TICK RECEIVER
    # ══════════════════════════════════════

    def _freeze_tick_receiver(self):
        """
        Arrête tous les threads tick pendant déconnexion.
        Évite spam de None et CPU gaspillé.
        """
        if self._tick_receiver:
            try:
                self._tick_receiver.stop_all()
                logger.info(
                    "TickReceiver freezé pendant déconnexion."
                )
            except Exception as e:
                logger.warning(f"Freeze TickReceiver échoué : {e}")

    def _restart_tick_receiver(self):
        """Redémarre les ticks sur toutes les paires actives."""
        if self._tick_receiver and self._active_pairs:
            try:
                for pair in self._active_pairs:
                    self._tick_receiver.start_pair(pair)
                logger.info(
                    f"TickReceiver redémarré pour : "
                    f"{self._active_pairs}"
                )
            except Exception as e:
                logger.error(f"Redémarrage TickReceiver échoué : {e}")

    # ══════════════════════════════════════
    # RECHARGEMENT BOUGIES MANQUANTES
    # ══════════════════════════════════════

    def _reload_missing_candles(self, since: datetime):
        """
        Recharge uniquement les bougies manquantes
        depuis le timestamp de déconnexion.
        Utilise fetch_since() du CandleFetcher.
        """
        if not self._candle_fetcher or not self._data_store:
            return
        if not self._active_pairs:
            return

        logger.info(
            f"Rechargement bougies manquantes depuis "
            f"{since.strftime('%H:%M:%S')} UTC..."
        )

        from config.constants import TIMEFRAMES
        for pair in self._active_pairs:
            for tf_name in TIMEFRAMES.keys():
                try:
                    df = self._candle_fetcher.fetch_since(
                        pair=pair,
                        timeframe=tf_name,
                        since=since,
                    )
                    if df is not None and not df.empty:
                        self._data_store.set_candles(pair, tf_name, df)
                        logger.debug(
                            f"Bougies rechargées — "
                            f"{pair} {tf_name} : "
                            f"{len(df)} nouvelles bougies"
                        )
                except Exception as e:
                    logger.warning(
                        f"Rechargement {pair} {tf_name} échoué : {e}"
                    )

    # ══════════════════════════════════════
    # NOTIFICATIONS DATASTORE
    # ══════════════════════════════════════

    def _notify_datastore_disconnect(self):
        """Marque KS99 actif dans DataStore."""
        if self._data_store:
            try:
                self._data_store.set_ks_state(
                    ks_id  = KS_DISCONNECT_ID,
                    active = True,
                    reason = "GATEWAY_DISCONNECT"
                )
            except Exception as e:
                logger.warning(f"DataStore notify disconnect échoué : {e}")

    def _notify_datastore_reconnect(self):
        """Désactive KS99 dans DataStore."""
        if self._data_store:
            try:
                self._data_store.set_ks_state(
                    ks_id  = KS_DISCONNECT_ID,
                    active = False,
                    reason = ""
                )
            except Exception as e:
                logger.warning(f"DataStore notify reconnect échoué : {e}")

    # ══════════════════════════════════════
    # HISTORIQUE DÉCONNEXIONS
    # ══════════════════════════════════════

    def _record_disconnect_event(
        self,
        disconnected_at: datetime,
        duration_sec: float
    ):
        """Enregistre l'événement dans l'historique."""
        with self._lock:
            self._disconnect_history.append({
                "disconnected_at":  disconnected_at,
                "reconnected_at":   datetime.utcnow(),
                "duration_sec":     round(duration_sec, 1),
                "emergency":        self._emergency_triggered,
            })
            # Garder max 50 événements
            if len(self._disconnect_history) > 50:
                self._disconnect_history = self._disconnect_history[-50:]

    def get_disconnect_history(self) -> list:
        """Historique complet — pour Supervisor et Dashboard."""
        with self._lock:
            return list(self._disconnect_history)

    def get_disconnect_stats(self) -> dict:
        """
        Statistiques déconnexions pour Dashboard Patron.
        Durée max, moyenne, nombre d'urgences déclenchées.
        """
        with self._lock:
            history = self._disconnect_history
            if not history:
                return {
                    "total_disconnects":   0,
                    "total_emergencies":   0,
                    "avg_duration_sec":    0,
                    "max_duration_sec":    0,
                    "is_disconnected":     self._is_disconnected,
                }
            durations  = [e["duration_sec"] for e in history]
            emergencies= sum(1 for e in history if e["emergency"])
            return {
                "total_disconnects":   len(history),
                "total_emergencies":   emergencies,
                "avg_duration_sec":    round(
                    sum(durations) / len(durations), 1
                ),
                "max_duration_sec":    max(durations),
                "last_disconnect":     history[-1]["disconnected_at"],
                "is_disconnected":     self._is_disconnected,
            }

    # ══════════════════════════════════════
    # ÉTAT + UTILITAIRES
    # ══════════════════════════════════════

    @property
    def is_disconnected(self) -> bool:
        return self._is_disconnected

    def current_disconnect_duration(self) -> float:
        """Secondes depuis la déconnexion en cours."""
        if not self._is_disconnected or self._disconnected_at is None:
            return 0.0
        return (
            datetime.utcnow() - self._disconnected_at
        ).total_seconds()

    def set_active_pairs(self, pairs: list):
        """Met à jour la liste des paires actives."""
        self._active_pairs = pairs

    def __repr__(self):
        stats = self.get_disconnect_stats()
        return (
            f"ReconnectManager("
            f"disconnected={self._is_disconnected}, "
            f"total_events={stats['total_disconnects']}, "
            f"emergencies={stats['total_emergencies']}"
            f")"
        )
