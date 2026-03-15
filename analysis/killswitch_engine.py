# analysis/killswitch_engine.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Moteur KillSwitches (9 règles de sécurité)
══════════════════════════════════════════════════════════════
Responsabilités :
  - Évaluer les 9 KillSwitches en temps réel avant chaque trade
  - Distinguer KS BLOQUANT (NO-TRADE forcé) vs AVERTISSEMENT
  - Pousser l'état de chaque KS dans DataStore
  - Fournir un verdict global : ALL_CLEAR / BLOCKED / WARNING
  - Exposer get_ks_status() pour scoring_engine et Dashboard

Les 9 KillSwitches KB5 :
  KS1  — Spread excessif          → BLOQUANT
  KS2  — Volatilité extrême       → BLOQUANT
  KS3  — News haute impact        → BLOQUANT
  KS4  — Hors session / Killzone  → AVERTISSEMENT
  KS5  — Drawdown journalier max  → BLOQUANT
  KS6  — Contre-tendance HTF      → BLOQUANT
  KS7  — Trop de positions        → BLOQUANT
  KS8  — Corrélation déjà exposée → AVERTISSEMENT
  KS9  — Circuit Breaker actif    → BLOQUANT
  KS99 — Gateway déconnecté       → BLOQUANT (injecté extern.)

Dépendances :
  - DataStore      → get_candles(), set_ks_state(), get_ks_state()
  - TickReceiver   → get_latest_spread(), seconds_since_last_tick()
  - OrderReader    → get_exposure_summary(), get_open_positions()
  - BiasDetector   → is_aligned()
  - config.constants → Trading, Risk, Gateway

Consommé par :
  - scoring_engine.py   → verdict final
  - circuit_breaker.py  → KS9 synchronisation
  - supervisor.py       → monitoring global
  - patron_dashboard.py → affichage état KS
