---
version: "4.0"
type: "bible_price_action"
last_updated: "2026-03-11"
description: "Bible Price Action v4.0 — KB5 Enrichie — Synergies ICT/PA + Tags TF + Confluence Scoring"
source: "PA Bible v3.0 + Extensions KB5 (Tags, Synergies ICT, Terminus enrichi, Narration Double)"
---

# 📖 BIBLE PRICE ACTION v4.0 — SENTINEL PRO KB5
## Al Brooks + Analyse Classique — Source Complète et Définitive

> **INTÉGRATION KB5 :** Chaque setup PA porte sa synergie ICT correspondante.
> Consulter 03_ICT_ENCYCLOPEDIE_v5.md pour les définitions ICT complètes.
> Consulter 07_MOTEUR_DECISION.md pour le scoring final.

---

## CHAPITRE 1 — LES 3 ÉTATS DU MARCHÉ

Tout marché est dans l'un de ces 3 états permanents. L'identification correcte est la condition préalable à TOUTE décision.

### 1.1 État 1 : BREAKOUT (Cassure)
**Définition :** Mouvement directionnel rapide qui sort d'un range.

**Caractéristiques :**
- Bougies de tendance larges (Trend Bars) avec peu de mèches
- Gap entre les corps de bougies (urgence institutionnelle)
- EMA 20 non retestée (le marché "fuit")
- Volume croissant

**Action Bot :** Entrer dans le sens du breakout uniquement si HTF confirme. Chercher le premier pullback (PE1) pour entrée de continuation.

**Piège :** Si le breakout est suivi immédiatement d'une grande bougie inverse → C'est un Flout/Failed BO. NE PAS ENTRER.

**Synergie ICT — KB5 :**

| Situation PA | Équivalent ICT | Verdict |
|-------------|----------------|---------|
| Breakout haussier fort | MSS + Displacement | ✅ A++ si Boolean_Sweep_ERL = True |
| Breakout sans volume | CHoCH seul | ⚠️ Attendre confirmation |
| Failed Breakout (Flout) | Judas Swing Phase 3 | ⛔ Anti-Inducement — NE PAS ENTRER |
| Breakout + retour EMA | Retour au CE du FVG | ✅ Entrée optimale |

### 1.2 État 2 : CANAL (Channel/Trend)
**Définition :** Tendance régulière avec pieds et sommets alternés (HH/HL ou LL/LH).

**Caractéristiques :**
- EMA 20 en angle d'environ 30-45 degrés
- Pullbacks peu profonds (< 40% du leg précédent)
- Chaque pullback teste la EMA 20 et rebondit

**Action Bot :** Mode "Always In" (AIL ou AIS selon direction). Acheter/Vendre les pullbacks, pas le momentum.

**Sortie :** Dès que le marché brise la structure et entre en Trading Range.

**Synergie ICT — KB5 :**
- Canal haussier = MMXM Phase 3 Distribution → Chercher les OB/FVG H1 pour les pullbacks
- Pullback sur EMA 20 dans un canal = Retour au CE d'un OB ou FVG → Entrée A++
- Canal + BOS réguliers = SOD STRONG_DISTRIBUTION → 100% sizing

### 1.3 État 3 : TRADING RANGE (Range)
**Définition :** Oscillation entre support et résistance sans direction claire.

**Caractéristiques :**
- EMA 20 horizontale
- Bougies qui se chevauchent (overlaps > 60%)
- Volumes décroissants
- Pattern : "Barb Wire" (fil barbelé)

**Action Bot :**
- Scalper uniquement aux extrêmes du range (S/R)
- JAMAIS de breakout trade (80% des breakouts échouent en range)
- Attendre le vrai breakout avec volume x2

**Synergie ICT — KB5 :**
- Trading Range = MMXM Phase 1 Accumulation ou Phase 4 Re-Accumulation
- Range = SOD ACCUMULATION → Position Size 0% (NO-TRADE)
- Si range entre EQL et EQH → BPR (Balanced Price Range) → Attendre breakout avec volume x2

---

## CHAPITRE 2 — ANATOMIE DES BOUGIES

### 2.1 Trend Bar (Bougie de Tendance)
La bougie la plus importante en Price Action.

