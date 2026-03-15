# dashboard/patron_dashboard.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Dashboard Patron (Interface Temps Réel)
══════════════════════════════════════════════════════════════
Responsabilités :
  - Afficher l'état complet du bot en temps réel (rich)
  - Montrer les verdicts + scores + pyramide par paire
  - Afficher les KillSwitches actifs + Circuit Breaker
  - Lister les positions ouvertes avec PnL live
  - Fournir les contrôles manuels Patron
  - Alerter sur WATCH + anomalies critiques
  - Logger l'historique des verdicts pour audit

Sections du Dashboard :
  ┌─ HEADER ─────────────────────────────────────────────┐
  │ Bot status | Session | Equity | CB level | DD%       │
  ├─ VERDICTS ────────────────────────────────────────────┤
  │ Paire | Direction | Score | Grade | Verdict | RR     │
  ├─ KILLSWITCHES ────────────────────────────────────────┤
  │ KS1..KS9+KS99 | État | Raison par paire             │
  ├─ POSITIONS ───────────────────────────────────────────┤
  │ Ticket | Paire | Dir | Entry | SL | TP | PnL | ATR  │
  ├─ PYRAMIDE ────────────────────────────────────────────┤
  │ MN | W1 | D1 | H4 | H1 | M15 scores par paire       │
  └─ HISTORIQUE ──────────────────────────────────────────┘
    Derniers 10 verdicts avec raisons

Dépendances :
  - Supervisor       → get_global_status(), pause(), resume()
  - OrderManager     → get_snapshot()
  - ScoringEngine    → get_all_verdicts(), get_statistics()
  - KillSwitchEngine → get_global_status()
  - CircuitBreaker   → get_snapshot()
  - OrderReader      → get_open_positions()
  - rich             → Console, Live, Table, Panel, Text

Consommé par :
  - main.py → dashboard.start() en thread séparé
══════════════════════════════════════════════════════════════
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# IMPORT RICH (avec fallback gracieux si non installé)
# ══════════════════════════════════════════════════════════════

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.layout import Layout
    from rich.live import Live
    from rich.columns import Columns
    from rich.rule import Rule
    from rich.align import Align
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    logger.warning(
        "Dashboard — rich non installé. "
        "Installer avec : pip install rich"
    )

# ══════════════════════════════════════════════════════════════
# CONSTANTES
# ══════════════════════════════════════════════════════════════

REFRESH_INTERVAL_SEC = 5     # refresh dashboard toutes les 5s
HISTORY_MAX_DISPLAY  = 10    # max verdicts affichés en historique
ALERT_COOLDOWN_SEC   = 60    # min entre 2 alertes identiques

# Couleurs par verdict
VERDICT_COLORS = {
    "EXECUTE":  "bold green",
    "WATCH":    "bold yellow",
    "NO_TRADE": "dim red",
    "UNKNOWN":  "dim white",
}

# Couleurs par grade
GRADE_COLORS = {
    "A+": "bold bright_green",
    "A":  "green",
    "A-": "green",
    "B+": "yellow",
    "B":  "yellow",
    "B-": "dim yellow",
    "C":  "dim red",
}

# Couleurs CB niveau
CB_COLORS = {
    0: "bold green",
    1: "bold yellow",
    2: "bold red",
    3: "bold bright_red",
}

# Couleurs KS
KS_ACTIVE_COLOR   = "bold red"
KS_INACTIVE_COLOR = "dim green"
KS_WARNING_COLOR  = "bold yellow"

# ══════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════

