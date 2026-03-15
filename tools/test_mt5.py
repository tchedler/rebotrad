# tools/test_mt5.py
import MetaTrader5 as mt5
from dotenv import load_dotenv
import os

load_dotenv()

login    = int(os.getenv("MT5_LOGIN",    "0"))
password = os.getenv("MT5_PASSWORD",     "")
server   = os.getenv("MT5_SERVER",       "")
path     = os.getenv("MT5_PATH",         "")

print(f"Tentative connexion...")
print(f"Login  : {login}")
print(f"Server : {server}")

ok = mt5.initialize(
    path     = path,
    login    = login,
    password = password,
    server   = server,
)

if ok:
    info = mt5.account_info()
    print(f"✅ Connecté — Compte : {info.login}")
    print(f"   Equity  : {info.equity}")
    print(f"   Serveur : {info.server}")
    mt5.shutdown()
else:
    err = mt5.last_error()
    print(f"❌ Échec connexion : {err}")
