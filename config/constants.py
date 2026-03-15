"""
config/constants.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sentinel Pro KB5 — Constantes immuables
Source unique de vérité pour toute l'architecture.

NE JAMAIS MODIFIER sans mise à jour KB5 correspondante.
Toute valeur ici est justifiée par une règle KB5 documentée.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import MetaTrader5 as mt5
from enum import Enum


# ══════════════════════════════════════════════════
# SECTION 1 — TIMEFRAMES
# ══════════════════════════════════════════════════

TIMEFRAMES = {
    "M1":  mt5.TIMEFRAME_M1,
    "M5":  mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1":  mt5.TIMEFRAME_H1,
    "H4":  mt5.TIMEFRAME_H4,
    "D1":  mt5.TIMEFRAME_D1,
    "W":   mt5.TIMEFRAME_W1,
    "MN":  mt5.TIMEFRAME_MN1,
}

# Ordre d'analyse top-down KB5 — immuable
PIPELINE_ORDER = ["MN", "W", "D1", "H4", "H1", "M15", "M5", "M1"]

# Bougies à charger par TF
CANDLES_PER_TF = {
    "M1":  500,
    "M5":  500,
    "M15": 300,
    "H1":  200,
    "H4":  100,
    "D1":  60,
    "W":   52,
    "MN":  24,
}

# TF utilisés par type de trade
TIMEFRAMES_BY_TRADE_TYPE = {
    "SWING":    ["MN", "W", "D1"],
    "INTRADAY": ["H4", "H1"],
    "SCALP":    ["M15", "M5", "M1"],
}


# ══════════════════════════════════════════════════
# SECTION 2 — TYPES DE MARCHÉ
# ══════════════════════════════════════════════════

class MarketType(Enum):
    FOREX     = "FOREX"
    CRYPTO    = "CRYPTO"       # Marché 24h/24 7j/7 — pas de Killzone classique
    GOLD      = "GOLD"         # Volatilité extrême possible — ATR surveillé
    INDEX     = "INDEX"        # VIX surveillé — Venom Model actif
    COMMODITY = "COMMODITY"

PAIR_MARKET_TYPE = {
    # FOREX Majeurs (standard)
    "EURUSD": MarketType.FOREX, "GBPUSD": MarketType.FOREX,
    "USDJPY": MarketType.FOREX, "USDCAD": MarketType.FOREX,
    "AUDUSD": MarketType.FOREX, "NZDUSD": MarketType.FOREX,
    "USDCHF": MarketType.FOREX, "EURGBP": MarketType.FOREX,
    "EURJPY": MarketType.FOREX, "GBPJPY": MarketType.FOREX,
    # FOREX Majeurs — suffixe 'm' (Exness)
    "EURUSDm": MarketType.FOREX, "GBPUSDm": MarketType.FOREX,
    "USDJPYm": MarketType.FOREX, "USDCADm": MarketType.FOREX,
    "AUDUSDm": MarketType.FOREX, "NZDUSDm": MarketType.FOREX,
    "USDCHFm": MarketType.FOREX,
    # Métaux
    "XAUUSD":  MarketType.GOLD,      "XAUUSDm": MarketType.GOLD,
    "XAGUSD":  MarketType.COMMODITY,  "XAGUSDm": MarketType.COMMODITY,
    # Énergie
    "XTIUSD":  MarketType.COMMODITY,  "XBRUSD":  MarketType.COMMODITY,
    "USOILm":  MarketType.COMMODITY,  "UKOILm":  MarketType.COMMODITY,
    # Indices US
    "US30":    MarketType.INDEX,  "NAS100":  MarketType.INDEX,
    "US100":   MarketType.INDEX,  "SPX500":  MarketType.INDEX,
    "US500":   MarketType.INDEX,
    # Indices — suffixe 'm'
    "USTECm":  MarketType.INDEX,  "US500m":  MarketType.INDEX,
    "DE30m":   MarketType.INDEX,  "UK100m":  MarketType.INDEX,
    # Crypto
    "BTCUSD":  MarketType.CRYPTO,  "BTCUSDm": MarketType.CRYPTO,
    "ETHUSD":  MarketType.CRYPTO,  "ETHUSDm": MarketType.CRYPTO,
    # DXY
    "DXYm":    MarketType.FOREX,
}


# ══════════════════════════════════════════════════
# SECTION 3 — KILLZONES KB5
# Heures EST (UTC-5) — source ICT Mentorships
# Format : (h_debut, h_fin, nom, sizing_multiplier)
# sizing_multiplier = facteur appliqué à la taille
# de position de référence pendant cette Killzone
# ══════════════════════════════════════════════════

KILLZONES = [
    (2,  5,  "LONDON_OPEN",   1.0),   # Killzone principale — taille pleine
    (10, 12, "LONDON_CLOSE",  0.75),  # Mouvement secondaire — taille réduite
    (7,  9,  "NY_OPEN",       1.0),   # Killzone principale — taille pleine
    (13, 16, "NY_PM",         0.75),  # Session PM — taille réduite
    (19, 22, "ASIAN_OPEN",    0.5),   # Session Asie — faible liquidité
    (20, 0,  "SYDNEY_OPEN",   0.5),   # Sydney — faible liquidité
]

# Paires prioritaires par Killzone
# Le Gestionnaire de Paires utilise cette liste
# pour activer / mettre en veille les bons instruments
KILLZONE_PAIR_PRIORITY = {
    "LONDON_OPEN":  ["EURUSD", "GBPUSD", "EURGBP", "USDCHF", "XAUUSD"],
    "LONDON_CLOSE": ["EURUSD", "GBPUSD", "XAUUSD"],
    "NY_OPEN":      ["EURUSD", "GBPUSD", "XAUUSD", "US30", "NAS100", "USDCAD"],
    "NY_PM":        ["US30", "NAS100", "US500", "USDCAD"],
    "ASIAN_OPEN":   ["USDJPY", "AUDUSD", "NZDUSD", "BTCUSD"],
    "SYDNEY_OPEN":  ["AUDUSD", "NZDUSD", "USDJPY"],
    "NONE":         [],
}

# Limites paires actives
MAX_ACTIVE_PAIRS           = 6    # Max simultanés en Killzone
MAX_WATCH_PAIRS            = 10   # En veille — analysées toutes les 15 min
MAX_ACTIVE_OUT_OF_KILLZONE = 3    # Hors Killzone — économie ressources


# ══════════════════════════════════════════════════
# SECTION 4 — MACROS ICT
# Heures précises des fenêtres de manipulation
# Source : ICT 2022-2024 Mentorships (heures EST)
# Format : {id: {name, start:(h,m), end:(h,m)}}
# ══════════════════════════════════════════════════

MACROS = {
    1: {"name": "MACRO_1_LONDON_AM",   "start": (2, 33),  "end": (3, 0)},
    2: {"name": "MACRO_2_LONDON_AM2",  "start": (4, 3),   "end": (4, 30)},
    3: {"name": "MACRO_3_NY_PRE",      "start": (8, 50),  "end": (9, 10)},
    4: {"name": "MACRO_4_NY_AM",       "start": (9, 50),  "end": (10, 10)},
    5: {"name": "MACRO_5_NY_AM2",      "start": (10, 50), "end": (11, 10)},
    6: {"name": "MACRO_6_NY_LUNCH",    "start": (11, 50), "end": (12, 10)},
    7: {"name": "MACRO_7_NY_PM",       "start": (13, 10), "end": (13, 40)},
    8: {"name": "MACRO_8_NY_CLOSE",    "start": (15, 15), "end": (15, 45)},
}

# Macros prioritaires pour le scoring (Axe 1 — 20 pts)
MACROS_PRIORITY_HIGH   = [3, 4, 5, 7]   # Score 20 pts
MACROS_PRIORITY_MEDIUM = [1, 2, 6, 8]   # Score 10 pts
# Macros non listées = 0 pts

# CBDR : range calculé entre 17h-20h EST
CBDR_START_H       = 17
CBDR_END_H         = 20
CBDR_EXPLOSIVE_PIPS = 40  # KS8 : si CBDR > 40 pips → Macro 1/2/8 suspendus


# ══════════════════════════════════════════════════
# SECTION 5 — KILLSWITCHES KB5
# Les 9 règles d'arrêt absolu — source KB5 Section 11
# Classe immuable — ne pas instancier
# ══════════════════════════════════════════════════

class KS:
    """
    9 Killswitches officiels KB5.
    Vérification dans l'ordre VERIFICATION_ORDER avant chaque décision.
    Un seul KS activé = blocage immédiat, aucune exception.
    """

    # ── NIVEAU 1 : Bloquants absolus ──────────────
    # KS1 — Drawdown hebdomadaire
    KS1_DRAWDOWN_WEEK_PCT  = 5.0   # ≥ 5% → stop total
    KS1_STOP_DAYS          = 5     # Durée d'arrêt en jours

    # KS2 — Série de pertes
    KS2_LOSSES_CONSECUTIVE = 3     # 3 pertes A consécutives → stop
    KS2_STOP_HOURS         = 24    # Durée d'arrêt en heures

    # KS3 — Événement macro imminent
    KS3_NEWS_MINUTES       = 30    # NFP/FOMC dans ≤ 30 min → fermer tout
    KS3_HIGH_IMPACT_EVENTS = [
        "NFP", "FOMC", "CPI", "ECB", "BOE",
        "FED", "BOJ", "RBNZ", "RBA", "BOC",
        "GDP", "PMI_FLASH",
    ]

    # KS5 — ERL non sweepé
    # BooleanSweepERL doit être True avant tout trade
    # Valeur par défaut système : False au démarrage
    KS5_SWEEP_ERL_REQUIRED = True

    # KS6 — Règle du lundi
    KS6_MONDAY_CUTOFF_H    = 10    # Avant 10h NY → pas de trade
    KS6_MONDAY_CUTOFF_M    = 0     # si Seek & Destroy non validé

    # KS7 — News imminente (fermeture positions)
    KS7_NEWS_CLOSE_MINUTES = 15    # Dans ≤ 15 min → fermer tout
    KS7_SAFETY_PIPS        = 30    # SL ajouté pour fermeture sécurisée

    # ── NIVEAU 2 : Filtrants (par paire) ──────────
    # KS4 — Spread anormal
    KS4_SPREAD_MAX_PIPS    = 3     # > 3 pips sur majeure → suspendre paire
    # Note : pour XAUUSD/indices/crypto → voir MAX_SPREAD_PIPS

    # KS8 — CBDR explosif
    # Activé si CBDRExplosive = True ET Macro 1, 2 ou 8
    KS8_CBDR_EXPLOSIVE     = True  # Drapeau — calculé par CBDR_EXPLOSIVE_PIPS
    KS8_BLOCKED_MACROS     = [1, 2, 8]  # Macros bloquées si CBDR explosif

    # ── NIVEAU 3 : Décisionnel ────────────────────
    # KS9 — Score minimum absolu (Non lié à l'Accumulation, garde son rôle de filtre de score bas)
    KS9_SCORE_MINIMUM      = 65    # < 65 = INTERDIT, peu importe le setup

    # ── Ordre de vérification obligatoire ─────────
    # Respecter cet ordre exact avant chaque décision
    # KS5 → KS3 → KS7 → KS6 → KS1 → KS2 → KS8 → KS4 → KS9
    VERIFICATION_ORDER     = [5, 3, 7, 6, 1, 2, 8, 4, 9]


# ══════════════════════════════════════════════════
# SECTION 6 — CIRCUIT BREAKER GLOBAL
# Niveau 0 — priorité absolue sur tout le système
# Drawdown calculé en temps réel sur fenêtre glissante
# ══════════════════════════════════════════════════

class CB:
    """
    Circuit Breaker Global — niveau 0 dans la hiérarchie.
    Écrase tous les autres composants sans exception.
    """
    # Niveau 1 — Alerte orange
    ALERT_PCT      = 3.0   # -3% en 4h → réduire taille 50%
    ALERT_WINDOW_H = 4

    # Niveau 2 — Pause rouge
    PAUSE_PCT      = 5.0   # -5% en 2h → stop nouveaux trades
    PAUSE_WINDOW_H = 2

    # Niveau 3 — Arrêt total noir
    STOP_PCT       = 8.0   # -8% en 2h → fermer tout + déconnecter
    STOP_WINDOW_H  = 2

    # Actions par niveau
    ALERT_ACTION   = "REDUCE_SIZE_50"
    PAUSE_ACTION   = "STOP_NEW_TRADES"
    STOP_ACTION    = "CLOSE_ALL_DISCONNECT"

    # Reprise après arrêt total
    RESUME_MANUAL_ONLY = True  # Uniquement sur action Patron


# ══════════════════════════════════════════════════
# SECTION 7 — SCORING KB5
# Seuils différenciés par type de trade
# Source : KB5 + corrections P1 (cohérence scalp)
# ══════════════════════════════════════════════════

class Score:
    """Seuils d'exécution par type de trade."""

    # Seuils EXECUTE
    SWING_EXECUTE    = 85   # D1/Weekly
    INTRADAY_EXECUTE = 80   # H4/H1
    SCALP_EXECUTE    = 75   # M15/M5/M1

    # Seuil WATCH (tous types)
    WATCH            = 65

    # Seuil NO_TRADE absolu (Score insuffisant)
    NO_TRADE         = 65   # Cohérence avec KS9_SCORE_MINIMUM

    # Axes du scoring KB5 (total = 100 pts)
    AXE_TIMING       = 20   # Axe 1 — Killzone / Macro
    AXE_ERL_SWEEP    = 20   # Axe 2 — BooleanSweepERL
    AXE_PD_ARRAY     = 20   # Axe 3 — Qualité zone entrée
    AXE_TARGET_DOL   = 20   # Axe 4 — Target RR vs DOL
    AXE_SMT          = 20   # Axe 5 — Corrélation intermarket

    # Bonus
    BONUS_CASCADE_FRACTAL = 15  # MN→W→D1→H4→H1→M15 alignés
    BONUS_ENIGMA_LEVEL    = 10  # Entrée sur .00/.20/.50/.80
    BONUS_SILVER_BULLET   = 10  # Silver Bullet confirmé
    BONUS_WEEKLY_TEMPLATE =  5  # Template hebdomadaire connu
    BONUS_FIRST_FVG       =  5  # 1st Presented FVG utilisé

    # Malus
    MALUS_PREMIUM_HTF    = -20  # Prix > T20EQ en zone Premium — swing long
    MALUS_ENIGMA_MISS    = -15  # Target non sur niveau Enigma
    MALUS_MONDAY_NO_SD   = -10  # Lundi sans S&D validé
    MALUS_BAD_SETUP      = -10  # Setup récemment perdant (Performance Memory)

    # Scalp : garde-fous supplémentaires
    # Score 75-79 EXECUTE seulement si les 3 conditions sont réunies
    SCALP_REQUIRE_KILLZONE       = True
    SCALP_REQUIRE_CISD_OR_SILVER = True
    SCALP_REQUIRE_M15_CONFIRM    = True


