# datastore/priority_queue.py
# Sentinel Pro KB5 — File de Priorité Killzone
#
# Responsabilités :
# - File de priorité pour les paires actives selon la Killzone courante
# - Paires prioritaires traitées EN PREMIER par le Service Analyse
# - Priorité dynamique : change selon l'heure serveur MT5
# - Thread-safe
# - Statistiques pour Supervisor

import threading
import logging
from datetime import datetime, timezone
from queue import PriorityQueue as _PQ
from config.constants import KILLZONES, KILLZONE_PAIRS

logger = logging.getLogger(__name__)

# Niveaux de priorité (plus petit = traité en premier)
class Priority:
    KILLZONE_ACTIVE  = 1   # Paire dans la Killzone courante
    WATCH            = 2   # Paire surveillée hors Killzone
    IDLE             = 3   # Paire inactive / hors session


class KillzonePriorityQueue:
    """
    File de priorité dynamique basée sur les Killzones ICT.

    Principe :
    - À chaque cycle d'analyse, les paires sont ordonnées
      selon leur priorité dans la Killzone courante
    - Paires dans la Killzone active → Priority.KILLZONE_ACTIVE (1)
    - Autres paires actives          → Priority.WATCH (2)
    - Paires hors session            → Priority.IDLE (3)

    Killzones définies en UTC (depuis constants.py) :
      ASIA        : 00h–04h UTC
      LONDON_OPEN : 07h–10h UTC
      LONDON_CLOSE: 10h–12h UTC
      NY_OPEN     : 13h–16h UTC
      NY_CLOSE    : 19h–20h UTC

    Utilisation :
        kpq = KillzonePriorityQueue(connector)
        kpq.rebuild(active_pairs)         # reconstruire la file
        pair = kpq.get_next()             # paire la plus prioritaire
        kpq.task_done(pair)               # marquer traitement terminé
    """

    def __init__(self, connector=None):
        """
        Args:
            connector : MT5Connector — pour obtenir l'heure serveur UTC.
                        Si None, utilise l'heure locale UTC.
        """
        self.connector  = connector
        self._lock      = threading.RLock()
        self._queue     = _PQ()
        self._pairs_in  = set()    # paires actuellement dans la file

        # Stats
        self._rebuild_count  = 0
        self._last_rebuilt   = None
        self._current_kz     = None

    # ─────────────────────────────────────────────
    # HEURE SERVEUR
    # ─────────────────────────────────────────────

    def _get_server_time_utc(self) -> datetime:
        """
        Retourne l'heure serveur MT5 en UTC.
        Fallback sur l'heure locale UTC si connector indisponible.
        """
        if self.connector:
            try:
                t = self.connector.get_server_time()
                if t:
                    return t
            except Exception:
                pass
        return datetime.now(tz=timezone.utc).replace(tzinfo=None)

    # ─────────────────────────────────────────────
    # KILLZONE COURANTE
    # ─────────────────────────────────────────────

    def get_current_killzone(self, utc_hour: int = None) -> str | None:
        """
        Retourne le nom de la Killzone active à l'heure UTC donnée.
        Retourne None si aucune Killzone active.

        Killzones depuis constants.py :
            KILLZONES = {
                "ASIA":         {"start": 0,  "end": 4},
                "LONDON_OPEN":  {"start": 7,  "end": 10},
                "LONDON_CLOSE": {"start": 10, "end": 12},
                "NY_OPEN":      {"start": 13, "end": 16},
                "NY_CLOSE":     {"start": 19, "end": 20},
            }
        """
        if utc_hour is None:
            utc_hour = self._get_server_time_utc().hour

        for kz_name, kz_range in KILLZONES.items():
            if kz_range["start"] <= utc_hour < kz_range["end"]:
                return kz_name
        return None

    def get_killzone_pairs(self, killzone: str) -> list:
        """
        Retourne les paires prioritaires pour une Killzone donnée.
        Depuis KILLZONE_PAIRS dans constants.py.
        """
        return list(KILLZONE_PAIRS.get(killzone, []))

    # ─────────────────────────────────────────────
    # CONSTRUCTION DE LA FILE
    # ─────────────────────────────────────────────

    def rebuild(self, active_pairs: list):
        """
        Reconstruit la file de priorité selon la Killzone courante.
        À appeler :
        - Au démarrage
        - À chaque changement de Killzone (toutes les heures)
        - Après ajout/retrait d'une paire active

        Args:
            active_pairs : liste des paires actives configurées
        """
        with self._lock:
            # Vider la file
            self._queue = _PQ()
            self._pairs_in.clear()

            utc_now      = self._get_server_time_utc()
            utc_hour     = utc_now.hour
            current_kz   = self.get_current_killzone(utc_hour)
            kz_pairs     = self.get_killzone_pairs(current_kz) if current_kz else []

            self._current_kz = current_kz

            for pair in active_pairs:
                if pair in kz_pairs:
                    priority = Priority.KILLZONE_ACTIVE
                else:
                    priority = Priority.WATCH

                # PriorityQueue trie par (priority, pair)
                # pair en tie-breaker alphabétique
                self._queue.put((priority, pair))
                self._pairs_in.add(pair)

            self._rebuild_count += 1
            self._last_rebuilt   = utc_now

            logger.info(
                f"File priorité reconstruite — "
                f"KZ={current_kz or 'AUCUNE'} | "
                f"Paires KZ={kz_pairs} | "
                f"Total={len(active_pairs)} paires"
            )

    # ─────────────────────────────────────────────
    # CONSOMMATION DE LA FILE
    # ─────────────────────────────────────────────

    def get_next(self, timeout: float = 1.0) -> str | None:
        """
        Retourne la prochaine paire à analyser (priorité la plus haute).
        Bloque jusqu'à timeout si la file est vide.

        Returns:
            str  : nom de la paire (ex: "EURUSD")
            None : file vide ou timeout
        """
        try:
            priority, pair = self._queue.get(timeout=timeout)
            return pair
        except Exception:
            return None

    def get_all_ordered(self) -> list:
        """
        Retourne toutes les paires dans l'ordre de priorité.
        Non destructif — recrée la file après lecture.

        Utilisé par le Service Analyse pour itérer
        sur toutes les paires dans le bon ordre.
        """
        with self._lock:
            items = []
            temp  = []

            # Vider la file dans temp
            while not self._queue.empty():
                item = self._queue.get_nowait()
                temp.append(item)
                items.append(item[1])   # pair name

            # Remettre dans la file
            for item in temp:
                self._queue.put(item)

            return items

    def task_done(self, pair: str = None):
        """
        Marque la tâche comme terminée.
        Compatible avec PriorityQueue.task_done().
        """
        try:
            self._queue.task_done()
        except Exception:
            pass

    def is_empty(self) -> bool:
        """True si la file est vide."""
        return self._queue.empty()

    def size(self) -> int:
        """Nombre de paires dans la file."""
        return self._queue.qsize()

    # ─────────────────────────────────────────────
    # PRIORITÉ D'UNE PAIRE
    # ─────────────────────────────────────────────

    def get_pair_priority(self, pair: str) -> int:
        """
        Retourne le niveau de priorité actuel d'une paire.
        Utilisé par le Supervisor pour le monitoring.
        """
        with self._lock:
            kz_pairs = self.get_killzone_pairs(self._current_kz) \
                       if self._current_kz else []
            if pair in kz_pairs:
                return Priority.KILLZONE_ACTIVE
            if pair in self._pairs_in:
                return Priority.WATCH
            return Priority.IDLE

    def is_killzone_pair(self, pair: str) -> bool:
        """
        True si la paire est dans la Killzone active courante.
        Utilisé par KB5Engine pour le bonus de timing (+20 pts score).
        """
        with self._lock:
            kz_pairs = self.get_killzone_pairs(self._current_kz) \
                       if self._current_kz else []
            return pair in kz_pairs

    def get_priority_label(self, pair: str) -> str:
        """Label lisible de la priorité pour le Dashboard."""
        p = self.get_pair_priority(pair)
        return {
            Priority.KILLZONE_ACTIVE: "🔴 KILLZONE ACTIVE",
            Priority.WATCH:           "🟡 WATCH",
            Priority.IDLE:            "⚪ IDLE",
        }.get(p, "UNKNOWN")

    # ─────────────────────────────────────────────
    # AJOUT / RETRAIT DYNAMIQUE
    # ─────────────────────────────────────────────

    def add_pair(self, pair: str):
        """
        Ajoute une paire à la file en temps réel.
        Calcule sa priorité selon la Killzone courante.
        """
        with self._lock:
            if pair in self._pairs_in:
                return
            kz_pairs = self.get_killzone_pairs(self._current_kz) \
                       if self._current_kz else []
            priority = Priority.KILLZONE_ACTIVE if pair in kz_pairs \
                       else Priority.WATCH
            self._queue.put((priority, pair))
            self._pairs_in.add(pair)
            logger.debug(
                f"Paire ajoutée à la file : {pair} "
                f"[priorité={priority}]"
            )

    def remove_pair(self, pair: str):
        """
        Retire une paire de la file.
        Nécessite rebuild() pour effet immédiat
        car PriorityQueue ne supporte pas remove().
        """
        with self._lock:
            self._pairs_in.discard(pair)
            logger.debug(
                f"Paire retirée de la file : {pair} "
                f"— rebuild() requis pour effet immédiat."
            )

    # ─────────────────────────────────────────────
    # STATISTIQUES SUPERVISOR
    # ─────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Stats complètes pour le Supervisor/Dashboard."""
        with self._lock:
            server_time = self._get_server_time_utc()
            kz_pairs    = self.get_killzone_pairs(self._current_kz) \
                          if self._current_kz else []
            return {
                "current_killzone":    self._current_kz or "AUCUNE",
                "killzone_pairs":      kz_pairs,
                "queue_size":          self._queue.qsize(),
                "pairs_in_queue":      list(self._pairs_in),
                "rebuild_count":       self._rebuild_count,
                "last_rebuilt":        self._last_rebuilt,
                "server_time_utc":     server_time,
                "server_hour_utc":     server_time.hour,
                "next_killzone":       self._get_next_killzone(server_time.hour),
            }

    def get_ordered_summary(self) -> list:
        """
        Résumé ordonné de toutes les paires avec leur priorité.
        Format lisible pour le Dashboard Patron.
        """
        pairs = self.get_all_ordered()
        return [
            {
                "pair":     pair,
                "priority": self.get_pair_priority(pair),
                "label":    self.get_priority_label(pair),
            }
            for pair in pairs
        ]

    def _get_next_killzone(self, current_hour: int) -> dict:
        """
        Retourne la prochaine Killzone et dans combien d'heures.
        Utile pour le Dashboard — affichage countdown.
        """
        for kz_name, kz_range in KILLZONES.items():
            start = kz_range["start"]
            if start > current_hour:
                return {
                    "name":       kz_name,
                    "starts_at":  f"{start:02d}h UTC",
                    "in_hours":   start - current_hour,
                }
        # Si on est après NY_CLOSE → prochaine = ASIA demain
        asia = KILLZONES.get("ASIA", {})
        return {
            "name":      "ASIA",
            "starts_at": f"{asia.get('start', 0):02d}h UTC",
            "in_hours":  24 - current_hour + asia.get("start", 0),
        }

    def __repr__(self):
        return (
            f"KillzonePriorityQueue("
            f"kz={self._current_kz or 'NONE'} | "
            f"size={self._queue.qsize()} | "
            f"rebuilds={self._rebuild_count})"
        )
