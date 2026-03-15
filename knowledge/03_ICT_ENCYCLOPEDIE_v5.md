---
version: "5.0"
type: "encyclopedie_ict"
last_updated: "2026-03-11"
description: "Encyclopédie ICT complète enrichie KB5 — Tags Fractal/Spécifique + Cascade + Amplitude"
source: "KB4 v4.0 + Extensions KB5 (Fractal/Spécifique, Cascade, Amplitude par TF, Instruments)"
---

# 📚 ENCYCLOPÉDIE ICT COMPLÈTE v5.0 — SENTINEL PRO KB5
## Source Unique de Vérité ICT/SMC — Michael Huddleston 2016-2026

> **TAG SYSTEM KB5 :** Chaque concept porte son tag [FRACTAL] ou [SPÉCIFIQUE TF/INSTRUMENT].
> Consulter 01_CADRE_FRACTAL_SPECIFIQUE.md pour la matrice complète d'applicabilité.

---

## SECTION 1 — FONDEMENTS IPDA

### 1.1 L'IPDA — Interbank Price Delivery Algorithm
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS]**

L'algorithme IPDA gère les carnets d'ordres interbancaires mondiaux.
Toute action des prix est la livraison algorithmique de cet algorithme.

**Vérité fondamentale :** Les marchés ne sont PAS aléatoires. Ils sont livrés par un
algorithme qui cherche systématiquement la liquidité.

**Les 4 Objectifs de l'IPDA :**
1. Collecter la liquidité BSL/SSL (purger les stops retail)
2. Combler les déséquilibres FVG/VI (toute dette doit être remboursée)
3. Livrer vers le prochain DOL (toujours un objectif directionnel précis)
4. Suivre les cycles temporels (IPDA fonctionne sur des cycles 20/40/60 jours)

### 1.2 Cycles IPDA — Lookback
**[SPÉCIFIQUE : 60j/40j → MN/W/D1 | 20j → MN/W/D1/H4]**

| Cycle | TF Applicables | Usage |
|-------|---------------|-------|
| **20 jours** | MN, W, D1, H4 | Dealing Range immédiate (EQ, Premium, Discount) |
| **40 jours** | MN, W, D1 | Tendance du trimestre en cours |
| **60 jours** | MN, W, D1 | Direction institutionnelle macro |

```python
# Lookback T-20 — Règle KB5
High_T20 = max(20_dernieres_bougies_Daily)
Low_T20  = min(20_dernieres_bougies_Daily)
EQ_T20   = (High_T20 + Low_T20) / 2

# INTERDICTION ABSOLUE :
# Si prix > EQ_T20 (zone Premium HTF) → bot N'ENTRE PAS en swing long
# Risque de Quarterly Shift trop élevé
```

### 1.3 Power of Three (AMD) — Le Cycle Fondamental
**[FRACTAL — TOUS TF (⚠️ M1 dégradé)]**

| TF | Accumulation | Manipulation | Distribution |
|----|-------------|--------------|--------------|
| MN | Janvier | Février | Mars-Décembre |
| W  | Lundi | Mardi | Mercredi-Vendredi |
| D1 | 00h-08h NY | 08h-10h NY | 10h-16h NY |
| H4/H1 | Début Killzone | Milieu Killzone | Fin Killzone |
| M5 | 0-15 min Macro | 15-30 min Macro | 30-60 min Macro |
| M1 | ⚠️ Trop micro — utiliser CISD | — | — |

---

## SECTION 2 — STRUCTURE DE MARCHÉ

### 2.1 Terminologie Officielle
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS]**

| Terme | Définition | Signal Bot |
|-------|-----------|-----------|
| **MSS** | Cassure swing MAJEUR + Displacement | Signal d'exécution |
| **CHoCH** | Cassure swing mineur | Avertissement uniquement |
| **BOS** | Continuation dans le sens de la tendance | Confirmation HTF Bias |
| **HH/HL** | Hauts/bas croissants | Structure haussière |
| **LL/LH** | Bas/hauts décroissants | Structure baissière |

**Règle Anti-Inducement Absolue :**

```python
Boolean_Sweep_ERL = False  # Par défaut

# IF prix N'A PAS purgé de liquidité externe (ERL) :
#     IGNORER tous CHoCH, MSS, FVG, OB
#     Boolean_Sweep_ERL reste False
#     → AUCUNE EXCEPTION. Jamais.
```

### 2.2 Smooth vs Jagged Highs/Lows — Concept 2024
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS]**

- **Smooth High :** Hauts alignés horizontalement → Masse de BSL au-dessus → Cible prioritaire
- **Jagged High :** Hauts irréguliers → Liquidité déjà prise ou non ciblée → Ignorer
- **Smooth Low :** Bas alignés → Masse de SSL en dessous → Cible prioritaire
- **Jagged Low :** Bas irréguliers → Ignorer

**Amplitude par TF :**

