---
version: "2.0"
type: "glossaire"
last_updated: "2026-03-11"
description: "Vocabulaire officiel KB5 — Mise à jour complète avec termes nouveaux."
---

# 📖 GLOSSAIRE UNIFIÉ v2.0 — SENTINEL PRO KB5
## Source Unique de Vérité Terminologique

> RÈGLE ABSOLUE : Ce glossaire est la seule référence acceptée.
> Tout autre terme pour le même concept est une erreur de synchronisation.
> Le bot ne connaît que les termes définis ici.

---

## A

**AIL** — Always In Long
État de marché où la direction dominante est haussière.
Si le bot n'était pas dans le marché, il achèterait immédiatement.

**AIS** — Always In Short
État inverse. Direction dominante baissière.

**AMD** — Accumulation-Manipulation-Distribution
Le modèle cyclique fondamental du Power of 3. Aussi appelé Power of 3.

**Anti-Inducement**
Règle absolue : le bot IGNORE tout signal CHoCH, MSS, FVG
tant que Boolean_Sweep_ERL = False.

**Asian Range**
High et Low de la session asiatique (20h00-00h00 EST).
Zone de liquidité à purger par Londres ou NY.
Asian_Range_High → BSL. Asian_Range_Low → SSL.

**ATR** — Average True Range
Mesure de volatilité de référence sur 14 périodes.

---

## B

**BISI** — Buy-Side Imbalance / Sell-Side Inefficiency
Zone où l'offre (sell-side) est insuffisante → le prix monte rapidement.
Équivalent ICT 2022 d'un FVG haussier avec contexte directionnel.

**Boolean_Sweep_ERL**
Variable globale d'état True/False.
Devient True uniquement après qu'un niveau de liquidité externe ERL a été purgé.
Garde absolu du bot.

**Boolean_Sweep_IRL**
Variable identique pour la liquidité interne.

**BPR** — Balanced Price Range
Zone de 20 bougies avec hauts/bas équilibrés où Smart Money s'accumule discrètement.
Un breakout avec volume × 2 signale A++.

