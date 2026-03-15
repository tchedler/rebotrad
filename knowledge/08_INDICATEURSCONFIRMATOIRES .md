---
version: 1.0
fichier: 08_INDICATEURSCONFIRMATOIRES.md
projet: Sentinel Pro KB5
date: 2026-03-11
auteur: Département Étude & Analyse
statut: Production-ready
licence: CC BY-NC-SA 4.0
sources: file:55 (KB5), file:58 (LuxAlgo SMC), file:59 (LuxAlgo ICT)
---

# 08 — INDICATEURS CONFIRMATOIRES
## Sentinel Pro KB5 v1.0

---

## ⚠️ PHILOSOPHIE FONDAMENTALE KB5

> **ICT/Price Action = Signal. Indicateurs = Confirmation/Filtre.**
> Un indicateur ne crée JAMAIS une zone. Il confirme une zone ICT déjà identifiée.
> Tout signal autonome d'indicateur = ignoré. Violation = NO-TRADE automatique.

**Règle d'or** :
```
IF indicateur.signal AND NOT ict_zone_identifiée:
    return NO_TRADE  # Signal orphelin interdit
IF ict_zone_identifiée AND indicateur.confirms:
    score += bonus_pts
```

---

## CATÉGORIE A — NATIFS OBLIGATOIRES (toujours actifs, tous TF)

Ces 3 indicateurs sont déjà intégrés dans `04_PRICEACTIONBIBLE_v4.md` et `05_INSTRUMENTS_SPECIFIQUES.md`.
Ils sont **actifs en permanence**, sans condition.

---

### A1 — EMA 20 (Exponential Moving Average)

| Paramètre | Valeur |
|-----------|--------|
| Période | 20 |
| Type | Exponentielle |
| TF applicables | Tous (MN → M1) |
| Bonus scoring | Natif (pas de bonus séparé) |

**Rôles précis dans KB5 :**

| Signal EMA | Contexte ICT | Interprétation | Action Bot |
|------------|-------------|----------------|------------|
| Prix > EMA 20 | SOD DISTRIBUTION | Biais haussier confirmé | Always In Long (AIL) |
| Prix < EMA 20 | SOD DISTRIBUTION | Biais baissier confirmé | Always In Short (AIS) |
| EMA 20 horizontale | SOD ACCUMULATION | Range, pas de tendance | NO TRADE |
| Gap Bar (Low > EMA) | Killzone active | Tendance forte institutionnelle | Réduire partiels |
| Pullback jusqu'à EMA | Canal haussier | Retest OTE potentiel | Chercher FVG/OB dans zone |
| Prix casse EMA + volume | CHoCH suspect | Possible MSS | Surveiller confirmation |

**Règles absolues :**
- EMA 50, EMA 100, EMA 200 = **INTERDITES** dans KB5. Redondant, lagging.
- Ne JAMAIS shorter une série de Gap Bars (Low > EMA 20).
- 3 Gap Bars consécutives = tendance parabolique → préparer sortie partielle.

---

### A2 — ATR 14 (Average True Range)

| Paramètre | Valeur |
|-----------|--------|
| Période | 14 |
| TF applicables | Tous |
| Bonus scoring | Natif (filtre qualité) |

**Usages précis par contexte :**

| Usage | Règle | Seuil |
|-------|-------|-------|
| Filtre Trend Bar | Corps bougie > 0.6 × ATR14 | Trend Bar valide |
| Filtre Trend Bar LOOSE (H1/M15) | Corps > 0.5 × ATR14 | Acceptable |
| Détection Climax | Bougie > 2 × ATR14 | Début MTR possible |
| SL Sizing | SL = 1.5 × ATR14 min | Évite stops trop serrés |
| CBDR Régime | CBDR > ATR14 × 0.8 | Journée explosive |
| Displacement valide | Amplitude > ATR min TF | Voir tableau ci-dessous |

**Amplitudes minimales par TF (ATR-calibré) :**

