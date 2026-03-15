---
version: "1.0"
type: "moteur_decision"
last_updated: "2026-03-11"
description: "Moteur de décision final KB5 — Scoring 100pts + Vetos + Matrice conflits + Verdict"
source: "KB5 — Cerveau du département analyse — Lit le DOSSIER_PAIRE, produit le verdict"
---

# ⚙️ MOTEUR DE DÉCISION v1.0 — SENTINEL PRO KB5
## Cerveau du Département Analyse — Verdict Final

> **RÔLE :** Ce fichier est le **dernier maillon** de la chaîne KB5.
> Il lit le `DOSSIER_PAIRE` produit par le pipeline d'analyse,
> applique les règles de veto, le scoring, et la matrice de conflits,
> puis produit le **verdict final d'exécution**.
> **RÈGLE D'OR :** Le moteur ne trade pas. Il décide. L'exécution est une étape séparée.

---

## SECTION 1 — ARCHITECTURE DU MOTEUR

```
ENTRÉE : DOSSIER_PAIRE (JSON complet — 06_DOSSIER_PAIRE_SCHEMA.md)
    ↓
ÉTAPE 1 : Vérification des VETOS ABSOLUS (bloquants immédiats)
    ↓
ÉTAPE 2 : Vérification des VETOS DESCENDANTS (HTF gouverne LTF)
    ↓
ÉTAPE 3 : Calcul du SCORE 100 points
    ↓
ÉTAPE 4 : Application des BONUS et MALUS
    ↓
ÉTAPE 5 : Résolution de la MATRICE DES CONFLITS
    ↓
ÉTAPE 6 : Vérification des EXCLUSIONS ABSOLUES
    ↓
ÉTAPE 7 : Production du VERDICT FINAL
    ↓
SORTIE : verdict JSON → {autorisation, confiance, score, sizing, raison, vetos}
```

---

## SECTION 2 — VETOS ABSOLUS (Étape 1)

### 2.1 Liste des 8 Vetos Absolus

Un seul veto absolu déclenché = **INTERDIT immédiat, score ignoré.**

```python
def check_vetos_absolus(dossier):
    vetos = []

    # VETO 1 — Anti-Inducement (Règle n°1 de tout le système KB5)
    if not dossier["liquidite"]["boolean_sweep_erl"]:
        vetos.append({
            "code": "VETO_ANTI_INDUCEMENT",
            "priorite": "ABSOLU",
            "message": "ERL non purgé — Boolean_Sweep_ERL = False",
            "action": "INTERDIT"
        })

    # VETO 2 — SOD Manipulation ou Unknown
    if dossier["structure_marche"]["sod_actuel"] in ["MANIPULATION", "UNKNOWN"]:
        vetos.append({
            "code": "VETO_SOD_BLOQUANT",
            "priorite": "ABSOLU",
            "message": f"SOD = {dossier['structure_marche']['sod_actuel']} — Freeze total",
            "action": "FREEZE"
        })

    # VETO 3 — News haute impact imminentes
    if (dossier["timing"]["minutes_to_next_news"] < 30 and
        dossier["timing"]["news_impact_next"] >= 8):
        vetos.append({
            "code": "VETO_NEWS_FREEZE",
            "priorite": "ABSOLU",
            "message": f"News impact {dossier['timing']['news_impact_next']}/10 dans {dossier['timing']['minutes_to_next_news']} min",
            "action": "FREEZE",
            "score_malus": -50
        })

    # VETO 4 — Biais HTF global inconnu ou conflit total
    if dossier["biais_htf"]["bias_global"] in ["UNKNOWN", "CONFLIT"]:
        vetos.append({
            "code": "VETO_BIAIS_INCONNU",
            "priorite": "ABSOLU",
            "message": "Biais global HTF UNKNOWN ou CONFLIT total",
            "action": "INTERDIT"
        })

    # VETO 5 — Dossier invalide ou expiré
    if dossier["meta"]["statut"] == "INVALIDE":
        vetos.append({
            "code": "VETO_DOSSIER_INVALIDE",
            "priorite": "ABSOLU",
            "message": "Dossier marqué INVALIDE par le pipeline",
            "action": "INTERDIT"
        })

    # VETO 6 — VIX extrême sur indices
    if (dossier["meta"]["instrument_type"] == "INDICES" and
        dossier["intermarket"]["vix"] > 35):
        vetos.append({
            "code": "VETO_VIX_EXTREME",
            "priorite": "ABSOLU",
            "message": f"VIX = {dossier['intermarket']['vix']} > 35 — Volatilité incontrôlable",
            "action": "INTERDIT"
        })

    # VETO 7 — Liquidation cascade BTC
    if (dossier["meta"]["instrument_type"] == "BTC" and
        dossier["instrument_specifique"].get("liquidation_cascade", False)):
        vetos.append({
            "code": "VETO_BTC_LIQUIDATION",
            "priorite": "ABSOLU",
            "message": "Liquidation cascade BTC détectée — No-trade 2h",
            "action": "FREEZE"
        })

    # VETO 8 — Lundi avant 10h00 NYC (structures instables)
    if (dossier["timing"].get("is_monday_pre_10h", False)):
        vetos.append({
            "code": "VETO_LUNDI_PRE_10H",
            "priorite": "ABSOLU",
            "message": "Lundi avant 10h NYC — Structures instables",
            "action": "ATTENDRE"
        })

    return vetos
```

