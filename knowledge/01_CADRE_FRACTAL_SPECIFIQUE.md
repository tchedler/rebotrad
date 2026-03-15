---
version: "1.0"
type: "cadre_methodologique"
last_updated: "2026-03-11"
description: "Gouvernance Fractal vs Spécifique — KB5 Sentinel Pro"
role: "Fichier de gouvernance central. Lu en PREMIER par le bot avant toute analyse."
---

# 🔄 CADRE FRACTAL vs SPÉCIFIQUE v1.0 — SENTINEL PRO KB5
## Loi Fondamentale du Département Analyse

> **RÈGLE ABSOLUE :** Avant d'appliquer un concept ICT/SMC/PA, le bot DOIT vérifier
> sa nature (FRACTAL ou SPÉCIFIQUE) et ses conditions d'applicabilité.
> Un concept utilisé hors de son périmètre = analyse invalide = no-trade obligatoire.

---

## SECTION 1 — LES DEUX NATURES

### 1.1 Nature FRACTALE
Un concept est FRACTAL s'il :
- Fonctionne de manière IDENTIQUE sur tous les timeframes
- Seules l'amplitude (en pips) et la durée de formation changent
- La logique de détection est la même sur MN, W, D1, H4, H1, M15, M5, M1
- Peut être détecté par le FractalEngine universel

### 1.2 Nature SPÉCIFIQUE
Un concept est SPÉCIFIQUE s'il :
- N'est applicable que sur CERTAINS timeframes définis
- Et/ou N'est applicable que sur CERTAINS instruments définis
- Hors de son périmètre : concept NON APPLICABLE (pas de dégradation, suppression totale)
- Activé/désactivé par le SpecificModules engine

### 1.3 Règle de Cascade Fractale
La confluence entre TF est le VRAI POUVOIR du système fractal.
Un concept de TF inférieur DANS un concept de TF supérieur = bonus de score.

```
RÈGLE DE CASCADE :
FVG H1 DANS OB H4 DANS FVG D1 = Triple confluence A+++
→ Score bonus : +35 points (voir 07_MOTEUR_DECISION.md)

Double confluence (2 TF) : +15 points
Triple confluence (3 TF) : +35 points
Quadruple confluence (4 TF) : +50 points (extrêmement rare)
```

---

## SECTION 2 — GROUPE A : STRUCTURE DE MARCHÉ (100% FRACTAL)

Tous ces concepts fonctionnent identiquement sur MN, W, D1, H4, H1, M15, M5, M1.

### 2.1 MSS (Market Structure Shift)
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS

| TF | Interprétation | Amplitude typique |
|----|---------------|-------------------|
| MN | Retournement macro (années) | 500-5000 pips |
| W  | Retournement swing (semaines) | 200-1000 pips |
| D1 | Retournement journalier | 50-300 pips |
| H4 | Setup d'entrée HTF | 20-100 pips |
| H1 | Confirmation d'entrée | 10-50 pips |
| M15 | Entrée scalp | 5-20 pips |
| M5 | Entrée précise | 3-12 pips |
| M1 | Micro-entrée (zone CISD) | 1-5 pips |

- **Cascade :** MSS M1 dans FVG H1 dans OB H4 = confluence maximale
- **Condition absolue :** Displacement présent + Boolean_Sweep_ERL = True

### 2.2 CHoCH (Change of Character)
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS
- **Rôle :** Avertissement uniquement. PAS signal d'entrée.
- **Cascade :** CHoCH LTF sert d'alerte que le MSS HTF approche

### 2.3 BOS (Break of Structure)
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS
- **Rôle :** Confirmation de continuation de tendance

### 2.4 HH / HL / LH / LL
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS
- **Note :** Seule l'amplitude change selon le TF

### 2.5 Swing High / Swing Low
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS

---

## SECTION 3 — GROUPE B : LIQUIDITÉ (100% FRACTAL)

### 3.1 BSL / SSL
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS

| TF | BSL concret | SSL concret |
|----|------------|------------|
| MN | High 3-6 mois | Low 3-6 mois |
| W  | PWH (Previous Week High) | PWL (Previous Week Low) |
| D1 | PDH (Previous Day High) | PDL (Previous Day Low) |
| H4 | High session précédente | Low session précédente |
| H1 | High heure précédente | Low heure précédente |
| M5 | High 15 dernières minutes | Low 15 dernières minutes |