**Critères STRICT (requis pour D1/H4) :**
- Corps > 65% du range H-L
- Mèche haute < 10% du range
- Corps > 70% ATR(14)
- Clôture dans les 70% supérieurs du range (bullish)

**Critères LOOSE (acceptable H1/M15 si confirmé HTF) :**
- Corps > 50% du range
- Direction claire (Close > Open)
- Corps > 50% ATR(14)

**Synergie ICT — KB5 :**
- Trend Bar = Bougie de Displacement ICT → Crée un FVG si espace avec les mèches adjacentes
- Trend Bar sur OB = Signal Bar + OB confluence → Score +20 pts
- 3 Trend Bars consécutives sans pullback = Micro-Gap / Volume Imbalance série

### 2.2 Signal Bar (Bougie de Signal)
Annonce un retournement ou une continuation sur un niveau clé.

**Critères pour Signal Bar Bullish de qualité :**
- Low touche ou perfore le niveau de support
- Mèche inférieure > 40% du range (rejet fort)
- Corps haussier (Close > Open)
- Close dans le tiers supérieur de la bougie
- Close > support + 30% du range

**Quantification du rejet :**
- Mèche 40-60% du range = Rejet Normal
- Mèche > 60% du range = Rejet Fort (A++)
- Pas de mèche = Pas de Signal Bar (bougie de tendance)

**Synergie ICT — KB5 :**

| Signal Bar sur... | Équivalent ICT | Score Bonus |
|------------------|----------------|-------------|
| OB Bullish | Signal Bar + OB = Confluence maximale | +15 pts |
| CE d'un FVG (.50) | Signal Bar + ENIGMA .50 | +10 pts |
| EQL (Equal Lows) | Signal Bar + SSL sweep = Turtle Soup | +20 pts |
| RDRB | Signal Bar sur zone retravaillée | +10 pts |
| Niveau .20 | Signal Bar + ENIGMA .20 | +15 pts |

### 2.3 Doji (Indécision)
- Corps < 10% du range
- Signification : Équilibre acheteurs/vendeurs
- Sur niveau clé = Signal de retournement potentiel
- En tendance = Alerte, mais continuation possible

**Synergie ICT — KB5 :**
- Doji dans un FVG = Indécision dans la zone institutionnelle → Attendre résolution
- Doji + VWAP plat + EMA 20 horizontale = SOD ACCUMULATION → Position size 0%
- Doji après Climax Bar = Début de la phase Canal MTR

### 2.4 Gap Bars & Micro-Gaps (Urgence Institutionnelle)

**Gap Bar :**
- Une bougie haussière dont le Low est >= EMA 20
- Signification : Marché trop pressé pour revenir à la moyenne
- Règle Bot : Ne jamais shorter une Gap Bar. Attendre 2 tentatives de retour mean.

**Micro-Gap :**
- Espace entre le CORPS de deux bougies consécutives
- Preuve de déséquilibre total entre offre et demande
- 3 micro-gaps consécutifs = Mouvement Parabolique (exit mode)

**Synergie ICT — KB5 :**
- Gap Bar = Volume Imbalance ICT (VI) → Corps non chevauchés = PD Array rang 9
- Micro-Gap série = Displacement fort → FVG probable sur le TF supérieur
- 3 Micro-Gaps = Parabolique → TERMINUS potentiel si + KZ + .00/.50

---

## CHAPITRE 3 — LEGS & PULLBACKS

### 3.1 Les Legs (Jambes de Tendance)
Un "leg" est un mouvement directionnel entre deux pivots.

**Caractéristiques d'un Leg Sain :**
- 3-8 bougies de tendance consécutives
- Mèches courtes (corps > 60% du range)
- Volume stable ou croissant
- Peu ou pas d'overlap entre bougies

### 3.2 Les 4 Types de Pullbacks
| Type | Profondeur | Volume Pullback | Action | Fiabilité |
|------|-----------|-----------------|--------|-----------|
| **One-Bar** | < 20% du leg | Décroissant | Acheter clôture de la Bar 2 | 80%+ |
| **Two-Bar** | 20-35% | Décroissant | Acheter test de la Bar 2 | 70%+ |
| **Shakeout** | 40-50% (piège) | Spike momentané | Acheter si volume revient à la normale | 65%+ |
| **Deep Pullback** | 50-70% | Décroissant | Attendre confirmation supplémentaire | 55% |