---

## SECTION 3 — VETOS DESCENDANTS (Étape 2)

### 3.1 Principe HTF Gouverne LTF

```
RÈGLE FONDAMENTALE :
Un signal LTF (H1, M15, M5) ne peut JAMAIS aller contre le biais HTF (D1, H4).
Le timeframe supérieur a toujours le DROIT DE VETO sur le timeframe inférieur.

HIÉRARCHIE DES DROITS DE VETO :
MN > W > D1 > H4 > H1 > M15 > M5 > M1
```

```python
def check_vetos_descendants(dossier):
    vetos = []
    direction_signal = dossier["trade_plan"]["direction"]  # LONG ou SHORT
    bias = dossier["biais_htf"]

    # Veto D1 sur H1/M15
    if direction_signal == "LONG" and bias["daily_bias"] == "BEARISH":
        vetos.append({
            "code": "VETO_D1_SUR_LTF",
            "priorite": "FORT",
            "message": "Signal LONG contre Daily Bias BEARISH",
            "action": "PASSER",
            "exception": "Autorisé si score >= 90 ET Weekly_bias = BULLISH (Counter-trend A++)"
        })

    if direction_signal == "SHORT" and bias["daily_bias"] == "BULLISH":
        vetos.append({
            "code": "VETO_D1_SUR_LTF",
            "priorite": "FORT",
            "message": "Signal SHORT contre Daily Bias BULLISH",
            "action": "PASSER",
            "exception": "Autorisé si score >= 90 ET Weekly_bias = BEARISH"
        })

    # Veto H4 sur M15/M5
    if direction_signal == "LONG" and bias["h4_bias"] == "BEARISH":
        vetos.append({
            "code": "VETO_H4_SUR_SCALP",
            "priorite": "MODÉRÉ",
            "message": "Signal LONG contre H4 Bias BEARISH",
            "action": "REDUCE_50PCT",
            "score_malus": -20
        })

    # Veto Monthly sur tout
    if direction_signal == "LONG" and bias["monthly_bias"] == "BEARISH":
        vetos.append({
            "code": "VETO_MONTHLY_ABSOLU",
            "priorite": "FORT",
            "message": "Signal LONG contre Monthly Bias BEARISH",
            "action": "PASSER",
            "score_malus": -30
        })

    return vetos
```

---

## SECTION 4 — CALCUL DU SCORE (Étape 3 & 4)

### 4.1 Base 100 Points