| TF | Amplitude min | Amplitude max |
|----|--------------|--------------|
| MN | 200 pips | 2000 pips |
| W | 50 pips | 500 pips |
| D1 | 20 pips | 100 pips |
| H4 | 10 pips | 50 pips |
| H1 | 5 pips | 25 pips |
| M15 | 3 pips | 15 pips |
| M5 | 2 pips | 10 pips |
| M1 | 1 pip | 5 pips |

---

### A3 — Volume brut

| Paramètre | Valeur |
|-----------|--------|
| Type | Volume brut (tick volume Forex, réel Indices/BTC) |
| TF applicables | Tous |
| Bonus scoring | +8 pts si volume > 2× sur MSS (moteur décision) |

**Usages précis :**

| Signal Volume | Contexte ICT | Interprétation | Bonus |
|--------------|-------------|----------------|-------|
| Volume > 1.5× moyenne sur breakout | MSS sortie range | Vrai breakout institutionnel | +8 pts score |
| Volume décroissant sur pullback | Canal haussier/baissier | Pullback sain → entrer OB/FVG | Valide entrée |
| Volume spike sur EQH/EQL | BSL/SSL zone | ERL purgé → BooleanSweepERL = True | Confirme sweep |
| Volume > 1.5× sur bougie inverse | Dans un OB | OB en danger → freshness réduite | Alerte |
| Volume croissant sur pullback | Retracement | Pullback invalide → probable inversion | NO TRADE |

**Avertissement Forex :** Volume = tick volume (proxy), pas volume réel. Indices/BTC = volume réel fiable.

---

## CATÉGORIE B — CONFIRMATEURS GÉNÉRAUX (bonus scoring)

Ces indicateurs sont **optionnels** mais fortement recommandés. Ils ne génèrent pas de signal d'entrée autonome.

---

### B4 — LuxAlgo Smart Money Concepts (SMC) Historical

| Paramètre | Valeur |
|-----------|--------|
| Source | TradingView (code Pine v5 fourni — `file:58`, 51k chars) |
| Licence | CC BY-NC-SA 4.0 LuxAlgo |
| Paramètres KB5 | Historical, Colored, All/All, Tiny, All/All, Small, 50, 5, 5, Atr, HighLow, 3, 0.1, Tiny, 1 |
| TF recommandés | H4, H1, M15 |
| Bonus scoring | 5 à 15 pts selon confluence |

**Fonctionnalités détectées et rôle KB5 :**

| Fonctionnalité LuxAlgo SMC | Correspondance KB5 | Bonus |
|---------------------------|-------------------|-------|
| Internal BOS/CHoCH | MSS interne (H1/M15) | +5 pts si align KB5 |
| Swing BOS/CHoCH | MSS swing (H4/D1) | +10 pts si align KB5 |
| Internal Order Blocks (IOB) | OB interne KB5 | +10 pts si align PD Array |
| Swing Order Blocks (OB) | OB swing KB5 | +15 pts si align PD Array |
| Equal Highs/Lows (EQH/EQL) | BSL/SSL KB5 | Confirme BooleanSweepERL |
| Fair Value Gaps (FVG) | FVG KB5 | +5 pts si align zone ICT |
| Premium/Discount Zones | Zone P/D KB5 | Confirme OTE |
| MTF Levels (Daily/Weekly) | PDH/PDL/PWH/PWL | Confirme niveaux HTF |
| Strong/Weak High-Low | Trailing Swing KB5 | Contexte directionnel |

**Règles d'intégration :**
```python
def lux_smc_bonus(kb5_pd_array, smc_detection):
    score = 0
    if smc_detection['swing_ob'] and kb5_pd_array['ob_align']:
        score += 15  # OB Swing LuxAlgo + OB KB5 alignés
    if smc_detection['internal_bos'] and kb5_pd_array['mss_confirmed']:
        score += 10  # MSS double confirmation
    if smc_detection['fvg'] and kb5_pd_array['fvg_fresh']:
        score += 5   # FVG double confirmation
    if smc_detection['eqh_eql'] and kb5_boolean_sweep_erl:
        score += 5   # EQL/EQH confirme ERL purge
    return min(score, 15)  # Cap 15 pts max
```

**Veto LuxAlgo SMC :**
```
IF lux_smc.mss_direction != kb5.mss_direction:
    score -= 20  # Divergence MSS = signal dangereux
```

