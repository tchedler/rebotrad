---
version: "1.0"
type: "pipeline_analyse"
last_updated: "2026-03-11"
description: "Pipeline Top-Down complet MN→W→D1→H4→H1→Scalp — KB5 Sentinel Pro"
role: "Manuel opératoire du Département Analyse. Checklists + Sorties + Conditions de passage."
---

# 📐 PYRAMIDE D'ANALYSE v1.0 — SENTINEL PRO KB5
## Pipeline Top-Down : Du Grand au Petit

> **RÈGLE ABSOLUE :** Chaque niveau DOIT produire sa sortie avant de passer au suivant.
> Un niveau incomplet = blocage du niveau inférieur = NO-TRADE obligatoire.
> Le biais HTF prime TOUJOURS sur le signal LTF. Jamais de contournement.

---
> **DÉPENDANCE KB5 :** Ce fichier utilise `01_CADRE_FRACTAL_SPECIFIQUE.md` comme référence
> de gouvernance. Avant d'appliquer un concept à un niveau donné, vérifier sa nature
> FRACTAL/SPÉCIFIQUE via `FractalEngine.is_applicable(concept, timeframe, instrument)`.
 
## VUE D'ENSEMBLE DU PIPELINE

```
┌─────────────────────────────────────────────────────────┐
│  MONTHLY — Le Grand Architecte                          │
│  Fréquence : 1x/mois (1er jour du mois)                │
│  Produit   : {biais_macro, cot_score, ipda_60j, saison} │
└──────────────────────────┬──────────────────────────────┘
                           │ VETO possible ↓
┌──────────────────────────▼──────────────────────────────┐
│  WEEKLY — Le Stratège                                   │
│  Fréquence : Dimanche 18h NY                            │
│  Produit   : {template, dol_weekly, pwh, pwl, nwog}     │
└──────────────────────────┬──────────────────────────────┘
                           │ VETO possible ↓
┌──────────────────────────▼──────────────────────────────┐
│  DAILY — Le Planificateur                               │
│  Fréquence : 00h00 NY chaque jour                       │
│  Produit   : {daily_bias, sod, pdh, pdl, cbdr, ndog}    │
└──────────────────────────┬──────────────────────────────┘
                           │ VETO possible ↓
┌──────────────────────────▼──────────────────────────────┐
│  H4 — Le Tacticien                                      │
│  Fréquence : Chaque fermeture H4 (6x/jour)              │
│  Produit   : {structure_h4, zone_entree, ote_h4, smt}   │
└──────────────────────────┬──────────────────────────────┘
                           │ VETO possible ↓
┌──────────────────────────▼──────────────────────────────┐
│  H1 — L'Exécutant                                       │
│  Fréquence : Chaque fermeture H1                        │
│  Produit   : {mss_h1, fvg_h1, pa_signal, score_h1}      │
└──────────────────────────┬──────────────────────────────┘
                           │ Si score > 65 → SCALP WATCH
┌──────────────────────────▼──────────────────────────────┐
│  SCALP M15/M5/M1 — Le Sniper                           │
│  Fréquence : Temps réel (Killzone uniquement)           │
│  Produit   : {entry, sl, tp, rr, score_final, décision} │
└─────────────────────────────────────────────────────────┘
```

---

## NIVEAU 1 — MONTHLY : Le Grand Architecte

### Fréquence d'exécution
- **1 fois par mois** : le 1er jour ouvrable du mois
- **Révision partielle** : en cas d'événement macro exceptionnel (FOMC surprise, crise)

### Inputs requis
- Prix de clôture des 60 dernières bougies Daily
- Données COT Report (dernière publication CFTC vendredi précédent)
- Tableau de saisonnalité par devise
- Niveaux PDH/PDL/EQH/EQL du Monthly actuel