```python
def calculate_base_score(dossier):
    score = 0
    detail = {}

    # Critère 1 — Killzone + Macro active (20 pts)
    if dossier["timing"]["killzone_active"] and dossier["timing"]["macro_active"]:
        score += 20
        detail["killzone_macro"] = 20
    elif dossier["timing"]["killzone_active"] or dossier["timing"]["macro_active"]:
        score += 10
        detail["killzone_macro"] = 10
    else:
        detail["killzone_macro"] = 0

    # Critère 2 — ERL Sweep (20 pts)
    if dossier["liquidite"]["boolean_sweep_erl"]:
        score += 20
        detail["erl_sweep"] = 20
    else:
        detail["erl_sweep"] = 0  # + Veto absolu déjà déclenché

    # Critère 3 — Qualité zone PD Array (20 pts)
    pd_score_map = {
        "CE": 20, "SUSPENSION_BLOCK": 20, "BREAKER_BLOCK": 18,
        "ORDER_BLOCK": 16, "FVG": 15, "BPR": 12,
        "REJECTION_BLOCK": 10, "NDOG": 10, "VOLUME_IMBALANCE": 8
    }
    zone_type = dossier["pd_arrays"].get("zone_entree_optimale_type", "FVG")
    pd_pts = pd_score_map.get(zone_type, 10)
    # Ajustement freshness
    freshness = dossier["pd_arrays"].get("zone_entree_freshness", "MITIGÉ")
    freshness_mult = {"FRAIS": 1.0, "MITIGÉ": 0.7, "REVISITÉ": 0.4, "INVALIDE": 0.0}
    score += int(pd_pts * freshness_mult.get(freshness, 0.5))
    detail["pd_array_qualite"] = int(pd_pts * freshness_mult.get(freshness, 0.5))

    # Critère 4 — DOL identifié + RR >= 2:1 (20 pts)
    rr = dossier["trade_plan"].get("rr_tp3", 0)
    dol_ok = dossier["liquidite"].get("dol_actif") is not None
    if dol_ok and rr >= 3.0:
        score += 20
        detail["dol_rr"] = 20
    elif dol_ok and rr >= 2.0:
        score += 15
        detail["dol_rr"] = 15
    elif dol_ok:
        score += 8
        detail["dol_rr"] = 8
    else:
        detail["dol_rr"] = 0

    # Critère 5 — Corrélation SMT (20 pts)
    piliers = dossier["intermarket"].get("piliers_alignes", 0)
    if piliers == 5:    score += 20; detail["smt"] = 20
    elif piliers >= 3:  score += 12; detail["smt"] = 12
    elif piliers >= 2:  score += 5;  detail["smt"] = 5
    else:               detail["smt"] = 0

    return score, detail
```

### 4.2 Bonus et Malus

```python
def calculate_bonus_malus(dossier):
    bonus = 0
    malus = 0
    detail_bonus = {}
    detail_malus = {}

    # ===== BONUS =====

    # Entrée sur ENIGMA .20 ou .80
    entry = dossier["trade_plan"].get("entry_price", 0)
    entry_decimals = round(entry % 1, 2)
    if entry_decimals in [0.20, 0.80]:
        bonus += 10
        detail_bonus["enigma_entry"] = 10

    # Weekly Template confirmé
    if dossier["instrument_specifique"].get("weekly_template") not in [None, "UNKNOWN", "CHOPPY"]:
        bonus += 5
        detail_bonus["weekly_template"] = 5

    # 1st Presented FVG (09h30-10h00)
    if dossier["timing"].get("first_presented_fvg_active", False):
        bonus += 5
        detail_bonus["first_presented_fvg"] = 5

    # Cascade Fractale
    cascade = dossier["pd_arrays"].get("cascade_type", "STANDALONE")
    if cascade == "CASCADE_TRIPLE":
        bonus += 35
        detail_bonus["cascade_triple"] = 35
    elif cascade == "CASCADE_DOUBLE":
        bonus += 15
        detail_bonus["cascade_double"] = 15

    # Convergence MMXM multi-TF
    mmxm_bonus = dossier["structure_marche"].get("mmxm_phase", {}).get("convergence_bonus", 0)
    if mmxm_bonus > 0:
        bonus += mmxm_bonus
        detail_bonus["mmxm_convergence"] = mmxm_bonus

    # SMT bonus (5 piliers alignés)
    if dossier["intermarket"].get("piliers_alignes", 0) == 5:
        bonus += 20
        detail_bonus["smt_5_piliers"] = 20

    # Signal Bar A++ sur zone ICT
    sig_qualite = dossier["analyse_pa"].get("dernier_signal_bar", {}).get("qualite", "")
    if sig_qualite == "A_PLUS_PLUS":
        bonus += 10
        detail_bonus["signal_bar_axx"] = 10

    # H2/L2 dans zone ICT
    if dossier["analyse_pa"].get("bar_count") in ["H2", "L2"]:
        bonus += 8
        detail_bonus["h2_l2_ict"] = 8

    # ===== MALUS =====

    # TP hors niveaux .00 ou .50
    tp3 = dossier["trade_plan"].get("tp3", 0)
    tp3_dec = round(tp3 % 1, 2)
    if tp3_dec not in [0.00, 0.50]:
        malus += 15
        detail_malus["tp_hors_enigma"] = -15

    # Position en zone Premium T-20 + signal LONG
    if (dossier["ipda"].get("t20_position") == "PREMIUM" and
        dossier["trade_plan"].get("direction") == "LONG"):
        malus += 20
        detail_malus["premium_t20_long"] = -20

    # H3 ou L3 détecté (3ème tentative)
    if dossier["analyse_pa"].get("bar_count") in ["H3", "L3"]:
        malus += 15
        detail_malus["h3_l3_detected"] = -15

    # VIX élevé (indices seulement)
    vix = dossier["intermarket"].get("vix", 0)
    if dossier["meta"]["instrument_type"] == "INDICES":
        if vix > 25:   malus += 15; detail_malus["vix_eleve"] = -15
        elif vix > 20: malus += 8;  detail_malus["vix_modere"] = -8

    # Conflit HTF mineur
    if dossier["biais_htf"].get("conflits_htf", False):
        malus += 10
        detail_malus["conflit_htf_mineur"] = -10

    # Quarterly Shift actif
    if dossier["ipda"].get("quarterly_shift_active", False):
        malus += 15
        detail_malus["quarterly_shift"] = -15

    return bonus, malus, detail_bonus, detail_malus
```

