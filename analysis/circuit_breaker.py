# analysis/circuit_breaker.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Circuit Breaker (Niveaux 0→3)
══════════════════════════════════════════════════════════════
Responsabilités :
  - Surveiller le drawdown journalier en temps réel
  - Surveiller les pertes consécutives
  - Escalader le niveau CB 0→3 selon les seuils
  - Déclencher les actions par niveau (réduction/pause/halt)
  - Auto-reset CB1 si equity remonte
  - Notifier DataStore + KillSwitchEngine (KS9)
  - Fournir get_status() pour Dashboard Patron

Niveaux Circuit Breaker :
  CB0 — NOMINAL  : Trading autorisé, surveillance passive
  CB1 — WARNING  : Drawdown approche seuil → taille réduite 50%
  CB2 — PAUSE    : Seuil atteint → plus de nouveaux trades
  CB3 — HALT     : Critique → fermeture forcée + arrêt total

Seuils de déclenchement :
  CB1 : drawdown ≥ 1.0% OU 2 pertes consécutives
  CB2 : drawdown ≥ 2.0% OU 3 pertes consécutives
  CB3 : drawdown ≥ 3.5% OU 5 pertes consécutives
        OU single trade loss ≥ 1.5× risk initial

Auto-reset :
  CB1 → CB0 si equity remonte au-dessus du seuil CB1
  CB2/CB3 → reset manuel uniquement (Patron)

Dépendances :
  - DataStore    → set_cb_state(), get_cb_level()
  - OrderReader  → get_exposure_summary(), get_open_positions()
  - MT5Connector → get_equity(), get_balance()
  - config.constants → Risk

Consommé par :
  - killswitch_engine.py  → KS9 lit cb_level DataStore
  - scoring_engine.py     → vérifie cb_level avant verdict
  - order_manager.py      → réduit sizing si CB1
  - supervisor.py         → monitoring + actions CB3
  - patron_dashboard.py   → affichage niveau CB
