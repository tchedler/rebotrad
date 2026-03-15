# supervisor/heartbeat_monitor.py
# Sentinel Pro KB5 — Superviseur Système
#
# Responsabilités :
# - Surveille tous les composants du bot (Gateway, DataStore,
#   TickReceiver, CandleFetcher, BackupManager, PriorityQueue)
# - Alerte si un composant est mort ou silencieux
# - Vérifie la fraîcheur des ticks et bougies par paire
# - Vérifie l'état KillSwitches et Circuit Breaker
# - Notifie le Patron (log critique + callback alerte)
# - Rapport de santé complet pour Dashboard
# - Thread dédié non-bloquant

import threading
import logging
from datetime import datetime, timezone
from config.constants import Gateway

logger = logging.getLogger(__name__)

# Seuils de surveillance (secondes)
TICK_STALE_SEC    = 10    # tick trop vieux → alerte
CANDLE_STALE_SEC  = 300   # bougie trop vieille → alerte (5 min)
BACKUP_STALE_SEC  = 360   # backup trop vieux → alerte (6 min)
CHECK_INTERVAL    = 10    # fréquence de vérification (10 sec)

# Statuts composants
class ComponentStatus:
    OK       = "✅ OK"
    WARNING  = "⚠️  WARNING"
    CRITICAL = "🔴 CRITICAL"
    UNKNOWN  = "❓ UNKNOWN"


