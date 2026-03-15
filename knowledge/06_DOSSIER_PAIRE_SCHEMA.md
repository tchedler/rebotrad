---
version: "1.0"
type: "dossier_paire_schema"
last_updated: "2026-03-11"
description: "Contrat de données — Format JSON du DOSSIER_PAIRE produit par le département analyse"
source: "KB5 Extensions — Interface entre analyse et moteur de décision"
---

# 📋 DOSSIER PAIRE SCHEMA v1.0 — SENTINEL PRO KB5
## Format de Sortie du Département Analyse — Contrat de Données

> **RÔLE :** Ce fichier définit la structure exacte du `DOSSIER_PAIRE` JSON produit après
> chaque analyse complète (pipeline 02_PYRAMIDE_ANALYSE.md exécuté).
> Le `07_MOTEUR_DECISION.md` lit ce dossier pour produire le verdict final.
> **RÈGLE :** Tout champ marqué `OBLIGATOIRE` doit être renseigné. Un champ manquant = analyse invalide.

---

## SECTION 1 — STRUCTURE JSON COMPLÈTE

```json
{
  "DOSSIER_PAIRE": {

    "meta": {
      "paire": "EUR/USD",
      "instrument_type": "FOREX",
      "analyse_timestamp": "2026-03-11T21:00:00Z",
      "analyste": "SENTINEL_BOT_v5",
      "pipeline_version": "KB5_v1.0",
      "validite_heures": 4,
      "statut": "COMPLET"
    },

    "biais_htf": {
      "monthly_bias": "BULLISH",
      "weekly_bias": "BULLISH",
      "daily_bias": "BULLISH",
      "h4_bias": "BULLISH",
      "bias_global": "BULLISH",
      "conflits_htf": false,
      "detail_conflit": null
    },

    "ipda": {
      "t20_high": 1.09500,
      "t20_low": 1.07200,
      "t20_eq": 1.08350,
      "t20_position": "DISCOUNT",
      "t40_direction": "BULLISH",
      "t60_direction": "BULLISH",
      "quarterly_shift_active": false,
      "quarterly_shift_regime": "NORMAL"
    },

    "liquidite": {
      "bsl_targets": [
        {"niveau": 1.09500, "type": "PWH", "priorite": "HAUTE", "freshness": "FRAIS"},
        {"niveau": 1.09200, "type": "EQH", "priorite": "MOYENNE", "freshness": "FRAIS"}
      ],
      "ssl_targets": [
        {"niveau": 1.07200, "type": "PWL", "priorite": "HAUTE", "freshness": "FRAIS"},
        {"niveau": 1.07800, "type": "EQL", "priorite": "MOYENNE", "freshness": "MITIGÉ"}
      ],
      "erl_swept": true,
      "erl_type_swept": "SSL",
      "erl_sweep_timestamp": "2026-03-11T09h45Z",
      "boolean_sweep_erl": true,
      "dol_actif": {"niveau": 1.09200, "type": "EQH", "direction": "BULLISH"}
    },

    "pd_arrays": {
      "zones_actives": [
        {
          "id": "OB_H4_001",
          "type": "ORDER_BLOCK",
          "timeframe": "H4",
          "direction": "BULLISH",
          "high": 1.08150,
          "low": 1.07980,
          "ce": 1.08065,
          "freshness": "FRAIS",
          "score_ob": "4/5",
          "cascade": "CASCADE_DOUBLE",
          "cascade_bonus": 15,
          "within_htf_zone": "FVG_D1_001",
          "created_at": "2026-03-10T14h00Z",
          "visites": 0
        },
        {
          "id": "FVG_D1_001",
          "type": "FVG",
          "timeframe": "D1",
          "direction": "BULLISH",
          "high": 1.08200,
          "low": 1.07900,
          "ce": 1.08050,
          "freshness": "FRAIS",
          "cascade": "STANDALONE",
          "cascade_bonus": 0,
          "within_htf_zone": null,
          "created_at": "2026-03-09T00h00Z",
          "visites": 0
        }
      ],
      "zone_entree_optimale": "OB_H4_001",
      "zone_entree_ce": 1.08065
    },

    "structure_marche": {
      "h4_structure": "BULLISH",
      "h1_structure": "BULLISH",
      "m15_structure": "BULLISH",
      "dernier_mss": {
        "timeframe": "H1",
        "direction": "BULLISH",
        "niveau": 1.08100,
        "displacement": true,
        "timestamp": "2026-03-11T10h15Z"
      },
      "sod_actuel": "STRONG_DISTRIBUTION",
      "always_in": "AIL",
      "mmxm_phase": {
        "d1": "DISTRIBUTION",
        "h4": "ACCUMULATION",
        "h1": "DISTRIBUTION",
        "convergence": "BUY_CONTINUATION",
        "convergence_bonus": 10
      }
    },

    "timing": {
      "killzone_active": "NY_OPEN",
      "killzone_sizing": 1.0,
      "macro_active": true,
      "macro_numero": 3,
      "silver_bullet_active": false,
      "venom_active": false,
      "london_fix_proximity": false,
      "cbdr_range": 35,
      "cbdr_regime": "EXPLOSIF",
      "minutes_to_next_news": 180,
      "news_impact_next": 0
    },

    "analyse_pa": {
      "etat_marche": "CANAL",
      "always_in_pa": "AIL",
      "dernier_signal_bar": {
        "type": "BULLISH_SIGNAL_BAR",
        "rejection_pct": 65,
        "qualite": "A_PLUS_PLUS",
        "sur_zone_ict": "OB_H4_001",
        "timestamp": "2026-03-11T10h20Z"
      },
      "bar_count": "H2",
      "pullback_type": "TWO_BAR",
      "pullback_valid": true,
      "measured_move_target": 1.09200,
      "narration": "Pullback Two-Bar sain sur OB H4 frais en NY Open. Signal Bar rejet 65%. H2 formé. Biais ICT BULLISH D1+H4+H1 alignés. Entrée A++."
    },

    "intermarket": {
      "dxy_direction": "BEARISH",
      "dxy_aligned": true,
      "gbp_usd_direction": "BULLISH",
      "gbp_aligned": true,
      "spx_direction": "BULLISH",
      "spx_aligned": true,
      "yields_10y_direction": "BEARISH",
      "yields_aligned": true,
      "cot_bias": "BULLISH_FORT",
      "cot_semaine": "2026-03-07",
      "piliers_alignes": 5,
      "piliers_conflit": 0,
      "smt_bonus": 20,
      "vix": 14.5,
      "vix_regime": "CALME"
    },

    "instrument_specifique": {
      "instrument": "EUR/USD",
      "cbdr_applied": true,
      "weekly_template": "CLASSIC_UP",
      "weekly_template_prob": 0.45,
      "spread_actuel": 1.2,
      "spread_ok": true,
      "london_fix_active": false,
      "funding_rate": null,
      "open_interest_signal": null,
      "eia_proximity": false,
      "opec_proximity": false,
      "overrides_actifs": []
    },

    "scoring": {
      "base": {
        "killzone_macro": 20,
        "erl_sweep": 20,
        "pd_array_qualite": 20,
        "dol_rr": 20,
        "smt_correlation": 20,
        "sous_total_base": 100
      },
      "bonus": {
        "enigma_entry": 0,
        "weekly_template": 5,
        "first_presented_fvg": 0,
        "cascade_double": 15,
        "cascade_triple": 0,
        "mmxm_convergence": 10,
        "smt_bonus": 20,
        "total_bonus": 50
      },
      "malus": {
        "target_hors_niveau": 0,
        "premium_t20": 0,
        "news_proximity": 0,
        "h3_detected": 0,
        "vix_eleve": 0,
        "total_malus": 0
      },
      "score_final": 100,
      "categorie": "EXECUTION_A_PLUS_PLUS",
      "sizing_recommande": 1.0
    },

    "trade_plan": {
      "direction": "LONG",
      "entry_price": 1.08065,
      "entry_type": "LIMIT",
      "stop_loss": 1.07960,
      "sl_type": "OUTSIDE_OB",
      "sl_distance_pips": 10.5,
      "tp1": 1.08500,
      "tp1_pct_close": 25,
      "tp2": 1.08900,
      "tp2_pct_close": 25,
      "tp3": 1.09200,
      "tp3_pct_close": 50,
      "rr_tp1": 4.1,
      "rr_tp3": 10.8,
      "terminus_conditions": {
        "measured_move_atteint": false,
        "killzone_active": true,
        "enigma_00_50_proche": false,
        "terminus_score": 0
      },
      "be_trigger": "APRES_TP1",
      "trailing_mode": false
    },

    "verdict": {
      "autorisation": "EXECUTER",
      "confiance": "A_PLUS_PLUS",
      "score": 100,
      "raison_principale": "Score 100/100 — Grail Setup complet — Cascade Double H4+D1 — MMXM convergence — COT BULLISH_FORT — 5/5 piliers SMT alignés",
      "vetos_actifs": [],
      "timestamp_verdict": "2026-03-11T10h25Z"
    }
  }
}
```