### 3.2 EQH / EQL (Equal Highs / Equal Lows)
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS
- **Règle détection :** 2+ niveaux alignés à ± 5 pips (ajuster selon ATR du TF)

### 3.3 Liquidity Void
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS

### 3.4 Smooth vs Jagged Highs/Lows
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS
- **Smooth :** Hauts/bas alignés = liquidité massive. Cible prioritaire.
- **Jagged :** Irréguliers = liquidité déjà prise ou non ciblée. Ignorer.

---

## SECTION 4 — GROUPE C : PD ARRAYS (100% FRACTAL)

### 4.1 FVG (Fair Value Gap)
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS

| TF | Amplitude typique | Puissance relative |
|----|------------------|-------------------|
| MN | 200-2000 pips | ★★★★★ (rare = ultra-puissant) |
| W  | 50-200 pips | ★★★★★ |
| D1 | 20-80 pips | ★★★★☆ |
| H4 | 10-40 pips | ★★★★☆ |
| H1 | 5-20 pips | ★★★☆☆ |
| M15 | 2-10 pips | ★★★☆☆ |
| M5 | 2-8 pips | ★★☆☆☆ |
| M1 | 1-5 pips | ★★☆☆☆ (micro-FVG scalp) |

- **Hiérarchie :** FVG MN > W > D1 > H4 > H1 > M15 > M5 > M1
- **Cascade :** FVG D1 contenant FVG H4 contenant FVG H1 = A+++

### 4.2 Order Block (OB)
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS (attention : BTC peut avoir faux OB par wash trading)
- **Scoring 0-5 :** identique sur tous les TF

### 4.3 Breaker Block
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS

### 4.4 Rejection Block
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS

### 4.5 Volume Imbalance (VI)
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS (attention : volume Forex = tick volume, pas volume réel)

### 4.6 Suspension Block (2025)
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS
- **Force :** +2 pts vs OB standard sur tous les TF

### 4.7 BPR (Balanced Price Range)
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS

### 4.8 CE (Consequent Encroachment)
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS
- **Calcul :** CE = (High_zone + Low_zone) / 2 — identique sur tous les TF

### 4.9 Premium / Discount
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS
- **Calcul :** EQ = (High_range + Low_range) / 2. Au-dessus = Premium. En-dessous = Discount.

### 4.10 OTE (Optimal Trade Entry)
- **Nature :** FRACTAL (le principe), ATTENTION sur l'application
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS
- **RÈGLE CRITIQUE :** Le Fibonacci se trace sur le DERNIER SWING du TF d'EXÉCUTION.
  OTE H4 ≠ OTE H1 (deux zones différentes, l'une dans l'autre possible).
- **Zone OTE :** 61.8% - 79% (niveaux 0.618 à 0.79 du swing)

---

## SECTION 5 — GROUPE D : MODÈLES COMPORTEMENTAUX (FRACTAL)

### 5.1 MMXM (Market Maker Model)
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1 (⚠️ M1 = dégradé)
- **Instruments :** TOUS

| TF | Durée du cycle complet |
|----|----------------------|
| MN/W | 3-6 mois |
| D1 | 1-5 jours |
| H4/H1 | 4-24 heures |
| M15/M5 | 30-90 minutes |
| M1 | ⚠️ Trop court — utiliser CISD à la place |

### 5.2 Power of 3 (AMD)
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5 (⚠️ M1 = dégradé)
- **Instruments :** TOUS

| TF | Accumulation | Manipulation | Distribution |
|----|-------------|--------------|--------------|
| MN | Janvier | Février | Mars-Décembre |
| W  | Lundi | Mardi | Mer-Ven |
| D1 | 00h-08h NY | 08h-10h NY | 10h-16h NY |
| H1 | Début Killzone | Milieu Killzone | Fin Killzone |
| M1 | ⚠️ Utiliser CISD — PO3 trop micro |

### 5.3 Judas Swing
- **Nature :** FRACTAL (avec nuance)
- **TF applicables :** MN, W, D1, H4, H1
- **Instruments :** TOUS
- **NUANCE :** Les 6 phases complètes s'appliquent sur D1/H4.
  Sur H1 = 4 phases observables. Sur M15/M5/M1 = utiliser CISD.

