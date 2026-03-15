---
version: "1.0"
type: "instruments_specifiques"
last_updated: "2026-03-11"
description: "Règles ICT/PA adaptées par instrument — Forex, Indices US, BTC, Or, Pétrole"
source: "KB5 Extensions — Spécificités algorithme IPDA par classe d'actif"
---

# 🎯 INSTRUMENTS SPÉCIFIQUES v1.0 — SENTINEL PRO KB5
## Adaptations ICT/PA par Classe d'Actif

> **USAGE :** Ce fichier est consulté APRÈS 03_ICT_ENCYCLOPEDIE_v5.md et 04_PRICE_ACTION_BIBLE_v4.md.
> Il contient les OVERRIDES et RÈGLES SUPPLÉMENTAIRES propres à chaque instrument.
> Ce qui n'est pas mentionné ici = règles générales ICT/PA applicables sans modification.

---

## SECTION 1 — FOREX (EUR/USD, GBP/USD, USD/JPY, AUD/USD...)

### 1.1 Spécificités Algorithmiques Forex

**[SPÉCIFIQUE : TOUS TF FOREX — TOUS MODÈLES ICT APPLICABLES]**

Le Forex est l'environnement **natif** de l'ICT. Tous les modèles s'appliquent sans restriction.

**Caractéristiques clés :**
- Marché 24h/5j → Killzones critiques : London Open (03h-05h EST) et NY Open (08h-12h EST)
- Liquidité maximale lors des chevauchements London/NY (08h-12h EST)
- Spread variable : plus élevé aux heures creuses (20h-02h EST)
- Session Asiatique = Accumulation silencieuse → Piège pour les traders de range asiatique

### 1.2 CBDR — Central Bank Decision Range
**[SPÉCIFIQUE : D1 — FOREX UNIQUEMENT]**

```python
# Calcul quotidien obligatoire — 17h00 à 20h00 EST
CBDR_High = max(prix entre 17h00 et 20h00 EST)
CBDR_Low  = min(prix entre 17h00 et 20h00 EST)
CBDR_Range = CBDR_High - CBDR_Low  # en pips

# Interprétation
if CBDR_Range < 40:
    regime = "EXPLOSIF"
    sizing_next_day = 100  # % — Journée explosive probable
    macros_to_trade = [3, 5]  # Uniquement KZ3 et KZ5

elif CBDR_Range >= 40 and CBDR_Range <= 100:
    regime = "NORMAL"
    sizing_next_day = 80

elif CBDR_Range > 100:
    regime = "LARGE_RANGE"
    sizing_next_day = 60  # Range déjà large = prudence
```

**Paires applicables :** EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, USD/CHF, NZD/USD
**Paires NON applicables :** Crypto, Indices, Pétrole

### 1.3 Weekly Templates Forex
**[SPÉCIFIQUE : W1 — FOREX/GOLD]**

Consulter Section 7 de l'encyclopédie ICT pour la liste complète.

**Priorité identification dimanche soir :**
```python
def identify_weekly_template(cot_bias, ipda_t20_position, prev_week_structure):
    if cot_bias == "BULLISH" and ipda_t20_position == "DISCOUNT":
        base_template = "CLASSIC_UP"       # +10% probabilité
    elif cot_bias == "BEARISH" and ipda_t20_position == "PREMIUM":
        base_template = "CLASSIC_DOWN"     # +10% probabilité
    elif prev_week_structure == "CHOPPY":
        base_template = "CLASSIC"          # Retour à la normale probable
    else:
        base_template = "UNKNOWN"          # Attendre lundi

    return base_template
```

### 1.4 COT — Commitment of Traders Forex
**[SPÉCIFIQUE : MN/W — FOREX/GOLD]**

| Paire | Contrat CME à surveiller | Lecture |
|-------|------------------------|---------|
| EUR/USD | EUR Futures | Non-Comm. Longs nets ↑ = EUR haussier |
| GBP/USD | GBP Futures | Non-Comm. Longs nets ↑ = GBP haussier |
| USD/JPY | JPY Futures | Non-Comm. Longs nets ↑ = JPY haussier = USD/JPY baissier |
| AUD/USD | AUD Futures | Non-Comm. Longs nets ↑ = AUD haussier |
| XAU/USD | Gold Futures COMEX | Non-Comm. Longs nets ↑ = Or haussier |