---

## SECTION 5 — MATRICE DES CONFLITS (Étape 5)

### 5.1 Conflits HTF Classiques et Résolutions

| Situation | Conflit | Résolution | Sizing |
|-----------|---------|-----------|--------|
| Monthly BULLISH + Weekly BEARISH | Mineur | Suivre Monthly si D1 confirme | 60% |
| Weekly BULLISH + Daily BEARISH | Mineur | Attendre Daily retournement | 40% |
| Monthly BULLISH + Daily BEARISH | Modéré | Réduire — Contre-tendance D1 | 30% |
| Monthly BEARISH + Weekly BULLISH + Daily BULLISH | Fort | PASSER — Trap probable | 0% |
| Tous TF alignés BULLISH | Aucun | ✅ Full size | 100% |
| Tous TF alignés BEARISH | Aucun | ✅ Full size | 100% |
| 2 BULLISH + 2 BEARISH | Majeur | PASSER — Range ou transition | 0% |

```python
def resolve_htf_conflict(monthly, weekly, daily, h4):
    signals = {"BULLISH": 1, "BEARISH": -1, "NEUTRE": 0, "UNKNOWN": None}
    values = [signals.get(x) for x in [monthly, weekly, daily, h4]]

    if None in values:
        return "CONFLIT_INCONNU", 0.0

    total = sum(values)

    if total == 4:    return "CONSENSUS_BULLISH", 1.0
    if total == -4:   return "CONSENSUS_BEARISH", 1.0
    if total == 3:    return "BULLISH_FORT", 0.8
    if total == -3:   return "BEARISH_FORT", 0.8
    if total == 2:    return "BULLISH_MINEUR", 0.5
    if total == -2:   return "BEARISH_MINEUR", 0.5
    if total == 0:    return "CONFLIT_MAJEUR", 0.0
    return "CONFLIT_MODÉRÉ", 0.3
```

### 5.2 Conflits SMT et Résolutions

```python
def resolve_smt_conflict(dossier):
    piliers_ok = dossier["intermarket"]["piliers_alignes"]
    piliers_ko = dossier["intermarket"]["piliers_conflit"]

    if piliers_ko == 0:
        return "SMT_PARFAIT", 1.0, 0

    if piliers_ko == 1:
        return "SMT_BON", 0.8, -5

    if piliers_ko == 2:
        return "SMT_CONFLIT_MODERE", 0.5, -15

    if piliers_ko >= 3:
        return "SMT_CONFLIT_MAJEUR", 0.0, -30  # PASSER
```

