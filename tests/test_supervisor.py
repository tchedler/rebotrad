# tests/test_supervisor.py
import MetaTrader5 as mt5
from dotenv import load_dotenv
import os, sys
sys.path.insert(0, os.getcwd())

load_dotenv()

login    = int(os.getenv("MT5_LOGIN",    "0"))
password = os.getenv("MT5_PASSWORD",     "")
server   = os.getenv("MT5_SERVER",       "")
path     = os.getenv("MT5_PATH",         "")

print("\nTest Supervisor minimal — SENTINEL PRO KB5")
print("─" * 40)

# Test 1 — Connexion MT5
ok = mt5.initialize(path=path, login=login,
                    password=password, server=server)
if ok:
    info = mt5.account_info()
    print(f"✅ MT5 connecté — Equity: {info.equity}$")
else:
    print(f"❌ MT5 non connecté")
    sys.exit(1)

# Test 2 — Import modules critiques
try:
    from config.constants import Trading, Risk, Gateway, CB, KS, Score
    print(f"✅ constants.py — Trading.BOT_MAGIC_NUMBER: "
          f"{Trading.BOT_MAGIC_NUMBER}")
except Exception as e:
    print(f"❌ constants.py — {e}")

# Test 3 — DataStore
try:
    from datastore.data_store import DataStore
    ds = DataStore()
    print(f"✅ DataStore instancié")
except Exception as e:
    print(f"❌ DataStore — {e}")

# Test 4 — Import Supervisor
try:
    from supervisor.supervisor import Supervisor
    print(f"✅ Supervisor importé")
except Exception as e:
    print(f"❌ Supervisor — {e}")

# Test 5 — Import Dashboard
try:
    from dashboard.patron_dashboard import PatronDashboard
    print(f"✅ PatronDashboard importé")
except Exception as e:
    print(f"❌ PatronDashboard — {e}")

# Test 6 — Logs
import logging
from pathlib import Path
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    filename="logs/sentinel_kb5.log",
    level=logging.DEBUG
)
logging.info("Test log Phase 3 OK")
print(f"✅ Logs — fichier logs/sentinel_kb5.log créé")

print("─" * 40)
print("Phase 3 terminée.")
mt5.shutdown()