**Règle COT pour le bot :**
```python
def cot_bias(non_comm_longs_net, prev_week_net):
    delta = non_comm_longs_net - prev_week_net
    if delta > 5000:      return "BULLISH_FORT"
    elif delta > 0:       return "BULLISH_FAIBLE"
    elif delta < -5000:   return "BEARISH_FORT"
    elif delta < 0:       return "BEARISH_FAIBLE"
    else:                 return "NEUTRE"
```

### 1.5 Corrélations Forex Critiques

| Paire | Corrélé Positif | Corrélé Négatif | Règle Bot |
|-------|----------------|-----------------|-----------|
| EUR/USD | GBP/USD (+0.80) | DXY (-0.85) | Si GBP opposé → Réduire 40% |
| AUD/USD | NZD/USD (+0.90) | Copper baisse | Si Copper bear → PASS |
| USD/JPY | Risk-off actif | SPX bearish → JPY fort | VIX > 25 = USD/JPY risqué |
| USD/CAD | Pétrole inverse (-0.70) | — | Oil ↑ = USD/CAD ↓ = attention |

### 1.6 Silver Bullet Forex
**[SPÉCIFIQUE : M5 — FOREX/GOLD]**

Les 3 fenêtres Silver Bullet s'appliquent pleinement sur Forex :
- SB1 : 10h00-11h00 EST → Post-NY Open, premier retournement
- SB2 : 14h00-15h00 EST → Réouverture NY PM
- SB3 : 20h00-21h00 EST → Ouverture Asie (moins fiable)

**Condition supplémentaire Forex :**
- Le spread doit être < 2 pips au moment de l'entrée
- Éviter SB3 les lundis (spread élargi ouverture semaine)

---

## SECTION 2 — INDICES US (NQ, ES, YM, RTY)

### 2.1 Spécificités Algorithmiques Indices

**[SPÉCIFIQUE : TOUS TF INDICES — ADAPTATIONS MAJEURES]**

Les indices ont des **comportements différents** du Forex :
- Marché fermé le week-end → Gaps d'ouverture fréquents (NWOG)
- Session unique efficace : 09h30-16h00 EST
- VIX = indicateur de volatilité institutionnelle → Crucial
- Corrélations entre NQ/ES/YM très fortes (+0.90)
- RTY (Russell 2000) = Indicateur de risk appetite

### 2.2 Venom Trading Model — NQ/ES/YM Exclusif
**[SPÉCIFIQUE : M5/M15 — NQ/ES/YM UNIQUEMENT]**
**[⛔ NON APPLICABLE : FOREX, BTC, GOLD, PÉTROLE]**

```python
# Activation automatique chaque jour de trading
def venom_setup(session_data):
    # Étape 1 : Tracer le 90-min Range
    range_high = max(session_data["08h00_to_09h30"]["highs"])
    range_low  = min(session_data["08h00_to_09h30"]["lows"])

    # Étape 2 : Détection du sweep à 09h30
    if session_data["09h30"]["price"] > range_high:
        sweep_direction = "SWEEP_HIGH"
        bias = "BEARISH"  # Après sweep du high = distribution baissière
    elif session_data["09h30"]["price"] < range_low:
        sweep_direction = "SWEEP_LOW"
        bias = "BULLISH"  # Après sweep du low = distribution haussière
    else:
        return {"status": "NO_VENOM", "reason": "PAS_DE_SWEEP_09h30"}

    # Étape 3 : Entrée sur premier FVG post-sweep
    return {
        "status": "VENOM_ACTIVE",
        "bias": bias,
        "entry": "CE_PREMIER_FVG_POST_SWEEP",
        "target": "COTE_OPPOSE_90MIN_RANGE",
        "target_extension": "STD_DEV_MINUS_2",
        "profit_typical": "50-80 ticks NQ"
    }
```