---

## SECTION 2 — DÉFINITION DES CHAMPS

### 2.1 Bloc `meta` — Obligatoire

| Champ | Type | Valeurs | Obligatoire | Description |
|-------|------|---------|-------------|-------------|
| `paire` | string | "EUR/USD", "NQ", "BTC/USD"... | ✅ | Instrument analysé |
| `instrument_type` | enum | FOREX, INDICES, BTC, OR, PETROLE | ✅ | Classe d'actif |
| `analyse_timestamp` | ISO8601 | datetime UTC | ✅ | Moment de l'analyse |
| `validite_heures` | int | 1-8 | ✅ | Durée de validité du dossier |
| `statut` | enum | COMPLET, PARTIEL, INVALIDE | ✅ | PARTIEL = moteur bloqué |

### 2.2 Bloc `biais_htf` — Obligatoire

| Champ | Type | Valeurs | Obligatoire |
|-------|------|---------|-------------|
| `monthly_bias` | enum | BULLISH, BEARISH, NEUTRE, UNKNOWN | ✅ |
| `weekly_bias` | enum | BULLISH, BEARISH, NEUTRE, UNKNOWN | ✅ |
| `daily_bias` | enum | BULLISH, BEARISH, NEUTRE, UNKNOWN | ✅ |
| `h4_bias` | enum | BULLISH, BEARISH, NEUTRE, UNKNOWN | ✅ |
| `bias_global` | enum | BULLISH, BEARISH, CONFLIT, UNKNOWN | ✅ |
| `conflits_htf` | bool | true/false | ✅ |