class HeartbeatMonitor:
    """
    Superviseur central de Sentinel Pro.

    Vérifie toutes les 10 secondes :
    1. Gateway MT5Connector     — connexion active ?
    2. TickReceiver             — ticks frais par paire ?
    3. DataStore                — fraîcheur bougies par paire ?
    4. BackupManager            — backup récent ?
    5. KillSwitches             — aucun KS actif non prévu ?
    6. Circuit Breaker          — niveau CB ?
    7. PriorityQueue            — file cohérente avec les paires actives ?

    Sur anomalie :
    - Log WARNING ou CRITICAL selon gravité
    - Appel callback patron_alert (Telegram, email, etc.)
    - Rapport stocké dans self._last_report
    """

    def __init__(
        self,
        connector,
        datastore,
        tick_receiver,
        backup_manager   = None,
        priority_queue   = None,
        active_pairs     : list = None,
        patron_alert_cb  = None,
    ):
        self.connector      = connector
        self.datastore      = datastore
        self.tick_receiver  = tick_receiver
        self.backup_manager = backup_manager
        self.priority_queue = priority_queue
        self.active_pairs   = active_pairs or []
        self.patron_alert   = patron_alert_cb   # callback alerte Patron

        self._stop_event    = threading.Event()
        self._thread        = None
        self._lock          = threading.RLock()

        # Rapport de santé
        self._last_report   = {}
        self._check_count   = 0
        self._alert_count   = 0
        self._last_check_at = None

        logger.info("HeartbeatMonitor initialisé.")

    # ─────────────────────────────────────────────
    # DÉMARRAGE / ARRÊT
    # ─────────────────────────────────────────────

    def start(self):
        """Lance le thread de surveillance."""
        if self._thread and self._thread.is_alive():
            logger.warning("HeartbeatMonitor déjà actif.")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="HeartbeatMonitor"
        )
        self._thread.start()
        logger.info(
            f"HeartbeatMonitor démarré — "
            f"vérification toutes les {CHECK_INTERVAL}s."
        )

    def stop(self):
        """Arrête le thread proprement."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("HeartbeatMonitor arrêté.")

    # ─────────────────────────────────────────────
    # BOUCLE PRINCIPALE
    # ─────────────────────────────────────────────

    def _monitor_loop(self):
        """Boucle de surveillance — vérifie toutes les CHECK_INTERVAL sec."""
        logger.debug("HeartbeatMonitor — boucle démarrée.")
        while not self._stop_event.is_set():
            self._stop_event.wait(CHECK_INTERVAL)
            if self._stop_event.is_set():
                break
            try:
                self._run_checks()
            except Exception as e:
                logger.error(f"HeartbeatMonitor — erreur inattendue : {e}")

    # ─────────────────────────────────────────────
    # VÉRIFICATIONS PRINCIPALES
    # ─────────────────────────────────────────────

    def _run_checks(self):
        """Exécute tous les checks et produit le rapport de santé."""
        report = {
            "checked_at":  datetime.utcnow(),
            "components":  {},
            "pairs":       {},
            "alerts":      [],
            "overall":     ComponentStatus.OK,
        }

        # 1. Gateway
        report["components"]["gateway"] = self._check_gateway()

        # 2. TickReceiver — par paire
        report["components"]["tick_receiver"] = self._check_tick_receiver()
        for pair in self.active_pairs:
            report["pairs"][pair] = self._check_pair(pair)

        # 3. DataStore
        report["components"]["datastore"] = self._check_datastore()

        # 4. BackupManager
        report["components"]["backup_manager"] = self._check_backup()

        # 5. KillSwitches
        report["components"]["killswitches"] = self._check_killswitches()

        # 6. Circuit Breaker
        report["components"]["circuit_breaker"] = self._check_circuit_breaker()

        # 7. PriorityQueue
        report["components"]["priority_queue"] = self._check_priority_queue()

        # Calcul statut global
        all_statuses = [
            c["status"]
            for c in report["components"].values()
        ] + [
            p["status"]
            for p in report["pairs"].values()
        ]

        if ComponentStatus.CRITICAL in all_statuses:
            report["overall"] = ComponentStatus.CRITICAL
        elif ComponentStatus.WARNING in all_statuses:
            report["overall"] = ComponentStatus.WARNING
        else:
            report["overall"] = ComponentStatus.OK

        # Collecter les alertes
        for name, comp in report["components"].items():
            if comp["status"] != ComponentStatus.OK:
                report["alerts"].append(
                    f"{comp['status']} [{name}] : {comp.get('detail', '')}"
                )
        for pair, pdata in report["pairs"].items():
            if pdata["status"] != ComponentStatus.OK:
                report["alerts"].append(
                    f"{pdata['status']} [pair:{pair}] : {pdata.get('detail', '')}"
                )

        # Logger et notifier si alertes
        if report["alerts"]:
            for alert in report["alerts"]:
                if ComponentStatus.CRITICAL in alert:
                    logger.critical(alert)
                else:
                    logger.warning(alert)
            self._alert_count += len(report["alerts"])
            self._notify_patron(report)

        # Stocker le rapport
        with self._lock:
            self._last_report   = report
            self._check_count  += 1
            self._last_check_at = datetime.utcnow()

    # ─────────────────────────────────────────────
    # CHECKS INDIVIDUELS
    # ─────────────────────────────────────────────

    def _check_gateway(self) -> dict:
        """Vérifie que MT5Connector est connecté."""
        try:
            if not self.connector.is_connected:
                return {
                    "status": ComponentStatus.CRITICAL,
                    "detail": "MT5Connector déconnecté.",
                }
            status = self.connector.get_status()
            age    = status.get("time_since_last_seen", 0)
            if age > Gateway.HEARTBEAT_INTERVAL_SEC * 3:
                return {
                    "status": ComponentStatus.WARNING,
                    "detail": f"Dernier heartbeat il y a {age:.0f}s.",
                }
            return {"status": ComponentStatus.OK, "detail": f"Connecté. Age={age:.0f}s"}
        except Exception as e:
            return {"status": ComponentStatus.CRITICAL, "detail": str(e)}

    def _check_tick_receiver(self) -> dict:
        """Vérifie que TickReceiver tourne pour toutes les paires actives."""
        try:
            active = self.tick_receiver.active_pairs
            missing = [p for p in self.active_pairs if p not in active]
            if missing:
                return {
                    "status": ComponentStatus.CRITICAL,
                    "detail": f"Paires sans tick receiver : {missing}",
                }
            return {
                "status": ComponentStatus.OK,
                "detail": f"{len(active)} paires actives.",
            }
        except Exception as e:
            return {"status": ComponentStatus.CRITICAL, "detail": str(e)}

    def _check_pair(self, pair: str) -> dict:
        """
        Vérifie la fraîcheur des ticks et bougies pour une paire.
        Détecte paire silencieuse, spread KS4, bougies périmées.
        """
        issues = []
        status = ComponentStatus.OK

        try:
            # Tick freshness
            stats = self.tick_receiver.get_stats(pair)
            last  = stats.get("last_tick_at")
            if last is None:
                issues.append("Aucun tick reçu.")
                status = ComponentStatus.WARNING
            else:
                age = (datetime.utcnow() - last).total_seconds()
                if age > TICK_STALE_SEC:
                    issues.append(f"Tick trop vieux : {age:.0f}s.")
                    status = ComponentStatus.WARNING

            # Spread KS4
            spread = stats.get("last_spread", 0.0)
            if spread > 3.0:
                issues.append(f"Spread KS4 actif : {spread} pips.")
                status = ComponentStatus.WARNING

            # Paire silencieuse
            if self.tick_receiver.is_pair_silent(pair):
                issues.append("Paire SILENCIEUSE.")
                status = ComponentStatus.CRITICAL

            # Bougies DataStore
            if not self.datastore.has_candles(pair, "H1"):
                issues.append("Bougies H1 absentes.")
                status = ComponentStatus.WARNING

        except Exception as e:
            issues.append(str(e))
            status = ComponentStatus.CRITICAL

        return {
            "status": status,
            "detail": " | ".join(issues) if issues else "OK",
        }

    def _check_datastore(self) -> dict:
        """Vérifie que le DataStore est opérationnel."""
        try:
            stats = self.datastore.get_stats()
            pairs = stats.get("pairs_count", 0)
            if pairs == 0:
                return {
                    "status": ComponentStatus.WARNING,
                    "detail": "DataStore vide — aucune paire chargée.",
                }
            return {
                "status": ComponentStatus.OK,
                "detail": f"{pairs} paires en mémoire.",
            }
        except Exception as e:
            return {"status": ComponentStatus.CRITICAL, "detail": str(e)}

    def _check_backup(self) -> dict:
        """Vérifie que le BackupManager tourne et que le dernier backup est récent."""
        if self.backup_manager is None:
            return {"status": ComponentStatus.WARNING, "detail": "BackupManager non configuré."}
        try:
            stats   = self.backup_manager.get_stats()
            running = stats.get("is_running", False)
            last_at = stats.get("last_backup_at")

            if not running:
                return {
                    "status": ComponentStatus.CRITICAL,
                    "detail": "BackupManager thread arrêté.",
                }
            if last_at is None:
                return {
                    "status": ComponentStatus.WARNING,
                    "detail": "Aucun backup effectué depuis le démarrage.",
                }
            age = (datetime.utcnow() - last_at).total_seconds()
            if age > BACKUP_STALE_SEC:
                return {
                    "status": ComponentStatus.WARNING,
                    "detail": f"Dernier backup il y a {age:.0f}s (seuil {BACKUP_STALE_SEC}s).",
                }
            return {
                "status": ComponentStatus.OK,
                "detail": f"Backup OK. Dernier il y a {age:.0f}s.",
            }
        except Exception as e:
            return {"status": ComponentStatus.CRITICAL, "detail": str(e)}

    def _check_killswitches(self) -> dict:
        """Vérifie l'état des 9 KillSwitches KB5."""
        try:
            active_ks = self.datastore.get_active_ks_list()
            if not active_ks:
                return {"status": ComponentStatus.OK, "detail": "Aucun KS actif."}

            # KS1/KS2 = bloquants absolus → CRITICAL
            critical_ks = [k for k in active_ks if k in [1, 2, 3, 5, 6, 7]]
            warning_ks  = [k for k in active_ks if k in [4, 8, 9]]

            if critical_ks:
                return {
                    "status": ComponentStatus.CRITICAL,
                    "detail": f"KillSwitches BLOQUANTS actifs : KS{critical_ks}",
                }
            return {
                "status": ComponentStatus.WARNING,
                "detail": f"KillSwitches FILTRANTS actifs : KS{warning_ks}",
            }
        except Exception as e:
            return {"status": ComponentStatus.CRITICAL, "detail": str(e)}

    def _check_circuit_breaker(self) -> dict:
        """Vérifie le niveau du Circuit Breaker."""
        try:
            level = self.datastore.get_cb_level()
            if level == 0:
                return {"status": ComponentStatus.OK, "detail": "CB niveau 0 — Clear."}
            elif level == 1:
                return {
                    "status": ComponentStatus.WARNING,
                    "detail": f"CB niveau 1 — ALERTE drawdown.",
                }
            elif level == 2:
                return {
                    "status": ComponentStatus.CRITICAL,
                    "detail": "CB niveau 2 — PAUSE trading.",
                }
            else:
                return {
                    "status": ComponentStatus.CRITICAL,
                    "detail": "CB niveau 3 — STOP trading.",
                }
        except Exception as e:
            return {"status": ComponentStatus.CRITICAL, "detail": str(e)}

    def _check_priority_queue(self) -> dict:
        """Vérifie que la PriorityQueue est cohérente avec les paires actives."""
        if self.priority_queue is None:
            return {"status": ComponentStatus.WARNING, "detail": "PriorityQueue non configurée."}
        try:
            stats = self.priority_queue.get_stats()
            size  = stats.get("queue_size", 0)
            if size == 0 and self.active_pairs:
                return {
                    "status": ComponentStatus.WARNING,
                    "detail": "File priorité vide alors que des paires sont actives.",
                }
            kz = stats.get("current_killzone", "AUCUNE")
            return {
                "status": ComponentStatus.OK,
                "detail": f"KZ={kz} | {size} paires en file.",
            }
        except Exception as e:
            return {"status": ComponentStatus.CRITICAL, "detail": str(e)}

    # ─────────────────────────────────────────────
    # NOTIFICATION PATRON
    # ─────────────────────────────────────────────

    def _notify_patron(self, report: dict):
        """
        Notifie le Patron en cas d'alerte.
        Appelle le callback patron_alert si défini.
        (Telegram, email, SMS, etc.)
        """
        if self.patron_alert:
            try:
                self.patron_alert(report)
            except Exception as e:
                logger.error(f"Notification Patron échouée : {e}")

    # ─────────────────────────────────────────────
    # RAPPORT SANTÉ
    # ─────────────────────────────────────────────

    def get_health_report(self) -> dict:
        """
        Retourne le dernier rapport de santé complet.
        Appelé par le Dashboard Patron en temps réel.
        """
        with self._lock:
            return dict(self._last_report)

    def get_stats(self) -> dict:
        """Stats du HeartbeatMonitor pour le Dashboard."""
        with self._lock:
            return {
                "check_count":    self._check_count,
                "alert_count":    self._alert_count,
                "last_check_at":  self._last_check_at,
                "check_interval": CHECK_INTERVAL,
                "active_pairs":   self.active_pairs,
                "is_running":     self._thread.is_alive() if self._thread else False,
                "overall_status": self._last_report.get("overall", ComponentStatus.UNKNOWN),
            }

    def force_check(self) -> dict:
        """
        Force une vérification immédiate hors cycle.
        Retourne le rapport complet.
        Utilisé par main.py au démarrage.
        """
        self._run_checks()
        return self.get_health_report()

    def __repr__(self):
        status = self._last_report.get("overall", ComponentStatus.UNKNOWN)
        return (
            f"HeartbeatMonitor("
            f"status={status} | "
            f"checks={self._check_count} | "
            f"alerts={self._alert_count})"
        )