---

## SECTION 6 — EXCLUSIONS ABSOLUES (Étape 6)

### 6.1 Les 10 Règles d'Exclusion Absolues

Ces règles s'appliquent APRÈS le scoring. Un trade peut avoir un score de 100 et être quand même exclu.

```python
def check_exclusions_absolues(dossier, score_final):
    exclusions = []

    # Exclusion 1 — Score insuffisant (règle ultime)
    if score_final < 65:
        exclusions.append(("SCORE_INSUFFISANT", f"Score {score_final} < 65 — No-trade"))

    # Exclusion 2 — RR insuffisant
    if dossier["trade_plan"]["rr_tp1"] < 2.0:
        exclusions.append(("RR_INSUFFISANT", "RR < 2:1 — Risque/récompense inacceptable"))

    # Exclusion 3 — Weekly Template CHOPPY
    if dossier["instrument_specifique"].get("weekly_template") == "CHOPPY":
        exclusions.append(("WEEKLY_CHOPPY", "Semaine CHOPPY — NO-TRADE toute la semaine"))

    # Exclusion 4 — SOD ACCUMULATION (pas de tendance)
    if dossier["structure_marche"]["sod_actuel"] == "ACCUMULATION":
        exclusions.append(("SOD_ACCUMULATION", "SOD = Accumulation — Pas de trade directional"))

    # Exclusion 5 — Spread excessif Forex
    if (dossier["meta"]["instrument_type"] == "FOREX" and
        dossier["instrument_specifique"].get("spread_actuel", 0) > 3):
        exclusions.append(("SPREAD_EXCESSIF", "Spread > 3 pips — Coût inacceptable"))

    # Exclusion 6 — Dossier expiré
    if dossier["meta"]["statut"] == "EXPIRE":
        exclusions.append(("DOSSIER_EXPIRE", "Dossier expiré — Relancer l'analyse"))

    # Exclusion 7 — Aucune zone PD Array valide
    zones_valides = [z for z in dossier["pd_arrays"]["zones_actives"]
                     if z["freshness"] in ["FRAIS", "MITIGÉ"]]
    if len(zones_valides) == 0:
        exclusions.append(("NO_PD_ARRAY_VALIDE", "Aucune zone institutionnelle valide"))

    # Exclusion 8 — Série d'échecs (PA)
    if dossier["analyse_pa"].get("consecutive_failures", 0) >= 5:
        exclusions.append(("SERIE_ECHECS_PA", "5 échecs Signal Bar consécutifs — Pause forcée"))

    # Exclusion 9 — EIA/OPEC imminents (pétrole)
    if (dossier["meta"]["instrument_type"] == "PETROLE" and
        (dossier["instrument_specifique"].get("eia_proximity") or
         dossier["instrument_specifique"].get("opec_proximity"))):
        exclusions.append(("EVENEMENT_PETROLE", "EIA ou OPEC+ imminent — No-trade"))

    # Exclusion 10 — London Fix imminent (Or)
    if (dossier["meta"]["instrument_type"] == "OR" and
        dossier["instrument_specifique"].get("london_fix_active")):
        exclusions.append(("LONDON_FIX_OR", "London Fix ±15 min — Réduire à 30% ou PASS"))

    return exclusions
```

---

## SECTION 7 — VERDICT FINAL (Étape 7)

### 7.1 Moteur de Décision Principal