**Règle de calcul `bias_global` :**
```python
def calc_bias_global(monthly, weekly, daily, h4):
    biases = [monthly, weekly, daily, h4]
    bullish_count = biases.count("BULLISH")
    bearish_count = biases.count("BEARISH")

    if bullish_count >= 3 and bearish_count == 0:
        return "BULLISH", False
    elif bearish_count >= 3 and bullish_count == 0:
        return "BEARISH", False
    elif bullish_count >= 2 and bearish_count <= 1:
        return "BULLISH", True   # Conflit mineur
    elif bearish_count >= 2 and bullish_count <= 1:
        return "BEARISH", True   # Conflit mineur
    else:
        return "CONFLIT", True   # Conflit majeur → Réduire size 50%
```

### 2.3 Bloc `liquidite` — Obligatoire

| Champ | Type | Obligatoire | Description |
|-------|------|-------------|-------------|
| `boolean_sweep_erl` | bool | ✅ | RÈGLE ABSOLUE — False = dossier invalide |
| `erl_swept` | bool | ✅ | ERL purgé OUI/NON |
| `erl_type_swept` | enum | ✅ si swept | BSL, SSL |
| `dol_actif` | object | ✅ | Direction of Liquidity active |
| `bsl_targets` | array | ✅ | Liste des cibles BSL |
| `ssl_targets` | array | ✅ | Liste des cibles SSL |

**Statuts Freshness autorisés :**

| Freshness | Utilisation autorisée | Score |
|-----------|----------------------|-------|
| `FRAIS` | ✅ Oui — Force maximale | 100% |
| `MITIGÉ` | ✅ Avec précaution | 70% |
| `REVISITÉ` | ⚠️ Sauf confluence majeure | 40% |
| `INVALIDE` | ❌ Supprimer du dossier | 0% |

### 2.4 Bloc `pd_arrays` — Obligatoire

Chaque zone active doit avoir :
- `id` unique (type_TF_numéro)
- `type` : ORDER_BLOCK, FVG, BREAKER_BLOCK, SUSPENSION_BLOCK, BPR, REJECTION_BLOCK, CE, RDRB
- `freshness` : FRAIS, MITIGÉ, REVISITÉ, INVALIDE
- `cascade` : CASCADE_TRIPLE, CASCADE_DOUBLE, STANDALONE
- `cascade_bonus` : 35, 15, ou 0