### 2.3 VIX — Règles de Sizing Indices

| VIX | Régime | Position Sizing | Remarque |
|-----|--------|----------------|----------|
| < 15 | Calme | 100% | Trading normal |
| 15-20 | Normal | 80% | Attention aux retournements |
| 20-25 | Élevé | 50% | Journées erratiques possibles |
| 25-30 | Très élevé | 30% | Réduire drastiquement |
| > 30 | Crise | 0-20% | Scalp uniquement ou NO-TRADE |

```python
def get_sizing_vix(vix_value):
    if vix_value < 15:    return 1.00
    elif vix_value < 20:  return 0.80
    elif vix_value < 25:  return 0.50
    elif vix_value < 30:  return 0.30
    else:                 return 0.15
```

### 2.4 NWOG — New Week Opening Gap Indices
**[SPÉCIFIQUE : W/D1 — INDICES US]**

```python
# Calcul chaque lundi à l'ouverture
NWOG_High = max(Friday_close, Monday_open)
NWOG_Low  = min(Friday_close, Monday_open)
NWOG_Size = abs(Monday_open - Friday_close)  # en ticks

if NWOG_Size > 20:  # ticks NQ
    # Gap significatif → Zone institutionnelle à combler
    # 78% des NWOG sont comblés dans les 3 premiers jours
    nwog_target = Friday_close  # Retour vers le close vendredi
    nwog_priority = "HIGH"
```

### 2.5 Corrélations Indices

| Signal | Corrélé | Lecture |
|--------|---------|---------|
| NQ bearish | YM bearish | Confirmation large marché → Valide |
| NQ bearish | YM haussier | Divergence sectorielle → Réduire 50% |
| ES haussier | RTY baissier | Risk appetite faible → Prudence |
| NQ haussier + VIX < 15 | — | Régime favorable → 100% sizing |
| Tous indices baissiers + VIX > 25 | — | Panique → NO-TRADE ou Scalp court |

### 2.6 Macro Spécifique Indices — 09h30 Opening Range

```
Règle Opening Range Indices :
- 09h30-10h00 EST = Première bougie M30 = Direction probable de la journée
- Si Close M30 > Open M30 + ATR×0.3 → Biais BULLISH journée
- Si Close M30 < Open M30 - ATR×0.3 → Biais BEARISH journée
- First Presented FVG M1 (09h30-10h00) → Biais scellé à 90%

Attention lundi :
- NE PAS TRADER avant 10h00 EST le lundi (gap filling erratique)
```

---

## SECTION 3 — BITCOIN (BTC/USD, BTC/USDT)

### 3.1 Spécificités Algorithmiques BTC

**[SPÉCIFIQUE : TOUS TF BTC — ADAPTATIONS MAJEURES]**

Bitcoin est un marché **24h/7j** avec des comportements distincts :
- Pas de sessions fixes → Utiliser les heures NY comme référence principale
- Liquidations massives = Version amplifiée du Judas Swing ICT
- Funding Rate = Indicateur de biais institutionnel crypto
- Open Interest = Mesure de l'engagement des participants

### 3.2 Funding Rate — Indicateur de Biais BTC

```python
def btc_bias_from_funding(funding_rate_8h):
    """
    Funding Rate positif = Longs dominants = Institution SHORT probable
    Funding Rate négatif = Shorts dominants = Institution LONG probable
    """
    if funding_rate_8h > 0.03:    # > 3% annualisé
        return "BEARISH_INSTITUTIONNEL", "REDUCE_LONGS_50PCT"
    elif funding_rate_8h > 0.01:
        return "LÉGÈREMENT_BEARISH", "NORMAL"
    elif funding_rate_8h < -0.01:
        return "BULLISH_INSTITUTIONNEL", "OPPORTUNITÉ_LONG"
    elif funding_rate_8h < -0.03:
        return "TRÈS_BULLISH", "PRIORITÉ_LONG_TOTALE"
    else:
        return "NEUTRE", "NORMAL"
```