# ══════════════════════════════════════════════════
# SECTION 8 — STATUTS SYSTÈME
# Utilisés par tous les composants pour communication
# ══════════════════════════════════════════════════

class Status:
    """Statuts officiels du système Sentinel Pro."""

    # Connexion Gateway
    CONNECTED    = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    RECONNECTING = "RECONNECTING"

    # Paire (Gestionnaire de Paires)
    ACTIVE  = "ACTIVE"    # Analyse temps réel
    WATCH   = "WATCH"     # Analyse toutes les 15 min
    DORMANT = "DORMANT"   # Analyse toutes les 60 min
    FROZEN  = "FROZEN"    # Bloquée (anomalie / news)

    # News Sentinel
    NEWS_CLEAR   = "NEWS_CLEAR"    # Aucune news imminente
    NEWS_CAUTION = "NEWS_CAUTION"  # T-60 à T-30 → réduire taille
    NEWS_FREEZE  = "NEWS_FREEZE"   # T-15 → bloquer tout

    # Circuit Breaker
    CB_CLEAR  = "CB_CLEAR"
    CB_ALERT  = "CB_ALERT"   # Niveau 1 — alerte
    CB_PAUSE  = "CB_PAUSE"   # Niveau 2 — pause
    CB_STOP   = "CB_STOP"    # Niveau 3 — arrêt total

    # Verdicts
    EXECUTE  = "EXECUTE"
    WATCH    = "WATCH"
    NO_TRADE = "NO_TRADE"
    INTERDIT = "INTERDIT"   # Règle absolue (Gateway, KS bloquant, ACCUMULATION_BLOCK, etc.)

    # SOD — State of Delivery
    SOD_ACCUMULATION      = "ACCUMULATION"
    SOD_MANIPULATION      = "MANIPULATION"
    SOD_STRONG_DIST       = "STRONG_DISTRIBUTION"
    SOD_WEAK_DIST         = "WEAK_DISTRIBUTION"
    SOD_UNKNOWN           = "UNKNOWN"

    # Freshness PD Arrays
    FRAIS    = "FRAIS"
    MITIGE   = "MITIGÉ"
    REVISITE = "REVISITÉ"
    INVALIDE = "INVALIDE"