| TF | Tolérance alignement "Smooth" |
|----|------------------------------|
| MN/W | ± 30-50 pips |
| D1/H4 | ± 10-20 pips |
| H1 | ± 5-10 pips |
| M5/M1 | ± 2-5 pips |

---

## SECTION 3 — LES PD ARRAYS (Zones Institutionnelles)

### 3.1 Hiérarchie PD Array Matrix 2025
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS]**

| Rang | PD Array | Force | Condition requise |
|------|---------|-------|------------------|
| 1 | **Consequent Encroachment (CE)** | ★★★★★ | 50% d'un FVG D1/H4 frais |
| 2 | **Suspension Block 2025** | ★★★★★ | Bougie entre 2 Volume Imbalances |
| 3 | **Breaker Block** | ★★★★☆ | OB invalide qui se retourne |
| 4 | **Order Block (OB)** | ★★★★☆ | Dernière bougie opposée avant move |
| 5 | **FVG** | ★★★★☆ | 3 bougies avec espace entre mèches |
| 6 | **BPR** | ★★★☆☆ | Superposition FVG opposés |
| 7 | **Rejection Block** | ★★★☆☆ | Cluster de mèches sans corps |
| 8 | **NDOG / NWOG** | ★★★☆☆ | Gap ouverture jour/semaine |
| 9 | **Volume Imbalance** | ★★☆☆☆ | Corps non chevauchés |

### 3.2 FVG — Fair Value Gap
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS]**

**Condition de formation :**

```
FVG Bullish : Candle[N-1].High < Candle[N+1].Low (espace entre les mèches)
FVG Bearish : Candle[N-1].Low > Candle[N+1].High
+ Le corps de Candle[N] (bougie centrale) doit être large = Displacement
```

**Statuts de Freshness (KB5) :**
- **FRAIS :** Jamais visité → Force maximale → Utiliser
- **MITIGÉ :** Visité une fois partiellement → Force réduite → Utiliser avec précaution
- **REVISITÉ :** 2+ visites → Force faible → Éviter sauf confluence majeure
- **INVALIDE :** Prix clôturé au-delà → Supprimer du dossier

**1st Presented FVG (2025) :**

```
Fenêtre : 09h30-10h00 NY uniquement
Condition : FVG créé sur M1 après 09h30 ET casse le range de la bougie 09h29
Résultat : Biais scellé à 90% pour la journée entière
SPÉCIFIQUE : M1/M5 uniquement — fenêtre 09h30-10h00
```

**Amplitude FVG par TF :**

| TF | Amplitude minimale | Amplitude typique | Puissance |
|----|-------------------|-------------------|-----------|
| MN | 100 pips | 200-2000 pips | ★★★★★ |
| W  | 50 pips | 50-200 pips | ★★★★★ |
| D1 | 15 pips | 20-80 pips | ★★★★☆ |
| H4 | 8 pips | 10-40 pips | ★★★★☆ |
| H1 | 4 pips | 5-20 pips | ★★★☆☆ |
| M15 | 2 pips | 2-10 pips | ★★★☆☆ |
| M5 | 1.5 pips | 2-8 pips | ★★☆☆☆ |
| M1 | 1 pip | 1-5 pips | ★★☆☆☆ |

### 3.3 Order Block (OB) — Critères Précis
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS]**

**Un OB valide doit satisfaire 3/5 critères minimum :**
1. Dernière bougie OPPOSÉE avant un grand mouvement
2. Corps de la bougie OB ≥ 50% de son range High-Low
3. Le mouvement après l'OB crée un FVG (Displacement)
4. Le niveau de l'OB coïncide avec un niveau de liquidité (EQL/EQH)
5. L'OB est FRAIS (prix ne l'a jamais revisité)

**Scoring OB pour le bot :**

```
5/5 critères : OB A++ — Score 5/5
4/5 critères : OB A   — Score 4/5
3/5 critères : OB acceptable — Score 3/5
< 3 critères : OB INVALIDE — Ignorer
```

**Amplitude OB par Timeframe :**

| TF | Amplitude typique | Buffer tolérance |
|----|------------------|-----------------|
| MN | 300-800 pips | ±50 pips |
| W | 100-300 pips | ±20 pips |
| D1 | 30-80 pips | ±10 pips |
| H4 | 15-40 pips | ±5 pips |
| H1 | 5-15 pips | ±3 pips |
| M15 | 2-8 pips | ±2 pips |
| M5/M1 | 1-4 pips | ±1 pip |

**Règle d'invalidation universelle :**

```python
def is_ob_invalidated(ob, current_candle):
    # Seule une CLÔTURE invalide. Un wick ne suffit pas.
    if ob["type"] == "BULLISH_OB":
        return current_candle.close < ob["low"]
    elif ob["type"] == "BEARISH_OB":
        return current_candle.close > ob["high"]
```

### 3.4 Suspension Block — Nouveau PD Array 2025
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS]**