**Pullback Invalide (Piège) :**
- Profondeur > 70% → Probable inversion (MTR)
- Volume croissant pendant le pullback → Vente active (pas juste correction)
- EMA 20 cassée et retestée par en-dessous → Tendance en danger

### 3.3 Règle de Validation Pullback

```
VALID Pullback = TOUTES les conditions :
1. Depth < 50% du leg précédent
2. EMA 20 intacte (prix > EMA si trend bullish)
3. Volume décroissant pendant le pullback
4. Durée < 5 bougies
5. Pas de bougies larges baissières (pas de capitulation)

→ 4/5 conditions = Pullback acceptable
→ < 4 conditions = Probablement une inversion
```

**Synergie ICT — KB5 :**
- Pullback One-Bar sur FVG = One-Bar Pullback + FVG → Score +15 pts
- Pullback Two-Bar sur OB = Two-Bar + OB → Score +20 pts
- Shakeout dans SSL/EQL = Shakeout = Turtle Soup ICT → Boolean_Sweep_ERL = True → A++
- Deep Pullback vers OTE 70.5-79% = Grail Setup si dans Killzone → Score 100/100

---

## CHAPITRE 4 — BAR COUNTING (H1/H2/L1/L2)

### 4.1 Les Tentatives de Cassure
Chaque tentative de cassure d'un niveau est comptée :
- **H1** : Première tentative de cassure haussière (souvent échoue = piège)
- **H2** : Deuxième tentative consécutive haussière (fiabilité 70%+)
- **L1** : Première tentative de cassure baissière
- **L2** : Deuxième tentative baissière consécutive

**L'H2/L2 est le setup d'entrée de continuation le plus fiable de Brooks.**

### 4.2 Synergies ICT — KB5

```
H2 Bullish en contexte ICT :
- H2 qui se forme DANS un FVG bullish       → Score +20 pts (confluence maximale)
- H2 qui se forme DANS un OB bullish        → Score +15 pts
- H2 sur un niveau .20 (ENIGMA)             → Score +15 pts (A++)
- H2 dans une Killzone active               → Score +10 pts
- H2 + Cascade Double (H4+H1)              → Score +15 pts supplémentaires

H2 Raté (H2 qui échoue) :
- = Signal de retournement PA
- = Equivalent MSS ICT
- → Boolean_Sweep_ERL devient True
- → Chercher FVG/OB dans sens opposé
```

### 4.3 H3 — Troisième Tentative (Règle KB5)

```
H3 dans une tendance forte :
- 3ème tentative de cassure = Signal de RÉDUCTION
- Fiabilité chute à 45%
- Règle Bot : Si H3 détecté → Réduire size à 50%
- Exception : Si H3 + Cascade Triple ICT → Conserver 100% size

L3 dans une tendance baissière forte :
- Même logique inversée
```

---

## CHAPITRE 5 — MEASURED MOVES

### 5.1 Le Principe du Measured Move
Quand le marché éclate d'un range ou complète un leg, le prochain move est souvent égal au premier.

**Formule :**

```
Target Measured Move (MM) = Point de départ du leg 2 + Amplitude du leg 1

Exemple :
- Leg 1 : 1.0800 → 1.0900 (100 pips)
- Range/Pullback : 1.0900 → 1.0850
- MM Target : 1.0850 + 100 pips = 1.0950
```

**Probabilités par TF :**
| TF | Fiabilité Measured Move | Tolérance |
|----|------------------------|-----------|
| D1 | 72% | ±15 pips |
| H4 | 68% | ±8 pips |
| H1 | 63% | ±5 pips |
| M15 | 58% | ±3 pips |
| M5 | 52% | ±2 pips |

### 5.2 Règle du Terminus — Synergie PA + ICT (KB5)