### 5.4 Displacement
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS
- **Condition :** Corps bougie centrale > ATR(14) * 1.2 du TF considéré

### 5.5 Trapped Traders
- **Nature :** FRACTAL
- **TF applicables :** MN, W, D1, H4, H1, M15, M5, M1
- **Instruments :** TOUS

---

## SECTION 6 — CONCEPTS SPÉCIFIQUES PAR TIMEFRAME

### 6.1 SPÉCIFIQUES MN / W UNIQUEMENT

#### COT Report
- **Nature :** SPÉCIFIQUE
- **TF applicables :** MN, W (⚠️ D1 = contexte seulement)
- **Instruments :** FOREX, GOLD
- **Hors périmètre :** H4, H1, M15, M5, M1 = NON APPLICABLE
- **Règle :** COT = contexte macro uniquement. Jamais signal d'entrée direct.
- **Seuil :** Net Long > +50k = biais haussier macro. Net Short > -50k = biais baissier.

#### Saisonnalité / Quarterly Shift
- **Nature :** SPÉCIFIQUE
- **TF applicables :** MN, W
- **Instruments :** TOUS (statistiques par devise)
- **Hors périmètre :** D1 et inférieur = NON APPLICABLE
- **Règle :** Q1/Q2/Q3/Q4 = contexte macro de 3 mois. Ne jamais trader un signal
  intraday contre la saisonnalité forte.

#### IPDA Cycles 60 jours / 40 jours
- **Nature :** SPÉCIFIQUE
- **TF applicables :** MN, W, D1
- **Instruments :** TOUS
- **Hors périmètre :** H4 et inférieur = NON APPLICABLE pour 40j/60j

#### Yearly Seasonality par Devise
- **Nature :** SPÉCIFIQUE
- **TF applicables :** MN uniquement
- **Instruments :** FOREX
- **Hors périmètre :** W et inférieur = contexte uniquement

#### IPDA Cycle 20 jours (Lookback T-20)
- **Nature :** SPÉCIFIQUE
- **TF applicables :** MN, W, D1, H4 (maximum)
- **Instruments :** TOUS
- **Hors périmètre :** H1 et inférieur = NON APPLICABLE directement

#### Weekly Templates (5 types)
- **Nature :** SPÉCIFIQUE
- **TF applicables :** W UNIQUEMENT
- **Instruments :** FOREX, GOLD (moins fiable sur BTC)
- **Hors périmètre :** D1 et inférieur = contexte uniquement, jamais signal
- **Fréquence :** Identifié le dimanche soir. Valide pour la semaine entière.

### 6.2 SPÉCIFIQUES DAILY UNIQUEMENT

#### CBDR (Central Bank Decision Range)
- **Nature :** SPÉCIFIQUE
- **TF applicables :** D1 UNIQUEMENT (calcul entre 17h-20h EST)
- **Instruments :** FOREX UNIQUEMENT
- **Hors périmètre :** H4 et inférieur = lecture du résultat seulement
- **Calcul :** 1 fois par jour. Résultat utilisable toute la journée suivante.

#### NDOG (New Day Opening Gap)
- **Nature :** SPÉCIFIQUE
- **TF applicables :** D1 au début de chaque journée (00h NY)
- **Instruments :** TOUS (très puissant sur Indices)
- **Validité :** Perd sa signification après 2h de trading

#### Daily Bias
- **Nature :** SPÉCIFIQUE
- **TF applicables :** D1 — établi une fois par jour
- **Instruments :** TOUS
- **Règle :** Contexte journalier. Jamais signal d'entrée direct.

### 6.3 SPÉCIFIQUES H4 / H1

#### Grail Setup (5 conditions)
- **Nature :** SPÉCIFIQUE
- **TF applicables :** H4, H1 (⚠️ M15 = adaptation possible)
- **Instruments :** FOREX, GOLD
- **Hors périmètre :** D1 = trop lent. M5/M1 = trop rapide.

#### Unicorn Model
- **Nature :** SPÉCIFIQUE
- **TF applicables :** H4 + H1 simultanément (idéal)
- **Instruments :** FOREX, GOLD, INDICES
- **Adaptation :** M5 + M1 = "micro-unicorn" score réduit à 75/100

### 6.4 SPÉCIFIQUES INTRADAY (M15 / M5 / M1)

