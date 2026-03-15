"""
datastore/data_store.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sentinel Pro KB5 — Source unique de vérité

Responsabilités :
- Bougies OHLCV par paire + TF (copie protégée)
- Ticks temps réel (deque circulaire O(1))
- Résultats analyse KB5 (FVG, OB, score, bias...)
- État KillSwitches + Circuit Breaker
- Cache positions/ordres (évite requêtes MT5 répétées)
- Métadonnées freshness par paire
- Statistiques DataStore pour Supervisor
- Purge et reset
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import os
import threading
import logging
from datetime import datetime
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class DataStore:
    """
    Source unique de vérité pour tout Sentinel Pro.
    Thread-safe via RLock — lecture et écriture concurrentes.

    Sections :
    1. Bougies       → OHLCV par paire + TF
    2. Ticks         → temps réel, deque circulaire
    3. Analyse       → résultats KB5 (FVG, OB, score...)
    4. KS / CB       → état KillSwitches + Circuit Breaker
    5. Positions     → cache snapshot OrderReader
    6. Métadonnées   → timestamps freshness
    7. Stats         → métriques Supervisor
    8. Purge / Reset
    """

    def __init__(
        self,
        max_ticks_per_pair: int = 1000,
        max_analysis_history: int = 50,
    ):
        self._lock = threading.RLock()

        # ── Section 1 : Bougies ───────────────
        # {pair: {tf: DataFrame}}
        self._candles: dict = defaultdict(dict)

        # ── Section 2 : Ticks ─────────────────
        # {pair: deque(maxlen=N)} — O(1) natif
        self._max_ticks        = max_ticks_per_pair
        self._ticks: dict      = defaultdict(
            lambda: deque(maxlen=max_ticks_per_pair)
        )

        # ── Section 3 : Résultats Analyse ─────
        # {pair: {tf: dernier_résultat}}
        self._analysis: dict   = defaultdict(dict)
        # {pair: deque(maxlen=N)} — historique
        self._analysis_history: dict = defaultdict(
            lambda: deque(maxlen=max_analysis_history)
        )

        # ── Section 4 : KS / CB ───────────────
        # État global — partagé par tous les modules
        self._ks_state: dict   = {}   # {ks_id: {active, reason, since}}
        self._cb_state: dict   = {
            "level":      0,           # 0=clear, 1=alert, 2=pause, 3=stop
            "status":     "CB_CLEAR",
            "triggered_at": None,
            "pct_drop":   0.0,
        }

        # ── Section 5 : Positions / Ordres ────
        # Cache dernier snapshot OrderReader
        self._positions_cache: list = []
        self._orders_cache:    list = []
        self._cache_updated_at: datetime | None = None

        # ── Section 5b : Equity ───────────────
        # Cache equity compte — mis à jour par CircuitBreaker/OrderReader
        self._equity: float = 0.0
        self._equity_updated_at: datetime | None = None

        # ── Section 6 : Métadonnées ───────────
        # {pair: {event: datetime}}
        self._metadata: dict   = defaultdict(dict)

        # ── Configuration Persistence ─────────
        self._storage_path = os.path.join("data", "datastore_state.json")
        os.makedirs("data", exist_ok=True)

        logger.info(
            f"DataStore initialisé — "
            f"max_ticks={max_ticks_per_pair} | "
            f"max_analysis={max_analysis_history}"
        )

        # Tenter le chargement au démarrage
        self.load_from_disk()

    # ══════════════════════════════════════════
    # SECTION 1 — BOUGIES
    # ══════════════════════════════════════════

    def set_candles(self, pair: str, timeframe: str, df):
        """
        Stocke les bougies d'une paire + TF.
        Écrase les données précédentes.
        """
        with self._lock:
            self._candles[pair][timeframe] = df
            self._touch(pair, f"candles_{timeframe}")
            logger.debug(
                f"Bougies stockées — {pair} {timeframe} : "
                f"{len(df)} bougies | "
                f"Dernière : {df.index[-1] if not df.empty else 'N/A'}"
            )

    def get_candles(self, pair: str, timeframe: str):
        """
        Retourne une COPIE du DataFrame.
        Protection contre modification externe.
        Retourne None si absent.
        """
        with self._lock:
            df = self._candles.get(pair, {}).get(timeframe)
            return df.copy() if df is not None else None

    def get_all_timeframes(self, pair: str) -> dict:
        """Retourne toutes les copies TF d'une paire."""
        with self._lock:
            tfs = self._candles.get(pair, {})
            return {tf: df.copy() for tf, df in tfs.items()}

    def has_candles(self, pair: str, timeframe: str) -> bool:
        with self._lock:
            df = self._candles.get(pair, {}).get(timeframe)
            return df is not None and not df.empty

    def get_candles_loaded_count(self, pair: str) -> int:
        """Nombre de TF chargés pour cette paire."""
        with self._lock:
            return len(self._candles.get(pair, {}))

    # ══════════════════════════════════════════
    # SECTION 2 — TICKS
    # ══════════════════════════════════════════

    def add_tick(self, tick_data: dict):
        """
        Ajoute un tick au buffer circulaire.
        deque(maxlen=N) → O(1), pas de recopie.
        """
        pair = tick_data.get("pair")
        if not pair:
            return
        with self._lock:
            self._ticks[pair].append(tick_data)
            self._touch(pair, "tick")

    def get_latest_tick(self, pair: str) -> dict:
        """Dernier tick reçu pour cette paire."""
        with self._lock:
            ticks = self._ticks.get(pair)
            if not ticks:
                return {}
            return dict(ticks[-1])

    def get_recent_ticks(self, pair: str, n: int = 10) -> list:
        """
        N derniers ticks.
        Utilisé par Anomaly Detector (spike, flash crash).
        """
        with self._lock:
            ticks = self._ticks.get(pair)
            if not ticks:
                return []
            return [dict(t) for t in list(ticks)[-n:]]

    def get_current_price(self, pair: str) -> float:
        """Prix bid actuel."""
        return self.get_latest_tick(pair).get("bid", 0.0)

    def get_current_ask(self, pair: str) -> float:
        """Prix ask actuel."""
        return self.get_latest_tick(pair).get("ask", 0.0)

    def get_current_spread(self, pair: str) -> float:
        """Spread actuel en pips — pour KS4."""
        return self.get_latest_tick(pair).get("spread", 0.0)

    def get_tick_count(self, pair: str) -> int:
        """Nombre de ticks en buffer."""
        with self._lock:
            return len(self._ticks.get(pair, []))

    # ══════════════════════════════════════════
    # SECTION 3 — RÉSULTATS ANALYSE KB5
    # ══════════════════════════════════════════

    def set_analysis(self, pair: str, timeframe: str, result: dict):
        """
        Stocke le dernier résultat d'analyse KB5.
        result contient : bias, score, FVG, OB, MSS,
                          verdict, ks_status, etc.
        """
        with self._lock:
            result["stored_at"] = datetime.utcnow()
            result["pair"]      = pair
            result["timeframe"] = timeframe
            self._analysis[pair][timeframe] = result
            self._analysis_history[pair].append(result)
            self._touch(pair, f"analysis_{timeframe}")
            
            # Auto-save pour les résultats persistants (Master Lists)
            self.save_to_disk()

            logger.debug(
                f"Analyse stockée — {pair} {timeframe} | "
                f"Score : {result.get('score', 'N/A')} | "
                f"Verdict : {result.get('verdict', 'N/A')}"
            )

    def get_analysis(self, pair: str, timeframe: str) -> dict:
        """Dernier résultat d'analyse pour paire + TF."""
        with self._lock:
            return dict(
                self._analysis.get(pair, {}).get(timeframe, {})
            )

    def get_analysis_history(self, pair: str, n: int = 10) -> list:
        """
        N dernières analyses pour cette paire (tous TF).
        Utilisé par Performance Memory.
        """
        with self._lock:
            history = self._analysis_history.get(pair)
            if not history:
                return []
            return [dict(r) for r in list(history)[-n:]]

    def get_latest_score(self, pair: str, timeframe: str) -> float:
        """Score KB5 le plus récent pour paire + TF."""
        analysis = self.get_analysis(pair, timeframe)
        return analysis.get("score", 0.0)

    def get_latest_verdict(self, pair: str, timeframe: str) -> str:
        """Verdict le plus récent : EXECUTE/WATCH/NO_TRADE."""
        analysis = self.get_analysis(pair, timeframe)
        return analysis.get("verdict", "NO_TRADE")

    def get_daily_bias(self, pair: str) -> str:
        """Daily bias stocké par Service Analyse."""
        analysis = self.get_analysis(pair, "D1")
        return analysis.get("bias", "NEUTRAL")

    # ══════════════════════════════════════════
    # SECTION 4 — KILLSWITCHES + CIRCUIT BREAKER
    # ══════════════════════════════════════════

    def set_ks_state(self, ks_id: int, active: bool, reason: str = ""):
        """
        Met à jour l'état d'un KillSwitch.
        Appelé par KillswitchEngine après chaque vérification.
        """
        with self._lock:
            self._ks_state[ks_id] = {
                "active":     active,
                "reason":     reason,
                "updated_at": datetime.utcnow(),
            }
            if active:
                logger.warning(
                    f"KS{ks_id} ACTIVÉ — Raison : {reason}"
                )

    def get_ks_state(self, ks_id: int) -> dict:
        """État d'un KillSwitch spécifique."""
        with self._lock:
            return dict(self._ks_state.get(ks_id, {
                "active": False,
                "reason": "",
                "updated_at": None,
            }))

    def is_any_ks_active(self) -> bool:
        """True si au moins un KillSwitch est actif."""
        with self._lock:
            return any(
                ks.get("active", False)
                for ks in self._ks_state.values()
            )

    def get_active_ks_list(self) -> list:
        """Liste des IDs de KillSwitches actifs."""
        with self._lock:
            return [
                ks_id for ks_id, state in self._ks_state.items()
                if state.get("active", False)
            ]

    def set_cb_state(
        self,
        level: int,
        status: str,
        pct_drop: float = 0.0
    ):
        """
        Met à jour l'état du Circuit Breaker.
        level : 0=clear, 1=alert, 2=pause, 3=stop
        """
        with self._lock:
            old_level = self._cb_state.get("level", 0)
            self._cb_state = {
                "level":        level,
                "status":       status,
                "pct_drop":     pct_drop,
                "triggered_at": datetime.utcnow() if level > 0 else None,
            }
            if level > old_level:
                logger.warning(
                    f"CIRCUIT BREAKER niveau {level} — "
                    f"Statut : {status} | "
                    f"Drop : {pct_drop:.2f}%"
                )

    def get_cb_state(self) -> dict:
        """État actuel du Circuit Breaker."""
        with self._lock:
            return dict(self._cb_state)

    def get_cb_level(self) -> int:
        """Niveau CB actuel (0-3)."""
        with self._lock:
            return self._cb_state.get("level", 0)

    def is_cb_blocking(self) -> bool:
        """True si CB niveau 2 ou 3 (bloque nouveaux trades)."""
        return self.get_cb_level() >= 2

    # ══════════════════════════════════════════
    # SECTION 5 — CACHE POSITIONS / ORDRES
    # ══════════════════════════════════════════

    def set_positions_cache(
        self,
        positions: list,
        orders: list
    ):
        """
        Met à jour le cache positions/ordres.
        Appelé par OrderReader toutes les N secondes.
        Évite N requêtes MT5 simultanées par les modules.
        """
        with self._lock:
            self._positions_cache  = positions
            self._orders_cache     = orders
            self._cache_updated_at = datetime.utcnow()

    def get_positions_cache(self) -> list:
        with self._lock:
            return list(self._positions_cache)

    def get_orders_cache(self) -> list:
        with self._lock:
            return list(self._orders_cache)

    def set_equity(self, equity: float) -> None:
        """
        Met à jour le cache d'equity compte.
        Appelé par CircuitBreaker ou OrderReader à chaque cycle.

        Args:
            equity: equity actuelle du compte en devise de base
        """
        with self._lock:
            self._equity             = float(equity)
            self._equity_updated_at  = datetime.utcnow()
        logger.debug(f"DataStore — Equity mise à jour : {equity:.2f}")

    def get_equity(self) -> float:
        """
        Retourne l'equity en cache.
        Priorité dans CapitalAllocator : MT5 direct > DataStore.get_equity() > 0.0

        Returns:
            float equity du compte, 0.0 si jamais initialisée
        """
        with self._lock:
            return self._equity

    def get_cache_age_sec(self) -> float:
        """Âge du cache positions en secondes."""
        with self._lock:
            if self._cache_updated_at is None:
                return float("inf")
            return (
                datetime.utcnow() - self._cache_updated_at
            ).total_seconds()

    # ══════════════════════════════════════════
    # SECTION 6 — MÉTADONNÉES / FRESHNESS
    # ══════════════════════════════════════════

    def _touch(self, pair: str, event: str):
        """Enregistre le timestamp d'une mise à jour."""
        self._metadata[pair][f"last_{event}"] = datetime.utcnow()

    def get_metadata(self, pair: str) -> dict:
        with self._lock:
            return dict(self._metadata.get(pair, {}))

    def is_fresh(
        self,
        pair: str,
        timeframe: str,
        max_age_sec: int = 60
    ) -> bool:
        """
        True si les bougies de cette paire/TF
        ont été mises à jour il y a moins de max_age_sec.
        """
        with self._lock:
            meta = self._metadata.get(pair, {})
            last = meta.get(f"last_candles_{timeframe}")
            if last is None:
                return False
            return (datetime.utcnow() - last).total_seconds() < max_age_sec

    def is_tick_fresh(self, pair: str, max_age_sec: int = 5) -> bool:
        """True si un tick a été reçu dans les dernières N secondes."""
        with self._lock:
            meta = self._metadata.get(pair, {})
            last = meta.get("last_tick")
            if last is None:
                return False
            return (datetime.utcnow() - last).total_seconds() < max_age_sec

    def get_stalest_pair(self, timeframe: str = "H1") -> str | None:
        """
        Retourne la paire dont les bougies sont les plus vieilles.
        Utilisé par Supervisor pour prioriser les mises à jour.
        """
        with self._lock:
            oldest_pair = None
            oldest_time = datetime.utcnow()
            for pair, meta in self._metadata.items():
                last = meta.get(f"last_candles_{timeframe}")
                if last and last < oldest_time:
                    oldest_time = last
                    oldest_pair = pair
            return oldest_pair

    # ══════════════════════════════════════════
    # SECTION 7 — STATISTIQUES SUPERVISOR
    # ══════════════════════════════════════════

    def get_all_pairs(self) -> list:
        with self._lock:
            pairs = (
                set(self._candles.keys()) |
                set(self._ticks.keys())   |
                set(self._analysis.keys())
            )
            return sorted(pairs)

    def get_stats(self) -> dict:
        """
        Métriques globales DataStore.
        Appelé par Supervisor pour monitoring.
        """
        with self._lock:
            pairs = self.get_all_pairs()
            return {
                "pairs_count":        len(pairs),
                "pairs":              pairs,
                "candles_loaded":     {
                    p: len(self._candles.get(p, {}))
                    for p in pairs
                },
                "tick_buffers":       {
                    p: len(self._ticks.get(p, []))
                    for p in pairs
                },
                "analysis_stored":    {
                    p: len(self._analysis.get(p, {}))
                    for p in pairs
                },
                "active_ks":          self.get_active_ks_list(),
                "cb_level":           self.get_cb_level(),
                "positions_cached":   len(self._positions_cache),
                "cache_age_sec":      round(self.get_cache_age_sec(), 1),
                "snapshot_at":        datetime.utcnow(),
            }

    # ══════════════════════════════════════════
    # SECTION 8 — PURGE / RESET
    # ══════════════════════════════════════════

    def purge_pair(self, pair: str):
        """
        Supprime toutes les données d'une paire.
        Utilisé lors du retrait d'une paire active.
        """
        with self._lock:
            self._candles.pop(pair, None)
            self._ticks.pop(pair, None)
            self._analysis.pop(pair, None)
            self._analysis_history.pop(pair, None)
            self._metadata.pop(pair, None)
            logger.info(f"DataStore — Données purgées pour {pair}")

    def purge_candles(self, pair: str, timeframe: str):
        """Purge uniquement un TF spécifique d'une paire."""
        with self._lock:
            if pair in self._candles:
                self._candles[pair].pop(timeframe, None)
            logger.debug(f"DataStore — Bougies {pair} {timeframe} purgées")

    def reset_ks(self):
        """Remet tous les KillSwitches à False."""
        with self._lock:
            self._ks_state.clear()
            logger.info("DataStore — KillSwitches réinitialisés.")

    def reset_cb(self):
        """Remet le Circuit Breaker au niveau 0."""
        with self._lock:
            self._cb_state = {
                "level":        0,
                "status":       "CB_CLEAR",
                "pct_drop":     0.0,
                "triggered_at": None,
            }
            logger.info("DataStore — Circuit Breaker réinitialisé.")

    def full_reset(self):
        """
        Reset complet — utilisé au redémarrage du bot.
        Conserve la structure mais vide toutes les données.
        """
        with self._lock:
            self._candles.clear()
            self._ticks.clear()
            self._analysis.clear()
            self._analysis_history.clear()
            self._metadata.clear()
            self._positions_cache.clear()
            self._orders_cache.clear()
            self._ks_state.clear()
            self.reset_cb()
            logger.warning("DataStore — Reset complet effectué.")

    # ══════════════════════════════════════════
    # PERSISTENCE DISQUE (Point 2.11)
    # ══════════════════════════════════════════

    def save_to_disk(self):
        """Sauvegarde l'état critique de l'analyse et métadonnées sur le disque."""
        try:
            with self._lock:
                state = {
                    "analysis": self._analysis,
                    "metadata": self._metadata,
                    "ks_state": self._ks_state,
                    "cb_state": self._cb_state,
                }
                
                with open(self._storage_path, "w", encoding="utf-8") as f:
                    json.dump(state, f, cls=DataStoreEncoder, indent=2)
                
                logger.debug(f"DataStore — État sauvegardé sur {self._storage_path}")
        except Exception as e:
            logger.error(f"DataStore — Erreur de sauvegarde disque : {e}")

    def load_from_disk(self):
        """Charge l'état depuis le disque si le fichier existe."""
        if not os.path.exists(self._storage_path):
            logger.info("DataStore — Aucun fichier de persistance trouvé.")
            return

        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            with self._lock:
                # Reconstruire les dictionnaires (json.load donne des dicts simples)
                # On met à jour les defaultdict existants
                if "analysis" in data:
                    for pair, tfs in data["analysis"].items():
                        for tf, res in tfs.items():
                            # Convertir timestamps ISO -> datetime
                            if "stored_at" in res and isinstance(res["stored_at"], str):
                                res["stored_at"] = datetime.fromisoformat(res["stored_at"])
                            self._analysis[pair][tf] = res

                if "metadata" in data:
                    for pair, events in data["metadata"].items():
                        for event, ts in events.items():
                            if isinstance(ts, str):
                                try:
                                    ts = datetime.fromisoformat(ts)
                                except: pass
                            self._metadata[pair][event] = ts

                if "ks_state" in data:
                    self._ks_state.update(data["ks_state"])

                if "cb_state" in data:
                    self._cb_state.update(data["cb_state"])

                logger.info(f"DataStore — État restauré depuis {self._storage_path}")
        except Exception as e:
            logger.error(f"DataStore — Erreur chargement disque : {e}")

    def __repr__(self):
        stats = self.get_stats()
        return (
            f"DataStore("
            f"pairs={stats['pairs_count']}, "
            f"cb_level={stats['cb_level']}, "
            f"active_ks={stats['active_ks']}"
            f")"
        )

# ══════════════════════════════════════════════════════════════
# UTILITAIRE : ENCODER JSON POUR DATETIME
# ══════════════════════════════════════════════════════════════

class DataStoreEncoder(json.JSONEncoder):
    """Permet de sérialiser les objets datetime en ISO format."""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)