# ══════════════════════════════════════════════════
# SECTION 9 — FRESHNESS PD ARRAYS
# Facteur multiplicateur appliqué au score
# selon l'état de fraîcheur de la zone
# ══════════════════════════════════════════════════

FRESHNESS_SCORE = {
    "FRAIS":    1.0,   # Zone jamais touchée — pleine valeur
    "MITIGÉ":   0.7,   # Zone partiellement touchée — valeur réduite
    "REVISITÉ": 0.4,   # Zone touchée plusieurs fois — faible valeur
    "INVALIDE": 0.0,   # Zone invalidée — ne pas utiliser
}


# ══════════════════════════════════════════════════
# SECTION 10 — SPREAD MAX PAR INSTRUMENT
# Utilisé par KS4 et Behaviour Shield
# Valeurs en pips (1 pip = 0.0001 pour FX)
# Chaque instrument a son propre seuil
# ══════════════════════════════════════════════════

MAX_SPREAD_PIPS = {
    # Forex majeurs (standard)
    "EURUSD": 3,   "GBPUSD": 3,   "USDJPY": 3,
    "AUDUSD": 3,   "USDCAD": 3,   "USDCHF": 3,
    "NZDUSD": 3,   "EURGBP": 4,   "EURJPY": 4,
    "GBPJPY": 5,
    # Forex 'm' — Exness
    "EURUSDm": 3,  "GBPUSDm": 3,  "USDJPYm": 3,
    "AUDUSDm": 3,  "USDCADm": 3,  "USDCHFm": 3,
    "NZDUSDm": 3,
    # Métaux
    "XAUUSD":  30,  "XAUUSDm": 30,
    "XAGUSD":  50,  "XAGUSDm": 50,
    # Énergie
    "XTIUSD":  50,  "XBRUSD":  50,
    "USOILm":  50,  "UKOILm":  50,
    # Indices
    "US30":    8,   "NAS100":  8,   "US100":  8,
    "SPX500":  5,   "US500":   5,
    "USTECm":  8,   "US500m":  5,
    "DE30m":   8,   "UK100m":  8,
    # Crypto
    "BTCUSD":  100, "BTCUSDm": 100,
    "ETHUSD":  80,  "ETHUSDm": 80,
    # DXY
    "DXYm":    2,
}