### Checklist Monthly
```
□ 1. COT REPORT
      → Calculer positions nettes Commercial vs Non-Commercial
      → Net Long > +50k       = COT_SCORE = BULLISH
      → Net Short > -50k      = COT_SCORE = BEARISH
      → Entre -50k et +50k    = COT_SCORE = NEUTRAL
      → INSTRUMENTS : FOREX et GOLD uniquement

□ 2. IPDA 60 JOURS
      → High_60j = Max(60 dernières bougies Daily)
      → Low_60j  = Min(60 dernières bougies Daily)
      → EQ_60j   = (High_60j + Low_60j) / 2
      → Si prix > EQ_60j → POSITION = PREMIUM_60J
      → Si prix < EQ_60j → POSITION = DISCOUNT_60J
      → Quel côté de la liquidité 60j n'a PAS été purgé ?

□ 3. SAISONNALITÉ
      → Q1 (Jan-Mar) / Q2 (Avr-Jun) / Q3 (Jul-Sep) / Q4 (Oct-Déc)
      → Lire table saisonnalité par devise (fichier 05_INSTRUMENTS)
      → SAISON_BIAS = BULLISH / BEARISH / NEUTRAL / UNCERTAIN

□ 4. NIVEAUX ALGORITHMIQUES MONTHLY
      → PDH_MN = High de la bougie mensuelle précédente → BSL
      → PDL_MN = Low de la bougie mensuelle précédente → SSL
      → EQH_MN = Equal Highs sur Monthly (2+ mois) → BSL cible
      → EQL_MN = Equal Lows sur Monthly (2+ mois) → SSL cible
      → Identifier le "Big Target" mensuel

□ 5. NARRATION MONTHLY
      → Formuler en 2-3 phrases :
         "EUR/USD est en [DISCOUNT/PREMIUM] mensuel.
          COT [HAUSSIER/BAISSIER/NEUTRE].
          Q[X] = favorable [devise]. Biais MACRO = [LONG/SHORT/NEUTRE]."
```

### Sortie Monthly (JSON)
```python
MONTHLY_OUTPUT = {
    "biais_macro":      "BULLISH",          # BULLISH | BEARISH | NEUTRAL
    "cot_score":        +45000,             # Valeur nette positions
    "cot_signal":       "BULLISH",          # BULLISH | BEARISH | NEUTRAL
    "ipda_60j": {
        "high_60j":     1.1200,
        "low_60j":      1.0500,
        "eq_60j":       1.0850,
        "position":     "DISCOUNT_60J",     # PREMIUM_60J | DISCOUNT_60J
        "liquidite_non_purgee": "BSL"       # BSL | SSL
    },
    "saisonnalite": {
        "trimestre":    "Q2",
        "biais_saison": "BULLISH_EUR",
        "confiance":    "HAUTE"             # HAUTE | MOYENNE | BASSE
    },
    "niveaux_MN": {
        "pdh_mn":       1.1200,
        "pdl_mn":       1.0500,
        "eqh_mn":       [1.1150, 1.1180],
        "eql_mn":       [1.0510, 1.0520],
        "big_target":   1.1200
    },
    "narratif_MN": "EUR/USD en Discount mensuel. COT haussier +45k. Q2 favorable EUR. Biais LONG macro.",
    "validite": "2026-04-01"               # Date de révision
}
```

### Conditions de VETO Monthly sur Weekly
```
VETO MONTHLY → WEEKLY si :
- biais_macro = BEARISH ET weekly_template = CLASSIC_UP → Score Weekly -30pts
- ipda_60j.position = PREMIUM ET biais = BULLISH → WARNING : risque Quarterly Shift
- cot_score NEUTRAL → Réduire confiance Weekly de 50%
```

---

## NIVEAU 2 — WEEKLY : Le Stratège

### Fréquence d'exécution
- **Dimanche soir 18h00-20h00 NY** (avant ouverture asiatique)
- **Révision** : Si lundi clôture hors du range attendu → réviser mardi matin

### Inputs requis
- MONTHLY_OUTPUT validé
- Prix des 20 dernières bougies Daily (T-20)
- PWH / PWL de la semaine précédente
- NWOG (New Week Opening Gap) : calculé lundi 00h NY

