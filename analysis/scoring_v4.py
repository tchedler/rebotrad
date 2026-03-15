"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Scoring V4 (Sections A/B/C/D)
══════════════════════════════════════════════════════════════
Structure : 4 sections × 25 pts = 100 pts max

Section A (25 pts) — Structure & Direction
  +10 : DOL < 0.3% du prix actuel
  +10 : MSS + displacement confirmé
  + 5 : HTF bias non-neutral (W+D alignés)

Section B (25 pts) — Zone d'entrée
  +10 : FVG dans OB même direction
  +10 : Setup dans Killzone/Macro ICT
  + 5 : OTE zone 62-79% (bonus)
  Malus -10 : hors session principale
  Malus  -5 : OTE MISSED

Section C (25 pts) — Liquidité
  +15 : EQH/EQL non sweepé présent
  +10 : DOL < 0.5% (Draw on Liquidity proche)
  + 5 : LRLR/HRLR bonus confirmé

Section D (25 pts) — Confirmation
  +10 : Zone Premium/Discount alignée
  +10 : Turtle Soup / Liquidity Sweep
  + 5 : Displacement (bougie forte)
══════════════════════════════════════════════════════════════
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Points par critère
# Section A
SCORE_A_DOL_TIGHT    = 10   # DOL < 0.3%
SCORE_A_MSS          = 10   # MSS + displacement
SCORE_A_HTF_BIAS     = 5    # HTF bias aligné

# Section B
SCORE_B_FVG_IN_OB    = 10   # FVG dans OB
SCORE_B_KILLZONE     = 10   # dans KZ/Macro
SCORE_B_OTE          = 5    # OTE INSIDE bonus
MALUS_B_OFF_SESSION  = -10  # hors session
MALUS_B_OTE_MISSED   = -5   # OTE MISSED

# Section C
SCORE_C_EQL_PRESENT  = 15   # EQH/EQL non sweepé
SCORE_C_DOL_CLOSE    = 10   # DOL < 0.5%
SCORE_C_LRLR         = 5    # LRLR/HRLR confirmé

# Section D
SCORE_D_PD_ALIGN     = 10   # Premium/Discount aligné
SCORE_D_SWEEP        = 10   # Turtle Soup / Sweep
SCORE_D_DISPLACEMENT = 5    # Displacement