# ══════════════════════════════════════════════════
# SECTION 11 — GATEWAY & CONNEXION
# Paramètres de robustesse de la connexion MT5
# ══════════════════════════════════════════════════

class Gateway:
    HEARTBEAT_INTERVAL_SEC   = 10    # Vérification connexion toutes les 10 sec
    RECONNECT_TIMEOUT_SEC    = 120   # Déconnecté > 2 min → annuler tout
    RECONNECT_WAIT_SEC       = 30    # Attendre avant chaque tentative
    MAX_RECONNECT_ATTEMPTS   = 5     # Tentatives max avant alerte critique
    TICK_UPDATE_INTERVAL_SEC = 1     # Behaviour Shield : max 1 tick/sec/paire


# ══════════════════════════════════════════════════
# SECTION 12 — BEHAVIOUR SHIELD
# Protège contre le bannissement par le broker
# Liste blanche = actions jamais retardées
# ══════════════════════════════════════════════════

class BehaviourShield:
    MAX_ORDERS_PER_DAY     = 50    # Limite journalière globale
    MIN_ORDER_INTERVAL_SEC = 3     # Min 3 sec entre deux actions MT5
    MIN_CANCEL_DELAY_SEC   = 30    # Min 30 sec avant annulation volontaire
    RANDOM_DELAY_MIN_SEC   = 1     # Délai aléatoire min (comportement humain)
    RANDOM_DELAY_MAX_SEC   = 5     # Délai aléatoire max

    # Actions JAMAIS soumises au délai (urgences niveau 1)
    EXEMPT_ACTIONS = [
        "MOVE_SL",               # Déplacement stop loss
        "CLOSE_POSITION",        # Fermeture position
        "CANCEL_KILLSWITCH",     # Annulation sur KS activé
        "CANCEL_CIRCUIT_BREAKER",# Annulation sur CB niveau 3
        "CANCEL_NEWS_FREEZE",    # Annulation sur News T-15
        "CANCEL_DISCONNECT",     # Annulation sur coupure Gateway
    ]


