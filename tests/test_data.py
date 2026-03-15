# tools/test_data.py
import MetaTrader5 as mt5
from dotenv import load_dotenv
import os, sys
sys.path.insert(0, os.getcwd())

load_dotenv()

login    = int(os.getenv("MT5_LOGIN",    "0"))
password = os.getenv("MT5_PASSWORD",     "")
server   = os.getenv("MT5_SERVER",       "")
path     = os.getenv("MT5_PATH",         "")

# Connexion MT5
mt5.initialize(path=path, login=login,
               password=password, server=server)

# Test chargement bougies EURUSD H1
rates = mt5.copy_rates_from_pos("EURUSDm",
                                 mt5.TIMEFRAME_H1, 0, 100)
if rates is None or len(rates) == 0:
    print("❌ Bougies EURUSD H1 non chargées")
else:
    print(f"✅ EURUSD H1 — {len(rates)} bougies chargées")
    print(f"   Dernière bougie close : {rates[-1]['close']}")

# Test chargement bougies XAUUSD M15
rates2 = mt5.copy_rates_from_pos("XAUUSDm",
                                  mt5.TIMEFRAME_M15, 0, 100)
if rates2 is None or len(rates2) == 0:
    print("❌ Bougies XAUUSD M15 non chargées")
else:
    print(f"✅ XAUUSD M15 — {len(rates2)} bougies chargées")
    print(f"   Dernière bougie close : {rates2[-1]['close']}")

# Test tick EURUSD
tick = mt5.symbol_info_tick("EURUSDm")
if tick:
    print(f"✅ Tick EURUSD — Bid: {tick.bid} Ask: {tick.ask}")
else:
    print("❌ Tick EURUSD indisponible")

mt5.shutdown()
print("\nPhase 1 terminée.")