### 3.3 Open Interest (OI) — Confirmation BTC

| OI | Prix | Signal |
|----|------|--------|
| OI ↑ | Prix ↑ | Trend haussier sain → Continuation probable |
| OI ↑ | Prix ↓ | Short squeeze probable → Trap baissier |
| OI ↓ | Prix ↑ | Short covering → Move moins fiable |
| OI ↓ | Prix ↓ | Long liquidation → Accélération baissière |
| OI spike × 2 | Tout | Event de liquidation massif → NE PAS ENTRER |

### 3.4 Adaptations ICT pour BTC

**Modèles qui FONCTIONNENT sur BTC :**
- Judas Swing (tous TF) ✅ — Amplitudes × 3-5 vs Forex
- MMXM (tous TF) ✅ — Cycles plus rapides (D1 = 1-3 jours vs 3-10j)
- FVG / OB (tous TF) ✅ — Très fiables, amplitudes larges
- MSS / BOS / CHoCH ✅ — Standard
- BSL/SSL / ERL/IRL ✅ — Standard

**Modèles NON APPLICABLES sur BTC :**
- CBDR ❌ — Pas de session centrale bancaire
- Silver Bullet ❌ — Pas de fenêtres institutionnelles fixes
- Weekly Templates ❌ — Structure hebdomadaire différente
- COT Reports ❌ — Pas de contrat CME retail standardisé utile
- Venom Model ❌ — Pas de 09h30 Opening Range institutionnel

**Adaptations des amplitudes BTC :**

| TF | Amplitude FVG typique BTC | Amplitude OB typique |
|----|--------------------------|---------------------|
| W | 2000-10000 USD | 1000-5000 USD |
| D1 | 500-3000 USD | 300-1500 USD |
| H4 | 200-1000 USD | 100-500 USD |
| H1 | 50-300 USD | 30-150 USD |
| M15 | 20-100 USD | 10-50 USD |

### 3.5 Asian Range BTC — Accumulation Nocturne
**[SPÉCIFIQUE : H1/H4 — BTC]**

```python
# Asian Range BTC : 20h00-00h00 EST
asian_high = max(prix entre 20h00 et 00h00 EST)
asian_low  = min(prix entre 20h00 et 00h00 EST)
asian_range = asian_high - asian_low

if asian_range < 500:  # USD
    # Range serré = Accumulation → Breakout probable à NY Open
    asian_explosive = True
    # → Attendre sweep du high ou low asiatique à 08h00-10h00 EST
    # → Entrée après sweep = Judas Swing BTC

if asian_range > 2000:
    # Range large = Marché déjà en mouvement → Prudence
    asian_explosive = False
```

### 3.6 Règles de Sizing BTC

| Volatilité BTC (ATR D1) | Position Sizing |
|------------------------|----------------|
| ATR D1 < 1000 USD | 100% |
| ATR D1 1000-2000 USD | 70% |
| ATR D1 2000-4000 USD | 50% |
| ATR D1 > 4000 USD | 30% |
| Liquidation cascade détectée | 0% — NO-TRADE |

---

## SECTION 4 — OR (XAU/USD)

### 4.1 Spécificités Algorithmiques Or

**[SPÉCIFIQUE : TOUS TF OR — ADAPTATIONS MODÉRÉES]**

L'Or partage de nombreuses caractéristiques avec le Forex mais a ses propres règles :
- Très sensible aux décisions des banques centrales (Fed, BCE)
- London Fix (10h30 EST et 15h00 EST) = Moments de manipulation fréquents
- Corrélation inverse forte avec USD (-0.80) et yields 10Y (-0.70)
- Safe Haven = Comportement anti-corrélé en période de crise (Risk-off)

### 4.2 London Fix — Piège Critique Or
**[SPÉCIFIQUE : M5/M15 — XAU/USD]**