#### Silver Bullet
- **Nature :** SPÉCIFIQUE
- **TF applicables :** M5 (⚠️ M15 = adaptation)
- **Instruments :** FOREX, GOLD principalement
- **Fenêtres :** 10h-11h / 14h-15h / 20h-21h EST UNIQUEMENT
- **Hors périmètre :** H1, D1 = NON APPLICABLE

#### CISD (Change in State of Delivery) 2026
- **Nature :** SPÉCIFIQUE
- **TF applicables :** M1, M5, M15 (⚠️ H1 = adaptation)
- **Instruments :** TOUS
- **Hors périmètre :** D1 et supérieur = utiliser MSS classique

#### Venom Model
- **Nature :** SPÉCIFIQUE
- **TF applicables :** M5, M15 UNIQUEMENT
- **Instruments :** NQ, ES, YM (DOW) EXCLUSIVEMENT
- **Hors périmètre :** FOREX, BTC, GOLD = NON APPLICABLE
- **Fenêtre :** 08h00-11h00 EST uniquement

#### 1st Presented FVG
- **Nature :** SPÉCIFIQUE
- **TF applicables :** M1, M5 UNIQUEMENT
- **Instruments :** TOUS
- **Fenêtre :** 09:30-10:00 NY UNIQUEMENT
- **Validité :** Journée entière (biais scellé à 90%)

#### Killzones (timing précis)
- **Nature :** SPÉCIFIQUE
- **TF applicables :** M5, M15, H1 (timing précis)
- **Instruments :** FOREX, GOLD, INDICES
- **Note :** Sur D1 = noter globalement "London" ou "NY", pas timing précis

---

## SECTION 7 — MATRICE COMPLÈTE D'APPLICABILITÉ

```
CONCEPT              MN   W    D1   H4   H1   M15  M5   M1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FRACTALS (universels)
MSS/CHoCH/BOS         ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅
FVG                   ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅
Order Block           ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅
BSL/SSL               ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅
EQH/EQL               ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅
Liquidity Void        ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅
Displacement          ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅
Breaker Block         ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅
BPR                   ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅
Suspension Block      ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅
Premium/Discount      ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅
CE                    ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅
OTE (Fib 62-79%)      ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅
Trapped Traders       ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅
MMXM                  ✅   ✅   ✅   ✅   ✅   ✅   ✅   ⚠️
Power of 3 (AMD)      ✅   ✅   ✅   ✅   ✅   ✅   ✅   ⚠️
Judas Swing           ✅   ✅   ✅   ✅   ✅   ⚠️  ❌   ❌
SOD                   ✅   ✅   ✅   ✅   ✅   ✅   ✅   ✅

SPÉCIFIQUES TF
COT Report            ✅   ✅   ⚠️  ❌   ❌   ❌   ❌   ❌
Saisonnalité          ✅   ✅   ❌   ❌   ❌   ❌   ❌   ❌
IPDA 60j/40j          ✅   ✅   ✅   ❌   ❌   ❌   ❌   ❌
IPDA 20j              ✅   ✅   ✅   ✅   ❌   ❌   ❌   ❌
Weekly Templates      ❌   ✅   ❌   ❌   ❌   ❌   ❌   ❌
CBDR                  ❌   ❌   ✅   ❌   ❌   ❌   ❌   ❌
NDOG/NWOG             ❌   ✅   ✅   ❌   ❌   ❌   ❌   ❌
Daily Bias            ❌   ❌   ✅   ❌   ❌   ❌   ❌   ❌
Grail Setup           ❌   ❌   ❌   ✅   ✅   ⚠️  ❌   ❌
Unicorn Model         ❌   ❌   ❌   ✅   ✅   ❌   ❌   ❌
Silver Bullet         ❌   ❌   ❌   ❌   ❌   ⚠️  ✅   ❌
CISD 2026             ❌   ❌   ❌   ❌   ⚠️  ✅   ✅   ✅
Venom Model           ❌   ❌   ❌   ❌   ❌   ✅   ✅   ❌
1st Presented FVG     ❌   ❌   ❌   ❌   ❌   ⚠️  ✅   ✅
Killzones précises    ❌   ❌   ⚠️  ✅   ✅   ✅   ✅   ✅
Macros ICT            ❌   ❌   ❌   ❌   ✅   ✅   ✅   ✅

SPÉCIFIQUES INSTRUMENT
COT Gold              ✅   ✅   ⚠️  ❌   ❌   ❌   ❌   ❌
Funding Rate BTC      ✅   ✅   ✅   ⚠️  ❌   ❌   ❌   ❌
Venom (Indices)       ❌   ❌   ❌   ❌   ❌   ✅   ✅   ❌
London Fix (Gold)     ❌   ❌   ✅   ✅   ✅   ❌   ❌   ❌
VIX (Indices)         ✅   ✅   ✅   ✅   ⚠️  ❌   ❌   ❌
Halving BTC           ✅   ✅   ❌   ❌   ❌   ❌   ❌   ❌
Real Yields (Gold)    ✅   ✅   ✅   ❌   ❌   ❌   ❌   ❌
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ = Applicable   ⚠️ = Partiel/Adapté   ❌ = Non applicable
```