### Checklist Weekly
```
□ 1. IPDA 20 JOURS — DEALING RANGE HEBDOMADAIRE
      → High_T20 = Max(20 dernières bougies Daily)
      → Low_T20  = Min(20 dernières bougies Daily)
      → EQ_T20   = (High_T20 + Low_T20) / 2
      → Position_T20 = PREMIUM si prix > EQ_T20, DISCOUNT sinon
      → RÈGLE : Si PREMIUM → ne pas chercher longs aggressifs
      → RÈGLE : Si DISCOUNT → ne pas chercher shorts aggressifs

□ 2. NIVEAUX HEBDOMADAIRES
      → PWH = High de la semaine précédente (BSL)
      → PWL = Low de la semaine précédente (SSL)
      → NWOG = Gap lundi matin (zone magnétique)
      → EQH_W = Equal Highs hebdomadaires identifiés
      → EQL_W = Equal Lows hebdomadaires identifiés

□ 3. DOL DE LA SEMAINE
      → Côté non purgé de la semaine précédente ?
      → PWH touché la semaine dernière ? Non → BSL = DOL probable
      → PWL touché la semaine dernière ? Non → SSL = DOL probable
      → DOL_WEEKLY = BSL @ [prix] ou SSL @ [prix]

□ 4. WEEKLY TEMPLATE (probabiliste)
      → Appliquer l'algo de reconnaissance automatique :

      SI Position_T20 = DISCOUNT ET COT = BULLISH ET Biais_MN = BULLISH :
         → Template probable = CLASSIC_UP (probabilité ajustée +10%)

      SI Position_T20 = PREMIUM ET COT = BEARISH ET Biais_MN = BEARISH :
         → Template probable = CLASSIC_DOWN (probabilité ajustée +10%)

      SI PWH non purgé ET PWL non purgé ET Range semaine < 50 pips :
         → Template possible = CHOPPY (5%) → NO-TRADE semaine

      Probabilités de base :
         CLASSIC_UP      : 35%
         CLASSIC_DOWN    : 30%
         UP_DOWN_UP      : 20%
         DOWN_UP_DOWN    : 15%
         CHOPPY          : 5%

      → PIÈGE CRITIQUE : Template UP_DOWN_UP ou DOWN_UP_DOWN
         → Mercredi = FAUSSE direction. Ne pas trader mardi-mercredi.

□ 5. ALERTES HEBDOMADAIRES
      → Placer alerte si prix approche PWH ± 20 pips
      → Placer alerte si prix approche PWL ± 20 pips
      → Placer alerte sur NWOG si > 15 pips

□ 6. NARRATION WEEKLY
      → "Template probable = [TEMPLATE] ([%]).
         DOL principal = [BSL/SSL] @ [prix].
         Lundi = [accumulation/manipulation] attendu[e].
         Danger [jour] = possible Judas Swing [direction]."
```

### Sortie Weekly (JSON)
```python
WEEKLY_OUTPUT = {
    "template":         "CLASSIC_UP",
    "probabilite":      0.45,               # Probabilité ajustée contexte
    "dol_weekly":       "BSL",
    "dol_prix":         1.09250,
    "ipda_20j": {
        "high_t20":     1.09500,
        "low_t20":      1.07800,
        "eq_t20":       1.08650,
        "position":     "DISCOUNT_T20"
    },
    "niveaux_W": {
        "pwh":          1.09250,
        "pwl":          1.07980,
        "nwog": {
		"calcul": "Lundi 00h00 NY — Gap entre vendredi close et lundi open",
		"formule": "nwog_high = max(vendredi_close, lundi_open), nwog_low = min(vendredi_close, lundi_open)",
		"zone":    None,           # Calculé lundi matin 00h00 NY
		"pips":    None,           # Calculé lundi matin
		"valide":  False,          # Devient True si gap > 5 pips
		"magnetique": False        # Devient True si gap > 15 pips
	},                
        "eqh_w":        [],
        "eql_w":        [1.08050, 1.08020]
    },
    "piege_semaine":    "MERCREDI",         # Jour de piège selon template
    "alertes_W":        [
        {"niveau": 1.09230, "type": "BSL_APPROCHE"},
        {"niveau": 1.08000, "type": "PWL_APPROCHE"}
    ],
    "narratif_W":       "Classic Bullish. DOL=PWH@1.09250. Lundi=accumulation. Danger mardi AM.",
    "validite":         "2026-03-15"
}
```

---

## NIVEAU 3 — DAILY : Le Planificateur

### Fréquence d'exécution
- **00h00 NY chaque jour ouvrable** (avant session asiatique)
- **Calcul CBDR** : entre 17h00-20h00 EST le jour même (pour le lendemain)