```python
def moteur_decision(dossier):
    """
    Moteur principal KB5 — Produit le verdict final
    """
    result = {
        "vetos_absolus": [],
        "vetos_descendants": [],
        "score_base": 0,
        "score_bonus": 0,
        "score_malus": 0,
        "score_final": 0,
        "exclusions": [],
        "sizing_final": 0.0,
        "verdict": "INTERDIT",
        "confiance": "REFUSE",
        "raison": ""
    }

    # ÉTAPE 1 — Vetos absolus
    result["vetos_absolus"] = check_vetos_absolus(dossier)
    if any(v["action"] in ["INTERDIT", "FREEZE"] for v in result["vetos_absolus"]):
        result["verdict"] = result["vetos_absolus"][0]["action"]
        result["raison"] = result["vetos_absolus"][0]["message"]
        return result

    # ÉTAPE 2 — Vetos descendants
    result["vetos_descendants"] = check_vetos_descendants(dossier)
    veto_malus = sum(v.get("score_malus", 0) for v in result["vetos_descendants"])

    # ÉTAPE 3 & 4 — Scoring
    base, detail_base = calculate_base_score(dossier)
    bonus, malus, detail_bonus, detail_malus = calculate_bonus_malus(dossier)
    malus += abs(veto_malus)

    result["score_base"] = base
    result["score_bonus"] = bonus
    result["score_malus"] = malus
    score_final = max(0, min(150, base + bonus - malus))
    result["score_final"] = score_final

    # ÉTAPE 5 — Conflits HTF
    htf_resolution, htf_sizing = resolve_htf_conflict(
        dossier["biais_htf"]["monthly_bias"],
        dossier["biais_htf"]["weekly_bias"],
        dossier["biais_htf"]["daily_bias"],
        dossier["biais_htf"]["h4_bias"]
    )[:2]

    # ÉTAPE 6 — Exclusions absolues
    result["exclusions"] = check_exclusions_absolues(dossier, score_final)
    if result["exclusions"]:
        result["verdict"] = "INTERDIT"
        result["raison"] = result["exclusions"][0][1]
        return result

    # ÉTAPE 7 — Verdict final
    if score_final >= 80:
        result["verdict"] = "EXECUTER"
        result["confiance"] = "A_PLUS_PLUS"
        result["sizing_final"] = min(1.0, htf_sizing)
    elif score_final >= 65:
        result["verdict"] = "EXECUTER"
        result["confiance"] = "A"
        result["sizing_final"] = min(0.5, htf_sizing)
    else:
        result["verdict"] = "INTERDIT"
        result["confiance"] = "REFUSE"
        result["sizing_final"] = 0.0

    return result
```

### 7.2 Table de Décision Finale

| Score Final | Catégorie | Verdict | Sizing |
|-------------|-----------|---------|--------|
| 95-150 | GRAIL / CASCADE TRIPLE | EXECUTER A++ | 100% |
| 80-94 | EXÉCUTION NORMALE | EXECUTER A++ | 100% |
| 70-79 | SNIPER | EXECUTER A | 50% |
| 65-69 | BORDERLINE | EXECUTER A | 50% — Confirmer H2/L2 |
| 50-64 | INSUFFISANT | ATTENDRE | 0% — Monitoring |
| < 50 | REFUSÉ | INTERDIT | 0% |
| Veto absolu | BLOQUÉ | INTERDIT/FREEZE | 0% |

---

## SECTION 8 — TERMINUS DETECTION

### 8.1 Détection du Point de Sortie Total

```python
def check_terminus(dossier, current_price, current_time):
    """
    Détecte si les conditions de Terminus sont réunies → Sortie 100%
    """
    terminus_score = 0
    conditions = []

    # Condition 1 — Measured Move PA atteint (±5 pips)
    mm_target = dossier["analyse_pa"].get("measured_move_target", 0)
    if mm_target and abs(current_price - mm_target) <= 0.0005:
        terminus_score += 40
        conditions.append("MEASURED_MOVE_ATTEINT")

    # Condition 2 — Killzone ICT active
    if dossier["timing"]["killzone_active"]:
        terminus_score += 30
        conditions.append("KILLZONE_ACTIVE")

    # Condition 3 — Niveau ENIGMA .00 ou .50 touché
    price_dec = round(current_price % 1, 2)
    if price_dec in [0.00, 0.50]:
        terminus_score += 30
        conditions.append("ENIGMA_00_50_TOUCHE")

    # Condition 4 (bonus) — FVG HTF rempli
    if dossier["pd_arrays"].get("fvg_htf_filled", False):
        terminus_score += 15
        conditions.append("FVG_HTF_REMPLI")

    # Condition 5 (bonus) — Std Dev -2.5 atteinte
    if dossier["trade_plan"].get("std_dev_2_5_reached", False):
        terminus_score += 20
        conditions.append("STD_DEV_2_5")

    if terminus_score >= 70 and len(conditions) >= 2:
        return True, terminus_score, conditions

    return False, terminus_score, conditions
```

