# analysis/kb5_engine.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Moteur Principal Pyramide 6 Niveaux
══════════════════════════════════════════════════════════════
Responsabilités :
  - Orchestrer l'analyse pyramidale MN → W1 → D1 → H4 → H1 → M15
  - Agréger les scores FVG + OB + SMT + Bias par timeframe
  - Appliquer la cascade de confluence HTF → LTF
  - Calculer l'Entry Model ICT (entry, sl, tp, rr)
  - Produire le KB5_RESULT consommé par scoring_engine

Pyramide ICT KB5 :
  MN  (Monthly)  → Context macro, biais de fond         poids: 0.30
  W1  (Weekly)   → Structure hebdo, targets liquidité   poids: 0.25
  D1  (Daily)    → Biais journalier, PD Arrays majeurs  poids: 0.20
  H4  (4H)       → Structure intermédiaire, OB majeurs  poids: 0.12
  H1  (1H)       → Setup entry, FVG/OB d'entrée         poids: 0.08
  M15 (15min)    → Trigger précis, confirmation entry   poids: 0.05

Règle de cascade :
  Si score MN < 50 → tous les scores LTF plafonnés à 70
  Si score W1 < 50 → scores D1/H4/H1/M15 plafonnés à 75
  Si biais D1 NON aligné → pénalité -15 sur score global

Dépendances :
  - DataStore     → get_candles(), set_analysis()
  - FVGDetector   → get_fresh_fvg(), get_fvg_count()
  - OBDetector    → get_valid_ob(), get_nearest_ob(), get_bpr()
  - SMTDetector   → get_smt_score(), has_smt_confirmation()
  - BiasDetector  → get_bias(), get_bias_score(), get_pd_zone()
  - config.constants → Trading

Consommé par :
  - scoring_engine.py  (KB5_RESULT complet)
  - killswitch_engine.py (biais aligné check)
