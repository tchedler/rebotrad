
import MetaTrader5 as mt5
import os
from dotenv import load_dotenv
import pathlib

# Load .env if exists
env_path = pathlib.Path('c:/Users/djerm/Desktop/bottrading/sentinel_pro/.env')
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

login = int(os.getenv("MT5_LOGIN", 0))
password = os.getenv("MT5_PASSWORD", "")
server = os.getenv("MT5_SERVER", "")
path = os.getenv("MT5_PATH", "")

print(f"Connecting to {server} for account {login}...")

if not mt5.initialize(path=path):
    print(f"initialize() failed, error code = {mt5.last_error()}")
    quit()

authorized = mt5.login(login, password, server)
if authorized:
    print(f"Connected to account {login}")
    account_info = mt5.account_info()._asdict()
    print(f"Account Info: {account_info}")
    
    positions = mt5.positions_get()
    if positions:
        print(f"Found {len(positions)} positions:")
        for p in positions:
            print(p._asdict())
    else:
        print("No open positions found.")
        
    orders = mt5.orders_get()
    if orders:
        print(f"Found {len(orders)} pending orders:")
        for o in orders:
            print(o._asdict())
    else:
        print("No pending orders found.")
else:
    print(f"failed to connect to account {login}, error code = {mt5.last_error()}")

mt5.shutdown()