```
TERMINUS = Sortie 100% garantie — Signal A++

Conditions (3/3 OBLIGATOIRES) :
1. Measured Move PA atteint (ou à ±5 pips près)
2. Killzone ICT active (London Open ou NY Open)
3. Niveau algorithmique .00 ou .50 touché (ENIGMA)

Conditions Bonus (augmentent la confiance) :
+ FVG HTF rempli dans la zone
+ ERL purgé (BSL ou SSL)
+ Std Dev ICT -2.0 ou -2.5 atteinte

→ TERMINUS confirmé = EXIT 100% immédiat
→ Log le trade comme "TERMINUS COMPLET"
```

---

## CHAPITRE 6 — MICRO-STRUCTURES

### 6.1 Micro-Canaux (Trendlines Serrées)

```
Si prix dans un micro-canal (3-5 bougies dans trendline serrée) :
- Ne pas entrer dans le sens du canal (épuisement proche)
- Le breakout du canal = Premier signal de correction
- Breakout + retour dans le canal = "Micro-Canal Trap"
```

**Synergie ICT — KB5 :**
- Micro-Canal Trap = CISD en sens inverse dans une Macro → Entrée anticipée
- Breakout du micro-canal avec Displacement = MSS + FVG créé → Signal A

### 6.2 Patterns Inside/Outside Bars

**Inside Bar (iOi) :**
- Corps < corps de la bougie précédente (indécision)
- Si après un long move = Compression avant explosion
- Breakout de l'Inside Bar = Signal de continuation

**Outside Bar :**
- Corps englobe le range de la bougie précédente
- Signifie : Tentation des deux camps, puis décision
- Suivi d'une clôture forte = Signal fort dans cette direction

**Synergie ICT — KB5 :**
- Inside Bar dans un OB = Compression dans la zone institutionnelle → Breakout explosive attendu
- Outside Bar sur EQL/EQH = Sweep de liquidité + retournement = Turtle Soup A++
- Inside Bar + CISD = Entrée anticipée KB5

---

## CHAPITRE 7 — ALWAYS IN (LOGIQUE DE DIRECTION)

### 7.1 La Question Fondamentale
"Si je n'étais pas dans le marché en ce moment, devrais-je acheter ou vendre PAR PEUR DE RATER un grand mouvement ?"

### 7.2 Basculements AIL/AIS

**Basculement vers Always In Long (AIL) :**
- Trend Bar bullish qui casse la trendline baissière ET l'EMA 20
- Après un Double Bottom avec volume décroissant sur le 2ème creux
- Le marché ne retourne pas sous le point de cassure dans les 5 bougies suivantes

**Basculement vers Always In Short (AIS) :** Inverse miroir.

**Maintien du Statut :**
- AIL maintenu tant que le prix ne forme pas un signal inverse équivalent
- Ne jamais sortir d'un AIL parce que "le marché semble suracheté"
- Sortir uniquement sur signal inverse qualifié

**Synergie ICT — KB5 :**
- AIL = Biais Daily Bullish ICT + SOD STRONG_DISTRIBUTION → 100% size autorisé
- Basculement AIL → AIS = MSS HTF (D1/H4) + Boolean_Sweep_ERL = True
- AIL annulé si : Premium T-20 atteint OU MMXM Phase 2 Manipulation détectée sur HTF

---

## CHAPITRE 8 — MTR (MAJOR TREND REVERSAL)

### 8.1 Les Signaux du MTR
Un MTR est confirmé quand au moins 3 de ces signaux sont présents :
1. Double Top ou Double Bottom (EQH/EQL)
2. Brisure de la trendline principale (minimum 5 points de contact)
3. Volume décroissant sur le dernier high/low (divergence)
4. Clôture sous l'EMA 20 sur D1 (H4 pour intraday)
5. CHoCH confirmé sur HTF (D1)

### 8.2 La Fin de Tendance (Climax)

```
Séquence MTR Classique :
1. Climax Bar : Bougie géante (> ATR x2) = Épuisement
2. Zone de Repos : Micro-canal lent dans le sens du climax
3. La Cassure du Canal : = Signal MTR le plus fiable

Règle Bot CRITIQUE :
- Ne JAMAIS shorter/longer contre un Climax immédiat
- Attendre la transition Canal puis la cassure du canal
- Confirmation H2/L2 sur HTF avant d'entrer contre la tendance
```

**Synergie ICT — KB5 :**