**Définition :** Bougie unique "suspendue" entre deux Volume Imbalances.
**Critère visuel :** Wick de la bougie précédente ET wick de la suivante chevauchent
le corps de la bougie centrale, sans FVG classique.
**Force :** +2 pts supplémentaires vs OB standard sur tous les TF.

### 3.5 BPR — Balanced Price Range
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS]**

**Identification :**
- Range de 20 bougies avec upper_touches ≥ 5 ET lower_touches ≥ 5
- Volume normal (pas de spike)
- Range ≤ 50 pips (amplitude typique)

**Cas Tradeable :**
- Breakout haussier avec volume x2 → BUY — fiabilité 90%
- Breakout baissier avec volume x2 → SELL — fiabilité 90%
- Target = midpoint range × 1.5

**BPR Failure (Flout) :**
- Wick du breakout > 40% du corps → Manipulation
- Réintégration du range dans les 3 bougies → Faux breakout

---

## SECTION 4 — TIMING ET MACROS

### 4.1 Les Killzones — Fenêtres Institutionnelles
**[SPÉCIFIQUE : M5/M15/H1 — FOREX/GOLD/INDICES]**

| Killzone | Horaire EST | Activité | Position Sizing |
|----------|------------|----------|-----------------|
| Asian KZ | 20h00-00h00 | Accumulation silencieuse | 20% |
| London Prep | 02h00-03h00 | Préparation London | 50% |
| **London Open** | **03h00-05h00** | **Première manipulation** | **100%** |
| London AM | 06h00-08h00 | Suite London | 50% |
| **NY Open (KZ3)** | **08h00-12h00** | **Meilleure KZ. Priorité A++** | **100%** |
| NY Lunch | 12h00-14h00 | Scalp uniquement | 50% |
| **NY PM (KZ5)** | **14h00-17h00** | **Deuxième opportunité** | **100%** |
| CBDR Window | 17h00-20h00 | Calcul CBDR — pas de trading | 20% |

### 4.2 Les Macros ICT — Fenêtres Algorithmiques
**[SPÉCIFIQUE : H1/M15/M5/M1 — TOUS INSTRUMENTS]**

| # | Fenêtre EST | Mode | Action Bot |
|---|------------|------|-----------|
| 1 | 00h00-06h00 | Accumulation silencieuse | Mode veille |
| 2 | 06h00-08h00 | Préparation London | 50% sizing |
| **3** | **08h00-12h00** | **London Open — PRIORITÉ A++** | **100% sizing** |
| 4 | 12h00-14h00 | London Lunch — Scalp | 50% sizing |
| **5** | **14h00-17h00** | **NY Open — PRIORITÉ A++** | **100% sizing** |
| 6 | 17h00-20h00 | CBDR Calculation | 50% sizing |
| 7 | 20h00-21h00 | Fermeture Wall St. | 20% sizing |
| 8 | 21h00-00h00 | Transition Asie | 20% sizing |

**CBDR (Central Bank Decision Range) :**
**[SPÉCIFIQUE : D1 — FOREX UNIQUEMENT]**

```python
# Calcul obligatoire chaque jour entre 17h00-20h00 EST
CBDR_Range = High_17h_20h - Low_17h_20h  # en pips

if CBDR_Range < 40:
    CBDR_Explosive = True
    # → Journée explosive probable le lendemain
    # → Attendre les grandes Macros 3 et 5 uniquement
elif CBDR_Range > 100:
    CBDR_Normal = True
    # → Trading plan standard applicable
```

### 4.3 Les Silver Bullet — Fenêtres d'Entrée Précises
**[SPÉCIFIQUE : M5 — FOREX/GOLD]**

3 fenêtres par jour où le prix crée un FVG M5 tradable :
- **Silver Bullet 1 :** 10h00-11h00 EST
- **Silver Bullet 2 :** 14h00-15h00 EST
- **Silver Bullet 3 :** 20h00-21h00 EST (Session Asiatique)

**Condition de validation :**
- FVG M5 créé DANS la fenêtre temporelle
- MSS ou CISD présent après le FVG
- Dans le sens du Daily Bias

---

## SECTION 5 — MODÈLES DE TRADING

### 5.1 Le Judas Swing — 6 Phases
**[FRACTAL — MN/W/D1/H4/H1 — TOUS INSTRUMENTS]**
**[⚠️ M15 partiel — M5/M1 : utiliser CISD]**

| Phase | Horaire relatif | Description | Signal Bot |
|-------|----------------|-------------|-----------|
| 1. Accumulation | Pre-Killzone | Range étroit, VWAP plat | SOD = ACCUMULATION |
| 2. False Start | Début KZ | Push dans FAUSSE direction | FVG faible + Wick long détectés |
| 3. Acceleration Fausse | +10 min | Momentum fausse direction | ⛔ Anti-Inducement : NE PAS ENTRER |
| 4. The Reversal | -30 min vrai move | MSS + Displacement | Boolean_Sweep_ERL = True |
| 5. Retracement | +15 min | Prix revient dans le FVG | ✅ ENTRÉE OPTIMALE au CE du FVG |
| 6. Distribution | +1-4h | Vrai mouvement directionnel | Trail Stop, profits partiels |