### Inputs requis
- WEEKLY_OUTPUT validé
- Prix de clôture J-1 (PDH, PDL)
- Données MMXM sur Daily
- FVG et OB D1 frais (non revisités)

### Checklist Daily
```
□ 1. DAILY BIAS
      → Prix vs EQ_T20 (Lookback T-20)
      → Alignement avec Weekly Template
         Exemple : Template CLASSIC_UP + Lundi matin → Biais = BULLISH
      → State of Delivery D1 actuel :
         ACCUMULATION / MANIPULATION / STRONG_DISTRIBUTION / WEAK_DISTRIBUTION

□ 2. MMXM SUR DAILY
      → Phase actuelle du Market Maker Model sur D1 :
         Phase 1 : Accumulation (range étroit, VWAP plat, volume faible)
         Phase 2 : Manipulation (Sweep SSL ou BSL)
         Phase 3 : Distribution (vrai mouvement)
         Phase 4 : Re-accumulation
      → Judas Swing attendu aujourd'hui ?
         Si Weekly Template = CLASSIC_UP ET Lundi ou Mardi matin → Probable

□ 3. LIQUIDITÉ JOURNALIÈRE
      → PDH = High du jour précédent → BSL à surveiller
      → PDL = Low du jour précédent → SSL à surveiller
      → NDOG = Gap entre clôture J-1 et ouverture J0
         Si NDOG > 15 pips → Zone magnétique prioritaire
      → EQH_D1 = Equal Highs sur D1 (2+ jours)
      → EQL_D1 = Equal Lows sur D1 (2+ jours)

□ 4. PD ARRAYS D1 FRAIS
      → Scanner FVG D1 : freshness = FRAIS ou MITIGÉ uniquement
      → Scanner OB D1 : score ≥ 3/5, freshness = FRAIS
      → Scanner Breaker D1
      → Scanner Suspension Block D1
      → Appliquer PD Array Matrix pour prioriser
      → INTERDIRE zones INVALIDES ou REVISITÉES (3+ fois)

□ 5. CBDR (Central Bank Decision Range)
      → FOREX UNIQUEMENT
      → Calculé entre 17h00-20h00 EST
      → CBDR_Range = High(17h-20h) - Low(17h-20h)
      → Si CBDR < 40 pips → CBDR_Explosive = True
         → Lendemain : attendre Macros 3 et 5 uniquement
         → Attendre large move directionnelle
      → Si CBDR > 100 pips → CBDR_Normal = True
         → Lendemain : trading plan standard

□ 6. NARRATION DAILY
      → "Biais [HAUSSIER/BAISSIER].
         PDL @ [prix] = SSL.
         FVG D1 frais @ [zone].
         Judas Swing [baissier/haussier] probable en [London/NY AM].
         Distribution [haussière/baissière] vers PDH/PDL [prix]."
```

### Sortie Daily (JSON)
```python
DAILY_OUTPUT = {
    "daily_bias":       "BULLISH",
    "sod_d1":           "ACCUMULATION",
    "mmxm_phase":       "PHASE_2_MANIPULATION",
    "judas_swing":      True,
    "judas_direction":  "BEARISH_FIRST",    # Fausse direction = baissier d'abord
    "liquidite_D1": {
        "pdh":          1.08950,
        "pdl":          1.08120,
        "ndog":         {"zone": [1.08200, 1.08350], "pips": 15},
        "eqh_d1":       [],
        "eql_d1":       [1.08130, 1.08110]
    },
    "pd_arrays_D1": [
        {"type": "FVG", "zone": [1.08200, 1.08350], "ce": 1.08275,
         "freshness": "FRAIS", "score": 5},
        {"type": "OB",  "zone": [1.08150, 1.08250], "ce": 1.08200,
         "freshness": "FRAIS", "score": 4}
    ],
    "cbdr": {
        "range_pips":   28,
        "explosive":    True,
        "normal":       False
    },
    "narratif_D1":   "Biais HAUSSIER. PDL@1.0812=SSL. FVG D1@1.0820-35. Judas baissier London→dist. NY.",
    "alertes_D1":    [
        {"niveau": 1.08350, "type": "FVG_APPROCHE"},
        {"niveau": 1.08120, "type": "PDL_APPROCHE"}
    ]
}
```