---

### B5 — LuxAlgo ICT Concepts

| Paramètre | Valeur |
|-----------|--------|
| Source | TradingView (code Pine v5 fourni — `file:59`, 52k chars) |
| Licence | CC BY-NC-SA 4.0 LuxAlgo |
| Paramètres KB5 | Present, 5, 2, 10, 5, 5, 4, 2, IFVG, 2, 3, 1, Liq, 0800-1100, 0800-1100, 1600-1700, 1000-1400 |
| TF recommandés | H1, M15, M5 |
| Bonus scoring | 10 pts |

**Fonctionnalités détectées et rôle KB5 :**

| Fonctionnalité LuxAlgo ICT | Correspondance KB5 | Bonus |
|---------------------------|-------------------|-------|
| Market Structure Shift (MSS) | MSS KB5 Section 2 | +10 pts si align |
| BOS (Break of Structure) | BOS KB5 | Confirme structure |
| Order Blocks Bull/Bear | OB KB5 Section 3.3 | +10 pts si align |
| Fair Value Gaps (FVG) | FVG KB5 Section 3.2 | +5 pts si align |
| Inverted FVG (IFVG) | IFVG KB5 | Identifie zones inversées |
| Balance Price Range (BPR) | BPR KB5 Section 3.5 | +5 pts si align |
| Buyside Liquidity (BSL) | BSL KB5 Section 6.1 | Confirme cibles |
| Sellside Liquidity (SSL) | SSL KB5 Section 6.1 | Confirme cibles |
| Volume Imbalance (VI) | VI KB5 Section 4.5 | Suspension Block check |
| NWOG (New Week Opening Gap) | NWOG KB5 | +10 pts Indices |
| NDOG (New Day Opening Gap) | NDOG KB5 | Niveau combler |
| Killzones NY/London/Asian | Killzones KB5 Section 4.1 | Timing confirmation |
| Displacement | Displacement KB5 | Confirme qualité MSS |
| Fibonacci | OTE KB5 Section 4.10 | 61.8-79% zone entry |

**Règles d'intégration :**
```python
def lux_ict_bonus(kb5_state, ict_detection, current_time_est):
    score = 0
    # Killzone timing
    active_kz = ['NY_AM', 'London', 'London_Close', 'Asian']
    if ict_detection['killzone_active'] in active_kz:
        score += 10
    # NWOG Indices
    if ict_detection['nwog_level'] and kb5_state['instrument'] in ['NQ','ES','YM']:
        score += 10
    # MSS alignment
    if ict_detection['mss'] == kb5_state['mss_direction']:
        score += 10
    # Liquidity confirmation
    if ict_detection['bsl_swept'] and kb5_state['boolean_sweep_erl']:
        score += 5
    return min(score, 10)  # Cap 10 pts
```

---

### B6 — VWAP (Volume Weighted Average Price)

| Paramètre | Valeur |
|-----------|--------|
| Source | Natif TradingView / MT5 |
| Type | Anchored Daily VWAP recommandé |
| TF applicables | Tous (surtout H1, M15, M5) |
| Bonus scoring | 10 pts |

**Usages précis :**

| Signal VWAP | Contexte ICT | Action |
|-------------|-------------|--------|
| Prix > VWAP | SOD DISTRIBUTION bull | Biais haussier confirmé +10 pts |
| Prix < VWAP | SOD DISTRIBUTION bear | Biais baissier confirmé +10 pts |
| OB au-dessus VWAP (bull) | FVG + VWAP align | Confluence maximale A |
| Rejet VWAP = résistance | MSS baissier | Confirme distribution |
| Prix croise VWAP + volume | Possible MSS | Surveiller FVG post-croisement |
| VWAP = niveau .50 MM | Terminus PA | EXIT 100% position |
| Anti-inducement | Prix casse VWAP et revient | Signal trap → ignorer |

```python
def vwap_bonus(close_price, vwap_level, kb5_bias):
    if kb5_bias == 'BULLISH' and close_price > vwap_level:
        return 10
    elif kb5_bias == 'BEARISH' and close_price < vwap_level:
        return 10
    return 0
```

