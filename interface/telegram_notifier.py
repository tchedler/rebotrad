"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Telegram Notifier
══════════════════════════════════════════════════════════════
Responsabilités :
- Envoyer les alertes A+ en temps réel au Patron
- Format HTML structuré : Entry/SL/TP/Score/Setup
- Alertes critiques : CB3, KS99, Gate Regret Rate
- Résumé quotidien automatique à 22h UTC
══════════════════════════════════════════════════════════════
"""

import logging
import threading
import requests
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Configuration (à renseigner dans config/constants.py) ──
# TELEGRAM_TOKEN = "votre_bot_token"
# TELEGRAM_CHAT_ID = "votre_chat_id"

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
TIMEOUT_SEC  = 5


class TelegramNotifier:
    """
    Envoie des alertes HTML formatées sur Telegram.
    Thread-safe — peut être appelé depuis n'importe quel thread.
    """

    def __init__(self, token: str, chat_id: str):
        self._token   = token
        self._chat_id = chat_id
        self._lock    = threading.Lock()
        self._url     = TELEGRAM_API.format(token=token)
        logger.info("TelegramNotifier initialisé")

    # ══════════════════════════════════════════════════════════
    # ALERTES TRADES
    # ══════════════════════════════════════════════════════════

    def send_execute(self, scalp_output: dict) -> bool:
        """
        Alerte EXECUTE — trade envoyé à MT5.
        Format : emoji + paire + direction + score + Entry/SL/TP/RR
        """
        pair      = scalp_output.get("pair", "?")
        direction = scalp_output.get("direction", "?")
        score     = scalp_output.get("score", 0)
        grade     = scalp_output.get("grade", "?")
        entry     = scalp_output.get("entry", 0)
        sl        = scalp_output.get("sl", 0)
        tp        = scalp_output.get("tp", 0)
        rr        = scalp_output.get("rr", 0)
        session   = scalp_output.get("session", "?")
        lot       = scalp_output.get("lot_size", 0)

        arrow  = "🟢" if direction == "BULLISH" else "🔴"
        emoji  = "⚡" if score >= 90 else "✅"

        msg = (
            f"{emoji} <b>EXECUTE — {pair}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{arrow} Direction : <b>{direction}</b>\n"
            f"📊 Score    : <b>{score}/100</b> ({grade})\n"
            f"🕐 Session  : {session}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 Entry    : <code>{entry}</code>\n"
            f"🛑 SL       : <code>{sl}</code>\n"
            f"🎯 TP       : <code>{tp}</code>\n"
            f"📐 RR       : <b>{rr:.1f}R</b>\n"
            f"📦 Lot      : {lot}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🕰 {self._now()}"
        )
        return self._send(msg)

    def send_close(self, ticket: int, pair: str,
                   pnl: float, outcome: str) -> bool:
        """Alerte fermeture de position."""
        emoji = "💰" if outcome == "WIN" else "💸" if outcome == "LOSS" else "⚖️"
        msg = (
            f"{emoji} <b>CLOSE — {pair}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎫 Ticket   : {ticket}\n"
            f"📈 Résultat : <b>{outcome}</b>\n"
            f"💵 PnL      : <b>{pnl:+.2f} $</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🕰 {self._now()}"
        )
        return self._send(msg)

    # ══════════════════════════════════════════════════════════
    # ALERTES CRITIQUES
    # ══════════════════════════════════════════════════════════

    def send_circuit_breaker(self, level: int,
                              reason: str) -> bool:
        """Alerte Circuit Breaker activé."""
        names = {1: "⚠️ CB1 — Ralentissement",
                 2: "🚨 CB2 — PAUSE",
                 3: "🔴 CB3 — HALT TOTAL"}
        name = names.get(level, f"CB{level}")
        msg = (
            f"{name}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 Raison : {reason}\n"
            f"🕰 {self._now()}"
        )
        return self._send(msg)

    def send_ks99(self, reason: str) -> bool:
        """Alerte KS99 — Gateway déconnecté."""
        msg = (
            f"🔌 <b>KS99 — GATEWAY DÉCONNECTÉ</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 Raison : {reason}\n"
            f"⛔ Tous les trades sont bloqués\n"
            f"🕰 {self._now()}"
        )
        return self._send(msg)

    def send_gate_regret(self, regret_rate: float,
                          top_error: str) -> bool:
        """Alerte Gate Regret Rate déclenché."""
        msg = (
            f"🧠 <b>GATE REGRET RATE DÉCLENCHÉ</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Regret Rate : <b>{regret_rate:.0%}</b>\n"
            f"❌ Top erreur  : {top_error}\n"
            f"⛔ Blocage préventif activé\n"
            f"🕰 {self._now()}"
        )
        return self._send(msg)

    # ══════════════════════════════════════════════════════════
    # RÉSUMÉ QUOTIDIEN
    # ══════════════════════════════════════════════════════════

    def send_daily_summary(self, stats: dict,
                            failure_report: dict) -> bool:
        """Résumé quotidien automatique."""
        total    = stats.get("total", 0)
        wins     = stats.get("wins", 0)
        losses   = stats.get("losses", 0)
        winrate  = stats.get("winrate", 0)
        regret   = failure_report.get("regret_rate", 0)
        top_err  = failure_report.get("top_error", "NONE")
        lessons  = failure_report.get("lessons", [])

        lessons_txt = ""
        for i, l in enumerate(lessons[:3], 1):
            lessons_txt += f"\n{i}. {l.get('category')}: {l.get('lesson')[:60]}..."

        final_lessons_txt = lessons_txt if lessons_txt else "\nAucune erreur aujourd'hui ✅"

        msg = (
            f"📅 <b>RÉSUMÉ JOURNALIER — KB5</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Trades    : {total} "
            f"(✅{wins} / ❌{losses})\n"
            f"🎯 Winrate   : <b>{winrate:.1f}%</b>\n"
            f"🧠 Regret    : {regret:.0%}\n"
            f"❌ Top erreur: {top_err}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📚 <b>Leçons du jour :</b>{final_lessons_txt}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🕰 {self._now()}"
        )
        return self._send(msg)

    # ══════════════════════════════════════════════════════════
    # ENVOI HTTP
    # ══════════════════════════════════════════════════════════

    def _send(self, text: str) -> bool:
        """Envoie un message HTML sur Telegram."""
        try:
            resp = requests.post(
                self._url,
                json={
                    "chat_id"    : self._chat_id,
                    "text"       : text,
                    "parse_mode" : "HTML",
                },
                timeout=TIMEOUT_SEC,
            )
            if resp.status_code == 200:
                return True
            logger.warning(f"Telegram erreur HTTP "
                           f"{resp.status_code} : {resp.text[:100]}")
            return False
        except Exception as e:
            logger.error(f"TelegramNotifier — erreur envoi : {e}")
            return False

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    def __repr__(self) -> str:
        return f"TelegramNotifier(chat_id={self._chat_id})"