══════════════════════════════════════════════════════════════
"""

import logging
import threading
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Optional

from datastore.data_store import DataStore
from config.constants import (
    Trading, Score,
    MACROS, MACROS_PRIORITY_HIGH, MACROS_PRIORITY_MEDIUM,
    CBDR_START_H, CBDR_END_H, CBDR_EXPLOSIVE_PIPS,
)

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# POIDS PYRAMIDE KB5
# ══════════════════════════════════════════════════════════════

PYRAMID_WEIGHTS = {
    "MN":  0.30,
    "W1":  0.25,
    "D1":  0.20,
    "H4":  0.12,
    "H1":  0.08,
    "M15": 0.05,
}

PYRAMID_ORDER = ["MN", "W1", "D1", "H4", "H1", "M15"]

# Seuils cascade
CASCADE_MN_THRESHOLD  = 50   # si MN < 50 → plafond LTF
CASCADE_W1_THRESHOLD  = 50   # si W1 < 50 → plafond LTF
CASCADE_MN_CAP        = 55   # (AVANT: 70) Plafond très strict si MN contre nous
CASCADE_W1_CAP        = 65   # (AVANT: 75) Plafond strict si W1 contre nous
MISALIGN_PENALTY      = 15   # pénalité si D1 non aligné

# Bonus de confluence ICT
CONFLUENCE_FVG_OB       = 15   # FVG + OB même TF même direction
CONFLUENCE_SMT          = 10   # SMT confirmation présente
CONFLUENCE_BPR          = 8    # BPR dans la zone d'entrée
CONFLUENCE_KILLZONE     = 10   # setup dans Killzone ICT
CONFLUENCE_PD_ALIGN     = 12   # entrée cohérente Premium/Discount
CONFLUENCE_SWEEP        = 12   # Liquidity Sweep (Turtle Soup) confirmé
CONFLUENCE_MIDNIGHT     = 8    # entrée cohérente avec Midnight Open
CONFLUENCE_AMD_DISTRIB  = 15   # Phase Distribution active (AMD) — moment idéal
CONFLUENCE_AMD_SETUP    = 10   # Fin de Manipulation = setup imminient (AMD)
CONFLUENCE_MACRO_HIGH   = 15   # Setup DANS une Macro ICT haute priorité
CONFLUENCE_MACRO_LOW    = 8    # Setup DANS une Macro ICT secondaire
CONFLUENCE_ROUND_NUMBER = 8    # Prix proche d'un Chiffre Rond (psychologique)
CONFLUENCE_TRENDLINE    = 10   # Setup sur Ligne de Tendance validée
CONFLUENCE_ENGULFING    = 12   # Bougie Engulfing confirme la direction
CONFLUENCE_MSS_CONFIRM  = 15   # MSS confirme la direction (fort momentum)
CONFLUENCE_CHOCH        = 8    # CHoCH early warning aligné avec la direction
CONFLUENCE_IRL_TARGET   = 6    # Cible IRL identifiée (TP1 défini).

# ATR pour calcul SL/TP
ATR_PERIOD            = 14
SL_ATR_MULTIPLIER     = 0.3  # SL = 0.3 × ATR sous/sur le setup
TP_MIN_RR             = 0.5  # RR minimum acceptable

# ══════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════

class KB5Engine:
    """
    Moteur central du bot SENTINEL PRO KB5.
    Orchestre la pyramide d'analyse 6 niveaux et produit
    le KB5_RESULT complet prêt pour scoring_engine.

    Le KB5_RESULT contient :
      - scores par TF (MN→M15)
      - score agrégé pondéré
      - direction dominante
      - Entry Model (entry, sl, tp, rr)
      - structures actives (FVG, OB, BPR, SMT)
      - confluences détectées
      - invalidation condition
    """

    def __init__(self,
                 data_store,
                 fvg_detector,
                 ob_detector,
                 smt_detector,
                 bias_detector,
                 liquidity_detector=None,
                 amd_detector=None,
                 pa_detector=None,
                 mss_detector=None,
                 choch_detector=None,
                 irl_detector=None):
        self._ds    = data_store
        self._fvg   = fvg_detector
        self._ob    = ob_detector
        self._smt   = smt_detector
        self._bias  = bias_detector
        self._liq   = liquidity_detector   # LiquidityDetector (optionnel — rétrocompatible)
        self._amd   = amd_detector         # AMDDetector Power of 3 (optionnel)
        self._pa    = pa_detector          # PADetector Price Action pur (optionnel)
        self._mss   = mss_detector         # MSSDetector — cassure de structure (optionnel)
        self._choch = choch_detector       # CHoCHDetector — early warning (optionnel)
        self._irl   = irl_detector         # IRLDetector — cibles TP internes (optionnel)
        self._lock  = threading.Lock()
        self._cache: dict[str, dict] = {}
        logger.info("KB5Engine initialisé — Pyramide 6 niveaux + MSS/CHoCH/IRL prête")

    # ══════════════════════════════════════════════════════════
    # MÉTHODE PRINCIPALE
    # ══════════════════════════════════════════════════════════

    def analyze(self, pair: str) -> dict:
        """
        Analyse complète pyramidale pour une paire.
        Point d'entrée principal appelé par scoring_engine.

        Pipeline :
          1. Calculer biais global (BiasDetector)
          2. Scorer chaque TF MN→M15
          3. Appliquer cascade de confluence HTF
          4. Calculer score agrégé pondéré
          5. Identifier structures actives
          6. Calculer Entry Model (entry/sl/tp/rr)
          7. Retourner KB5_RESULT

        Args:
            pair: ex. "EURUSD"

        Returns:
            dict KB5_RESULT complet
        """
        now = datetime.now(timezone.utc)

        # ── Étape 1 : Biais global ──────────────────────────
        bias_result   = self._bias.analyze_pair(pair)
        direction     = bias_result.get("alignment", {}).get("direction", "NEUTRAL")
        bias_score    = bias_result.get("bias_score", 0)
        pd_zone       = bias_result.get("pd_zone", {}).get("zone", "UNKNOWN")
        in_killzone   = bias_result.get("in_killzone", False)
        bias_aligned  = bias_result.get("aligned", False)

        if direction == "NEUTRAL":
            logger.info(f"KB5 — {pair} | Biais NEUTRAL → KB5_RESULT vide retourné")
            return self._empty_result(pair, "BIAIS_NEUTRE")

        # ── Étape 2 : Scorer chaque TF ─────────────────────
        tf_scores: dict[str, dict] = {}
        for tf in PYRAMID_ORDER:
            tf_scores[tf] = self._score_timeframe(pair, tf, direction)

        # ── Étape 3 : Cascade HTF ──────────────────────────
        tf_scores = self._apply_cascade(tf_scores, bias_aligned)

        # ── Étape 4 : Score agrégé pondéré ─────────────────
        raw_score = sum(
            tf_scores[tf]["score"] * PYRAMID_WEIGHTS[tf]
            for tf in PYRAMID_ORDER
        )

        # ── Étape 5 : Bonus de confluence ──────────────────
        confluences = self._detect_confluences(
            pair, direction, pd_zone, in_killzone
        )
        confluence_bonus = sum(c["bonus"] for c in confluences)

        # Score final plafonné à 100
        # NOTE : scoring_engine a ses propres pondérations. On transmet le score KB5 brut.
        # Le plafond à 100 ici évite que la pyramide seule ne dépasse la logique.
        final_score = min(int(raw_score + confluence_bonus), 100)

        # ── Étape 6 : Entry Model ──────────────────────────
        entry_model = self._calculate_entry_model(
            pair, direction, tf_scores
        )

        # ── Étape 7 : Assemblage KB5_RESULT ────────────────
        result = {
            "pair":        pair,
            "timestamp":   now.isoformat(),
            "direction":   direction,

            # Scores pyramide
            "pyramid_scores": {
                tf: tf_scores[tf]["score"]
                for tf in PYRAMID_ORDER
            },
            "tf_details": tf_scores,

            # Score global
            "raw_score":       round(raw_score,    1),
            "confluence_bonus": confluence_bonus,
            "final_score":     final_score,

            # Biais
            "bias_score":   bias_score,
            "bias_aligned": bias_aligned,
            "pd_zone":      pd_zone,
            "in_killzone":  in_killzone,
            "session":      bias_result.get("session"),

            # Confluences actives
            "confluences":  confluences,

            # Entry Model
            "entry_model":  entry_model,

            # Structures actives (résumé)
            "structures":   self._get_active_structures(pair, direction),

            # IRL Targets (TP1, TP2, TP3 si disponibles)
            "irl_targets":  (
                self._irl.get_irl_targets(pair, direction)
                if self._irl is not None else []
            ),

            # Invalidation
            "invalidation": self._get_invalidation(pair, direction, entry_model),
        }

        with self._lock:
            self._cache[pair] = result

        self._ds.set_analysis(pair, "kb5", result)

        # Noms des confluences actives pour le log
        conf_names = ", ".join(c["name"] for c in confluences) if confluences else "aucune"
        logger.info(
            f"KB5 analysé — {pair} | "
            f"Direction : {direction} | "
            f"Score : {final_score} | "
            f"Confluences ({len(confluences)}) : {conf_names} | "
            f"RR : {entry_model.get('rr', 0)}"
        )

        return result

    # ══════════════════════════════════════════════════════════
    # SCORING PAR TIMEFRAME
    # ══════════════════════════════════════════════════════════

    def _score_timeframe(self, pair: str, tf: str,
                          direction: str) -> dict:
        """
        Calcule le score d'un timeframe donné (0→100).

        Composantes :
          - FVG frais dans la direction     (0→30 pts)
          - OB valide dans la direction     (0→30 pts)
          - Structure de prix (HH/HL)       (0→20 pts)
          - SMT confirmation sur ce TF      (0→20 pts)

        Args:
            pair:      ex. "EURUSD"
            tf:        ex. "H4"
            direction: "BULLISH" ou "BEARISH"

        Returns:
            dict {score, components, fvg_count, ob_count}
        """
        score = 0
        components = {}

        # ── FVG Score (0→30) ────────────────────────────────
        fvg_score = self._score_fvg(pair, tf, direction)
        score += fvg_score
        components["fvg"] = fvg_score

        # ── OB Score (0→30) ─────────────────────────────────
        ob_score = self._score_ob(pair, tf, direction)
        score += ob_score
        components["ob"] = ob_score

        # ── Structure Score (0→20) ──────────────────────────
        struct_score = self._score_structure(pair, tf, direction)
        score += struct_score
        components["structure"] = struct_score

        # ── SMT Score (0→20) ────────────────────────────────
        smt_raw = self._smt.get_smt_score(pair, direction)
        # Plafonner à 20 pts contribution par TF
        smt_score = min(int(smt_raw * 0.20), 20)
        score += smt_score
        components["smt"] = smt_score

        return {
            "score":      min(score, 100),
            "components": components,
            "fvg_count":  self._fvg.get_fvg_count(pair, tf),
            "ob_count":   self._ob.get_ob_count(pair, tf),
            "tf":         tf,
        }

    def _score_fvg(self, pair: str, tf: str,
                   direction: str) -> int:
        """
        Score FVG pour un TF donné (0→30 pts).

        Règle :
          - FVG FRESH dans la direction  : +20 pts
          - FVG MITIGATED (partiel)      : +10 pts
          - Ratio ATR élevé (> 1.0)      : +10 pts bonus
          - Multiple FVG frais           : +5 pts
        """
        fresh_fvg    = self._fvg.get_fresh_fvg(pair, tf, direction)
        mitig_fvg    = self._fvg.get_all_fvg(pair, tf, status="MITIGATED")
        mitig_dir    = [f for f in mitig_fvg if f["direction"] == direction]

        if not fresh_fvg and not mitig_dir:
            return 0

        score = 0
        if fresh_fvg:
            score += 20
            # Bonus ATR ratio (FVG significatif)
            best_ratio = max(f.get("atr_ratio", 0) for f in fresh_fvg)
            if best_ratio >= 1.0:
                score += 10
            # Bonus multi-FVG
            if len(fresh_fvg) >= 2:
                score += 5
        elif mitig_dir:
            score += 10

        return min(score, 30)

    def _score_ob(self, pair: str, tf: str,
                  direction: str) -> int:
        """
        Score OB pour un TF donné (0→30 pts).

        Règle :
          - OB VALID dans la direction   : +20 pts
          - OB TESTED (≥ 1 touch)        : +15 pts (déjà prouvé)
          - Breaker Block cohérent       : +10 pts
          - BPR présent                  : +10 pts
          - Ratio ATR élevé              : +5 pts
        """
        valid_ob  = self._ob.get_valid_ob(pair, tf, direction)
        breakers  = self._ob.get_breakers(pair, tf, direction)
        bpr_list  = self._ob.get_bpr(pair, tf)

        if not valid_ob and not breakers:
            return 0

        score = 0
        if valid_ob:
            # Préférer OB TESTED (déjà prouvé par le marché)
            tested = [o for o in valid_ob if o["status"] == "TESTED"]
            if tested:
                score += 15
                best_ratio = max(o.get("atr_ratio", 0) for o in tested)
            else:
                score += 20
                best_ratio = max(o.get("atr_ratio", 0) for o in valid_ob)

            if best_ratio >= 2.0:
                score += 5

        if breakers:
            score += 10

        if bpr_list:
            score += 10

        return min(score, 30)

    def _score_structure(self, pair: str, tf: str,
                          direction: str) -> int:
        """
        Score structure de prix sur un TF (0→20 pts).

        Règle :
          - Tendance confirmée (HH+HL ou LH+LL)  : +15 pts
          - Pas de CHoCH récent                  : +5 pts
          - Biais aligné avec direction           : inclus dans biais
        """
        df = self._ds.get_candles(pair, tf)
        if df is None or len(df) < 6:
            return 0

        highs  = df["high"].values[-6:]
        lows   = df["low"].values[-6:]

        hh = highs[-1] > highs[-3]
        hl = lows[-1]  > lows[-3]
        lh = highs[-1] < highs[-3]
        ll = lows[-1]  < lows[-3]

        score = 0
        if direction == "BULLISH":
            if hh and hl:
                score += 15
            elif hh or hl:
                score += 8
        else:  # BEARISH
            if lh and ll:
                score += 15
            elif lh or ll:
                score += 8

        # Pas de CHoCH récent = structure saine
        choch = self._bias.get_bias(pair)
        if choch:
            bias_shift = choch.get("bias_shift", {})
            if not bias_shift.get("detected", False):
                score += 5

        return min(score, 20)

    # ══════════════════════════════════════════════════════════
    # CASCADE HTF
    # ══════════════════════════════════════════════════════════

    def _apply_cascade(self, tf_scores: dict,
                        bias_aligned: bool) -> dict:
        """
        Applique les règles de cascade HTF sur les scores LTF.

        Règles :
          1. Si MN < 50 → plafond sur W1/D1/H4/H1/M15 = 70
          2. Si W1 < 50 → plafond sur D1/H4/H1/M15    = 75
          3. Si biais D1 non aligné → pénalité -15 globale

        Args:
            tf_scores:    dict scores par TF
            bias_aligned: alignement HTF (BiasDetector)

        Returns:
            dict scores mis à jour
        """
        mn_score = tf_scores["MN"]["score"]
        w1_score = tf_scores["W1"]["score"]

        # Règle 1 : MN faible
        if mn_score < CASCADE_MN_THRESHOLD:
            for tf in ["W1", "D1", "H4", "H1", "M15"]:
                if tf_scores[tf]["score"] > CASCADE_MN_CAP:
                    tf_scores[tf]["score"] = CASCADE_MN_CAP
                    tf_scores[tf]["capped"] = f"MN<{CASCADE_MN_THRESHOLD}"
            logger.debug(f"Cascade MN appliquée — plafond {CASCADE_MN_CAP}")

        # Règle 2 : W1 faible
        if w1_score < CASCADE_W1_THRESHOLD:
            for tf in ["D1", "H4", "H1", "M15"]:
                if tf_scores[tf]["score"] > CASCADE_W1_CAP:
                    tf_scores[tf]["score"] = CASCADE_W1_CAP
                    tf_scores[tf]["capped"] = f"W1<{CASCADE_W1_THRESHOLD}"
            logger.debug(f"Cascade W1 appliquée — plafond {CASCADE_W1_CAP}")

        # Règle 3 : biais non aligné
        if not bias_aligned:
            for tf in PYRAMID_ORDER:
                original = tf_scores[tf]["score"]
                tf_scores[tf]["score"] = max(0, original - MISALIGN_PENALTY)
            logger.debug(f"Pénalité misalignment appliquée : -{MISALIGN_PENALTY}")

        return tf_scores

    # ══════════════════════════════════════════════════════════
    # CONFLUENCES ICT
    # ══════════════════════════════════════════════════════════

    def _detect_confluences(self, pair: str, direction: str,
                             pd_zone: str,
                             in_killzone: bool) -> list:
        """
        Détecte toutes les confluences ICT actives et retourne
        la liste des bonus applicables au score final.

        Returns:
            liste de dicts {name, bonus, description}
        """
        confluences = []

        # ── Silver Bullet ICT (10h, 14h, 15h NY) ────────────
        if self._is_silver_bullet():
            confluences.append({
                "name":        "SILVER_BULLET",
                "bonus":       Score.BONUS_SILVER_BULLET,
                "description": "Exécution précise dans une fenêtre ICT Silver Bullet",
            })

        # ── Confluence FVG + OB même TF ─────────────────────
        for tf in ["H4", "H1", "M15"]:
            fresh_fvg = self._fvg.get_fresh_fvg(pair, tf, direction)
            valid_ob  = self._ob.get_valid_ob(pair, tf, direction)
            if fresh_fvg and valid_ob:
                confluences.append({
                    "name":        f"FVG_OB_{tf}",
                    "bonus":       CONFLUENCE_FVG_OB,
                    "description": f"FVG frais + OB valide alignés sur {tf}",
                    "tf":          tf,
                })
                break  # un seul bonus FVG+OB (éviter double-count)

        # ── SMT Confirmation ────────────────────────────────
        if self._smt.has_smt_confirmation(pair, direction):
            confluences.append({
                "name":        "SMT_CONFIRM",
                "bonus":       CONFLUENCE_SMT,
                "description": "SMT Divergence confirme la direction",
            })

        # ── BPR dans la zone ────────────────────────────────
        for tf in ["H4", "H1"]:
            bpr = self._ob.get_bpr(pair, tf)
            if bpr:
                confluences.append({
                    "name":        f"BPR_{tf}",
                    "bonus":       CONFLUENCE_BPR,
                    "description": f"Balanced Price Range présent sur {tf}",
                    "tf":          tf,
                })
                break

        # ── Killzone ICT ────────────────────────────────────
        if in_killzone:
            confluences.append({
                "name":        "KILLZONE",
                "bonus":       CONFLUENCE_KILLZONE,
                "description": "Setup dans une Killzone ICT",
            })

        # ── Premium/Discount cohérent ───────────────────────
        pd_ok = (
            (direction == "BULLISH" and pd_zone == "DISCOUNT") or
            (direction == "BEARISH" and pd_zone == "PREMIUM")
        )
        if pd_ok:
            confluences.append({
                "name":        "PD_ALIGN",
                "bonus":       CONFLUENCE_PD_ALIGN,
                "description": f"Entrée en zone {pd_zone} cohérente avec {direction}",
            })

        # ── Liquidity Sweep (Turtle Soup) ────────────────────
        # Le signal le plus puissant en ICT : la liquidité a été prise
        # dans le sens INVERSE du trade → les institutions ont leur carburant.
        if self._liq is not None:
            if self._liq.has_fresh_sweep(pair, direction):
                sweeps = self._liq.get_sweeps(pair, status="FRESH",
                                              direction=direction)
                best = sweeps[0] if sweeps else None
                confluences.append({
                    "name":        "LIQUIDITY_SWEEP",
                    "bonus":       CONFLUENCE_SWEEP,
                    "description": (
                        f"Sweep {best['pool_type']} ({best['pool_level']}) "
                        f"confirmé ({best['atr_ratio']}× ATR)"
                        if best else "Liquidity Sweep FRESH détecté"
                    ),
                    "sweep":       best,
                })

        # ── Midnight Open (pivot institutionnel 00h00 UTC) ───
        # Idéal : on entre en-dessous du MO pour BULLISH,
        # au-dessus du MO pour BEARISH.
        if self._liq is not None:
            mo = self._liq.get_midnight_open(pair)
            if mo is not None:
                is_above_mo = self._liq.is_price_above_midnight(pair)
                mo_ok = (
                    (direction == "BULLISH" and is_above_mo is False) or
                    (direction == "BEARISH" and is_above_mo is True)
                )
                if mo_ok:
                    confluences.append({
                        "name":        "MIDNIGHT_OPEN",
                        "bonus":       CONFLUENCE_MIDNIGHT,
                        "description": (
                            f"Entrée {'en Discount' if direction == 'BULLISH' else 'en Premium'} "
                            f"par rapport au Midnight Open ({mo['level']})"
                        ),
                        "mo_level":    mo["level"],
                    })

        # ── AMD (Power of 3) — Phase Distribution ou Setup post-Manip ──
        # La Distribution ICT est la fenêtre idéale d'exécution.
        # La Manipulation active est un FILTRE (bloquer les trades suiveurs)
        if self._amd is not None:
            amd_state   = self._amd.get_amd_state(pair, tf="H1")
            amd_phase   = amd_state.get("phase", "UNKNOWN")
            amd_profile = amd_state.get("profile", "UNKNOWN")
            amd_conf    = amd_state.get("confidence", "NONE")
            manip_data  = amd_state.get("manip", {})
            distrib_data = amd_state.get("distrib", {})

            # Bonus Distribution : on est dans la fenetre d'expansion ideale
            if self._amd.is_distribution_active(pair, tf="H1"):
                distrib_dir = distrib_data.get("direction", "")
                profile_ok  = (
                    (direction == "BULLISH" and distrib_dir == "BULLISH") or
                    (direction == "BEARISH" and distrib_dir == "BEARISH")
                )
                if profile_ok:
                    strength = distrib_data.get("strength", "MODERATE")
                    confluences.append({
                        "name":        "AMD_DISTRIBUTION",
                        "bonus":       CONFLUENCE_AMD_DISTRIB,
                        "description": (
                            f"Phase Distribution ICT active — MSS {distrib_dir} "
                            f"({strength}) → c'est le VRAI mouvement directionnel"
                        ),
                        "amd_phase":   amd_phase,
                        "strength":    strength,
                    })

            # Bonus Setup post-Manipulation : Judas Swing vient de se terminer
            elif self._amd.is_manipulation_active(pair, tf="H1"):
                manip_dir = manip_data.get("direction", "")
                # Le setup est bon si on trade dans la direction prevue par la Manip
                anticipated_bias = manip_data.get("intended_bias", "")
                if direction == anticipated_bias:
                    confluences.append({
                        "name":        "AMD_POST_MANIPULATION",
                        "bonus":       CONFLUENCE_AMD_SETUP,
                        "description": (
                            f"Judas Swing {manip_dir} en cours — "
                            f"setup d'entrée aligne avec le biais réel ({anticipated_bias})"
                        ),
                        "amd_phase":   amd_phase,
                        "manip_dir":   manip_dir,
                    })

        # ── C. ICT Macros (Fenêtres algorithmiques spécifiques) ──
        # Verifier si l'heure courante est dans une fenetre Macro ICT.
        # Les Macros sont des periodes de 20-27 minutes ou les algos
        # interbancaires deplacent agressivement les prix.
        # Les heures MACROS sont en EST (UTC-5).
        now_utc = datetime.now(timezone.utc)
        now_est_h = (now_utc.hour - 5) % 24
        now_est_m = now_utc.minute

        # Detection CBDR explosif (Central Bank Dealers Range)
        # Si CBDR soir > CBDR_EXPLOSIVE_PIPS, les Macros 1/2/8 sont suspendues
        cbdr_explosive = False
        df_h1_macro = self._ds.get_candles(pair, "H1")
        if df_h1_macro is not None and len(df_h1_macro) >= 6:
            try:
                # On estime le CBDR sur les bougies 17h-20h EST
                cbdr_highs, cbdr_lows = [], []
                times = df_h1_macro.index if hasattr(df_h1_macro.index, '__iter__') \
                        else df_h1_macro["time"]
                for i in range(len(df_h1_macro) - 10, len(df_h1_macro)):
                    if i < 0:
                        continue
                    t_est_h = (int(pd.to_datetime(times[i]).hour) - 5) % 24
                    if CBDR_START_H <= t_est_h < CBDR_END_H:
                        cbdr_highs.append(float(df_h1_macro["high"].values[i]))
                        cbdr_lows.append(float(df_h1_macro["low"].values[i]))
                if cbdr_highs and cbdr_lows:
                    cbdr_range = max(cbdr_highs) - min(cbdr_lows)
                    # Convertir en pips (approximation Forex 5D)
                    cbdr_pips = cbdr_range * 10000
                    cbdr_explosive = cbdr_pips > CBDR_EXPLOSIVE_PIPS
            except Exception:
                pass

        active_macro = None
        for macro_id, macro in MACROS.items():
            sh, sm = macro["start"]
            eh, em = macro["end"]
            # Convertir en minutes depuis minuit EST pour comparer facilement
            start_m = sh * 60 + sm
            end_m   = eh * 60 + em
            now_m   = now_est_h * 60 + now_est_m
            in_window = start_m <= now_m < end_m

            if in_window:
                # Suspendre les Macros 1, 2, 8 si CBDR explosif
                if cbdr_explosive and macro_id in (1, 2, 8):
                    logger.debug(
                        f"Macro {macro['name']} SUSPENDUE — CBDR explosif detecte"
                    )
                    break

                active_macro = {"id": macro_id, **macro}
                break

        if active_macro is not None:
            is_high_priority = active_macro["id"] in MACROS_PRIORITY_HIGH
            bonus = CONFLUENCE_MACRO_HIGH if is_high_priority else CONFLUENCE_MACRO_LOW
            confluences.append({
                "name":        "ICT_MACRO",
                "bonus":       bonus,
                "description": (
                    f"Setup DANS la Macro ICT {active_macro['name']} — "
                    f"fenetre algorithmique {'HAUTE' if is_high_priority else 'SECONDAIRE'} priorite"
                ),
                "macro_name":     active_macro["name"],
                "macro_priority": "HIGH" if is_high_priority else "LOW",
                "cbdr_explosive": cbdr_explosive,
            })

        # ── E. Price Action Pur (PADetector) ──────────────────
        if self._pa is not None:
            # E1 - Round Numbers
            near_rounds = self._pa.get_near_round_numbers(pair)
            if near_rounds:
                # Prendre le plus proche
                rn = near_rounds[0]
                rn_side = rn.get("side", "")
                rn_str  = rn.get("strength", "MINOR")
                rn_ok = (
                    (direction == "BULLISH" and rn_side == "BELOW") or
                    (direction == "BEARISH" and rn_side == "ABOVE")
                )
                if rn_ok:
                    confluences.append({
                        "name":        "ROUND_NUMBER",
                        "bonus":       CONFLUENCE_ROUND_NUMBER,
                        "description": (
                            f"Chiffre Rond {'MAJEUR' if rn_str == 'MAJOR' else 'secondaire'} "
                            f"{rn['level']} a {rn['distance']:.5f} du prix courant"
                        ),
                        "level":    rn["level"],
                        "strength": rn_str,
                    })

            # E2 - Trendlines
            trendlines = self._pa.get_active_trendlines(pair)
            for tl in trendlines:
                tl_ok = (
                    (direction == "BULLISH" and tl["type"] == "BULLISH_TL") or
                    (direction == "BEARISH" and tl["type"] == "BEARISH_TL")
                )
                if tl_ok and tl.get("near"):
                    confluences.append({
                        "name":        "TRENDLINE",
                        "bonus":       CONFLUENCE_TRENDLINE,
                        "description": (
                            f"Setup sur Trendline {tl['type']} "
                            f"(valeur courante: {tl['current_value']}, "
                            f"dist: {tl['price_distance']:.5f})"
                        ),
                        "tl_type":     tl["type"],
                        "current_val": tl["current_value"],
                    })
                    break  # Une seule trendline confluence

            # E3 - Engulfing (H1 d'abord, M15 en fallback)
            for tf_eng in ("H1", "M15"):
                engulf = self._pa.get_engulfing(pair, tf=tf_eng, direction=direction)
                if engulf.get("type") != "NONE":
                    confluences.append({
                        "name":        "ENGULFING",
                        "bonus":       CONFLUENCE_ENGULFING,
                        "description": (
                            f"Bougie {engulf['type']} detectee sur {tf_eng} "
                            f"({engulf.get('strength', '')}) — "
                            f"ratio corps: {engulf.get('body_ratio', 0):.1f}x"
                        ),
                        "engulf_type": engulf["type"],
                        "strength":    engulf.get("strength"),
                        "tf":          tf_eng,
                    })
                    break  # Un seul Engulfing confluence

        # ── F. MSS (Market Structure Shift) ──────────────────
        # Un MSS haussier (ou baissier) dans la direction → forte confirmation
        if self._mss is not None:
            mss_dom = self._mss.get_dominant_mss(pair)
            if mss_dom.get("detected") and mss_dom.get("fresh"):
                mss_dir = mss_dom.get("direction", "")
                if mss_dir == direction:
                    strength = mss_dom.get("strength", "MODERATE")
                    confluences.append({
                        "name":        "MSS_CONFIRM",
                        "bonus":       CONFLUENCE_MSS_CONFIRM,
                        "description": (
                            f"MSS {direction} confirmé sur {mss_dom.get('tf', 'N/A')} "
                            f"— Niveau cassé: {mss_dom.get('break_level')} "
                            f"({'FORT' if strength == 'STRONG' else 'MODÉRÉ'})"
                        ),
                        "mss_tf":      mss_dom.get("tf"),
                        "mss_level":   mss_dom.get("break_level"),
                        "strength":    strength,
                    })

        # ── G. CHoCH (Change of Character) early warning ─────
        # Un CHoCH aligné avec la direction = confirmation LTF supplémentaire
        if self._choch is not None:
            choch_dom = self._choch.get_dominant_choch(pair)
            if choch_dom.get("detected") and choch_dom.get("fresh"):
                choch_dir = choch_dom.get("direction", "")
                if choch_dir == direction:
                    confluences.append({
                        "name":        "CHOCH_CONFIRM",
                        "bonus":       CONFLUENCE_CHOCH,
                        "description": (
                            f"CHoCH {direction} détecté sur {choch_dom.get('tf', 'N/A')} "
                            f"— Premier signe de changement de structure"
                        ),
                        "choch_tf":    choch_dom.get("tf"),
                        "choch_level": choch_dom.get("break_level"),
                    })

        # ── H. IRL (Internal Range Liquidity) take-profit ────
        # Si une cible IRL est disponible dans la direction → TP1 calculé
        if self._irl is not None:
            irl_target = self._irl.get_best_target(pair, direction)
            if irl_target:
                confluences.append({
                    "name":        "IRL_TARGET",
                    "bonus":       CONFLUENCE_IRL_TARGET,
                    "description": (
                        f"Cible IRL identifiée : {irl_target['type']} "
                        f"@ {irl_target['level']} (TF: {irl_target.get('tf', 'N/A')}) "
                        f"— TP1 objectif intermédiaire précis"
                    ),
                    "irl_level":   irl_target.get("level"),
                    "irl_type":    irl_target.get("type"),
                    "irl_tf":      irl_target.get("tf"),
                })

        return confluences


    # ══════════════════════════════════════════════════════════
    # ENTRY MODEL ICT
    # ══════════════════════════════════════════════════════════

    def _calculate_entry_model(self, pair: str, direction: str,
                                tf_scores: dict) -> dict:
        """
        Calcule le modèle d'entrée ICT optimal.

        Logique de priorité pour l'entrée :
          1. OB H1 TESTED le plus proche du prix actuel
          2. FVG H1 FRESH midpoint si pas d'OB
          3. BPR H1 midpoint si présent
          4. Prix marché courant comme fallback

        SL = low/high de la structure H1 - 1.5 × ATR H1
        TP = prochain niveau de liquidité HTF (high/low D1)
        RR = (TP - entry) / (entry - SL)

        Returns:
            dict {entry, sl, tp, rr, entry_type, entry_basis}
        """
        df_h1 = self._ds.get_candles(pair, "H1")
        if df_h1 is None or len(df_h1) < ATR_PERIOD + 1:
            return self._empty_entry_model("H1 insuffisant")

        current_price = float(df_h1["close"].iloc[-1])
        atr_h1        = self._calculate_atr(df_h1)

        # ── Trouver la zone d'entrée ────────────────────────
        entry        = None
        entry_basis  = None
        entry_type   = "LIMIT"

        # Priorité 1 : OB H1
        nearest_ob = self._ob.get_nearest_ob(pair, "H1",
                                              current_price, direction)
        if nearest_ob:
            ob_mid   = (nearest_ob["top"] + nearest_ob["bottom"]) / 2
            entry    = round(ob_mid, 6)
            entry_basis = f"OB_H1_{nearest_ob['status']}"
            entry_type  = "LIMIT"

        # Priorité 2 : FVG H1
        if entry is None:
            nearest_fvg = self._fvg.get_nearest_fvg(
                pair, "H1", current_price, direction
            )
            if nearest_fvg:
                entry       = round(nearest_fvg["midpoint"], 6)
                entry_basis = f"FVG_H1_{nearest_fvg['type']}"
                entry_type  = "LIMIT"

        # Priorité 3 : BPR H1
        if entry is None:
            bpr = self._ob.get_bpr(pair, "H1")
            if bpr:
                entry       = round(bpr[0]["midpoint"], 6)
                entry_basis = "BPR_H1"
                entry_type  = "LIMIT"

        # Fallback : prix marché
        if entry is None:
            entry       = round(current_price, 6)
            entry_basis = "MARKET"
            entry_type  = "MARKET"

        # ── SL : structure H1 + ATR buffer ──────────────────
        if direction == "BULLISH":
            if nearest_ob:
                sl = round(float(nearest_ob["bottom"]) - (0.3 * atr_h1), 6)
            elif nearest_fvg:
                sl = round(float(nearest_fvg["bottom"]) - (0.3 * atr_h1), 6)
            else:
                swing_low = float(df_h1["low"].iloc[-5:].min())
                sl = round(swing_low - (0.3 * atr_h1), 6)
        else:  # BEARISH
            if nearest_ob:
                sl = round(float(nearest_ob["top"]) + (0.3 * atr_h1), 6)
            elif nearest_fvg:
                sl = round(float(nearest_fvg["top"]) + (0.3 * atr_h1), 6)
            else:
                swing_high = float(df_h1["high"].iloc[-5:].max())
                sl = round(swing_high + (0.3 * atr_h1), 6)


        # ── TP : Cible DOL prioritaire (Liquidity Pool) puis fallback D1 ──
        df_d1 = self._ds.get_candles(pair, "D1")
        tp    = None
        tp_basis = "D1_RANGE"

        # Priorité 1 : DOL (Draw on Liquidity) depuis LiquidityDetector
        if self._liq is not None:
            dol = self._liq.get_dol(pair)
            if (dol.get("direction") == direction and
                    dol.get("target_level") is not None and
                    dol.get("confidence") in ("HIGH", "MODERATE")):
                dol_tp = dol["target_level"]
                # Vérifier que le DOL est dans la bonne direction
                if direction == "BULLISH" and dol_tp > entry:
                    tp       = round(dol_tp, 6)
                    tp_basis = f"DOL_{dol['target_type']}"
                elif direction == "BEARISH" and dol_tp < entry:
                    tp       = round(dol_tp, 6)
                    tp_basis = f"DOL_{dol['target_type']}"

        # Priorité 2 : Fallback D1 max/min (méthode originale)
        if tp is None and df_d1 is not None and len(df_d1) >= 5:
            if direction == "BULLISH":
                tp = round(float(df_d1["high"].iloc[-5:].max()), 6)
                if tp <= entry:
                    tp = round(entry + (atr_h1 * 4), 6)
            else:  # BEARISH
                tp = round(float(df_d1["low"].iloc[-5:].min()), 6)
                if tp >= entry:
                    tp = round(entry - (atr_h1 * 4), 6)

        # Fallback TP
        if tp is None:
            multiplier = TP_MIN_RR * abs(entry - sl)
            tp = round(
                entry + multiplier if direction == "BULLISH"
                else entry - multiplier,
                6
            )

        # ── RR ──────────────────────────────────────────────
        risk   = abs(entry - sl)
        reward = abs(tp - entry)
        rr     = round(reward / risk, 2) if risk > 0 else 0.0

        # Vérifier RR minimum
        rr_valid = rr >= TP_MIN_RR

        if not rr_valid:
            logger.warning(
                f"Entry Model — {pair} | RR insuffisant : {rr} < {TP_MIN_RR} | "
                f"Entry : {entry} | SL : {sl} | TP : {tp}"
            )

        return {
            "entry":       entry,
            "sl":          sl,
            "tp":          tp,
            "rr":          rr,
            "rr_valid":    rr_valid,
            "entry_type":  entry_type,
            "entry_basis": entry_basis,
            "atr_h1":      round(atr_h1, 6),
            "risk_pips":   round(risk,   6),
            "reward_pips": round(reward, 6),
        }

    # ══════════════════════════════════════════════════════════
    # STRUCTURES ACTIVES (RÉSUMÉ)
    # ══════════════════════════════════════════════════════════

    def _get_active_structures(self, pair: str,
                                direction: str) -> dict:
        """
        Résumé des structures actives par catégorie.
        Utilisé par scoring_engine et Dashboard Patron.

        Returns:
            dict {fvg, ob, bpr, smt, bias}
        """
        best_fvg = None
        best_ob  = None

        for tf in ["H1", "H4", "D1"]:
            if best_fvg is None:
                fresh = self._fvg.get_fresh_fvg(pair, tf, direction)
                if fresh:
                    best_fvg = {"tf": tf, "count": len(fresh),
                                "type": fresh[0]["type"]}

            if best_ob is None:
                valid = self._ob.get_valid_ob(pair, tf, direction)
                if valid:
                    best_ob = {"tf": tf, "count": len(valid),
                               "status": valid[0]["status"]}

        smt_signal = self._smt.get_strongest_signal(pair, direction)
        bias_snap  = self._bias.get_snapshot(pair)

        return {
            "fvg":  best_fvg,
            "ob":   best_ob,
            "bpr":  bool(self._ob.get_bpr(pair, "H1") or
                         self._ob.get_bpr(pair, "H4")),
            "smt":  {
                "detected": smt_signal is not None,
                "strength": smt_signal.get("strength") if smt_signal else None,
            },
            "bias": {
                "weekly":  bias_snap.get("weekly"),
                "daily":   bias_snap.get("daily"),
                "sod":     bias_snap.get("sod"),
                "aligned": bias_snap.get("aligned"),
            },
        }

    # ══════════════════════════════════════════════════════════
    # INVALIDATION
    # ══════════════════════════════════════════════════════════

    def _get_invalidation(self, pair: str, direction: str,
                           entry_model: dict) -> dict:
        """
        Définit la condition d'invalidation du setup KB5.

        Un setup est invalidé quand :
          BULLISH → price ferme sous le SL OU sous le dernier OB Bull H1
          BEARISH → price ferme au-dessus du SL OU au-dessus du dernier OB Bear H1

        Returns:
            dict {condition, price_level, description}
        """
        sl = entry_model.get("sl", 0)

        nearest_ob = self._ob.get_nearest_ob(
            pair, "H1",
            entry_model.get("entry", 0),
            direction
        )

        if direction == "BULLISH":
            invalidation_level = sl
            condition = "CLOSE_BELOW_SL"
            if nearest_ob:
                invalidation_level = min(sl, nearest_ob["bottom"])
                condition = "CLOSE_BELOW_OB_OR_SL"
        else:
            invalidation_level = sl
            condition = "CLOSE_ABOVE_SL"
            if nearest_ob:
                invalidation_level = max(sl, nearest_ob["top"])
                condition = "CLOSE_ABOVE_OB_OR_SL"

        return {
            "condition":   condition,
            "price_level": round(invalidation_level, 6),
            "description": (
                f"Setup invalide si price {condition.replace('_', ' ').lower()} "
                f"{invalidation_level}"
            ),
        }

    # ══════════════════════════════════════════════════════════
    # CALCUL ATR
    # ══════════════════════════════════════════════════════════

    def _calculate_atr(self, df: pd.DataFrame,
                       period: int = ATR_PERIOD) -> float:
        """ATR sur `period` bougies. Fallback 0.0001."""
        if len(df) < period + 1:
            return 0.0001

        high  = df["high"].values
        low   = df["low"].values
        close = df["close"].values

        tr_list = [
            max(high[i] - low[i],
                abs(high[i]  - close[i - 1]),
                abs(low[i]   - close[i - 1]))
            for i in range(1, len(df))
        ]

        atr = float(np.mean(tr_list[-period:]))
        return atr if atr > 0 else 0.0001

    # ══════════════════════════════════════════════════════════
    # UTILITAIRES
    # ══════════════════════════════════════════════════════════

    def _empty_result(self, pair: str, reason: str) -> dict:
        """Retourne un KB5_RESULT vide standardisé."""
        return {
            "pair":            pair,
            "timestamp":       datetime.now(timezone.utc).isoformat(),
            "direction":       "NEUTRAL",
            "pyramid_scores":  {tf: 0 for tf in PYRAMID_ORDER},
            "tf_details":      {},
            "raw_score":       0,
            "confluence_bonus": 0,
            "final_score":     0,
            "bias_score":      0,
            "bias_aligned":    False,
            "pd_zone":         "UNKNOWN",
            "in_killzone":     False,
            "confluences":     [],
            "entry_model":     self._empty_entry_model(reason),
            "structures":      {},
            "invalidation":    {},
            "reason":          reason,
        }

    def _empty_entry_model(self, reason: str) -> dict:
        """Retourne un Entry Model vide standardisé."""
        return {
            "entry": None, "sl": None, "tp": None,
            "rr": 0.0, "rr_valid": False,
            "entry_type": None, "entry_basis": None,
            "reason": reason,
        }

    # ══════════════════════════════════════════════════════════
    # API PUBLIQUE
    # ══════════════════════════════════════════════════════════

    def get_result(self, pair: str) -> Optional[dict]:
        """
        Retourne le dernier KB5_RESULT calculé.

        Returns:
            dict KB5_RESULT ou None
        """
        with self._lock:
            return dict(self._cache.get(pair, {})) or None

    def get_final_score(self, pair: str) -> int:
        """
        Retourne le score final 0→100.
        Raccourci pour scoring_engine.
        """
        with self._lock:
            return self._cache.get(pair, {}).get("final_score", 0)

    def get_entry_model(self, pair: str) -> dict:
        """
        Retourne l'Entry Model pour order_manager.

        Returns:
            dict {entry, sl, tp, rr, entry_type}
        """
        with self._lock:
            return self._cache.get(pair, {}).get(
                "entry_model", self._empty_entry_model("non calculé")
            )

    def get_snapshot(self, pair: str) -> dict:
        """Snapshot compact pour Dashboard Patron."""
        with self._lock:
            result = dict(self._cache.get(pair, {}))

        if not result:
            return {"pair": pair, "status": "non calculé"}

        return {
            "pair":       pair,
            "direction":  result.get("direction"),
            "score":      result.get("final_score"),
            "rr":         result.get("entry_model", {}).get("rr"),
            "pd_zone":    result.get("pd_zone"),
            "in_killzone":result.get("in_killzone"),
            "aligned":    result.get("bias_aligned"),
            "confluences":len(result.get("confluences", [])),
            "pyramid":    result.get("pyramid_scores"),
        }

    def _is_silver_bullet(self) -> bool:
        """
        Vérifie si l'heure actuelle correspond à l'une des 3 fenêtres
        Silver Bullet ICT (Heures d'ouverture avec fort afflux de liquidité).
        Heures officielles ICT (Heure de New York ET) :
          - London SB : 03:00 - 04:00 AM (08:00 - 09:00 UTC)
          - AM SB     : 10:00 - 11:00 AM (15:00 - 16:00 UTC)
          - PM SB     : 02:00 - 03:00 PM (19:00 - 20:00 UTC)
        """
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            # Fallback pour versions antérieures à Python 3.9
            # On utilisera un décalage fixe si ZoneInfo n'est pas dispo
            ZoneInfo = None

        now_utc = datetime.now(timezone.utc)
        
        if ZoneInfo:
            try:
                test_ny = now_utc.astimezone(ZoneInfo("America/New_York"))
            except Exception:
                # Fallback si TZ info n'est pas installé sur le système
                test_ny = now_utc - timedelta(hours=4) # EDT approximatif
        else:
            test_ny = now_utc - timedelta(hours=4)

        ny_hour = test_ny.hour
        
        # Période valide : de HH:00 à HH:59 (1h complète)
        if ny_hour in [3, 10, 14]:
            return True

        return False

    def clear_cache(self, pair: str = None) -> None:
        """Vide le cache KB5."""
        with self._lock:
            if pair:
                self._cache.pop(pair, None)
                logger.info(f"KB5 cache vidé — Paire : {pair}")
            else:
                self._cache.clear()
                logger.info("KB5 cache vidé — toutes les paires")

    def __repr__(self) -> str:
        pairs = list(self._cache.keys())
        return f"KB5Engine(pairs={pairs}, weights={PYRAMID_WEIGHTS})"
