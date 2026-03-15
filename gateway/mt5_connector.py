"""
gateway/mt5_connector.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sentinel Pro KB5 — Connexion Exness MT5

Responsabilités :
- Login / logout propre (initialize + login séparés)
- Heartbeat toutes les 10 sec
- Reconnexion automatique (MAX_RECONNECT_ATTEMPTS)
- Système d'abonnement multi-callbacks déconnexion
- Infos compte : balance, equity, free_margin
- Heure serveur MT5 (UTC) pour Killzones/Macros
- Statut complet pour Dashboard Patron
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import MetaTrader5 as mt5
import threading
import time
import logging
from datetime import datetime
from config.settings  import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_PATH
from config.constants import Status, Gateway

logger = logging.getLogger(__name__)


class MT5Connector:
    """
    Connexion stable et auto-résiliente à Exness MT5.
    Thread-safe. Heartbeat toutes les 10 sec.
    Multi-callbacks sur déconnexion.
    """

    def __init__(self):
        self._status              = Status.DISCONNECTED
        self._lock                = threading.RLock()
        self._heartbeat_thread    = None
        self._stop_event          = threading.Event()
        self._last_seen           = None
        self._last_connected_at   = None
        self._disconnected_at     = None
        self._reconnect_count     = 0
        self._reconnecting        = False

        # Multi-callbacks — tout module peut s'abonner
        self._disconnect_callbacks = []

    # ══════════════════════════════════════
    # PROPRIÉTÉS
    # ══════════════════════════════════════

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @property
    def is_connected(self) -> bool:
        return self.status == Status.CONNECTED

    # ══════════════════════════════════════
    # ABONNEMENTS CALLBACKS
    # ══════════════════════════════════════

    def subscribe_disconnect(self, callback):
        """
        Abonne un module à l'événement déconnexion.
        Usage :
            connector.subscribe_disconnect(reconnect_manager.handle)
            connector.subscribe_disconnect(order_manager.cancel_all)
            connector.subscribe_disconnect(supervisor.alert_patron)
        """
        if callback not in self._disconnect_callbacks:
            self._disconnect_callbacks.append(callback)
            logger.debug(
                f"Abonné déconnexion : {callback.__self__.__class__.__name__}"
            )

    def _notify_disconnect(self):
        """Notifie tous les abonnés — chacun géré indépendamment."""
        for cb in self._disconnect_callbacks:
            try:
                cb()
            except Exception as e:
                logger.error(
                    f"Callback déconnexion échoué "
                    f"({cb.__self__.__class__.__name__}) : {e}"
                )

    # ══════════════════════════════════════
    # CONNEXION
    # ══════════════════════════════════════

    def connect(self) -> bool:
        """
        Connexion en deux étapes :
        1. initialize() — démarre le terminal MT5
        2. login()      — authentifie sur Exness
        Séparés pour identifier précisément l'origine d'un échec.
        """
        logger.info("Connexion à Exness MT5...")

        # Étape 1 — Terminal
        if not mt5.initialize(path=MT5_PATH):
            logger.error(
                f"mt5.initialize() échoué : {mt5.last_error()}"
            )
            self._set_status(Status.DISCONNECTED)
            return False

        # Étape 2 — Authentification
        if not mt5.login(
            login=MT5_LOGIN,
            password=MT5_PASSWORD,
            server=MT5_SERVER
        ):
            logger.error(
                f"mt5.login() échoué : {mt5.last_error()}"
            )
            mt5.shutdown()
            self._set_status(Status.DISCONNECTED)
            return False

        # Étape 3 — Vérification compte
        account = mt5.account_info()
        if account is None:
            logger.error("Impossible de lire les infos du compte.")
            mt5.shutdown()
            self._set_status(Status.DISCONNECTED)
            return False

        # Succès
        self._set_status(Status.CONNECTED)
        self._last_seen         = datetime.utcnow()
        self._last_connected_at = datetime.utcnow()
        self._reconnecting      = False

        logger.info(
            f"Connecté — "
            f"Compte : {account.login} | "
            f"Solde : {account.balance} {account.currency} | "
            f"Serveur : {account.server} | "
            f"Levier : 1:{account.leverage}"
        )

        self._start_heartbeat()
        return True

    def disconnect(self):
        """Déconnexion propre — arrête heartbeat puis shutdown."""
        self._stop_event.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5)
        mt5.shutdown()
        self._set_status(Status.DISCONNECTED)
        logger.info("Déconnecté de MT5.")

    # ══════════════════════════════════════
    # HEARTBEAT
    # ══════════════════════════════════════

    def _start_heartbeat(self):
        self._stop_event.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="MT5-Heartbeat",
            daemon=True
        )
        self._heartbeat_thread.start()
        logger.debug("Heartbeat démarré.")

    def _heartbeat_loop(self):
        while not self._stop_event.is_set():
            self._stop_event.wait(Gateway.HEARTBEAT_INTERVAL_SEC)
            if self._stop_event.is_set():
                break
            try:
                terminal = mt5.terminal_info()
                if terminal is None or not terminal.connected:
                    logger.warning("Heartbeat — connexion MT5 perdue.")
                    self._set_status(Status.DISCONNECTED)
                    self._disconnected_at = datetime.utcnow()
                    self._notify_disconnect()
                    # Tenter reconnexion automatique
                    if not self._reconnecting:
                        self._reconnect_loop()
                else:
                    self._last_seen = datetime.utcnow()
                    logger.debug(
                        f"Heartbeat OK — "
                        f"{self._last_seen.strftime('%H:%M:%S')} UTC"
                    )
                    if self.status != Status.CONNECTED:
                        self._set_status(Status.CONNECTED)

            except Exception as e:
                logger.error(f"Heartbeat exception : {e}")

    # ══════════════════════════════════════
    # RECONNEXION AUTOMATIQUE
    # ══════════════════════════════════════

    def _reconnect_loop(self):
        """
        Tente de reconnecter automatiquement.
        MAX_RECONNECT_ATTEMPTS tentatives espacées de RECONNECT_WAIT_SEC.
        Si tout échoue → alerte critique + notification callbacks.
        """
        self._reconnecting = True
        self._set_status(Status.RECONNECTING)

        for attempt in range(1, Gateway.MAX_RECONNECT_ATTEMPTS + 1):
            logger.info(
                f"Reconnexion tentative {attempt}/"
                f"{Gateway.MAX_RECONNECT_ATTEMPTS} "
                f"dans {Gateway.RECONNECT_WAIT_SEC} sec..."
            )
            time.sleep(Gateway.RECONNECT_WAIT_SEC)
            mt5.shutdown()

            if self.connect():
                self._reconnect_count += 1
                self._reconnecting = False
                logger.info(
                    f"Reconnexion réussie "
                    f"(tentative {attempt}) — "
                    f"Total reconnexions : {self._reconnect_count}"
                )
                return

        # Toutes tentatives échouées
        self._reconnecting = False
        logger.critical(
            "CRITIQUE — Toutes tentatives de reconnexion échouées. "
            "Intervention manuelle requise."
        )
        # Notifier à nouveau pour déclencher
        # annulation urgence dans ReconnectManager
        self._notify_disconnect()

    # ══════════════════════════════════════
    # INFOS COMPTE
    # ══════════════════════════════════════

    def get_account_info(self) -> dict | None:
        if not self.is_connected:
            return None
        info = mt5.account_info()
        if info is None:
            return None
        return {
            "login":       info.login,
            "balance":     info.balance,
            "equity":      info.equity,
            "margin":      info.margin,
            "free_margin": info.margin_free,
            "currency":    info.currency,
            "server":      info.server,
            "leverage":    info.leverage,
        }

    def get_equity(self) -> float:
        """Équité actuelle — utilisée par Circuit Breaker."""
        info = self.get_account_info()
        return info["equity"] if info else 0.0

    def get_balance(self) -> float:
        """Solde — utilisé par Capital Allocator."""
        info = self.get_account_info()
        return info["balance"] if info else 0.0

    def get_free_margin(self) -> float:
        """Marge libre — vérifiée avant tout nouveau trade."""
        info = self.get_account_info()
        return info["free_margin"] if info else 0.0

    # ══════════════════════════════════════
    # TEMPS SERVEUR
    # ══════════════════════════════════════

    def get_server_time(self) -> datetime | None:
        """
        Heure serveur MT5 en UTC.
        Utilisée pour calculer Killzones et Macros ICT.
        NE PAS utiliser l'heure locale — toujours l'heure serveur.
        """
        if not self.is_connected:
            return None
        tick = mt5.symbol_info_tick("EURUSD")
        if tick:
            return datetime.utcfromtimestamp(tick.time)
        return None

    def get_server_time_est(self) -> datetime | None:
        """
        Heure serveur convertie en EST (UTC-5).
        Utilisée pour les Macros ICT (définies en heures EST).
        """
        utc = self.get_server_time()
        if utc is None:
            return None
        from datetime import timedelta
        return utc - timedelta(hours=5)

    # ══════════════════════════════════════
    # STATUT COMPLET
    # ══════════════════════════════════════

    def get_status(self) -> dict:
        """Dict complet pour Dashboard Patron et Supervisor."""
        return {
            "status":             self.status,
            "is_connected":       self.is_connected,
            "last_seen":          self._last_seen,
            "last_connected_at":  self._last_connected_at,
            "disconnected_at":    self._disconnected_at,
            "reconnect_count":    self._reconnect_count,
            "reconnecting":       self._reconnecting,
            "time_since_last_seen": self.time_since_last_seen(),
        }

    def time_since_last_seen(self) -> float:
        """Secondes depuis le dernier heartbeat OK."""
        if self._last_seen is None:
            return float("inf")
        return (datetime.utcnow() - self._last_seen).total_seconds()

    # ══════════════════════════════════════
    # UTILITAIRES
    # ══════════════════════════════════════

    def _set_status(self, status: str):
        with self._lock:
            if self._status != status:
                old = self._status
                self._status = status
                logger.info(f"Statut connexion : {old} → {status}")

    def __repr__(self):
        return (
            f"MT5Connector("
            f"status={self.status}, "
            f"last_seen={self._last_seen}, "
            f"reconnects={self._reconnect_count}"
            f")"
        )
    def get_symbol_info(self, symbol: str):
        """Retourne symbol_info pour CapitalAllocator."""
        if not self.terminal:
            logger.warning(f"MT5Connector — terminal indisponible pour {symbol}")
            return None
        info = self.terminal.symbol_info(symbol)
        if info is None:
            logger.warning(f"Symbol_info {symbol} indisponible")
        return info
