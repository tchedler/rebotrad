# execution/order_manager.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Order Manager (Envoi Ordres MT5)
══════════════════════════════════════════════════════════════
Responsabilités :
  - Envoyer les ordres LIMIT / STOP / MARKET à MT5
  - Attacher SL et TP obligatoires à chaque ordre
  - Modifier le SL (trailing ATR manuel)
  - Fermer partiellement ou totalement une position
  - Annuler les ordres pending invalidés
  - Vérifier la confirmation MT5 post-envoi
  - Appliquer la retry logic (3 tentatives)
  - Notifier CircuitBreaker des résultats de trade
  - Respecter le magic number KB5 sur tous les ordres

Types d'ordres supportés :
  MARKET  → ORDER_TYPE_BUY / ORDER_TYPE_SELL
  LIMIT   → ORDER_TYPE_BUY_LIMIT / ORDER_TYPE_SELL_LIMIT
  STOP    → ORDER_TYPE_BUY_STOP  / ORDER_TYPE_SELL_STOP

Règle absolue KB5 :
  Aucun ordre n'est envoyé sans SL valide.
  Aucun ordre n'est envoyé si KS99 ou CB≥2 actif.
  Tout ordre utilise BOT_MAGIC_NUMBER = 20260101.

Dépendances :
  - MT5Connector      → initialize(), order_send()
  - DataStore         → get_ks_state(), get_cb_level()
  - OrderReader       → get_position_by_ticket()
  - CapitalAllocator  → get_risk_summary()
  - CircuitBreaker    → record_trade_result()
  - config.constants  → Trading, Gateway

Consommé par :
  - supervisor.py  → appelle send_order() si EXECUTE
══════════════════════════════════════════════════════════════
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import MetaTrader5 as mt5

from datastore.data_store import DataStore
from config.constants import Trading, Gateway

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# CONSTANTES ORDER MANAGER
# ══════════════════════════════════════════════════════════════

BOT_MAGIC_NUMBER   = getattr(Trading, "BOT_MAGIC_NUMBER", 20260101)
MAX_RETRIES        = 3          # tentatives max par ordre
RETRY_DELAY_SEC    = 1.0        # délai entre tentatives
CONFIRM_TIMEOUT_SEC= 5.0        # timeout confirmation post-envoi
DEVIATION_POINTS   = 20         # slippage max autorisé (points)
PARTIAL_CLOSE_PCT  = 0.50       # fermeture partielle = 50%

# ATR Trailing
TRAILING_ATR_FACTOR= 1.0        # SL trail = 1× ATR H1 sous le prix
TRAILING_MIN_MOVE  = 0.5        # SL ne bouge que si gain ≥ 0.5× ATR

# Map direction → type ordre MT5
ORDER_TYPE_MAP = {
    ("BULLISH", "MARKET"): mt5.ORDER_TYPE_BUY,
    ("BEARISH", "MARKET"): mt5.ORDER_TYPE_SELL,
    ("BULLISH", "LIMIT"):  mt5.ORDER_TYPE_BUY_LIMIT,
    ("BEARISH", "LIMIT"):  mt5.ORDER_TYPE_SELL_LIMIT,
    ("BULLISH", "STOP"):   mt5.ORDER_TYPE_BUY_STOP,
    ("BEARISH", "STOP"):   mt5.ORDER_TYPE_SELL_STOP,
}

# ══════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════