---

### B7 — Volume Profile (POC / VAH / VAL / LVN)

| Paramètre | Valeur |
|-----------|--------|
| Source | Natif TradingView / MT5 |
| Type | Session Volume Profile recommandé |
| TF applicables | H4, H1 (contexte D1) |
| Bonus scoring | 15 pts |

**Niveaux clés et rôle KB5 :**

| Niveau | Nom complet | Rôle KB5 | Bonus |
|--------|-------------|----------|-------|
| POC | Point of Control | Si dans OB/FVG → liquidité institutionnelle confirmée | +15 pts |
| VAH | Value Area High | Résistance premium possible | Contexte |
| VAL | Value Area Low | Support discount possible | Contexte |
| LVN | Low Volume Node | Zone faible liquidité = FVG potentiel | Alerte |
| HVN | High Volume Node | Zone forte liquidité = OB/FVG institutionnel | +10 pts |

```python
def volume_profile_bonus(kb5_zone, poc_level, lvn_zones):
    if kb5_zone['low'] <= poc_level <= kb5_zone['high']:
        return 15  # POC dans zone ICT = confluence maximale
    for lvn in lvn_zones:
        if kb5_zone['low'] <= lvn <= kb5_zone['high']:
            return 10  # LVN = FVG potentiel
    return 0
```

---

### B8 — RSI (Relative Strength Index) — Divergences uniquement

| Paramètre | Valeur |
|-----------|--------|
| Période | 14 |
| TF applicables | H1, M15 uniquement |
| Bonus scoring | 5 pts (divergences sur zone ICT seulement) |

**⚠️ USAGE STRICTEMENT LIMITÉ :**

| Signal RSI | Conditions KB5 | Valide ? | Bonus |
|-----------|---------------|---------|-------|
| Divergence Bearish : prix HH + RSI LH | Sur résistance ICT (OB/FVG/BSL) | ✅ OUI | +5 pts |
| Divergence Bullish : prix LL + RSI HL | Sur support ICT (OB/FVG/SSL) | ✅ OUI | +5 pts |
| RSI < 30 (survendu) seul | N'importe où | ❌ NON | 0 pt |
| RSI > 70 (suracheté) seul | N'importe où | ❌ NON | 0 pt |
| RSI crossover 50 | N'importe où | ❌ INTERDIT | 0 pt |
| RSI signal d'entrée autonome | Sans zone ICT | ❌ INTERDIT | -10 pts |

```python
def rsi_divergence_bonus(price_highs, rsi_highs, price_lows, rsi_lows, in_ict_zone):
    if not in_ict_zone:
        return 0  # Hors zone ICT = 0 valeur
    # Divergence bearish
    if price_highs[-1] > price_highs[-2] and rsi_highs[-1] < rsi_highs[-2]:
        return 5
    # Divergence bullish
    if price_lows[-1] < price_lows[-2] and rsi_lows[-1] > rsi_lows[-2]:
        return 5
    return 0
```

---

## CATÉGORIE C — SPÉCIFIQUES PAR INSTRUMENT (sizing / filtre macro)

---

### C9 — VIX (Volatility Index) — Indices US uniquement

| Instrument | NQ, ES, YM, RTY |
|------------|----------------|
| Source | Natif (symbole VIX) |
| TF | D1 |
| Rôle | Sizing dynamique |

**Règles de sizing VIX :**

| VIX Niveau | Interprétation | Position Size |
|-----------|----------------|--------------|
| < 15 | Marché calme | 100% size normal |
| 15 – 25 | Volatilité normale | 100% |
| 25 – 35 | Volatilité élevée | 50% |
| > 35 | Volatilité extrême | **0% — INTERDIT** |
| > 50 | Crise systémique | **ARRÊT TOTAL bot** |

```python
def vix_sizing(vix_level):
    if vix_level > 35: return 0.0   # Interdit
    if vix_level > 25: return 0.5   # Réduit
    return 1.0                       # Normal
```

---

### C10 — Funding Rate — BTC uniquement