---

## NIVEAU 4 — H4 : Le Tacticien

### Fréquence d'exécution
- **À chaque fermeture de bougie H4** (6 fermetures par jour)
- Uniquement si la paire est en mode ACTIVE (score Daily > 40)

### Inputs requis
- DAILY_OUTPUT validé + daily_bias
- Données structurelles H4 (swings, MSS, CHoCH)
- PD Arrays H4 (FVG, OB, Breaker, Suspension Block)

### Checklist H4
```
□ 1. STRUCTURE H4
      → Identifier la direction dominante H4 : HH/HL (Bullish) ou LH/LL (Bearish)
      → MSS H4 présent ? (Cassure swing majeur + Displacement)
      → CHoCH H4 ? (Avertissement uniquement)
      → Boolean_Sweep_ERL H4 = True ou False ?

□ 2. PREMIUM / DISCOUNT H4
      → Calculer EQ du dernier dealing range H4
      → Prix actuel vs EQ H4 :
         > EQ H4 = PREMIUM H4 → Zone de vente
         < EQ H4 = DISCOUNT H4 → Zone d'achat
      → RÈGLE : Discount H4 + Bullish Bias = chercher longs sur FVG/OB H4

□ 3. PD ARRAYS H4 (Hiérarchie PD Array Matrix)
      → FVG H4 frais : Consequent Encroachment = entrée idéale
      → OB H4 : score 0-5, freshness FRAIS requis
      → Suspension Block H4 : score +2 vs OB
      → Breaker Block H4 : si structure H4 invalidée
      → Appliquer Hiérarchie : CE > Suspension > Breaker > OB > FVG > VI
      → Calculer Cascade Fractale :
	  → FRESHNESS TRACKER inter-sessions :
         FRAIS     : Zone jamais touchée depuis sa création → Score plein
         MITIGÉ    : Touché 1 fois partiellement (prix entré mais pas clôturé dedans) → -20%
         REVISITÉ  : Touché 2 fois → Score -50%, surveiller invalidation
         INVALIDE  : Prix a clôturé AU-DELÀ de la zone → Supprimer immédiatement
         
         Règle : À chaque fermeture H4, mettre à jour le statut freshness
         de TOUS les PD Arrays actifs dans le dossier paire.
         Un PD Array INVALIDE NE DOIT JAMAIS être utilisé comme zone d'entrée.

         Est-ce que le PD Array H4 est DANS un PD Array D1 ?
         Si oui → Cascade_H4_D1 = True → +15 pts score

□ 4. OTE H4
      → Tracer Fibonacci sur le DERNIER swing H4
      → Zone OTE H4 = entre 61.8% et 79% du swing
      → OTE_H4_zone = [prix_min, prix_max]
      → Est-ce que la zone OTE H4 coïncide avec un PD Array H4 ? → Confluent

□ 5. SMT H4
      → Vérifier corrélation DXY H4 vs paire analysée
      → Si EUR/USD → comparer avec GBP/USD H4
      → Divergence = SMT signal → Score +10 pts
      → Alignement = confirmation → Score +5 pts

□ 6. ZONE D'ENTRÉE HTF
      → Définir la zone d'entrée prioritaire pour H1 :
         Zone = intersection de : OTE H4 + PD Array H4 + Discount H4
      → Cette zone sera transmise au niveau H1

□ 7. STATE OF DELIVERY H4
      → SOD_H4 = ACCUMULATION / MANIPULATION / DISTRIBUTION / WEAK / UNKNOWN
```

### Sortie H4 (JSON)
```python
H4_OUTPUT = {
    "structure_H4":     "BULLISH",
    "direction":        "HH_HL",
    "sweep_erl_h4":     True,
    "mss_h4":           "CONFIRMED",
    "premium_discount": "DISCOUNT_H4",
    "eq_h4":            1.08400,
    "pd_arrays_H4": [
        {"type": "FVG",  "zone": [1.08200, 1.08350], "ce": 1.08275,
         "freshness": "FRAIS", "score": 5, "cascade_d1": True},
        {"type": "OB",   "zone": [1.08150, 1.08250], "ce": 1.08200,
         "freshness": "FRAIS", "score": 4}
    ],
    "ote_h4":           {"zone": [1.08220, 1.08280], "confluent": True},
    "zone_entree_HTF":  [1.08200, 1.08350],
    "smt_h4":           "ALIGNED",
    "sod_h4":           "ACCUMULATION",
    "cascade_bonus":    15                  # Bonus si cascade H4+D1 confirmée
}
```

