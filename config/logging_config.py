# config/logging_config.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Configuration Logging Centralisée
══════════════════════════════════════════════════════════════
6 fichiers de log spécialisés + console colorée.
Chaque fichier cible un domaine précis pour faciliter
l'investigation sans chercher dans un fichier monolithique.

Usage dans chaque module :
  from config.logging_config import get_logger, log_trade,
                                    log_verdict, log_ks,
                                    log_cb, log_perf

  logger = get_logger(__name__)
══════════════════════════════════════════════════════════════
"""

import os
import sys
import json
import logging
import threading
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ══════════════════════════════════════════════════════════════
# CONSTANTES
# ══════════════════════════════════════════════════════════════

LOG_DIR         = Path(os.getenv("LOG_DIR", "logs"))
LOG_LEVEL_FILE  = logging.DEBUG
LOG_LEVEL_CON   = getattr(
    logging,
    os.getenv("LOG_LEVEL", "INFO").upper(),
    logging.INFO
)

# Taille max par fichier
MB = 1024 * 1024
LOG_SIZE = {
    "main":        50 * MB,
    "trades":       5 * MB,
    "verdicts":    20 * MB,
    "killswitches":10 * MB,
    "cb":           5 * MB,
    "errors":      20 * MB,
    "performance": 10 * MB,
}
LOG_BACKUPS = int(os.getenv("LOG_BACKUPS", "5"))

# ══════════════════════════════════════════════════════════════
# FORMATS
# ══════════════════════════════════════════════════════════════

FMT_FULL = (
    "%(asctime)s.%(msecs)03d | %(levelname)-8s | "
    "%(name)-35s | %(funcName)-25s | %(message)s"
)
FMT_SHORT = (
    "%(asctime)s | %(levelname)-8s | %(message)s"
)
FMT_JSON_FIELDS = [
    "asctime", "levelname", "name",
    "funcName", "message"
]
DATEFMT = "%Y-%m-%d %H:%M:%S"

# ══════════════════════════════════════════════════════════════
# FILTRE PAR MODULE (pour logs spécialisés)
# ══════════════════════════════════════════════════════════════

class ModuleFilter(logging.Filter):
    """Filtre les logs par préfixe de logger name."""

    def __init__(self, prefixes: list):
        super().__init__()
        self._prefixes = prefixes

    def filter(self, record: logging.LogRecord) -> bool:
        return any(
            record.name.startswith(p)
            for p in self._prefixes
        )


class LevelFilter(logging.Filter):
    """Filtre les logs par niveau exact ou minimum."""

    def __init__(self, min_level: int, max_level: int = None):
        super().__init__()
        self._min = min_level
        self._max = max_level or logging.CRITICAL

    def filter(self, record: logging.LogRecord) -> bool:
        return self._min <= record.levelno <= self._max


class MarkerFilter(logging.Filter):
    """
    Filtre les logs contenant un marqueur spécial.
    Utilisé pour les logs spécialisés (trades, verdicts, etc.)
    """

    def __init__(self, marker: str):
        super().__init__()
        self._marker = marker

    def filter(self, record: logging.LogRecord) -> bool:
        return self._marker in record.getMessage()

# ══════════════════════════════════════════════════════════════
# FORMATTER JSON (pour performance.log)
# ══════════════════════════════════════════════════════════════

class JSONFormatter(logging.Formatter):
    """
    Formatte les logs en JSON sur une ligne.
    Facilite l'ingestion par des outils d'analyse.
    """

    def format(self, record: logging.LogRecord) -> str:
        record.asctime = self.formatTime(record, DATEFMT)
        record.message = record.getMessage()

        data = {
            "ts":       record.asctime,
            "level":    record.levelname,
            "logger":   record.name,
            "fn":       record.funcName,
            "msg":      record.message,
        }

        # Ajouter les extra fields si présents
        extra_keys = [
            k for k in record.__dict__
            if k not in logging.LogRecord(
                "", 0, "", 0, "", (), None
            ).__dict__
            and not k.startswith("_")
            and k not in (
                "message", "asctime", "msecs",
                "relativeCreated", "thread",
                "threadName", "processName", "process"
            )
        ]
        for key in extra_keys:
            data[key] = getattr(record, key, None)

        try:
            return json.dumps(data, ensure_ascii=False,
                               default=str)
        except Exception:
            return json.dumps({"ts": record.asctime,
                               "msg": str(record.message)})

# ══════════════════════════════════════════════════════════════
# SETUP PRINCIPAL
# ══════════════════════════════════════════════════════════════

_setup_done = False
_setup_lock = threading.Lock()


def setup_logging() -> None:
    """
    Configure le système de logging complet.
    Idempotent — peut être appelé plusieurs fois sans effet.
    Doit être appelé une seule fois depuis main.py.
    """
    global _setup_done

    with _setup_lock:
        if _setup_done:
            return
        _setup_done = True

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # ── 1. Console colorée ──────────────────────────────────
    _add_console_handler(root)

    # ── 2. Log principal (tout) ─────────────────────────────
    _add_file_handler(
        root,
        name      = "main",
        filename  = LOG_DIR / "sentinel_kb5.log",
        level     = logging.DEBUG,
        formatter = logging.Formatter(FMT_FULL, DATEFMT),
        max_bytes = LOG_SIZE["main"],
    )

    # ── 3. Trades uniquement ────────────────────────────────
    _add_file_handler(
        root,
        name      = "trades",
        filename  = LOG_DIR / "trades.log",
        level     = logging.INFO,
        formatter = logging.Formatter(FMT_SHORT, DATEFMT),
        max_bytes = LOG_SIZE["trades"],
        filter_   = MarkerFilter("[TRADE]"),
    )

    # ── 4. Verdicts ─────────────────────────────────────────
    _add_file_handler(
        root,
        name      = "verdicts",
        filename  = LOG_DIR / "verdicts.log",
        level     = logging.INFO,
        formatter = logging.Formatter(FMT_SHORT, DATEFMT),
        max_bytes = LOG_SIZE["verdicts"],
        filter_   = MarkerFilter("[VERDICT]"),
    )

    # ── 5. KillSwitches ─────────────────────────────────────
    _add_file_handler(
        root,
        name      = "ks",
        filename  = LOG_DIR / "killswitches.log",
        level     = logging.INFO,
        formatter = logging.Formatter(FMT_SHORT, DATEFMT),
        max_bytes = LOG_SIZE["killswitches"],
        filter_   = MarkerFilter("[KS]"),
    )

    # ── 6. Circuit Breaker ───────────────────────────────────
    _add_file_handler(
        root,
        name      = "cb",
        filename  = LOG_DIR / "circuit_breaker.log",
        level     = logging.INFO,
        formatter = logging.Formatter(FMT_SHORT, DATEFMT),
        max_bytes = LOG_SIZE["cb"],
        filter_   = MarkerFilter("[CB]"),
    )

    # ── 7. Erreurs uniquement ────────────────────────────────
    _add_file_handler(
        root,
        name      = "errors",
        filename  = LOG_DIR / "errors.log",
        level     = logging.WARNING,
        formatter = logging.Formatter(FMT_FULL, DATEFMT),
        max_bytes = LOG_SIZE["errors"],
    )

    # ── 8. Performance JSON ──────────────────────────────────
    _add_file_handler(
        root,
        name      = "perf",
        filename  = LOG_DIR / "performance.log",
        level     = logging.INFO,
        formatter = JSONFormatter(),
        max_bytes = LOG_SIZE["performance"],
        filter_   = MarkerFilter("[PERF]"),
    )

    # ── Réduire les libs tierces ─────────────────────────────
    for noisy in [
        "urllib3", "asyncio",
        "MetaTrader5", "PIL"
    ]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        f"Logging configuré — "
        f"Dossier : {LOG_DIR.resolve()} | "
        f"Niveau console : {logging.getLevelName(LOG_LEVEL_CON)}"
    )


def _add_console_handler(root: logging.Logger) -> None:
    """Ajoute le handler console avec couleurs si disponible."""
    try:
        from colorlog import ColoredFormatter
        fmt = ColoredFormatter(
            "%(log_color)s%(asctime)s | %(levelname)-8s | "
            "%(name)-20s | %(message)s%(reset)s",
            datefmt=DATEFMT,
            log_colors={
                "DEBUG":    "cyan",
                "INFO":     "white",
                "WARNING":  "yellow",
                "ERROR":    "red,bold",
                "CRITICAL": "red,bg_white,bold",
            },
        )
    except ImportError:
        fmt = logging.Formatter(FMT_SHORT, DATEFMT)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(LOG_LEVEL_CON)
    ch.setFormatter(fmt)
    root.addHandler(ch)


def _add_file_handler(
    root:      logging.Logger,
    name:      str,
    filename:  Path,
    level:     int,
    formatter: logging.Formatter,
    max_bytes: int,
    filter_:   logging.Filter = None,
) -> None:
    """Crée et attache un RotatingFileHandler."""
    fh = RotatingFileHandler(
        filename,
        maxBytes    = max_bytes,
        backupCount = LOG_BACKUPS,
        encoding    = "utf-8",
    )
    fh.setLevel(level)
    fh.setFormatter(formatter)
    if filter_:
        fh.addFilter(filter_)
    root.addHandler(fh)

# ══════════════════════════════════════════════════════════════
# API PUBLIQUE — LOGGERS SPÉCIALISÉS
# ══════════════════════════════════════════════════════════════

def get_logger(name: str) -> logging.Logger:
    """
    Retourne un logger nommé.
    Usage standard dans chaque module :
      logger = get_logger(__name__)
    """
    return logging.getLogger(name)


def log_trade(action: str, pair: str,
               direction: str = "",
               ticket: int    = 0,
               lot: float     = 0.0,
               entry: float   = 0.0,
               sl: float      = 0.0,
               tp: float      = 0.0,
               pnl: float     = None,
               rr: float      = 0.0,
               score: int     = 0,
               grade: str     = "",
               reason: str    = "",
               **kwargs) -> None:
    """
    Log structuré pour les événements de trade.
    Écrit dans trades.log via le marqueur [TRADE].

    Actions standard :
      OPEN, CLOSE, PARTIAL_CLOSE, CANCEL,
      TRAIL_SL, MODIFY_SL, REJECTED

    Usage :
      log_trade("OPEN", "EURUSD", "BULLISH",
                ticket=12345, lot=0.05,
                entry=1.08500, sl=1.08200, tp=1.09100,
                rr=2.0, score=85, grade="A")
    """
    logger = logging.getLogger("trades")

    parts = [
        f"[TRADE] {action}",
        f"pair={pair}",
    ]
    if direction: parts.append(f"dir={direction}")
    if ticket:    parts.append(f"ticket={ticket}")
    if lot:       parts.append(f"lot={lot:.2f}")
    if entry:     parts.append(f"entry={entry}")
    if sl:        parts.append(f"sl={sl}")
    if tp:        parts.append(f"tp={tp}")
    if rr:        parts.append(f"rr={rr:.2f}")
    if pnl is not None:
                  parts.append(f"pnl={pnl:+.2f}")
    if score:     parts.append(f"score={score}")
    if grade:     parts.append(f"grade={grade}")
    if reason:    parts.append(f"reason={reason}")

    for k, v in kwargs.items():
        parts.append(f"{k}={v}")

    logger.info(" | ".join(parts))


def log_verdict(pair: str,
                verdict:   str,
                score:     int,
                grade:     str     = "",
                direction: str     = "",
                rr:        float   = 0.0,
                reason:    str     = "",
                override:  str     = "",
                confluences: list  = None,
                pyramid:   dict    = None,
                **kwargs) -> None:
    """
    Log structuré pour les verdicts de scoring.
    Écrit dans verdicts.log via le marqueur [VERDICT].

    Usage :
      log_verdict("EURUSD", "EXECUTE", 85, "A",
                  "BULLISH", 2.5,
                  pyramid={"MN":80,"W1":75,...})
    """
    logger = logging.getLogger("verdicts")

    parts = [
        f"[VERDICT] {verdict}",
        f"pair={pair}",
        f"score={score}",
    ]
    if grade:     parts.append(f"grade={grade}")
    if direction: parts.append(f"dir={direction}")
    if rr:        parts.append(f"rr={rr:.2f}")
    if reason:    parts.append(f"reason={reason}")
    if override:  parts.append(f"override={override}")

    if confluences:
        conf_str = ",".join(
            c.get("type", str(c)) if isinstance(c, dict)
            else str(c)
            for c in confluences
        )
        parts.append(f"confluences=[{conf_str}]")

    if pyramid:
        pyr_str = " ".join(
            f"{tf}:{v}" for tf, v in pyramid.items()
        )
        parts.append(f"pyramid=[{pyr_str}]")

    for k, v in kwargs.items():
        parts.append(f"{k}={v}")

    level = (
        logging.INFO    if verdict == "EXECUTE" else
        logging.INFO    if verdict == "WATCH"   else
        logging.DEBUG
    )
    logger.log(level, " | ".join(parts))


def log_ks(ks_id:   int,
            action:  str,
            pair:    str   = "",
            reason:  str   = "",
            value:   Any   = None,
            threshold: Any = None,
            **kwargs) -> None:
    """
    Log structuré pour les KillSwitches.
    Écrit dans killswitches.log via le marqueur [KS].

    Actions : ACTIVATED, DEACTIVATED, CHECKED_OK, FORCED

    Usage :
      log_ks(1, "ACTIVATED", "EURUSD",
             reason="Spread 3.5p > limite 2.0p",
             value=3.5, threshold=2.0)
    """
    logger = logging.getLogger("ks")

    parts = [
        f"[KS] KS{ks_id} {action}",
    ]
    if pair:      parts.append(f"pair={pair}")
    if reason:    parts.append(f"reason={reason}")
    if value is not None:
                  parts.append(f"value={value}")
    if threshold is not None:
                  parts.append(f"threshold={threshold}")

    for k, v in kwargs.items():
        parts.append(f"{k}={v}")

    level = (
        logging.WARNING if action == "ACTIVATED"  else
        logging.INFO    if action == "DEACTIVATED" else
        logging.DEBUG
    )
    logger.log(level, " | ".join(parts))


def log_cb(level_from: int,
            level_to:   int,
            action:     str,
            dd_pct:     float = 0.0,
            consec:     int   = 0,
            equity:     float = 0.0,
            reason:     str   = "",
            **kwargs) -> None:
    """
    Log structuré pour le Circuit Breaker.
    Écrit dans circuit_breaker.log via le marqueur [CB].

    Usage :
      log_cb(0, 1, "ESCALADE",
             dd_pct=-1.2, consec=2, equity=9876.50)
    """
    logger = logging.getLogger("cb")

    direction = "↑ ESCALADE" if level_to > level_from else "↓ RESET"
    cb_names  = {0:"NOMINAL", 1:"WARNING", 2:"PAUSE", 3:"HALT"}

    parts = [
        f"[CB] CB{level_from}→CB{level_to} "
        f"{direction} ({cb_names.get(level_to, '?')})",
        f"action={action}",
        f"dd={dd_pct:+.3f}%",
        f"consec={consec}",
        f"equity={equity:.2f}",
    ]
    if reason: parts.append(f"reason={reason}")

    for k, v in kwargs.items():
        parts.append(f"{k}={v}")

    log_level = (
        logging.CRITICAL if level_to >= 3 else
        logging.ERROR    if level_to == 2 else
        logging.WARNING  if level_to == 1 else
        logging.INFO
    )
    logger.log(log_level, " | ".join(parts))


def log_perf(event: str,
              pair:  str   = "",
              data:  dict  = None,
              **kwargs) -> None:
    """
    Log structuré JSON pour performance.log.
    Utilisé pour les statistiques périodiques
    et les métriques de cycle.

    Usage :
      log_perf("CYCLE_STATS",
               data={"execute": 3, "watch": 5,
                     "no_trade": 42, "equity": 10234.50})
    """
    logger = logging.getLogger("perf")

    payload = {
        "event": f"[PERF] {event}",
        "pair":  pair,
        "ts":    datetime.now(timezone.utc).isoformat(),
    }
    if data:
        payload.update(data)
    payload.update(kwargs)

    # Le JSONFormatter captera le message et les extras
    logger.info(
        f"[PERF] {event}",
        extra=payload
    )