| Signal PA | Équivalent ICT | Confluence |
|----------|----------------|-----------|
| MTR sur D1 | MSS D1 + Displacement | A++ si Boolean_Sweep_ERL = True |
| Double Top (EQH) | BSL sweep + Judas Swing | ✅ Turtle Soup inverse |
| Climax Bar | Venom Phase 2 (indices) | ✅ Pour NQ/ES uniquement |
| Canal post-Climax | MMXM Phase 4 Re-Accumulation | ⚠️ Surveiller direction HTF |
| Cassure Canal | CISD sur M5/M15 dans Macro | ✅ Entrée anticipée |

---

## CHAPITRE 9 — TRAPPED TRADERS

### 9.1 Le Mécanisme des Traders Coincés
La liquidité est créée par les traders qui ont tort. Identifier où ils sont coincés = identifier d'où viendra le prochain mouvement.

**Les 3 Sources de Traders Piégés :**
1. **Breakout Buyers** : Ont acheté le breakout d'un niveau. Leurs stops sont juste sous ce niveau.
2. **Counter-Trend Sellers** : Ont shorté le trend. Leurs stops sont au-dessus du dernier high.
3. **Range Traders** : Ont acheté/vendu aux extrêmes. Coincés si range éclate.

### 9.2 Règle d'Entrée sur Trapped Traders

```
Signal PA : Fakeout d'un Double Top (EQH ICT) → Shorts piégés
Entry PA : Dès que le prix repasse au-dessus des highs après le fakeout
(les shorts doivent couvrir → fuel du move haussier)
```

**Équivalences ICT complètes — KB5 :**

| Situation PA | Équivalent ICT | Action Bot | Score |
|-------------|----------------|-----------|-------|
| Trapped Shorts sur EQH | Turtle Soup (Sweep EQL + reversal haussier) | BUY après sweep | +20 pts |
| Trapped Longs sur EQL | Judas Swing (Sweep EQH + distribution baissière) | SELL après sweep | +20 pts |
| Trapped Breakout Buyers | Failed BO + Anti-Inducement | ⛔ NE PAS ENTRER | -50 pts |
| Trapped Range Sellers | BPR Breakout avec volume x2 | BUY si HTF confirme | +15 pts |

---

## CHAPITRE 10 — GAP BARS & MICRO-GAPS

### 10.1 Gap Bars
**Définition :** Bougie dont le Low est > EMA 20 (bullish) ou High < EMA 20 (bearish).

**Signification :** Le marché refuse de revenir à la moyenne = urgence institutionnelle.

**Règle :**
- 1 Gap Bar = Tendance forte, continuation probable
- 3 Gap Bars consécutives = Tendance PARABOLIQUE, exit préparation
- Ne jamais shorter une série de Gap Bars

### 10.2 Micro-Gaps
**Définition :** Espace entre le corps d'une bougie et le corps de la suivante.

**Signification :** Déséquilibre total acheteurs/vendeurs.

**Statistiques Brooks :**
- 1 Micro-Gap : Continuation 65%
- 2 Micro-Gaps consécutifs : Continuation 75%
- 3+ Micro-Gaps : Alerte Parabolique, préparer sortie partielle

**Synergie ICT — KB5 :**
- Micro-Gap = Volume Imbalance (VI) — PD Array rang 9
- Série de 3 Micro-Gaps = Mouvement Parabolique → TERMINUS si + .00/.50 + Killzone
- Gap Bar dans une Killzone = Displacement ICT → FVG probable au TF supérieur

---

## CHAPITRE 11 — NARRATION BAR-PAR-BAR

### 11.1 Le Principe de Narration
Chaque bougie a une "signification" dans le contexte de la séquence. Le bot doit "lire" cette séquence comme un scénario.

**Exemple de Narration :**

```
Bougie 1 : Trend Bar haussière          (Urgence acheteurs)
Bougie 2 : Doji                          (Premiers vendeurs résistent)
Bougie 3 : Inside Bar                    (Pause, indécision)
Bougie 4 : Trend Bar baissière + volume (Les vendeurs prennent le contrôle)

Narration : "Les acheteurs ont poussé mais rencontrent une résistance.
             Les vendeurs commencent à dominer. Biais change de AIL → Neutre."
```

