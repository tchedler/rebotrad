"""
config/settings.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sentinel Pro KB5 — Configuration d'environnement

RESPONSABILITÉ UNIQUE :
→ Credentials MT5 (depuis .env)
→ Listes de paires surveillées
→ Chemins fichiers
→ Flags d'environnement (dev/prod/paper)
→ Niveau de log

NE PAS DUPLIQUER les constantes de constants.py.
Toute règle KB5 appartient à constants.py.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
from dotenv import load_dotenv
from config.constants import PAIR_MARKET_TYPE, MarketType

load_dotenv()


# ══════════════════════════════════════════════════
# SECTION 1 — CREDENTIALS EXNESS MT5
# Jamais en dur dans le code — toujours via .env
# ══════════════════════════════════════════════════

MT5_LOGIN    = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER   = os.getenv("MT5_SERVER",   "Exness-MT5Real")
MT5_PATH     = os.getenv(
    "MT5_PATH",
    "C:/Program Files/Exness MT5 Terminal/terminal64.exe"
)

# Validation au démarrage
def validate_credentials() -> bool:
    """Vérifie que les credentials sont bien chargés depuis .env"""
    if MT5_LOGIN == 0:
        raise EnvironmentError(
            "MT5_LOGIN manquant dans .env — "
            "Créez le fichier .env à la racine du projet."
        )
    if not MT5_PASSWORD:
        raise EnvironmentError("MT5_PASSWORD manquant dans .env")
    if not MT5_SERVER:
        raise EnvironmentError("MT5_SERVER manquant dans .env")
    return True


# ══════════════════════════════════════════════════
# SECTION 2 — PAIRES SURVEILLÉES
# Organisées par catégorie de marché
# Utilisé par le Gestionnaire de Paires
# ══════════════════════════════════════════════════

PAIRS_FOREX = [
    "EURUSD", "GBPUSD", "USDJPY",
    "AUDUSD", "USDCAD", "USDCHF",
    "NZDUSD", "EURGBP", "EURJPY", "GBPJPY",
]

PAIRS_METALS = [
    "XAUUSD",   # Or — volatilité élevée, spread spécifique
    "XAGUSD",   # Argent
]

PAIRS_INDICES = [
    "US30",     # Dow Jones — Venom Model actif
    "NAS100",   # Nasdaq  — Venom Model actif
    "US100",    # Nasdaq (nom alternatif Exness)
    "SPX500",   # S&P 500
    "US500",    # S&P 500 (nom alternatif Exness)
]

PAIRS_CRYPTO = [
    "BTCUSD",   # Bitcoin — marché 24h/24 7j/7
    "ETHUSD",   # Ethereum
]

PAIRS_OIL = [
    "XTIUSD",   # WTI Crude Oil (Exness)
    "XBRUSD",   # Brent Crude Oil
]

# Liste complète — source unique pour initialisation
ALL_PAIRS = (
    PAIRS_FOREX +
    PAIRS_METALS +
    PAIRS_INDICES +
    PAIRS_CRYPTO +
    PAIRS_OIL
)

# Paires actives au démarrage
# (modifiable par l'utilisateur depuis l'interface)
DEFAULT_ACTIVE_PAIRS = [
    "EURUSD",
    "GBPUSD",
    "XAUUSD",
    "USDJPY",
    "NAS100",
    "BTCUSD",
]


# ══════════════════════════════════════════════════
# SECTION 3 — ENVIRONNEMENT
# Flags de comportement selon le contexte
# ══════════════════════════════════════════════════

ENV          = os.getenv("ENV", "development")
# "development" → logs verbeux, assertions actives
# "production"  → logs INFO+, performance optimisée

PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"
# True  → simulation — aucun ordre réel envoyé
# False → live — ordres réels sur compte Exness

DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
# True → logs DEBUG activés + latences affichées

def is_production() -> bool:
    return ENV == "production" and not PAPER_TRADING

def is_paper() -> bool:
    return PAPER_TRADING


# ══════════════════════════════════════════════════
# SECTION 4 — CHEMINS FICHIERS
# Tous les répertoires du système en un seul endroit
# ══════════════════════════════════════════════════

BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR       = os.path.join(BASE_DIR, "logs")
BACKUP_DIR    = os.path.join(BASE_DIR, "backups")
REPORTS_DIR   = os.path.join(BASE_DIR, "reports")
DATA_DIR      = os.path.join(BASE_DIR, "data")

# Création automatique des répertoires si absents
for _dir in [LOG_DIR, BACKUP_DIR, REPORTS_DIR, DATA_DIR]:
    os.makedirs(_dir, exist_ok=True)


# ══════════════════════════════════════════════════
# SECTION 5 — LOGGING
# Niveau configurable par .env
# Format et rotation définis dans constants.py (Log)
# ══════════════════════════════════════════════════

LOG_LEVEL = os.getenv(
    "LOG_LEVEL",
    "DEBUG" if DEBUG_MODE else "INFO"
)


# ══════════════════════════════════════════════════
# SECTION 6 — HELPERS
# Fonctions utilitaires basées sur les settings
# ══════════════════════════════════════════════════

def get_market_type(pair: str) -> MarketType:
    """Retourne le type de marché d'une paire."""
    return PAIR_MARKET_TYPE.get(pair, MarketType.FOREX)

def is_crypto(pair: str) -> bool:
    return get_market_type(pair) == MarketType.CRYPTO

def is_gold(pair: str) -> bool:
    return get_market_type(pair) == MarketType.GOLD

def is_index(pair: str) -> bool:
    return get_market_type(pair) == MarketType.INDEX

def is_forex(pair: str) -> bool:
    return get_market_type(pair) == MarketType.FOREX

def get_pairs_by_type(market_type: MarketType) -> list:
    """Retourne toutes les paires d'un type donné."""
    return [
        pair for pair, mtype in PAIR_MARKET_TYPE.items()
        if mtype == market_type
    ]

def is_market_open_24h(pair: str) -> bool:
    """
    Crypto = marché ouvert 24h/24 7j/7.
    Tous les autres = fermés le weekend.
    """
    return is_crypto(pair)