---

## SECTION 8 — ARCHITECTURE DU MOTEUR

### 8.1 FractalEngine (universel)
```python
class FractalEngine:
    """
    Tourne sur TOUS les TF et TOUS les instruments.
    Détecte les concepts fractals de manière identique.
    """
    def run(self, candles: list, timeframe: str, instrument: str) -> dict:
        return {
            "mss":           self.detect_mss(candles),
            "choch":         self.detect_choch(candles),
            "bos":           self.detect_bos(candles),
            "fvg_list":      self.detect_all_fvg(candles),
            "ob_list":       self.detect_all_ob(candles),
            "breaker_list":  self.detect_breakers(candles),
            "suspension_list": self.detect_suspension_blocks(candles),
            "bsl_levels":    self.detect_bsl(candles),
            "ssl_levels":    self.detect_ssl(candles),
            "eqh_eql":       self.detect_equal_levels(candles),
            "smooth_jagged": self.classify_highs_lows(candles),
            "premium_disc":  self.calculate_pd_zone(candles),
            "eq":            self.calculate_equilibrium(candles),
            "ote_zone":      self.calculate_ote(candles),
            "mmxm_phase":    self.detect_mmxm_phase(candles),
            "sod":           self.detect_sod(candles),
            "displacement":  self.detect_displacement(candles),
            "trapped":       self.detect_trapped_traders(candles),
            "sweep_erl":     self.check_erl_sweep(candles),
            "sweep_irl":     self.check_irl_sweep(candles),
        }
```

### 8.2 SpecificModules (conditionnel)
```python
class SpecificModules:
    """
    Chaque module s'active UNIQUEMENT si TF et instrument sont dans le périmètre.
    """
    MODULE_ACTIVATION = {
        "cot":              {"tf": ["MN","W"],              "instruments": ["FOREX","GOLD"]},
        "seasonality":      {"tf": ["MN","W"],              "instruments": ["ALL"]},
        "yearly_season":    {"tf": ["MN"],                  "instruments": ["FOREX"]},
        "ipda_60_40":       {"tf": ["MN","W","D1"],         "instruments": ["ALL"]},
        "ipda_20":          {"tf": ["MN","W","D1","H4"],    "instruments": ["ALL"]},
        "weekly_template":  {"tf": ["W"],                   "instruments": ["FOREX","GOLD"]},
        "cbdr":             {"tf": ["D1"],                  "instruments": ["FOREX"]},
        "ndog":             {"tf": ["D1"],                  "instruments": ["ALL"]},
        "nwog":             {"tf": ["W"],                   "instruments": ["ALL"]},
        "daily_bias":       {"tf": ["D1"],                  "instruments": ["ALL"]},
        "grail_setup":      {"tf": ["H4","H1"],             "instruments": ["FOREX","GOLD"]},
        "unicorn_model":    {"tf": ["H4","H1"],             "instruments": ["FOREX","GOLD","INDICES"]},
        "silver_bullet":    {"tf": ["M5","M15"],            "instruments": ["FOREX","GOLD"]},
        "cisd":             {"tf": ["M1","M5","M15"],       "instruments": ["ALL"]},
        "venom_model":      {"tf": ["M5","M15"],            "instruments": ["NQ","ES","YM"]},
        "first_fvg":        {"tf": ["M1","M5"],             "instruments": ["ALL"]},
        "killzone_precise": {"tf": ["H1","M15","M5"],       "instruments": ["FOREX","GOLD","INDICES"]},
        "macros_ict":       {"tf": ["H1","M15","M5","M1"],  "instruments": ["ALL"]},
        # Spécifiques instruments
        "cot_gold":         {"tf": ["MN","W"],              "instruments": ["GOLD"]},
        "funding_rate":     {"tf": ["MN","W","D1"],         "instruments": ["BTC","ETH"]},
        "london_fix":       {"tf": ["D1","H4","H1"],        "instruments": ["GOLD"]},
        "vix_sentiment":    {"tf": ["MN","W","D1","H4"],    "instruments": ["NQ","ES","YM"]},
        "halving_cycle":    {"tf": ["MN","W"],              "instruments": ["BTC"]},
        "real_yields":      {"tf": ["MN","W","D1"],         "instruments": ["GOLD"]},
        "opec_eia":         {"tf": ["MN","W","D1"],         "instruments": ["WTI","BRENT"]},
    }

    def get_active_modules(self, timeframe: str, instrument: str) -> list:
        active = []
        for module, config in self.MODULE_ACTIVATION.items():
            tf_ok = timeframe in config["tf"]
            inst_ok = "ALL" in config["instruments"] or instrument in config["instruments"]
            if tf_ok and inst_ok:
                active.append(module)
        return active
```

