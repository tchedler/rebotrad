# analysis/scoring_engine.py
"""
══════════════════════════════════════════════════════════════
Sentinel Pro KB5 — Moteur de Scoring Final
══════════════════════════════════════════════════════════════
Responsabilités :
  - Agréger KB5Engine + KillSwitches + CircuitBreaker + Bias
  - Calculer le score final 0→100
  - Produire le verdict EXECUTE / WATCH / NO_TRADE
  - Attribuer le grade A+/A/A-/B+/B/B-/C
  - Appliquer les overrides KS et CB
  - Valider le RR minimum avant EXECUTE
  - Produire le SCALP_OUTPUT complet pour order_manager
  - Maintenir l'historique des verdicts pour audit

Hiérarchie des décisions :
  1. KS99 actif (Gateway)       → NO_TRADE forcé
  2. CB ≥ 2 (Pause/Halt)        → NO_TRADE forcé
  3. KS bloquant actif           → NO_TRADE forcé
  4. Score < 15                  → NO_TRADE
  5. RR < 0.5                    → NO_TRADE (même si score ≥ 80)
  6. Biais non aligné            → NO_TRADE (même si score ≥ 65)
  7. Score 15-79                 → WATCH (alerte Patron)
  8. Score ≥ 80 + tous filtres   → EXECUTE

Seuils de score :
  EXECUTE  : ≥ 80   → ordre automatique
  WATCH    : 15-79  → alerte Patron, pas d'ordre auto
  NO_TRADE : < 15   → log raison, aucune action

Dépendances :
  - KB5Engine          → get_result(), get_entry_model()
  - KillSwitchEngine   → evaluate(), get_blocking_ks()
  - CircuitBreaker     → get_level(), get_size_factor()
  - BiasDetector       → get_bias_score(), is_aligned()
  - DataStore          → set_analysis()
  - config.constants   → Trading, Risk

Consommé par :
  - order_manager.py      → SCALP_OUTPUT si EXECUTE
  - supervisor.py         → monitoring verdict global
  - patron_dashboard.py   → affichage temps réel
══════════════════════════════════════════════════════════════
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from datastore.data_store import DataStore
from analysis.boolean_erl import BooleanERL
from analysis.scoring_v4 import ScoringV4
from analysis.ote_detector import OTEDetector
from analysis.cisd_detector import CISDDetector

from config.constants import Trading, Risk

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# SEUILS ET CONSTANTES
# ══════════════════════════════════════════════════════════════

SCORE_EXECUTE_SCALP    = 75   # Scalp M15/M5
SCORE_EXECUTE_INTRADAY = 80   # Intraday H4/H1
SCORE_EXECUTE_SWING    = 85   # Swing D1/W1
SCORE_EXECUTE          = 75   # Seuil global minimum
SCORE_WATCH            = 15   # → alerte Patron
SCORE_NO_TRADE         = 15   # → NO_TRADE si < 15
# Classification automatique du trade type
TRADE_TYPE_THRESHOLDS = {
    "SCALP":    ["M15", "M5"],
    "INTRADAY": ["H1", "H4"],
    "SWING":    ["D1", "W1", "MN"],
}

def infer_trade_type(dominant_tf: str) -> str:
    """Retourne SCALP, INTRADAY ou SWING selon le TF dominant."""
    for trade_type, tfs in TRADE_TYPE_THRESHOLDS.items():
        if dominant_tf in tfs:
            return trade_type
    return "INTRADAY"  # défaut

def get_execute_threshold(trade_type: str) -> int:
    """Retourne le seuil EXECUTE selon le type de trade."""
    thresholds = {
        "SCALP":    SCORE_EXECUTE_SCALP,
        "INTRADAY": SCORE_EXECUTE_INTRADAY,
        "SWING":    SCORE_EXECUTE_SWING,
    }
    return thresholds.get(trade_type, SCORE_EXECUTE)

RR_MINIMUM_SCALP    = 1.5   # Scalp M15/M5
RR_MINIMUM_INTRADAY = 2.0   # Intraday H4/H1
RR_MINIMUM_SWING    = 2.0   # Swing D1/W1
RR_MINIMUM          = 2.0   # Seuil global minimum

# Poids agrégation score final
WEIGHT_KB5       = 0.60  # score pyramide KB5
WEIGHT_BIAS      = 0.25  # score biais directionnel
WEIGHT_SMT       = 0.15  # score SMT (via KB5 structures)

# Grades par score
GRADE_MAP = [
    (92, "A+"),
    (85, "A"),
    (80, "A-"),
    (75, "B+"),
    (70, "B"),
    (65, "B-"),
    (0,  "C"),
]

# ══════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════

class ScoringEngine:
    """
    Juge final du système SENTINEL PRO KB5.
    Agrège toutes les analyses et produit le SCALP_OUTPUT
    avec verdict EXECUTE / WATCH / NO_TRADE.

    Le SCALP_OUTPUT est l'objet unique consommé par order_manager.py
    pour décider d'envoyer ou non un ordre à MT5.
    """

    def __init__(self,
                 data_store: DataStore,
                 kb5_engine,
                 killswitch_engine,
                 circuit_breaker,
                 bias_detector):
        self._ds   = data_store
        self._kb5  = kb5_engine
        self._ks   = killswitch_engine
        self._cb   = circuit_breaker
        self._bias = bias_detector
        self._erl = BooleanERL(data_store, kb5_engine._liq
            if hasattr(kb5_engine, '_liq') else None)
        self._ote      = OTEDetector(data_store)
        self._cisd     = CISDDetector(data_store)
        liq            = getattr(kb5_engine, '_liq', None)

        self._scoring_v4 = ScoringV4(
            liquidity_detector = liq,
            ote_detector       = self._ote,
            cisd_detector      = self._cisd,
        )

        self._lock = threading.RLock()

        # Cache des derniers SCALP_OUTPUTs par paire
        self._cache: dict[str, dict] = {}

        # Historique verdicts (tous les setups évalués)
        self._history: list[dict] = []

        logger.info("ScoringEngine initialisé — Juge KB5 prêt")

    # ══════════════════════════════════════════════════════════
    # MÉTHODE PRINCIPALE — ÉVALUATION COMPLÈTE
    # ══════════════════════════════════════════════════════════

    def evaluate(self, pair: str, direction: str = None) -> dict:
        """
        Évaluation complète et production du SCALP_OUTPUT.
        Point d'entrée principal appelé par supervisor.py.

        Pipeline :
          1. Lancer l'analyse KB5 complète (pyramide + entry)
          2. Évaluer tous les KillSwitches
          3. Lire le niveau Circuit Breaker
          4. Calculer le score agrégé final
          5. Appliquer les overrides (KS / CB / RR / Biais)
          6. Attribuer grade et verdict
          7. Assembler le SCALP_OUTPUT
          8. Logger et stocker

        Args:
            pair:      ex. "EURUSD"
            direction: override directionnel optionnel

        Returns:
            dict SCALP_OUTPUT complet
        """
        now = datetime.now(timezone.utc)

        # ── Étape 1 : Analyse KB5 ───────────────────────────
        kb5_result = self._kb5.analyze(pair)
        kb5_direction = kb5_result.get("direction", "NEUTRAL")

        # Utiliser direction KB5 si pas d'override
        final_direction = direction or kb5_direction

        if final_direction == "NEUTRAL":
            return self._build_no_trade(
                pair, 0, "BIAIS_NEUTRE",
                "Aucun biais directionnel détecté",
                kb5_result, {}, now
            )

        # ── Étape 2 : KillSwitches ──────────────────────────
        ks_result = self._ks.evaluate(pair, final_direction)

        # ── Étape 3 : Circuit Breaker ───────────────────────
        cb_level      = self._cb.get_level()
        cb_size_factor= self._cb.get_size_factor()
        trading_ok    = self._cb.is_trading_allowed()

        # ── Étape 4 : Score agrégé pondéré ──────────────────────────
        # La pyramide KB5 est sur 100 (poids 60%)
        # Le Biais est sur 100 (poids 25%)
        # Le SMT est un bonus capé à 100 (poids 15%)
        kb5_score  = kb5_result.get("final_score",  0)
        bias_score = self._bias.get_bias_score(pair)
        smt_score  = self._get_smt_contribution(kb5_result)

        raw_score = (
            (kb5_score * WEIGHT_KB5) +
            (bias_score * WEIGHT_BIAS) +
            (smt_score * WEIGHT_SMT)
        )
        
        # Plafonner strictement la note finale du système à 100
        # Gate §0 — Boolean ERL
        erl_result = self._erl.check(pair, final_direction)
        final_score = min(int(round(raw_score)), 100)

        # Gate §0 — Boolean ERL
        erl_result  = self._erl.check(pair, final_direction)
        final_score = self._erl.apply_gate(final_score, erl_result)

        # Scoring V4 — enrichissement A/B/C/D
        v4_result   = self._scoring_v4.compute(
                          pair, final_direction, kb5_result)
        v4_score    = v4_result["total"]
        final_score = min(int(round(
                          final_score * 0.60 + v4_score * 0.40
                      )), 100)



        # ── Étape 5 : Overrides ─────────────────────────────
        override = self._apply_overrides(
            pair, final_direction, final_score,
            ks_result, cb_level, trading_ok,
            kb5_result
        )

        # ── Étape 6 : Verdict et Grade ──────────────────────
        # Déterminer le type de trade et le seuil adapté
        tf_details = kb5_result.get("tf_details", {})
        best_tf = max(tf_details, key=lambda t: tf_details[t].get("score", 0)) \
                  if tf_details else "H1"
        trade_type = infer_trade_type(best_tf)
        execute_threshold = get_execute_threshold(trade_type)

        if override["forced_no_trade"]:
            verdict = "NO_TRADE"
            reason  = override["reason"]
            grade   = "C"
        elif final_score >= execute_threshold:
            verdict = "EXECUTE"
            reason  = f"Tous filtres validés — {trade_type} (seuil {execute_threshold})"
            grade   = self._get_grade(final_score)
        elif final_score >= SCORE_WATCH:
            verdict = "WATCH"
            reason  = f"Score {final_score} insuffisant pour auto-exécution"
            grade   = self._get_grade(final_score)
        else:
            verdict = "NO_TRADE"
            reason  = f"Score {final_score} < seuil {SCORE_NO_TRADE}"
            grade   = "C"


        # ── Étape 7 : Entry Model final ─────────────────────
        entry_model = kb5_result.get("entry_model", {})

        # Ajuster lot size selon CB size_factor
        lot_size = self._calculate_lot_size(
            pair, entry_model, cb_size_factor
        )

        # ── Étape 8 : Assemblage SCALP_OUTPUT ───────────────
        scalp_output = self._build_scalp_output(
            pair         = pair,
            direction    = final_direction,
            verdict      = verdict,
            grade        = grade,
            final_score  = final_score,
            reason       = reason,
            kb5_result   = kb5_result,
            ks_result    = ks_result,
            cb_level     = cb_level,
            cb_size_factor= cb_size_factor,
            entry_model  = entry_model,
            lot_size     = lot_size,
            override     = override,
            now          = now,
        )

        # ── Stockage et logging ─────────────────────────────
        with self._lock:
            self._cache[pair] = scalp_output
            self._history.append(self._history_entry(scalp_output))
            # Limiter l'historique à 500 entrées
            if len(self._history) > 500:
                self._history = self._history[-500:]

        self._ds.set_analysis(pair, "scoring", scalp_output)

        self._log_verdict(scalp_output)

        return scalp_output

    # ══════════════════════════════════════════════════════════
    # OVERRIDES
    # ══════════════════════════════════════════════════════════

    def _apply_overrides(self, pair: str, direction: str,
                          score: int, ks_result: dict,
                          cb_level: int, trading_ok: bool,
                          kb5_result: dict) -> dict:
        """
        Applique les règles d'override dans l'ordre de priorité.
        Un seul override suffit à forcer NO_TRADE.

        Ordre de priorité :
          1. KS99 Gateway déconnecté
          2. CB ≥ 2 (Pause/Halt)
          3. KS bloquant actif
          4. Biais non aligné
          5. RR insuffisant
          6. Direction invalide vs PD zone

        Returns:
            dict {forced_no_trade, reason, override_type, details}
        """
        # ── Override 1 : KS99 Gateway ───────────────────────
                # Déterminer le type de trade
        tf_details = kb5_result.get("tf_details", {})
        best_tf = max(tf_details, key=lambda t: tf_details[t].get("score", 0)) \
                  if tf_details else "H1"
        trade_type = infer_trade_type(best_tf)

        ks99 = self._ds.get_ks_state(ks_id="99")

        if ks99.get("active", False):
            return self._override(
                "KS99_GATEWAY",
                "Gateway MT5 déconnecté — aucun ordre possible",
                ks99
            )

        # ── Override 2 : Circuit Breaker ────────────────────
        if not trading_ok:
            cb_cfg = {2: "PAUSE", 3: "HALT"}
            cb_name = cb_cfg.get(cb_level, f"CB{cb_level}")
            return self._override(
                f"CB{cb_level}_{cb_name}",
                f"Circuit Breaker niveau {cb_level} ({cb_name}) actif",
                {"cb_level": cb_level}
            )

        # ── Override 3 : KS bloquant ────────────────────────
        blocked_by = ks_result.get("blocked_by", [])
        if blocked_by:
            first_ks = blocked_by[0]
            ks_detail = ks_result.get("ks_details", {}).get(
                first_ks.lower(), {}
            )
            return self._override(
                first_ks,
                ks_detail.get("reason", f"{first_ks} actif"),
                {"all_blocked": blocked_by}
            )

        # ── Override 4 : Biais non aligné ───────────────────
        bias_aligned = kb5_result.get("bias_aligned", False)
        if not bias_aligned:
            bias_snap = self._bias.get_bias(pair)
            alignment = bias_snap.get("alignment", {}) if bias_snap else {}
            return self._override(
                "BIAS_MISALIGNED",
                f"Biais HTF non aligné — W/D/SOD divergents "
                f"({alignment.get('details', '')})",
                alignment
            )

        # ── Override 5 : RR insuffisant ─────────────────────
        entry_model = kb5_result.get("entry_model", {})
        rr = entry_model.get("rr", 0.0)
        rr_valid = entry_model.get("rr_valid", False)

        if not rr_valid or rr < RR_MINIMUM:
            return self._override(
                "RR_INSUFFICIENT",
                f"RR {rr:.2f} < minimum {RR_MINIMUM:.1f}",
                {"rr": rr, "rr_minimum": RR_MINIMUM}
            )

                # Override 6b : Scalp hors Killzone
        if trade_type == "SCALP":
            in_killzone = kb5_result.get("in_killzone", False)
            m15_score = kb5_result.get("pyramid_scores", {}).get("M15", 0)
            if not in_killzone:
                return self._override(
                    "SCALP_NO_KILLZONE",
                    "Scalp refusé — hors Killzone ICT",
                    {"trade_type": "SCALP", "in_killzone": False}
                )
            if m15_score < 40:
                return self._override(
                    "SCALP_NO_M15_CONFIRM",
                    f"Scalp refusé — M15 insuffisant ({m15_score}/100)",
                    {"trade_type": "SCALP", "m15_score": m15_score}
                )

        # Override 6 : PD Zone incohérente
        pd_zone = kb5_result.get("pd_zone", "UNKNOWN")
        pd_conflict = (
            (direction == "BULLISH" and pd_zone == "PREMIUM") or
            (direction == "BEARISH" and pd_zone == "DISCOUNT")
        )
        if pd_conflict and score < 15:
            return self._override(
                "PD_ZONE_CONFLICT",
                f"Entrée {direction} en zone {pd_zone} "
                f"(score {score} insuffisant pour override)",
                {"pd_zone": pd_zone, "direction": direction}
            )

        # ── Pas d'override ──────────────────────────────────
        return {
            "forced_no_trade": False,
            "reason":          None,
            "override_type":   None,
            "details":         {},
        }

    def _override(self, override_type: str,
                   reason: str, details: dict) -> dict:
        """Construit un dict override standardisé."""
        return {
            "forced_no_trade": True,
            "reason":          reason,
            "override_type":   override_type,
            "details":         details,
        }

    # ══════════════════════════════════════════════════════════
    # ASSEMBLAGE SCALP_OUTPUT
    # ══════════════════════════════════════════════════════════

    def _build_scalp_output(self, pair: str, direction: str,
                             verdict: str, grade: str,
                             final_score: int, reason: str,
                             kb5_result: dict, ks_result: dict,
                             cb_level: int, cb_size_factor: float,
                             entry_model: dict, lot_size: float,
                             override: dict,
                             now: datetime) -> dict:
        """
        Assemble le SCALP_OUTPUT final complet.
        C'est l'unique objet transmis à order_manager.py.

        Returns:
            dict SCALP_OUTPUT complet
        """
        bias_snap = self._bias.get_snapshot(pair)
        session   = kb5_result.get("session", "UNKNOWN")
        killzone  = kb5_result.get("in_killzone", False)

        return {
            # ── Identité ─────────────────────────────────
            "pair":       pair,
            "timestamp":  now.isoformat(),
            "session":    session,
            "in_killzone": killzone,

            # ── Verdict ──────────────────────────────────
            "score":      final_score,
            "verdict":    verdict,
            "grade":      grade,
            "reason":     reason,
            "confidence": self._get_confidence(final_score),

            # ── Override ─────────────────────────────────
            "override":   override,

            # ── Direction & Entrée ────────────────────────
            "direction":  direction,
            "entry":      entry_model.get("entry"),
            "sl":         entry_model.get("sl"),
            "tp":         entry_model.get("tp"),
            "rr":         entry_model.get("rr",  0.0),
            "rr_valid":   entry_model.get("rr_valid", False),
            "entry_type": entry_model.get("entry_type"),
            "entry_basis":entry_model.get("entry_basis"),
            "lot_size":   lot_size,
            "atr_h1":     entry_model.get("atr_h1", 0.0),

            # ── Biais ─────────────────────────────────────
            "bias": {
                "weekly":   bias_snap.get("weekly"),
                "daily":    bias_snap.get("daily"),
                "sod":      bias_snap.get("sod"),
                "aligned":  bias_snap.get("aligned"),
                "score":    bias_snap.get("bias_score"),
                "pd_zone":  bias_snap.get("pd_zone"),
            },

            # ── Pyramide KB5 ──────────────────────────────
            "pyramid_scores": kb5_result.get("pyramid_scores", {}),
            "kb5_score":      kb5_result.get("final_score",    0),
            "confluences":    kb5_result.get("confluences",    []),
            "structures":     kb5_result.get("structures",     {}),

            # ── KillSwitches ──────────────────────────────
            "killswitches": {
                "verdict":    ks_result.get("verdict"),
                "all_clear":  ks_result.get("all_clear"),
                "blocked_by": ks_result.get("blocked_by", []),
                "warnings":   ks_result.get("warnings",   []),
            },

            # ── Circuit Breaker ───────────────────────────
            "circuit_breaker": {
                "level":       cb_level,
                "size_factor": cb_size_factor,
                "trading_ok":  cb_level < 2,
            },

            # ── Invalidation ──────────────────────────────
            "invalidation": kb5_result.get("invalidation", {}),
        }

    def _build_no_trade(self, pair: str, score: int,
                         override_type: str, reason: str,
                         kb5_result: dict, ks_result: dict,
                         now: datetime) -> dict:
        """
        Construit un SCALP_OUTPUT NO_TRADE standardisé.
        Utilisé pour les cas d'abandon précoce (biais neutre, etc.)
        """
        return {
            "pair":       pair,
            "timestamp":  now.isoformat(),
            "session":    kb5_result.get("session", "UNKNOWN"),
            "in_killzone": False,
            "score":      score,
            "verdict":    "NO_TRADE",
            "grade":      "C",
            "reason":     reason,
            "confidence": "NONE",
            "override":   {
                "forced_no_trade": True,
                "reason":          reason,
                "override_type":   override_type,
                "details":         {},
            },
            "direction":   "NEUTRAL",
            "entry":       None,
            "sl":          None,
            "tp":          None,
            "rr":          0.0,
            "rr_valid":    False,
            "entry_type":  None,
            "entry_basis": None,
            "lot_size":    0.0,
            "atr_h1":      0.0,
            "bias":        {},
            "pyramid_scores": {tf: 0 for tf in
                               ["MN","W1","D1","H4","H1","M15"]},
            "kb5_score":   0,
            "confluences": [],
            "structures":  {},
            "killswitches":{"verdict":"UNKNOWN","all_clear":False,
                            "blocked_by":[],"warnings":[]},
            "circuit_breaker": {"level":0,"size_factor":1.0,
                                "trading_ok":True},
            "invalidation": {},
        }

    # ══════════════════════════════════════════════════════════
    # LOT SIZE
    # ══════════════════════════════════════════════════════════

    def _calculate_lot_size(self, pair: str,
                             entry_model: dict,
                             cb_size_factor: float) -> float:
        """
        Calcule la taille de lot finale en tenant compte
        du facteur CB et du risque configuré.

        Logique :
          - Risque de base = Risk.DEFAULT_RISK_PCT de l'equity
          - Lot = risque / (risk_pips × pip_value)
          - Applique cb_size_factor (1.0 / 0.5 / 0.0)

        Returns:
            float lot_size arrondi à 2 décimales
        """
        if cb_size_factor <= 0:
            return 0.0

        try:
            # Récupérer equity depuis DataStore
            equity = self._ds.get_stats().get("equity", 10000.0)
            risk_pct = getattr(Risk, "DEFAULT_RISK_PCT", 1.0)
            risk_amount = equity * (risk_pct / 100)

            risk_pips = entry_model.get("risk_pips", 0.0)
            atr_h1    = entry_model.get("atr_h1",    0.0)

            # Fallback sur ATR si risk_pips nul
            if risk_pips <= 0:
                risk_pips = atr_h1 * 1.5

            if risk_pips <= 0:
                return 0.01  # lot minimum sécurité

            # Pip value approximatif (à affiner par capital_allocator)
            pip_value = getattr(Risk, "DEFAULT_PIP_VALUE", 10.0)

            lot = (risk_amount / (risk_pips * pip_value)) * cb_size_factor

            # Clamp entre lot min et lot max
            lot_min = getattr(Risk, "LOT_MIN", 0.01)
            lot_max = getattr(Risk, "LOT_MAX", 5.0)
            lot = max(lot_min, min(lot_max, lot))

            return round(lot, 2)

        except Exception as e:
            logger.error(f"ScoringEngine — lot_size erreur : {e}")
            return 0.01

    # ══════════════════════════════════════════════════════════
    # HELPERS — GRADE / CONFIDENCE / SMT
    # ══════════════════════════════════════════════════════════

    def _get_grade(self, score: int) -> str:
        """
        Retourne le grade lettre selon le score.

        Returns:
            str "A+", "A", "A-", "B+", "B", "B-", ou "C"
        """
        for threshold, grade in GRADE_MAP:
            if score >= threshold:
                return grade
        return "C"

    def _get_confidence(self, score: int) -> str:
        """
        Retourne le niveau de confiance textuel.

        Returns:
            "HIGH" / "MEDIUM" / "LOW" / "NONE"
        """
        if score >= SCORE_EXECUTE:
            return "HIGH"
        elif score >= SCORE_WATCH:
            return "MEDIUM"
        elif score > 0:
            return "LOW"
        return "NONE"

    def _get_smt_contribution(self, kb5_result: dict) -> float:
        """
        Extrait la contribution SMT depuis le KB5_RESULT.
        Utilise le confidence_score du meilleur signal SMT.

        Returns:
            float score SMT 0→100
        """
        structures = kb5_result.get("structures", {})
        smt        = structures.get("smt", {})

        if not smt.get("detected", False):
            return 0.0

        strength_map = {"STRONG": 85, "MODERATE": 65, "WEAK": 40}
        return float(strength_map.get(smt.get("strength"), 0))

    # ══════════════════════════════════════════════════════════
    # LOGGING STRUCTURÉ
    # ══════════════════════════════════════════════════════════

    def _log_verdict(self, output: dict) -> None:
        """
        Log structuré du verdict final avec tous les éléments clés.
        Niveau de log adapté au verdict.
        """
        pair    = output["pair"]
        verdict = output["verdict"]
        score   = output["score"]
        grade   = output["grade"]
        reason  = output["reason"]
        rr      = output.get("rr", 0.0)
        entry   = output.get("entry")
        sl      = output.get("sl")
        tp      = output.get("tp")
        lot     = output.get("lot_size", 0.0)
        ks_warn = output.get("killswitches", {}).get("warnings", [])

        msg = (
            f"VERDICT — {pair} | "
            f"{verdict} [{grade}] | "
            f"Score : {score} | "
            f"Direction : {output.get('direction')} | "
            f"RR : {rr} | "
            f"Entry : {entry} | SL : {sl} | TP : {tp} | "
            f"Lot : {lot} | "
            f"Raison : {reason}"
        )

        if ks_warn:
            msg += f" | Warnings KS : {ks_warn}"

        if verdict == "EXECUTE":
            logger.info(f"🟢 {msg}")
        elif verdict == "WATCH":
            logger.info(f"🟡 {msg}")
        else:
            logger.info(f"🔴 {msg}")

    def _history_entry(self, output: dict) -> dict:
        """Entrée d'historique compacte pour audit."""
        return {
            "timestamp": output["timestamp"],
            "pair":      output["pair"],
            "verdict":   output["verdict"],
            "grade":     output["grade"],
            "score":     output["score"],
            "direction": output["direction"],
            "rr":        output.get("rr", 0.0),
            "reason":    output["reason"],
            "override":  output.get("override", {}).get("override_type"),
        }

    # ══════════════════════════════════════════════════════════
    # API PUBLIQUE
    # ══════════════════════════════════════════════════════════

    def get_latest(self, pair: str) -> Optional[dict]:
        """
        Retourne le dernier SCALP_OUTPUT pour une paire.
        Consommé par order_manager et Dashboard Patron.

        Returns:
            dict SCALP_OUTPUT ou None
        """
        with self._lock:
            return dict(self._cache.get(pair, {})) or None

    def get_verdict(self, pair: str) -> str:
        """
        Retourne uniquement le verdict actuel.
        Raccourci pour supervisor.py.

        Returns:
            "EXECUTE", "WATCH", "NO_TRADE", ou "UNKNOWN"
        """
        with self._lock:
            return self._cache.get(pair, {}).get("verdict", "UNKNOWN")

    def is_executable(self, pair: str) -> bool:
        """
        Vérifie si le dernier verdict est EXECUTE.
        Raccourci pour order_manager.py.

        Returns:
            True si verdict == EXECUTE
        """
        return self.get_verdict(pair) == "EXECUTE"

    def get_all_verdicts(self) -> dict:
        """
        Retourne un résumé des verdicts de toutes les paires.
        Consommé par supervisor.py pour le monitoring global.

        Returns:
            dict {pair: {verdict, score, grade, direction}}
        """
        with self._lock:
            return {
                pair: {
                    "verdict":   output.get("verdict"),
                    "score":     output.get("score"),
                    "grade":     output.get("grade"),
                    "direction": output.get("direction"),
                    "rr":        output.get("rr"),
                }
                for pair, output in self._cache.items()
            }

    def get_executable_pairs(self) -> list:
        """
        Retourne la liste des paires avec verdict EXECUTE.
        Consommé par supervisor.py pour lancer les ordres.

        Returns:
            liste de str ex. ["EURUSD", "XAUUSD"]
        """
        with self._lock:
            return [
                pair for pair, output in self._cache.items()
                if output.get("verdict") == "EXECUTE"
            ]

    def get_statistics(self) -> dict:
        """
        Statistiques globales sur l'historique des verdicts.
        Consommé par Dashboard Patron section performance.

        Returns:
            dict {total, execute, watch, no_trade, grades, avg_score}
        """
        with self._lock:
            history = list(self._history)

        if not history:
            return {"total": 0}

        execute_list = [h for h in history if h["verdict"] == "EXECUTE"]
        watch_list   = [h for h in history if h["verdict"] == "WATCH"]
        no_trade_list= [h for h in history if h["verdict"] == "NO_TRADE"]

        grade_counts: dict[str, int] = {}
        for h in history:
            g = h.get("grade", "C")
            grade_counts[g] = grade_counts.get(g, 0) + 1

        avg_score = (
            sum(h["score"] for h in history) / len(history)
            if history else 0
        )

        # Override types fréquents
        overrides = [
            h["override"] for h in history
            if h["override"] is not None
        ]
        override_counts: dict[str, int] = {}
        for o in overrides:
            override_counts[o] = override_counts.get(o, 0) + 1

        return {
            "total":           len(history),
            "execute":         len(execute_list),
            "watch":           len(watch_list),
            "no_trade":        len(no_trade_list),
            "execute_rate":    round(len(execute_list) / len(history) * 100, 1),
            "grades":          grade_counts,
            "avg_score":       round(avg_score, 1),
            "override_counts": override_counts,
            "last_verdict":    history[-1] if history else None,
        }

    def get_snapshot(self, pair: str) -> dict:
        """
        Snapshot compact pour Dashboard Patron.

        Returns:
            dict {pair, verdict, score, grade, rr, direction, reason}
        """
        with self._lock:
            output = dict(self._cache.get(pair, {}))

        if not output:
            return {"pair": pair, "status": "non évalué"}

        return {
            "pair":       pair,
            "verdict":    output.get("verdict"),
            "score":      output.get("score"),
            "grade":      output.get("grade"),
            "confidence": output.get("confidence"),
            "direction":  output.get("direction"),
            "rr":         output.get("rr"),
            "entry":      output.get("entry"),
            "sl":         output.get("sl"),
            "tp":         output.get("tp"),
            "lot_size":   output.get("lot_size"),
            "reason":     output.get("reason"),
            "timestamp":  output.get("timestamp"),
            "pyramid":    output.get("pyramid_scores"),
            "aligned":    output.get("bias", {}).get("aligned"),
            "in_killzone":output.get("in_killzone"),
        }

    def clear_cache(self, pair: str = None) -> None:
        """
        Vide le cache scoring. Reset entre sessions.
        """
        with self._lock:
            if pair:
                self._cache.pop(pair, None)
                logger.info(f"Scoring cache vidé — Paire : {pair}")
            else:
                self._cache.clear()
                logger.info("Scoring cache vidé — toutes les paires")

    def __repr__(self) -> str:
        with self._lock:
            verdicts = {
                p: o.get("verdict") for p, o in self._cache.items()
            }
        return (
            f"ScoringEngine("
            f"verdicts={verdicts}, "
            f"history={len(self._history)})"
        )