---

## NIVEAU 5 — H1 : L'Exécutant

### Fréquence d'exécution
- **À chaque fermeture de bougie H1**
- Uniquement si la paire est en zone_entree_HTF (prix dans la zone H4)

### Inputs requis
- H4_OUTPUT validé + zone_entree_HTF
- Données structurelles H1
- PA signal bars sur H1
- Killzone active ou non

### Checklist H1
```
□ 1. CONFIRMATION MSS H1
      → MSS H1 dans le sens du Daily Bias
      → Displacement présent (FVG créé par le MSS)
      → Boolean_Sweep_ERL H1 = True ?
      → MSS H1 DANS zone_entree_HTF → Confluence forte

□ 2. FVG H1 FRAIS
      → FVG H1 créé par le displacement post-MSS
      → Freshness = FRAIS obligatoire
      → CE H1 calculé = entrée OTE
      → Est-ce que ce FVG H1 est DANS zone H4 ? → Cascade H4+H1 = True → +15 pts

□ 3. VERDICT PA H1 (Voir 04_PRICE_ACTION_BIBLE_v4.md)
      → État du marché PA sur H1 :
         BREAKOUT / CANAL / TRADING_RANGE
      → Signal Bar présent sur FVG/OB H1 ?
         Mèche basse > 40% range = Rejet FORT (A++)
         Mèche basse 20-40% = Rejet NORMAL
         Pas de mèche = Pas de signal bar (invalide)
      → H2 ou L2 formé dans la zone ?
         H2 dans FVG H1 = confluent maximal
         L2 dans OB H1 = confluent maximal
      → Narration bar-par-bar H1 (3 dernières bougies)

□ 4. BAR COUNTING H1
      → Compter les tentatives H1/H2/L1/L2 sur le niveau
      → Trapped Traders identifiés ?
      → > 3 tentatives ratées = zone épuisée → NE PAS ENTRER

□ 5. KILLZONE H1
      → Sommes-nous dans une Killzone ?
         London : 02h-05h EST | NY AM : 07h-11h EST | NY PM : 13h30-16h
      → Macro ICT active ? (Macro 3 : 08h-12h ou Macro 5 : 14h-17h)
      → Hors Killzone → Score réduit de 30 pts

□ 6. SCORE PARTIEL H1
      → ICT Score  : MSS(20) + ERL_Sweep(20) + FVG_frais(15) + Zone_H4(15) = max 70
      → PA Score   : Signal_Bar(10) + H2L2(10) + PA_état(10) = max 30
      → Killzone   : Actif(+10), Hors KZ(-30)
      → Cascade    : H1_dans_H4(+15), H1_dans_H4_dans_D1(+35)
      → SCORE_PARTIEL_H1 = Σ tous les points

      Si SCORE_H1 > 65 → SCALP_WATCH = True → Passer au niveau M5
      Si SCORE_H1 ≤ 65 → Attendre ou NO-TRADE
```

### Sortie H1 (JSON)
```python
H1_OUTPUT = {
    "mss_h1":           "CONFIRMED",
    "displacement_h1":  True,
    "sweep_erl_h1":     True,
    "fvg_h1": {
        "zone":         [1.08250, 1.08330],
        "ce":           1.08290,
        "freshness":    "FRAIS",
        "dans_zone_h4": True
    },
    "pa_signal": {
        "type":         "SIGNAL_BAR_BULLISH",
        "rejection":    "FORT",             # FORT | NORMAL | ABSENT
        "h2_forme":     True,
        "etat_marche":  "CANAL_BULLISH"
    },
    "killzone":         "NY_AM",
    "macro_active":     3,
    "score_ict":        65,
    "score_pa":         25,
    "cascade_bonus":    15,
    "score_partiel":    105,                # Sera normalisé sur 100 dans moteur
    "scalp_watch":      True,
    "type_setup":       "GRAIL_PARTIEL"     # GRAIL | GRAIL_PARTIEL | STANDARD
}
```