══════════════════════════════════════════════════════════════
"""

import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

from datastore.data_store import DataStore
from config.constants import Trading, Risk, Gateway

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# CONFIGURATION KS — depuis constants (pas de magic numbers)
# ══════════════════════════════════════════════════════════════

# Spread max par instrument (en pips)
SPREAD_LIMITS = {
    # Forex standard
    "EURUSD":  2.0,  "GBPUSD":  2.5,  "AUDUSD":  2.5,
    "USDCHF":  2.5,  "USDJPY":  2.0,  "USDCAD":  2.5,
    "NZDUSD":  2.5,

    # Forex 'm' — Exness
    "EURUSDm": 2.0,  "GBPUSDm": 2.5,  "AUDUSDm": 2.5,
    "USDCHFm": 2.5,  "USDJPYm": 2.0,  "USDCADm": 2.5,
    "NZDUSDm": 2.5,

    # Métaux
    "XAUUSD": 30.0,  "XAUUSDm": 30.0,
    "XAGUSD": 50.0,  "XAGUSDm": 50.0,

    # Énergie
    "USOIL":  10.0,  "USOILm": 10.0,
    "UKOIL":  10.0,  "UKOILm": 10.0,

    # Indices
    "US30":   15.0,  "NAS100": 10.0,
    "USTECm": 10.0,  "US500m":  5.0,
    "DE30m":  15.0,  "UK100m": 15.0,

    # Crypto
    "BTCUSD": 50.0,  "BTCUSDm": 50.0,
    "ETHUSD": 40.0,  "ETHUSDm": 40.0,

    # DXY
    "DXYm":    1.0,

    "DEFAULT": 3.0,   # fallback
}

ATR_VOLATILITY_FACTOR   = 3.0    # KS2 : ATR spike > 3× moyenne
ATR_PERIOD              = 14
ATR_SPIKE_LOOKBACK      = 5      # comparer dernier ATR vs 5 précédents

NEWS_WINDOW_MINUTES     = 30     # KS3 : ±30 min autour d'une news
MAX_OPEN_POSITIONS      = 99     # KS7 : max positions simultanées (DÉMO)
MAX_CORR_EXPOSURE       = 2      # KS8 : max 2 paires corrélées exposées

# KS9: Accumulation Logic (Dynamique)
ACCUMULATION_LOOKBACK   = 20     # Lookback pour range local (bougies M15)
IMPULSE_MULTIPLIER      = 1.5    # Facteur corps > moy. 5 pour breakout validé
IGNORE_TIME_FILTER      = True   # Autoriser KS9 breakout hors session (Crypto/Gold)

# Paires corrélées (même groupe = exposition commune)
CORR_GROUPS = {
    "USD_MAJORS": [
        "EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDJPY", "USDCAD", "NZDUSD",
        "EURUSDm", "GBPUSDm", "AUDUSDm", "USDCHFm", "USDJPYm", "USDCADm", "NZDUSDm",
    ],
    "INDICES": [
        "US30", "NAS100", "SPX500",
        "USTECm", "US500m", "DE30m", "UK100m",
    ],
    "COMMODITIES": [
        "XAUUSD", "USOIL", "UKOIL",
        "XAUUSDm", "XAGUSDm", "USOILm", "UKOILm",
    ],
    "CRYPTO": [
        "BTCUSD", "ETHUSD",
        "BTCUSDm", "ETHUSDm",
    ],
}

# Classification KS : BLOCKING vs WARNING
KS_BLOCKING  = {1, 2, 3, 5, 6, 7, 9, 99}
KS_WARNING   = {4, 8}

# ══════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════

class KillSwitchEngine:
    """
    Évalue les 9 KillSwitches de sécurité KB5 avant chaque trade.
    Un seul KS BLOQUANT suffit à annuler un setup quelle que soit
    la qualité du signal KB5.

    Hiérarchie de vérification (ordre d'importance) :
      KS99 → KS9 → KS5 → KS2 → KS1 → KS3 → KS6 → KS7 → KS4 → KS8
    """

    def __init__(self,
                 data_store: DataStore,
                 tick_receiver=None,
                 order_reader=None,
                 bias_detector=None):
        self._ds     = data_store
        self._ticks  = tick_receiver
        self._orders = order_reader
        self._bias   = bias_detector
        self._lock   = threading.Lock()

        # Cache news (liste de datetime UTC)
        self._news_calendar: list[datetime] = []

        # Cache état KS par paire
        self._ks_cache: dict[str, dict] = {}

        logger.info("KillSwitchEngine initialisé — 9 KS + KS99 prêts")

    def update_news_calendar(self, news_list: list):
        """
        Met à jour le calendrier des news haute importance.
        Appelé périodiquement par NewsManager.
        """
        with self._lock:
            self._news_calendar = news_list
            logger.info(f"KS3 — Calendrier mis à jour avec {len(news_list)} news HTF.")

    # ══════════════════════════════════════════════════════════
    # MÉTHODE PRINCIPALE — ÉVALUATION COMPLÈTE
    # ══════════════════════════════════════════════════════════

    def evaluate(self, pair: str, direction: str = None) -> dict:
        """
        Évalue tous les KillSwitches pour une paire en respectant
        l'ordre STRICT d'exécution de la doctrine KB5 (Cascade Short-Circuit).
        Dès qu'un filtre BLOCKING est actif, l'évaluation s'arrête
        immédiatement pour économiser du CPU.

        Ordre d'évaluation officiel :
        KS99 (Gateway) → KS5 (Drawdown) → KS3 (News) → KS7 (VIX)
        → KS6 (Corrélation) → KS1 (Spread) → KS2 (Volatilité)
        → KS8 (Session) → KS4 (Killzone) → KS9 (Accumulation)

        Returns:
            dict KSResult:
                verdict:   "ALL_CLEAR" / "WARNING" / "BLOCKED"
                blocked_by: [liste ID KS bloquants]
                warnings:   [liste ID KS avertissements]
                ks_details: {resultats des KS évalués}
                all_clear:  bool
        """
        now = datetime.now(timezone.utc)
        ks_details: dict[str, dict] = {}

        # ── Évaluation dans l'ordre de priorité ─────────────
        ks_details["ks99"] = self._check_ks99()
        ks_details["ks9"]  = self._check_ks9(pair, now)
        ks_details["ks5"]  = self._check_ks5(pair)
        ks_details["ks2"]  = self._check_ks2(pair)
        ks_details["ks1"]  = self._check_ks1(pair)
        ks_details["ks3"]  = self._check_ks3(pair, now)
        ks_details["ks6"]  = self._check_ks6(pair, direction)
        ks_details["ks7"]  = self._check_ks7(pair)
        ks_details["ks4"]  = self._check_ks4(now)
        ks_details["ks8"]  = self._check_ks8(pair)

        # ── Classifier bloquants vs avertissements ───────────
        blocked_by = []
        warnings   = []

        for ks_id_str, ks_result in ks_details.items():
            if not ks_result.get("active", False):
                continue

            ks_num = int(ks_id_str.replace("ks", ""))
            if ks_num in KS_BLOCKING:
                blocked_by.append(ks_id_str.upper())
            else:
                warnings.append(ks_id_str.upper())

        # ── Verdict global ──────────────────────────────────
        if blocked_by:
            verdict   = "BLOCKED"
            all_clear = False
        elif warnings:
            verdict   = "WARNING"
            all_clear = False
        else:
            verdict   = "ALL_CLEAR"
            all_clear = True

        # ── Pousser dans DataStore ───────────────────────────
        for ks_id_str, ks_result in ks_details.items():
            ks_num = int(ks_id_str.replace("ks", ""))
            self._ds.set_ks_state(
                ks_id=ks_num,
                active=ks_result.get("active", False),
                reason=ks_result.get("reason", "")
            )

        result = {
            "pair":       pair,
            "timestamp":  now.isoformat(),
            "verdict":    verdict,
            "all_clear":  all_clear,
            "blocked_by": blocked_by,
            "warnings":   warnings,
            "ks_details": ks_details,
        }

        with self._lock:
            self._ks_cache[pair] = result

        if not all_clear:
            logger.warning(
                f"KS évaluation — {pair} | "
                f"Verdict : {verdict} | "
                f"Bloqué par : {blocked_by} | "
                f"Warnings : {warnings}"
            )

        return result

    # ══════════════════════════════════════════════════════════
    # KS99 — GATEWAY DÉCONNECTÉ
    # ══════════════════════════════════════════════════════════

    def _check_ks99(self) -> dict:
        """
        KS99 — Gateway MT5 déconnecté.
        Injecté par ReconnectManager via DataStore.
        Vérifie l'état KS99 dans DataStore directement.

        Niveau : BLOQUANT — aucun ordre possible sans connexion.
        """
        ks99_state = self._ds.get_ks_state(ks_id=99)
        active     = ks99_state.get("active", False)

        return {
            "id":          99,
            "name":        "GATEWAY_DISCONNECT",
            "active":      active,
            "blocking":    True,
            "reason":      ks99_state.get("reason", "Gateway connecté") if active
                           else "Gateway connecté — OK",
            "value":       None,
            "threshold":   None,
        }

    # ══════════════════════════════════════════════════════════
    # KS9 — ACCUMULATION PHASE (DYNAMIC RANGE / SQUEEZE)
    # ══════════════════════════════════════════════════════════

    def _check_ks9(self, pair: str, now: datetime) -> dict:
        """
        KS9 — Phase Accumulation (Filtre dynamique).
        Anciennement Circuit Breaker, renommé selon audit.
        Détecte une compression de prix (range). Se bloque tant
        que le prix ne sort pas avec une bougie d'impulsion.

        Niveau : BLOQUANT — empêche le whipsaw en range mort.
        """
        # Utiliser M15 pour la vue fractale de l'accumulation
        df = self._ds.get_candles(pair, "M15")

        if df is None or len(df) < ACCUMULATION_LOOKBACK + 5:
            return self._ks_unavailable(9, "ACCUMULATION_BLOCK",
                                        "bougies M15 insuffisantes")

        # 1. Définir le Range d'Accumulation local (Lookback)
        lookback_df = df.iloc[-(ACCUMULATION_LOOKBACK+1):-1] # ignorer bougie en cours
        range_high  = lookback_df["high"].max()
        range_low   = lookback_df["low"].min()

        # 2. Vérifier "Sortie de Cage" de la bougie précédente (clôturée)
        last_closed = lookback_df.iloc[-1]
        
        # 3. Indice d'impulsion (Corps > Moyenne des 5 dernières)
        recent_bodies = [abs(row["close"] - row["open"]) for _, row in lookback_df.iloc[-6:-1].iterrows()]
        avg_body = sum(recent_bodies) / len(recent_bodies) if recent_bodies else 0
        current_body = abs(last_closed["close"] - last_closed["open"])
        
        is_impulse = current_body > (avg_body * IMPULSE_MULTIPLIER)

        # 4. Breakout validé ?
        breakout_up   = last_closed["close"] > range_high and is_impulse
        breakout_down = last_closed["close"] < range_low and is_impulse
        
        # Si True, on autorise, donc le KS (qui est un bloqueur) doit être inactif.
        # Donc "active = True" (Bloquant) si on N'EST PAS en breakout.
        active = not (breakout_up or breakout_down)

        # 5. Ignore Time Filter pour paires volatiles comme discuté
        # Si on est dans le cas Ignore, peu importe l'heure, 
        # C'est la structure M15 (le breakout de range) qui fait foi.
        in_asian_session = (now.hour >= 23 or now.hour < 8) # Grossièrement session asie
        is_crypto_gold = "XAU" in pair or "BTC" in pair or "ETH" in pair
        
        if is_crypto_gold and IGNORE_TIME_FILTER and not active:
             # On a cassé le range asiat sur l'or/crypto = KS9 désactivé IMMÉDIATEMENT = on trade
             pass 

        reason = "Phase Accumulation (Range serré sans impulsion)" if active else "Breakout validé (Fin d'accumulation)"

        return {
            "id":        9,
            "name":      "ACCUMULATION_BLOCK",
            "active":    active,
            "blocking":  True,
            "reason":    reason,
            "value":     round(current_body, 5),
            "threshold": round(avg_body * IMPULSE_MULTIPLIER, 5),
            "range_top": round(range_high, 5),
            "range_bot": round(range_low, 5)
        }

    # ══════════════════════════════════════════════════════════
    # KS5 — DRAWDOWN JOURNALIER MAX
    # ══════════════════════════════════════════════════════════

    def _check_ks5(self, pair: str) -> dict:
        """
        KS5 — Drawdown journalier dépasse le seuil configuré.
        Consulte l'exposition via OrderReader.

        Niveau : BLOQUANT — protection capital prioritaire.
        """
        if self._orders is None:
            return self._ks_unavailable(5, "DAILY_DRAWDOWN",
                                        "OrderReader non disponible")

        try:
            exposure = self._orders.get_exposure_summary()
            daily_pnl_pct = exposure.get("daily_pnl_pct", 0.0)
            max_dd        = getattr(Risk, "MAX_DAILY_DRAWDOWN_PCT", 2.0)
            active        = daily_pnl_pct <= -abs(max_dd)

            return {
                "id":        5,
                "name":      "DAILY_DRAWDOWN",
                "active":    active,
                "blocking":  True,
                "reason":    (
                    f"Drawdown journalier {daily_pnl_pct:.2f}% "
                    f"≥ max {max_dd}%" if active
                    else f"Drawdown journalier {daily_pnl_pct:.2f}% — OK"
                ),
                "value":     round(daily_pnl_pct, 3),
                "threshold": -abs(max_dd),
            }
        except Exception as e:
            logger.error(f"KS5 erreur : {e}")
            return self._ks_unavailable(5, "DAILY_DRAWDOWN", str(e))

    # ══════════════════════════════════════════════════════════
    # KS2 — VOLATILITÉ EXTRÊME
    # ══════════════════════════════════════════════════════════

    def _check_ks2(self, pair: str) -> dict:
        """
        KS2 — ATR actuel > ATR_VOLATILITY_FACTOR × ATR moyen.
        Détecte les spikes de volatilité (news non planifiées,
        flash crashes, ouvertures gap).

        Niveau : BLOQUANT — SL non garanti en volatilité extrême.
        """
        df = self._ds.get_candles(pair, "H1")
        if df is None or len(df) < ATR_PERIOD + ATR_SPIKE_LOOKBACK + 1:
            return self._ks_unavailable(2, "EXTREME_VOLATILITY",
                                        "bougies H1 insuffisantes")

        high  = df["high"].values
        low   = df["low"].values
        close = df["close"].values

        # Calculer ATR sur toute la fenêtre
        tr_list = [
            max(high[i] - low[i],
                abs(high[i]  - close[i - 1]),
                abs(low[i]   - close[i - 1]))
            for i in range(1, len(df))
        ]

        atr_recent  = tr_list[-1]                              # ATR dernière bougie
        atr_average = sum(tr_list[-(ATR_PERIOD + ATR_SPIKE_LOOKBACK):-ATR_SPIKE_LOOKBACK]) / ATR_PERIOD

        ratio  = atr_recent / atr_average if atr_average > 0 else 0
        active = ratio >= ATR_VOLATILITY_FACTOR

        if active:
            logger.warning(
                f"KS2 ACTIVÉ — {pair} | "
                f"ATR spike : {ratio:.1f}× moyenne | "
                f"ATR actuel : {atr_recent:.6f} | "
                f"ATR moyen : {atr_average:.6f}"
            )

        return {
            "id":        2,
            "name":      "EXTREME_VOLATILITY",
            "active":    active,
            "blocking":  True,
            "reason":    (
                f"ATR spike {ratio:.1f}× > seuil {ATR_VOLATILITY_FACTOR}×" if active
                else f"Volatilité normale {ratio:.1f}× — OK"
            ),
            "value":     round(ratio,       3),
            "threshold": ATR_VOLATILITY_FACTOR,
            "atr_now":   round(atr_recent,  6),
            "atr_avg":   round(atr_average, 6),
        }

    # ══════════════════════════════════════════════════════════
    # KS1 — SPREAD EXCESSIF
    # ══════════════════════════════════════════════════════════

    def _check_ks1(self, pair: str) -> dict:
        """
        KS1 — Spread actuel dépasse le seuil de la paire.
        Protège contre les entrées coûteuses en spread élargi
        (ouvertures, news, liquidité faible).

        Niveau : BLOQUANT — spread élevé annule l'edge ICT.
        """
        if self._ticks is None:
            return self._ks_unavailable(1, "SPREAD_EXCESSIVE",
                                        "TickReceiver non disponible")

        try:
            spread_pips = self._ticks.get_current_spread(pair)
            limit       = SPREAD_LIMITS.get(pair, SPREAD_LIMITS["DEFAULT"])
            active      = spread_pips > limit

            if active:
                logger.warning(
                    f"KS1 ACTIVÉ — {pair} | "
                    f"Spread : {spread_pips:.1f} pips > "
                    f"limite : {limit:.1f} pips"
                )

            return {
                "id":        1,
                "name":      "SPREAD_EXCESSIVE",
                "active":    active,
                "blocking":  True,
                "reason":    (
                    f"Spread {spread_pips:.1f}p > limite {limit:.1f}p" if active
                    else f"Spread {spread_pips:.1f}p — OK"
                ),
                "value":     round(spread_pips, 2),
                "threshold": limit,
            }
        except Exception as e:
            logger.error(f"KS1 erreur : {e}")
            return self._ks_unavailable(1, "SPREAD_EXCESSIVE", str(e))

    # ══════════════════════════════════════════════════════════
    # KS3 — NEWS HAUTE IMPACT
    # ══════════════════════════════════════════════════════════

    def _check_ks3(self, pair: str,
                   now: datetime) -> dict:
        """
        KS3 — News haute impact dans la fenêtre ±30 min.
        Vérifie le calendrier économique injecté via
        set_news_calendar().

        Niveau : BLOQUANT — slippage imprévisible sur news.
        """
        if not self._news_calendar:
            return {
                "id":       3,
                "name":     "HIGH_IMPACT_NEWS",
                "active":   False,
                "blocking": True,
                "reason":   "Calendrier news vide — OK (pas de vérification)",
                "value":    None,
                "threshold": NEWS_WINDOW_MINUTES,
            }

        window = timedelta(minutes=NEWS_WINDOW_MINUTES)
        upcoming_news = []
        
        # News impactant cette paire spécifiquement
        for n in self._news_calendar:
            # Calculer distance temporelle
            diff = abs((n['time'] - now).total_seconds())
            if diff <= window.total_seconds():
                # Vérifier si la news impacte les devises de la paire
                # Ex: EURUSD est impacté par EUR et USD
                news_currency = n.get('currency', 'ALL')
                if news_currency == 'ALL' or news_currency in pair:
                    upcoming_news.append(n)

        active      = len(upcoming_news) > 0
        next_news   = min(upcoming_news, default=None,
                          key=lambda n: abs((n['time'] - now).total_seconds()))
        minutes_to  = (
            round(abs((next_news['time'] - now).total_seconds()) / 60, 1)
            if next_news else None
        )

        if active:
            logger.warning(
                f"KS3 ACTIVÉ — {pair} | "
                f"News dans {minutes_to} min | "
                f"Nb news : {len(upcoming_news)}"
            )

        return {
            "id":        3,
            "name":      "HIGH_IMPACT_NEWS",
            "active":    active,
            "blocking":  True,
            "reason":    (
                f"News haute impact dans {minutes_to} min" if active
                else "Pas de news dans la fenêtre — OK"
            ),
            "value":     minutes_to,
            "threshold": NEWS_WINDOW_MINUTES,
            "news_count": len(upcoming_news),
        }

    # ══════════════════════════════════════════════════════════
    # KS6 — CONTRE-TENDANCE HTF
    # ══════════════════════════════════════════════════════════

    def _check_ks6(self, pair: str,
                   direction: Optional[str]) -> dict:
        """
        KS6 — Trade en direction opposée au biais HTF aligné.
        Vérifie l'alignement BiasDetector (Weekly+Daily+SOD).

        Niveau : BLOQUANT — trading contre le flux institutionnel.
        """
        if self._bias is None or direction is None:
            return self._ks_unavailable(6, "COUNTER_TREND_HTF",
                                        "BiasDetector ou direction absent")

        bias_direction = self._bias.get_direction(pair)
        bias_aligned   = self._bias.is_aligned(pair)

        # KS6 actif si : biais aligné ET direction opposée
        active = (
            bias_aligned and
            bias_direction != "NEUTRAL" and
            direction != bias_direction
        )

        if active:
            logger.warning(
                f"KS6 ACTIVÉ — {pair} | "
                f"Trade : {direction} | "
                f"Biais HTF : {bias_direction} | "
                f"Aligné : {bias_aligned}"
            )

        return {
            "id":            6,
            "name":          "COUNTER_TREND_HTF",
            "active":        active,
            "blocking":      True,
            "reason":        (
                f"Direction {direction} contre biais HTF {bias_direction}" if active
                else f"Aligné avec biais {bias_direction} — OK"
            ),
            "value":         direction,
            "threshold":     bias_direction,
            "bias_aligned":  bias_aligned,
        }

    # ══════════════════════════════════════════════════════════
    # KS7 — TROP DE POSITIONS OUVERTES
    # ══════════════════════════════════════════════════════════

    def _check_ks7(self, pair: str) -> dict:
        """
        KS7 — Nombre de positions ouvertes dépasse le maximum.
        Protège contre la sur-exposition simultanée du capital.

        Niveau : BLOQUANT — gestion du risque global.
        """
        if self._orders is None:
            return self._ks_unavailable(7, "MAX_POSITIONS",
                                        "OrderReader non disponible")

        try:
            positions   = self._orders.get_open_positions()
            open_count  = len([p for p in positions
                                if p.get("magic") == getattr(
                                    Trading, "BOT_MAGIC_NUMBER", 20260101
                                )])
            active = open_count >= MAX_OPEN_POSITIONS

            if active:
                logger.warning(
                    f"KS7 ACTIVÉ — {pair} | "
                    f"Positions ouvertes : {open_count} / {MAX_OPEN_POSITIONS}"
                )

            return {
                "id":        7,
                "name":      "MAX_POSITIONS",
                "active":    active,
                "blocking":  True,
                "reason":    (
                    f"{open_count} positions ≥ max {MAX_OPEN_POSITIONS}" if active
                    else f"{open_count} positions ouvertes — OK"
                ),
                "value":     open_count,
                "threshold": MAX_OPEN_POSITIONS,
            }
        except Exception as e:
            logger.error(f"KS7 erreur : {e}")
            return self._ks_unavailable(7, "MAX_POSITIONS", str(e))

    # ══════════════════════════════════════════════════════════
    # KS4 — HORS SESSION / KILLZONE
    # ══════════════════════════════════════════════════════════

    def _check_ks4(self, now: datetime) -> dict:
        """
        KS4 — Trading hors des heures de Killzone ICT.
        Avertissement seulement (le Patron peut override).

        Niveau : AVERTISSEMENT — pas de blocage dur,
        mais signal de sous-optimalité.
        """
        if self._bias is None:
            return self._ks_unavailable(4, "OUT_OF_SESSION",
                                        "BiasDetector non disponible")

        in_killzone = self._bias.is_in_killzone()
        active      = not in_killzone

        return {
            "id":        4,
            "name":      "OUT_OF_SESSION",
            "active":    False,
            "blocking":  False,   # KS4 desactive temporairement
            "reason":    (
                "Hors Killzone ICT — timing sous-optimal" if active
                else "Dans Killzone ICT — OK"
            ),
            "value":     in_killzone,
            "threshold": True,
        }

    # ══════════════════════════════════════════════════════════
    # KS8 — CORRÉLATION DÉJÀ EXPOSÉE
    # ══════════════════════════════════════════════════════════

    def _check_ks8(self, pair: str) -> dict:
        """
        KS8 — Une paire du même groupe de corrélation est déjà
        en position ouverte, risque de double exposition.

        Niveau : AVERTISSEMENT — pas de blocage dur,
        mais signal de sur-corrélation.
        """
        if self._orders is None:
            return self._ks_unavailable(8, "CORR_EXPOSURE",
                                        "OrderReader non disponible")

        try:
            # Trouver le groupe de corrélation de la paire
            pair_group  = None
            for group, members in CORR_GROUPS.items():
                if pair in members:
                    pair_group = group
                    break

            if pair_group is None:
                return {
                    "id": 8, "name": "CORR_EXPOSURE",
                    "active": False, "blocking": False,
                    "reason": f"{pair} hors groupe corrélation — OK",
                    "value": 0, "threshold": MAX_CORR_EXPOSURE,
                }

            # Compter les positions sur les paires du même groupe
            positions    = self._orders.get_open_positions()
            group_pairs  = CORR_GROUPS[pair_group]
            exposed_corr = [
                p for p in positions
                if p.get("symbol") in group_pairs
                and p.get("symbol") != pair
                and p.get("magic") == getattr(
                    Trading, "BOT_MAGIC_NUMBER", 20260101
                )
            ]

            active = len(exposed_corr) >= MAX_CORR_EXPOSURE

            if active:
                logger.warning(
                    f"KS8 ACTIVÉ — {pair} | "
                    f"Groupe : {pair_group} | "
                    f"Paires exposées : "
                    f"{[p['symbol'] for p in exposed_corr]}"
                )

            return {
                "id":          8,
                "name":        "CORR_EXPOSURE",
                "active":      active,
                "blocking":    False,   # AVERTISSEMENT
                "reason":      (
                    f"{len(exposed_corr)} paires corrélées exposées ({pair_group})"
                    if active else f"Exposition corrélée acceptable — OK"
                ),
                "value":       len(exposed_corr),
                "threshold":   MAX_CORR_EXPOSURE,
                "group":       pair_group,
                "exposed":     [p["symbol"] for p in exposed_corr],
            }
        except Exception as e:
            logger.error(f"KS8 erreur : {e}")
            return self._ks_unavailable(8, "CORR_EXPOSURE", str(e))

    # ══════════════════════════════════════════════════════════
    # UTILITAIRES INTERNES
    # ══════════════════════════════════════════════════════════

    def _ks_unavailable(self, ks_id: int, name: str,
                         reason: str) -> dict:
        """
        Retourne un état KS 'non disponible' standardisé.
        Un KS indisponible est considéré inactif (pas de blocage
        par manque de données) mais loggé.
        """
        logger.debug(f"KS{ks_id} non évaluable — {reason}")
        return {
            "id":        ks_id,
            "name":      name,
            "active":    False,
            "blocking":  ks_id in KS_BLOCKING,
            "reason":    f"Non évaluable : {reason}",
            "value":     None,
            "threshold": None,
            "unavailable": True,
        }

    # ══════════════════════════════════════════════════════════
    # GESTION CALENDRIER NEWS
    # ══════════════════════════════════════════════════════════

    def set_news_calendar(self, news_events: list[datetime]) -> None:
        """
        Injecte le calendrier des news haute impact.
        Appelé par supervisor.py en début de session.

        Args:
            news_events: liste de datetime UTC des news haute impact
        """
        with self._lock:
            self._news_calendar = sorted(news_events)
        logger.info(
            f"Calendrier news mis à jour — "
            f"{len(news_events)} événements chargés"
        )

    def add_news_event(self, event_time: datetime) -> None:
        """
        Ajoute un événement news en temps réel.
        Utilisé pour les news inattendues (ex: FED surprise).
        """
        with self._lock:
            self._news_calendar.append(event_time)
            self._news_calendar.sort()
        logger.warning(
            f"News urgente ajoutée — "
            f"Heure : {event_time.isoformat()}"
        )

    def clear_past_news(self) -> None:
        """
        Purge les news passées du calendrier.
        Appelé chaque heure par supervisor.py.
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            before = len(self._news_calendar)
            self._news_calendar = [
                n for n in self._news_calendar if n > now
            ]
            after = len(self._news_calendar)
        logger.debug(
            f"News purgées — {before - after} supprimées, "
            f"{after} restantes"
        )

    # ══════════════════════════════════════════════════════════
    # API PUBLIQUE
    # ══════════════════════════════════════════════════════════

    def is_all_clear(self, pair: str,
                     direction: str = None) -> bool:
        """
        Vérification rapide : aucun KS bloquant actif.
        Raccourci pour scoring_engine.

        Returns:
            True si ALL_CLEAR
        """
        result = self.evaluate(pair, direction)
        return result["all_clear"]

    def get_blocking_ks(self, pair: str) -> list:
        """
        Retourne la liste des KS bloquants actifs.
        Utilisé par scoring_engine pour la raison NO-TRADE.

        Returns:
            liste de str ex. ["KS1", "KS3"]
        """
        with self._lock:
            cached = self._ks_cache.get(pair, {})
        return cached.get("blocked_by", [])

    def get_ks_status(self, pair: str) -> dict:
        """
        Retourne le dernier KSResult complet pour une paire.

        Returns:
            dict KSResult ou dict vide
        """
        with self._lock:
            return dict(self._ks_cache.get(pair, {}))

    def get_global_status(self) -> dict:
        """
        Résumé global de tous les KS pour toutes les paires.
        Consommé par supervisor.py et Dashboard Patron.

        Returns:
            dict {pair: verdict} pour toutes les paires
        """
        with self._lock:
            return {
                pair: {
                    "verdict":    result.get("verdict"),
                    "blocked_by": result.get("blocked_by", []),
                    "warnings":   result.get("warnings",   []),
                }
                for pair, result in self._ks_cache.items()
            }

    def get_snapshot(self, pair: str) -> dict:
        """
        Snapshot compact pour Dashboard Patron.

        Returns:
            dict {pair, verdict, blocked_by, warnings, ks_count}
        """
        with self._lock:
            result = dict(self._ks_cache.get(pair, {}))

        if not result:
            return {"pair": pair, "status": "non évalué"}

        active_ks = [
            k for k, v in result.get("ks_details", {}).items()
            if v.get("active", False)
        ]

        return {
            "pair":       pair,
            "verdict":    result.get("verdict"),
            "all_clear":  result.get("all_clear"),
            "blocked_by": result.get("blocked_by", []),
            "warnings":   result.get("warnings",   []),
            "active_ks":  active_ks,
            "ks_count":   len(active_ks),
            "timestamp":  result.get("timestamp"),
        }

    def force_ks(self, ks_id: int, reason: str) -> None:
        """
        Force l'activation d'un KS manuellement.
        Utilisé par Patron via Dashboard pour override manuel.

        Args:
            ks_id:  numéro KS (1-9 ou 99)
            reason: raison textuelle
        """
        self._ds.set_ks_state(ks_id=ks_id, active=True, reason=reason)
        logger.warning(
            f"KS{ks_id} FORCÉ MANUELLEMENT — Raison : {reason}"
        )

    def clear_ks(self, ks_id: int) -> None:
        """
        Désactive manuellement un KS.
        Utilisé par Patron ou ReconnectManager (KS99 après reconnexion).

        Args:
            ks_id: numéro KS à désactiver
        """
        self._ds.set_ks_state(ks_id=ks_id, active=False,
                               reason="Désactivé manuellement")
        logger.info(f"KS{ks_id} désactivé manuellement")

    def __repr__(self) -> str:
        pairs   = list(self._ks_cache.keys())
        blocked = sum(
            1 for r in self._ks_cache.values()
            if r.get("verdict") == "BLOCKED"
        )
        return (
            f"KillSwitchEngine("
            f"pairs={pairs}, "
            f"blocked={blocked}/{len(pairs)})"
        )