**Amplitude Judas Swing par TF :**

| TF | Durée phases 1-3 | Amplitude fausse direction |
|----|-----------------|--------------------------|
| MN/W | Semaines | 200-1000+ pips |
| D1 | 2-6h | 30-100 pips |
| H4 | 1-2h | 15-50 pips |
| H1 | 20-45 min | 8-25 pips |

### 5.2 Le Grail Setup — 5 Conditions OBLIGATOIRES
**[SPÉCIFIQUE : H4/H1 (⚠️ M15 adapté) — FOREX/GOLD]**

**Toutes les 5 conditions DOIVENT être remplies simultanément :**

```
1. Boolean_Sweep_ERL = True          (ERL purgé)
2. MSS confirmé HTF avec Displacement
3. OTE entre 70.5%-79% du dernier swing
4. FVG frais dans la Killzone active
5. Alignement avec le Weekly Bias

→ Score Grail = 100/100 automatiquement si 5/5 réunies
→ EXÉCUTION AUTOMATIQUE si score ≥ 80
```

### 5.3 Venom Trading Model — 2025
**[SPÉCIFIQUE : M5/M15 — NQ/ES/YM EXCLUSIVEMENT]**
**[⛔ NON APPLICABLE : FOREX, BTC, GOLD]**

```
Étape 1 : Tracer High & Low entre 08h00-09h30 EST (90-min Range)
Étape 2 : À 09h30 → l'algorithme DOIT purger soit le High soit le Low
Étape 3 : Après le Sweep → Chercher FVG + BPR + CISD
Étape 4 : Entrée au CE du premier FVG post-sweep
Cible   : Côté opposé de la plage 90min + Projection SD -2.0
Profit typique : 50-80 ticks sur NQ/ES

Bot Flag : Activer Venom_Active = True entre 08h00-11h00 (jours de semaine)
```

### 5.4 CISD 2026 — Change in State of Delivery
**[SPÉCIFIQUE : M1/M5/M15 (⚠️ H1 adapté) — TOUS INSTRUMENTS]**

```
Condition : Sans attendre la cassure d'un swing fractal,
la clôture du CORPS de la bougie actuelle doit dépasser
les CORPS des 2 bougies précédentes, DANS UNE MACRO.

Signal : Plus précoce que le MSS
Avantage : Entrée "early bird" +10-20 pips/ticks avant les autres
Utilisation : Remplace le Judas Swing sur M5/M1
```

### 5.5 MMXM — Market Maker Models
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS (⚠️ M1 dégradé)]**

**Market Maker Buy Model :**
1. Accumulation (SSL ciblé en dessous)
2. Manipulation baissière (Sweep SSL → Boolean_Sweep_ERL = True)
3. Distribution haussière (le vrai mouvement)
4. Re-accumulation (consolidation avant prochain leg)

**Market Maker Sell Model :** Inverse miroir exact.

**Durée du cycle par TF :**

| TF | Durée cycle complet |
|----|---------------------|
| MN/W | 3-6 mois |
| D1 | 3-10 jours |
| H4/H1 | 4-24 heures |
| M15/M5 | 30-90 minutes |

### 5.6 Unicorn Model — 2022
**[SPÉCIFIQUE : H4+H1 simultanément — FOREX/GOLD/INDICES]**

```
Conditions :
- MSS sur deux TF simultanément (ex: H1 + H4)
- FVG sur les deux TF dans la même zone géographique

→ Score automatique = 95/100
→ Micro-Unicorn (M5+M1) = 75/100 (moins fiable)
```

---

## SECTION 6 — SYSTÈMES DE LIQUIDITÉ

### 6.1 BSL/SSL — Les Cibles Algorithmiques
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS]**

```
BSL (Buy-Side Liquidity) :         SSL (Sell-Side Liquidity) :
─────────────────────────          ─────────────────────────
EQH (Equal Highs)                  EQL (Equal Lows)
PWH (Previous Week High)           PWL (Previous Week Low)
PDH (Previous Day High)            PDL (Previous Day Low)
Smooth Highs                       Smooth Lows
Résistances visibles               Supports visibles
→ Piège pour vendeurs à découvert  → Piège pour acheteurs
```

### 6.2 ERL/IRL Cycles — Séquence Prédictive
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS]**

```
ERL (External Range Liquidity) → PDH, PDL, EQH, EQL (hors du range)
IRL (Internal Range Liquidity) → FVG, CE d'OB, milieu de range

Séquence Prédictive (~70% du temps) :
1. SWEEP ERL HIGH → Prédiction : IRL Mid dans 30-90 min
2. SWEEP IRL MID  → Prédiction : ERL LOW dans 30-90 min
3. SWEEP ERL LOW  → Phase post-sweep = ENTRÉE contre le sweep = A++
```

