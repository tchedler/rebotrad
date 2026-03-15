"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Performance Memory
══════════════════════════════════════════════════════════════
Responsabilités :
- Mémoriser les performances par setup (paire + session + zone)
- Appliquer un malus -10pts si le même setup a perdu 2x
- Réinitialiser le malus si le setup gagne 1 fois
- Permettre au bot de s'améliorer automatiquement
══════════════════════════════════════════════════════════════
"""

import logging
import threading
import json
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

MEMORY_FILE     = "learning/performance_memory.json"
MALUS_THRESHOLD = 2      # nb de pertes consécutives avant malus
MALUS_POINTS    = -10    # malus appliqué sur le score final


class PerformanceMemory:
    """
    Mémoire des performances par setup.
    Clé de setup = pair + session + pd_zone + trade_type
    """

    def __init__(self, memory_file: str = MEMORY_FILE):
        self._file   = memory_file
        self._lock   = threading.Lock()
        self._memory : dict = {}
        Path(memory_file).parent.mkdir(parents=True, exist_ok=True)
        self._load()
        logger.info("PerformanceMemory initialisé — "
                    f"{len(self._memory)} setups en mémoire")

    # ══════════════════════════════════════════════════════════
    # ENREGISTREMENT
    # ══════════════════════════════════════════════════════════

    def record(self, pair: str, session: str,
               pd_zone: str, trade_type: str,
               outcome: str) -> None:
        """
        Enregistre le résultat d'un trade pour un setup donné.

        Args:
            pair       : ex. "EURUSD"
            session    : "LONDON", "NEW_YORK", etc.
            pd_zone    : "PREMIUM", "DISCOUNT"
            trade_type : "SCALP", "INTRADAY", "SWING"
            outcome    : "WIN", "LOSS", "BE"
        """
        key = self._make_key(pair, session, pd_zone, trade_type)

        with self._lock:
            if key not in self._memory:
                self._memory[key] = {
                    "consecutive_losses" : 0,
                    "total_wins"         : 0,
                    "total_losses"       : 0,
                    "last_outcome"       : None,
                    "malus_active"       : False,
                    "last_updated"       : None,
                }

            entry = self._memory[key]

            if outcome == "WIN":
                entry["consecutive_losses"] = 0
                entry["total_wins"]        += 1
                entry["malus_active"]       = False
                logger.debug(f"PerformanceMemory — WIN "
                             f"{key} — malus désactivé")

            elif outcome == "LOSS":
                entry["consecutive_losses"] += 1
                entry["total_losses"]       += 1
                if entry["consecutive_losses"] >= MALUS_THRESHOLD:
                    entry["malus_active"] = True
                    logger.warning(
                        f"PerformanceMemory — MALUS activé "
                        f"{key} "
                        f"({entry['consecutive_losses']} pertes "
                        f"consécutives)"
                    )

            entry["last_outcome"]  = outcome
            entry["last_updated"]  = datetime.now(
                timezone.utc).isoformat()

            self._save()

    # ══════════════════════════════════════════════════════════
    # APPLICATION DU MALUS
    # ══════════════════════════════════════════════════════════

    def get_malus(self, pair: str, session: str,
                  pd_zone: str, trade_type: str) -> int:
        """
        Retourne le malus à appliquer sur le score final.

        Returns:
            int  0 si pas de malus, MALUS_POINTS (-10) si actif
        """
        key   = self._make_key(pair, session, pd_zone, trade_type)
        with self._lock:
            entry = self._memory.get(key, {})
            if entry.get("malus_active", False):
                logger.info(
                    f"PerformanceMemory — malus {MALUS_POINTS} "
                    f"appliqué sur {key}"
                )
                return MALUS_POINTS
            return 0

    def apply_malus(self, score: int, pair: str,
                    session: str, pd_zone: str,
                    trade_type: str) -> int:
        """
        Applique le malus directement sur un score.
        Appelé par scoring_engine après calcul du score final.

        Returns:
            int score après malus (min 0)
        """
        malus = self.get_malus(pair, session, pd_zone, trade_type)
        if malus < 0:
            new_score = max(score + malus, 0)
            logger.info(
                f"PerformanceMemory — score {score} → "
                f"{new_score} (malus {malus})"
            )
            return new_score
        return score

    # ══════════════════════════════════════════════════════════
    # PERSISTANCE JSON
    # ══════════════════════════════════════════════════════════

    def _save(self) -> None:
        """Sauvegarde la mémoire sur disque (JSON)."""
        try:
            tmp = self._file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._memory, f, indent=2)
            Path(tmp).replace(self._file)
        except Exception as e:
            logger.error(f"PerformanceMemory — erreur save : {e}")

    def _load(self) -> None:
        """Charge la mémoire depuis le disque."""
        try:
            if Path(self._file).exists():
                with open(self._file, "r", encoding="utf-8") as f:
                    self._memory = json.load(f)
        except Exception as e:
            logger.error(f"PerformanceMemory — erreur load : {e}")
            self._memory = {}

    # ══════════════════════════════════════════════════════════
    # UTILITAIRES
    # ══════════════════════════════════════════════════════════

    def _make_key(self, pair: str, session: str,
                  pd_zone: str, trade_type: str) -> str:
        return f"{pair}|{session}|{pd_zone}|{trade_type}"

    def get_snapshot(self) -> dict:
        """Snapshot pour Dashboard Patron."""
        with self._lock:
            active_malus = [
                k for k, v in self._memory.items()
                if v.get("malus_active")
            ]
            return {
                "total_setups"  : len(self._memory),
                "active_malus"  : active_malus,
                "malus_count"   : len(active_malus),
            }

    def reset(self, pair: str = None) -> None:
        """Remet à zéro la mémoire (par paire ou totale)."""
        with self._lock:
            if pair:
                keys = [k for k in self._memory if k.startswith(pair)]
                for k in keys:
                    del self._memory[k]
                logger.info(f"PerformanceMemory reset — {pair}")
            else:
                self._memory.clear()
                logger.info("PerformanceMemory reset — total")
            self._save()

    def __repr__(self) -> str:
        return (f"PerformanceMemory("
                f"setups={len(self._memory)}, "
                f"file='{self._file}')")