---

## NIVEAU 6 — SCALP M15/M5/M1 : Le Sniper

### Fréquence d'exécution
- **Temps réel uniquement pendant une Killzone active**
- Activé uniquement si SCALP_WATCH = True (score H1 > 65)

### Inputs requis
- H1_OUTPUT validé + fvg_h1.ce comme zone cible
- Données M5 en temps réel
- Vérification Silver Bullet / CISD / Venom selon instrument

### Checklist Scalp
```
□ 1. SILVER BULLET CHECK (FOREX / GOLD)
      → Fenêtre 10h-11h EST (Silver Bullet 1) ?
      → Fenêtre 14h-15h EST (Silver Bullet 2) ?
      → Fenêtre 20h-21h EST (Silver Bullet 3) ?
      → FVG M5 créé dans cette fenêtre ?
      → Si Oui → Silver_Bullet_Active = True → Score +10 pts

□ 2. VENOM CHECK (INDICES NQ/ES/YM UNIQUEMENT)
      → Range 90min tracé (08h00-09h30 EST) ?
      → Sweep du range à 09h30 confirmé ?
      → FVG + CISD post-sweep identifiés ?
      → Si Oui → Venom_Active = True → Score +15 pts
□ 2-BIS. BRANCHE INSTRUMENT (OBLIGATOIRE)
      → Quel est l'instrument analysé ?

      SI INSTRUMENT = FOREX ou GOLD :
         → Utiliser Silver Bullet (fenêtres 10h/14h/20h)
         → Utiliser CISD M5/M1
         → Utiliser 1st Presented FVG si fenêtre 09h30-10h NY
         → NE PAS utiliser Venom

      SI INSTRUMENT = NQ / ES / YM :
         → Utiliser Venom Model (08h-11h uniquement)
         → Utiliser CISD M5/M1
         → NE PAS utiliser Silver Bullet
         → NE PAS utiliser CBDR

      SI INSTRUMENT = BTC :
         → Vérifier Funding Rate (positif > 0.01% = longs surchargés)
         → Vérifier Open Interest (hausse OI + hausse prix = confirmation)
         → Utiliser CISD M5/M1
         → NE PAS utiliser Silver Bullet, Venom, CBDR
         → Asian Range remplace CBDR comme range de référence

      SI INSTRUMENT = OIL (WTI/BRENT) :
         → Vérifier rapport EIA (mercredi 10h30 NY)
         → Utiliser CISD M5/M1
         → NE PAS utiliser Silver Bullet, Venom, CBDR

□ 3. CISD M5/M1
      → Clôture du CORPS de la bougie actuelle
         dépasse les CORPS des 2 bougies précédentes ?
      → Dans une Macro active ?
      → Si Oui → CISD_Confirmed = True → Entrée "early bird"
         (+10-20 pips avant les entrées MSS classiques)

□ 4. 1st PRESENTED FVG (09h30-10h00 NY)
      → Première fenêtre NY seulement
      → FVG créé sur M1 après 09h30 ET casse le range de la bougie 09h29 ?
      → Si Oui → First_FVG_Valid = True → Biais scellé 90% pour la journée

□ 5. PRIX D'ENTRÉE PRÉCIS
      → Prix exact = CE du FVG M5 (ou M1 si CISD)
      → Sur niveau ENIGMA (.20 ou .80) ? → Bonus +10 pts
      → Sur niveau .00 ou .50 → Attention : peut être TP du mouvement précédent

□ 6. SL PLACEMENT
      → SL = sous le Low COMPLET du FVG/OB (pas à l'intérieur)
      → Buffer minimum = spread + 2 pips
      → SL sur niveau ENIGMA si possible (améliore RR)

□ 7. TP PLACEMENT
      → TP1 = prochain niveau algorithmique (.00 ou .50)
      → TP2 = DOL journalier (PDH ou PDL)
      → TP3 = DOL hebdomadaire (PWH ou PWL)
      → R:R minimum = 2:1 obligatoire
      → R:R ≥ 3:1 → Score +5 pts

□ 8. SCORE FINAL → DÉCISION
      → Voir 07_MOTEUR_DECISION.md pour score complet et seuils de décision
```