### 6.3 Magnetic Force Theory — Score de Niveau
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS]**

| Facteur | Points | Condition |
|---------|--------|-----------|
| Distance < 50 pips | +30 | Niveau proche = plus magnétique |
| Type FVG / Extrémum | +35-40 | Zone institutionnelle forte |
| Type OB | +30 | Réentrée institutionnelle |
| Type S/R Historique | +20 | Niveau testé 3+ fois |
| Fraîcheur < 10 bougies | +15 | FRAIS = plus puissant |
| Confluence 2+ niveaux | +15 | Cascade fractale bonus |

```
Score ≥ 85 : Attraction quasi-garantie → Cibler
Score 60-84 : Probable → Surveiller
Score < 40  : Ignorer le niveau
```

---

## SECTION 7 — PROFILS HEBDOMADAIRES

### 7.1 Les 5 Weekly Templates
**[SPÉCIFIQUE : W1 — FOREX/GOLD]**

| Template | Fréquence | Structure | Piège Critique | Jour Danger |
|----------|-----------|-----------|---------------|-------------|
| **Classic Bullish** | 35% | Lun acc. → Mar-Ven hausse | Judas Swing mardi AM | Mardi AM |
| **Classic Bearish** | 30% | Lun acc. → Mar-Ven baisse | Judas Swing mardi AM | Mardi AM |
| **Up-Down-Up** | 20% | Lun-Mar ↑ → Mer ↓ (fake) → Jeu-Ven ↑ | Mercredi = PIÈGE MAJEUR | Mercredi |
| **Down-Up-Down** | 15% | Lun-Mar ↓ → Mer ↑ (fake) → Jeu-Ven ↓ | Mercredi = PIÈGE MAJEUR | Mercredi |
| **Choppy** | 5% | Accumulation toute la semaine | NO-TRADE semaine entière | TOUS |

### 7.2 Reconnaissance Automatique du Template
**[SPÉCIFIQUE : W1 — FOREX/GOLD]**

```python
# Algorithme de reconnaissance — Dimanche soir

if lundi_range < 20 and lundi_volume < moyenne * 0.8:
    accueil = "ACCUMULATION"  # Attendre confirmation mardi

if mardi_breakout_haussier and mardi_fvg_present and mardi_retracement_immediat:
    template = "CLASSIC_UP"   # 35% probabilité de base
    dol = "HIGH_mercredi_jeudi"

if mardi_breakout_haussier and mardi_retracement_complet:
    template = "UP_DOWN_UP"   # 20% probabilité
    # DANGER : Mercredi = fake baissier probable

if position_t20 == "DISCOUNT" and cot == "BULLISH" and biais_mn == "BULLISH":
    template_prob_CLASSIC_UP += 0.10  # Probabilité ajustée

if pwh_purge and pwl_purge and range_semaine < 50:
    template = "CHOPPY"       # NO-TRADE
```

---

## SECTION 8 — STATE OF DELIVERY (SOD)

### 8.1 Les 5 États de Livraison
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS]**

| État | Signaux | Action Bot | Position Size |
|------|---------|-----------|---------------|
| **ACCUMULATION** | VWAP plat, range < 20 pips, volume décroissant | NO-TRADE | 0% |
| **MANIPULATION** | Spike ATR×2, volume×3, rejet immédiat | ⛔ FREEZE Anti-Inducement | 0% |
| **STRONG_DIST.** | HH/HL réguliers, volume normal, EMA20 rejeté | TRADER AGRESSIVEMENT | 100% |
| **WEAK_DIST.** | HH/HL désordonnés, pullbacks > 40% | TRADER MODÉRÉMENT | 50% |
| **UNKNOWN** | Données insuffisantes | ⛔ INTERDICTION ABSOLUE | 0% |

---

## SECTION 9 — ANALYSE CORRÉLATIVE SMT

### 9.1 SMT Divergence — Les 10 Configurations
**[FRACTAL — TOUS TF (focus H4/H1) — FOREX/GOLD/INDICES]**

| Config | Signal Principal | Signal Corrélé | Verdict | Action |
|--------|-----------------|----------------|---------|--------|
| 1 | EUR/USD BULLISH | DXY BEARISH | ALIGNÉ ✅ | BUY EUR — A++ |
| 2 | EUR/USD BULLISH | DXY BULLISH | CONFLIT ⚠️ | Réduire taille 60% |
| 3 | BTC BULLISH | SPX BEARISH | DIVERGENCE | Réduire 30% |
| 4 | EUR/USD BEARISH | SPX BULLISH | CONFLIT | PASSER le trade |
| 5 | USD/JPY BULLISH | SPX BEARISH + VIX↑ | PARFAIT ✅ | BUY USD/JPY — A++ |
| 6 | AUD/USD BULLISH | Copper BEARISH | CONFLIT MAJEUR | PASSER complet |
| 7 | Gold RISING | USD RISING | DIVERGENCE RARE | Réduire 25% |
| 8 | 10Y Yields FALLING | DXY RISING | CONFLIT | Analyser raison |
| 9 | BTC BULLISH | ETH BEARISH | ROTATION | BTC OK, pas ETH |
| 10 | NQ BULLISH | YM BEARISH | DIV. SECTORIELLE | Attendre clarification |

