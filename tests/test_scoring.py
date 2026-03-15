# tests/test_scoring.py
import MetaTrader5 as mt5
from dotenv import load_dotenv
import os, sys
sys.path.insert(0, os.getcwd())

load_dotenv()

login    = int(os.getenv("MT5_LOGIN",    "0"))
password = os.getenv("MT5_PASSWORD",     "")
server   = os.getenv("MT5_SERVER",       "")
path     = os.getenv("MT5_PATH",         "")

mt5.initialize(path=path, login=login,
               password=password, server=server)

pair = "EURUSDm"

# Test récupération multi-timeframes
timeframes = {
    "M15": mt5.TIMEFRAME_M15,
    "H1":  mt5.TIMEFRAME_H1,
    "H4":  mt5.TIMEFRAME_H4,
    "D1":  mt5.TIMEFRAME_D1,
}

print(f"\nTest chargement pyramide KB5 — {pair}")
print("─" * 40)

all_ok = True
for tf_name, tf_val in timeframes.items():
    rates = mt5.copy_rates_from_pos(pair, tf_val, 0, 200)
    if rates is None or len(rates) == 0:
        print(f"❌ {tf_name} — aucune bougie")
        all_ok = False
    else:
        high  = max(r['high']  for r in rates)
        low   = min(r['low']   for r in rates)
        close = rates[-1]['close']
        print(f"✅ {tf_name} — {len(rates)} bougies | "
              f"Close: {close} | "
              f"Range: {round(high-low, 5)}")

print("─" * 40)
if all_ok:
    print(f"\n✅ Pyramide KB5 chargeable sur {pair}")
    print("   Phase 2 OK — prêt pour Supervisor")
else:
    print(f"\n❌ Certains timeframes manquants")

mt5.shutdown()