```
London AM Fix : 10h30 EST
London PM Fix : 15h00 EST

Comportement typique :
- 10-30 min AVANT le Fix → Manipulation (Judas Swing M5)
- Au moment du Fix → Volume spike + retournement brutal
- 30 min APRÈS le Fix → Vrai mouvement directionnel

Règle Bot :
IF time IN [10h15-10h45 EST] OR [14h45-15h15 EST]:
    sizing = 30%  # Réduire drastiquement
    entry_type = "LIMIT_ONLY"  # Pas de market orders
    wait_for_post_fix_mss = True  # Attendre MSS après le fix
```

### 4.3 COT Or
**[SPÉCIFIQUE : MN/W — XAU/USD]**

- Contrat : Gold Futures COMEX (GC)
- Non-Commercial Longs nets ↑ = Or haussier la semaine suivante (fiabilité 68%)
- Commercials (producteurs d'or) = Short naturellement → À ne PAS suivre
- Non-Commercial Net Position > +200 000 = Extrême haussier → Prudence (reversal possible)

### 4.4 Adaptations ICT pour l'Or

**Modèles qui FONCTIONNENT sur l'Or :**
- Weekly Templates ✅ — Applicables (similaire Forex)
- Silver Bullet ✅ — Applicables (FOREX/GOLD mentionné dans encyclopédie)
- CBDR ✅ — Applicable (similaire Forex)
- Judas Swing ✅ — Très fiable sur Or
- COT ✅ — Applicable (contrat COMEX)
- SMT avec DXY ✅ — Corrélation inverse forte

**Adaptations des amplitudes Or :**

| TF | Amplitude FVG typique | Amplitude OB typique | Smooth tolerance |
|----|----------------------|---------------------|------------------|
| W | 30-100 USD | 20-60 USD | ±3 USD |
| D1 | 8-30 USD | 5-20 USD | ±1 USD |
| H4 | 3-12 USD | 2-8 USD | ±0.5 USD |
| H1 | 1-5 USD | 0.8-3 USD | ±0.3 USD |

### 4.5 Or Safe Haven — Règle de Crise

```python
def gold_safe_haven_regime(vix, dxy_direction, spx_direction):
    """
    En période de crise, l'Or se découple de ses corrélations normales
    """
    if vix > 30 and spx_direction == "BEARISH":
        # Risk-off total → Or monte même si DXY monte
        return "SAFE_HAVEN_ACTIVE", "TOUTES_CORRELATIONS_SUSPENDUES"

    if vix > 25 and dxy_direction == "BULLISH" and spx_direction == "BEARISH":
        # Confusion liquidité → Or volatile, imprévisible
        return "VOLATILITE_EXTREME", "REDUCE_50PCT_OR_PASS"

    return "NORMAL_REGIME", "CORRELATIONS_STANDARD"
```

---

## SECTION 5 — PÉTROLE (WTI/BRENT — CL/BRN)

### 5.1 Spécificités Algorithmiques Pétrole

**[SPÉCIFIQUE : TOUS TF PÉTROLE — ADAPTATIONS MAJEURES]**

Le pétrole est un marché **fortement fondamental** avec des triggers géopolitiques :
- Rapport EIA (inventaires pétrole) : Mercredi 10h30 EST → Impact fort
- OPEC+ décisions : Trimestrielles → Impact majeur sur tendance MN/W
- Futures CL (WTI) = Référence principale
- Contango/Backwardation = Structure de terme importante

### 5.2 Événements Clés Pétrole

| Événement | Fréquence | Timing EST | Impact | Règle Bot |
|-----------|-----------|-----------|--------|-----------|
| **EIA Crude Inventories** | Hebdomadaire | Mercredi 10h30 | 8/10 | Gel 15 min avant + après |
| **API Report** | Hebdomadaire | Mardi 16h30 | 6/10 | Réduire taille 50% |
| **OPEC+ Meeting** | Trimestriel | Variable | 10/10 | NO-TRADE journée OPEC |
| **NFP** | Mensuel | Vendredi 08h30 | 6/10 | Impact indirect via DXY |
| **FOMC** | 6x/an | Mercredi 14h00 | 7/10 | Impact via DXY/inflation |

### 5.3 Adaptations ICT pour le Pétrole

**Modèles qui FONCTIONNENT sur le Pétrole :**
- Judas Swing (D1/H4) ✅ — Fiable
- MMXM (D1/W) ✅ — Cycles géopolitiques
- FVG / OB (D1/H4/H1) ✅ — Standard
- BSL/SSL ✅ — Standard

**Modèles NON APPLICABLES ou DÉGRADÉS sur le Pétrole :**
- Silver Bullet ❌ — Fenêtres institutionnelles moins pertinentes
- CBDR ❌ — Pas de banque centrale directement
- Weekly Templates ❌ — Structure trop influencée par fondamentaux
- COT ✅ mais différent — Commercials = Producteurs/Raffineurs (hedgers naturels)

**Corrélations Pétrole :**

| Asset | Corrélation | Règle Bot |
|-------|-------------|-----------|
| USD/CAD | Inverse forte (-0.75) | Oil ↑ = USD/CAD ↓ — Attention |
| AUD/USD | Positive (+0.65) | Oil ↑ = Risk-on = AUD potentiel |
| SPX | Positive (+0.50) | Oil baisse + SPX baisse = Risk-off total |
| Inflation | Positive | Oil ↑ soutenu = Fed hawkish = USD ↑ |

### 5.4 Amplitudes Pétrole par TF

| TF | Amplitude FVG typique | Amplitude OB typique | Buffer SL |
|----|----------------------|---------------------|-----------|
| W | 3-10 USD | 2-6 USD | ±0.5 USD |
| D1 | 1-4 USD | 0.8-2.5 USD | ±0.3 USD |
| H4 | 0.4-1.5 USD | 0.3-1 USD | ±0.15 USD |
| H1 | 0.15-0.6 USD | 0.1-0.4 USD | ±0.08 USD |

---

## SECTION 6 — MATRICE DE SYNTHÈSE PAR INSTRUMENT

### 6.1 Applicabilité des Modèles ICT par Instrument

| Modèle ICT | EUR/USD | Indices | BTC | Or | Pétrole |
|------------|---------|---------|-----|----|---------|
| Judas Swing | ✅ | ✅ | ✅ | ✅ | ✅ |
| MMXM | ✅ | ✅ | ✅ | ✅ | ✅ |
| Grail Setup | ✅ | ✅ | ⚠️ adapté | ✅ | ⚠️ adapté |
| Silver Bullet | ✅ | ❌ | ❌ | ✅ | ❌ |
| Venom | ❌ | ✅ NQ/ES/YM | ❌ | ❌ | ❌ |
| CBDR | ✅ | ❌ | ❌ | ✅ | ❌ |
| Weekly Templates | ✅ | ❌ | ❌ | ✅ | ❌ |
| COT | ✅ | ❌ | ❌ | ✅ | ⚠️ différent |
| Asian Range | ⚠️ | ⚠️ | ✅ | ⚠️ | ❌ |
| NWOG | ⚠️ | ✅ | ⚠️ | ⚠️ | ⚠️ |
| FVG / OB | ✅ | ✅ | ✅ | ✅ | ✅ |
| BSL / SSL | ✅ | ✅ | ✅ | ✅ | ✅ |
| SMT Divergence | ✅ | ✅ | ⚠️ | ✅ | ⚠️ |

### 6.2 Indicateurs Spécifiques par Instrument

| Indicateur | EUR/USD | Indices | BTC | Or | Pétrole |
|-----------|---------|---------|-----|----|---------|
| DXY | ✅ Inverse | ⚠️ Indirect | ⚠️ Faible | ✅ Inverse | ⚠️ Indirect |
| VIX | ⚠️ | ✅ Direct | ✅ | ✅ | ✅ |
| COT CFTC | ✅ | ❌ | ❌ | ✅ | ✅ différent |
| Funding Rate | ❌ | ❌ | ✅ Direct | ❌ | ❌ |
| Open Interest | ❌ | ✅ | ✅ Direct | ⚠️ | ✅ |
| 10Y Yields | ✅ Inverse | ✅ | ⚠️ | ✅ Inverse | ⚠️ |
| Copper | ⚠️ | ⚠️ | ❌ | ⚠️ | ❌ |
| EIA Report | ❌ | ❌ | ❌ | ❌ | ✅ Direct |
| OPEC+ | ❌ | ❌ | ❌ | ❌ | ✅ Direct |
| London Fix | ❌ | ❌ | ❌ | ✅ Direct | ❌ |

### 6.3 Sizing Recommandé par Instrument et Régime

```python
def get_instrument_sizing(instrument, regime):
    base_sizing = {
        "FOREX":    {"CALME": 1.0, "NORMAL": 0.8, "VOLATILE": 0.5, "CRISE": 0.2},
        "INDICES":  {"CALME": 1.0, "NORMAL": 0.8, "VOLATILE": 0.4, "CRISE": 0.1},
        "BTC":      {"CALME": 0.8, "NORMAL": 0.6, "VOLATILE": 0.3, "CRISE": 0.0},
        "OR":       {"CALME": 1.0, "NORMAL": 0.8, "VOLATILE": 0.5, "CRISE": 0.3},
        "PETROLE":  {"CALME": 0.8, "NORMAL": 0.6, "VOLATILE": 0.3, "CRISE": 0.0},
    }
    return base_sizing.get(instrument, {}).get(regime, 0.5)
```

---

## SECTION 7 — RÈGLES D'EXCLUSION PAR INSTRUMENT

### 7.1 Exclusions Absolues Communes (Tous Instruments)

1. **News impact 8+/10 dans les 30 minutes** → Score -50 pts automatique
2. **SOD = MANIPULATION** → FREEZE total
3. **Boolean_Sweep_ERL = False** → Aucun signal valide
4. **Score global < 65** → No-trade obligatoire

### 7.2 Exclusions Spécifiques

```
FOREX :
- Spread > 3 pips → No-trade (coût trop élevé)
- CBDR > 200 pips → Range déjà trop large, prudence
- Lundi avant 08h00 EST → Liquidité insuffisante

INDICES :
- VIX > 35 → No-trade (volatilité incontrôlable)
- Lundi avant 10h00 EST → Gaps erratiques
- Mardi après-midi si EIA (ETFs liés) → Prudence
- Après FOMC les 2 premières heures → Attendre stabilisation

BTC :
- Liquidation cascade (OI chute > 20% en 1h) → No-trade 2h
- Funding Rate > 0.05% → Réduire longs à 20%
- Week-end dimanche 20h00-23h00 EST → Liquidité faible

OR :
- London Fix ±15 min → Réduire à 30%
- FOMC jour J → Extrême volatilité, 30% max
- NFP jour J → Reduce 30%
- Crise géopolitique active (VIX > 30 + headlines) → Safe Haven rules

PÉTROLE :
- EIA Report ±15 min → No-trade
- OPEC+ jour J → No-trade total
- Contango extrême (front month > 10% discount vs spot) → Prudence structure
```

---

## RÉFÉRENCES INTER-FICHIERS KB5

| Concept | Fichier source | Usage |
|---------|---------------|-------|
| Définitions ICT complètes | `03_ICT_ENCYCLOPEDIE_v5.md` | FVG, OB, MSS, MMXM... |
| Synergies PA/ICT | `04_PRICE_ACTION_BIBLE_v4.md` | Confluence PA sur zones |
| Matrice Fractal/Spécifique | `01_CADRE_FRACTAL_SPECIFIQUE.md` | Tags par TF |
| Scoring + décision finale | `07_MOTEUR_DECISION.md` | Verdict avec overrides instrument |
| Format dossier paire | `06_DOSSIER_PAIRE_SCHEMA.md` | Output structuré |

---

*Instruments Spécifiques v1.0 — KB5 Sentinel Pro — 2026-03-11*
*Source : Extensions KB5 — Huddleston 2016-2026 + Spécificités marchés*
*Forex / Indices US / BTC / Or / Pétrole — Adaptations ICT/PA par classe d'actif*