### 9.2 COT Reports — Commitment of Traders
**[SPÉCIFIQUE : MN/W (⚠️ D1 contexte) — FOREX/GOLD]**

Rapport CFTC hebdomadaire (publié vendredi 15h30 EST) :
- **Non-Commercial Longs nets ↑ :** Biais haussier confirmé semaine suivante
- **Non-Commercial Longs nets ↓ :** Prudence, reversal possible
- **Commercial vs Non-Commercial divergence :** SMT signal macro

**Paires à surveiller :**
- EUR/USD → Positions EUR futures CME
- GBP/USD → Positions GBP futures
- USD/JPY → Inverser positions JPY (contrat contre USD/JPY)
- XAU/USD → Positions Gold futures COMEX

---

## SECTION 10 — GESTION DU RISQUE

### 10.1 Stop Loss ICT — Placement Algorithmique
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS]**

```
RÈGLES ABSOLUES :
- SL TOUJOURS sous le Low COMPLET de l'OB/FVG (pas à l'intérieur)
- Buffer minimum = spread + 2 pips (FOREX) ou 2 ticks (Indices)
- Le prix "respire" toujours avant de partir → Laisser de la marge

Types de SL :
- SL Outside OB    : Sous le Low de l'Order Block
- SL Outside FVG   : Sous le bas du FVG bullish
- SL Outside Swing : Sous le dernier swing low validé
```

### 10.2 Système de Scoring 100 Points — KB5
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS]**

| Critère | Points | Condition |
|---------|--------|-----------|
| Killzone active + Macro | 20 | Fenêtre temporelle correcte |
| ERL Sweep (Boolean_Sweep_ERL) | 20 | ERL purgé avant le signal |
| Zone OB/FVG qualité (PD Matrix) | 20 | Selon hiérarchie PD Array |
| DOL identifié + RR ≥ 2:1 | 20 | Cible logique confirmée |
| Corrélation SMT (DXY + paires) | 20 | Alignement intermarket |

**Ajustements Bonus/Malus :**

| Ajustement | Points | Condition |
|-----------|--------|-----------|
| Entrée sur ENIGMA (.20/.80) | +10 | Niveau algorithmique précis |
| Weekly Template confirmé | +5 | Probabilité ajustée |
| 1st Presented FVG (09h30-10h) | +5 | Biais scellé 90% |
| Cascade fractale double | +15 | FVG H1 dans OB H4 |
| Cascade fractale triple | +35 | FVG H1 + OB H4 + FVG D1 |
| Grail Setup complet | +0 | Score automatique 100 |
| Target hors niveaux .00/.50 | -15 | TP mal placé |
| Premium T-20 + long swing | -20 | Structure HTF contre |
| News < 30 min | -50 | Gel obligatoire |

**Décision finale :**

```
Score 80-100 : EXÉCUTION A++  → Full size (100%)
Score 65-79  : SNIPER          → 50% size, confirmer H2/L2
Score < 65   : INTERDIT        → No-trade, log raison
```

### 10.3 Pyramidage et Partiels ICT
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS]**

```
Partiel 1 (25%) : Std Dev -1.0 / prochain .00 ou .50
Partiel 2 (25%) : Std Dev -2.0
Partiel 3 (50%) : Std Dev -2.5 = cible algorithmique finale

→ Déplacer SL au Break-Even après Partiel 1 obligatoire
→ Terminus Point : Sortie 100% si PA Measured Move + KZ + .00/.50 simultanés
```

---

## SECTION 11 — CONCEPTS 2025-2026

### 11.1 Institutional Pricing Theory — ENIGMA
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS]**

| Niveau | Signification | Force | Règle Bot |
|--------|--------------|-------|-----------|
| **.00** | Big Figure | ★★★★★ | TP obligatoire. Jamais SL ici. |
| **.50** | Mid Figure | ★★★★★ | TP obligatoire. Jamais SL ici. |
| **.20** | Engagement Long | ★★★★☆ | Entrée longue idéale +10pts |
| **.80** | Engagement Short | ★★★★☆ | Entrée short idéale +10pts |

**Règle d'or :** Toujours placer les TP sur .00 ou .50. Jamais sur .437 ou .683.

### 11.2 RDRB — Redelivered Rebalanced Price Range
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS]**

**Définition :** Zone retravaillée 3+ fois par l'algorithme.
**Comportement :** Barrière quasi-infranchissable à court terme.

