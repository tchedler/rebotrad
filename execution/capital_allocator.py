# execution/capital_allocator.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Capital Allocator (Sizing ATR)
══════════════════════════════════════════════════════════════
Responsabilités :
  - Calculer le lot size précis basé sur le risque en %
  - Utiliser le SL du SCALP_OUTPUT pour calibrer le risque
  - Adapter la pip value par instrument (Forex/Or/Indices/BTC)
  - Appliquer le CB size_factor (CB1 = 50%, CB2/CB3 = 0%)
  - Respecter les contraintes MT5 (lot min/max/step/marge)
  - Retourner un AllocationResult complet pour order_manager

Formule de base :
  risk_amount = equity × (risk_pct / 100)
  sl_pips     = abs(entry - sl) / pip_size
  pip_value   = contract_size × pip_size   (par lot)
  lot_size    = risk_amount / (sl_pips × pip_value)
  lot_size   *= cb_size_factor
  lot_size    = clamp(lot_size, lot_min, lot_max)
  lot_size    = round_to_step(lot_size, lot_step)

Pip size par type d'instrument :
  Forex 5 déc. (EURUSD)  : pip = 0.0001
  Forex JPY   (USDJPY)   : pip = 0.01
  Or          (XAUUSD)   : pip = 0.1  (1 pip = $1 par oz)
  Pétrole     (USOIL)    : pip = 0.01
  Indices US  (US30)     : pip = 1.0  (1 point)
  BTC         (BTCUSD)   : pip = 1.0  (1 dollar)

Dépendances :
  - DataStore       → get_stats() pour equity
  - MT5Connector    → symbol_info() pour contraintes lot
  - CircuitBreaker  → get_size_factor()
  - config.constants → Risk, Trading

Consommé par :
  - behaviour_shield.py  → validation lot avant envoi
  - order_manager.py     → lot final pour envoi ordre MT5