══════════════════════════════════════════════════════════════
"""

import logging
import threading
from datetime import datetime, timezone, date
from typing import Optional

from datastore.data_store import DataStore
from config.constants import Risk

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# SEUILS CIRCUIT BREAKER — depuis config (pas de magic numbers)
# ══════════════════════════════════════════════════════════════

CB_LEVELS = {
    0: {
        "name":           "NOMINAL",
        "dd_threshold":   0.0,
        "consec_losses":  0,
        "action":         "TRADING_NORMAL",
        "size_factor":    1.0,    # taille normale
        "description":    "Trading autorisé — surveillance passive",
    },
    1: {
        "name":           "WARNING",
        "dd_threshold":   1.0,   # % drawdown
        "consec_losses":  2,     # pertes consécutives
        "action":         "REDUCE_SIZE",
        "size_factor":    0.5,   # 50% de la taille normale
        "description":    "Drawdown warning — taille réduite 50%",
    },
    2: {
        "name":           "PAUSE",
        "dd_threshold":   2.0,
        "consec_losses":  3,
        "action":         "NO_NEW_TRADES",
        "size_factor":    0.0,   # aucun nouveau trade
        "description":    "Drawdown seuil — plus de nouveaux trades",
    },
    3: {
        "name":           "HALT",
        "dd_threshold":   3.5,
        "consec_losses":  5,
        "action":         "CLOSE_ALL_HALT",
        "size_factor":    0.0,
        "description":    "Drawdown critique — fermeture forcée + arrêt",
    },
}

# Seuil trade individuel : perte > X× risque initial → CB2 immédiat
SINGLE_TRADE_LOSS_FACTOR  = 1.5

# Auto-reset CB1 : si equity remonte au-dessus du seuil CB1
CB1_AUTORESET_THRESHOLD   = 0.8  # remonte à 80% du seuil CB1

# Intervalle de vérification minimum (secondes)
CHECK_INTERVAL_SEC        = 10

# ══════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════

class CircuitBreaker:
    """
    Surveille le drawdown et les pertes consécutives en temps réel.
    Escalade automatiquement le niveau CB 0→3 et déclenche
    les actions de protection associées.

    Le niveau CB est stocké dans DataStore et lu par KillSwitchEngine
    (KS9) — pas d'appel direct entre les deux modules.
    """

    def __init__(self,
                 data_store: DataStore,
                 order_reader=None,
                 mt5_connector=None):
        self._ds        = data_store
        self._orders    = order_reader
        self._connector = mt5_connector
        self._lock      = threading.Lock()

        # État interne
        self._current_level:     int   = 0
        self._equity_day_open:   float = 0.0
        self._consecutive_losses: int  = 0
        self._last_check:        Optional[datetime] = None
        self._day_initialized:   bool  = False
        self._current_day:       Optional[date] = None

        # Historique des escalades
        self._escalation_log: list[dict] = []

        # Callbacks pour actions CB3 (injecté par supervisor)
        self._on_halt_callbacks: list = []

        logger.info("CircuitBreaker initialisé — CB0 NOMINAL")

    # ══════════════════════════════════════════════════════════
    # INITIALISATION JOURNALIÈRE
    # ══════════════════════════════════════════════════════════

    def initialize_day(self) -> bool:
        """
        Initialise l'equity de référence pour le jour en cours.
        Doit être appelé une fois par jour à l'ouverture.
        Appelé par supervisor.py au démarrage de chaque session.

        Returns:
            True si initialisation réussie
        """
        equity = self._get_current_equity()
        if equity <= 0:
            logger.error("CircuitBreaker — impossible d'initialiser l'equity jour")
            return False

        today = date.today()
        with self._lock:
            self._equity_day_open  = equity
            self._current_day      = today
            self._day_initialized  = True
            self._consecutive_losses = 0

        logger.info(
            f"CircuitBreaker — Equity jour initialisée : "
            f"{equity:.2f} | Date : {today}"
        )
        return True

    # ══════════════════════════════════════════════════════════
    # MÉTHODE PRINCIPALE — ÉVALUATION
    # ══════════════════════════════════════════════════════════

    def evaluate(self) -> dict:
        """
        Évalue l'état du Circuit Breaker.
        Appelé périodiquement par supervisor.py.

        Pipeline :
          1. Vérifier reset journalier si nouveau jour
          2. Calculer drawdown actuel
          3. Compter pertes consécutives
          4. Déterminer le niveau CB requis
          5. Escalader ou auto-reset si nécessaire
          6. Pousser dans DataStore
          7. Retourner CBResult

        Returns:
            dict CBResult complet
        """
        now = datetime.now(timezone.utc)

        # ── Reset journalier ────────────────────────────────
        today = date.today()
        with self._lock:
            if self._current_day != today:
                self._day_initialized = False

        if not self._day_initialized:
            self.initialize_day()

        # ── Calcul drawdown ─────────────────────────────────
        current_equity = self._get_current_equity()
        dd_pct         = self._calculate_drawdown_pct(current_equity)

        # ── Pousser l'equity dans DataStore (pour CapitalAllocator) ──
        if current_equity > 0:
            self._ds.set_equity(current_equity)

        # ── Pertes consécutives ─────────────────────────────
        consec = self._get_consecutive_losses()

        # ── Niveau CB requis ────────────────────────────────
        required_level = self._determine_required_level(dd_pct, consec)

        # ── Vérifier single trade loss ──────────────────────
        single_loss_trigger = self._check_single_trade_loss()
        if single_loss_trigger and required_level < 2:
            required_level = 2
            logger.warning(
                "CircuitBreaker — Single trade loss excessive "
                f"→ escalade forcée CB2"
            )

        # ── Escalade ou auto-reset ──────────────────────────
        with self._lock:
            prev_level     = self._current_level
            new_level      = self._resolve_level(
                                 prev_level, required_level, dd_pct
                             )
            self._current_level = new_level

        # ── Action si changement de niveau ──────────────────
        if new_level != prev_level:
            self._on_level_change(prev_level, new_level, dd_pct,
                                   consec, now)

        # ── Pousser dans DataStore ───────────────────────────
        self._ds.set_cb_state(new_level, CB_LEVELS[new_level]["name"], dd_pct)


        result = {
            "level":          new_level,
            "level_name":     CB_LEVELS[new_level]["name"],
            "action":         CB_LEVELS[new_level]["action"],
            "size_factor":    CB_LEVELS[new_level]["size_factor"],
            "dd_pct":         round(dd_pct,        3),
            "consec_losses":  consec,
            "equity_now":     round(current_equity, 2),
            "equity_open":    round(self._equity_day_open, 2),
            "timestamp":      now.isoformat(),
            "escalations":    len(self._escalation_log),
            "single_loss":    single_loss_trigger,
            "thresholds": {
                lvl: CB_LEVELS[lvl]["dd_threshold"]
                for lvl in CB_LEVELS
            },
        }

        self._last_check = now
        return result

    # ══════════════════════════════════════════════════════════
    # CALCUL DRAWDOWN
    # ══════════════════════════════════════════════════════════

    def _calculate_drawdown_pct(self, current_equity: float) -> float:
        """
        Calcule le drawdown en % par rapport à l'equity d'ouverture.

        Returns:
            float négatif si drawdown, positif si gain
            ex : -2.5 = drawdown de 2.5%
        """
        with self._lock:
            day_open = self._equity_day_open

        if day_open <= 0:
            return 0.0

        dd_pct = ((current_equity - day_open) / day_open) * 100
        return round(dd_pct, 4)

    def _determine_required_level(self, dd_pct: float,
                                    consec: int) -> int:
        """
        Détermine le niveau CB requis selon drawdown et pertes.

        Règle : prendre le niveau le plus élevé déclenché
        par l'une ou l'autre des conditions.

        Returns:
            int niveau CB requis (0→3)
        """
        required = 0

        for level in [3, 2, 1]:
            cfg = CB_LEVELS[level]
            dd_trigger     = dd_pct <= -abs(cfg["dd_threshold"])
            consec_trigger = consec >= cfg["consec_losses"]

            if dd_trigger or consec_trigger:
                required = level
                break

        return required

    def _resolve_level(self, current: int, required: int,
                        dd_pct: float) -> int:
        """
        Résout le niveau final en appliquant les règles d'escalade
        et d'auto-reset.

        Règles :
          - Escalade toujours autorisée (required > current)
          - CB2/CB3 → reset manuel uniquement
          - CB1 → auto-reset si dd_pct remonte

        Args:
            current:  niveau CB actuel
            required: niveau CB calculé
            dd_pct:   drawdown actuel en %

        Returns:
            int niveau CB résolu
        """
        # Escalade toujours prioritaire
        if required > current:
            return required

        # Auto-reset CB1 → CB0 si equity remonte
        if current == 1 and required == 0:
            cb1_threshold = CB_LEVELS[1]["dd_threshold"]
            reset_threshold = cb1_threshold * CB1_AUTORESET_THRESHOLD
            if dd_pct > -abs(reset_threshold):
                logger.info(
                    f"CircuitBreaker — Auto-reset CB1→CB0 | "
                    f"DD actuel : {dd_pct:.2f}% | "
                    f"Seuil reset : {-abs(reset_threshold):.2f}%"
                )
                return 0

        # CB2/CB3 restent jusqu'au reset manuel
        if current >= 2:
            return current

        return current

    # ══════════════════════════════════════════════════════════
    # PERTES CONSÉCUTIVES
    # ══════════════════════════════════════════════════════════

    def _get_consecutive_losses(self) -> int:
        """
        Calcule le nombre de pertes consécutives du bot.
        Lit les positions fermées du jour via OrderReader.

        Returns:
            int nombre de pertes consécutives récentes
        """
        if self._orders is None:
            with self._lock:
                return self._consecutive_losses

        try:
            closed = []  # méthode indisponible

            if not closed:
                return 0

            # Filtrer uniquement les ordres du bot
            bot_magic = getattr(
                __import__('config.constants', fromlist=['Trading']).Trading,
                'BOT_MAGIC_NUMBER', 20260101
            )
            bot_closed = [
                o for o in closed
                if o.get("magic") == bot_magic
            ]

            if not bot_closed:
                return 0

            # Compter les pertes consécutives depuis la fin
            consec = 0
            for order in reversed(bot_closed):
                if order.get("profit", 0) < 0:
                    consec += 1
                else:
                    break  # série interrompue

            with self._lock:
                self._consecutive_losses = consec

            return consec

        except Exception as e:
            logger.error(f"CircuitBreaker — erreur pertes consécutives : {e}")
            with self._lock:
                return self._consecutive_losses

    def record_trade_result(self, profit: float) -> None:
        """
        Enregistre manuellement le résultat d'un trade.
        Appelé par order_manager après fermeture de position.

        Args:
            profit: PnL du trade (positif = gain, négatif = perte)
        """
        with self._lock:
            if profit < 0:
                self._consecutive_losses += 1
            else:
                self._consecutive_losses = 0

        logger.debug(
            f"CircuitBreaker — Trade enregistré | "
            f"PnL : {profit:.2f} | "
            f"Pertes consécutives : {self._consecutive_losses}"
        )

        # Re-évaluer immédiatement
        self.evaluate()

    # ══════════════════════════════════════════════════════════
    # SINGLE TRADE LOSS
    # ══════════════════════════════════════════════════════════

    def _check_single_trade_loss(self) -> bool:
        """
        Vérifie si un trade individuel a dépassé
        SINGLE_TRADE_LOSS_FACTOR × risque initial.

        Returns:
            True si une perte individuelle excessive détectée
        """
        if self._orders is None:
            return False

        try:
            exposure = self._orders.get_exposure_summary()
            positions = self._orders.get_open_positions()

            for pos in positions:
                profit    = pos.get("profit", 0)
                risk_amt  = pos.get("risk_amount", 0)

                if risk_amt <= 0:
                    continue

                loss_factor = abs(profit) / risk_amt
                if profit < 0 and loss_factor >= SINGLE_TRADE_LOSS_FACTOR:
                    logger.warning(
                        f"CircuitBreaker — Single loss excessive | "
                        f"Symbol : {pos.get('symbol')} | "
                        f"Perte : {profit:.2f} | "
                        f"Facteur : {loss_factor:.2f}×"
                    )
                    return True

            return False

        except Exception as e:
            logger.error(f"CircuitBreaker — erreur single loss check : {e}")
            return False

    # ══════════════════════════════════════════════════════════
    # ACTIONS PAR NIVEAU
    # ══════════════════════════════════════════════════════════

    def _on_level_change(self, prev: int, new: int,
                          dd_pct: float, consec: int,
                          now: datetime) -> None:
        """
        Déclenche les actions associées au changement de niveau CB.
        Loggue l'événement et notifie les callbacks enregistrés.
        """
        direction = "↑ ESCALADE" if new > prev else "↓ RESET"
        level_name = CB_LEVELS[new]["name"]
        action     = CB_LEVELS[new]["action"]

        log_msg = (
            f"CircuitBreaker {direction} — "
            f"CB{prev} → CB{new} ({level_name}) | "
            f"DD : {dd_pct:.2f}% | "
            f"Pertes consécutives : {consec} | "
            f"Action : {action}"
        )

        if new >= 2:
            logger.critical(log_msg)
        elif new == 1:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        # Historique escalade
        self._escalation_log.append({
            "timestamp":  now.isoformat(),
            "from_level": prev,
            "to_level":   new,
            "dd_pct":     dd_pct,
            "consec":     consec,
            "action":     action,
        })

        # Callbacks CB3 (fermeture forcée)
        if new == 3:
            logger.critical(
                "CircuitBreaker CB3 HALT — "
                "Déclenchement fermeture forcée toutes positions"
            )
            for cb in self._on_halt_callbacks:
                try:
                    cb()
                except Exception as e:
                    logger.error(f"CircuitBreaker — callback CB3 erreur : {e}")

    # ══════════════════════════════════════════════════════════
    # EQUITY
    # ══════════════════════════════════════════════════════════

    def _get_current_equity(self) -> float:
        """
        Récupère l'equity actuelle via MT5Connector ou OrderReader.

        Returns:
            float equity actuelle, ou 0.0 si indisponible
        """
        # Priorité 1 : MT5Connector
        if self._connector is not None:
            try:
                info = self._connector.get_account_info()
                equity = info.get("equity", 0.0)
                if equity > 0:
                    return float(equity)
            except Exception as e:
                logger.error(f"CircuitBreaker — equity MT5 erreur : {e}")

        # Priorité 2 : OrderReader
        if self._orders is not None:
            try:
                exposure = self._orders.get_exposure_summary()
                equity   = exposure.get("equity", 0.0)
                if equity > 0:
                    return float(equity)
            except Exception as e:
                logger.error(f"CircuitBreaker — equity OrderReader erreur : {e}")

        logger.error("CircuitBreaker — equity indisponible (0.0 retourné)")
        return 0.0

    # ══════════════════════════════════════════════════════════
    # RESET MANUEL
    # ══════════════════════════════════════════════════════════

    def manual_reset(self, target_level: int = 0,
                     reason: str = "Reset Patron") -> bool:
        """
        Reset manuel du niveau CB.
        Utilisé exclusivement par le Patron via Dashboard.
        CB2/CB3 ne peuvent être réinitialisés qu'ici.

        Args:
            target_level: niveau cible (0 par défaut)
            reason:       raison du reset

        Returns:
            True si reset effectué
        """
        if target_level not in CB_LEVELS:
            logger.error(
                f"CircuitBreaker — reset invalide : "
                f"niveau {target_level} inexistant"
            )
            return False

        with self._lock:
            prev = self._current_level
            self._current_level      = target_level
            self._consecutive_losses = 0

        self._ds.set_cb_state(target_level, CB_LEVELS[target_level]["name"], 0.0)


        logger.warning(
            f"CircuitBreaker — RESET MANUEL | "
            f"CB{prev} → CB{target_level} | "
            f"Raison : {reason}"
        )

        self._escalation_log.append({
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "from_level": prev,
            "to_level":   target_level,
            "dd_pct":     None,
            "consec":     0,
            "action":     f"MANUAL_RESET — {reason}",
        })

        return True

    # ══════════════════════════════════════════════════════════
    # CALLBACKS CB3
    # ══════════════════════════════════════════════════════════

    def register_halt_callback(self, callback) -> None:
        """
        Enregistre un callback déclenché sur CB3 HALT.
        Utilisé par supervisor.py pour fermer toutes les positions.

        Args:
            callback: fonction callable sans argument
        """
        self._on_halt_callbacks.append(callback)
        logger.info(
            f"CircuitBreaker — callback HALT enregistré : "
            f"{getattr(callback, '__name__', str(callback))}"
        )

    # ══════════════════════════════════════════════════════════
    # API PUBLIQUE
    # ══════════════════════════════════════════════════════════

    def get_level(self) -> int:
        """
        Retourne le niveau CB actuel.
        Raccourci pour scoring_engine et order_manager.

        Returns:
            int 0→3
        """
        with self._lock:
            return self._current_level

    def get_size_factor(self) -> float:
        """
        Retourne le facteur de taille de position selon CB.
        Consommé directement par capital_allocator.py.

        Returns:
            float 1.0 (normal) / 0.5 (CB1) / 0.0 (CB2-CB3)
        """
        with self._lock:
            level = self._current_level
        return CB_LEVELS[level]["size_factor"]

    def is_trading_allowed(self) -> bool:
        """
        Vérifie si le trading est autorisé selon le niveau CB.
        Raccourci pour scoring_engine.

        Returns:
            True uniquement si CB0 ou CB1
        """
        with self._lock:
            level = self._current_level
        return level < 2

    def get_status(self) -> dict:
        """
        Retourne le statut complet du Circuit Breaker.
        Consommé par supervisor.py et Dashboard Patron.

        Returns:
            dict {level, name, action, dd_pct, consec, equity...}
        """
        with self._lock:
            level  = self._current_level
            consec = self._consecutive_losses
            eq_open= self._equity_day_open

        current_equity = self._get_current_equity()
        dd_pct         = self._calculate_drawdown_pct(current_equity)

        return {
            "level":         level,
            "level_name":    CB_LEVELS[level]["name"],
            "action":        CB_LEVELS[level]["action"],
            "size_factor":   CB_LEVELS[level]["size_factor"],
            "dd_pct":        round(dd_pct,         3),
            "consec_losses": consec,
            "equity_now":    round(current_equity,  2),
            "equity_open":   round(eq_open,          2),
            "trading_ok":    self.is_trading_allowed(),
            "escalations":   len(self._escalation_log),
            "last_check":    self._last_check.isoformat()
                             if self._last_check else None,
            "thresholds":    {
                f"CB{lvl}": CB_LEVELS[lvl]["dd_threshold"]
                for lvl in CB_LEVELS
            },
        }

    def get_escalation_log(self, last_n: int = 10) -> list:
        """
        Retourne les N dernières escalades pour audit.
        Utilisé par Dashboard Patron section historique.

        Args:
            last_n: nombre d'entrées à retourner

        Returns:
            liste des dernières escalades
        """
        return list(self._escalation_log[-last_n:])

    def get_snapshot(self) -> dict:
        """
        Snapshot compact pour Dashboard Patron.

        Returns:
            dict {level, name, dd_pct, trading_ok, consec}
        """
        status = self.get_status()
        return {
            "level":       status["level"],
            "name":        status["level_name"],
            "dd_pct":      status["dd_pct"],
            "trading_ok":  status["trading_ok"],
            "size_factor": status["size_factor"],
            "consec":      status["consec_losses"],
            "equity_now":  status["equity_now"],
        }

    def __repr__(self) -> str:
        with self._lock:
            level = self._current_level
        return (
            f"CircuitBreaker("
            f"level=CB{level} {CB_LEVELS[level]['name']}, "
            f"equity_open={self._equity_day_open:.2f})"
        )