class OrderManager:
    """
    Gère l'envoi, la modification et la fermeture des ordres MT5.
    Seul module autorisé à communiquer avec l'API MT5 pour les ordres.

    Garanties :
      - Jamais d'ordre sans SL valide
      - Magic number sur chaque ordre
      - Confirmation systématique post-envoi
      - Un seul ordre actif par paire (verrou par paire)
    """

    def __init__(self,
                 data_store: DataStore,
                 mt5_connector=None,
                 order_reader=None,
                 capital_allocator=None,
                 circuit_breaker=None):
        self._ds        = data_store
        self._connector = mt5_connector
        self._reader    = order_reader
        self._allocator = capital_allocator
        self._cb        = circuit_breaker
        self._lock      = threading.Lock()

        # Verrous par paire (un seul ordre actif par paire)
        self._pair_locks: dict[str, threading.Lock] = {}

        # Historique des ordres envoyés
        self._order_history: list[dict] = []

        # Map ticket → SCALP_OUTPUT d'origine
        self._ticket_map: dict[int, dict] = {}

        logger.info(
            f"OrderManager initialisé — "
            f"Magic : {BOT_MAGIC_NUMBER}"
        )

    # ══════════════════════════════════════════════════════════
    # MÉTHODE PRINCIPALE — ENVOI ORDRE
    # ══════════════════════════════════════════════════════════

    def send_order(self, pair: str,
                   scalp_output: dict,
                   allocation: dict) -> dict:
        """
        Point d'entrée principal. Envoie un ordre à MT5
        selon le SCALP_OUTPUT et l'AllocationResult.

        Pipeline :
          1. Pré-validations (KS99, CB, SL, lot)
          2. Construire la requête MT5
          3. Envoyer avec retry logic
          4. Confirmer la présence dans MT5
          5. Logger et stocker
          6. Retourner OrderResult

        Args:
            pair:         ex. "EURUSD"
            scalp_output: dict SCALP_OUTPUT de scoring_engine
            allocation:   dict AllocationResult de capital_allocator

        Returns:
            dict OrderResult {success, ticket, reason, ...}
        """
        now = datetime.now(timezone.utc)

        # ── Pré-validations ─────────────────────────────────
        pre_check = self._pre_validate(pair, scalp_output, allocation)
        if not pre_check["ok"]:
            return self._order_failed(pair, pre_check["reason"],
                                       scalp_output, now)

        direction  = scalp_output["direction"]
        entry_type = scalp_output.get("entry_type", "LIMIT")
        entry      = scalp_output["entry"]
        sl         = scalp_output["sl"]
        tp         = scalp_output["tp"]
        lot        = allocation["lot_size"]
        comment    = f"KB5_{pair}_{direction[:4]}"

        # ── Verrou par paire ────────────────────────────────
        pair_lock = self._get_pair_lock(pair)
        if not pair_lock.acquire(blocking=False):
            return self._order_failed(
                pair,
                f"Ordre déjà en cours sur {pair} — verrou actif",
                scalp_output, now
            )

        try:
            # ── Construire requête MT5 ───────────────────────
            order_type = ORDER_TYPE_MAP.get(
                (direction, entry_type),
                mt5.ORDER_TYPE_BUY if direction == "BULLISH"
                else mt5.ORDER_TYPE_SELL
            )

            request = self._build_request(
                pair, order_type, lot,
                entry, sl, tp, comment
            )

            if request is None:
                return self._order_failed(
                    pair, "Construction requête MT5 échouée",
                    scalp_output, now
                )

            # ── Envoi avec retry ────────────────────────────
            result_mt5 = self._send_with_retry(pair, request)

            if result_mt5 is None:
                return self._order_failed(
                    pair, "Envoi MT5 échoué après retries",
                    scalp_output, now
                )

            ticket = result_mt5.order

            # ── Confirmation post-envoi ─────────────────────
            confirmed = self._confirm_order(pair, ticket, direction)
            if not confirmed:
                logger.warning(
                    f"OrderManager — {pair} | "
                    f"Ticket {ticket} non confirmé dans MT5"
                )

            # ── Enregistrement ──────────────────────────────
            order_result = {
                "success":    True,
                "ticket":     ticket,
                "pair":       pair,
                "direction":  direction,
                "entry_type": entry_type,
                "entry":      entry,
                "sl":         sl,
                "tp":         tp,
                "lot":        lot,
                "comment":    comment,
                "magic":      BOT_MAGIC_NUMBER,
                "confirmed":  confirmed,
                "timestamp":  now.isoformat(),
                "retcode":    result_mt5.retcode,
                "score":      scalp_output.get("score"),
                "grade":      scalp_output.get("grade"),
                "rr":         scalp_output.get("rr"),
            }

            with self._lock:
                self._order_history.append(order_result)
                self._ticket_map[ticket] = scalp_output
                if len(self._order_history) > 200:
                    self._order_history = self._order_history[-200:]

            logger.info(
                f"Ordre exécuté — {pair} {direction} | "
                f"Ticket : {ticket} | "
                f"Vol : {lot} | "
                f"Entry : {entry} | SL : {sl} | TP : {tp} | "
                f"RR : {scalp_output.get('rr')} | "
                f"Score : {scalp_output.get('score')} "
                f"[{scalp_output.get('grade')}]"
            )

            return order_result

        finally:
            pair_lock.release()

    # ══════════════════════════════════════════════════════════
    # PRÉ-VALIDATIONS
    # ══════════════════════════════════════════════════════════

    def _pre_validate(self, pair: str,
                      scalp_output: dict,
                      allocation: dict) -> dict:
        """
        Validations de sécurité avant envoi.
        Vérifications indépendantes du SCALP_OUTPUT.

        Returns:
            dict {ok: bool, reason: str}
        """
        # KS99 Gateway
        ks99 = self._ds.get_ks_state(ks_id=99)
        if ks99.get("active", False):
            return {"ok": False,
                    "reason": "KS99 — Gateway déconnecté"}

        # Anti-doublons : refuser si position déjà ouverte sur cette paire
        try:
            positions = mt5.positions_get(symbol=pair)
            if positions:
                bot_pos = [p for p in positions
                           if p.magic == BOT_MAGIC_NUMBER]
                if bot_pos:
                    return {"ok": False,
                            "reason": f"Position déjà ouverte sur {pair} "
                                      f"(ticket {bot_pos[0].ticket})"}
        except Exception as e:
            logger.warning(f"OrderManager — anti-doublon {pair} : {e}")

        # Circuit Breaker
        cb_level = self._ds.get_cb_level()
        if cb_level >= 2:
            return {"ok": False,
                    "reason": f"CB{cb_level} actif — trading bloqué"}

        # Verdict
        if scalp_output.get("verdict") != "EXECUTE":
            return {"ok": False,
                    "reason": f"Verdict {scalp_output.get('verdict')} "
                               f"≠ EXECUTE"}

        # SL obligatoire
        sl = scalp_output.get("sl")
        if sl is None or sl == 0:
            return {"ok": False,
                    "reason": "SL absent ou nul — ordre refusé"}

        # TP obligatoire
        tp = scalp_output.get("tp")
        if tp is None or tp == 0:
            return {"ok": False,
                    "reason": "TP absent ou nul — ordre refusé"}

        # Lot valide
        lot = allocation.get("lot_size", 0.0)
        if lot <= 0:
            return {"ok": False,
                    "reason": f"Lot invalide : {lot}"}

        # Allocation approuvée
        if not allocation.get("approved", False):
            return {"ok": False,
                    "reason": f"Allocation rejetée : "
                               f"{allocation.get('reason')}"}

        # MT5 connecté
        if self._connector is None:
            return {"ok": False,
                    "reason": "MT5Connector non disponible"}

        return {"ok": True, "reason": ""}

    # ══════════════════════════════════════════════════════════
    # CONSTRUCTION REQUÊTE MT5
    # ══════════════════════════════════════════════════════════

    def _build_request(self, pair: str,
                        order_type: int,
                        lot: float,
                        entry: float,
                        sl: float,
                        tp: float,
                        comment: str) -> Optional[dict]:
        """
        Construit le dict de requête MT5 selon le type d'ordre.

        Pour MARKET : price = 0, action = TRADE_ACTION_DEAL
        Pour PENDING : price = entry, action = TRADE_ACTION_PENDING

        Returns:
            dict request MT5 ou None si erreur
        """
        try:
            is_market = order_type in (
                mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL
            )

            # Prix selon le type
            if is_market:
                tick = self._get_tick(pair)
                if tick is None:
                    logger.error(
                        f"OrderManager — {pair} | "
                        f"Tick indisponible pour ordre market"
                    )
                    return None

                price = (tick["ask"] if order_type == mt5.ORDER_TYPE_BUY
                         else tick["bid"])
                action = mt5.TRADE_ACTION_DEAL
            else:
                price  = entry
                action = mt5.TRADE_ACTION_PENDING

            request = {
                "action":    action,
                "symbol":    pair,
                "volume":    float(lot),
                "type":      order_type,
                "price":     float(price),
                "sl":        float(sl),
                "tp":        float(tp),
                "deviation": DEVIATION_POINTS,
                "magic":     BOT_MAGIC_NUMBER,
                "comment":   comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            return request

        except Exception as e:
            logger.error(
                f"OrderManager — build_request erreur : {e}"
            )
            return None

    # ══════════════════════════════════════════════════════════
    # ENVOI AVEC RETRY
    # ══════════════════════════════════════════════════════════

    def _send_with_retry(self, pair: str,
                          request: dict):
        """
        Tente d'envoyer l'ordre jusqu'à MAX_RETRIES fois.
        Délai RETRY_DELAY_SEC entre chaque tentative.

        Returns:
            résultat MT5 order_send ou None si échec total
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = mt5.order_send(request)

                if result is None:
                    logger.warning(
                        f"OrderManager — {pair} | "
                        f"Tentative {attempt}/{MAX_RETRIES} : "
                        f"order_send retourne None"
                    )
                    time.sleep(RETRY_DELAY_SEC)
                    continue

                if result.retcode == mt5.TRADE_RETCODE_DONE:
                    logger.info(
                        f"OrderManager — {pair} | "
                        f"Ordre accepté tentative {attempt} | "
                        f"Retcode : {result.retcode}"
                    )
                    return result

                # Retcodes récupérables
                recoverable = {
                    mt5.TRADE_RETCODE_REQUOTE,
                    mt5.TRADE_RETCODE_PRICE_CHANGED,
                    mt5.TRADE_RETCODE_OFF_QUOTES,
                    mt5.TRADE_RETCODE_PRICE_OFF,
                }

                if result.retcode in recoverable:
                    logger.warning(
                        f"OrderManager — {pair} | "
                        f"Tentative {attempt}/{MAX_RETRIES} | "
                        f"Retcode récupérable : {result.retcode} | "
                        f"Retry dans {RETRY_DELAY_SEC}s"
                    )

                    # Mettre à jour le prix pour MARKET
                    if request["action"] == mt5.TRADE_ACTION_DEAL:
                        tick = self._get_tick(pair)
                        if tick:
                            is_buy = (
                                request["type"] == mt5.ORDER_TYPE_BUY
                            )
                            request["price"] = (
                                tick["ask"] if is_buy else tick["bid"]
                            )

                    time.sleep(RETRY_DELAY_SEC)
                    continue

                # Retcode non récupérable
                logger.error(
                    f"OrderManager — {pair} | "
                    f"Retcode non récupérable : {result.retcode} | "
                    f"Comment : {result.comment}"
                )
                return None

            except Exception as e:
                logger.error(
                    f"OrderManager — {pair} | "
                    f"Exception tentative {attempt} : {e}"
                )
                time.sleep(RETRY_DELAY_SEC)

        logger.error(
            f"OrderManager — {pair} | "
            f"Échec après {MAX_RETRIES} tentatives"
        )
        return None

    # ══════════════════════════════════════════════════════════
    # CONFIRMATION POST-ENVOI
    # ══════════════════════════════════════════════════════════

    def _confirm_order(self, pair: str, ticket: int,
                        direction: str) -> bool:
        """
        Vérifie que l'ordre/position est bien présent dans MT5.
        Interroge OrderReader avec get_position_by_ticket().

        Returns:
            True si confirmé dans MT5
        """
        if self._reader is None:
            return True  # pas de vérification possible

        deadline = time.time() + CONFIRM_TIMEOUT_SEC

        while time.time() < deadline:
            try:
                pos = self._reader.get_position_by_ticket(ticket)
                if pos is not None:
                    return True

                # Vérifier aussi les ordres pending
                orders = mt5.orders_get(ticket=ticket)
                if orders and len(orders) > 0:
                    return True

            except Exception as e:
                logger.error(
                    f"OrderManager — confirm erreur : {e}"
                )

            time.sleep(0.5)

        return False

    # ══════════════════════════════════════════════════════════
    # MODIFICATION SL (TRAILING ATR)
    # ══════════════════════════════════════════════════════════

    def trail_sl(self, ticket: int, pair: str,
                  direction: str) -> dict:
        """
        Déplace le SL vers le break-even ou en trailing ATR.

        Règle de trailing KB5 :
          - Calculer ATR H1 actuel
          - BULLISH : nouveau SL = current_price - 1× ATR H1
          - BEARISH : nouveau SL = current_price + 1× ATR H1
          - Ne déplacer que si nouveau SL est meilleur ET
            gain ≥ 0.5× ATR (évite trailing trop agressif)

        Args:
            ticket:    ticket de la position
            pair:      symbole
            direction: "BULLISH" ou "BEARISH"

        Returns:
            dict {moved, new_sl, old_sl, reason}
        """
        if self._reader is None or self._connector is None:
            return {"moved": False,
                    "reason": "Reader ou Connector absent"}

        try:
            pos = self._reader.get_position_by_ticket(ticket)
            if pos is None:
                return {"moved": False,
                        "reason": f"Position {ticket} non trouvée"}

            current_sl  = pos.get("sl", 0.0)
            current_price = pos.get("price_current",
                                     pos.get("price_open", 0.0))

            # ATR H1
            df_h1 = self._ds.get_candles(pair, "H1")
            if df_h1 is None or len(df_h1) < 15:
                return {"moved": False,
                        "reason": "H1 insuffisant pour ATR trailing"}

            atr_h1 = self._calculate_atr_h1(df_h1)

            # Calculer le nouveau SL
            if direction == "BULLISH":
                new_sl  = current_price - (TRAILING_ATR_FACTOR * atr_h1)
                min_gain = pos.get("price_open", 0) + (
                    TRAILING_MIN_MOVE * atr_h1
                )
                sl_better = new_sl > current_sl
                gain_ok   = current_price >= min_gain
            else:
                new_sl  = current_price + (TRAILING_ATR_FACTOR * atr_h1)
                min_gain = pos.get("price_open", 0) - (
                    TRAILING_MIN_MOVE * atr_h1
                )
                sl_better = new_sl < current_sl
                gain_ok   = current_price <= min_gain

            if not sl_better or not gain_ok:
                return {
                    "moved":   False,
                    "reason":  "Conditions trailing non remplies",
                    "new_sl":  round(new_sl, 6),
                    "old_sl":  round(current_sl, 6),
                    "sl_better": sl_better,
                    "gain_ok":   gain_ok,
                }

            new_sl = round(new_sl, 6)

            # Envoyer la modification à MT5
            request = {
                "action":   mt5.TRADE_ACTION_SLTP,
                "ticket":   ticket,
                "sl":       new_sl,
                "tp":       pos.get("tp", 0.0),
            }

            result = mt5.order_send(request)

            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(
                    f"Trailing SL — {pair} ticket {ticket} | "
                    f"SL : {current_sl} → {new_sl} | "
                    f"Price : {current_price} | "
                    f"ATR : {round(atr_h1, 6)}"
                )
                return {
                    "moved":   True,
                    "new_sl":  new_sl,
                    "old_sl":  round(current_sl, 6),
                    "reason":  "Trailing ATR appliqué",
                }

            return {
                "moved":  False,
                "reason": f"MT5 retcode : "
                          f"{result.retcode if result else 'None'}",
            }

        except Exception as e:
            logger.error(
                f"OrderManager — trail_sl erreur : {e}"
            )
            return {"moved": False, "reason": str(e)}

    # ══════════════════════════════════════════════════════════
    # FERMETURE POSITION
    # ══════════════════════════════════════════════════════════

    def close_position(self, ticket: int, pair: str,
                        direction: str,
                        partial: bool = False) -> dict:
        """
        Ferme une position totalement ou partiellement (50%).

        Args:
            ticket:    ticket de la position
            pair:      symbole
            direction: "BULLISH" ou "BEARISH"
            partial:   True = fermer 50%, False = tout fermer

        Returns:
            dict {success, closed_lot, pnl, reason}
        """
        if self._reader is None:
            return {"success": False,
                    "reason": "OrderReader absent"}

        try:
            pos = self._reader.get_position_by_ticket(ticket)
            if pos is None:
                return {"success": False,
                        "reason": f"Position {ticket} non trouvée"}

            total_lot = pos.get("volume", 0.0)
            close_lot = (
                round(total_lot * PARTIAL_CLOSE_PCT, 2)
                if partial else total_lot
            )

            # Type de clôture (inverse de l'ouverture)
            close_type = (
                mt5.ORDER_TYPE_SELL
                if direction == "BULLISH"
                else mt5.ORDER_TYPE_BUY
            )

            tick = self._get_tick(pair)
            if tick is None:
                return {"success": False,
                        "reason": "Tick indisponible"}

            price = (tick["bid"] if direction == "BULLISH"
                     else tick["ask"])

            request = {
                "action":    mt5.TRADE_ACTION_DEAL,
                "symbol":    pair,
                "volume":    float(close_lot),
                "type":      close_type,
                "position":  ticket,
                "price":     float(price),
                "deviation": DEVIATION_POINTS,
                "magic":     BOT_MAGIC_NUMBER,
                "comment":   f"CLOSE_{'PARTIAL' if partial else 'FULL'}_{ticket}",
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = self._send_with_retry(pair, request)

            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                # Notifier CircuitBreaker
                pnl = pos.get("profit", 0.0)
                if self._cb and not partial:
                    self._cb.record_trade_result(pnl)

                logger.info(
                    f"Position fermée — {pair} ticket {ticket} | "
                    f"Type : {'Partielle' if partial else 'Totale'} | "
                    f"Lot : {close_lot} | "
                    f"PnL : {pnl:.2f}"
                )

                return {
                    "success":    True,
                    "ticket":     ticket,
                    "closed_lot": close_lot,
                    "pnl":        round(pnl, 2),
                    "partial":    partial,
                    "reason":     "Fermeture réussie",
                }

            return {
                "success": False,
                "reason":  f"MT5 retcode : "
                           f"{result.retcode if result else 'None'}",
            }

        except Exception as e:
            logger.error(
                f"OrderManager — close_position erreur : {e}"
            )
            return {"success": False, "reason": str(e)}

    # ══════════════════════════════════════════════════════════
    # ANNULATION ORDRE PENDING
    # ══════════════════════════════════════════════════════════

    def cancel_pending(self, ticket: int,
                        reason: str = "") -> dict:
        """
        Annule un ordre pending (LIMIT/STOP) non déclenché.
        Appelé par supervisor si le setup est invalidé.

        Args:
            ticket: ticket de l'ordre pending
            reason: raison de l'annulation (pour logs)

        Returns:
            dict {success, ticket, reason}
        """
        try:
            request = {
                "action": mt5.TRADE_ACTION_REMOVE,
                "order":  ticket,
            }

            result = mt5.order_send(request)

            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(
                    f"Ordre pending annulé — Ticket : {ticket} | "
                    f"Raison : {reason}"
                )
                return {
                    "success": True,
                    "ticket":  ticket,
                    "reason":  reason or "Annulation réussie",
                }

            return {
                "success": False,
                "ticket":  ticket,
                "reason":  f"MT5 retcode : "
                           f"{result.retcode if result else 'None'}",
            }

        except Exception as e:
            logger.error(
                f"OrderManager — cancel_pending erreur : {e}"
            )
            return {"success": False, "reason": str(e)}

    def cancel_all_pending(self, pair: str = None,
                            reason: str = "") -> list:
        """
        Annule tous les ordres pending du bot.
        Appelé par supervisor sur CB3 ou KS99.

        Args:
            pair:   filtrer par paire optionnel
            reason: raison de l'annulation globale

        Returns:
            liste des résultats d'annulation
        """
        try:
            orders = mt5.orders_get()
            if not orders:
                return []

            bot_orders = [
                o for o in orders
                if o.magic == BOT_MAGIC_NUMBER
                and (pair is None or o.symbol == pair)
            ]

            results = []
            for order in bot_orders:
                res = self.cancel_pending(
                    order.ticket,
                    reason or f"cancel_all — {pair or 'ALL'}"
                )
                results.append(res)

            logger.warning(
                f"OrderManager — cancel_all_pending | "
                f"Paire : {pair or 'TOUTES'} | "
                f"Annulés : {len(results)} | "
                f"Raison : {reason}"
            )

            return results

        except Exception as e:
            logger.error(
                f"OrderManager — cancel_all_pending erreur : {e}"
            )
            return []

    def close_all_positions(self, reason: str = "") -> list:
        """
        Ferme toutes les positions ouvertes du bot.
        Appelé par CircuitBreaker CB3 via callback supervisor.

        Args:
            reason: raison de la fermeture forcée

        Returns:
            liste des résultats de fermeture
        """
        try:
            positions = mt5.positions_get()
            if not positions:
                return []

            bot_positions = [
                p for p in positions
                if p.magic == BOT_MAGIC_NUMBER
            ]

            results = []
            for pos in bot_positions:
                direction = (
                    "BULLISH" if pos.type == mt5.POSITION_TYPE_BUY
                    else "BEARISH"
                )
                res = self.close_position(
                    pos.ticket, pos.symbol,
                    direction, partial=False
                )
                results.append(res)

            logger.critical(
                f"OrderManager — close_all_positions | "
                f"Fermées : {len(results)} | "
                f"Raison : {reason}"
            )

            return results

        except Exception as e:
            logger.error(
                f"OrderManager — close_all_positions erreur : {e}"
            )
            return []

    # ══════════════════════════════════════════════════════════
    # UTILITAIRES INTERNES
    # ══════════════════════════════════════════════════════════

    def _get_tick(self, pair: str) -> Optional[dict]:
        """
        Récupère le tick actuel pour un symbole.

        Returns:
            dict {bid, ask, time} ou None
        """
        try:
            tick = mt5.symbol_info_tick(pair)
            if tick is None:
                return None
            return {
                "bid":  tick.bid,
                "ask":  tick.ask,
                "time": tick.time,
            }
        except Exception as e:
            logger.error(
                f"OrderManager — get_tick {pair} erreur : {e}"
            )
            return None

    def _get_pair_lock(self, pair: str) -> threading.Lock:
        """Retourne (ou crée) le verrou pour une paire."""
        with self._lock:
            if pair not in self._pair_locks:
                self._pair_locks[pair] = threading.Lock()
            return self._pair_locks[pair]

    def _calculate_atr_h1(self, df,
                            period: int = 14) -> float:
        """ATR H1 pour trailing SL."""
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

        atr = sum(tr_list[-period:]) / period
        return atr if atr > 0 else 0.0001

    def _order_failed(self, pair: str, reason: str,
                       scalp_output: dict,
                       now: datetime) -> dict:
        """Retourne un OrderResult d'échec standardisé."""
        logger.warning(
            f"OrderManager — Ordre refusé | "
            f"{pair} | Raison : {reason}"
        )
        return {
            "success":    False,
            "ticket":     None,
            "pair":       pair,
            "direction":  scalp_output.get("direction"),
            "reason":     reason,
            "timestamp":  now.isoformat(),
        }

    # ══════════════════════════════════════════════════════════
    # API PUBLIQUE
    # ══════════════════════════════════════════════════════════

    def get_order_history(self, pair: str = None,
                           last_n: int = 20) -> list:
        """
        Retourne l'historique des ordres envoyés.

        Args:
            pair:   filtre par paire optionnel
            last_n: nombre d'entrées max

        Returns:
            liste des derniers ordres
        """
        with self._lock:
            history = list(self._order_history)

        if pair:
            history = [o for o in history if o["pair"] == pair]

        return history[-last_n:]

    def get_order_stats(self) -> dict:
        """
        Statistiques ordres pour Dashboard Patron.

        Returns:
            dict {total, success, failed, by_pair}
        """
        with self._lock:
            history = list(self._order_history)

        success_list = [o for o in history if o.get("success")]
        failed_list  = [o for o in history if not o.get("success")]

        by_pair: dict[str, int] = {}
        for o in success_list:
            p = o.get("pair", "?")
            by_pair[p] = by_pair.get(p, 0) + 1

        return {
            "total":   len(history),
            "success": len(success_list),
            "failed":  len(failed_list),
            "by_pair": by_pair,
        }

    def get_snapshot(self) -> dict:
        """Snapshot compact pour Dashboard Patron."""
        stats = self.get_order_stats()
        return {
            "total_orders": stats["total"],
            "success":      stats["success"],
            "failed":       stats["failed"],
            "by_pair":      stats["by_pair"],
            "last_order":   (
                self._order_history[-1]
                if self._order_history else None
            ),
        }

    def __repr__(self) -> str:
        with self._lock:
            total = len(self._order_history)
        return (
            f"OrderManager("
            f"magic={BOT_MAGIC_NUMBER}, "
            f"orders_sent={total})"
        )