```
Bot Rule :
- Utiliser le RDRB comme ancre pour le SL ou rebond
- Ne JAMAIS shorter sur un RDRB haussier
- Ne JAMAIS longer sur un RDRB baissier
- Si prix traverse un RDRB avec volume x2 → Acceleration signal
```

### 11.3 Checklist Anti-Inducement Finale — 30 Secondes
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS]**

```
Avant TOUTE exécution, vérifier les 10 points :

□ 1.  Narrative HTF formulée (D1 + Direction + DOL)
□ 2.  Boolean_Sweep_ERL = True (ERL purgé)
□ 3.  Signal = MSS (pas juste CHoCH)
□ 4.  Dans une Killzone ou Macro active
□ 5.  SL sous le Low COMPLET de l'OB
□ 6.  HTF (D1/H4) dans la même direction
□ 7.  Pas lundi avant 10h NYC
□ 8.  RR ≥ 2:1
□ 9.  COT aligné ou neutre
□ 10. Aucune news majeure dans les 30 minutes

Si 1 case non cochée → STOP
Si 10/10 cases cochées → EXÉCUTION AUTORISÉE
```

---

## SECTION 12 — PROTOCOLE NEWS

### 12.1 Les 7 News Critiques
**[SPÉCIFIQUE : D1/H4/H1 — FOREX/GOLD/INDICES selon news]**

| News | Timing EST | Impact | Protocole Bot |
|------|-----------|--------|--------------|
| **NFP** | 1er Vendredi, 08h30 | 10/10 | Gel 15 min avant. Limit orders seulement 0-30 min après |
| **FOMC** | 6x/an, Mercredi 14h00 | 9/10 | Gel 60 min avant. Entrée 30 min après |
| **CPI** | Mensuel, 08h30 | 8/10 | Gel 15 min avant |
| **ECB** | 6x/an, Jeudi 13h45 | 8/10 | Gel 15 min avant |
| **BoE** | 8x/an, Jeudi 12h00 | 7/10 | Gel 15 min avant |
| **China PMI** | Mensuel, variable | 6/10 | Réduire la taille |
| **RBA/BOJ** | Variable | 6/10 | Réduire la taille |

### 12.2 Les 3 Phases de Chaque News

```
Phase 1 (0-5 min après) :    MANIPULATION → Faux premier mouvement → NE PAS TRADER
Phase 2 (5-15 min après) :   Attendre premier MSS avec Displacement → Entrée possible
Phase 3 (15+ min après) :    LE VRAI MOUVEMENT → Entrée en confiance

Règle NFP Vendredi :
Si gain > 30 pips avant 08h15 → Fermer toutes positions
```

---

## SECTION 13 — SAISONNALITÉ & BIAIS MACRO

### 13.1 Yearly Seasonality par Devise
**[SPÉCIFIQUE : MN — FOREX]**

| Trimestre | EUR | GBP | JPY | Notes |
|-----------|-----|-----|-----|-------|
| Q1 (Jan-Mar) | Normalement baissier | Variable | Haussier | USD fort début d'année |
| Q2 (Avr-Jun) | Tendance à rebondir | Haussier | Baissier | Risk-on printanier |
| Q3 (Jul-Sep) | Incertain | Baissier | Variable | Vacances = liquidité faible |
| Q4 (Oct-Déc) | Haussier | Haussier | Mixte | Fin d'année = positioning |

### 13.2 Quarterly Shift
**[SPÉCIFIQUE : MN/W — TOUS INSTRUMENTS]**

```
Chaque début de trimestre = Repositionnement institutionnel majeur.
Règle : Durant les 2-3 premières semaines du trimestre = PRUDENCE MAXIMALE.
Les niveaux Lookback T-60 peuvent être ciblés pour la nouvelle dealing range.

Bot Rule :
- Semaines 1-2 du trimestre : Réduire taille de 50%
- Semaine 3 : Retrouver la taille normale si direction confirmée
```

```python
def is_quarterly_shift_period(current_date):
    """
    Détecte si nous sommes dans la période de transition trimestrielle
    """
    month = current_date.month
    day   = current_date.day
    is_start = month in [1, 4, 7, 10] and day <= 14

    if is_start:
        return True, "REDUCE_50PCT", f"QSM actif — Semaine {(day//7)+1} du Q{(month-1)//3+1}"
    elif month in [1, 4, 7, 10] and day <= 21:
        return True, "REDUCE_25PCT", "QSM — Phase orientation"
    return False, "NORMAL", "Hors période QSM"
```

---

## SECTION 14 — CASCADE FRACTALE

### 14.1 Principe de la Cascade
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS]**

Un signal est **multiplié** quand le même concept existe sur plusieurs TF simultanément.
C'est la règle de scoring la plus impactante du KB5.

```
CASCADE TRIPLE (D1 + H4 + H1) : +35 pts
CASCADE DOUBLE (D1 + H4 ou H4 + H1) : +15 pts
STANDALONE (TF isolé) : 0 pts bonus
```