| Instrument | BTCUSD, BTCUSDT |
|------------|----------------|
| Source | Binance / Bybit / Coinglass |
| TF | H4 (actualisé toutes les 8h) |
| Rôle | Biais institutionnel crypto |

| Funding Rate | Interprétation | Biais KB5 |
|-------------|----------------|----------|
| > +0.1% | Longs surchargés | Short bias → purge probable |
| +0.01% à +0.1% | Marché neutre/légèrement bull | Neutre |
| -0.01% à -0.1% | Shorts surchargés | Long bias → squeeze probable |
| < -0.1% | Shorts extrêmes | Long fort → purge shorts imminente |

---

### C11 — Open Interest (OI) — BTC et Pétrole

| Instrument | BTCUSD, CL (Pétrole) |
|------------|---------------------|
| Source | Coinglass (BTC) / CME (Pétrole) |
| TF | H1 |
| Rôle | Confirmation direction + liquidation cascade |

| Signal OI | Prix | Interprétation KB5 |
|-----------|------|-------------------|
| OI ↑ + Prix ↑ | Hausse | New longs entrent → tendance haussière forte |
| OI ↑ + Prix ↓ | Baisse | New shorts entrent → tendance baissière forte |
| OI ↓ + Prix ↑ | Hausse | Shorts couvrent → squeeze, méfiance |
| OI ↓ + Prix ↓ | Baisse | Longs liquident → faiblesse, méfiance |
| OI spike > 20% | Tout | Liquidation cascade possible → réduire size 50% |

---

### C12 — COT Report (Commitment of Traders) — Forex, Or, Pétrole

| Instrument | EUR, GBP, JPY, XAU, CL |
|------------|------------------------|
| Source | CFTC (publié vendredi 15h30 EST) |
| TF | MN, W uniquement |
| Rôle | Biais macro institutionnel |

| Positions Net Non-Commercial | Seuil KB5 | Biais Macro |
|-----------------------------|-----------|-------------|
| Long nets > +50,000 | BULLISH macro confirmé | Biais haussier semaine suivante |
| Long nets entre -50k et +50k | NEUTRE | Prudence, pas de biais clair |
| Short nets < -50,000 | BEARISH macro confirmé | Biais baissier semaine suivante |
| Commercial vs Non-Commercial diverge | SMT macro | Signal retournement potentiel |

**Paires surveillées :**
- EURUSD → Positions EUR futures CME
- GBPUSD → Positions GBP futures CME
- USDJPY → Inverser positions JPY
- XAUUSD → Positions Gold futures COMEX

**Bonus scoring :** COT aligné avec KB5 bias = **+20 pts** (via `05_INTERMARKET` et scoring 9.2)

---

### C13 — DXY (Dollar Index) — Forex et Or

| Instrument | EURUSD, GBPUSD, AUDUSD, XAUUSD |
|------------|-------------------------------|
| Source | Natif TradingView (symbole DXY) |
| TF | H4, D1 |
| Rôle | Filtre biais global corrélatif |

| Signal DXY | Corrélation | Action KB5 |
|-----------|-------------|-----------|
| DXY haussier + EURUSD signal long | Conflit -0.85 | Réduire size 60% ou PASS |
| DXY baissier + EURUSD signal long | Aligné | Confirme signal +10 pts |
| DXY haussier + XAUUSD signal short | Aligné | Confirme signal +10 pts |
| DXY divergent 3 jours | SMT Divergence | Signal retournement macro |

---

## TABLEAU DE SCORING GLOBAL — INDICATEURS