### 11.2 Intégration ICT/PA — Narration Double (KB5)

La narration double est le mécanisme central de lecture KB5 : **PA décrit ce qui se passe visuellement, ICT explique pourquoi algorithmiquement.**

```
EXEMPLE 1 — Judas Swing Confirmé par PA :
  ICT dit  : "Phase 3 = Accélération Fausse du Judas Swing"
  PA dit   : "Gap Bar haussière + Inside Bar = Compression avant reversal"
  Narration: "PA confirme la Manipulation ICT → PIÈGE IDENTIFIÉ"
  Action   : Attendre la bougie de reversal (Phase 4 ICT) = MSS + Signal Bar

EXEMPLE 2 — Continuation Confirmée :
  ICT dit  : "FVG H1 frais dans Killzone NY Open"
  PA dit   : "Two-Bar Pullback sur EMA 20, volume décroissant"
  Narration: "Pullback sain dans zone institutionnelle = Entrée A++"
  Action   : Entrer au CE du FVG sur Signal Bar haussière — Score +35 pts

EXEMPLE 3 — Conflit PA/ICT :
  ICT dit  : "OB H4 bullish frais"
  PA dit   : "Bougies larges baissières avec clôtures basses (capitulation)"
  Narration: "Structure PA contredit OB ICT → Réduire size à 50%"
  Action   : Attendre Signal Bar + volume décroissant avant entrée
```

### 11.3 Tableau de Convergences PA/ICT — Matrix de Confluence

| Signal PA | Signal ICT | Score Total | Action |
|-----------|-----------|-------------|--------|
| Signal Bar sur OB | OB A++ (5/5 critères) | 100/100 | EXÉCUTION A++ |
| H2 dans FVG | FVG FRAIS + Killzone | 95/100 | EXÉCUTION A++ |
| Signal Bar sur EQL + Rejet | SSL Sweep + MSS | 95/100 | EXÉCUTION A++ |
| Measured Move + .50 | Std Dev -2.0 + CE FVG | 90/100 | EXÉCUTION A++ |
| Pullback EMA + H2 | OB H4 + Cascade D1+H4 | 95/100 | EXÉCUTION A++ |
| MTR D1 | MSS D1 + Boolean_ERL=True | 90/100 | EXÉCUTION A++ |
| Signal Bar seule | Pas de zone ICT | 40/100 | INTERDIT |
| H2 sans zone | Hors Killzone | 35/100 | INTERDIT |

---

## CHAPITRE 12 — INTERMARKET ANALYSIS

### 12.1 Les 5 Piliers Intermarket
| Pilier | Asset | Corrélation EUR/USD | Règle Bot |
|--------|-------|-------------------|-----------|
| 1 | **DXY** | Inverse -0.85 | DXY haussier = NE PAS acheter EUR |
| 2 | **Yields 10Y** | Inverse -0.70 | Yields montent = USD attractif = EUR baisse |
| 3 | **GBP/USD** | Positive +0.80 | GBP/USD bearish ET EUR bullish = Conflit. Réduire. |
| 4 | **SPX (Risk Sentiment)** | Positive +0.65 | SPX bearish = Risk-off = EUR/AUD sous pression |
| 5 | **Copper/AUD** | Positive +0.70 | Copper baisse + AUD bullish = Conflit. Pass. |

### 12.2 Scoring Intermarket

```
Tous les 5 piliers alignés     : +20 pts bonus au score global
3-4 piliers alignés            : 0 (neutre)
1-2 piliers en conflit         : -15 pts
3+ piliers en conflit          : -30 pts (souvent PASS)
```

**Synergie ICT — KB5 :**
- Piliers alignés = SMT Divergence alignée → Score Section 9.1 de l'encyclopédie ICT
- DXY haussier + EUR/USD bearish = Confirme Weekly Template Classic Bearish
- SPX bearish + VIX↑ = Venom Model activable sur NQ/ES (Section 5.3 ICT)

---

## CHAPITRE 13 — CALENDRIER ÉCONOMIQUE

### 13.1 Protocole Pre-News