**Breaker Block**
Ancien Order Block invalide (le prix l'a traversé) qui se retourne
et agit comme zone inverse. Un OB bullish devenu Breaker = résistance.

**BSL** — Buy-Side Liquidity
Cluster de stop-loss acheteurs au-dessus des hauts.
L'algorithme monte pour les purger.

---

## C

**Cascade Fractale**
Phénomène où un concept ICT (FVG, OB, MSS) se confirme
simultanément sur plusieurs TF imbriqués.
FVG H1 dans FVG H4 dans FVG D1 = Cascade 3 niveaux = +35 pts.

**CBDR** — Central Bank Decision Range
Plage High-Low calculée entre 17h00-20h00 EST chaque jour.
Détermine si la journée du lendemain sera explosive (< 40 pips) ou normale (> 100 pips).
Applicable : FOREX uniquement.

**CE** — Consequent Encroachment
Le point médian exact (50%) d'un FVG ou d'un OB.
Point d'entrée optimal par excellence. Rang 1 de la PD Array Matrix.

**CHoCH** — Change of Character
Premier signe d'un changement de direction.
Cassure d'un swing mineur. Moins fort que le MSS.
Requiert validation anti-inducement.

**CISD** — Change in State of Delivery
Signal 2026. Changement du mode de livraison institutionnel.
Plus rapide que le MSS : détecté quand la clôture du corps
dépasse les corps des 2 bougies précédentes en cours de Macro.

**COT** — Commitment of Traders
Rapport hebdomadaire CFTC sur les positions des grandes institutions.
Publié chaque vendredi. Donnent le biais macro.
Applicable : FOREX et GOLD uniquement (MN/W).

---

## D

**Daily Bias**
Direction directionnelle valide pour la journée complète.
Doit être établi avant la première trade.
Sources : Weekly Template + État de livraison HTF.

**Dealing Range**
Zone de prix définie par le Lookback T-20 (20 dernières bougies Daily).
Structurée en Premium/Discount avec Equilibrium au centre.

**Displacement**
Mouvement de prix rapide et violent, signature de Smart Money.
Crée des FVG et réinitialise l'état de Livraison.

**DOL** — Draw on Liquidity
Cible logique du prochain mouvement de prix.
Toujours vers la liquidité non-purgée la plus proche.

**Dossier Paire**
Objet JSON produit par le pipeline d'analyse pour chaque paire/instrument.
Contient tous les outputs MN→W→D1→H4→H1→Scalp.
Transmis à l'agent trader après validation.

**DXY** — Dollar Index
Indice de la force du Dollar US.
Corrélation inverse -0.85 avec EUR/USD. Pilier 1 de l'Analyse Intermarket.

---

## E

**Equilibrium (EQ)**
Point médian exact du Dealing Range (50%).
Zone où la valeur est juste. Ni Premium, ni Discount.

**EQL** — Equal Lows
Deux ou plusieurs creux alignés horizontalement → SSL → liquidité baissière.
Cible algorithmique prioritaire.

**EQH** — Equal Highs
Deux ou plusieurs sommets alignés → BSL → liquidité haussière.
Cible algorithmique prioritaire.

**ERL** — External Range Liquidity
Liquidité en dehors du range : PDH, PDL, EQH, EQL, PWH, PWL.
Le sweep ERL déclenche Boolean_Sweep_ERL = True.

**IRL** — Internal Range Liquidity
Liquidité interne : FVG, CE d'OB, milieu de range.

---

## F

**Failed BO** — Failed Breakout
Un breakout qui réintègre le range.
Équivalent Price Action du Turtle Soup et du Flout.
Signal de retournement fort.

**Final Flag**
Dernière structure de congestion après un trend étendu (3-5 legs).
Le breakout raté de ce flag signal MTR Price Action.

**Flout Pattern**
Faux breakout institutionnel : faible volume + mèche longue.
L'algorithme attire les traders puis inverse immédiatement.
Conditions : Volume BAS + Wick > 40% du corps.

**FOMC** — Federal Open Market Committee
Décisions de taux 6×/an. Impact maximum sur DXY et paires USD.

**Fractal**
Qualificatif d'un concept ICT/PA applicable sur TOUS les timeframes.
Exemple : FVG, MSS, CHoCH, MMXM, OB, BSL/SSL.
Opposé de "Spécifique".

**Freshness**
Statut d'un PD Array (FVG, OB, etc.) :
- FRAIS : Jamais revisité. Score plein.
- MITIGÉ : Revisité 1 fois partiellement. Score -20%.
- REVISITÉ : Revisité 2+ fois. Score -50%.
- INVALIDE : Prix a clôturé au-delà. Supprimer.

**FVG** — Fair Value Gap
Espace vide entre la mèche haute de bougie[N-1] et la mèche basse de bougie[N+1].
"Dette" que l'algorithme doit combler. Force magnétique 10/10.

---

## G

**Grail Setup**
Le setup le plus puissant du Mentorship ICT.
Requiert 5 conditions simultanées :
1. ERL Sweep vérifié
2. MSS confirmé HTF
3. OTE entre 70.5-79%
4. FVG dans la Killzone
5. Dans le sens du Weekly Bias
Applicable : H4/H1 uniquement.

---

## H

**HTF** — Higher Time Frame
Tout timeframe supérieur au timeframe d'exécution.
Règle : Le biais HTF prime TOUJOURS sur le signal LTF.

---

## I

**IFVG** — Inverted Fair Value Gap
Un FVG qui a été comblé puis retourné.
Agit comme support/résistance inverse après mitigation complète.
Rang inférieur à l'OB dans la PD Array Matrix.

**IPDA** — Interbank Price Delivery Algorithm
L'algorithme de livraison de prix réel des marchés institutionnels.
Fonctionne sur des cycles de 20, 40 et 60 jours.

**IOF** — Institutional Order Flow
Confirmation que les institutions sont du même côté que le bot.
Signaux : Displacement + Volume croissant + Structure qui ne casse pas.

---

## J

**Judas Swing**
Manipulation caractéristique en 6 phases.
Phase 1-3 : Montée manipulatrice.
Phase 4 : Retournement.
Phase 5-6 : Distribution réelle.

---

## K

**Killzone**
Fenêtre temporelle d'activité institutionnelle haute.
- Asian KZ : 20h00-00h00 EST
- London KZ : 02h00-05h00 EST (03h00-05h00 focus)
- NY AM KZ : 07h00-11h00 EST (08h30-11h00 focus)
- NY PM KZ : 13h30-16h00 EST

---

## L

**Leg**
Mouvement directionnel complet entre deux pivots.
Une tendance saine = minimum 2-3 legs.

**LTF** — Lower Time Frame
Timeframe d'exécution. Règle : valider le signal LTF sur HTF avant d'entrer.

**Liquidity Void**
Espace sur le graphique sans transactions (pas de bougies).
L'algorithme doit combler ce vide.

**Lookback T-20**
Analyse des 20 dernières bougies journalières pour définir la Dealing Range.
EQ_T20 = (High_T20 + Low_T20) / 2

**LRLR** — Low Resistance Liquidity Run
Le prix glisse facilement vers une zone de haute liquidité sans résistance.
Signal d'accélération.

---

## M

**Magnetic Force Score**
Score 0-100 qui quantifie l'attraction d'un niveau.
≥ 85 = Entrée en confiance. < 40 = Ignorer.

**Macro ICT**
Fenêtre temporelle spécifique d'action algorithmique (voir liste 8 Macros).
Ne pas confondre avec "Macro économique".

**Mitigation Block**
Order Block partiellement visité (1-2 touches).
Moins fort qu'un OB frais. Plus fort qu'un Breaker.
Rang entre OB et Breaker dans la PD Array Matrix.

**MMXM** — Market Maker Buy/Sell Model
Le modèle canonique en 4 phases :
Accumulation → Manipulation → Distribution → Re-accumulation.
Fractal sur tous les TF.

**MSS** — Market Structure Shift
Cassure d'un swing MAJEUR confirmant le changement de direction HTF.
Plus fort que le CHoCH. Déclenche la validation d'un setup.

**MTR** — Major Trend Reversal
Retournement de tendance long terme (structure majeure).
Signal ultime de clôture de position et de changement de biais.

---

## N

**NFP** — Non-Farm Payroll
Publication emploi US le 1er vendredi du mois. Impact maximum.
Le bot gèle toute exécution 15 min avant.

**NDOG** — New Day Opening Gap
Écart entre clôture J-1 et ouverture J0. Zone magnétique prioritaire.

**NWOG** — New Week Opening Gap
Écart entre vendredi soir et lundi matin. Zone magnétique hebdomadaire.

---

## O

**OB** — Order Block
La dernière bougie opposée avant un grand mouvement directionnel.
Zone de rentrée institutionnelle.
Types : Bullish OB, Bearish OB, Breaker, Rejection, Mitigation.

**OTE** — Optimal Trade Entry
Entrée par retracement entre 61.8%-79% du dernier swing.
Niveaux Fibonacci : 0.705-0.79.

---

## P

**PA** — Price Action
Méthode d'analyse basée sur Al Brooks. Complémentaire ICT.

**PD Array** — Premium/Discount Array
Toute zone de prix institutionnelle (FVG, OB, Breaker, BPR, Suspension Block...)
qui agit comme support/résistance.

**PD Array Matrix** — Hiérarchie 2025
Ordre de priorité des PD Arrays :
1. Consequent Encroachment (CE) — 50% d'un FVG D1/H4 frais
2. Suspension Block (2025)
3. Breaker Block
4. Order Block (OB)
5. Fair Value Gap (FVG)
6. BPR (Balanced Price Range)
7. Rejection Block
8. NDOG / NWOG
9. Volume Imbalance (VI)

**POI** — Point of Interest
Zone marquée sur le graphique pour rentrée potentielle.

**Propulsion Block**
Cluster de 3-5 bougies consécutives dans le sens du mouvement,
créant un FVG sur leur passage.
Zone de rechargement institutionnel.
Rang entre BPR et Rejection Block dans la PD Array Matrix.

---

## Q

**Quarterly Theory (AMDX)**
Logique algorithmique divisant le temps (année/mois/semaine/session 90min)
en 4 quarts : Q1=Accumulation, Q2=Manipulation, Q3=Distribution, Q4=Continuation ou Reversal.
Applicable sur tous les TF (fractal).

---

## R

**RDRB** — Redelivered Rebalanced Price Range
Zone retravaillée 3+ fois par l'algorithme.
Agit comme barrière quasi-infranchissable à court terme.
Ne JAMAIS shorter sur un RDRB haussier.

**Rejection Block**
Variante d'OB : cluster de mèches dans une zone précise sans corps.
Résistance/Support de wicks.

---

## S

**SFP** — Swing Failure Pattern
Le prix dépasse brièvement un niveau clé puis clôture en dessous.
Confirmation d'un piège sur la liquidité.
Équivalent du Flout sur une seule bougie.

**SIBI** — Sell-Side Imbalance / Buy-Side Inefficiency
Zone où la demande (buy-side) est insuffisante → le prix descend rapidement.
Équivalent ICT 2022 d'un FVG baissier avec contexte directionnel.

**Silver Bullet**
Setup d'entrée précis sur FVG M5 pendant 3 fenêtres de temps :
10h00-11h00, 14h00-15h00, 20h00-21h00 EST.
Applicable : FOREX et GOLD uniquement (pas indices, pas BTC).

**SMT** — Smart Money Timing/Trap
Divergence inter-marché entre deux actifs corrélés.
EUR/USD monte mais GBP/USD baisse = SMT.
Signal de reversal fort.

**SOD** — State of Delivery
État actuel de la livraison de prix. 5 états :
ACCUMULATION, MANIPULATION, STRONG_DISTRIBUTION, WEAK_DISTRIBUTION, UNKNOWN.

**Spécifique**
Qualificatif d'un concept ICT/PA applicable uniquement sur certains TF
ou certains instruments.
Exemple : CBDR (D1/FOREX), Venom (M5/Indices), Silver Bullet (M5/FOREX+GOLD).
Opposé de "Fractal".

**SSL** — Sell-Side Liquidity
Cluster de stop-loss vendeurs sous les bas.
L'algorithme descend pour les purger.

**Suspension Block**
Nouveau PD Array 2025. Bougie unique suspendue entre deux Volume Imbalances.
Force supérieure à l'OB classique en zone Premium/Discount extrême.
Rang 2 dans la PD Array Matrix.

---

## T

**Terminus Point**
Règle de sortie 100%. Conditions :
Measured Move PA atteint AND Killzone ICT active AND Niveau .00/.50 touché.

**Trapped Traders**
Traders coincés du mauvais côté après un faux breakout.
Leur obligation de fermer leurs positions alimente le vrai mouvement.

**Turtle Soup**
Reversal sur breakout raté de EQL ou EQH.
Équivalent ICT du Failed BO Price Action.

---

## V

**Vacuum Block**
Zone de prix à très faible liquidité traversée rapidement.
Le prix y revient rarement et rapidement.

**Venom Model**
Modèle 2025 pour indices US (NQ/ES/YM).
Range 90min pré-open → Sweep 09h30 → FVG/BPR/MSS → Reversal violent.
Applicable : NQ/ES/YM UNIQUEMENT. Interdit sur FOREX, GOLD, BTC.

**Veto Descendant**
Règle KB5. Un TF supérieur peut interdire l'entrée sur un TF inférieur.
Exemple : Biais mensuel BEARISH + template weekly BULLISH = veto partiel.

**VI** — Volume Imbalance
Chevauchement entre le corps d'une bougie et les mèches des bougies adjacentes.
Moins fort qu'un FVG mais toujours magnétique.

---

## W

**Weekly Template**
Un des 5 profils de semaine canoniques ICT :
Classic Bullish (35%), Classic Bearish (30%), Bullish Reversal (15%),
Bearish Reversal (15%), Consolidation/Choppy (5%).

---

*GLOSSAIRE_v2.md — KB5 Sentinel Pro v2.0 — 2026-03-11*
*Source unique de vérité terminologique. Tous les termes non définis ici sont interdits.*