# ══════════════════════════════════════════════════
# SECTION 13 — DATA STORE
# Paramètres de stockage et gestion mémoire
# ══════════════════════════════════════════════════

class DataStore:
    BACKUP_INTERVAL_SEC  = 300    # Backup toutes les 5 min
    BACKUP_DIR           = "backups/"
    MAX_TICKS_PER_PAIR   = 1000   # Buffer circulaire ticks
    MAX_DATA_AGE_SEC     = 60     # Donnée considérée fraîche si < 60 sec


# ══════════════════════════════════════════════════
# SECTION 14 — RISK MANAGEMENT
# Paramètres de capital — alignés KB5
# ══════════════════════════════════════════════════

class Risk:
    # Taille de position par type (% du capital)
    SWING_PCT    = 0.5   # Swing — risque réduit (durée longue)
    INTRADAY_PCT = 1.0   # Intraday — standard
    SCALP_PCT    = 0.5   # Scalp — risque réduit (SL serré)

    # Limites globales
    MAX_DAILY_RISK_PCT       = 3.0   # 3% max par jour toutes positions
    MAX_EXPOSURE_PER_PAIR_PCT= 2.0   # 2% max sur une même paire

    # Réductions automatiques selon volatilité
    VOLATILITY_HIGH_REDUCE   = 0.70  # ATR > 1.5x → taille × 0.70
    VOLATILITY_EXTREME_REDUCE= 0.30  # ATR > 2x   → taille × 0.30
    VOLATILITY_CRASH_REDUCE  = 0.00  # ATR > 3x   → FREEZE total

    # Seuils ATR
    ATR_HIGH_MULTIPLIER    = 1.5
    ATR_EXTREME_MULTIPLIER = 2.0
    ATR_CRASH_MULTIPLIER   = 3.0

    # Corrélation — seuils dynamiques (Correlation Engine)
    CORR_IDENTICAL_THRESHOLD = 0.85  # > 0.85 → compte comme 1 trade
    CORR_HIGH_THRESHOLD      = 0.60  # 0.60-0.85 → compte comme 1.5 trade
    # < 0.60 → indépendant → compte comme 2 trades

    # Performance Memory — fenêtre glissante
    MEMORY_WINDOW_DAYS     = 21      # 3 semaines
    MEMORY_WEIGHT_W1       = 0.50    # Semaine la plus récente
    MEMORY_WEIGHT_W2       = 0.30
    MEMORY_WEIGHT_W3       = 0.20