```
T-60 min : Réduire taille de position à 50%
T-30 min : Réduire à 25% ou fermer trades < 30 pips
T-15 min : FREEZE total (pas de nouvelles entrées)
T-0      : Observer (Chaos Phase)
T+5 min  : Possible entrée limite seulement (pas market)
T+30 min : Retour au trading normal
```

### 13.2 La Règle du Surprise Factor

```
Si Actual > Expected par > 2 écarts-types :
  → Mouvement de 150-500 pips attendu
  → Entrée sur retest du premier FVG post-news
  → Cible : prochain niveau ENIGMA (.00/.50)

Si Actual ≈ Expected :
  → Peu d'impact. Reprendre le trading habituel après T+15 min.
```

---

## CHAPITRE 14 — PULLBACK TAXONOMY (7 Types)

| Type | Depth | Volume | Durée | Fiabilité | Action |
|------|-------|--------|-------|-----------|--------|
| **One-Bar** | < 20% | Décroissant | 1 bougie | 80%+ | Entrer bar suivante |
| **Two-Bar** | 20-30% | Décroissant | 2 bougies | 75% | Entrer bar 3 |
| **Multi-Bar** | 30-50% | Décroissant | 3-7 bougies | 65% | H2/L2 requis |
| **Deep Pullback** | 50-70% | Décroissant | Variable | 55% | Confirmation H2 requise |
| **Shakeout** | 40-60% | Spike bref | Court | 60% | Entrer si volume normalise |
| **Fake Reversal** | > 50% | Croissant | Bref | Dangereux | Attendre re-test |
| **Accumulation** | Horizontal | Décroissant | Long | Variable | No-trade. Wait breakout |

**Synergies ICT par type de pullback — KB5 :**
- **One-Bar + FVG H1** : Score +25 pts → Entrée au CE du FVG
- **Two-Bar + OB H4** : Score +20 pts → Entrée au CE de l'OB
- **Shakeout + SSL Sweep** : Turtle Soup → Score +20 pts → Boolean_Sweep_ERL = True
- **Deep Pullback + OTE 70.5-79%** : Grail Setup si dans Killzone → Score 100/100
- **Fake Reversal** : = Anti-Inducement → ⛔ NE PAS ENTRER

---

## CHAPITRE 15 — RÈGLES D'EXCLUSION ABSOLUES

Ne jamais utiliser Price Action dans ces contextes :

1. **Trading Range Indéfinissable** : Overlaps > 60%, VWAP horizontal, ATR < 50% normal
2. **Pre-News < 30 minutes** : Haut impact (NFP, FOMC, CPI) → Score -50 pts automatique
3. **EMA 20 Violemment Cassée** : Corps > ATR×1.2 au-delà de la EMA, volume ×1.5 → Changer de logique
4. **Gaps Overnight Contre-Tendance** : Gap > 50% du leg précédent dans le sens opposé
5. **Série de 5 Échecs Signal Bar** : Le marché a perdu sa confluence → Pause forcée
6. **SOD = MANIPULATION (ICT)** : ATR×2, volume×3 → ⛔ FREEZE Anti-Inducement
7. **Boolean_Sweep_ERL = False** : Aucun signal PA n'est valide sans ERL purgé

```python
def pa_exclusion_check(market_state):
    """
    Retourne True si le trading PA est AUTORISÉ
    Retourne False + raison si INTERDIT
    """
    if market_state["overlaps_pct"] > 60:
        return False, "RANGE_INDEFINISSABLE"
    if market_state["minutes_to_news"] < 30 and market_state["news_impact"] >= 8:
        return False, "PRE_NEWS_FREEZE"
    if market_state["ema_break_force"] > 1.2:
        return False, "EMA_VIOLENTEMENT_CASSEE"
    if market_state["consecutive_signal_failures"] >= 5:
        return False, "SERIE_ECHECS_SIGNAL_BAR"
    if market_state["sod"] == "MANIPULATION":
        return False, "SOD_MANIPULATION_FREEZE"
    if not market_state["boolean_sweep_erl"]:
        return False, "ERL_NON_PURGE"
    return True, "PA_AUTORISE"
```

---

## CHAPITRE 16 — SETUPS DE FIN DE TENDANCE

### 16.1 Final Flag (Le Dernier Drapeau)