```python
def check_cascade(pd_array_ltf, pd_arrays_htf_list):
    cascade_count = 0
    for pd_htf in pd_arrays_htf_list:
        if (pd_array_ltf["low"] >= pd_htf["low"] and
            pd_array_ltf["high"] <= pd_htf["high"] and
            pd_htf["freshness"] in ["FRAIS", "MITIGÉ"]):
            cascade_count += 1
    if cascade_count >= 2:
        return {"cascade": True, "bonus": 35, "label": "CASCADE_TRIPLE"}
    elif cascade_count == 1:
        return {"cascade": True, "bonus": 15, "label": "CASCADE_DOUBLE"}
    return {"cascade": False, "bonus": 0, "label": "STANDALONE"}
```

### 14.2 MMXM Multi-TF — Convergence des Phases
**[FRACTAL — D1/H4/H1 — TOUS INSTRUMENTS]**

```python
def check_mmxm_convergence(mmxm_d1, mmxm_h4, mmxm_h1):
    # D1 Distribution + H4 Accumulation = re-entrée dans le trend
    if mmxm_d1 == "DISTRIBUTION" and mmxm_h4 == "ACCUMULATION":
        return {"signal": "BUY_CONTINUATION", "bonus": 10}
    # Double Manipulation = zone dangereuse, attendre
    if mmxm_d1 == "MANIPULATION" and mmxm_h1 == "MANIPULATION":
        return {"signal": "FREEZE", "reason": "DOUBLE_MANIPULATION", "bonus": -20}
    # Ré-accumulation sur les deux TF = signal fort
    if mmxm_d1 == "RE_ACCUMULATION" and mmxm_h4 == "ACCUMULATION":
        return {"signal": "HIGH_PROBABILITY_BUY", "bonus": 15}
    return {"signal": "STANDARD", "bonus": 0}
```

**Lecture rapide des convergences :**

| MMXM D1 | MMXM H4 | MMXM H1 | Verdict | Bonus |
|---------|---------|---------|---------|-------|
| DISTRIBUTION | ACCUMULATION | — | Re-entrée trend | +10 |
| MANIPULATION | — | MANIPULATION | FREEZE | -20 |
| RE_ACCUMULATION | ACCUMULATION | — | Signal fort | +15 |
| DISTRIBUTION | DISTRIBUTION | DISTRIBUTION | Triple dist. A++ | +20 |
| UNKNOWN | — | — | Interdit | -50 |

### 14.3 ERL/IRL — Délais par TF et Expiration de Cycle
**[FRACTAL — TOUS TF — TOUS INSTRUMENTS]**

| TF | Délai ERL→IRL | Délai IRL→ERL | Fiabilité | Expiration |
|----|--------------|--------------|-----------|------------|
| MN→W | 2-4 semaines | 3-6 semaines | 65% | 40 320 min |
| W→D1 | 1-3 jours | 2-4 jours | 70% | 5 760 min |
| D1→H4 | 2-6h | 4-12h | 72% | 720 min |
| H4→H1 | 30-90 min | 1-3h | 75% | 180 min |
| H1→M15 | 15-45 min | 30-60 min | 78% | 60 min |
| M15→M5 | 5-20 min | 10-30 min | 80% | 30 min |

```python
def is_erl_irl_cycle_valid(sweep_event, elapsed_minutes, timeframe):
    max_delays = {
        "MN": 40320, "W": 5760, "D1": 720,
        "H4": 180,   "H1": 60,  "M15": 45, "M5": 20
    }
    max_delay = max_delays.get(timeframe, 60)
    if elapsed_minutes > max_delay:
        return False, "CYCLE_EXPIRÉ — Chercher le nouveau ERL"
    return True, "CYCLE_ACTIF"
```

---

## RÉFÉRENCES INTER-FICHIERS KB5

| Concept | Fichier source | Usage |
|---------|---------------|-------|
| Matrice Fractal/Spécifique complète | `01_CADRE_FRACTAL_SPECIFIQUE.md` | Gouvernance de tous les tags |
| Pipeline d'analyse Top-Down | `02_PYRAMIDE_ANALYSE.md` | Ordre d'application des concepts |
| Règles adaptées par instrument | `05_INSTRUMENTS_SPECIFIQUES.md` | Forex / Indices / BTC / Or / Pétrole |
| Scoring 100pts + veto + décision | `07_MOTEUR_DECISION.md` | Verdict final d'exécution |
| Dossier JSON par paire | `06_DOSSIER_PAIRE_SCHEMA.md` | Format de sortie des analyses |

---

*ICT Encyclopédie v5.0 — KB5 Sentinel Pro — 2026-03-11*
*Source : KB4 v4.0 + Extensions KB5 — Mentorships Huddleston 2016-2026*
*Tags Fractal/Spécifique + Amplitude par TF + Cascade + Freshness ajoutés*
*Gouvernance : 01_CADRE_FRACTAL_SPECIFIQUE.md | Moteur : 07_MOTEUR_DECISION.md*