### 2.5 Bloc `scoring` — Obligatoire

Le scoring est calculé automatiquement selon la grille de `03_ICT_ENCYCLOPEDIE_v5.md` Section 10.2.

```python
def calculate_score(dossier):
    # Base 100 pts
    base = (
        dossier["timing"]["killzone_active"] != None and 20 or 0
        + (dossier["liquidite"]["boolean_sweep_erl"] == True and 20 or 0)
        + get_pd_array_score(dossier["pd_arrays"]["zone_entree_optimale"])
        + (dossier["trade_plan"]["rr_tp3"] >= 2.0 and 20 or 0)
        + get_smt_score(dossier["intermarket"]["piliers_alignes"])
    )

    # Bonus
    bonus = (
        dossier["scoring"]["bonus"]["enigma_entry"]
        + dossier["scoring"]["bonus"]["weekly_template"]
        + dossier["scoring"]["bonus"]["cascade_double"]
        + dossier["scoring"]["bonus"]["cascade_triple"]
        + dossier["scoring"]["bonus"]["mmxm_convergence"]
        + dossier["scoring"]["bonus"]["smt_bonus"]
    )

    # Malus
    malus = sum(dossier["scoring"]["malus"].values())

    score_final = min(100, base + bonus - malus)
    return score_final
```

### 2.6 Bloc `verdict` — Produit par `07_MOTEUR_DECISION.md`

| Champ | Type | Valeurs |
|-------|------|---------|
| `autorisation` | enum | EXECUTER, ATTENDRE, PASSER, INTERDIT |
| `confiance` | enum | A_PLUS_PLUS, A, B, REFUSE |
| `score` | int | 0-100+ |
| `vetos_actifs` | array | Liste des règles de veto déclenchées |

---

## SECTION 3 — RÈGLES DE VALIDITÉ DU DOSSIER

### 3.1 Conditions d'Invalidation Automatique

```python
def validate_dossier(dossier):
    errors = []

    # Règle 1 — Anti-Inducement absolu
    if not dossier["liquidite"]["boolean_sweep_erl"]:
        errors.append("FATAL: boolean_sweep_erl = False — Dossier invalide")

    # Règle 2 — Biais global inconnu
    if dossier["biais_htf"]["bias_global"] == "UNKNOWN":
        errors.append("FATAL: bias_global = UNKNOWN — Analyse HTF incomplète")

    # Règle 3 — Statut partiel
    if dossier["meta"]["statut"] == "INVALIDE":
        errors.append("FATAL: meta.statut = INVALIDE")

    # Règle 4 — Aucune zone PD Array active
    if len(dossier["pd_arrays"]["zones_actives"]) == 0:
        errors.append("FATAL: Aucune zone PD Array identifiée")

    # Règle 5 — SOD MANIPULATION ou UNKNOWN
    if dossier["structure_marche"]["sod_actuel"] in ["MANIPULATION", "UNKNOWN"]:
        errors.append("FATAL: SOD = MANIPULATION ou UNKNOWN — Freeze")

    # Règle 6 — Score insuffisant
    if dossier["scoring"]["score_final"] < 65:
        errors.append(f"REFUS: Score {dossier['scoring']['score_final']} < 65")

    # Règle 7 — News imminentes
    if dossier["timing"]["minutes_to_next_news"] < 30 and        dossier["timing"]["news_impact_next"] >= 8:
        errors.append("FREEZE: News haute impact < 30 min")

    return len(errors) == 0, errors
```

### 3.2 Durée de Validité du Dossier

| Timeframe d'analyse | Durée de validité |
|---------------------|------------------|
| MN/W (Swing) | 7 jours |
| D1 (Swing) | 24 heures |
| H4 (Intraday) | 4 heures |
| H1 (Intraday) | 2 heures |
| M15/M5 (Scalp) | 30 minutes |

```python
def is_dossier_expired(dossier, current_time):
    from datetime import datetime, timedelta
    analyse_time = datetime.fromisoformat(dossier["meta"]["analyse_timestamp"])
    validity_h = dossier["meta"]["validite_heures"]
    expiry = analyse_time + timedelta(hours=validity_h)
    return current_time > expiry
```

---

## SECTION 4 — FLUX DE MISE À JOUR

### 4.1 Événements Déclenchant une Mise à Jour Obligatoire

