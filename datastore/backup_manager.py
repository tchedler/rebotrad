# datastore/backup_manager.py
# Sentinel Pro KB5 — Sauvegarde Automatique DataStore
#
# Responsabilités :
# - Backup DataStore toutes les 5 min (configurable)
# - Backup JSON compressé (.gz) pour économiser l'espace
# - Rotation automatique : garder les N derniers backups
# - Backup immédiat sur demande (avant arrêt bot)
# - Restauration depuis le dernier backup valide
# - Thread dédié non-bloquant
# - Statistiques pour Supervisor

import os
import json
import gzip
import threading
import logging
from datetime import datetime
from pathlib import Path
from config.constants import DataStore as DS

logger = logging.getLogger(__name__)

# Valeurs par défaut si non définies dans constants.py
DEFAULT_BACKUP_DIR      = "backups"
DEFAULT_BACKUP_INTERVAL = 300    # 5 min
DEFAULT_MAX_BACKUPS     = 10     # garder les 10 derniers


class BackupManager:
    """
    Sauvegarde automatique périodique du DataStore.

    Format  : JSON compressé (.json.gz)
    Nommage : sentinel_backup_YYYYMMDD_HHMMSS.json.gz
    Rotation: les N derniers backups sont conservés

    Thread dédié — non bloquant pour le reste du bot.

    Séquence démarrage :
      1. start()   → lance le thread backup
      2. Thread attend BACKUP_INTERVAL sec
      3. backup_now() → sauvegarde + rotation

    Séquence arrêt :
      1. stop()    → signal arrêt propre
      2. backup_now() → sauvegarde finale avant extinction
    """

    def __init__(
        self,
        datastore,
        backup_dir:      str = None,
        interval_sec:    int = None,
        max_backups:     int = None,
    ):
        self.datastore    = datastore
        self.backup_dir   = Path(backup_dir or getattr(DS, "BACKUP_DIR", DEFAULT_BACKUP_DIR))
        self.interval_sec = interval_sec or getattr(DS, "BACKUP_INTERVAL_SEC", DEFAULT_BACKUP_INTERVAL)
        self.max_backups  = max_backups  or DEFAULT_MAX_BACKUPS

        self._stop_event  = threading.Event()
        self._thread      = None
        self._lock        = threading.Lock()

        # Statistiques
        self._backup_count    = 0
        self._last_backup_at  = None
        self._last_backup_file = None
        self._errors          = 0

        # Créer le répertoire backups si absent
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            f"BackupManager initialisé — "
            f"dir={self.backup_dir} | "
            f"interval={self.interval_sec}s | "
            f"max={self.max_backups} backups"
        )

    # ─────────────────────────────────────────────
    # DÉMARRAGE / ARRÊT
    # ─────────────────────────────────────────────

    def start(self):
        """Lance le thread de backup périodique."""
        if self._thread and self._thread.is_alive():
            logger.warning("BackupManager déjà en cours.")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._backup_loop,
            daemon=True,
            name="BackupManager"
        )
        self._thread.start()
        logger.info(f"BackupManager démarré — backup toutes les {self.interval_sec}s.")

    def stop(self):
        """
        Arrête le thread proprement.
        Effectue un backup final avant extinction.
        """
        logger.info("BackupManager — arrêt demandé. Backup final en cours...")
        self._stop_event.set()

        # Backup final avant extinction
        self.backup_now(label="SHUTDOWN")

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        logger.info("BackupManager arrêté.")

    # ─────────────────────────────────────────────
    # BOUCLE PRINCIPALE
    # ─────────────────────────────────────────────

    def _backup_loop(self):
        """
        Boucle périodique de backup.
        Attend INTERVAL sec entre chaque sauvegarde.
        Utilise stop_event.wait() pour réagir immédiatement à stop().
        """
        logger.debug("BackupManager — boucle démarrée.")
        while not self._stop_event.is_set():
            self._stop_event.wait(self.interval_sec)
            if self._stop_event.is_set():
                break
            self.backup_now()

    # ─────────────────────────────────────────────
    # BACKUP IMMÉDIAT
    # ─────────────────────────────────────────────

    def backup_now(self, label: str = "AUTO") -> str | None:
        """
        Effectue un backup immédiat du DataStore.
        Retourne le chemin du fichier créé, ou None si erreur.

        Args:
            label : tag dans le nom de fichier (AUTO / SHUTDOWN / MANUAL)
        """
        with self._lock:
            try:
                snapshot = self._get_snapshot()
                filepath = self._write_backup(snapshot, label)
                self._rotate_backups()

                self._backup_count   += 1
                self._last_backup_at  = datetime.utcnow()
                self._last_backup_file = filepath

                logger.info(
                    f"Backup {label} #{self._backup_count} → {filepath.name} "
                    f"({filepath.stat().st_size // 1024} KB)"
                )
                return str(filepath)

            except Exception as e:
                self._errors += 1
                logger.error(f"Backup échoué [{label}] : {e}")
                return None

    # ─────────────────────────────────────────────
    # SNAPSHOT DATASTORE
    # ─────────────────────────────────────────────

    def _get_snapshot(self) -> dict:
        """
        Extrait les données sérialisables du DataStore.

        On ne sauvegarde PAS :
        - Les DataFrames pandas (trop lourds, rechargés depuis MT5)
        - Les threads/locks internes

        On sauvegarde :
        - État KillSwitches
        - État Circuit Breaker
        - Cache positions/ordres
        - Métadonnées freshness
        - Stats globales
        """
        try:
            stats = self.datastore.get_stats()
            return {
                "snapshot_at":    datetime.utcnow().isoformat(),
                "ks_state":       self._serialize_ks(),
                "cb_state":       self._serialize_cb(),
                "positions_cache": self.datastore.get_positions_cache(),
                "orders_cache":    self.datastore.get_orders_cache(),
                "active_pairs":    stats.get("pairs", []),
                "stats":           stats,
            }
        except Exception as e:
            logger.warning(f"Snapshot partiel — certaines données manquantes : {e}")
            return {
                "snapshot_at": datetime.utcnow().isoformat(),
                "error": str(e),
            }

    def _serialize_ks(self) -> dict:
        """Sérialise l'état KillSwitches en JSON-safe."""
        result = {}
        try:
            for ks_id in range(1, 10):   # KS1 à KS9
                state = self.datastore.get_ks_state(ks_id)
                result[str(ks_id)] = {
                    "active":    state.get("active", False),
                    "reason":    state.get("reason", ""),
                    "updated_at": (
                        state["updated_at"].isoformat()
                        if state.get("updated_at") else None
                    ),
                }
        except Exception as e:
            logger.warning(f"Sérialisation KS échouée : {e}")
        return result

    def _serialize_cb(self) -> dict:
        """Sérialise l'état Circuit Breaker en JSON-safe."""
        try:
            cb = self.datastore.get_cb_state()
            triggered = cb.get("triggered_at")
            return {
                "level":        cb.get("level", 0),
                "status":       cb.get("status", "CB_CLEAR"),
                "pct_drop":     cb.get("pct_drop", 0.0),
                "triggered_at": triggered.isoformat() if triggered else None,
            }
        except Exception as e:
            logger.warning(f"Sérialisation CB échouée : {e}")
            return {}

    # ─────────────────────────────────────────────
    # ÉCRITURE FICHIER
    # ─────────────────────────────────────────────

    def _write_backup(self, snapshot: dict, label: str) -> Path:
        """
        Écrit le snapshot en JSON compressé (.json.gz).
        Compression gzip — ratio ~80% sur données JSON.
        """
        ts       = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"sentinel_backup_{label}_{ts}.json.gz"
        filepath = self.backup_dir / filename

        json_bytes = json.dumps(
            snapshot,
            indent=2,
            default=str,   # gère datetime, Path, etc.
            ensure_ascii=False
        ).encode("utf-8")

        with gzip.open(filepath, "wb") as f:
            f.write(json_bytes)

        return filepath

    # ─────────────────────────────────────────────
    # ROTATION AUTOMATIQUE
    # ─────────────────────────────────────────────

    def _rotate_backups(self):
        """
        Supprime les anciens backups pour ne garder
        que les MAX_BACKUPS derniers fichiers.
        Tri par date de modification — les plus anciens supprimés.
        """
        backups = sorted(
            self.backup_dir.glob("sentinel_backup_*.json.gz"),
            key=lambda f: f.stat().st_mtime
        )

        while len(backups) > self.max_backups:
            oldest = backups.pop(0)
            oldest.unlink()
            logger.debug(f"Backup supprimé (rotation) : {oldest.name}")

    # ─────────────────────────────────────────────
    # RESTAURATION
    # ─────────────────────────────────────────────

    def restore_latest(self) -> dict | None:
        """
        Charge le dernier backup valide.
        Utilisé au démarrage du bot pour restaurer
        l'état KS/CB sans attendre le premier cycle complet.

        Retourne le snapshot dict, ou None si aucun backup.
        """
        backups = sorted(
            self.backup_dir.glob("sentinel_backup_*.json.gz"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )

        for backup_file in backups:
            try:
                with gzip.open(backup_file, "rb") as f:
                    data = json.loads(f.read().decode("utf-8"))
                logger.info(f"Backup restauré depuis : {backup_file.name}")
                return data
            except Exception as e:
                logger.warning(f"Backup corrompu ignoré [{backup_file.name}] : {e}")

        logger.warning("Aucun backup valide trouvé.")
        return None

    def restore_ks_cb(self) -> bool:
        """
        Restaure uniquement l'état KS et CB dans le DataStore
        depuis le dernier backup.
        Appelé par main.py au démarrage.
        """
        snapshot = self.restore_latest()
        if not snapshot:
            return False

        try:
            # Restaurer KillSwitches
            ks_state = snapshot.get("ks_state", {})
            for ks_id_str, state in ks_state.items():
                self.datastore.set_ks_state(
                    ks_id=int(ks_id_str),
                    active=state.get("active", False),
                    reason=state.get("reason", "RESTORED")
                )

            # Restaurer Circuit Breaker
            cb_state = snapshot.get("cb_state", {})
            if cb_state:
                self.datastore.set_cb_state(
                    level=cb_state.get("level", 0),
                    status=cb_state.get("status", "CB_CLEAR"),
                    pct_drop=cb_state.get("pct_drop", 0.0)
                )

            logger.info(
                f"État KS/CB restauré depuis backup "
                f"[{snapshot.get('snapshot_at', 'inconnu')}]"
            )
            return True

        except Exception as e:
            logger.error(f"Restauration KS/CB échouée : {e}")
            return False

    # ─────────────────────────────────────────────
    # STATISTIQUES SUPERVISOR
    # ─────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Stats complètes pour le Supervisor/Dashboard."""
        backups = list(self.backup_dir.glob("sentinel_backup_*.json.gz"))
        total_size = sum(f.stat().st_size for f in backups)

        return {
            "backup_count":      self._backup_count,
            "last_backup_at":    self._last_backup_at,
            "last_backup_file":  self._last_backup_file,
            "errors":            self._errors,
            "interval_sec":      self.interval_sec,
            "backup_dir":        str(self.backup_dir),
            "files_on_disk":     len(backups),
            "max_backups":       self.max_backups,
            "total_size_kb":     round(total_size / 1024, 1),
            "is_running":        self._thread.is_alive() if self._thread else False,
        }

    def list_backups(self) -> list:
        """
        Liste tous les backups disponibles.
        Utile pour le Dashboard Patron.
        """
        backups = sorted(
            self.backup_dir.glob("sentinel_backup_*.json.gz"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )
        return [
            {
                "filename":  f.name,
                "size_kb":   round(f.stat().st_size / 1024, 1),
                "created_at": datetime.fromtimestamp(
                    f.stat().st_mtime
                ).strftime("%Y-%m-%d %H:%M:%S"),
            }
            for f in backups
        ]

    def __repr__(self):
        return (
            f"BackupManager("
            f"dir={self.backup_dir.name} | "
            f"count={self._backup_count} | "
            f"interval={self.interval_sec}s)"
        )