class PatronDashboard:
    """
    Interface temps réel pour le Patron de SENTINEL PRO KB5.
    Affiche l'état complet du bot dans le terminal via rich.

    Deux modes :
      - LIVE : refresh automatique toutes les N secondes
      - STATIC : affichage unique sur demande (debug)
    """

    def __init__(self,
                 supervisor=None,
                 scoring_engine=None,
                 killswitch_engine=None,
                 circuit_breaker=None,
                 order_manager=None,
                 order_reader=None):
        self._supervisor = supervisor
        self._scoring    = scoring_engine
        self._ks         = killswitch_engine
        self._cb         = circuit_breaker
        self._orders     = order_manager
        self._reader     = order_reader

        self._console    = Console() if RICH_AVAILABLE else None
        self._lock       = threading.Lock()
        self._running    = False
        self._shutdown   = threading.Event()

        # Historique alertes (anti-flood)
        self._alert_history: dict[str, float] = {}

        # Buffer historique verdicts pour affichage
        self._verdict_buffer: list[dict] = []

        logger.info(
            f"PatronDashboard initialisé | "
            f"Rich : {'disponible' if RICH_AVAILABLE else 'ABSENT'}"
        )

    # ══════════════════════════════════════════════════════════
    # DÉMARRAGE
    # ══════════════════════════════════════════════════════════

    def start(self, live: bool = True) -> None:
        """
        Démarre le dashboard en mode LIVE ou STATIC.
        Appelé par main.py dans un thread séparé.

        Args:
            live: True = refresh auto, False = affichage unique
        """
        if not RICH_AVAILABLE:
            logger.warning(
                "Dashboard — Impossible de démarrer sans rich"
            )
            self._fallback_loop()
            return

        self._running = True

        if live:
            self._start_live()
        else:
            self._render_static()

    def _start_live(self) -> None:
        """
        Mode LIVE : refresh automatique toutes les N secondes.
        Utilise rich.Live pour un rendu fluide.
        """
        try:
            with Live(
                self._build_layout(),
                console=self._console,
                refresh_per_second=1,
                screen=True
            ) as live_display:

                while (self._running and
                       not self._shutdown.is_set()):
                    try:
                        live_display.update(self._build_layout())
                    except Exception as e:
                        logger.error(
                            f"Dashboard — Erreur refresh : {e}"
                        )
                    time.sleep(REFRESH_INTERVAL_SEC)

        except Exception as e:
            logger.error(
                f"Dashboard — Erreur live : {e}"
            )

    def stop(self) -> None:
        """Arrête le dashboard."""
        self._running = False
        self._shutdown.set()
        logger.info("PatronDashboard arrêté")

    # ══════════════════════════════════════════════════════════
    # CONSTRUCTION LAYOUT PRINCIPAL
    # ══════════════════════════════════════════════════════════

    def _build_layout(self):
        """
        Construit le layout complet du dashboard.
        Appelé à chaque refresh.

        Returns:
            rich renderable (Layout ou Columns)
        """
        try:
            status = self._get_status()

            sections = [
                self._build_header(status),
                self._build_verdicts_table(status),
                self._build_ks_table(status),
                self._build_positions_table(),
                self._build_pyramid_table(status),
                self._build_history_table(status),
                self._build_stats_panel(status),
            ]

            # Filtrer les None (sections indisponibles)
            rendered = [s for s in sections if s is not None]

            from rich.console import Group
            return Panel(
                Group(*rendered),
                title=(
                    "[bold cyan]SENTINEL PRO KB5[/] — "
                    + datetime.now(timezone.utc)
                    .strftime('%H:%M:%S')
                    + " UTC"
                ),
                border_style="cyan",
            )

        except Exception as e:
            logger.error(f"Dashboard — build_layout erreur : {e}")
            return Panel(
                Text(f"Erreur dashboard : {e}", style="red"),
                title="SENTINEL PRO KB5 — ERREUR",
                border_style="red",
            )

    # ══════════════════════════════════════════════════════════
    # SECTION HEADER
    # ══════════════════════════════════════════════════════════

    def _build_header(self, status: dict):
        """
        Header : statut bot | session | equity | CB | DD%
        """
        snap   = status.get("snapshot", {})
        cb     = status.get("cb",       {})

        running   = snap.get("running", False)
        paused    = snap.get("paused",  False)
        session   = snap.get("session", "?")
        equity    = snap.get("equity",  0.0)
        cb_level  = cb.get("level",     0)
        cb_name   = cb.get("name",      "?")
        dd_pct    = cb.get("dd_pct",    0.0)
        cycles    = snap.get("cycles",  0)
        executes  = snap.get("execute", 0)

        # État bot
        if not running:
            bot_status = Text("⛔ ARRÊTÉ",   style="bold red")
        elif paused:
            bot_status = Text("⏸ EN PAUSE", style="bold yellow")
        else:
            bot_status = Text("🟢 ACTIF",    style="bold green")

        # CB couleur
        cb_style = CB_COLORS.get(cb_level, "white")
        cb_text  = Text(
            f"CB{cb_level} {cb_name}",
            style=cb_style
        )

        # DD couleur
        dd_style = (
            "bold red"    if dd_pct <= -2.0 else
            "bold yellow" if dd_pct <= -1.0 else
            "green"
        )
        dd_text = Text(f"DD: {dd_pct:+.2f}%", style=dd_style)

        t = Table(box=box.SIMPLE, show_header=False,
                  padding=(0, 2))
        t.add_column()
        t.add_column()
        t.add_column()
        t.add_column()
        t.add_column()
        t.add_column()

        t.add_row(
            bot_status,
            Text(f"📍 {session}", style="cyan"),
            Text(f"💰 {equity:,.2f}$", style="bold white"),
            cb_text,
            dd_text,
            Text(
                f"Cycles: {cycles} | "
                f"Exec: {executes}",
                style="dim white"
            ),
        )

        return Panel(t, title="[bold]STATUT[/]",
                     border_style="blue", padding=(0, 1))

    # ══════════════════════════════════════════════════════════
    # SECTION VERDICTS
    # ══════════════════════════════════════════════════════════

    def _build_verdicts_table(self, status: dict):
        """
        Table des verdicts par paire.
        Colonnes : Paire | Dir | Score | Grade | Verdict | RR
                   | Entry | SL | TP | Biais | Killzone
        """
        verdicts = status.get("verdicts", {})
        if not verdicts:
            return None

        t = Table(
            title="📊 VERDICTS PAIRES",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
        )

        cols = [
            ("Paire",    "left",   8),
            ("Dir",      "center", 8),
            ("Score",    "right",  7),
            ("Grade",    "center", 7),
            ("Verdict",  "center", 10),
            ("RR",       "right",  6),
            ("Entry",    "right",  10),
            ("SL",       "right",  10),
            ("TP",       "right",  10),
            ("Biais",    "center", 8),
            ("KZ",       "center", 4),
        ]

        for name, justify, width in cols:
            t.add_column(name, justify=justify,
                         min_width=width)

        for pair, v in verdicts.items():
            verdict   = v.get("verdict",   "?")
            grade     = v.get("grade",     "C")
            score     = v.get("score",     0)
            direction = v.get("direction", "?")
            rr        = v.get("rr",        0.0)

            # Snapshot complet pour entry/sl/tp
            snap = {}
            if self._scoring:
                snap = self._scoring.get_snapshot(pair)

            entry = snap.get("entry")
            sl    = snap.get("sl")
            tp    = snap.get("tp")
            aligned   = snap.get("aligned",    False)
            killzone  = snap.get("in_killzone", False)

            v_style = VERDICT_COLORS.get(verdict, "white")
            g_style = GRADE_COLORS.get(grade, "white")

            dir_icon = (
                "⬆ BULL" if direction == "BULLISH" else
                "⬇ BEAR" if direction == "BEARISH" else
                "─ NEU"
            )
            dir_style = (
                "bold green" if direction == "BULLISH" else
                "bold red"   if direction == "BEARISH" else
                "dim"
            )

            score_style = (
                "bold green"  if score >= 80 else
                "bold yellow" if score >= 65 else
                "dim red"
            )

            t.add_row(
                Text(pair,       style="bold white"),
                Text(dir_icon,   style=dir_style),
                Text(str(score), style=score_style),
                Text(grade,      style=g_style),
                Text(verdict,    style=v_style),
                Text(f"{rr:.2f}" if rr else "─"),
                Text(
                    f"{entry:.5f}" if entry else "─",
                    style="cyan"
                ),
                Text(
                    f"{sl:.5f}"    if sl    else "─",
                    style="red"
                ),
                Text(
                    f"{tp:.5f}"    if tp    else "─",
                    style="green"
                ),
                Text(
                    "✓ ALG" if aligned else "✗ MIS",
                    style="green" if aligned else "red"
                ),
                Text(
                    "✓" if killzone else "─",
                    style="green" if killzone else "dim"
                ),
            )

        return t

    # ══════════════════════════════════════════════════════════
    # SECTION KILLSWITCHES
    # ══════════════════════════════════════════════════════════

    def _build_ks_table(self, status: dict):
        """
        Table des KillSwitches actifs.
        N'affiche que les KS actifs pour éviter le bruit.
        """
        ks_global = status.get("ks_global", {})
        if not ks_global:
            return None

        # Collecter tous les KS actifs
        active_ks = []
        for pair, ks_data in ks_global.items():
            blocked = ks_data.get("blocked_by", [])
            warnings= ks_data.get("warnings",   [])
            for ks in blocked:
                active_ks.append({
                    "pair":    pair,
                    "ks":      ks,
                    "type":    "BLOQUANT",
                    "style":   KS_ACTIVE_COLOR,
                })
            for ks in warnings:
                active_ks.append({
                    "pair":    pair,
                    "ks":      ks,
                    "type":    "WARNING",
                    "style":   KS_WARNING_COLOR,
                })

        if not active_ks:
            return Panel(
                Align.center(
                    Text(
                        "✅ Tous les KillSwitches OK — "
                        "Aucun bloquant actif",
                        style="bold green"
                    )
                ),
                title="🛡 KILLSWITCHES",
                border_style="green",
            )

        t = Table(
            title=f"🛡 KILLSWITCHES — "
                  f"{len(active_ks)} actifs",
            box=box.SIMPLE,
            header_style="bold red",
        )

        t.add_column("Paire",   min_width=8)
        t.add_column("KS",      min_width=8)
        t.add_column("Type",    min_width=10)

        for ks in active_ks:
            t.add_row(
                Text(ks["pair"], style="bold white"),
                Text(ks["ks"],   style=ks["style"]),
                Text(ks["type"], style=ks["style"]),
            )

        return t

    # ══════════════════════════════════════════════════════════
    # SECTION POSITIONS OUVERTES
    # ══════════════════════════════════════════════════════════

    def _build_positions_table(self):
        """
        Table des positions ouvertes du bot.
        Inclut PnL live + distance SL en pips.
        """
        if self._reader is None:
            return None

        try:
            positions = self._reader.get_open_positions()
            if not positions:
                return Panel(
                    Align.center(
                        Text(
                            "Aucune position ouverte",
                            style="dim"
                        )
                    ),
                    title="📈 POSITIONS OUVERTES",
                    border_style="dim",
                )

            t = Table(
                title=f"📈 POSITIONS OUVERTES "
                      f"({len(positions)})",
                box=box.ROUNDED,
                header_style="bold magenta",
            )

            for col in [
                "Ticket", "Paire", "Dir", "Lot",
                "Entry", "Prix Act.", "SL", "TP",
                "PnL $", "PnL %", "Durée"
            ]:
                t.add_column(col, justify="right",
                              min_width=9)

            now_utc = datetime.now(timezone.utc)

            for pos in positions:
                pnl        = pos.get("profit",       0.0)
                volume     = pos.get("volume",        0.0)
                direction  = pos.get("type_str",      "?")
                entry_p    = pos.get("price_open",    0.0)
                current_p  = pos.get("price_current", 0.0)
                sl         = pos.get("sl",            0.0)
                tp         = pos.get("tp",            0.0)
                pair       = pos.get("symbol",        "?")
                ticket     = pos.get("ticket",        0)
                open_time  = pos.get("time_open")

                # Durée
                if open_time:
                    try:
                        duration = now_utc - datetime.fromisoformat(
                            str(open_time).replace("Z", "+00:00")
                        )
                        h = int(duration.total_seconds() // 3600)
                        m = int(
                            (duration.total_seconds() % 3600) // 60
                        )
                        dur_str = f"{h}h{m:02d}m"
                    except Exception:
                        dur_str = "─"
                else:
                    dur_str = "─"

                # Styles PnL
                pnl_style = (
                    "bold green" if pnl > 0 else
                    "bold red"   if pnl < 0 else
                    "white"
                )
                dir_style = (
                    "green" if "BUY" in str(direction).upper()
                    else "red"
                )

                # PnL %
                equity = 10000.0
                if self._supervisor:
                    try:
                        snap   = self._supervisor.get_snapshot()
                        equity = snap.get("equity", 10000.0) or 10000.0
                    except Exception:
                        pass
                pnl_pct = (pnl / equity * 100) if equity > 0 else 0

                t.add_row(
                    Text(str(ticket),       style="dim"),
                    Text(pair,              style="bold white"),
                    Text(str(direction),    style=dir_style),
                    Text(f"{volume:.2f}",   style="white"),
                    Text(f"{entry_p:.5f}",  style="cyan"),
                    Text(f"{current_p:.5f}",style="white"),
                    Text(f"{sl:.5f}",       style="red"),
                    Text(f"{tp:.5f}",       style="green"),
                    Text(
                        f"{pnl:+.2f}",
                        style=pnl_style
                    ),
                    Text(
                        f"{pnl_pct:+.2f}%",
                        style=pnl_style
                    ),
                    Text(dur_str,           style="dim"),
                )

            return t

        except Exception as e:
            logger.error(
                f"Dashboard — positions_table erreur : {e}"
            )
            return None

    # ══════════════════════════════════════════════════════════
    # SECTION PYRAMIDE KB5
    # ══════════════════════════════════════════════════════════

    def _build_pyramid_table(self, status: dict):
        """
        Scores KB5 pyramide par paire (MN→M15).
        Colorés selon le niveau : vert ≥70, jaune 50-69, rouge <50.
        """
        verdicts = status.get("verdicts", {})
        if not verdicts:
            return None

        t = Table(
            title="🔺 PYRAMIDE KB5 (scores par TF)",
            box=box.SIMPLE,
            header_style="bold blue",
        )

        t.add_column("Paire",  min_width=8)
        for tf in ["MN", "W1", "D1", "H4", "H1", "M15"]:
            t.add_column(tf, justify="center", min_width=6)
        t.add_column("FINAL", justify="center", min_width=7)

        for pair in verdicts:
            if not self._scoring:
                continue
            snap   = self._scoring.get_snapshot(pair)
            pyr    = snap.get("pyramid", {}) or {}
            final  = snap.get("score",   0)

            row = [Text(pair, style="bold white")]

            for tf in ["MN", "W1", "D1", "H4", "H1", "M15"]:
                score = pyr.get(tf, 0)
                style = (
                    "bold green"  if score >= 70 else
                    "bold yellow" if score >= 50 else
                    "dim red"
                )
                row.append(Text(str(score), style=style))

            final_style = (
                "bold bright_green" if final >= 80 else
                "bold yellow"       if final >= 65 else
                "bold red"
            )
            row.append(Text(str(final), style=final_style))

            t.add_row(*row)

        return t

    # ══════════════════════════════════════════════════════════
    # SECTION HISTORIQUE VERDICTS
    # ══════════════════════════════════════════════════════════

    def _build_history_table(self, status: dict):
        """
        Derniers N verdicts avec raisons.
        Mise à jour à chaque refresh depuis le scoring engine.
        """
        if not self._scoring:
            return None

        stats = self._scoring.get_statistics()
        last  = stats.get("last_verdict")

        # Mettre à jour le buffer
        if last:
            with self._lock:
                if (not self._verdict_buffer or
                        self._verdict_buffer[-1].get("timestamp")
                        != last.get("timestamp")):
                    self._verdict_buffer.append(last)
                    if len(self._verdict_buffer) > HISTORY_MAX_DISPLAY:
                        self._verdict_buffer = (
                            self._verdict_buffer[-HISTORY_MAX_DISPLAY:]
                        )

        with self._lock:
            history = list(reversed(self._verdict_buffer))

        if not history:
            return None

        t = Table(
            title=f"📋 HISTORIQUE "
                  f"(derniers {len(history)} verdicts)",
            box=box.SIMPLE,
            header_style="bold white",
        )

        t.add_column("Heure",    min_width=8)
        t.add_column("Paire",    min_width=8)
        t.add_column("Dir",      min_width=6)
        t.add_column("Score",    min_width=6, justify="right")
        t.add_column("Grade",    min_width=6, justify="center")
        t.add_column("Verdict",  min_width=10)
        t.add_column("RR",       min_width=6, justify="right")
        t.add_column("Raison",   min_width=30)

        for entry in history:
            ts_str = "?"
            try:
                ts = datetime.fromisoformat(
                    entry.get("timestamp", "")
                    .replace("Z", "+00:00")
                )
                ts_str = ts.strftime("%H:%M:%S")
            except Exception:
                pass

            verdict = entry.get("verdict", "?")
            grade   = entry.get("grade",   "C")
            score   = entry.get("score",   0)
            dir_    = entry.get("direction","?")
            rr      = entry.get("rr",      0.0)
            reason  = entry.get("reason",  "─")
            pair    = entry.get("pair",    "?")

            v_style = VERDICT_COLORS.get(verdict, "white")
            g_style = GRADE_COLORS.get(grade,   "white")

            t.add_row(
                Text(ts_str,      style="dim"),
                Text(pair,        style="bold white"),
                Text(
                    "▲" if dir_ == "BULLISH" else
                    "▼" if dir_ == "BEARISH" else "─",
                    style=(
                        "green" if dir_ == "BULLISH" else
                        "red"   if dir_ == "BEARISH" else "dim"
                    )
                ),
                Text(str(score),  style="white"),
                Text(grade,       style=g_style),
                Text(verdict,     style=v_style),
                Text(
                    f"{rr:.2f}" if rr else "─",
                    style="cyan"
                ),
                Text(
                    reason[:45] + "…"
                    if len(reason) > 45 else reason,
                    style="dim"
                ),
            )

        return t

    # ══════════════════════════════════════════════════════════
    # SECTION STATISTIQUES
    # ══════════════════════════════════════════════════════════

    def _build_stats_panel(self, status: dict):
        """
        Panel compact de statistiques globales.
        """
        if not self._scoring:
            return None

        stats  = self._scoring.get_statistics()
        total  = stats.get("total",        0)
        exe    = stats.get("execute",      0)
        watch  = stats.get("watch",        0)
        no_t   = stats.get("no_trade",     0)
        rate   = stats.get("execute_rate", 0.0)
        avg_sc = stats.get("avg_score",    0.0)
        grades = stats.get("grade_counts", {})

        order_snap = {}
        if self._orders:
            order_snap = self._orders.get_snapshot()

        o_total  = order_snap.get("total_orders", 0)
        o_success= order_snap.get("success",      0)
        o_failed = order_snap.get("failed",       0)

        grade_str = " | ".join(
            f"{g}:{n}" for g, n in
            sorted(grades.items())
        ) if grades else "─"

        lines = [
            Text(
                f"Signaux — Total: {total} | "
                f"Execute: {exe} | Watch: {watch} | "
                f"No-Trade: {no_t} | "
                f"Execute Rate: {rate}%",
                style="white"
            ),
            Text(
                f"Ordres — Envoyés: {o_total} | "
                f"Succès: {o_success} | Échoués: {o_failed} | "
                f"Score moyen: {avg_sc}",
                style="white"
            ),
            Text(
                f"Grades — {grade_str}",
                style="dim"
            ),
        ]

        from rich.console import Group
        return Panel(
            Group(*lines),
            title="📈 STATISTIQUES GLOBALES",
            border_style="blue",
            padding=(0, 2),
        )

    # ══════════════════════════════════════════════════════════
    # SYSTÈME D'ALERTES
    # ══════════════════════════════════════════════════════════

    def alert(self, pair: str, scalp_output: dict) -> None:
        """
        Pousse une alerte WATCH dans le terminal.
        Respecte le cooldown pour éviter le flood.

        Args:
            pair:         symbole
            scalp_output: dict SCALP_OUTPUT
        """
        alert_key = f"{pair}_{scalp_output.get('direction')}"
        now       = time.time()

        with self._lock:
            last_alert = self._alert_history.get(alert_key, 0)
            if now - last_alert < ALERT_COOLDOWN_SEC:
                return
            self._alert_history[alert_key] = now

        if not self._console:
            logger.info(
                f"ALERTE WATCH — {pair} | "
                f"Score : {scalp_output.get('score')} "
                f"[{scalp_output.get('grade')}] | "
                f"RR : {scalp_output.get('rr')}"
            )
            return

        self._console.print(
            Panel(
                Text(
                    f"👁 WATCH — {pair} | "
                    f"Dir: {scalp_output.get('direction')} | "
                    f"Score: {scalp_output.get('score')} "
                    f"[{scalp_output.get('grade')}] | "
                    f"RR: {scalp_output.get('rr', 0):.2f} | "
                    f"Entry: {scalp_output.get('entry')} | "
                    f"SL: {scalp_output.get('sl')} | "
                    f"TP: {scalp_output.get('tp')}",
                    style="bold yellow"
                ),
                title="⚠ ALERTE WATCH",
                border_style="yellow",
            )
        )

    def alert_critical(self, message: str) -> None:
        """
        Alerte critique (CB3, KS99, erreur fatale).
        Toujours affichée, pas de cooldown.
        """
        if self._console:
            self._console.print(
                Panel(
                    Text(message, style="bold bright_red"),
                    title="🚨 ALERTE CRITIQUE",
                    border_style="bright_red",
                )
            )
        logger.critical(f"Dashboard CRITIQUE — {message}")

    # ══════════════════════════════════════════════════════════
    # UTILITAIRES
    # ══════════════════════════════════════════════════════════

    def _get_status(self) -> dict:
        """
        Collecte le statut de tous les modules.
        Appelé à chaque refresh. Gère les erreurs
        module par module pour éviter le crash total.

        Returns:
            dict status agrégé
        """
        status: dict = {}

        # Supervisor snapshot
        try:
            if self._supervisor:
                status["snapshot"] = (
                    self._supervisor.get_snapshot()
                )
            else:
                status["snapshot"] = {}
        except Exception:
            status["snapshot"] = {}

        # CB snapshot
        try:
            status["cb"] = (
                self._cb.get_snapshot()
                if self._cb else {}
            )
        except Exception:
            status["cb"] = {}

        # Verdicts
        try:
            status["verdicts"] = (
                self._scoring.get_all_verdicts()
                if self._scoring else {}
            )
        except Exception:
            status["verdicts"] = {}

        # KS global
        try:
            status["ks_global"] = (
                self._ks.get_global_status()
                if self._ks else {}
            )
        except Exception:
            status["ks_global"] = {}

        return status

    def _render_static(self) -> None:
        """
        Mode STATIC : affichage unique dans le terminal.
        Utilisé pour debug ou snapshot manuel.
        """
        if self._console:
            self._console.print(
                self._build_layout()
            )

    def _fallback_loop(self) -> None:
        """
        Fallback si rich n'est pas installé.
        Log basique toutes les N secondes.
        """
        while not self._shutdown.is_set():
            try:
                status = self._get_status()
                verdicts = status.get("verdicts", {})
                for pair, v in verdicts.items():
                    logger.info(
                        f"[DASHBOARD] {pair} | "
                        f"{v.get('verdict')} | "
                        f"Score: {v.get('score')} | "
                        f"Grade: {v.get('grade')}"
                    )
                cb = status.get("cb", {})
                logger.info(
                    f"[DASHBOARD] CB{cb.get('level')} | "
                    f"DD: {cb.get('dd_pct')}%"
                )
            except Exception as e:
                logger.error(
                    f"Dashboard fallback erreur : {e}"
                )
            self._shutdown.wait(timeout=REFRESH_INTERVAL_SEC * 6)

    # ══════════════════════════════════════════════════════════
    # API PUBLIQUE
    # ══════════════════════════════════════════════════════════

    def render_once(self) -> None:
        """Affichage unique snapshot — utile pour debug."""
        if RICH_AVAILABLE and self._console:
            self._console.print(self._build_layout())
        else:
            self._fallback_loop()

    def get_status_dict(self) -> dict:
        """
        Retourne le statut complet en dict.
        Consommé par des interfaces externes (API REST, etc.)

        Returns:
            dict statut complet
        """
        return self._get_status()

    def __repr__(self) -> str:
        return (
            f"PatronDashboard("
            f"rich={RICH_AVAILABLE}, "
            f"running={self._running})"
        )