### Sortie Scalp (JSON) — DOSSIER FINAL
```python
SCALP_OUTPUT = {
    "entry":            1.08290,            # CE du FVG M5
    "sl":               1.08100,            # Sous le Low complet OB + 2 pips
    "tp1":              1.08500,            # Prochain .50
    "tp2":              1.08950,            # PDH
    "tp3":              1.09250,            # PWH = DOL hebdomadaire
    "rr_tp1":           1.10,
    "rr_tp2":           3.47,
    "rr_tp3":           5.05,
    "type":             "LIMIT_ORDER",
    "silver_bullet":    True,
    "cisd":             True,
    "venom":            False,
    "enigma_entry":     False,
    "score_final":      87,                 # Calculé par 07_MOTEUR_DECISION
    "decision":         "EXECUTE_A++",      # Via 07_MOTEUR_DECISION
    "timestamp":        "2026-03-11 10:15 EST"
}
```

---

## FLUX TEMPOREL COMPLET

```
DIMANCHE 18h00-20h00 NY :
  → [Si 1er du mois] : Analyse MONTHLY → MONTHLY_OUTPUT
  → Analyse WEEKLY toutes les paires actives → WEEKLY_OUTPUT
  → Dossiers W1 prêts
  → Alertes PWH/PWL/NWOG placées

CHAQUE JOUR 00h00 NY :
  → Analyse DAILY toutes les paires actives → DAILY_OUTPUT
  → Mise à jour dossiers paires
  → Alertes PDH/PDL/NDOG placées
  → CBDR_précédent lu → influence taille position du jour

17h00-20h00 EST (chaque jour) :
  → Calcul CBDR pour la journée suivante

CHAQUE H4 (fermeture, 6x/jour) :
  → Si paire en mode ACTIVE :
     → Analyse H4 → H4_OUTPUT
     → Zone d'entrée HTF mise à jour

CHAQUE H1 (fermeture) :
  → Si paire en zone_entree_HTF :
     → Analyse H1 → H1_OUTPUT
     → Si score > 65 → SCALP_WATCH = True

TEMPS RÉEL (Killzone active uniquement) :
  → Si SCALP_WATCH = True :
     → Surveillance M5/M1 en continu
     → Dès Silver Bullet OU CISD OU 1st FVG détecté :
        → Score final calculé (07_MOTEUR_DECISION)
        → Si score ≥ 80 → Ordre envoyé automatiquement
        → Si score 65-79 → Alerte + attente confirmation
        → Si score < 65 → NO-TRADE, log raison
```

---

## CONDITIONS DE PASSAGE ENTRE NIVEAUX

```
MONTHLY → WEEKLY :
  Condition : MONTHLY_OUTPUT.biais_macro ≠ "NEUTRAL" OU contexte exceptionnel documenté
  Veto : biais_macro BEARISH + template CLASSIC_UP → pénalité -30 pts Weekly

WEEKLY → DAILY :
  Condition : WEEKLY_OUTPUT.template ≠ "CHOPPY"
  Veto : Template CHOPPY → NO-TRADE toute la semaine

DAILY → H4 :
  Condition : daily_bias ≠ "UNKNOWN" ET sod_d1 ≠ "UNKNOWN"
  Veto : sod_d1 = "MANIPULATION" → FREEZE (Anti-Inducement)

H4 → H1 :
  Condition : prix dans zone_entree_HTF ± 10 pips
  Veto : sweep_erl_h4 = False → NO-ENTRY (Anti-Inducement)

H1 → SCALP :
  Condition : score_partiel_h1 > 65
  Veto : score_partiel_h1 ≤ 65 → Attendre ou abandonner la paire

SCALP → ORDRE :
  Condition : score_final ≥ 80 (via 07_MOTEUR_DECISION)
  Veto : RR < 2:1 OU news < 30 min OU anti-inducement → BLOCAGE
```

---

*02_PYRAMIDE_ANALYSE.md — KB5 Sentinel Pro v1.0 — 2026-03-11*
*Pipeline opératoire officiel du Département Analyse*
