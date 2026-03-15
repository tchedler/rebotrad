"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Failure Lab
══════════════════════════════════════════════════════════════
Responsabilités :
- Analyser automatiquement les trades perdants
- Calculer le Gate Regret Rate quotidien
- Générer des leçons automatiques par catégorie d'erreur
- Alimenter performance_memory.py avec les malus

Gate Regret Rate :
  Si plus de 40% des trades du jour sont des erreurs évitables
  → alerte Patron + blocage préventif du lendemain
══════════════════════════════════════════════════════════════
"""

import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional
from learning.trade_journal import TradeJournal

logger = logging.getLogger(__name__)

# Seuils Gate Regret Rate
REGRET_RATE_WARNING = 0.30   # 30% → alerte jaune
REGRET_RATE_BLOCK   = 0.40   # 40% → blocage préventif

# Catégories d'erreurs "évitables" (les plus graves)
AVOIDABLE_ERRORS = {
    "FRIDAY_TRADE",
    "WRONG_BIAS",
    "BAD_TIMING",
    "WRONG_ZONE",
    "INDUCEMENT",
    "NO_DISPLACEMENT",
}

# Leçons automatiques par catégorie
LESSONS = {
    "FRIDAY_TRADE"    : "Ne jamais trader après 14h NY le vendredi. "
                        "Règle absolue ICT — le marché ferme tôt.",
    "WRONG_BIAS"      : "Vérifier l'alignement W+D+SOD avant toute entrée. "
                        "Le biais HTF est la fondation du setup.",
    "BAD_TIMING"      : "Attendre une Killzone ICT : London 02-05h NY, "
                        "NY 07-10h NY, ou une Macro confirmée.",
    "OVERTRADING"     : "Maximum 3 trades A+ par session. "
                        "Qualité > Quantité — ICT règle fondamentale.",
    "SL_TOO_TIGHT"    : "SL minimum 0.3 ATR H1 sous le swing low/high. "
                        "Un SL trop serré = stop prématuré garanti.",
    "INDUCEMENT"      : "Attendre le sweep de l'ERL AVANT l'entrée. "
                        "Le prix doit purger la liquidité en premier.",
    "REVENGE_TRADE"   : "Après 2 pertes consécutives → pause obligatoire. "
                        "Le revenge trading détruit les comptes.",
    "NO_DISPLACEMENT" : "Attendre une bougie de displacement M5/M1 (CISD). "
                        "Pas de displacement = pas d'entrée.",
    "WRONG_ZONE"      : "BULLISH en Discount uniquement (sous 50% du range). "
                        "BEARISH en Premium uniquement (au-dessus 50%).",
    "FRIDAY_TRADE"    : "Vendredi après 14h NY = risque maximal. "
                        "Les algorithmes ferment leurs positions.",
}


class FailureLab:
    """
    Laboratoire d'autopsie des pertes.
    Analyse les trades perdants et génère des leçons automatiques.
    """

    def __init__(self, trade_journal: TradeJournal,
                 datastore=None):
        self._journal   = trade_journal
        self._ds        = datastore
        self._lock      = threading.Lock()
        self._lessons   : list[dict] = []
        self._daily_report: Optional[dict] = None
        logger.info("FailureLab initialisé — autopsie des pertes prête")

    # ══════════════════════════════════════════════════════════
    # ANALYSE QUOTIDIENNE
    # ══════════════════════════════════════════════════════════

    def run_daily_autopsy(self) -> dict:
        """
        Lance l'autopsie quotidienne des trades perdants.
        Appelé par supervisor chaque jour à 00h05 UTC.

        Returns:
            dict {
                date, total_trades, losses, regret_rate,
                gate_triggered, lessons, top_error
            }
        """
        today  = datetime.now(timezone.utc).date()
        losses = self._journal.get_recent_losses(n=50)

        # Filtrer les trades du jour
        today_losses = [
            t for t in losses
            if t.get("close_time", "")[:10] == str(today)
        ]

        stats        = self._journal.get_stats(last_n=50)
        total_today  = stats.get("total", 0)
        loss_count   = len(today_losses)

        # Calculer le Regret Rate
        avoidable = [
            t for t in today_losses
            if t.get("error_category") in AVOIDABLE_ERRORS
        ]
        regret_rate = (len(avoidable) / total_today
                       if total_today > 0 else 0.0)

        # Gate Regret Rate
        gate_triggered = regret_rate >= REGRET_RATE_BLOCK
        gate_warning   = regret_rate >= REGRET_RATE_WARNING

        # Générer les leçons
        lessons = self._generate_lessons(today_losses)

        # Top erreur du jour
        error_counts = {}
        for t in today_losses:
            cat = t.get("error_category", "UNKNOWN")
            error_counts[cat] = error_counts.get(cat, 0) + 1
        top_error = max(error_counts, key=error_counts.get) \
                    if error_counts else "NONE"

        report = {
            "date"            : str(today),
            "total_trades"    : total_today,
            "losses"          : loss_count,
            "avoidable"       : len(avoidable),
            "regret_rate"     : round(regret_rate, 3),
            "gate_warning"    : gate_warning,
            "gate_triggered"  : gate_triggered,
            "top_error"       : top_error,
            "error_counts"    : error_counts,
            "lessons"         : lessons,
            "timestamp"       : datetime.now(timezone.utc).isoformat(),
        }

        with self._lock:
            self._daily_report = report

        if gate_triggered:
            logger.critical(
                f"FailureLab — GATE REGRET RATE DÉCLENCHÉ ! "
                f"Regret Rate={regret_rate:.0%} "
                f"≥ {REGRET_RATE_BLOCK:.0%} — "
                f"Blocage préventif activé pour demain"
            )
        elif gate_warning:
            logger.warning(
                f"FailureLab — Regret Rate élevé : "
                f"{regret_rate:.0%} ≥ {REGRET_RATE_WARNING:.0%}"
            )

        logger.info(
            f"FailureLab autopsie {today} — "
            f"Pertes:{loss_count} Évitables:{len(avoidable)} "
            f"RegretRate:{regret_rate:.0%} "
            f"TopErreur:{top_error}"
        )

        return report

    # ══════════════════════════════════════════════════════════
    # GÉNÉRATION DE LEÇONS
    # ══════════════════════════════════════════════════════════

    def _generate_lessons(self, losses: list) -> list:
        """Génère les leçons pour chaque erreur unique du jour."""
        seen     = set()
        lessons  = []
        for trade in losses:
            cat = trade.get("error_category", "UNKNOWN")
            if cat in seen or cat not in LESSONS:
                continue
            seen.add(cat)
            lessons.append({
                "category" : cat,
                "lesson"   : LESSONS[cat],
                "pair"     : trade.get("pair"),
                "pnl"      : trade.get("pnl"),
                "date"     : trade.get("close_time", "")[:10],
            })

        with self._lock:
            self._lessons.extend(lessons)
            if len(self._lessons) > 200:
                self._lessons = self._lessons[-200:]

        return lessons

    # ══════════════════════════════════════════════════════════
    # GATE REGRET RATE — Vérification temps réel
    # ══════════════════════════════════════════════════════════

    def is_gate_blocked(self) -> bool:
        """
        Retourne True si le Gate Regret Rate est déclenché.
        Appelé par scoring_engine avant chaque évaluation.
        """
        with self._lock:
            if not self._daily_report:
                return False
            report_date = self._daily_report.get("date", "")
            today       = str(datetime.now(timezone.utc).date())
            # Le gate s'applique seulement le jour du déclenchement
            if report_date != today:
                return False
            return self._daily_report.get("gate_triggered", False)

    def get_regret_rate(self) -> float:
        """Retourne le Regret Rate du jour."""
        with self._lock:
            if not self._daily_report:
                return 0.0
            return self._daily_report.get("regret_rate", 0.0)

    # ══════════════════════════════════════════════════════════
    # UTILITAIRES
    # ══════════════════════════════════════════════════════════

    def get_last_lessons(self, n: int = 5) -> list:
        """Retourne les N dernières leçons générées."""
        with self._lock:
            return list(self._lessons[-n:])

    def get_daily_report(self) -> Optional[dict]:
        """Retourne le dernier rapport quotidien."""
        with self._lock:
            return dict(self._daily_report) \
                   if self._daily_report else None

    def get_snapshot(self) -> dict:
        """Snapshot pour Dashboard Patron."""
        with self._lock:
            return {
                "regret_rate"    : self.get_regret_rate(),
                "gate_blocked"   : self.is_gate_blocked(),
                "last_lessons"   : self.get_last_lessons(3),
                "daily_report"   : self._daily_report,
            }

    def __repr__(self) -> str:
        return (f"FailureLab("
                f"gate={REGRET_RATE_BLOCK:.0%}, "
                f"lessons={len(self._lessons)})")