class ScoringV4:
    """
    Scoring ICT V4 en 4 sections A/B/C/D.
    Appelé par scoring_engine pour enrichir le score final KB5.
    Retourne un ScoringV4Result avec détail par section.
    """

    def __init__(self, liquidity_detector=None,
                 ote_detector=None,
                 cisd_detector=None):
        self._liq  = liquidity_detector
        self._ote  = ote_detector
        self._cisd = cisd_detector
        logger.info("ScoringV4 initialisé — 4 sections A/B/C/D prêt")

    # ══════════════════════════════════════════════════════════
    # MÉTHODE PRINCIPALE
    # ══════════════════════════════════════════════════════════

    def compute(self, pair: str, direction: str,
                kb5_result: dict) -> dict:
        """
        Calcule le score V4 complet en 4 sections.

        Args:
            pair        : ex. "EURUSD"
            direction   : "BULLISH" ou "BEARISH"
            kb5_result  : KB5_RESULT de kb5_engine

        Returns:
            dict {
                total      : int (0-100),
                section_a  : dict {score, details},
                section_b  : dict {score, details},
                section_c  : dict {score, details},
                section_d  : dict {score, details},
            }
        """
        sec_a = self._section_a(pair, direction, kb5_result)
        sec_b = self._section_b(pair, direction, kb5_result)
        sec_c = self._section_c(pair, direction, kb5_result)
        sec_d = self._section_d(pair, direction, kb5_result)

        total = min(
            max(sec_a["score"] + sec_b["score"] +
                sec_c["score"] + sec_d["score"], 0),
            100
        )

        logger.debug(f"ScoringV4 {pair} {direction} — "
                     f"A:{sec_a['score']} B:{sec_b['score']} "
                     f"C:{sec_c['score']} D:{sec_d['score']} "
                     f"Total:{total}")

        return {
            "total"     : total,
            "section_a" : sec_a,
            "section_b" : sec_b,
            "section_c" : sec_c,
            "section_d" : sec_d,
            "timestamp" : datetime.now(timezone.utc).isoformat(),
        }

    # ══════════════════════════════════════════════════════════
    # SECTION A — Structure & Direction (25 pts)
    # ══════════════════════════════════════════════════════════

    def _section_a(self, pair: str, direction: str,
                   kb5_result: dict) -> dict:
        score   = 0
        details = []

        # A1 — DOL < 0.3%
        dol = {}
        if self._liq:
            dol = self._liq.get_dol(pair)
        entry = kb5_result.get("entry_model", {}).get("entry", 0) or 0
        dol_level = dol.get("target_level")
        if dol_level and entry > 0:
            dol_pct = abs(dol_level - entry) / entry * 100
            if dol_pct < 0.3:
                score += SCORE_A_DOL_TIGHT
                details.append(f"DOL proche {dol_pct:.2f}% < 0.3% "
                                f"(+{SCORE_A_DOL_TIGHT})")

        # A2 — MSS + displacement
        confluences = kb5_result.get("confluences", [])
        has_sweep = any(c["name"] == "LIQUIDITY_SWEEP"
                        for c in confluences)
        has_amd   = any("AMD" in c["name"] for c in confluences)
        if has_sweep or has_amd:
            score += SCORE_A_MSS
            details.append(f"MSS/Displacement confirmé "
                            f"(+{SCORE_A_MSS})")

        # A3 — HTF bias non-neutral
        bias_aligned = kb5_result.get("bias_aligned", False)
        if bias_aligned:
            score += SCORE_A_HTF_BIAS
            details.append(f"HTF bias aligné W+D "
                            f"(+{SCORE_A_HTF_BIAS})")

        return {"score": min(score, 25), "details": details,
                "max": 25}

    # ══════════════════════════════════════════════════════════
    # SECTION B — Zone d'entrée (25 pts)
    # ══════════════════════════════════════════════════════════

    def _section_b(self, pair: str, direction: str,
                   kb5_result: dict) -> dict:
        score   = 0
        details = []

        # B1 — FVG dans OB
        confluences = kb5_result.get("confluences", [])
        has_fvg_ob = any("FVG_OB" in c["name"]
                         for c in confluences)
        if has_fvg_ob:
            score += SCORE_B_FVG_IN_OB
            details.append(f"FVG dans OB alignés "
                            f"(+{SCORE_B_FVG_IN_OB})")

        # B2 — Killzone ou Macro ICT
        in_killzone = kb5_result.get("in_killzone", False)
        has_macro   = any(c["name"] == "ICT_MACRO"
                          for c in confluences)
        session     = kb5_result.get("session", "")
        off_session = session not in ("LONDON", "NEW_YORK",
                                      "LONDON_NY_OVERLAP")

        if in_killzone or has_macro:
            score += SCORE_B_KILLZONE
            details.append(f"Dans Killzone/Macro ICT "
                            f"(+{SCORE_B_KILLZONE})")
        elif off_session:
            score += MALUS_B_OFF_SESSION
            details.append(f"Hors session principale "
                            f"({MALUS_B_OFF_SESSION})")

        # B3 — OTE bonus/malus
        if self._ote:
            ote = self._ote.check(pair, direction)
            if ote["status"] == "INSIDE":
                score += SCORE_B_OTE
                details.append(f"OTE INSIDE zone 62-79% "
                                f"(+{SCORE_B_OTE})")
            elif ote["status"] == "MISSED":
                score += MALUS_B_OTE_MISSED
                details.append(f"OTE MISSED zone dépassée "
                                f"({MALUS_B_OTE_MISSED})")

        return {"score": min(max(score, -10), 25),
                "details": details, "max": 25}

    # ══════════════════════════════════════════════════════════
    # SECTION C — Liquidité (25 pts)
    # ══════════════════════════════════════════════════════════

    def _section_c(self, pair: str, direction: str,
                   kb5_result: dict) -> dict:
        score   = 0
        details = []

        # C1 — EQH/EQL non sweepé
        pools = {}
        if self._liq:
            pools = self._liq.get_pools(pair)
        eq_highs = pools.get("equal_highs", [])
        eq_lows  = pools.get("equal_lows",  [])
        has_eq   = (direction == "BEARISH" and eq_highs) or \
                   (direction == "BULLISH" and eq_lows)
        if has_eq:
            score += SCORE_C_EQL_PRESENT
            details.append(f"EQH/EQL non sweepé présent "
                            f"(+{SCORE_C_EQL_PRESENT})")

        # C2 — DOL < 0.5%
        dol = self._liq.get_dol(pair) if self._liq else {}
        entry = kb5_result.get("entry_model", {}).get("entry", 0) or 0
        dol_level = dol.get("target_level")
        if dol_level and entry > 0:
            dol_pct = abs(dol_level - entry) / entry * 100
            if dol_pct < 0.5:
                score += SCORE_C_DOL_CLOSE
                details.append(f"DOL proche {dol_pct:.2f}% < 0.5% "
                                f"(+{SCORE_C_DOL_CLOSE})")

        # C3 — LRLR/HRLR sweepé
        if self._liq and hasattr(self._liq, "has_lrlr_swept"):
            if self._liq.has_lrlr_swept(pair, direction):
                score += SCORE_C_LRLR
                details.append(f"LRLR/HRLR sweepé "
                                f"(+{SCORE_C_LRLR})")

        return {"score": min(score, 25), "details": details,
                "max": 25}

    # ══════════════════════════════════════════════════════════
    # SECTION D — Confirmation (25 pts)
    # ══════════════════════════════════════════════════════════

    def _section_d(self, pair: str, direction: str,
                   kb5_result: dict) -> dict:
        score   = 0
        details = []

        # D1 — Premium/Discount aligné
        pd_zone = kb5_result.get("pd_zone", "UNKNOWN")
        pd_ok   = ((direction == "BULLISH" and pd_zone == "DISCOUNT") or
                   (direction == "BEARISH" and pd_zone == "PREMIUM"))
        if pd_ok:
            score += SCORE_D_PD_ALIGN
            details.append(f"Zone {pd_zone} alignée avec {direction} "
                            f"(+{SCORE_D_PD_ALIGN})")

        # D2 — Turtle Soup / Sweep
        confluences = kb5_result.get("confluences", [])
        has_sweep   = any(c["name"] == "LIQUIDITY_SWEEP"
                          for c in confluences)
        if has_sweep:
            score += SCORE_D_SWEEP
            details.append(f"Turtle Soup / Sweep confirmé "
                            f"(+{SCORE_D_SWEEP})")

        # D3 — Displacement (CISD ou AMD)
        has_cisd = False
        if self._cisd:
            cisd = self._cisd.check(pair, direction)
            has_cisd = cisd.get("detected", False)
        has_amd = any("AMD" in c["name"] for c in confluences)
        if has_cisd or has_amd:
            score += SCORE_D_DISPLACEMENT
            details.append(f"Displacement confirmé CISD/AMD "
                            f"(+{SCORE_D_DISPLACEMENT})")

        return {"score": min(score, 25), "details": details,
                "max": 25}

    def __repr__(self) -> str:
        return "ScoringV4(sections=A/B/C/D, max=100)"