```
Conditions :
- Tendance étendue de 3-5 legs
- Dernière contraction (flag tight)
- Volume décroissant dans le flag

Signal MTR :
- Breakout raté du flag (rentre dans le flag)
- Ou breakout + immédiate reversal avec volume
→ Exit 100%. Préparer entrée inverse.
```

### 16.2 Climax + Channel (La Signature de Fin)

```
Séquence :
1. Climax Bar (bougie 2-3x ATR) = Épuisement visible
2. La TRANSITION : Micro-canal lent dans le sens du climax (pas de pullback)
3. La Cassure du Canal = Signal MTR le plus fiable de Brooks

Règle Bot :
IF Climax_Detected THEN
   disable_all_entry(direction=climax_direction)
   wait_for_canal_formation(min_candles=5)
   enter_on_canal_break(confirmation="H2_or_L2")
```

**Synergie ICT — KB5 :**
- Final Flag = MMXM Phase 3 fin de Distribution → Chercher SSL/BSL pour entrée inverse
- Climax Bar = Std Dev -3.0 ICT atteinte → TERMINUS POTENTIEL
- Canal post-Climax = MMXM Phase 4 Re-Accumulation → Surveiller HTF pour nouveau biais

---

## CHAPITRE 17 — SYNERGIES ICT/PA — MATRICE COMPLÈTE KB5

### 17.1 Table de Conversion Universelle PA ↔ ICT

| Concept PA (Brooks) | Concept ICT Équivalent | Force Combinée |
|---------------------|----------------------|----------------|
| Trend Bar | Displacement / Bougie FVG | ★★★★★ |
| Signal Bar | Entry Candle sur OB/FVG | ★★★★★ |
| H2 dans FVG | Grail Setup | ★★★★★ |
| MTR D1 | MSS D1 + Boolean_ERL | ★★★★★ |
| Double Bottom + volume décroissant | SSL Sweep + Turtle Soup | ★★★★★ |
| Shakeout | Judas Swing Phase 2 | ★★★★☆ |
| Final Flag échoué | MMXM Phase 3 fin | ★★★★☆ |
| Fake Reversal | Anti-Inducement | ★★★★☆ |
| Micro-Gap série | Volume Imbalance / FVG | ★★★☆☆ |
| Inside Bar dans range | BPR / Accumulation | ★★★☆☆ |
| Climax Bar | Std Dev -3.0 dépassée | ★★★☆☆ |
| Breakout du canal | CISD sur M5/M15 | ★★★☆☆ |

### 17.2 Règle d'Or de Lecture Combinée

```
RÈGLE FONDAMENTALE KB5 :
- ICT dit QUOI cibler (liquidité, déséquilibre, DOL)
- PA dit QUAND entrer (bougie de signal, rejet, H2)
- La confluence des deux = Signal A++

Sans PA confirmant ICT → Attendre
Sans ICT encadrant PA → Score insuffisant (< 65)
Les deux ensemble → EXÉCUTION AUTORISÉE
```

---

## RÉFÉRENCES INTER-FICHIERS KB5

| Concept | Fichier source | Usage |
|---------|---------------|-------|
| Définitions ICT complètes (FVG, OB, MSS...) | `03_ICT_ENCYCLOPEDIE_v5.md` | Zones institutionnelles |
| Matrice Fractal/Spécifique | `01_CADRE_FRACTAL_SPECIFIQUE.md` | Applicabilité par TF |
| Pipeline Top-Down | `02_PYRAMIDE_ANALYSE.md` | Ordre d'analyse |
| Règles par instrument | `05_INSTRUMENTS_SPECIFIQUES.md` | Forex / Indices / BTC |
| Scoring final + veto | `07_MOTEUR_DECISION.md` | Décision d'exécution |

---

*Bible Price Action v4.0 — KB5 Sentinel Pro — 2026-03-11*
*Source : PA Bible v3.0 + Al Brooks 2026 + Extensions KB5*
*Synergies ICT/PA + Narration Double + Terminus enrichi + 7 Règles d'exclusion*
*Gouvernance : 03_ICT_ENCYCLOPEDIE_v5.md | Moteur : 07_MOTEUR_DECISION.md*