| # | Indicateur | Cat | Bonus max | Condition activation | Veto possible |
|---|------------|-----|-----------|---------------------|---------------|
| A1 | EMA 20 | A | Natif | Toujours actif | Non |
| A2 | ATR 14 | A | Natif | Toujours actif | Non |
| A3 | Volume | A | +8 pts | MSS > 2× volume | Non |
| B4 | LuxAlgo SMC | B | +15 pts | OB/FVG align KB5 | Oui (-20 si divergence MSS) |
| B5 | LuxAlgo ICT | B | +10 pts | Killzone + Liq align | Non |
| B6 | VWAP | B | +10 pts | Bias confirmé | Non |
| B7 | Volume Profile | B | +15 pts | POC dans zone ICT | Non |
| B8 | RSI | B | +5 pts | Divergence sur zone ICT | Oui (si signal autonome -10 pts) |
| C9 | VIX | C | Sizing | Indices uniquement | Oui (>35 = 0%) |
| C10 | Funding Rate | C | Sizing | BTC uniquement | Oui (extrême = réduire) |
| C11 | Open Interest | C | Sizing | BTC/Pétrole | Oui (spike OI = -50% size) |
| C12 | COT | C | +20 pts | Forex/Or/Pétrole MN/W | Non |
| C13 | DXY | C | +10 pts | Forex/Or H4 aligné | Oui (divergent = -15 pts) |

**Total bonus maximum : 93 pts**
**Score base ICT/PA : 100 pts**
**Décision :**
- ≥ 80 pts → EXECUTE A (full size)
- 65–79 pts → SNIPER (50% size, confirmation H2L2)
- < 65 pts → NO TRADE

---

## INDICATEURS REJETÉS — INTERDITS KB5

| Indicateur | Raison du rejet | Alternative KB5 |
|------------|----------------|-----------------|
| EMA 50 / EMA 100 / EMA 200 | Redondant EMA 20. Lagging. | EMA 20 seule |
| MACD | Lagging, bruit sur zones ICT | Volume + ATR |
| Stochastique | Faux signaux sur supports ICT | LuxAlgo EQH/EQL |
| Bandes de Bollinger | Inutile en displacement | Volume Profile VAH/VAL |
| RSI < 30 / > 70 (seul) | Suracheté/survendu retail trap | RSI divergences only |
| RSI crossover 50 | Jamais signal d'entrée | MSS + BOS KB5 |
| Ichimoku | Complexe, redondant OB/FVG | LuxAlgo ICT Concepts |
| Parabolic SAR | Lagging en zones ICT | Trailing stop ATR |
| ADX | Redondant ATR + SOD | ATR 14 |
| CCI | Faux signaux SMC | Volume Profile |

---

## INTÉGRATION BOT — FONCTION PRINCIPALE

```python
def calculate_indicators_bonus(
    market_data, kb5_zone, kb5_state, instrument,
    lux_smc_data, lux_ict_data,
    vwap_level, poc_level, rsi_values,
    vix_level=None, funding_rate=None,
    open_interest=None, cot_data=None, dxy_data=None
):
    score = 0
    size_multiplier = 1.0

    # === CATÉGORIE A : Natifs ===
    # EMA 20 (filtre biais)
    ema20 = market_data['ema20']
    if kb5_state['bias'] == 'BULLISH' and market_data['close'] > ema20:
        score += 0  # Natif, pas de bonus séparé

    # ATR 14 (filtre Trend Bar)
    atr14 = market_data['atr14']
    body = abs(market_data['close'] - market_data['open'])
    if body < 0.5 * atr14:
        return 0, "TREND_BAR_INVALIDE"  # Filtre entrée

    # Volume
    if market_data['volume'] > 2.0 * market_data['avg_volume']:
        score += 8  # Displacement fort

    # === CATÉGORIE B : Confirmateurs ===
    # LuxAlgo SMC
    if lux_smc_data:
        if lux_smc_data.get('swing_ob_align') and kb5_zone.get('ob_valid'):
            score += 15
        elif lux_smc_data.get('internal_ob_align'):
            score += 10
        if lux_smc_data.get('fvg_align') and kb5_zone.get('fvg_fresh'):
            score += 5
        if lux_smc_data.get('mss_direction') != kb5_state.get('mss_direction'):
            score -= 20  # Veto divergence MSS

    # LuxAlgo ICT Concepts
    if lux_ict_data:
        if lux_ict_data.get('killzone_active') in ['NY_AM', 'London', 'London_Close', 'Asian']:
            score += 10
        if lux_ict_data.get('nwog') and instrument in ['NQ', 'ES', 'YM']:
            score += 10

    # VWAP
    if vwap_level:
        if kb5_state['bias'] == 'BULLISH' and market_data['close'] > vwap_level:
            score += 10
        elif kb5_state['bias'] == 'BEARISH' and market_data['close'] < vwap_level:
            score += 10

    # Volume Profile POC
    if poc_level:
        if kb5_zone['low'] <= poc_level <= kb5_zone['high']:
            score += 15

    # RSI Divergences (zone ICT seulement)
    if rsi_values and kb5_zone.get('in_zone'):
        if rsi_values[-1] < rsi_values[-2] and market_data['high'] > market_data['prev_high']:
            score += 5  # Bear div
        elif rsi_values[-1] > rsi_values[-2] and market_data['low'] < market_data['prev_low']:
            score += 5  # Bull div

    # === CATÉGORIE C : Instrument-spécifique ===
    # VIX (Indices)
    if vix_level and instrument in ['NQ', 'ES', 'YM', 'RTY']:
        if vix_level > 35:
            return 0, size_multiplier, "VIX_EXTREME_NO_TRADE"
        elif vix_level > 25:
            size_multiplier *= 0.5

    # Funding Rate (BTC)
    if funding_rate and 'BTC' in instrument:
        if abs(funding_rate) > 0.1:
            size_multiplier *= 0.5

    # COT (Forex/Or)
    if cot_data and instrument in ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']:
        if abs(cot_data['net_non_commercial']) > 50000:
            if (cot_data['net_non_commercial'] > 0 and kb5_state['bias'] == 'BULLISH') or                (cot_data['net_non_commercial'] < 0 and kb5_state['bias'] == 'BEARISH'):
                score += 20  # COT aligné

    # DXY (Forex/Or)
    if dxy_data and instrument in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD']:
        dxy_bias = dxy_data['bias']
        if (dxy_bias == 'BEARISH' and kb5_state['bias'] == 'BULLISH') or            (dxy_bias == 'BULLISH' and kb5_state['bias'] == 'BEARISH'):
            score += 10  # DXY aligné
        else:
            score -= 15  # DXY divergent

    return score, size_multiplier
```

