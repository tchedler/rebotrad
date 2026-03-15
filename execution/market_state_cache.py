"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Market State Cache (Thread-Safe)
══════════════════════════════════════════════════════════════
Responsabilités :
- Stocker l'état du marché partagé entre tous les threads
- Garantir les accès concurrents sans race condition
- Throttle 3s pour éviter les écritures trop fréquentes
- Utilisé par supervisor, dashboard et scoring_engine
══════════════════════════════════════════════════════════════
"""

import os
import time
import pickle
import logging
import threading

logger = logging.getLogger(__name__)

CACHE_FILE    = "market_state.pkl"
THROTTLE_SEC  = 3.0  # écriture max toutes les 3 secondes


class MarketStateCache:
    """
    Cache thread-safe de l'état du marché.
    Utilise os.replace() pour écriture atomique (pas de fichier corrompu).
    Utilise threading.RLock() pour accès concurrent sécurisé.
    """

    def __init__(self, cache_file: str = CACHE_FILE,
                 throttle_sec: float = THROTTLE_SEC):
        self._cache_file   = cache_file
        self._throttle_sec = throttle_sec
        self._lock         = threading.RLock()
        self._state: dict  = {}
        self._last_write   = 0.0
        logger.info("MarketStateCache initialisé — thread-safe prêt")

    # ══════════════════════════════════════════════════════════
    # LECTURE
    # ══════════════════════════════════════════════════════════

    def get(self, key: str, default=None):
        """Lecture thread-safe d'une clé."""
        with self._lock:
            return self._state.get(key, default)

    def get_all(self) -> dict:
        """Retourne une copie complète de l'état."""
        with self._lock:
            return dict(self._state)

    # ══════════════════════════════════════════════════════════
    # ÉCRITURE
    # ══════════════════════════════════════════════════════════

    def set(self, key: str, value) -> None:
        """Écriture thread-safe avec throttle."""
        with self._lock:
            self._state[key] = value
            self._flush_if_needed()

    def update(self, data: dict) -> None:
        """Met à jour plusieurs clés en une seule opération atomique."""
        with self._lock:
            self._state.update(data)
            self._flush_if_needed()

    # ══════════════════════════════════════════════════════════
    # PERSISTANCE
    # ══════════════════════════════════════════════════════════

    def _flush_if_needed(self) -> None:
        """Écrit sur disque si le throttle est dépassé."""
        now = time.time()
        if now - self._last_write >= self._throttle_sec:
            self._write_to_disk()
            self._last_write = now

    def _write_to_disk(self) -> None:
        """Écriture atomique via os.replace() — évite les corruptions."""
        tmp_file = self._cache_file + ".tmp"
        try:
            with open(tmp_file, "wb") as f:
                pickle.dump(self._state, f)
            os.replace(tmp_file, self._cache_file)
            logger.debug(f"MarketStateCache — flush disque OK "
                         f"({len(self._state)} clés)")
        except Exception as e:
            logger.error(f"MarketStateCache — erreur écriture : {e}")

    def load_from_disk(self) -> bool:
        """Charge l'état depuis le fichier pickle au démarrage."""
        if not os.path.exists(self._cache_file):
            logger.info("MarketStateCache — pas de cache disque, démarrage vierge")
            return False
        try:
            with self._lock:
                with open(self._cache_file, "rb") as f:
                    self._state = pickle.load(f)
            logger.info(f"MarketStateCache — chargé depuis disque "
                        f"({len(self._state)} clés)")
            return True
        except Exception as e:
            logger.error(f"MarketStateCache — erreur lecture disque : {e}")
            return False

    def clear(self) -> None:
        """Vide le cache en mémoire et sur disque."""
        with self._lock:
            self._state.clear()
            self._write_to_disk()
        logger.info("MarketStateCache — cache vidé")

    # ══════════════════════════════════════════════════════════
    # UTILITAIRES
    # ══════════════════════════════════════════════════════════

    def __repr__(self) -> str:
        with self._lock:
            return (f"MarketStateCache("
                    f"keys={list(self._state.keys())}, "
                    f"file='{self._cache_file}')")