---

## SECTION 9 — LOGGING ET TRAÇABILITÉ

### 9.1 Structure du Log de Décision

```json
{
  "decision_log": {
    "timestamp": "2026-03-11T10h25Z",
    "paire": "EUR/USD",
    "pipeline": "KB5_v1.0",
    "score_base": 95,
    "score_bonus": 55,
    "score_malus": 0,
    "score_final": 100,
    "vetos_absolus_count": 0,
    "vetos_descendants_count": 0,
    "exclusions_count": 0,
    "verdict": "EXECUTER",
    "confiance": "A_PLUS_PLUS",
    "sizing_final": 1.0,
    "raison_principale": "Score 100 — Grail Setup — Cascade Double — MMXM convergence",
    "top_bonus": ["cascade_double +15", "mmxm_convergence +10", "smt_5_piliers +20"],
    "top_malus": [],
    "entry": 1.08065,
    "sl": 1.07960,
    "tp1": 1.08500,
    "tp3": 1.09200,
    "rr_final": 10.8
  }
}
```

### 9.2 Règles de Rétention des Logs

```
- Conserver tous les logs EXECUTER et INTERDIT
- Logs ATTENDRE : conserver 48h puis archiver
- Logs FREEZE : conserver jusqu'à levée du gel + 24h
- Format : JSON + CSV export hebdomadaire
- Analyse de performance : Win/Loss rate par catégorie de score
```

---

## SECTION 10 — AUTODIAGNOSTIC DU MOTEUR

### 10.1 Checklist de Santé du Moteur

```python
def moteur_health_check():
    checks = {
        "fichiers_kb5_presents": [
            "00_GLOSSAIRE_UNIFIE.md",
            "01_CADRE_FRACTAL_SPECIFIQUE.md",
            "02_PYRAMIDE_ANALYSE.md",
            "03_ICT_ENCYCLOPEDIE_v5.md",
            "04_PRICE_ACTION_BIBLE_v4.md",
            "05_INSTRUMENTS_SPECIFIQUES.md",
            "06_DOSSIER_PAIRE_SCHEMA.md",
            "07_MOTEUR_DECISION.md"
        ],
        "scoring_coherent": "base(100) + bonus_max(150) - malus_min(0) = plafond 150",
        "vetos_absolus": "8 vetos définis — Priorité absolue sur score",
        "vetos_descendants": "Hiérarchie MN > W > D1 > H4 > H1 > M15 > M5",
        "exclusions": "10 exclusions absolues post-scoring",
        "terminus": "3 conditions minimum / score >= 70 requis",
        "logging": "Tous les verdicts logués avec détail complet"
    }
    return checks
```

---

## RÉFÉRENCES INTER-FICHIERS KB5

| Fichier | Rôle dans ce moteur |
|---------|---------------------|
| `00_GLOSSAIRE_UNIFIE.md` | Terminologie de tous les champs |
| `01_CADRE_FRACTAL_SPECIFIQUE.md` | Tags fractal/spécifique des zones PD Array |
| `02_PYRAMIDE_ANALYSE.md` | Pipeline qui produit le DOSSIER_PAIRE |
| `03_ICT_ENCYCLOPEDIE_v5.md` | Grille de scoring PD Array + Cascade + MMXM |
| `04_PRICE_ACTION_BIBLE_v4.md` | Score Signal Bar + H2/L2 + Terminus PA |
| `05_INSTRUMENTS_SPECIFIQUES.md` | Overrides sizing + exclusions par instrument |
| `06_DOSSIER_PAIRE_SCHEMA.md` | Format d'entrée du moteur (DOSSIER_PAIRE JSON) |

---

*Moteur de Décision v1.0 — KB5 Sentinel Pro — 2026-03-11*
*Architecture : 7 étapes séquentielles — 8 vetos absolus — Score 100pts — 10 exclusions*
*Produit : Verdict JSON avec sizing, raison, vetos, et log complet*