---

## SOURCES CODES INDICATEURS LUXALGO

| Indicateur | Fichier source | Lignes | Statut |
|------------|---------------|--------|--------|
| LuxAlgo SMC Historical | `Smart-Money-Concepts.txt` — `file:58` | ~800 | ✅ Fourni |
| LuxAlgo ICT Concepts | `ICT-Concepts.txt` — `file:59` | ~700 | ✅ Fourni |

**Wrapper Python pour import MT5/TradingView :**
Les deux codes sources Pine Script v5 sont dans l'espace KB5. Pour l'intégration MT5, utiliser l'API TradingView (webhook) ou recoder les détections en Python pur selon les règles de détection dans `02_DETECTIONRULES_v5.md`.

---

## RÉFÉRENCES KB5

| Concept | Fichier source |
|---------|---------------|
| EMA 20 Gap Bars AIL/AIS | `04_PRICEACTIONBIBLE_v4.md` Ch. 2-7 |
| ATR Trend Bar Climax | `04_PRICEACTIONBIBLE_v4.md` Ch. 2 + `05_INSTRUMENTS` |
| Volume Displacement ERL | `03_ICTENCYCLOPEDIEv5.md` Section 5.4 |
| LuxAlgo SMC | `Smart-Money-Concepts.txt` (file:58) |
| LuxAlgo ICT | `ICT-Concepts.txt` (file:59) |
| VWAP Terminus | `04_PRICEACTIONBIBLE_v4.md` Ch. 5.2 |
| Volume Profile | `07_MOTEURDECISION.md` |
| RSI Divergences | `04_PRICEACTIONBIBLE_v4.md` |
| VIX sizing | `05_INSTRUMENTS_SPECIFIQUES.md` Section Indices |
| COT Report | `03_ICTENCYCLOPEDIEv5.md` Section 9.2 |
| DXY corrélation | `05_INSTRUMENTS_SPECIFIQUES.md` Section Forex |
| Scoring 100 pts | `07_MOTEURDECISION.md` |

---

*Fin du fichier 08_INDICATEURSCONFIRMATOIRES.md — Sentinel Pro KB5 v1.0 — 2026-03-11*