```
MISE À JOUR OBLIGATOIRE si :
1. Une zone PD Array change de freshness (FRAIS → MITIGÉ)
2. Le SOD change d'état
3. Un ERL est purgé (boolean_sweep_erl passe à True)
4. Un MSS se forme sur H4 ou supérieur
5. Le dossier expire (durée de validité atteinte)
6. News haute impact publiée
7. VIX change de régime (ex: < 20 → > 25)
```

### 4.2 Mise à Jour Partielle vs Complète

```python
def determine_update_type(event):
    full_update_triggers = [
        "MSS_HTF", "BIAS_CHANGE", "DOSSIER_EXPIRE", "NEWS_PUBLISHED"
    ]
    partial_update_triggers = [
        "FRESHNESS_CHANGE", "SOD_UPDATE", "VIX_REGIME_CHANGE", "SPREAD_UPDATE"
    ]

    if event in full_update_triggers:
        return "FULL_REANALYSIS"      # Reprendre pipeline complet
    elif event in partial_update_triggers:
        return "PARTIAL_UPDATE"       # Mettre à jour les blocs concernés
    else:
        return "NO_UPDATE_NEEDED"
```

---

## SECTION 5 — EXEMPLE DOSSIER INVALIDE

```json
{
  "DOSSIER_PAIRE": {
    "meta": {
      "paire": "EUR/USD",
      "statut": "INVALIDE",
      "raison_invalidite": "boolean_sweep_erl = False — Aucun ERL purgé"
    },
    "liquidite": {
      "boolean_sweep_erl": false,
      "erl_swept": false
    },
    "verdict": {
      "autorisation": "INTERDIT",
      "confiance": "REFUSE",
      "score": 0,
      "raison_principale": "Anti-Inducement : ERL non purgé — Aucun signal valide",
      "vetos_actifs": ["VETO_ANTI_INDUCEMENT"]
    }
  }
}
```

---

## SECTION 6 — CODES STATUT ET MESSAGES STANDARDISÉS

### 6.1 Codes de Verdict

| Code | Signification | Action Bot |
|------|--------------|-----------|
| `EXECUTER` | Score ≥ 80, tous critères OK | Placer l'ordre |
| `ATTENDRE` | Score 65-79, manque 1 condition | Monitoring actif |
| `PASSER` | Conflit majeur, SMT adverse | Skip ce trade |
| `INTERDIT` | Règle absolue violée | Log + blacklist temporaire |
| `FREEZE` | News/Manipulation/VIX | Gel total jusqu'à levée |

### 6.2 Codes de Veto

| Veto | Déclencheur | Priorité |
|------|------------|---------|
| `VETO_ANTI_INDUCEMENT` | boolean_sweep_erl = False | ABSOLU |
| `VETO_SOD_MANIPULATION` | SOD = MANIPULATION | ABSOLU |
| `VETO_NEWS_FREEZE` | News < 30 min, impact ≥ 8 | ABSOLU |
| `VETO_HTF_CONFLIT` | Biais HTF opposé | FORT |
| `VETO_SCORE_INSUFFISANT` | Score < 65 | FORT |
| `VETO_VIX_EXTREME` | VIX > 35 (indices) | FORT |
| `VETO_FRESHNESS` | Toutes zones INVALIDE | FORT |
| `VETO_DOSSIER_EXPIRE` | Validité dépassée | MODÉRÉ |

---

## RÉFÉRENCES INTER-FICHIERS KB5

| Concept | Fichier source | Usage |
|---------|---------------|-------|
| Pipeline de génération du dossier | `02_PYRAMIDE_ANALYSE.md` | Ordre de remplissage |
| Définitions zones ICT | `03_ICT_ENCYCLOPEDIE_v5.md` | FVG, OB, freshness, scoring |
| Synergies PA dans le dossier | `04_PRICE_ACTION_BIBLE_v4.md` | bloc analyse_pa |
| Règles instrument | `05_INSTRUMENTS_SPECIFIQUES.md` | bloc instrument_specifique |
| Lecture du dossier + décision | `07_MOTEUR_DECISION.md` | Verdict final |

---

*Dossier Paire Schema v1.0 — KB5 Sentinel Pro — 2026-03-11*
*Contrat de données — Interface Analyse ↔ Moteur de Décision*
*Champs obligatoires + validation + flux de mise à jour*
