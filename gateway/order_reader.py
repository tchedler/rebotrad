"""
gateway/order_reader.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sentinel Pro KB5 — Lecture ordres et positions MT5

Responsabilités :
- Positions ouvertes enrichies (RR live, durée, swap)
- Ordres pendants avec types traduits en string
- Détection ordres manuels (magic=0 + reason 0/1/2)
- Filtrage par paire
- Exposition globale pour Circuit Breaker
- Recherche par ticket pour Order Manager
- Métriques dashboard Patron
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import MetaTrader5 as mt5
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Magic number du bot — toutes les positions bot ont ce magic
BOT_MAGIC_NUMBER = 20260101  # Format YYYYMMDD — à aligner avec settings.py

# Traduction types ordres pendants MT5
ORDER_TYPE_MAP = {
    0: "BUY",
    1: "SELL",
    2: "BUY_LIMIT",
    3: "SELL_LIMIT",
    4: "BUY_STOP",
    5: "SELL_STOP",
    6: "BUY_STOP_LIMIT",
    7: "SELL_STOP_LIMIT",
}

# Raisons d'ouverture MT5 → lisible
POSITION_REASON_MAP = {
    0: "CLIENT",   # Terminal manuel
    1: "MOBILE",   # App mobile
    2: "WEB",      # WebTrader
    3: "EXPERT",   # Bot / EA
}


class OrderReader:
    """
    Lit et enrichit toutes les positions et ordres MT5.
    Thread-safe en lecture (MT5 API est thread-safe en lecture).
    """

    # ══════════════════════════════════════
    # POSITIONS OUVERTES
    # ══════════════════════════════════════

    def get_open_positions(self, pair: str = None) -> list:
        """
        Retourne toutes les positions ouvertes.
        Si pair fourni → filtre sur cette paire uniquement.
        Enrichi : RR live, durée, swap, reason traduit.
        """
        if pair:
            raw = mt5.positions_get(symbol=pair)
        else:
            raw = mt5.positions_get()

        if raw is None:
            return []

        return [self._build_position(p) for p in raw]

    def _build_position(self, p) -> dict:
        """
        Construit un dict position enrichi depuis un objet MT5.
        Calcule RR live, durée, type, reason.
        """
        direction   = "BUY" if p.type == 0 else "SELL"
        open_time   = datetime.utcfromtimestamp(p.time)
        duration_min = (
            datetime.utcnow() - open_time
        ).total_seconds() / 60

        # RR live : profit actuel / risque initial (SL)
        rr_live = self._calculate_rr_live(
            direction    = direction,
            open_price   = p.price_open,
            current_price= p.price_current,
            sl           = p.sl,
        )

        return {
            # Identifiants
            "ticket":        p.ticket,
            "identifier":    p.identifier,
            "pair":          p.symbol,
            "magic":         p.magic,
            "comment":       p.comment,

            # Direction et taille
            "type":          direction,
            "volume":        p.volume,

            # Prix
            "open_price":    p.price_open,
            "current_price": p.price_current,
            "sl":            p.sl,
            "tp":            p.tp,

            # Performance
            "profit":        round(p.profit, 2),
            "swap":          round(p.swap,   2),
            "total_pnl":     round(p.profit + p.swap, 2),
            "rr_live":       rr_live,

            # Timing
            "open_time":     open_time,
            "duration_min":  round(duration_min, 1),

            # Origine
            "reason":        POSITION_REASON_MAP.get(p.reason, "UNKNOWN"),
            "is_manual":     p.reason in (0, 1, 2) or p.magic == 0,
            "is_bot":        p.magic == BOT_MAGIC_NUMBER,
        }

    def _calculate_rr_live(
        self,
        direction: str,
        open_price: float,
        current_price: float,
        sl: float,
    ) -> float:
        """
        Calcule le RR live en temps réel.
        RR = distance parcourue / distance SL initiale
        Positif = en profit, négatif = en perte.
        """
        if sl == 0 or open_price == 0:
            return 0.0
        try:
            risk = abs(open_price - sl)
            if risk == 0:
                return 0.0
            if direction == "BUY":
                reward = current_price - open_price
            else:
                reward = open_price - current_price
            return round(reward / risk, 2)
        except Exception:
            return 0.0

    # ══════════════════════════════════════
    # HISTORIQUE ET DEALS
    # ══════════════════════════════════════

    def get_closed_today(self, magic: int = None) -> list:
        """
        Retourne tous les deals fermés aujourd'hui (UTC).
        Utilisé par Behaviour Shield pour le Killswitch BS6 (Revenge Trade).
        """
        from datetime import time
        now = datetime.now(timezone.utc)
        start_of_day = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
        
        # deals_get prend des timestamps
        raw = mt5.history_deals_get(start_of_day, now)
        if raw is None:
            return []
            
        deals = []
        for d in raw:
            # On ne garde que les deals de type DEAL_ENTRY_OUT (fermeture)
            # Et on filtre par magic si fourni
            if d.entry == 1: # mt5.DEAL_ENTRY_OUT
                if magic is None or d.magic == magic:
                    deals.append({
                        "ticket": d.ticket,
                        "order": d.order,
                        "symbol": d.symbol,
                        "magic": d.magic,
                        "profit": d.profit,
                        "time": datetime.utcfromtimestamp(d.time),
                    })
        return deals

    # ══════════════════════════════════════
    # ORDRES PENDANTS
    # ══════════════════════════════════════

    def get_pending_orders(self, pair: str = None) -> list:
        """
        Retourne tous les ordres pendants.
        Si pair fourni → filtre sur cette paire uniquement.
        Type traduit en string lisible.
        """
        if pair:
            raw = mt5.orders_get(symbol=pair)
        else:
            raw = mt5.orders_get()

        if raw is None:
            return []

        return [self._build_order(o) for o in raw]

    def _build_order(self, o) -> dict:
        """
        Construit un dict ordre depuis un objet MT5.
        Type traduit en string. Direction déduite du type.
        """
        type_str  = ORDER_TYPE_MAP.get(o.type, f"UNKNOWN_{o.type}")
        direction = "BUY" if "BUY" in type_str else "SELL"

        return {
            "ticket":      o.ticket,
            "pair":        o.symbol,
            "type":        type_str,
            "direction":   direction,
            "volume":      o.volume_current,
            "price":       o.price_open,
            "sl":          o.sl,
            "tp":          o.tp,
            "comment":     o.comment,
            "magic":       o.magic,
            "placed_at":   datetime.utcfromtimestamp(o.time_setup),
            "is_manual":   o.magic == 0,
            "is_bot":      o.magic == BOT_MAGIC_NUMBER,
        }

    # ══════════════════════════════════════
    # DÉTECTION ORDRES MANUELS
    # ══════════════════════════════════════

    def get_manual_positions(self) -> list:
        """
        Retourne uniquement les positions manuelles.
        Manuel = magic=0 OU reason CLIENT/MOBILE/WEB (0,1,2).
        Double critère plus fiable que magic seul.
        """
        all_pos = self.get_open_positions()
        manual  = [p for p in all_pos if p["is_manual"]]

        if manual:
            logger.warning(
                f"POSITIONS MANUELLES DÉTECTÉES : "
                f"{len(manual)} | "
                f"Paires : {[p['pair'] for p in manual]} | "
                f"PnL total : "
                f"{sum(p['total_pnl'] for p in manual):.2f}"
            )
        return manual

    def get_manual_orders(self) -> list:
        """Ordres pendants placés manuellement."""
        all_orders = self.get_pending_orders()
        return [o for o in all_orders if o["is_manual"]]

    # ══════════════════════════════════════
    # RECHERCHE PAR TICKET
    # ══════════════════════════════════════

    def get_position_by_ticket(self, ticket: int) -> dict | None:
        """
        Retrouve une position par son ticket.
        Utilisé par Order Manager pour modifier SL/TP ou fermer.
        """
        raw = mt5.positions_get(ticket=ticket)
        if raw is None or len(raw) == 0:
            logger.warning(f"Position ticket {ticket} introuvable.")
            return None
        return self._build_position(raw[0])

    def get_order_by_ticket(self, ticket: int) -> dict | None:
        """Retrouve un ordre pendant par son ticket."""
        raw = mt5.orders_get(ticket=ticket)
        if raw is None or len(raw) == 0:
            logger.warning(f"Ordre ticket {ticket} introuvable.")
            return None
        return self._build_order(raw[0])

    # ══════════════════════════════════════
    # VÉRIFICATIONS RAPIDES
    # ══════════════════════════════════════

    def has_position_on_pair(
        self,
        pair: str,
        direction: str = None
    ) -> bool:
        """
        Vérifie si une position est ouverte sur cette paire.
        Si direction fournie → vérifie aussi la direction.
        Utilisé par Behaviour Shield avant envoi d'ordre.
        """
        positions = self.get_open_positions(pair=pair)
        if not direction:
            return len(positions) > 0
        return any(p["type"] == direction for p in positions)

    def has_pending_order_on_pair(
        self,
        pair: str,
        direction: str = None
    ) -> bool:
        """Vérifie si un ordre pendant existe sur cette paire."""
        orders = self.get_pending_orders(pair=pair)
        if not direction:
            return len(orders) > 0
        return any(o["direction"] == direction for o in orders)

    def has_active_order_on_pair(
        self,
        pair: str,
        direction: str = None
    ) -> bool:
        """
        Positions ouvertes OU ordres pendants sur cette paire.
        Vérification complète avant tout nouveau trade.
        """
        return (
            self.has_position_on_pair(pair, direction) or
            self.has_pending_order_on_pair(pair, direction)
        )

    # ══════════════════════════════════════
    # EXPOSITION GLOBALE
    # ══════════════════════════════════════

    def get_exposure_summary(self) -> dict:
        """
        Métriques globales pour Circuit Breaker
        et Capital Allocator.
        Calculées en une seule lecture MT5.
        """
        positions = self.get_open_positions()
        orders    = self.get_pending_orders()

        total_pnl     = sum(p["total_pnl"] for p in positions)
        total_volume  = sum(p["volume"]    for p in positions)
        pairs_exposed = list({p["pair"]    for p in positions})
        manual_count  = sum(1 for p in positions if p["is_manual"])
        bot_count     = sum(1 for p in positions if p["is_bot"])

        return {
            "open_positions":  len(positions),
            "pending_orders":  len(orders),
            "total_pnl":       round(total_pnl,    2),
            "total_volume":    round(total_volume,  2),
            "pairs_exposed":   pairs_exposed,
            "pair_count":      len(pairs_exposed),
            "manual_count":    manual_count,
            "bot_count":       bot_count,
            "has_manual":      manual_count > 0,
            "timestamp":       datetime.utcnow(),
        }

    def get_pair_exposure(self, pair: str) -> dict:
        """
        Exposition détaillée sur une seule paire.
        Utilisé par Capital Allocator (MAX_EXPOSURE_PER_PAIR).
        """
        positions = self.get_open_positions(pair=pair)
        orders    = self.get_pending_orders(pair=pair)

        buy_vol  = sum(p["volume"] for p in positions if p["type"] == "BUY")
        sell_vol = sum(p["volume"] for p in positions if p["type"] == "SELL")
        pnl      = sum(p["total_pnl"] for p in positions)

        return {
            "pair":            pair,
            "open_positions":  len(positions),
            "pending_orders":  len(orders),
            "buy_volume":      round(buy_vol,  2),
            "sell_volume":     round(sell_vol, 2),
            "net_volume":      round(buy_vol - sell_vol, 2),
            "total_pnl":       round(pnl, 2),
            "positions":       positions,
        }

    # ══════════════════════════════════════
    # DASHBOARD PATRON
    # ══════════════════════════════════════

    def get_dashboard_snapshot(self) -> dict:
        """
        Snapshot complet pour affichage Dashboard Patron.
        Une seule lecture MT5 — toutes les métriques.
        """
        positions = self.get_open_positions()
        orders    = self.get_pending_orders()
        exposure  = self.get_exposure_summary()

        # Top positions par PnL
        top_winners = sorted(
            positions,
            key=lambda p: p["total_pnl"],
            reverse=True
        )[:3]

        top_losers = sorted(
            positions,
            key=lambda p: p["total_pnl"]
        )[:3]

        return {
            "exposure":    exposure,
            "positions":   positions,
            "orders":      orders,
            "top_winners": top_winners,
            "top_losers":  top_losers,
            "snapshot_at": datetime.utcnow(),
        }

    def __repr__(self):
        exp = self.get_exposure_summary()
        return (
            f"OrderReader("
            f"positions={exp['open_positions']}, "
            f"orders={exp['pending_orders']}, "
            f"pnl={exp['total_pnl']})"
        )