### 8.3 FractalCascade (bonus de confluence)
```python
class FractalCascade:
    """
    Calcule le bonus de score pour les confluences multi-TF.
    Un FVG H1 DANS un OB H4 DANS un FVG D1 = score x2.
    """
    CASCADE_BONUS = {
        2: 15,   # Double confluence (2 TF alignés)
        3: 35,   # Triple confluence (3 TF alignés)
        4: 50,   # Quadruple confluence (rare = A+++)
    }

    def calculate_fractal_confluence(self, dossier: dict) -> int:
        score_bonus = 0

        fvg_h1 = dossier.get("h1", {}).get("fvg_list", [])
        ob_h4  = dossier.get("h4", {}).get("ob_list", [])
        fvg_d1 = dossier.get("daily", {}).get("fvg_list", [])
        ob_w   = dossier.get("weekly", {}).get("ob_list", [])

        for fvg in fvg_h1:
            tfs_aligned = 1
            for ob in ob_h4:
                if ob["low"] <= fvg["ce"] <= ob["high"] and ob["freshness"] != "INVALIDE":
                    tfs_aligned = 2
                    for fvg_d in fvg_d1:
                        if fvg_d["low"] <= ob["ce"] <= fvg_d["high"] and fvg_d["freshness"] != "INVALIDE":
                            tfs_aligned = 3
                            for ob_w_item in ob_w:
                                if ob_w_item["low"] <= fvg_d["ce"] <= ob_w_item["high"]:
                                    tfs_aligned = 4
            if tfs_aligned >= 2:
                score_bonus += self.CASCADE_BONUS.get(tfs_aligned, 0)

        return score_bonus
```

---

## SECTION 9 — RÈGLES D'APPLICATION

### 9.1 Ordre de lecture obligatoire
```
Étape 1 : Identifier le TF d'analyse et l'instrument
Étape 2 : Lancer FractalEngine → résultats fractals (toujours disponibles)
Étape 3 : Appeler get_active_modules(TF, instrument) → liste des modules actifs
Étape 4 : Exécuter UNIQUEMENT les modules de la liste active
Étape 5 : Calculer FractalCascade → bonus de confluence multi-TF
Étape 6 : Passer au fichier 07_MOTEUR_DECISION pour le scoring final
```

### 9.2 Règle anti-erreur TF
```
INTERDIT :
- Chercher un Weekly Template sur M15
- Appliquer CBDR sur H1
- Utiliser le Venom Model sur EUR/USD
- Appliquer COT sur M5
- Utiliser Silver Bullet sur D1

Si le bot tente d'activer un module hors périmètre :
→ ERREUR CRITIQUE → Log + blocage automatique
```

### 9.3 Règle de dégradation ⚠️
```
Un concept marqué ⚠️ (partiel/adapté) :
- Peut être utilisé mais avec score réduit de 50%
- Ne peut jamais servir de signal principal
- Peut servir de confirmation secondaire uniquement
```

---

*01_CADRE_FRACTAL_SPECIFIQUE.md — KB5 Sentinel Pro v1.0 — 2026-03-11*
*Gouvernance centrale du Département Analyse*
