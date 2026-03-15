# supervisor/supervisor.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Supervisor (Orchestrateur Global)
══════════════════════════════════════════════════════════════
Responsabilités :
  - Démarrer tous les modules dans l'ordre correct
  - Orchestrer la boucle principale d'analyse/exécution
  - Planifier les tâches périodiques multi-fréquences
  - Gérer l'arrêt propre sur SIGTERM/SIGINT
  - Injecter les callbacks inter-modules (CB3 → close_all)
  - Charger le calendrier news en début de session
  - Surveiller la santé des modules (health check)
  - Logger les statistiques globales périodiquement

Boucle principale (CYCLE_INTERVAL_SEC) :
  Pour chaque paire active :
    1. scoring_engine.evaluate(pair)
    2. Si EXECUTE → capital_allocator.compute()
                 → behaviour_shield.validate()
                 → order_manager.send_order()
    3. Si WATCH   → log + notification Dashboard
    4. circuit_breaker.evaluate()
    5. killswitch_engine.evaluate(pair)
    6. trail_sl sur positions ouvertes

Tâches périodiques :
  CYCLE      ( 30s) → analyse + exécution
  TRAIL      ( 60s) → trailing SL toutes positions
  CB_EVAL    ( 10s) → évaluation circuit breaker
  CLEANUP    (300s) → purge news passées + caches
  HEALTH     ( 60s) → health check modules
  STATS      (600s) → log statistiques globales
  DAY_INIT   ( 1x ) → initialisation journalière equity

Dépendances :
  Tous les modules Phase 1, 2 et 3 — point d'entrée unique.

Consommé par :
  - main.py → supervisor.start()
  - patron_dashboard.py → supervisor.get_global_status()