══════════════════════════════════════════════════════════════
"""

import logging
import threading
import math
from typing import Optional

from datastore.data_store import DataStore
from config.constants import Risk, Trading

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# PIP SIZE PAR INSTRUMENT
# ══════════════════════════════════════════════════════════════

PIP_SIZE_MAP = {
    # Forex majeurs (5 décimales)
    "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001,
    "USDCHF": 0.0001, "NZDUSD": 0.0001, "USDCAD": 0.0001,
    "EURGBP": 0.0001, "EURAUD": 0.0001, "GBPAUD": 0.0001,

    # Forex majeurs — suffixe 'm' (Exness)
    "EURUSDm": 0.0001, "GBPUSDm": 0.0001, "AUDUSDm": 0.0001,
    "USDCHFm": 0.0001, "NZDUSDm": 0.0001, "USDCADm": 0.0001,

    # Forex JPY (3 décimales → pip = 0.01)
    "USDJPY": 0.01,   "EURJPY": 0.01,   "GBPJPY": 0.01,
    "AUDJPY": 0.01,   "CADJPY": 0.01,   "CHFJPY": 0.01,

    # Forex JPY — suffixe 'm'
    "USDJPYm": 0.01,

    # Métaux
    "XAUUSD": 0.1,    # Or : 1 pip = 0.1$
    "XAGUSD": 0.001,  # Argent

    # Métaux — suffixe 'm'
    "XAUUSDm": 0.1,   # Or
    "XAGUSDm": 0.001, # Argent

    # Énergie
    "USOIL":  0.01,   # Pétrole WTI
    "UKOIL":  0.01,

    # Énergie — suffixe 'm'
    "USOILm": 0.01,   # Pétrole WTI
    "UKOILm": 0.01,   # Pétrole Brent

    # Indices US (points entiers)
    "US30":   1.0,    # Dow Jones
    "NAS100": 1.0,    # Nasdaq
    "SPX500": 0.1,    # S&P 500

    # Indices — suffixe 'm'
    "USTECm": 1.0,    # Nasdaq 100
    "US500m": 0.1,    # S&P 500
    "DE30m":  1.0,    # DAX 40
    "UK100m": 1.0,    # FTSE 100

    # Crypto
    "BTCUSD": 1.0,    # BTC par dollar
    "ETHUSD": 0.1,

    # Crypto — suffixe 'm'
    "BTCUSDm": 1.0,   # BTC
    "ETHUSDm": 0.1,   # ETH

    # DXY (indice dollar)
    "DXYm":   0.001,

    # Défaut
    "DEFAULT": 0.0001,
}

# Taille de contrat par instrument (unités par lot)
CONTRACT_SIZE_MAP = {
    # Forex standard
    "EURUSD": 100000, "GBPUSD": 100000, "AUDUSD": 100000,
    "USDCHF": 100000, "USDJPY": 100000, "USDCAD": 100000,
    "NZDUSD": 100000,
    "EURGBP": 100000, "EURJPY": 100000, "GBPJPY": 100000,

    # Forex 'm' — Exness
    "EURUSDm": 100000, "GBPUSDm": 100000, "AUDUSDm": 100000,
    "USDCHFm": 100000, "USDJPYm": 100000, "USDCADm": 100000,
    "NZDUSDm": 100000,

    # Métaux
    "XAUUSD": 100,    # 100 oz par lot
    "XAGUSD": 5000,
    "XAUUSDm": 100,
    "XAGUSDm": 5000,

    # Énergie
    "USOIL":  1000,   # 1000 barils par lot
    "USOILm": 1000,
    "UKOILm": 1000,

    # Indices US
    "US30":   1.0,    # CFD : pip_value = 1$ × lot
    "NAS100": 1.0,
    "SPX500": 10.0,
    "USTECm": 1.0,    # Nasdaq Exness
    "US500m": 10.0,   # S&P 500 Exness
    "DE30m":  1.0,    # DAX
    "UK100m": 1.0,    # FTSE

    # Crypto
    "BTCUSD": 1.0,
    "ETHUSD": 1.0,
    "BTCUSDm": 1.0,
    "ETHUSDm": 1.0,

    # DXY
    "DXYm":   1000.0,

    "DEFAULT": 100000,
}

# ══════════════════════════════════════════════════════════════
# CONTRAINTES LOT PAR DÉFAUT (overridées par MT5 symbol_info)
# ══════════════════════════════════════════════════════════════

DEFAULT_LOT_CONSTRAINTS = {
    "lot_min":  0.01,
    "lot_max":  50.0,
    "lot_step": 0.01,
}

# ══════════════════════════════════════════════════════════════
# MODE TEST — PÉRIODE DE DÉMONSTRATION
# TODO: Passer TEST_MODE à False avant de passer en compte réel
# ══════════════════════════════════════════════════════════════
TEST_MODE         = True   # True = compte démo / phase de test
TEST_LOT_MIN      = 0.01   # Lot minimum en test
TEST_LOT_MAX      = 0.10   # Lot maximum en test (sécurité démo)

# ══════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════

class CapitalAllocator:
    """
    Calcule la taille de position optimale selon le risque ATR.
    Produit un AllocationResult complet pour order_manager.

    La règle fondamentale : on ne risque jamais plus de
    Risk.DEFAULT_RISK_PCT% de l'equity sur un seul trade,
    modulé par le Circuit Breaker (×0.5 en CB1, ×0.0 en CB2/CB3).
    """

    def __init__(self,
                 data_store: DataStore,
                 mt5_connector=None,
                 circuit_breaker=None):
        self._ds   = data_store
        self._mt5  = mt5_connector
        self._cb   = circuit_breaker
        self._lock = threading.Lock()

        # Cache des symbol_info MT5 (évite appels répétés)
        self._symbol_cache: dict[str, dict] = {}

        logger.info("CapitalAllocator initialisé — Sizing ATR prêt")

    # ══════════════════════════════════════════════════════════
    # MÉTHODE PRINCIPALE
    # ══════════════════════════════════════════════════════════

    def compute(self, pair: str,
                scalp_output: dict) -> dict:
        """
        Calcule le lot size final pour un SCALP_OUTPUT donné.
        Point d'entrée principal appelé par order_manager.

        Args:
            pair:         ex. "EURUSD"
            scalp_output: dict SCALP_OUTPUT de scoring_engine

        Returns:
            dict AllocationResult {
                lot_size, risk_amount, risk_pct,
                sl_pips, pip_value, cb_factor,
                approved, reason
            }
        """
        # ── Vérification verdict ────────────────────────────
        if scalp_output.get("verdict") != "EXECUTE":
            return self._rejected(
                "Verdict non-EXECUTE",
                scalp_output.get("verdict", "UNKNOWN")
            )

        entry = scalp_output.get("entry")
        sl    = scalp_output.get("sl")

        if entry is None or sl is None:
            return self._rejected("Entry ou SL absent", None)

        if abs(entry - sl) == 0:
            return self._rejected("Entry = SL (risque nul)", None)

        # ── Equity actuelle ─────────────────────────────────
        equity = self._get_equity()
        if equity <= 0:
            return self._rejected("Equity indisponible", 0)

        # ── Risque en montant ───────────────────────────────
        risk_pct    = getattr(Risk, "DEFAULT_RISK_PCT", 1.0)
        risk_amount = equity * (risk_pct / 100)

        # ── CB size_factor ──────────────────────────────────
        cb_factor = self._get_cb_factor(scalp_output)
        if cb_factor <= 0:
            return self._rejected(
                f"CB size_factor = {cb_factor} (trading bloqué)",
                cb_factor
            )

        risk_amount *= cb_factor

        # ── Pip size & contract size ────────────────────────
        pip_size      = self._get_pip_size(pair)
        contract_size = self._get_contract_size(pair)
        pip_value     = self._calculate_pip_value(
                            pair, pip_size, contract_size
                        )

        # ── SL en pips ──────────────────────────────────────
        sl_distance = abs(entry - sl)
        sl_pips     = sl_distance / pip_size

        if sl_pips <= 0:
            return self._rejected("SL distance nulle", sl_pips)

        # ── Calcul lot brut ─────────────────────────────────
        lot_raw = risk_amount / (sl_pips * pip_value)

        # ── Contraintes MT5 ─────────────────────────────────
        constraints = self._get_lot_constraints(pair)
        lot_min     = constraints["lot_min"]
        lot_max     = constraints["lot_max"]
        lot_step    = constraints["lot_step"]

        # Clamp entre min et max
        lot_clamped = max(lot_min, min(lot_max, lot_raw))

        # Arrondir au step
        lot_final   = self._round_to_step(lot_clamped, lot_step)

        # ── Validation marge disponible ─────────────────────
        # En mode TEST, on bypass la vérification de marge
        # pour permettre de trader sur tous les instruments en démo
        if TEST_MODE:
            lot_final = max(TEST_LOT_MIN, min(TEST_LOT_MAX, lot_final))
            logger.info(
                f"CapitalAllocator TEST_MODE — {pair} | "
                f"Lot forcé entre {TEST_LOT_MIN} et {TEST_LOT_MAX} : {lot_final}"
            )
        else:
            margin_ok = self._check_margin(pair, lot_final, entry)
            if not margin_ok:
                # Tenter de réduire le lot de 50%
                lot_reduced = self._round_to_step(lot_final * 0.5, lot_step)
                if lot_reduced >= lot_min:
                    lot_final = lot_reduced
                    logger.warning(
                        f"CapitalAllocator — {pair} | "
                        f"Marge insuffisante → lot réduit à {lot_final}"
                    )
                else:
                    return self._rejected(
                        "Marge insuffisante même à 50%",
                        lot_final
                    )

        # ── Risque réel recalculé ───────────────────────────
        actual_risk    = lot_final * sl_pips * pip_value
        actual_risk_pct= (actual_risk / equity) * 100 if equity > 0 else 0

        result = {
            # Résultat principal
            "lot_size":       lot_final,
            "approved":       True,
            "reason":         "Sizing validé",

            # Détail calcul
            "equity":         round(equity,        2),
            "risk_pct":       round(risk_pct,       2),
            "risk_amount":    round(risk_amount,    2),
            "actual_risk":    round(actual_risk,    2),
            "actual_risk_pct":round(actual_risk_pct,3),

            # Structure SL
            "entry":          entry,
            "sl":             sl,
            "sl_distance":    round(sl_distance,    6),
            "sl_pips":        round(sl_pips,        2),

            # Pip calculation
            "pip_size":       pip_size,
            "pip_value":      round(pip_value,      4),
            "contract_size":  contract_size,

            # CB
            "cb_factor":      cb_factor,

            # Lot détail
            "lot_raw":        round(lot_raw,     4),
            "lot_min":        lot_min,
            "lot_max":        lot_max,
            "lot_step":       lot_step,
        }

        logger.info(
            f"CapitalAllocator — {pair} | "
            f"Lot : {lot_final} | "
            f"Risque : {round(actual_risk, 2)}$ "
            f"({round(actual_risk_pct, 2)}%) | "
            f"SL : {round(sl_pips, 1)} pips | "
            f"CB factor : {cb_factor}"
        )

        return result

    # ══════════════════════════════════════════════════════════
    # PIP VALUE PAR INSTRUMENT
    # ══════════════════════════════════════════════════════════

    
    def _calculate_pip_value(self, pair: str, pip_size: float,
                            contract_size: float) -> float:
        """Pip value depuis MT5 directement (méthode fiable)."""
        # Priorité 1 : MT5 trade_tick_value / tick_size → pip value réelle
        if self.mt5 is not None:
            try:
                info = self.mt5.get_symbol_info(pair)
                if info:
                    tick_value = info.get("trade_tick_value", 0.0)
                    tick_size  = info.get("trade_tick_size", pip_size)
                    if tick_size > 0 and tick_value > 0:
                        return round((tick_value / tick_size) * pip_size, 6)
            except Exception as e:
                logger.warning(f"CapitalAllocator — pip_value MT5 {pair} : {e}")

        # Fallback : formule codée en dur (si MT5 indisponible)
        inverse_pairs = ["USDCHF", "USDJPY", "USDCAD"]
        direct_pairs  = [
            "EURUSDm", "GBPUSDm", "AUDUSDm", "NZDUSDm",
            "XAUUSDm", "XAGUSDm", "USOILm", "UKOILm",
            "USTECm", "US500m", "DE30m", "UK100m",
            "BTCUSDm", "ETHUSDm", "DXYm",
        ]
        if pair in direct_pairs:
            return contract_size * pip_size
        if pair in inverse_pairs:
            current_price = self.get_current_price(pair)
            if current_price > 0:
                return contract_size * pip_size / current_price
        return contract_size * pip_size

    # ══════════════════════════════════════════════════════════
    # CONTRAINTES MT5
    # ══════════════════════════════════════════════════════════

    def _get_lot_constraints(self, pair: str) -> dict:
        """
        Récupère les contraintes lot depuis MT5 via symbol_info.
        Cache pour éviter les appels répétés.

        Returns:
            dict {lot_min, lot_max, lot_step}
        """
        with self._lock:
            if pair in self._symbol_cache:
                return self._symbol_cache[pair]

        constraints = dict(DEFAULT_LOT_CONSTRAINTS)

        if self._mt5 is not None:
            try:
                info = self._mt5.get_symbol_info(pair)
                if info:
                    constraints = {
                        "lot_min":  info.get("volume_min",  0.01),
                        "lot_max":  info.get("volume_max",  50.0),
                        "lot_step": info.get("volume_step", 0.01),
                    }
            except Exception as e:
                logger.warning(
                    f"CapitalAllocator — symbol_info {pair} "
                    f"indisponible : {e} | defaults utilisés"
                )

        with self._lock:
            self._symbol_cache[pair] = constraints

        return constraints

    def _check_margin(self, pair: str, lot: float,
                       entry: float) -> bool:
        """
        Vérifie si la marge disponible est suffisante.

        Returns:
            True si marge suffisante ou vérification impossible
        """
        if self._mt5 is None:
            return True  # pas de vérification possible

        try:
            account = self._mt5.get_account_info()
            free_margin  = account.get("margin_free", 0.0)
            margin_needed = self._estimate_margin(
                pair, lot, entry, account
            )

            if margin_needed <= 0:
                return True

            ok = free_margin >= margin_needed * 1.2  # 20% buffer

            if not ok:
                logger.warning(
                    f"CapitalAllocator — {pair} | "
                    f"Marge libre : {free_margin:.2f} | "
                    f"Marge requise : {margin_needed:.2f} (×1.2 buffer)"
                )

            return ok

        except Exception as e:
            logger.error(
                f"CapitalAllocator — check_margin erreur : {e}"
            )
            return True  # fail open (pas bloquer sans certitude)

    def _estimate_margin(self, pair: str, lot: float,
                          entry: float,
                          account: dict) -> float:
        """
        Estime la marge requise pour un lot donné.

        Formule approximative :
          margin = (lot × contract_size × entry) / leverage

        Returns:
            float marge estimée en devise compte
        """
        try:
            leverage      = account.get("leverage", 100)
            contract_size = self._get_contract_size(pair)

            if leverage <= 0:
                leverage = 100

            margin = (lot * contract_size * entry) / leverage
            return round(margin, 2)

        except Exception:
            return 0.0

    # ══════════════════════════════════════════════════════════
    # UTILITAIRES
    # ══════════════════════════════════════════════════════════

    def _get_pip_size(self, pair: str) -> float:
        """Retourne la taille d'un pip pour le symbole."""
        return PIP_SIZE_MAP.get(pair, PIP_SIZE_MAP["DEFAULT"])

    def _get_contract_size(self, pair: str) -> float:
        """Retourne la taille de contrat pour le symbole."""
        return CONTRACT_SIZE_MAP.get(pair, CONTRACT_SIZE_MAP["DEFAULT"])

    def _get_cb_factor(self, scalp_output: dict) -> float:
        """
        Retourne le CB size_factor depuis CircuitBreaker
        ou depuis le SCALP_OUTPUT si CB non disponible.

        Returns:
            float 1.0 / 0.5 / 0.0
        """
        if self._cb is not None:
            return self._cb.get_size_factor()

        # Fallback : lire depuis SCALP_OUTPUT
        cb_data = scalp_output.get("circuit_breaker", {})
        return cb_data.get("size_factor", 1.0)

    def _get_equity(self) -> float:
        """
        Récupère l'equity actuelle depuis MT5 ou DataStore.

        Returns:
            float equity, ou 0.0 si indisponible
        """
        # Priorité 1 : MT5Connector
        if self._mt5 is not None:
            try:
                info   = self._mt5.get_account_info()
                equity = info.get("equity", 0.0)
                if equity > 0:
                    return float(equity)
            except Exception as e:
                logger.error(
                    f"CapitalAllocator — equity MT5 erreur : {e}"
                )

        # Priorité 2 : DataStore — equity poussée par le CircuitBreaker
        try:
            equity = self._ds.get_equity()
            if equity > 0:
                return float(equity)
        except Exception as e:
            logger.error(
                f"CapitalAllocator — equity DataStore erreur : {e}"
            )

        logger.error("CapitalAllocator — equity indisponible")
        return 0.0

    def _get_current_price(self, pair: str) -> float:
        """
        Récupère le prix actuel pour les calculs pip_value inversés.

        Returns:
            float prix actuel ou 0.0
        """
        if self._mt5 is not None:
            try:
                tick = self._mt5.get_latest_tick(pair)
                if tick:
                    return float(tick.get("bid", 0.0))
            except Exception:
                pass

        # Fallback DataStore
        try:
            df = self._ds.get_candles(pair, "M15")
            if df is not None and len(df) > 0:
                return float(df["close"].iloc[-1])
        except Exception:
            pass

        return 0.0

    def _round_to_step(self, lot: float, step: float) -> float:
        """
        Arrondit le lot au step inférieur le plus proche.
        Utilise math.floor pour ne jamais dépasser le risque calculé.

        Args:
            lot:  lot brut
            step: pas du symbole (ex: 0.01)

        Returns:
            float lot arrondi
        """
        if step <= 0:
            return round(lot, 2)

        decimals = max(0, -int(math.floor(math.log10(step))))
        rounded  = math.floor(lot / step) * step
        return round(rounded, decimals)

    def _rejected(self, reason: str, value) -> dict:
        """Retourne un AllocationResult rejeté standardisé."""
        logger.warning(
            f"CapitalAllocator — Allocation rejetée | "
            f"Raison : {reason} | Valeur : {value}"
        )
        
        # En mode test, on ne force plus rien ici
        # (TEST_MODE gère tout dans compute())
        return {
            "lot_size":    0.0,
            "approved":    False,
            "reason":      reason,
            "equity":      0.0,
            "risk_pct":    0.0,
            "risk_amount": 0.0,
            "sl_pips":     0.0,
            "pip_value":   0.0,
            "cb_factor":   0.0,
        }

    # ══════════════════════════════════════════════════════════
    # API PUBLIQUE
    # ══════════════════════════════════════════════════════════




    def get_risk_summary(self, pair: str,
                          entry: float, sl: float,
                          lot: float) -> dict:
        """
        Calcule le risque réel d'un lot donné.
        Utilisé par order_manager pour validation finale.

        Args:
            pair:  symbole
            entry: prix d'entrée
            sl:    stop loss
            lot:   taille de lot

        Returns:
            dict {risk_amount, risk_pct, sl_pips, pip_value}
        """
        pip_size      = self._get_pip_size(pair)
        contract_size = self._get_contract_size(pair)
        pip_value     = self._calculate_pip_value(
                            pair, pip_size, contract_size
                        )
        equity        = self._get_equity()
        sl_pips       = abs(entry - sl) / pip_size if pip_size > 0 else 0
        risk_amount   = lot * sl_pips * pip_value
        risk_pct      = (risk_amount / equity * 100) if equity > 0 else 0

        return {
            "risk_amount": round(risk_amount, 2),
            "risk_pct":    round(risk_pct,    3),
            "sl_pips":     round(sl_pips,     2),
            "pip_value":   round(pip_value,   4),
            "equity":      round(equity,      2),
        }

    def invalidate_symbol_cache(self, pair: str = None) -> None:
        """
        Vide le cache symbol_info pour forcer un rechargement.
        Appelé par supervisor au démarrage ou changement de symbole.

        Args:
            pair: symbole spécifique ou None pour tout vider
        """
        with self._lock:
            if pair:
                self._symbol_cache.pop(pair, None)
                logger.info(
                    f"CapitalAllocator — cache {pair} invalidé"
                )
            else:
                self._symbol_cache.clear()
                logger.info(
                    "CapitalAllocator — cache symboles vidé"
                )

    def get_snapshot(self) -> dict:
        """
        Snapshot pour Dashboard Patron.

        Returns:
            dict {equity, risk_pct, cb_factor, cached_symbols}
        """
        equity    = self._get_equity()
        cb_factor = self._cb.get_size_factor() if self._cb else 1.0

        return {
            "equity":          round(equity, 2),
            "risk_pct":        getattr(Risk, "DEFAULT_RISK_PCT", 1.0),
            "risk_amount":     round(
                                   equity *
                                   getattr(Risk, "DEFAULT_RISK_PCT", 1.0)
                                   / 100, 2
                               ),
            "cb_factor":       cb_factor,
            "effective_risk":  round(
                                   equity *
                                   getattr(Risk, "DEFAULT_RISK_PCT", 1.0)
                                   / 100 * cb_factor, 2
                               ),
            "cached_symbols":  list(self._symbol_cache.keys()),
        }

    def __repr__(self) -> str:
        equity = self._get_equity()
        return (
            f"CapitalAllocator("
            f"equity={equity:.2f}, "
            f"risk_pct={getattr(Risk, 'DEFAULT_RISK_PCT', 1.0)}%)"
        )
    def get_symbol_info(self, symbol: str):
        """Pour CapitalAllocator - retourne symbol_info."""
        if self.terminal is None:
            logger.warning(f"Terminal fermé pour {symbol}")
            return None
        info = self.terminal.symbol_info(symbol)
        logger.debug(f"Symbol_info {symbol}: {info.name if info else 'None'}")
        return info