# ══════════════════════════════════════════════════
# SECTION 15 — ENIGMA — NIVEAUX ALGORITHMIQUES
# Institutional Pricing Theory
# Niveaux .00 / .20 / .50 / .80
# ══════════════════════════════════════════════════

ENIGMA_LEVELS_PIPS = [0, 20, 50, 80]   # En pips dans la figure
ENIGMA_TOLERANCE   = 2                  # ±2 pips de tolérance

# Bonus/malus scoring selon Enigma
ENIGMA_TARGET_BONUS  = 10   # Target sur niveau Enigma → +10 pts
ENIGMA_TARGET_MALUS  = -15  # Target hors niveau Enigma → -15 pts
ENIGMA_ENTRY_BONUS   = 10   # Entrée sur niveau Enigma → +10 pts


# ══════════════════════════════════════════════════
# SECTION 16 — LOGGING
# ══════════════════════════════════════════════════

class Log:
    DIR      = "logs/"
    FILE     = "sentinel_pro.log"
    MAX_MB   = 10     # Rotation à 10 MB
    BACKUPS  = 5      # Garder 5 fichiers
    FORMAT   = "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s"
    DATE_FMT = "%Y-%m-%d %H:%M:%S"

# ══════════════════════════════════════════════════
# SECTION 17 — TRADING (compatibilité main.py)
# ══════════════════════════════════════════════════

class Trading:
    BOT_MAGIC_NUMBER         = 20260101
    ACTIVE_PAIRS             = [
        "EURUSDm", "GBPUSDm", "USDJPYm", "USDCHFm", "USDCADm",
        "AUDUSDm", "NZDUSDm", "USTECm",  "US500m",  "DE30m",
        "UK100m",  "XAUUSDm", "XAGUSDm", "USOILm",  "UKOILm",
        "BTCUSDm", "DXYm",    "ETHUSDm",
    ]
    CLOSE_ON_EXIT            = False
    MAX_DEVIATION_POINTS     = 20
    MAX_OPEN_POSITIONS       = 3
    MAX_POSITIONS_PER_PAIR   = 1
    MIN_ORDER_INTERVAL_SEC   = 300