══════════════════════════════════════════════════════════════
"""

import logging
import signal
import threading
import time
from datetime import datetime, timezone, date
from typing import Optional

import MetaTrader5 as mt5

from config.constants import Trading, Gateway, Risk, CB, KS, Score
from execution.news_manager import NewsManager

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# CONSTANTES SUPERVISOR
# ══════════════════════════════════════════════════════════════

CYCLE_INTERVAL_SEC  = 30    # analyse + exécution
TRAIL_INTERVAL_SEC  = 60    # trailing SL
CB_EVAL_INTERVAL    = 10    # circuit breaker
CLEANUP_INTERVAL    = 300   # purge caches
HEALTH_INTERVAL     = 60    # health check
STATS_INTERVAL      = 600   # log stats

STARTUP_DELAY_SEC   = 3     # délai entre init modules

# Paires actives par défaut (overridées par config)
DEFAULT_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY",
    "XAUUSD", "US30", "NAS100",
]

# Sessions ICT (UTC)
SESSIONS = {
    "TOKYO":  {"open": (0,  0), "close": (9,  0)},
    "LONDON": {"open": (7,  0), "close": (16, 0)},
    "NY":     {"open": (13, 0), "close": (22, 0)},
}

# ══════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════

class Supervisor:
    """
    Orchestrateur central de SENTINEL PRO KB5.
    Lance et coordonne tous les modules du bot.
    Point d'entrée unique appelé par main.py.

    Architecture threading :
      - Thread principal   : boucle analyse + exécution
      - Thread CB_EVAL     : circuit breaker à haute fréquence
      - Thread TRAIL       : trailing SL
      - Thread CLEANUP     : purge périodique
      - Thread HEALTH      : health check modules
      - Thread STATS       : statistiques périodiques
    """

    def __init__(self,
                 # Phase 1
                 data_store,
                 mt5_connector,
                 tick_receiver,
                 candle_fetcher,
                 order_reader,
                 reconnect_manager,
                 # Phase 2
                 fvg_detector,
                 ob_detector,
                 smt_detector,
                 bias_detector,
                 kb5_engine,
                 killswitch_engine,
                 circuit_breaker,
                 scoring_engine,
                 # Phase 3
                 capital_allocator,
                 behaviour_shield,
                 order_manager,
                 # Config
                 active_pairs: list = None):

        # ── Modules Phase 1 ─────────────────────────────────
        self._ds        = data_store
        self._connector = mt5_connector
        self._ticks     = tick_receiver
        self._candles   = candle_fetcher
        self._reader    = order_reader
        self._reconnect = reconnect_manager

        # ── Modules Phase 2 ─────────────────────────────────
        self._fvg     = fvg_detector
        self._ob      = ob_detector
        self._smt     = smt_detector
        self._bias    = bias_detector
        self._kb5     = kb5_engine
        self._ks      = killswitch_engine
        self._cb      = circuit_breaker
        self._scoring = scoring_engine

        # ── Modules Phase 3 ─────────────────────────────────
        self._allocator = capital_allocator
        self._shield    = behaviour_shield
        self._orders    = order_manager

        # ── News Manager (Point 1.12 Audit) ──────────────────
        # Injecter le callback de mise à jour vers le KillSwitchEngine
        self._news = NewsManager(
            on_update_callback=self._ks.update_news_calendar
        )

        # ── Configuration ────────────────────────────────────
        self._pairs = active_pairs or DEFAULT_PAIRS
        self._lock  = threading.Lock()

        # ── État interne ─────────────────────────────────────
        self._running          = False
        self._paused           = False
        self._shutdown_event   = threading.Event()
        self._current_day: Optional[date] = None
        self._session_log: list[dict]  = []

        # ── Statistiques cycle ────────────────────────────────
        self._cycle_count      = 0
        self._execute_count    = 0
        self._watch_count      = 0
        self._no_trade_count   = 0
        self._error_count      = 0

        # ── Threads ──────────────────────────────────────────
        self._threads: dict[str, threading.Thread] = {}

        # ── Timers dernier run ────────────────────────────────
        self._last_run: dict[str, float] = {
            "cycle":   0.0,
            "trail":   0.0,
            "cb_eval": 0.0,
            "cleanup": 0.0,
            "health":  0.0,
            "stats":   0.0,
        }

        logger.info(
            f"Supervisor initialisé | "
            f"Paires : {self._pairs} | "
            f"Cycle : {CYCLE_INTERVAL_SEC}s"
        )

    # ══════════════════════════════════════════════════════════
    # DÉMARRAGE
    # ══════════════════════════════════════════════════════════

    def start(self) -> bool:
        """
        Démarre le bot complet.
        Appelé par main.py — bloque jusqu'à l'arrêt.

        Pipeline de démarrage :
          1. Configurer les handlers de signal
          2. Injecter les callbacks inter-modules
          3. Initialisation journalière
          4. Lancer les threads périodiques
          5. Entrer dans la boucle principale

        Returns:
            True si arrêt propre, False si erreur fatale
        """
        logger.info("═" * 60)
        logger.info("SENTINEL PRO KB5 — DÉMARRAGE")
        logger.info("═" * 60)

        try:
            # ── Signaux OS ───────────────────────────────────
            signal.signal(signal.SIGTERM, self._on_signal)
            signal.signal(signal.SIGINT,  self._on_signal)

            # ── Callbacks inter-modules ──────────────────────
            self._inject_callbacks()

            # ── Initialisation journalière ───────────────────
            ok = self._daily_init()
            if not ok:
                logger.error(
                    "Supervisor — Initialisation journalière échouée"
                )
                return False

            # ── Threads périodiques ──────────────────────────
            self._start_background_threads()

            # ── Boucle principale ────────────────────────────
            self._running = True
            logger.info("Supervisor — Boucle principale démarrée")

            self._main_loop()

            return True

        except Exception as e:
            logger.critical(
                f"Supervisor — Erreur fatale démarrage : {e}",
                exc_info=True
            )
            return False

        finally:
            self._cleanup_on_exit()

    # ══════════════════════════════════════════════════════════
    # CALLBACKS INTER-MODULES
    # ══════════════════════════════════════════════════════════

    def _inject_callbacks(self) -> None:
        """
        Injecte les callbacks entre modules.
        Évite les dépendances circulaires en passant
        les fonctions au moment du démarrage.
        """
        # CB3 → fermer toutes les positions
        self._cb.register_halt_callback(
            lambda: self._orders.close_all_positions(
                reason="CB3 HALT — fermeture forcée"
            )
        )

        # CB3 → annuler tous les ordres pending
        self._cb.register_halt_callback(
            lambda: self._orders.cancel_all_pending(
                reason="CB3 HALT — annulation pending"
            )
        )

        # Reconnect manager → KS99 clear après reconnexion
        if hasattr(self._reconnect, "register_reconnect_callback"):
            self._reconnect.register_reconnect_callback(
                lambda: self._ks.clear_ks(99)
            )

        logger.info(
            "Supervisor — Callbacks inter-modules injectés"
        )

    # ══════════════════════════════════════════════════════════
    # INITIALISATION JOURNALIÈRE
    # ══════════════════════════════════════════════════════════

    def _daily_init(self) -> bool:
        """
        Initialisation exécutée une fois par jour.
        Lance aussi la première fois au démarrage.

        Tâches :
          1. Initialiser equity de référence CB
          2. Vider l'historique BehaviourShield
          3. Invalider caches CapitalAllocator
          4. Charger le calendrier news du jour
          5. Loguer la session active

        Returns:
            True si initialisation réussie
        """
        today = date.today()
        with self._lock:
            if self._current_day == today:
                return True  # déjà initialisé aujourd'hui
            self._current_day = today

        logger.info(
            f"Supervisor — Initialisation journalière | "
            f"Date : {today}"
        )

        # Equity Circuit Breaker
        cb_ok = self._cb.initialize_day()
        if not cb_ok:
            logger.warning(
                "Supervisor — CB equity init échoué — "
                "CB démarrera sans référence journalière"
            )

        # Reset BehaviourShield
        self._shield.clear_history()

        # Invalider cache symboles
        self._allocator.invalidate_symbol_cache()

        # Reset ScoringEngine cache
        self._scoring.clear_cache()

        # Charger calendrier news
        self._load_news_calendar()

        # Loguer session active
        session = self._get_active_session()
        logger.info(
            f"Supervisor — Session active : {session} | "
            f"Paires : {self._pairs}"
        )

        return True

    def _load_news_calendar(self) -> None:
        """
        Charge le calendrier news depuis ForexFactory CSV.
        Fallback : liste vide avec warning — KS3/KS7 désactivés.
        """
        try:
            import csv, urllib.request
            from datetime import date

            url = (
                "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            )
            with urllib.request.urlopen(url, timeout=5) as r:
                import json
                raw = json.loads(r.read().decode())

            today_str = date.today().strftime("%Y-%m-%d")
            high_impact = [
                e for e in raw
                if e.get("impact") == "High"
                and today_str in e.get("date", "")
            ]

            self._ks.set_news_calendar(high_impact)

            logger.info(
                f"Calendrier news chargé — "
                f"{len(high_impact)} événements haute impact aujourd'hui"
            )

        except Exception as e:
            logger.warning(
                f"Calendrier news indisponible : {e} | "
                f"⚠️ KS3/KS7 DÉSACTIVÉS — trades non protégés news"
            )
            self._ks.set_news_calendar([])


    # ══════════════════════════════════════════════════════════
    # BOUCLE PRINCIPALE
    # ══════════════════════════════════════════════════════════

    def _main_loop(self) -> None:
        """
        Boucle principale du bot.
        Tourne jusqu'au signal d'arrêt.
        """
        while not self._shutdown_event.is_set():
            try:
                now = time.time()

                # ── Reset journalier ─────────────────────────
                self._check_daily_reset()

                # ── Pause ? ──────────────────────────────────
                if self._paused:
                    time.sleep(1)
                    continue

                # ── Cycle analyse + exécution ─────────────────
                if now - self._last_run["cycle"] >= CYCLE_INTERVAL_SEC:
                    self._run_analysis_cycle()
                    self._last_run["cycle"] = now

                # Petit sleep pour éviter le busy-wait
                time.sleep(0.5)

            except Exception as e:
                self._error_count += 1
                logger.error(
                    f"Supervisor — Erreur boucle principale : {e}",
                    exc_info=True
                )
                time.sleep(CYCLE_INTERVAL_SEC)

    # ══════════════════════════════════════════════════════════
    # CYCLE ANALYSE + EXÉCUTION
    # ══════════════════════════════════════════════════════════

    def _run_analysis_cycle(self) -> None:
        """
        Un cycle complet sur toutes les paires actives.
        Cœur du bot : analyse → verdict → exécution.
        """
        now = datetime.now(timezone.utc)
        self._cycle_count += 1

        logger.debug(
            f"Supervisor — Cycle #{self._cycle_count} | "
            f"{now.strftime('%H:%M:%S')} UTC"
        )

        for pair in self._pairs:
            try:
                self._process_pair(pair)
            except Exception as e:
                self._error_count += 1
                logger.error(
                    f"Supervisor — Erreur paire {pair} : {e}",
                    exc_info=True
                )

    def _process_pair(self, pair: str) -> None:
        """
        Pipeline complet pour une paire.

          1. Évaluer KS (pré-check rapide)
          2. Évaluer scoring (analyse complète)
          3. Si EXECUTE → allocate → shield → order
          4. Si WATCH   → log + dashboard
        """
        # ── Pré-check KS rapide ──────────────────────────────
        ks_result = self._ks.evaluate(pair)
        if ks_result["verdict"] == "BLOCKED":
            logger.debug(
                f"Supervisor — {pair} | KS BLOCKED : "
                f"{ks_result['blocked_by']}"
            )
            return

        # ── Scoring complet ──────────────────────────────────
        scalp_output = self._scoring.evaluate(pair)
        verdict      = scalp_output.get("verdict", "NO_TRADE")

        # ── Traitement verdict ───────────────────────────────
        if verdict == "EXECUTE":
            self._execute_trade(pair, scalp_output)

        elif verdict == "WATCH":
            self._watch_alert(pair, scalp_output)

        else:
            self._no_trade_log(pair, scalp_output)

    def _execute_trade(self, pair: str,
                        scalp_output: dict) -> None:
        """
        Pipeline d'exécution : allocate → shield → order.
        """
        self._execute_count += 1

        # ── Capital Allocator ────────────────────────────────
        allocation = self._allocator.compute(pair, scalp_output)
        if not allocation.get("approved", False):
            logger.warning(
                f"Supervisor — {pair} | "
                f"Allocation rejetée : {allocation.get('reason')}"
            )
            return

        # ── Behaviour Shield ─────────────────────────────────
        shield = self._shield.validate(
            pair, scalp_output, allocation
        )
        if not shield.get("approved", False):
            logger.warning(
                f"Supervisor — {pair} | "
                f"Shield rejeté : {shield.get('reason')} "
                f"[{shield.get('filter_id')}]"
            )
            return

        # ── Envoi Ordre ──────────────────────────────────────
        result = self._orders.send_order(
            pair, scalp_output, allocation
        )

        if result.get("success"):
            logger.info(
                f"Supervisor — ✅ ORDRE EXÉCUTÉ {pair} | "
                f"Ticket : {result.get('ticket')} | "
                f"Lot : {result.get('lot')} | "
                f"Score : {scalp_output.get('score')} "
                f"[{scalp_output.get('grade')}]"
            )
        else:
            logger.error(
                f"Supervisor — ❌ ORDRE ÉCHOUÉ {pair} | "
                f"Raison : {result.get('reason')}"
            )

    def _watch_alert(self, pair: str,
                      scalp_output: dict) -> None:
        """WATCH — log structuré, pas d'ordre automatique."""
        self._watch_count += 1
        logger.info(
            f"Supervisor — 👁 WATCH {pair} | "
            f"Score : {scalp_output.get('score')} "
            f"[{scalp_output.get('grade')}] | "
            f"Direction : {scalp_output.get('direction')} | "
            f"RR : {scalp_output.get('rr')}"
        )

    def _no_trade_log(self, pair: str,
                       scalp_output: dict) -> None:
        """NO_TRADE — log debug uniquement."""
        self._no_trade_count += 1
        logger.debug(
            f"Supervisor — ⛔ NO_TRADE {pair} | "
            f"Score : {scalp_output.get('score')} | "
            f"Raison : {scalp_output.get('reason')}"
        )

    # ══════════════════════════════════════════════════════════
    # THREADS PÉRIODIQUES
    # ══════════════════════════════════════════════════════════

    def _start_background_threads(self) -> None:
        """Lance tous les threads périodiques en daemon."""
        tasks = [
            ("cb_eval",  CB_EVAL_INTERVAL,   self._task_cb_eval),
            ("trail",    TRAIL_INTERVAL_SEC,  self._task_trailing),
            ("cleanup",  CLEANUP_INTERVAL,    self._task_cleanup),
            ("health",   HEALTH_INTERVAL,     self._task_health),
            ("stats",    STATS_INTERVAL,      self._task_stats),
        ]

        # ── Démarrer le news manager (Point 1.12 Audit) ──────
        try:
            self._news.start()
        except Exception as e:
            logger.error(f"Supervisor — Erreur démarrage NewsManager : {e}")

        for name, interval, target in tasks:
            t = threading.Thread(
                target=self._periodic_wrapper,
                args=(name, interval, target),
                name=f"KB5_{name.upper()}",
                daemon=True
            )
            t.start()
            self._threads[name] = t
            logger.info(
                f"Supervisor — Thread {name} lancé "
                f"(intervalle : {interval}s)"
            )

    def _periodic_wrapper(self, name: str, interval: float,
                           target) -> None:
        """
        Wrapper pour les threads périodiques.
        Boucle jusqu'au signal d'arrêt, gère les exceptions.
        """
        while not self._shutdown_event.is_set():
            try:
                target()
            except Exception as e:
                self._error_count += 1
                logger.error(
                    f"Supervisor — Thread {name} erreur : {e}",
                    exc_info=True
                )
            # Attendre l'intervalle ou le signal d'arrêt
            self._shutdown_event.wait(timeout=interval)

    # ── CB EVAL ────────────────────────────────────────────────

    def _task_cb_eval(self) -> None:
        """Évaluation haute fréquence du Circuit Breaker."""
        cb_result = self._cb.evaluate()
        level = cb_result.get("level", 0)

        if level >= 2:
            logger.warning(
                f"Supervisor — CB EVAL | "
                f"Niveau {level} ({cb_result.get('level_name')}) | "
                f"DD : {cb_result.get('dd_pct')}%"
            )

    # ── TRAILING SL ────────────────────────────────────────────

    def _task_trailing(self) -> None:
        """
        Applique le trailing SL ATR sur toutes les positions
        ouvertes du bot.
        """
        try:
            positions = mt5.positions_get()
            if not positions:
                return

            magic = getattr(Trading, "BOT_MAGIC_NUMBER", 20260101)
            bot_pos = [p for p in positions if p.magic == magic]

            for pos in bot_pos:
                direction = (
                    "BULLISH" if pos.type == 0  # POSITION_TYPE_BUY
                    else "BEARISH"
                )
                result = self._orders.trail_sl(
                    pos.ticket, pos.symbol, direction
                )
                if result.get("moved"):
                    logger.info(
                        f"Supervisor — Trailing {pos.symbol} | "
                        f"Ticket : {pos.ticket} | "
                        f"SL : {result.get('old_sl')} → "
                        f"{result.get('new_sl')}"
                    )

        except Exception as e:
            logger.error(
                f"Supervisor — Trailing erreur : {e}"
            )

    # ── CLEANUP ────────────────────────────────────────────────

    def _task_cleanup(self) -> None:
        """
        Purge périodique des données périmées.
        Maintient la mémoire du bot sous contrôle.
        """
        # Purge news passées
        self._ks.clear_past_news()

        # Purge candles anciennes dans DataStore
        if hasattr(self._ds, "cleanup_old_candles"):
            self._ds.cleanup_old_candles()

        logger.debug("Supervisor — Cleanup périodique effectué")

    # ── HEALTH CHECK ───────────────────────────────────────────

    def _task_health(self) -> None:
        """
        Vérifie la santé de tous les modules critiques.
        Loggue les anomalies détectées.
        """
        issues = []

        # MT5 connexion
        try:
            if not self._connector.is_connected:
                issues.append("MT5Connector déconnecté")
        except Exception:
            issues.append("MT5Connector inaccessible")

        # DataStore
        try:
            self._ds.get_stats()
        except Exception:
            issues.append("DataStore inaccessible")

        # Circuit Breaker
        try:
            cb_level = self._cb.get_level()
            if cb_level >= 3:
                issues.append(f"CB{cb_level} HALT actif")
        except Exception:
            issues.append("CircuitBreaker inaccessible")

        # KS global
        try:
            ks_global = self._ks.get_global_status()
            blocked_pairs = [
                p for p, v in ks_global.items()
                if v.get("verdict") == "BLOCKED"
            ]
            if len(blocked_pairs) == len(self._pairs):
                issues.append(
                    f"TOUTES les paires KS BLOCKED : {blocked_pairs}"
                )
        except Exception:
            issues.append("KillSwitchEngine inaccessible")

        if issues:
            logger.warning(
                f"Supervisor — Health check | "
                f"Problèmes détectés : {issues}"
            )
        else:
            logger.debug("Supervisor — Health check OK")

    # ── STATS ──────────────────────────────────────────────────

    def _task_stats(self) -> None:
        """
        Log périodique des statistiques globales.
        Consommé aussi par Dashboard Patron.
        """
        scoring_stats = self._scoring.get_statistics()
        order_stats   = self._orders.get_snapshot()
        cb_snapshot   = self._cb.get_snapshot()
        alloc_snap    = self._allocator.get_snapshot()

        logger.info(
            f"═══ STATS KB5 ═══ | "
            f"Cycles : {self._cycle_count} | "
            f"Execute : {self._execute_count} | "
            f"Watch : {self._watch_count} | "
            f"No-Trade : {self._no_trade_count} | "
            f"Erreurs : {self._error_count} | "
            f"Execute rate : "
            f"{scoring_stats.get('execute_rate', 0)}% | "
            f"CB : CB{cb_snapshot.get('level')} "
            f"{cb_snapshot.get('name')} | "
            f"DD : {cb_snapshot.get('dd_pct')}% | "
            f"Equity : {alloc_snap.get('equity')} | "
            f"Ordres : {order_stats.get('total_orders')}"
        )

    # ══════════════════════════════════════════════════════════
    # GESTION QUOTIDIENNE
    # ══════════════════════════════════════════════════════════

    def _check_daily_reset(self) -> None:
        """
        Vérifie si un nouveau jour a commencé (UTC).
        Déclenche `_daily_init()` si nécessaire.
        """
        today_utc = datetime.now(timezone.utc).date()
        
        # Déclenchement si changement de jour
        should_reset = False
        with self._lock:
            if self._current_day != today_utc:
                should_reset = True
        
        if should_reset:
            logger.info(
                f"Supervisor — Nouveau jour détecté (UTC) : {today_utc} | "
                f"Lancement du reset journalier..."
            )
            self._daily_init()

    # ══════════════════════════════════════════════════════════
    # SESSIONS ICT
    # ══════════════════════════════════════════════════════════

    def _get_active_session(self) -> str:
        """
        Retourne la session ICT active (UTC).

        Returns:
            "LONDON" / "NY" / "TOKYO" / "OFF_SESSION"
        """
        now_utc = datetime.now(timezone.utc)
        h, m    = now_utc.hour, now_utc.minute
        current = h * 60 + m

        active = []
        for session, times in SESSIONS.items():
            open_min  = times["open"][0]  * 60 + times["open"][1]
            close_min = times["close"][0] * 60 + times["close"][1]
            if open_min <= current < close_min:
                active.append(session)

        if not active:
            return "OFF_SESSION"
        return "+".join(active)  # ex: "LONDON+NY" overlap

    # ══════════════════════════════════════════════════════════
    # ARRÊT PROPRE
    # ══════════════════════════════════════════════════════════

    def _on_signal(self, signum, frame) -> None:
        """Handler SIGTERM / SIGINT."""
        sig_name = "SIGTERM" if signum == 15 else "SIGINT"
        logger.warning(
            f"Supervisor — Signal reçu : {sig_name} | "
            f"Arrêt propre en cours"
        )
        self.shutdown(reason=sig_name)

    def shutdown(self, reason: str = "Manuel") -> None:
        """
        Arrêt ordonné du bot.

        Séquence :
          1. Lever l'événement d'arrêt (stop threads)
          2. Annuler tous les ordres pending
          3. Fermer toutes les positions (si configured)
          4. Logger les stats finales
          5. Déconnexion MT5

        Args:
            reason: raison de l'arrêt pour les logs
        """
        logger.warning(
            f"Supervisor — SHUTDOWN | Raison : {reason}"
        )

        # ── Stopper les boucles ──────────────────────────────
        self._shutdown_event.set()
        self._running = False

        # ── Stopper le NewsManager ───────────────────────────
        try:
            self._news.stop()
        except Exception as e:
            logger.error(f"Supervisor — Erreur arrêt NewsManager : {e}")

        # ── Attendre les threads ─────────────────────────────
        for name, thread in self._threads.items():
            thread.join(timeout=5)
            if thread.is_alive():
                logger.warning(
                    f"Supervisor — Thread {name} "
                    f"non terminé dans les 5s"
                )

        # ── Annuler ordres pending ────────────────────────────
        try:
            cancelled = self._orders.cancel_all_pending(
                reason=f"Shutdown — {reason}"
            )
            logger.info(
                f"Supervisor — {len(cancelled)} "
                f"ordres pending annulés"
            )
        except Exception as e:
            logger.error(
                f"Supervisor — Erreur annulation pending : {e}"
            )

        # ── Fermer positions si CB3 ou arrêt d'urgence ───────
        close_on_exit = getattr(
            Trading, "CLOSE_ON_EXIT", False
        )
        if close_on_exit or reason in ("SIGTERM", "CB3"):
            try:
                closed = self._orders.close_all_positions(
                    reason=f"Shutdown — {reason}"
                )
                logger.warning(
                    f"Supervisor — {len(closed)} "
                    f"positions fermées à l'arrêt"
                )
            except Exception as e:
                logger.error(
                    f"Supervisor — Erreur fermeture positions : {e}"
                )

        # ── Stats finales ────────────────────────────────────
        self._task_stats()

        # ── Déconnexion MT5 ──────────────────────────────────
        try:
            self._connector.disconnect()
            logger.info("Supervisor — MT5 déconnecté")
        except Exception as e:
            logger.error(
                f"Supervisor — Erreur déconnexion MT5 : {e}"
            )

        logger.info("Supervisor — Arrêt complet ✅")

    def _cleanup_on_exit(self) -> None:
        """Appelé dans le finally du start() pour garantir le cleanup."""
        if self._running:
            self.shutdown(reason="cleanup_on_exit")

    # ══════════════════════════════════════════════════════════
    # CONTRÔLE MANUEL (Dashboard Patron)
    # ══════════════════════════════════════════════════════════

    def pause(self, reason: str = "") -> None:
        """
        Met le bot en pause (analyse suspendue).
        Positions existantes maintenues.
        Appelé par Dashboard Patron.
        """
        with self._lock:
            self._paused = True
        logger.warning(
            f"Supervisor — BOT EN PAUSE | Raison : {reason}"
        )

    def resume(self, reason: str = "") -> None:
        """
        Reprend le bot après une pause.
        Appelé par Dashboard Patron.
        """
        with self._lock:
            self._paused = False
        logger.info(
            f"Supervisor — BOT REPRIS | Raison : {reason}"
        )

    def add_pair(self, pair: str) -> None:
        """Ajoute une paire à la surveillance en temps réel."""
        with self._lock:
            if pair not in self._pairs:
                self._pairs.append(pair)
                logger.info(
                    f"Supervisor — Paire ajoutée : {pair}"
                )

    def remove_pair(self, pair: str) -> None:
        """Retire une paire de la surveillance."""
        with self._lock:
            if pair in self._pairs:
                self._pairs.remove(pair)
                logger.info(
                    f"Supervisor — Paire retirée : {pair}"
                )

    # ══════════════════════════════════════════════════════════
    # API PUBLIQUE — STATUS
    # ══════════════════════════════════════════════════════════

    def get_global_status(self) -> dict:
        """
        Statut global complet pour Dashboard Patron.
        Agrège les snapshots de tous les modules.

        Returns:
            dict statut complet
        """
        return {
            "running":        self._running,
            "paused":         self._paused,
            "cycle_count":    self._cycle_count,
            "execute_count":  self._execute_count,
            "watch_count":    self._watch_count,
            "no_trade_count": self._no_trade_count,
            "error_count":    self._error_count,
            "session":        self._get_active_session(),
            "pairs":          list(self._pairs),
            "current_day":    str(self._current_day),

            # Modules
            "circuit_breaker":  self._cb.get_snapshot(),
            "allocator":        self._allocator.get_snapshot(),
            "orders":           self._orders.get_snapshot(),
            "shield":           self._shield.get_snapshot(),
            "scoring":          self._scoring.get_statistics(),
            "ks_global":        self._ks.get_global_status(),
            "all_verdicts":     self._scoring.get_all_verdicts(),

            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_snapshot(self) -> dict:
        """Snapshot compact pour Dashboard Patron header."""
        cb = self._cb.get_snapshot()
        return {
            "running":       self._running,
            "paused":        self._paused,
            "session":       self._get_active_session(),
            "pairs":         list(self._pairs),
            "cb_level":      cb.get("level"),
            "cb_name":       cb.get("name"),
            "dd_pct":        cb.get("dd_pct"),
            "equity":        cb.get("equity_now"),
            "cycles":        self._cycle_count,
            "execute":       self._execute_count,
            "errors":        self._error_count,
            "timestamp":     datetime.now(timezone.utc).isoformat(),
        }

    def is_running(self) -> bool:
        """True si le bot est actif et non en pause."""
        return self._running and not self._paused
    def is_ready(self) -> bool:
        """
        Vérifie que tous les modules critiques
        sont instanciés avant de lancer le Dashboard.
        """
        return all([
            self._ds        is not None,
            self._connector is not None,
            self._scoring   is not None,
            self._orders    is not None,
            self._cb        is not None,
            self._ks        is not None,
        ])


    def __repr__(self) -> str:
        return (
            f"Supervisor("
            f"pairs={self._pairs}, "
            f"running={self._running}, "
            f"cycles={self._cycle_count})"
        )
